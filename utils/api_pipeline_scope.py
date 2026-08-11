"""utils/api_pipeline_scope.py — Server-side cascade scope helper
for pipeline API endpoints.

Authored v10.504 Phase 3 Arc α Batch α2 — Pipeline Cascade Scope.

Purpose
-------
Closes GAP-001 from PIPELINE_DOMAIN_AUDIT Section 10. Before this
module existed, `/api/pipeline/summary` and `/api/pipeline/deals`
returned all deals regardless of caller — RBAC was applied only
client-side in Streamlit via `get_visible_staff()` in
`pages/3_pipeline.py:47`. That left a visibility hole the moment
any non-Streamlit client (e.g. the React frontend being introduced
incrementally) called the endpoints.

This module supplies a server-side equivalent: given the
authenticated caller's identity, return the set of staff codes
they're allowed to see deals for. The pipeline endpoints (and any
future organ-specific endpoints in the loan workflow) filter their
results through this set.

Doctrine context
----------------
**"No duplicate business logic across presentation surfaces."**
The Streamlit page calls `get_visible_staff(user_data, staff_scores)`
from `utils.core_audit`. That function walks `REPORTING_TREE`
(declared in `utils/core.py:5489`) to determine which rows of a
provided `staff_scores` DataFrame the user is permitted to see.

This module REUSES `get_visible_staff` — it does not reimplement
the cascade walk. It just supplies the staff roster DataFrame
(loaded from `data/staff_register.xlsx`) that the API path would
otherwise lack, and projects the result down to a set of staff
codes for set-membership filtering.

Caching strategy
----------------
`staff_register.xlsx` is a ~1,438-row spreadsheet loaded from disk.
Reading it on every request would add measurable latency under
load (487 staff × ~20-100 requests/min at peak). We cache the
DataFrame at module level with a 60-second TTL — the roster
changes rarely (new hires, terminations, role changes are
admin-driven events that don't need second-by-second freshness
for pipeline visibility). 60s is the right ballpark: matches the
ratchet documented for similar admin-data caches in v10.494+.

References
----------
- `docs/architecture/PIPELINE_DOMAIN_AUDIT.md` Section 15.10 — RBAC
  visibility chain end-to-end map.
- `utils/core_audit.py:190` — `get_visible_staff(user_data, scores)`,
  the canonical cascade-walk function.
- `utils/core.py:5489` — `REPORTING_TREE` config (the source of
  truth for who-sees-whom).
- `data/staff_register.xlsx` — staff roster with Staff Code, Staff
  Name, Role, Unit, Region columns (verified same-turn).
"""
from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Optional, Set

# Module-level cache state
_ROSTER_CACHE: Optional["pd.DataFrame"] = None  # type: ignore[name-defined]
_ROSTER_CACHE_LOADED_AT: float = 0.0
_ROSTER_CACHE_LOCK = threading.Lock()
# CACHE LIFETIME (2026-08-10). Was 60 seconds, which meant the cache expired
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
_ROSTER_CACHE_TTL_SECONDS = 3600.0


def _get_staff_roster_path() -> Path:
    """Resolve the canonical staff_register.xlsx location.

    Resolution order:
      1. `data/staff_register.xlsx` under the repo root (the canonical
         path documented in TRANSITION_BRIEF and used by every other
         consumer — utils/actuals_engine.py, utils/bsc_audit_engine.py,
         utils/core.py).

    If the file is not present, callers receive an empty roster and
    `get_visible_staff_codes` defaults to "no visibility" (empty set,
    plus the caller's own code as a self-fallback). That is the
    safe-default: an authenticated user always sees their own deals,
    but seeing OTHER users' deals requires the roster.
    """
    repo_root = Path(__file__).resolve().parent.parent
    return repo_root / "data" / "staff_register.xlsx"


def _load_staff_roster_fresh() -> "pd.DataFrame":  # type: ignore[name-defined]
    """Read staff_register.xlsx fresh from disk. Does not consult cache.

    Returns
    -------
    pandas.DataFrame
        Always has columns: Staff Code (str), Staff Name (str),
        Role (str), Unit (str), Region (str). Empty DataFrame with
        those columns if the file is missing.
    """
    # Lazy import: pandas is heavy and the API module loads at
    # FastAPI startup; we only want the import cost when a request
    # actually needs roster data.
    import pandas as pd

    path = _get_staff_roster_path()
    if not path.exists():
        return pd.DataFrame(
            columns=["Staff Code", "Staff Name", "Role", "Unit", "Region"]
        )
    df = pd.read_excel(path)
    # Defensive: ensure Staff Code is a string. The Excel reader
    # often returns int when codes are numeric; downstream string
    # comparisons fail silently otherwise.
    if "Staff Code" in df.columns:
        df["Staff Code"] = df["Staff Code"].astype(str)
    return df


def get_staff_roster() -> "pd.DataFrame":  # type: ignore[name-defined]
    """Return the staff roster, cached for ``_ROSTER_CACHE_TTL_SECONDS``.

    Thread-safe via a module-level lock. Safe to call from any
    request handler.
    """
    global _ROSTER_CACHE, _ROSTER_CACHE_LOADED_AT

    now = time.monotonic()
    # Fast path: in-cache and not stale
    if (
        _ROSTER_CACHE is not None
        and (now - _ROSTER_CACHE_LOADED_AT) < _ROSTER_CACHE_TTL_SECONDS
    ):
        return _ROSTER_CACHE

    with _ROSTER_CACHE_LOCK:
        # Re-check inside the lock: another thread may have refreshed
        now = time.monotonic()
        if (
            _ROSTER_CACHE is not None
            and (now - _ROSTER_CACHE_LOADED_AT) < _ROSTER_CACHE_TTL_SECONDS
        ):
            return _ROSTER_CACHE
        _ROSTER_CACHE = _load_staff_roster_fresh()
        _ROSTER_CACHE_LOADED_AT = now
        return _ROSTER_CACHE


def invalidate_staff_roster_cache() -> None:
    """Clear the roster cache. For admin endpoints that mutate the
    register (future arc) and for tests."""
    global _ROSTER_CACHE, _ROSTER_CACHE_LOADED_AT
    with _ROSTER_CACHE_LOCK:
        _ROSTER_CACHE = None
        _ROSTER_CACHE_LOADED_AT = 0.0



def _is_exco_full_funnel_member(user_data: dict) -> bool:
    """C3c: True if this user's staff_code is a committee member granted the
    full_funnel flag — an EXCO-level member the admin has elevated to see the whole
    pipeline+credit funnel for planning (same broad view as the MD)."""
    code = str(user_data.get("staff_code", "") or "")
    if not code:
        return False
    try:
        from utils.api import _read_committee_palette
        for c in (_read_committee_palette() or []):
            for m in (c.get("members") or []):
                if str(m.get("staff_code", "") or "") == code and bool(m.get("full_funnel", False)):
                    return True
    except Exception:
        return False
    return False


def get_visible_staff_codes(user_data: dict) -> Set[str]:
    """Return the set of staff codes this user is permitted to see
    pipeline deals for.

    Wraps the canonical ``get_visible_staff`` function from
    ``utils.core_audit`` (which walks ``REPORTING_TREE``), supplying
    the staff roster DataFrame the API path would otherwise lack.

    Returns
    -------
    set[str]
        Staff codes (as strings) the user can see. Always includes
        the user's own staff_code as a floor — even if the roster
        lookup yields nothing, an authenticated user sees their own
        deals.

        For admins / MD / roles in ``_ALL_VIEW_ROLES``,
        ``get_visible_staff`` returns the full roster — this function
        therefore returns the full roster's Staff Code set.

    Notes
    -----
    This function does NOT itself decide RBAC policy. It is a thin
    server-side adapter over the existing ``get_visible_staff``
    function. If ``REPORTING_TREE`` changes, this function's
    behaviour changes automatically — no duplicate-logic drift.
    """
    # Lazy import to avoid loading core_audit at module import time
    # (it pulls pandas + a lot of other surface area).
    from utils.core_audit import get_visible_staff

    # The user's own code is always included as a floor — protects
    # against edge cases where the roster doesn't yet contain a new
    # hire's record but the user is authenticated and viewing
    # their own draft deals.
    my_code = str(user_data.get("staff_code", "") or "")
    visible: Set[str] = {my_code} if my_code else set()

    roster = get_staff_roster()
    if roster is None or len(roster) == 0:
        return visible

    # C3c: a granted EXCO full-funnel member sees the whole roster (like the MD).
    if _is_exco_full_funnel_member(user_data) and "Staff Code" in roster.columns:
        return {str(c) for c in roster["Staff Code"].tolist() if c} | visible

    # get_visible_staff returns a DataFrame with the same columns
    # as the input, filtered to the caller's visible rows.
    try:
        visible_rows = get_visible_staff(user_data, roster)
    except Exception:
        # Defensive: if cascade-walk fails for any reason, fall back
        # to self-only visibility. This is the safe default — users
        # see less than expected, not more.
        return visible

    if visible_rows is None or len(visible_rows) == 0:
        return visible

    if "Staff Code" in visible_rows.columns:
        visible.update(
            str(c) for c in visible_rows["Staff Code"].tolist() if c
        )
    return visible


def filter_deals_by_visible_codes(
    deals: list, visible_codes: Set[str]
) -> list:
    """Filter a list of deal dicts to those whose staff_code or
    portfolio_owner_code is in the visible set.

    The portfolio_owner_code inclusion is per
    PIPELINE_DOMAIN_AUDIT Section 15.4 — a deal where the user is
    the portfolio owner (even if the active staff is someone else
    pursuing it) should still be visible to the portfolio owner
    for governance/oversight.

    Parameters
    ----------
    deals : list[dict]
        Deal records (typically from PipelineManager.get_deals()).
    visible_codes : set[str]
        Staff codes the caller can see.

    Returns
    -------
    list[dict]
        Filtered deals.
    """
    if not visible_codes:
        return []
    out: list = []
    for d in deals:
        sc = str(d.get("staff_code", "") or "")
        po = str(d.get("portfolio_owner_code", "") or "")
        if sc in visible_codes or (po and po in visible_codes):
            out.append(d)
    return out
