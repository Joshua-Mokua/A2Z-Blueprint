"""
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
