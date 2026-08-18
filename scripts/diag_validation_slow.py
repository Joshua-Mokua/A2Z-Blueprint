#!/usr/bin/env python
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
