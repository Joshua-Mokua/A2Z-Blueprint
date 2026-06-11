"""
v10.532 Phase 5 Batch γ3 — Target Cascade read-only routes.

4 endpoints under /api/cascade. All require Bearer JWT. Wraps the
existing CascadeManager in utils/core.py — no new manager class.

Endpoint inventory (read-only — write surfaces deferred to γ5):
  - GET  /api/cascade/bank-targets?period=2026
      Bank-level KPI targets. Bank-wide read (anyone authenticated).
  - GET  /api/cascade/given-to-me?period=2026
      What was allocated to the caller (incoming cascade).
  - GET  /api/cascade/my-allocations?period=2026
      What the caller has cascaded out (outgoing).
  - GET  /api/cascade/coverage?from_code=X&kpi=Y&period=2026
      Variance analysis for a single KPI from a single source.
      Used to surface over/under-allocation (e.g. 22B target with
      224B allocated_sum — currently the dominant data pattern).

Why no cascade scope filter on bank-targets:
  Bank-level targets are public to all staff. Cascading them is the
  whole point of the Target Cascade — visibility drives engagement.
  No PII; no per-customer data.

Why per-caller filter on given-to-me / my-allocations:
  Reading what was allocated to YOU (or by YOU) is naturally scoped
  to your staff_code. Admins/MDs already see everyone via direct
  query against the underlying JSON; γ5 may add explicit override
  query params for manager drill-down.

Audit emission: NOT emitted on these endpoints. Cascade is high-volume
browse data; per-request audit would be noise. Edit-time audits (γ5)
will be louder.
"""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query

from utils.auth_jwt import get_current_user
from utils.core import CascadeManager


router = APIRouter(prefix="/api/cascade", tags=["cascade"])


# Module-level singleton — CascadeManager is lightweight (just file paths
# and a dict of loaded JSON) so a singleton is fine.
_cam: Optional[CascadeManager] = None

def _get_cam() -> CascadeManager:
    global _cam
    if _cam is None:
        _cam = CascadeManager()
    return _cam


# ── Helpers ─────────────────────────────────────────────────────────────

def _derive_unit(kpi: str) -> str:
    """
    Best-effort unit hint for the React UI.
    'percent' for ratios/scores/rates; 'count' for explicit counts;
    'currency' for everything else (typically KES).
    """
    k = kpi.lower()
    if "ratio" in k or "score" in k or "par" == k.strip().lower() or "%" in k:
        return "percent"
    if "number of" in k or "accounts" == k.split()[-1].lower() if " " in k else False:
        return "count"
    if k.startswith("new accounts") or "borrowers" in k or "productivity" in k:
        return "count"
    return "currency"


def _bank_targets_list(cam: CascadeManager, period: str) -> list[dict]:
    """
    Flatten cam.bank_targets dict into a sorted list scoped to period.
    Each item has kpi name, target value, buffer_pct, derived unit.
    """
    out: list[dict] = []
    suffix = f"|{period}"
    for key, val in (cam.bank_targets or {}).items():
        if not key.endswith(suffix):
            continue
        kpi = key[:-len(suffix)]
        out.append({
            "kpi":        kpi,
            "period":     period,
            "target":     float(val.get("target", 0)),
            "buffer_pct": float(val.get("buffer_pct", 0)),
            "unit":       _derive_unit(kpi),
        })
    out.sort(key=lambda x: x["kpi"])
    return out


def _safe_user_field(user: dict, *keys: str, default: str = "") -> str:
    for k in keys:
        v = user.get(k)
        if v:
            return str(v)
    return default


# ── Endpoints ───────────────────────────────────────────────────────────

@router.get("/bank-targets")
def fetch_bank_targets(
    period: str = Query("2026", description="Performance period, e.g. '2026'"),
    user: dict = Depends(get_current_user),
):
    """Bank-level KPI targets for a period."""
    cam = _get_cam()
    targets = _bank_targets_list(cam, period)
    return {
        "targets":  targets,
        "count":    len(targets),
        "period":   period,
        "source":   "cascade_manager",
    }


@router.get("/given-to-me")
def fetch_given_to_me(
    period: str = Query("2026"),
    user: dict = Depends(get_current_user),
):
    """
    What was allocated to the caller (incoming cascade).
    Returns a list of allocations from various 'from' parents,
    one item per KPI the caller appears as a 'to' for.
    """
    cam = _get_cam()
    staff_code = _safe_user_field(user, "staff_code", "username")
    staff_name = _safe_user_field(user, "full_name", "name")
    if not staff_code:
        raise HTTPException(status_code=400, detail="No staff_code on session.")

    allocations = cam.get_what_i_was_given(staff_code, period, staff_name)
    return {
        "allocations": allocations,
        "count":       len(allocations) if hasattr(allocations, "__len__") else 0,
        "staff_code":  staff_code,
        "staff_name":  staff_name,
        "period":      period,
        "source":      "cascade_manager",
    }


@router.get("/my-allocations")
def fetch_my_allocations(
    period: str = Query("2026"),
    user: dict = Depends(get_current_user),
):
    """
    What the caller has cascaded OUT (outgoing).
    Returns the caller's allocations across all KPIs they're a 'from' on.
    """
    cam = _get_cam()
    staff_code = _safe_user_field(user, "staff_code", "username")
    if not staff_code:
        raise HTTPException(status_code=400, detail="No staff_code on session.")

    allocations = cam.get_my_allocations(staff_code, period)
    return {
        "allocations": allocations,
        "count":       len(allocations) if hasattr(allocations, "__len__") else 0,
        "staff_code":  staff_code,
        "period":      period,
        "source":      "cascade_manager",
    }


@router.get("/coverage")
def fetch_coverage(
    from_code: str = Query(..., description="Cascade source staff code"),
    kpi: str       = Query(..., description="KPI name (must match bank_targets entries)"),
    period: str    = Query("2026"),
    user: dict     = Depends(get_current_user),
):
    """
    Variance analysis for a single (from_code, kpi, period) tuple.
    Surfaces over/under-allocation by returning total_target, allocated_sum,
    and the gap. Caller can be anyone authenticated (read-only, low-sensitivity).
    """
    cam = _get_cam()
    coverage = cam.cascade_coverage(from_code, kpi, period)
    if coverage is None:
        raise HTTPException(
            status_code=404,
            detail=f"No cascade entry for from_code={from_code} kpi={kpi} period={period}",
        )
    return {
        "coverage": coverage,
        "from_code": from_code,
        "kpi":       kpi,
        "period":    period,
        "source":    "cascade_manager",
    }
