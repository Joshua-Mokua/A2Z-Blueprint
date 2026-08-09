#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
RF1 - referral credit on the daily log, derived at READ TIME.

WHAT ALREADY EXISTED, and is therefore reused rather than rebuilt: the referral
lifecycle is complete. pending -> accepted / declined, with accept, decline,
re-refer and reassign endpoints, incoming / outgoing / returned queues, and a
referral_chain preserved across departments. RF1 adds no state machine.

WHAT WAS MISSING: /branch-log/auto-activities showed "Referral made" in the day's
timeline but nothing CREDITED it. The index did not move, staff typed the count
by hand, and nothing reconciled the two.

RULINGS (2026-08-09)
    Credit on ACCEPTANCE only - a sent-but-unaccepted referral is an intention,
    not an outcome.
    Referrals do NOT expire for the referrer; they escalate until a decision.

THOSE TWO TOGETHER FORCE THE DESIGN. Because a referral never expires, a decision
can arrive days later, when the day it was sent has already LOCKED (three
business days). A credit written into that log would be impossible.

So it is not written. utils/referral_credit derives it whenever the log is read,
exactly as carried_forward already derives variance. The lock prevents editing;
it has no bearing on a computed figure. A decision on day 9 heals day 2 on the
next read - no unlock, no correcting entry, no retroactive surprise.

CREDIT LANDS ON THE DAY THE REFERRAL WAS SENT. The work happened that day.

Counting is conservative: only referrals this person SENT, only those now
ACCEPTED, and each hop of a re-referred chain credits ITS OWN referrer on ITS
OWN day - nobody inherits someone else's credit.

THE DISPLAYED INDEX IS THE EFFECTIVE ONE. carried_forward now writes the credited
index back onto the row, plus referral_credit saying how much came from
referrals. Scoring the effective figure while displaying the stored one would
show a manager 10 - 25 = -12 and invite them to distrust the whole column.

MEASURED:
    1 accepted + 1 pending + 1 declined, same referrer, same day -> 1 credited
    the RECIPIENT of an accepted referral                        -> 0 credited
    a day with one accepted referral   index 10.0 -> 13.0, variance -15 -> -12

Cached for 60s because this is consulted once per grid row; re-reading the deal
store per row is the O(n) mistake this codebase has already made twice.
invalidate() is exposed so an acceptance can show immediately.

NOT IN THIS BATCH, deliberately:
  * making the daily-log referral field uneditable - that comes only AFTER this
    credit is live, or staff lose the ability to record referrals at all, and it
    needs the submit endpoint to ignore posted values, not just a read-only input
  * the escalation clock and the referral bench UI (RF2)

Usage (from project root, .venv active):
    python scripts\patch_rf1_referral_credit.py            # dry run
    python scripts\patch_rf1_referral_credit.py --apply    # write + .pre_rf1 backup
"""
import os
import shutil
import sys

MOD = os.path.join("utils", "referral_credit.py")
AN = os.path.join("utils", "branch_log_analytics.py")
BACKUP_SUFFIX = ".pre_rf1"

MODULE = r'''"""
utils/referral_credit — daily-log credit for referrals, derived at READ TIME.

RULINGS (2026-08-09)
    Credit on ACCEPTANCE only. A referral that has been sent but not yet
    accepted is an intention, not an outcome.

    Referrals do NOT expire for the referrer - they escalate until a decision is
    given.

THOSE TWO TOGETHER FORCE THE DESIGN. Because a referral never expires, a
decision can arrive days later, when the day it was sent has already locked
(three business days, utils.branch_log_state). A credit WRITTEN into that log
would be impossible.

So it is not written. The credit is DERIVED whenever the log is read, exactly as
carried_forward already derives variance. The lock prevents editing; it has no
bearing on a figure that is computed rather than stored. A decision on day 9
simply heals day 2's index the next time anyone looks - no unlock, no correcting
entry, no retroactive surprise in a balance.

CREDIT LANDS ON THE DAY THE REFERRAL WAS SENT, not the day it was accepted. The
work happened that day.

Counting is deliberately conservative: only referrals this person SENT, only
those now ACCEPTED, and only hops whose timestamp resolves to the day in
question. A deal that was re-referred onward credits each referrer for their own
hop, on their own day - the chain is preserved, so nobody inherits someone
else's credit.
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Optional

logger = logging.getLogger(__name__)

# The daily-log metric this credit lands on. Config-driven so the bank can point
# it at a different field without a code change.
DEFAULT_FIELD = "loans_referred"

_lock = threading.Lock()
_cache: Optional[dict] = None
_cache_at = 0.0
_TTL = 60.0          # seconds; the deal store is read once per minute at most


def credit_field() -> str:
    try:
        from utils.branch_log import load_log_config
        return str((load_log_config() or {}).get("referral_credit_field")
                   or DEFAULT_FIELD)
    except Exception:
        return DEFAULT_FIELD


def _stamp_day(value) -> str:
    """YYYY-MM-DD from a timestamp, tolerating date-only strings.

    Never parses a date-only value into a clock time - that is the defect TZ-1
    fixed on the frontend, and it would misfile a referral by a day here.
    """
    s = str(value or "").strip()
    return s[:10] if len(s) >= 10 else ""


def _build() -> dict:
    """{(staff_code, YYYY-MM-DD): accepted_referral_count}.

    One pass over the deal store. Cached for _TTL because this is consulted once
    per grid row, and re-reading the deals per row is the O(n) mistake this
    codebase has made twice already.
    """
    out: dict = {}
    try:
        from utils.core import PipelineManager
        from utils.staff_code import canon
        pm = PipelineManager()
        deals = list(getattr(pm, "deals", []) or [])
    except Exception as exc:
        logger.warning("referral credit could not read the deal store: %s", exc)
        return out

    for d in deals:
        if not d.get("is_referral"):
            continue
        # ACCEPTANCE ONLY. pending and declined credit nobody.
        if str(d.get("referral_status") or "") != "accepted":
            continue

        chain = d.get("referral_chain") or []
        if chain:
            # Each hop credits ITS OWN referrer, on the day that hop was made.
            for hop in chain:
                if not isinstance(hop, dict):
                    continue
                who = canon(hop.get("referred_by_code") or hop.get("by_code") or "")
                day = _stamp_day(hop.get("at") or hop.get("referred_at")
                                 or hop.get("timestamp"))
                if who and day:
                    out[(who, day)] = out.get((who, day), 0) + 1
        else:
            who = canon(d.get("referred_by_code") or d.get("created_by_code") or "")
            day = _stamp_day(d.get("referred_at") or d.get("created_at")
                             or d.get("open_date"))
            if who and day:
                out[(who, day)] = out.get((who, day), 0) + 1
    return out


def _map() -> dict:
    global _cache, _cache_at
    with _lock:
        if _cache is not None and (time.monotonic() - _cache_at) < _TTL:
            return _cache
    built = _build()
    with _lock:
        _cache, _cache_at = built, time.monotonic()
    return built


def invalidate() -> None:
    """Drop the cache - call after a referral is accepted so the credit shows
    immediately rather than up to a minute later."""
    global _cache, _cache_at
    with _lock:
        _cache, _cache_at = None, 0.0


def accepted_referrals_on(staff_code: str, day: str) -> int:
    """How many referrals this person sent on this day have since been accepted."""
    try:
        from utils.staff_code import canon
        key = (canon(staff_code), str(day)[:10])
    except Exception:
        return 0
    return int(_map().get(key, 0))


def credit_index_for(staff_code: str, day: str) -> float:
    """The index contribution those accepted referrals are worth."""
    n = accepted_referrals_on(staff_code, day)
    if not n:
        return 0.0
    try:
        from utils.branch_log import activity_weights
        w = float((activity_weights() or {}).get(credit_field(), 0) or 0)
    except Exception:
        return 0.0
    return round(n * w, 2)
'''

EFF_NEW = r'''def _effective_index(log: dict) -> float:
    """The index that counts toward variance for a given day log.

    - A stored 'index' is used when present (submit/auto-submit already computed it).
    - Otherwise recompute from the day's metric fields.
    Auto-submitted/partial days already carry a deficit-bearing index (only keyed hours),
    so no special-casing is needed here — the deficit is inherent in the lower index.
    Returned-but-unvalidated days use their current index; when later corrected + validated,
    the higher index naturally heals the running sum on the next read.
    """
    idx = log.get("index")
    if idx is not None:
        try:
            base = float(idx or 0)
        except (TypeError, ValueError):
            base = compute_index({k: log.get(k, 0) for k in metric_keys()})
    else:
        base = compute_index({k: log.get(k, 0) for k in metric_keys()})

    # REFERRAL CREDIT, derived not stored (ruling 2026-08-09). Referrals credit
    # on ACCEPTANCE and never expire, so a decision can land after the day has
    # locked. Adding it here means the day heals on the next read instead of
    # needing an unlock and a correcting entry.
    try:
        from utils.referral_credit import credit_index_for
        base += credit_index_for(str(log.get("staff_code", "") or ""),
                                 str(log.get("log_date", ""))[:10])
    except Exception:
        pass
    return round(base, 2)


'''

SURF_NEW = r'''        idx = _effective_index(r)
        # Surface the EFFECTIVE index on the row, and say how much of it came
        # from accepted referrals. Leaving the stored index on display while
        # scoring the effective one would show a manager 10 - 25 = -12 and
        # invite them to distrust the whole column.
        try:
            from utils.referral_credit import credit_index_for
            _rc = credit_index_for(str(r.get("staff_code", "") or ""),
                                   str(r.get("log_date", ""))[:10])
        except Exception:
            _rc = 0.0
        if _rc:
            r["referral_credit"] = _rc
        r["index"] = round(idx, 2)
'''


EFF_OLD = """    idx = log.get("index")
    if idx is not None:
        try:
            return float(idx or 0)
        except (TypeError, ValueError):
            pass
    return compute_index({k: log.get(k, 0) for k in metric_keys()})"""

SURF_OLD = "        idx = _effective_index(r)\n"


def main():
    apply = "--apply" in sys.argv
    if not os.path.isfile(AN):
        print("ABORT: %s not found. Run from the project root." % AN)
        return 1
    if os.path.exists(MOD):
        print("ABORT: %s already exists - RF1 looks applied." % MOD)
        return 1

    an = open(AN, encoding="utf-8").read()
    if "referral_credit" in an:
        print("ABORT: analytics already references referral_credit.")
        return 1
    if "_excused" not in an:
        print("ABORT: apply patch_e1_exceptions.py first.")
        return 1
    if an.count(EFF_OLD) != 1:
        print("ABORT: _effective_index body matched %d times." % an.count(EFF_OLD))
        return 1
    if an.count(SURF_OLD) != 1:
        print("ABORT: carried_forward index line matched %d times." % an.count(SURF_OLD))
        return 1

    # Replace the body of _effective_index, then the surfacing line.
    i = an.index("def _effective_index(log: dict) -> float:")
    j = an.index("def _excused(log: dict) -> bool:")
    an = an[:i] + EFF_NEW + an[j:]
    print("  ok  _effective_index - read-time referral credit")

    a = an.index("        idx = _effective_index(r)")
    b = an.index("        if not _is_working_day(r):", a)
    an = an[:a] + SURF_NEW + an[b:]
    print("  ok  carried_forward - effective index + referral_credit on the row")

    if an.count("def _effective_index(") != 1:
        print("ABORT: post-check - _effective_index defined %d times."
              % an.count("def _effective_index("))
        return 1
    if an.count("from utils.referral_credit import credit_index_for") != 2:
        print("ABORT: post-check - expected the credit import in exactly two places.")
        return 1
    for token in ("accepted_referrals_on", "invalidate", "referral_chain"):
        if token not in MODULE:
            print("ABORT: embedded module missing %r." % token)
            return 1
    print("  ok  post-checks clean")

    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        return 0

    open(MOD, "w", encoding="utf-8", newline="").write(MODULE)
    print("CREATED %s" % MOD)
    shutil.copy2(AN, AN + BACKUP_SUFFIX)
    open(AN, "w", encoding="utf-8", newline="").write(an)
    print("APPLIED %s  (backup: %s)" % (AN, os.path.basename(AN) + BACKUP_SUFFIX))

    import py_compile
    for path in (MOD, AN):
        try:
            py_compile.compile(path, doraise=True)
            print("  ok  %s compiles" % os.path.basename(path))
        except Exception as exc:
            print("  FAIL %s: %s" % (path, exc))
            return 1

    print("\nRestart uvicorn. Accepted referrals now credit the referrer's day,")
    print("including days that have already locked.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
