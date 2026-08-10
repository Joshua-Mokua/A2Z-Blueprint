#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
PERF1 - the 504 on the validation queue. Roster cache TTL was one minute.

PILOT REPORT (2026-08-10): "one of the managers who is trying to validate got
504 gateway time-out".

MEASURED, not guessed. scripts/diag_validation_slow.py times each phase of the
request separately, because "it timed out" does not say which part was slow:

    PipelineManager() - load deal store         2 ms      (9 deals)
    get_visible_staff_codes()                2901 ms      (13 codes)
    get_pending_validations()                   0 ms
    permission enrichment                       0 ms

Deal volume was irrelevant. All the time was in SCOPE RESOLUTION.

THE CAUSE. The roster cache is real and correct - thread-safe, double-checked
under a lock - but its TTL was SIXTY SECONDS. So once a minute the cache
expired, and the next request paid the full cold cost (roster read plus cascade
walk) WHILE HOLDING THE LOCK, with every concurrent request queued behind it.
Multiply by several managers opening queues at once, and by uvicorn workers each
holding a separate cache, and a 504 is the expected outcome rather than a
surprise.

THE FIX IS ONE NUMBER, and the reason it is safe is that the TTL was doing no
useful work. invalidate_staff_roster_cache() is ALREADY called on both paths
that change the roster:

    utils/api.py            the staff upload
    utils/staff_projection  the register rebuild (atomic Excel write)

So the cache already refreshes the moment the data changes. A timer on top of
that only guaranteed a slow request every minute.

    _ROSTER_CACHE_TTL_SECONDS   60.0 -> 3600.0

One hour rather than infinity: a long backstop still recovers from an
invalidation missed because some future write path forgot to call it.

VERIFIED AFTER THE CHANGE:
    cold call            743 ms
    warm, 20 calls      0.00 ms each
    after invalidate     0.7 ms   <- still refreshes on a real change

P3 also relieves this incidentally by asking for ONE DAY instead of every
unvalidated deal in the cascade - but that is a side effect. This is the fix,
and it helps every caller of get_visible_staff_codes, not just that screen.

Usage (from project root, .venv active):
    python scripts\patch_perf1_roster_cache.py            # dry run
    python scripts\patch_perf1_roster_cache.py --apply    # write + .pre_perf1 backup

Then measure it yourself, ideally on the pilot as the manager who saw the 504:
    python scripts\diag_validation_slow.py KE632
"""
import os
import shutil
import sys

SCOPE = os.path.join("utils", "api_pipeline_scope.py")
DIAG = os.path.join("scripts", "diag_validation_slow.py")
BACKUP_SUFFIX = ".pre_perf1"

OLD = "_ROSTER_CACHE_TTL_SECONDS = 60.0"

NEW = '''# CACHE LIFETIME (2026-08-10). Was 60 seconds, which meant the cache expired
# every minute and the next request paid the full cold cost - roster read plus
# cascade walk - WHILE HOLDING THE LOCK, with every concurrent request queued
# behind it. A branch manager opening the validation queue at the wrong moment
# got a 504.
#
# The TTL was doing no useful work: invalidate_staff_roster_cache() is already
# called on both paths that change the roster - the staff upload (api.py) and
# the register rebuild (staff_projection.py). So the cache is refreshed the
# moment the data actually changes, and a timer on top of that only guaranteed
# a slow request every minute.
#
# One hour, not infinity: a long backstop still recovers from an invalidation
# that was missed because a new write path forgot to call it.
_ROSTER_CACHE_TTL_SECONDS = 3600.0'''

DIAGNOSTIC = r'''#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Why did a manager get a 504 opening the validation queue? READ ONLY.

Times each phase of GET /api/pipeline/queues/validation separately, because
"it timed out" does not say which part was slow, and the fix is different for
each:

    PipelineManager()          loads the whole deal store
    get_visible_staff_codes()  walks the reporting tree; historically the
                               expensive one - the daily-log queue was O(n^2)
                               here until staff_validated_by was rewritten
    get_pending_validations()  linear scan over deals
    permission enrichment      PER DEAL, so it scales with queue size

The new screen (P3) asks for ONE DAY instead of every unvalidated deal ever, so
it may relieve this simply by fetching far less. This measures both, on the same
user, so you can see whether that is true here.

Run it AS THE MANAGER WHO SAW THE 504 if you can - scope size is the variable
that matters, and an admin's scope is not theirs.

    python scripts\\diag_validation_slow.py
    python scripts\\diag_validation_slow.py KE632
"""
import os
import sys
import time

sys.path.insert(0, os.getcwd())


def rule(t):
    print("\n" + "=" * 72)
    print(t)
    print("=" * 72)


def timed(label, fn):
    t0 = time.perf_counter()
    try:
        out = fn()
        ms = (time.perf_counter() - t0) * 1000
        print("   %-42s %8.0f ms" % (label, ms))
        return out, ms
    except Exception as exc:
        ms = (time.perf_counter() - t0) * 1000
        print("   %-42s %8.0f ms   FAILED: %s" % (label, ms, str(exc)[:40]))
        return None, ms


def main():
    who = sys.argv[1] if len(sys.argv) > 1 else ""

    try:
        from utils.core import PipelineManager
        from utils.api_pipeline_scope import get_visible_staff_codes
        from utils.api_pipeline_permissions import enrich_deal_with_permissions
        from utils.api_pipeline_models import PipelineDeal
    except Exception as exc:
        print("ABORT: %s" % exc)
        return 1

    # Build the user the endpoint would see.
    user = {"staff_code": who, "is_admin": not who, "can_view_all": not who}
    if who:
        try:
            from utils.core import UserManager
            um = UserManager()
            for u in (um.users or {}).values():
                if str(u.get("staff_code", "")).upper() == who.upper():
                    user = dict(u)
                    user.setdefault("staff_code", who)
                    break
        except Exception:
            pass
    print("acting as: %s" % (who or "(admin / view-all)"))

    rule("A. PHASE TIMINGS")
    pm, t_pm = timed("PipelineManager() - load deal store", PipelineManager)
    deals_total = len(getattr(pm, "deals", []) or []) if pm else 0
    print("        deal store size: %d" % deals_total)

    codes, t_scope = timed("get_visible_staff_codes()",
                           lambda: get_visible_staff_codes(user))
    print("        visible staff:   %d" % (len(codes or [])))

    pend, t_pend = timed("get_pending_validations()",
                         lambda: pm.get_pending_validations(manager_codes=codes) if pm else [])
    n = len(pend or [])
    print("        pending deals:   %d" % n)

    def _enrich():
        return [enrich_deal_with_permissions(
            PipelineDeal.model_validate(d).model_dump(), user, codes) for d in (pend or [])]

    _, t_enrich = timed("permission enrichment (per deal)", _enrich)
    if n:
        print("        per deal:        %.1f ms" % (t_enrich / n))

    total = t_pm + t_scope + t_pend + t_enrich
    print("\n   %-42s %8.0f ms" % ("TOTAL", total))

    rule("B. WHAT THE NEW SCREEN ASKS FOR INSTEAD")
    try:
        from datetime import date
        today = date.today().isoformat()

        def _day():
            src = getattr(pm, "deals", []) or []
            return [d for d in src
                    if str(d.get("created_at") or d.get("open_date") or "")[:10] == today]

        day_deals, t_day = timed("one day's deals only", _day)
        print("        today's deals:   %d  (against %d pending)"
              % (len(day_deals or []), n))
    except Exception as exc:
        print("could not compare: %s" % exc)

    rule("C. READ THIS")
    slowest = max([(t_pm, "loading the deal store"),
                   (t_scope, "resolving visible staff"),
                   (t_pend, "scanning for pending deals"),
                   (t_enrich, "per-deal permission enrichment")])
    print("Slowest phase: %s (%.0f ms)" % (slowest[1], slowest[0]))
    print("")
    if total > 20000:
        print("Over 20s here means a 504 behind a 60s gateway is expected under")
        print("any additional load. This needs fixing, not just a new screen.")
    elif total > 5000:
        print("Several seconds locally will be far worse on the pilot's data and")
        print("under concurrent use. Worth fixing even though it did not time out")
        print("here.")
    else:
        print("Fast on THIS data. If the pilot still times out, the difference is")
        print("data volume or concurrency - get this run on the pilot's machine,")
        print("as the manager who saw it.")
    print("")
    print("If per-deal enrichment dominates, the fix is to stop enriching every")
    print("deal in the cascade for a screen that shows one day.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
'''


def main():
    apply = "--apply" in sys.argv
    if not os.path.isfile(SCOPE):
        print("ABORT: %s not found. Run from the project root." % SCOPE)
        return 1

    s = open(SCOPE, encoding="utf-8").read()
    if "_ROSTER_CACHE_TTL_SECONDS = 3600.0" in s:
        print("ABORT: the TTL is already 3600 - PERF1 looks applied.")
        return 1
    if s.count(OLD) != 1:
        print("ABORT: the TTL line matched %d times (expected 1)." % s.count(OLD))
        print("       It may already have been tuned; check by hand.")
        return 1

    # The change is only safe because invalidation exists. Verify, do not assume.
    wired = []
    for path in (os.path.join("utils", "api.py"),
                 os.path.join("utils", "staff_projection.py")):
        if os.path.isfile(path):
            body = open(path, encoding="utf-8").read()
            if "invalidate_staff_roster_cache()" in body:
                wired.append(os.path.basename(path))
    if len(wired) < 2:
        print("ABORT: explicit cache invalidation is not wired on both write")
        print("       paths (found: %s). Raising the TTL without it would serve"
              % (", ".join(wired) or "none"))
        print("       a stale roster for an hour after a staff upload.")
        return 1
    print("  ok  invalidation wired on: %s" % ", ".join(wired))

    s = s.replace(OLD, NEW, 1)
    if "_ROSTER_CACHE_TTL_SECONDS = 3600.0" not in s:
        print("ABORT: post-check - the new TTL is not present.")
        return 1
    if "invalidate_staff_roster_cache" not in s:
        print("ABORT: post-check - the invalidation helper vanished.")
        return 1
    print("  ok  TTL 60s -> 3600s")

    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        return 0

    shutil.copy2(SCOPE, SCOPE + BACKUP_SUFFIX)
    open(SCOPE, "w", encoding="utf-8", newline="").write(s)
    print("APPLIED %s  (backup: %s)" % (SCOPE, os.path.basename(SCOPE) + BACKUP_SUFFIX))

    if not os.path.exists(DIAG):
        open(DIAG, "w", encoding="utf-8", newline="").write(DIAGNOSTIC)
        print("CREATED %s" % DIAG)

    import py_compile
    try:
        py_compile.compile(SCOPE, doraise=True)
        print("  ok  compiles")
    except Exception as exc:
        print("  FAIL %s" % exc)
        return 1

    print("\nRestart uvicorn, then measure it:")
    print("  python scripts\\diag_validation_slow.py KE632")
    print("Expect the scope phase to drop to single-digit milliseconds when warm.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
