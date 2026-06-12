"""
v10.536 Phase 7 Batch γ5a — Target Cascade routes (read + write).

Extends γ3a (read-only, 4 endpoints) with γ5a write endpoints:
  - PUT  /api/cascade/bank-targets   (MD-only — set a single bank target)
  - PUT  /api/cascade/allocations    (any leader — set cascade allocations for own staff_code)

Authorization:
  - bank-targets PUT: role == "Managing Director". 403 otherwise.
  - allocations PUT: from_code == caller's staff_code. 403 otherwise.

Audit emission: writes log via Python logging (not the _audit pipeline)
to avoid a circular import with utils.api. Full audit hookup is a follow-up.
"""

import logging
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, ConfigDict

from utils.auth_jwt import get_current_user
from utils.core import CascadeManager


router = APIRouter(prefix="/api/cascade", tags=["cascade"])
_log = logging.getLogger("a2z.cascade")


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
    """Best-effort unit hint for the React UI."""
    k = kpi.lower()
    if "ratio" in k or "score" in k or "par" == k.strip().lower() or "%" in k:
        return "percent"
    if "number of" in k or ("accounts" in k.split()[-1].lower() if " " in k else False):
        return "count"
    if k.startswith("new accounts") or "borrowers" in k or "productivity" in k:
        return "count"
    return "currency"


def _bank_targets_list(cam: CascadeManager, period: str) -> list[dict]:
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


def _enrich(user: dict) -> dict:
    """
    Merge JWT claims with the full user record from users.json.

    Canonical pattern mirrored from utils/api.py:526 — comment there
    says "Identity (from users.json — never trust JWT for these)".
    The JWT carries only username + token claims; staff_code, role,
    full_name etc. live in users.json. Endpoints that gate on those
    fields MUST do this lookup or they will silently fall back to
    username (causing data-scope misses) or to default "Staff" role
    (causing MD/permission misses).

    γ5b-hotfix1 (2026-06-12): added after live test showed /my-allocations
    returning (0) for the MD — root cause was user.get("staff_code")
    returning None because staff_code isn't in the JWT.
    """
    from utils.core import UserManager
    username = user.get("username", "")
    if not username:
        return dict(user)
    um = UserManager()
    full = um.users.get(username) or {}
    # users.json is canonical for identity + role; layer JWT on top
    # so JWT claims (iat, exp, etc.) survive.
    return {**user, **full}


def _is_md(user: dict) -> bool:
    """True if the caller is the Managing Director per the role registry.

    Lenient match: real-world user records have role strings like
    'Chief Executive & Managing Director' (William Mwanake's title) as
    well as the bare 'Managing Director' canonical form. Both should
    pass; non-MD director roles (e.g. 'Director Retail Banking') do not
    contain 'managing director' so they don't false-positive.

    NOTE: callers should pass an ENRICHED user dict (via _enrich) — the
    raw JWT user has no role field and would always fail the check.
    """
    role = str(user.get("role", "")).lower()
    return "managing director" in role


# ── READ endpoints (γ3a — unchanged) ─────────────────────────────────────

@router.get("/bank-targets")
def fetch_bank_targets(
    period: str = Query("2026"),
    user: dict = Depends(get_current_user),
):
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
    enriched = _enrich(user)
    staff_code = _safe_user_field(enriched, "staff_code", "username")
    staff_name = _safe_user_field(enriched, "full_name", "name")
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
    enriched = _enrich(user)
    staff_code = _safe_user_field(enriched, "staff_code", "username")
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
    from_code: str = Query(...),
    kpi: str       = Query(...),
    period: str    = Query("2026"),
    user: dict     = Depends(get_current_user),
):
    cam = _get_cam()
    coverage = cam.cascade_coverage(from_code, kpi, period)
    if coverage is None:
        raise HTTPException(
            status_code=404,
            detail=f"No cascade entry for from_code={from_code} kpi={kpi} period={period}",
        )
    return {
        "coverage":  coverage,
        "from_code": from_code,
        "kpi":       kpi,
        "period":    period,
        "source":    "cascade_manager",
    }


# ── WRITE endpoints (γ5a — new) ─────────────────────────────────────────

class SetBankTargetRequest(BaseModel):
    """PUT /api/cascade/bank-targets body. MD only."""
    model_config = ConfigDict(extra="forbid")
    kpi:        str   = Field(description="KPI name; must match an existing bank_targets key family")
    period:     str   = Field(default="2026")
    target:     float = Field(description="Bank-level target value (canonical units per KPI)")
    buffer_pct: float = Field(default=0, description="Stretch target buffer percentage (0..100)")


class AllocationRowIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    to_code: str   = Field(description="Recipient staff code")
    to_name: str   = Field(default="", description="Recipient display name (optional)")
    amount:  float = Field(description="Allocation amount (non-negative)")


class SetAllocationRequest(BaseModel):
    """PUT /api/cascade/allocations body. Caller must be from_code."""
    model_config = ConfigDict(extra="forbid")
    from_code:    str                   = Field(description="Cascade source — must equal caller's staff_code")
    kpi:          str                   = Field(description="KPI being cascaded")
    period:       str                   = Field(default="2026")
    total_target: float                 = Field(description="The from_code's own target being divided")
    allocations:  List[AllocationRowIn] = Field(default_factory=list, description="Per-recipient amounts")


@router.put("/bank-targets")
def set_bank_target(
    payload: SetBankTargetRequest,
    user: dict = Depends(get_current_user),
):
    """
    MD-only: set a bank-level target for (kpi, period).
    Wraps CascadeManager.set_bank_target. 403 for non-MD callers.
    """
    enriched = _enrich(user)
    if not _is_md(enriched):
        raise HTTPException(
            status_code=403,
            detail="Only the Managing Director can set bank targets.",
        )

    cam = _get_cam()
    cam.set_bank_target(
        payload.kpi,
        payload.period,
        payload.target,
        payload.buffer_pct,
    )
    _log.info(
        "CASCADE_BANK_TARGET_SET by=%s kpi=%s period=%s target=%s buffer_pct=%s",
        enriched.get("username"), payload.kpi, payload.period, payload.target, payload.buffer_pct,
    )

    return {
        "ok":         True,
        "kpi":        payload.kpi,
        "period":     payload.period,
        "target":     payload.target,
        "buffer_pct": payload.buffer_pct,
        "source":     "cascade_manager",
    }


@router.put("/allocations")
def set_allocations(
    payload: SetAllocationRequest,
    user: dict = Depends(get_current_user),
):
    """
    Set/replace the cascade allocations from (from_code, kpi, period).
    Caller must equal payload.from_code (you can only cascade YOUR OWN targets).
    Wraps CascadeManager.set_allocation.
    """
    enriched = _enrich(user)
    caller_code = _safe_user_field(enriched, "staff_code", "username")
    if not caller_code:
        raise HTTPException(status_code=400, detail="No staff_code on session.")

    # Scope: from_code MUST be the caller's own staff_code.
    if payload.from_code.strip() != caller_code.strip():
        raise HTTPException(
            status_code=403,
            detail=(
                f"You can only cascade allocations for your own staff_code "
                f"(yours: {caller_code}, requested: {payload.from_code})."
            ),
        )

    # Reject negative amounts at the API gate (defence in depth even though
    # the UI should enforce this too).
    for row in payload.allocations:
        if row.amount < 0:
            raise HTTPException(
                status_code=400,
                detail=f"Allocation amount must be non-negative (got {row.amount} for {row.to_code}).",
            )

    cam = _get_cam()
    result = cam.set_allocation(
        from_code=payload.from_code,
        kpi=payload.kpi,
        period=payload.period,
        allocations=[a.model_dump() for a in payload.allocations],
        total_target=payload.total_target,
        updated_by=caller_code,
    )

    _log.info(
        "CASCADE_ALLOCATION_SET by=%s kpi=%s period=%s recipients=%d total=%s",
        caller_code, payload.kpi, payload.period, len(payload.allocations), payload.total_target,
    )

    return {
        "ok":     True,
        "entry":  result,
        "source": "cascade_manager",
    }
