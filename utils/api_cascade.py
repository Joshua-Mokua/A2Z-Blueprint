"""utils/api_cascade.py — Cascade FastAPI router (v10.413, E7).

Per Joshua's React requirement: this module is the bridge between the
pure-compute cascade engines (built across v10.406-v10.412) and a React
front-end.

Wraps:
  - cascade_health_engine    (v10.411)
  - target_scenario_simulator (v10.408)
  - pillar_impact_engine     (v10.407)
  - manager_rollup           (v10.406)
  - kpi_ownership_pairing    (v10.410)
  - capacity_feedback        (v10.412)
  - cascade_structure_engine (foundation)

Design principles:
  1. Pydantic request + response models — types are the contract
  2. JWT auth via Depends(get_current_user)
  3. Engine functions called UNCHANGED — same imports as Streamlit
  4. OpenAPI auto-generates at /api/docs (FastAPI built-in)
  5. JSON responses use asdict on dataclasses (engine returns)
  6. Zero state mutation in GET endpoints; POST/PATCH for writes

URL convention:
  GET  /api/v1/cascade/health/summary                 — bank summary
  GET  /api/v1/cascade/health/pillars                 — per-pillar
  GET  /api/v1/cascade/health/sbu                     — per-chief subtree
  GET  /api/v1/cascade/health/kpis                    — per-KPI
  GET  /api/v1/cascade/health/broken-chains           — diagnostic
  GET  /api/v1/cascade/health/stale-entries           — stale records

  GET  /api/v1/cascade/rollup/{manager_code}/{period} — team progress

  GET  /api/v1/cascade/pillars/{staff_code}/{period}  — personal pillar mix
  GET  /api/v1/cascade/pillars/bank-weights           — canonical weights

  GET  /api/v1/cascade/pairing/shared-kpis            — list KPIs with co-owners
  GET  /api/v1/cascade/pairing/co-owners/{kpi}        — who owns this KPI
  POST /api/v1/cascade/pairing/apply                  — compute pairing

  POST /api/v1/cascade/simulator/scenario             — compute scenario
  POST /api/v1/cascade/simulator/split                — apply split strategy

  POST /api/v1/cascade/capacity/submit                — staff submit feedback
  GET  /api/v1/cascade/capacity/staff/{code}          — staff's feedback
  GET  /api/v1/cascade/capacity/team/{mgr}/{period}   — manager view
  PATCH /api/v1/cascade/capacity/{id}/resolve         — manager resolve

This router is INCLUDED by utils/api.py's main FastAPI app at startup.

Shipped: v10.413.
"""
from __future__ import annotations

from dataclasses import asdict
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from utils.auth_jwt import get_current_user

# ════════════════════════════════════════════════════════════════════
# Router setup
# ════════════════════════════════════════════════════════════════════

router = APIRouter(
    prefix="/api/v1/cascade",
    tags=["cascade"],
    dependencies=[Depends(get_current_user)],  # JWT-required on every endpoint
)


# ════════════════════════════════════════════════════════════════════
# Pydantic request/response models (the React-facing contract)
# ════════════════════════════════════════════════════════════════════

class BankHealthSummaryResponse(BaseModel):
    period: str
    total_bank_targets: int
    cascade_entries: int
    distinct_recipients: int
    distinct_kpis_cascaded: int
    fully_allocated_count: int
    partial_allocated_count: int
    under_allocated_count: int
    average_coverage_pct: float
    overall_health_score: float


class PillarHealthResponse(BaseModel):
    pillar: str
    bank_weight: float
    kpis_with_target: int
    cascaded_count: int
    not_cascaded_count: int
    avg_coverage_pct: float


class SBUHealthResponse(BaseModel):
    sbu: str
    chief_code: Optional[str]
    chief_name: Optional[str]
    direct_reports_in_cascade: int
    total_direct_reports: int
    distinct_kpis_received: int
    completeness_pct: float
    notes: List[str] = Field(default_factory=list)


class KPIHealthResponse(BaseModel):
    kpi: str
    pillar: str
    bank_target_set: bool
    cascade_entries: int
    distinct_recipients: int
    avg_coverage_pct: float


class BrokenChainResponse(BaseModel):
    staff_code: str
    staff_name: str
    role: str
    kpi: str
    received_amount: float
    has_direct_reports: bool
    reports_with_subcascade: int
    reason: str


class StaleEntryResponse(BaseModel):
    from_code: str
    from_name: str
    kpi: str
    period: str
    last_modified: Optional[str]
    days_stale: int
    coverage_pct: float


class TeamRollupResponse(BaseModel):
    manager_code: str
    period: str
    direct_reports_count: int
    indirect_subordinates_count: int
    by_kpi: Dict[str, Any]


class PillarBreakdownResponse(BaseModel):
    pillar: str
    bank_weight: float
    personal_weight: float
    kpi_count: int
    kpis: List[str]


class CoOwnershipResponse(BaseModel):
    kpi: str
    primary_owners: List[str]
    secondary_owners: List[str]
    default_pairing: str
    note: str


class PairingRequest(BaseModel):
    kpi: str
    total_target: float
    recipients: List[str]
    strategy: str = "equal_split"
    manual_shares: Optional[Dict[str, float]] = None


class PairingResultResponse(BaseModel):
    kpi: str
    strategy: str
    total_target: float
    allocations: Dict[str, float]
    notes: List[str] = Field(default_factory=list)


class SimulatorRequest(BaseModel):
    kpi: str
    period: str
    total_target: float
    recipient_codes: List[str]
    strategy: str = "equal"


# Capacity feedback models live in utils/api_capacity_feedback.py (v10.412)


# ════════════════════════════════════════════════════════════════════
# /health/* — Executive cascade health (wraps v10.411 engine)
# ════════════════════════════════════════════════════════════════════

@router.get("/health/summary", response_model=BankHealthSummaryResponse,
            summary="Bank-wide cascade health summary")
def get_bank_health_summary(
    period: str = Query(..., description="Period like '2026'"),
    user: dict = Depends(get_current_user),
):
    """Composite health score + entry counts + coverage distribution.

    Wraps `cascade_health_engine.bank_health_summary(period)`.
    """
    try:
        from utils.cascade_health_engine import bank_health_summary
        s = bank_health_summary(period)
        return asdict(s)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(500, f"Health summary failed: {exc}")


@router.get("/health/pillars", response_model=List[PillarHealthResponse],
            summary="Per-pillar cascade health")
def get_pillar_health(
    period: str = Query(...),
    user: dict = Depends(get_current_user),
):
    try:
        from utils.cascade_health_engine import health_by_pillar
        return [asdict(p) for p in health_by_pillar(period)]
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(500, f"Pillar health failed: {exc}")


@router.get("/health/sbu", response_model=List[SBUHealthResponse],
            summary="Per-SBU (chief) subtree completeness")
def get_sbu_health(
    period: str = Query(...),
    user: dict = Depends(get_current_user),
):
    try:
        from utils.cascade_health_engine import health_by_sbu
        return [asdict(s) for s in health_by_sbu(period)]
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(500, f"SBU health failed: {exc}")


@router.get("/health/kpis", response_model=List[KPIHealthResponse],
            summary="Per-KPI cascade health")
def get_kpi_health(
    period: str = Query(...),
    user: dict = Depends(get_current_user),
):
    try:
        from utils.cascade_health_engine import health_by_kpi
        return [asdict(k) for k in health_by_kpi(period)]
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(500, f"KPI health failed: {exc}")


@router.get("/health/broken-chains", response_model=List[BrokenChainResponse],
            summary="Managers who received but didn't cascade onward")
def get_broken_chains(
    period: str = Query(...),
    max_results: int = Query(50, ge=1, le=500),
    user: dict = Depends(get_current_user),
):
    try:
        from utils.cascade_health_engine import broken_chains
        return [asdict(b) for b in broken_chains(period, max_results=max_results)]
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(500, f"Broken chains failed: {exc}")


@router.get("/health/stale-entries", response_model=List[StaleEntryResponse],
            summary="Cascade entries older than N days without acceptance")
def get_stale_entries(
    period: str = Query(...),
    days: int = Query(30, ge=1, le=365),
    user: dict = Depends(get_current_user),
):
    try:
        from utils.cascade_health_engine import stale_entries
        return [asdict(s) for s in stale_entries(period, days=days)]
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(500, f"Stale entries failed: {exc}")


# ════════════════════════════════════════════════════════════════════
# /rollup/* — Team progress (wraps v10.406 manager_rollup engine)
# ════════════════════════════════════════════════════════════════════

@router.get("/rollup/{manager_code}/{period}",
            summary="Live progress rollup for a manager's subtree")
def get_team_rollup(
    manager_code: str,
    period: str,
    user: dict = Depends(get_current_user),
):
    """Aggregated KPI progress across the manager's full subtree."""
    try:
        from utils.manager_rollup import build_team_rollup
        result = build_team_rollup(manager_code, period)
        return asdict(result) if hasattr(result, '__dataclass_fields__') else result
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(500, f"Rollup failed: {exc}")


# ════════════════════════════════════════════════════════════════════
# /pillars/* — Strategic pillar viz (wraps v10.407 engine)
# ════════════════════════════════════════════════════════════════════

@router.get("/pillars/bank-weights",
            summary="Canonical bank pillar weights")
def get_bank_pillar_weights(
    user: dict = Depends(get_current_user),
):
    try:
        from utils.pillar_impact_engine import bank_pillar_weights
        return bank_pillar_weights()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(500, f"Bank weights failed: {exc}")


@router.get("/pillars/staff/{staff_code}/{period}",
            response_model=List[PillarBreakdownResponse],
            summary="Personal pillar mix for a staff member")
def get_staff_pillar_breakdown(
    staff_code: str,
    period: str,
    user: dict = Depends(get_current_user),
):
    try:
        from utils.pillar_impact_engine import pillar_breakdown_for_staff
        results = pillar_breakdown_for_staff(staff_code, period)
        return [asdict(r) for r in results]
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(500, f"Staff pillar breakdown failed: {exc}")


# ════════════════════════════════════════════════════════════════════
# /pairing/* — Co-KPI chief pairing (wraps v10.410 engine)
# ════════════════════════════════════════════════════════════════════

@router.get("/pairing/shared-kpis", response_model=List[str],
            summary="List all KPIs with 2+ primary co-owners")
def get_shared_kpis(
    user: dict = Depends(get_current_user),
):
    try:
        from utils.kpi_ownership_pairing import list_shared_kpis
        return list_shared_kpis()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(500, f"Shared KPIs failed: {exc}")


@router.get("/pairing/co-owners/{kpi}", response_model=CoOwnershipResponse,
            summary="Co-ownership map for a specific KPI")
def get_co_owners_for_kpi(
    kpi: str,
    user: dict = Depends(get_current_user),
):
    try:
        from utils.kpi_ownership_pairing import get_co_owners
        co = get_co_owners(kpi)
        if not co:
            raise HTTPException(404, f"No co-ownership map for {kpi}")
        return asdict(co)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(500, f"Co-owners lookup failed: {exc}")


@router.post("/pairing/apply", response_model=PairingResultResponse,
             summary="Compute pairing allocations across co-owners")
def apply_pairing(
    req: PairingRequest,
    user: dict = Depends(get_current_user),
):
    try:
        from utils.kpi_ownership_pairing import apply_pairing_strategy
        result = apply_pairing_strategy(
            kpi=req.kpi,
            total_target=req.total_target,
            recipients=req.recipients,
            strategy=req.strategy,
            manual_shares=req.manual_shares,
        )
        return asdict(result)
    except ValueError as ve:
        raise HTTPException(400, str(ve))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(500, f"Pairing failed: {exc}")


# ════════════════════════════════════════════════════════════════════
# /simulator/* — Target what-if (wraps v10.408 engine)
# ════════════════════════════════════════════════════════════════════

@router.get("/simulator/current/{manager_code}/{kpi}/{period}",
            summary="Load current allocation scenario")
def get_current_scenario(
    manager_code: str,
    kpi: str,
    period: str,
    user: dict = Depends(get_current_user),
):
    try:
        from utils.target_scenario_simulator import load_current_scenario
        scenario = load_current_scenario(manager_code, kpi, period)
        return asdict(scenario) if hasattr(scenario, '__dataclass_fields__') else scenario
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(500, f"Current scenario failed: {exc}")


@router.post("/simulator/split",
             summary="Apply a split strategy (equal / weighted)")
def apply_split(
    req: SimulatorRequest,
    user: dict = Depends(get_current_user),
):
    try:
        from utils.target_scenario_simulator import (
            split_equal, split_weighted_by_history,
        )
        if req.strategy == "equal":
            result = split_equal(req.total_target, req.recipient_codes)
        elif req.strategy == "weighted":
            result = split_weighted_by_history(
                req.total_target, req.recipient_codes, req.kpi
            )
        else:
            raise HTTPException(400, f"Unknown strategy: {req.strategy}")
        return result
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(500, f"Split failed: {exc}")


# ════════════════════════════════════════════════════════════════════
# /capacity/* — handled by utils/api_capacity_feedback.py
# (Defined v10.412, mounted v10.413, at prefix /api/cascade/capacity-feedback)
# Not duplicated here per single-source-of-truth discipline.
# ════════════════════════════════════════════════════════════════════


# ════════════════════════════════════════════════════════════════════
# /structure/* — Cascade structure engine (foundation)
# ════════════════════════════════════════════════════════════════════

@router.get("/structure/audit-summary",
            summary="Cascade structure engine audit summary")
def get_structure_audit(
    user: dict = Depends(get_current_user),
):
    try:
        from utils.cascade_structure_engine import full_audit
        a = full_audit()
        return a.summary
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(500, f"Structure audit failed: {exc}")


# ════════════════════════════════════════════════════════════════════
# /buffer/* — Per-layer buffer + MD per-KPI cap (v10.414, F2)
# ════════════════════════════════════════════════════════════════════
# Per Joshua's F2 design: MD sets max stretch % per KPI; each cascade
# layer can add stretch within that cap (hidden from layer below).
# These endpoints expose the cap-management surface; per-allocation
# stretch slider (Set team targets) lands v10.415; layer-hiding render
# in BSC lands v10.417 (F5).

class BufferCapResponse(BaseModel):
    kpi: str
    max_stretch_pct: float
    set_by: str
    set_at: str
    note: str = ""


class BufferCapSetRequest(BaseModel):
    max_stretch_pct: float = Field(..., ge=0.0, le=0.5,
                                    description="0.0 to 0.50 (50% absolute max)")
    note: str = ""


class BufferValidationRequest(BaseModel):
    kpi: str
    proposed_pct: float = Field(..., ge=0.0, le=1.0)


class BufferValidationResponse(BaseModel):
    kpi: str
    proposed_pct: float
    cap_pct: float
    ok: bool
    reason: str = ""


class BufferSummaryResponse(BaseModel):
    kpi: str
    period: str
    cap_pct: float
    cap_set_by: str
    total_allocations: int
    allocations_with_stretch: int
    max_stretch_observed_pct: float
    avg_stretch_pct: float
    cap_utilization_pct: float
    notes: List[str] = []


@router.get("/buffer/caps", response_model=List[BufferCapResponse],
            summary="All KPI buffer caps configured by MD")
def get_buffer_caps(
    user: dict = Depends(get_current_user),
):
    try:
        from utils.cascade_buffer_engine import get_all_buffer_caps
        caps = get_all_buffer_caps()
        return [BufferCapResponse(**asdict(c)) for c in caps]
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(500, f"get_buffer_caps failed: {exc}")


@router.get("/buffer/cap/{kpi}", response_model=BufferCapResponse,
            summary="Get buffer cap for a specific KPI")
def get_buffer_cap_endpoint(
    kpi: str,
    user: dict = Depends(get_current_user),
):
    try:
        from utils.cascade_buffer_engine import get_buffer_cap
        cap = get_buffer_cap(kpi)
        if cap is None:
            raise HTTPException(404, f"No cap configured for {kpi}")
        return BufferCapResponse(**asdict(cap))
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(500, f"get_buffer_cap failed: {exc}")


@router.put("/buffer/cap/{kpi}", response_model=BufferCapResponse,
            summary="MD sets max stretch % for a KPI")
def set_buffer_cap_endpoint(
    kpi: str,
    body: BufferCapSetRequest,
    user: dict = Depends(get_current_user),
):
    """Requires authentication. Production: add MD-role check via dependency."""
    try:
        from utils.cascade_buffer_engine import set_buffer_cap
        set_by = str(user.get("staff_code") or user.get("username") or "unknown")
        cfg = set_buffer_cap(kpi, body.max_stretch_pct, set_by, note=body.note)
        if cfg is None:
            raise HTTPException(400, "Invalid buffer cap parameters")
        return BufferCapResponse(**asdict(cfg))
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(500, f"set_buffer_cap failed: {exc}")


@router.delete("/buffer/cap/{kpi}",
               summary="Remove buffer cap for a KPI")
def delete_buffer_cap_endpoint(
    kpi: str,
    user: dict = Depends(get_current_user),
):
    try:
        from utils.cascade_buffer_engine import remove_buffer_cap
        removed_by = str(user.get("staff_code") or user.get("username") or "unknown")
        ok = remove_buffer_cap(kpi, removed_by)
        if not ok:
            raise HTTPException(404, f"No cap found for {kpi}")
        return {"kpi": kpi, "removed": True, "removed_by": removed_by}
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(500, f"remove_buffer_cap failed: {exc}")


@router.post("/buffer/validate", response_model=BufferValidationResponse,
             summary="Validate a proposed stretch % against MD's cap")
def validate_buffer_endpoint(
    body: BufferValidationRequest,
    user: dict = Depends(get_current_user),
):
    try:
        from utils.cascade_buffer_engine import validate_buffer
        v = validate_buffer(body.kpi, body.proposed_pct)
        return BufferValidationResponse(**asdict(v))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(500, f"validate_buffer failed: {exc}")


@router.get("/buffer/summary/{kpi}/{period}",
            response_model=BufferSummaryResponse,
            summary="Cascade-wide buffer usage summary for a KPI/period")
def get_buffer_summary_endpoint(
    kpi: str,
    period: str,
    user: dict = Depends(get_current_user),
):
    try:
        from utils.cascade_buffer_engine import summarize_cascade_buffer
        s = summarize_cascade_buffer(kpi, period)
        return BufferSummaryResponse(**asdict(s))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(500, f"summarize_cascade_buffer failed: {exc}")


# v10.415 — F2 part B: apply per-allocation stretch
class StretchApplyRequest(BaseModel):
    kpi: str
    allocations: List[Dict[str, Any]] = Field(
        ..., description="Existing allocation records (with to_code, amount, optional stretch_pct)"
    )
    stretch_map: Dict[str, float] = Field(
        ..., description="Map of to_code -> new stretch_pct"
    )


class StretchApplyResponse(BaseModel):
    kpi: str
    cap_pct: float
    total_allocations: int
    updated_count: int
    new_allocations: List[Dict[str, Any]]
    violations: List[Dict[str, Any]]
    new_total_amount: float


@router.post("/buffer/apply", response_model=StretchApplyResponse,
             summary="Apply per-allocation stretch and validate against cap")
def apply_stretch_endpoint(
    body: StretchApplyRequest,
    user: dict = Depends(get_current_user),
):
    """Apply stretch percentages to a list of allocations and return the
    updated list plus any cap violations. Does NOT persist — caller saves."""
    try:
        from utils.cascade_buffer_engine import apply_stretch_to_allocations
        result = apply_stretch_to_allocations(
            body.allocations, body.stretch_map, body.kpi,
        )
        return StretchApplyResponse(**asdict(result))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(500, f"apply_stretch failed: {exc}")


# ════════════════════════════════════════════════════════════════════
# /retain/* — Per-line-manager retain authorization (v10.416, F3)
# ════════════════════════════════════════════════════════════════════
# Per Joshua's F3 design: 100% cascade required up to BM tier; below BM,
# the line manager's boss ticks 'can retain' per direct report.

class RetainAuthResponse(BaseModel):
    staff_code: str
    period: str
    authorized_by: str
    authorized_at: str
    can_retain: bool
    note: str = ""


class RetainAuthSetRequest(BaseModel):
    can_retain: bool = True
    note: str = ""


class RetentionAuditSummaryResponse(BaseModel):
    period: str
    total_authorizations: int
    granted_count: int
    revoked_count: int
    authorizing_managers: List[str]


@router.get("/retain/{staff_code}/{period}",
            response_model=RetainAuthResponse,
            summary="Get retention authorization for a specific staff/period")
def get_retain_endpoint(
    staff_code: str,
    period: str,
    user: dict = Depends(get_current_user),
):
    try:
        from utils.cascade_retain_engine import get_retain_authorization
        auth = get_retain_authorization(staff_code, period)
        if auth is None:
            raise HTTPException(404, f"No authorization for {staff_code} in {period}")
        return RetainAuthResponse(**asdict(auth))
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(500, f"get_retain failed: {exc}")


@router.put("/retain/{staff_code}/{period}",
            response_model=RetainAuthResponse,
            summary="Set/update retention authorization (boss only)")
def set_retain_endpoint(
    staff_code: str,
    period: str,
    body: RetainAuthSetRequest,
    user: dict = Depends(get_current_user),
):
    """Boss grants/revokes retention. Production: add boss-role check via dependency."""
    try:
        from utils.cascade_retain_engine import set_retain_authorization
        authorized_by = str(user.get("staff_code") or user.get("username") or "unknown")
        auth = set_retain_authorization(
            staff_code, authorized_by, period,
            can_retain=body.can_retain, note=body.note,
        )
        if auth is None:
            raise HTTPException(400, "Invalid authorization parameters")
        return RetainAuthResponse(**asdict(auth))
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(500, f"set_retain failed: {exc}")


@router.delete("/retain/{staff_code}/{period}",
               summary="Revoke retention authorization")
def delete_retain_endpoint(
    staff_code: str,
    period: str,
    user: dict = Depends(get_current_user),
):
    try:
        from utils.cascade_retain_engine import remove_retain_authorization
        removed_by = str(user.get("staff_code") or user.get("username") or "unknown")
        ok = remove_retain_authorization(staff_code, period, removed_by)
        if not ok:
            raise HTTPException(404, f"No authorization to remove")
        return {"staff_code": staff_code, "period": period, "removed": True, "removed_by": removed_by}
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(500, f"remove_retain failed: {exc}")


@router.get("/retain/summary/{period}",
            response_model=RetentionAuditSummaryResponse,
            summary="Bank-wide retention authorization summary for a period")
def retain_summary_endpoint(
    period: str,
    user: dict = Depends(get_current_user),
):
    try:
        from utils.cascade_retain_engine import retention_audit_summary
        s = retention_audit_summary(period)
        return RetentionAuditSummaryResponse(**asdict(s))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(500, f"retention_audit_summary failed: {exc}")


# v10.418 — Cascade-validation surgery: compliance-aware allocation check
class ComplianceCheckRequest(BaseModel):
    staff_code: str
    kpi: str
    period: str
    total_target: float
    allocated_sum: float


class ComplianceCheckResponse(BaseModel):
    staff_code: str
    kpi: str
    period: str
    total_target: float
    allocated_sum: float
    retained_amount: float
    retained_pct: float
    coverage_pct: float
    has_retain_auth: bool
    status: str
    compliance_ok: bool
    note: str = ""


@router.post("/retain/compliance",
             response_model=ComplianceCheckResponse,
             summary="Check allocation compliance with F3 retention rules")
def check_compliance_endpoint(
    body: ComplianceCheckRequest,
    user: dict = Depends(get_current_user),
):
    """Returns compliance verdict for a manager's cascade: fully_cascaded,
    retained_authorized, under_no_auth, over_allocated, or no_target."""
    try:
        from utils.cascade_retain_engine import compute_allocation_compliance
        c = compute_allocation_compliance(
            body.staff_code, body.kpi, body.period,
            body.total_target, body.allocated_sum,
        )
        return ComplianceCheckResponse(**asdict(c))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(500, f"compute_allocation_compliance failed: {exc}")


# ════════════════════════════════════════════════════════════════════
# /dual-view/* — F5 BSC dual-view rendering data (v10.417)
# ════════════════════════════════════════════════════════════════════
# Per Joshua's F5 design: in the BSC scorecard, show stretch as the
# primary metric (what staff is striving for) with base shown as a
# secondary aside (the un-stretched target). These endpoints expose
# the dual-view breakdown for React/Streamlit consumption.

class DualViewEntryResponse(BaseModel):
    staff_code: str
    period: str
    kpi: str
    base_amount: float
    stretch_pct: float
    stretch_amount: float
    effective_amount: float
    has_stretch: bool
    from_code: str
    from_name: str


class DualViewSummaryResponse(BaseModel):
    staff_code: str
    period: str
    kpi_count: int
    stretched_kpi_count: int
    total_base: float
    total_effective: float
    total_stretch: float
    by_kpi: Dict[str, Dict[str, Any]]


@router.get("/dual-view/{staff_code}/{period}",
            response_model=List[DualViewEntryResponse],
            summary="Per-KPI base/stretch breakdown for a staff member")
def get_dual_view_endpoint(
    staff_code: str,
    period: str,
    user: dict = Depends(get_current_user),
):
    try:
        from utils.cascade_buffer_engine import compute_dual_view
        entries = compute_dual_view(staff_code, period)
        return [DualViewEntryResponse(**asdict(e)) for e in entries]
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(500, f"compute_dual_view failed: {exc}")


@router.get("/dual-view/{staff_code}/{period}/summary",
            response_model=DualViewSummaryResponse,
            summary="Rollup of dual-view for a staff member (totals across KPIs)")
def get_dual_view_summary_endpoint(
    staff_code: str,
    period: str,
    user: dict = Depends(get_current_user),
):
    try:
        from utils.cascade_buffer_engine import get_dual_view_summary
        s = get_dual_view_summary(staff_code, period)
        return DualViewSummaryResponse(**s)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(500, f"get_dual_view_summary failed: {exc}")


# ════════════════════════════════════════════════════════════════════
# Convenience — module-level export
# ════════════════════════════════════════════════════════════════════

__all__ = ["router"]
