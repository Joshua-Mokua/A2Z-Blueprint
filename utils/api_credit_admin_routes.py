"""utils/api_credit_admin_routes.py — Credit Admin (CALMS) FastAPI routes.

Authored v10.518 Phase 3 Arc α Batch α9 — Credit Admin API.

Four endpoints mounted under /api/credit-admin/cases:

  GET    /api/credit-admin/cases                            List (cascade-scoped)
  GET    /api/credit-admin/cases/{id}                       Detail + permissions
  POST   /api/credit-admin/cases/{id}/conditions/fulfill    Fulfill condition (anyone in scope)
  POST   /api/credit-admin/cases/{id}/disburse              Clear for disbursement (manager-only)

Mounted via APIRouter (second use of the pattern after α8 LMS).
Pattern is now established for backend routes in this codebase.

Doctrine: "Streamlit stays, React additive, FastAPI canonical."
This module exposes CreditAdminManager (utils/core.py) to React.
Streamlit continues to call CreditAdminManager directly.

Authorization (defense in depth):
  1. Bearer JWT — verified by get_current_user dependency
  2. Cascade scope — get_visible_staff_codes (rm_code-based)
  3. Per-action tier — is_manager() gate on /disburse only
  4. State guardrails — case_can_be_disbursed,
                        case_can_have_condition_fulfilled

Audit events emitted (action, username, detail):
  CREDIT_ADMIN_CONDITION_FULFILLED   detail: {case_id}|{condition_type}|{officer}
  CREDIT_ADMIN_DISBURSED             detail: {case_id}|{authority}
"""
from __future__ import annotations

from typing import Dict, Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict

from utils.auth_jwt import get_current_user
from utils.core import CreditAdminManager
from utils.core_audit import audit_log

from utils.api_pipeline_scope import get_visible_staff_codes
from utils.api_pipeline_manager_actions import is_manager

from utils.api_credit_admin_models import (
    CreditAdminCasesResponse,
    CreditAdminCaseDetailResponse,
    FulfillConditionRequest,
    DisburseCaseRequest,
    CreditAdminMutationResponse,
    RequestAuthorizationRequest,
    AuthorizeRequest,
)
from utils.api_credit_admin_scope import (
    filter_cases_by_visible_codes,
    is_case_in_scope,
)
from utils.api_credit_admin_mutations import (
    validate_fulfill_condition_payload,
    validate_disburse_payload,
    case_can_be_disbursed,
    case_can_have_condition_fulfilled,
    condition_exists_on_case,
)
from utils.api_credit_admin_permissions import resolve_case_permissions


router = APIRouter(
    prefix="/api/credit-admin",
    tags=["Credit Admin - CALMS"],
)


def _cam() -> CreditAdminManager:
    """Fresh CreditAdminManager per request (same convention as α8)."""
    return CreditAdminManager()


# ─────────────────────────────────────────────────────────────────────
# GET /api/credit-admin/cases — list
# ─────────────────────────────────────────────────────────────────────


@router.get("/cases", response_model=CreditAdminCasesResponse)
def credit_admin_cases_list(
    user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """List credit-admin cases visible in caller's cascade.

    Scope: rm_code in caller's get_visible_staff_codes set. Admins
    see everything (their visible_codes spans the whole roster).
    """
    cam = _cam()
    visible_codes = get_visible_staff_codes(user)
    cases = filter_cases_by_visible_codes(cam.cases, visible_codes)

    return {
        "cases": cases,
        "count": len(cases),
        "source": "credit_admin_manager",
    }


# ─────────────────────────────────────────────────────────────────────
# GET /api/credit-admin/cases/{case_id} — detail
# ─────────────────────────────────────────────────────────────────────


@router.get(
    "/cases/{case_id}",
    response_model=CreditAdminCaseDetailResponse,
)
def credit_admin_case_detail(
    case_id: str,
    user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """Single case detail + per-caller permission flags.

    404 if case doesn't exist. 403 if caller out-of-scope.
    """
    cam = _cam()
    case = cam.get(case_id)
    if not case:
        raise HTTPException(
            status_code=404,
            detail=f"Case '{case_id}' not found",
        )

    visible_codes = get_visible_staff_codes(user)
    permissions = resolve_case_permissions(user, case, visible_codes)

    if not permissions["can_view"]:
        raise HTTPException(
            status_code=403,
            detail="You do not have visibility to this case",
        )

    return {
        "case": case,
        "permissions": permissions,
        "source": "credit_admin_manager",
    }


# ─────────────────────────────────────────────────────────────────────
# POST /api/credit-admin/cases/{id}/conditions/fulfill
# ─────────────────────────────────────────────────────────────────────


@router.post(
    "/cases/{case_id}/conditions/fulfill",
    response_model=CreditAdminMutationResponse,
)
def credit_admin_fulfill_condition(
    case_id: str,
    payload: FulfillConditionRequest,
    user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """Mark a specific condition fulfilled on this case.

    Authorization: anyone in cascade scope. Operations-level action
    (collecting documents, marking board resolutions received, etc.)

    Wraps CreditAdminManager.fulfill_condition(). The manager method
    sets the condition's fulfilled=True, date_met=today, officer=...,
    and recomputes all_conditions_met across the case.

    Returns:
      404 if case doesn't exist
      403 if case out-of-scope
      400 if case is disbursed, condition not found, or payload invalid
      500 if manager method fails
    """
    cam = _cam()
    case = cam.get(case_id)
    if not case:
        raise HTTPException(
            status_code=404,
            detail=f"Case '{case_id}' not found",
        )

    # Scope check
    visible_codes = get_visible_staff_codes(user)
    if not user.get('is_admin') and not is_case_in_scope(case, visible_codes):
        raise HTTPException(
            status_code=403,
            detail="Case not in your cascade scope",
        )

    # State guardrail (case not disbursed)
    ok, reason = case_can_have_condition_fulfilled(case)
    if not ok:
        raise HTTPException(status_code=400, detail=reason)

    # Payload validation
    payload_dict = payload.model_dump()
    ok, reason = validate_fulfill_condition_payload(payload_dict)
    if not ok:
        raise HTTPException(status_code=400, detail=reason)

    # Condition existence check — better error than silent manager failure
    if not condition_exists_on_case(case, payload.condition_type):
        existing = [
            str(c.get('type', '?'))
            for c in (case.get('conditions') or [])
        ]
        raise HTTPException(
            status_code=400,
            detail=(
                f"Condition '{payload.condition_type}' not found on case "
                f"'{case_id}'. Available conditions: {existing}"
            ),
        )

    # Apply
    success = cam.fulfill_condition(
        case_id,
        condition_type=payload.condition_type,
        officer_name=payload.officer_name,
    )
    if not success:
        raise HTTPException(
            status_code=500,
            detail="Condition fulfillment failed (manager method returned False)",
        )

    # Audit (action, username, detail) — α9 emits officer_name in the
    # detail since the audit trail needs to record WHO marked it,
    # which may not be the same as the username (delegated mark-on-behalf-of)
    audit_log(
        "CREDIT_ADMIN_CONDITION_FULFILLED",
        str(user.get('username', '') or ''),
        f"{case_id}|{payload.condition_type}|{payload.officer_name}",
    )

    updated = cam.get(case_id)
    return {"case": updated, "status": "condition_fulfilled"}


# ─────────────────────────────────────────────────────────────────────
# P4-2: CP/CS classification + facility security classification
# ─────────────────────────────────────────────────────────────────────
class _ClassifyConditionRequest(BaseModel):
    condition_type: str
    classification: Optional[str] = None   # "precedent" | "subsequent"
    mandatory: Optional[bool] = None
    due_date: Optional[str] = None
    model_config = ConfigDict(extra="allow")


class _FacilityClassificationRequest(BaseModel):
    facility_security_type: str            # "unsecured" | "secured"
    security_subtype: Optional[str] = None
    model_config = ConfigDict(extra="allow")


def _ca_manager_in_scope(user, case):
    """Classification is a credit decision — require manager-tier (or admin),
    in scope. Mirrors the scope check used elsewhere in this module."""
    if user.get("is_admin"):
        return True
    visible = get_visible_staff_codes(user)
    return is_case_in_scope(case, visible)


@router.post("/cases/{case_id}/conditions/classify",
             response_model=CreditAdminMutationResponse)
def credit_admin_classify_condition(
    case_id: str,
    payload: _ClassifyConditionRequest,
    user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """Reclassify a condition as Condition Precedent or Subsequent, set whether
    it is mandatory, and (for Subsequent) an optional due date. CP that is
    mandatory blocks disbursement (enforced at the P4-6 gate); CS is tracked
    post-disbursement and never blocks."""
    cam = _cam()
    case = cam.get(case_id)
    if not case:
        raise HTTPException(status_code=404, detail=f"Case '{case_id}' not found")
    if not _ca_manager_in_scope(user, case):
        raise HTTPException(status_code=403, detail="Case not in your cascade scope")
    if (payload.classification is not None
            and payload.classification not in ("precedent", "subsequent")):
        raise HTTPException(status_code=400,
                            detail="classification must be 'precedent' or 'subsequent'")
    ok = cam.classify_condition(
        case_id, condition_type=payload.condition_type,
        classification=payload.classification, mandatory=payload.mandatory,
        due_date=payload.due_date)
    if not ok:
        raise HTTPException(
            status_code=400,
            detail=f"Condition '{payload.condition_type}' not found on case '{case_id}'")
    audit_log("CREDIT_ADMIN_CONDITION_CLASSIFIED",
              str(user.get('username', '') or ''),
              f"{case_id}|{payload.condition_type}|{payload.classification}|"
              f"mandatory={payload.mandatory}")
    return {"case": cam.get(case_id), "status": "condition_classified"}


@router.post("/cases/{case_id}/classify-facility",
             response_model=CreditAdminMutationResponse)
def credit_admin_classify_facility(
    case_id: str,
    payload: _FacilityClassificationRequest,
    user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """Set the facility's security type (unsecured/secured) and optional
    subtype. Drives perfection routing; the disbursement gate enforces it in
    P4-6."""
    cam = _cam()
    case = cam.get(case_id)
    if not case:
        raise HTTPException(status_code=404, detail=f"Case '{case_id}' not found")
    if not _ca_manager_in_scope(user, case):
        raise HTTPException(status_code=403, detail="Case not in your cascade scope")
    ok = cam.set_facility_classification(
        case_id, facility_security_type=payload.facility_security_type,
        security_subtype=payload.security_subtype or "")
    if not ok:
        raise HTTPException(
            status_code=400,
            detail="facility_security_type must be 'unsecured' or 'secured'")
    audit_log("CREDIT_ADMIN_FACILITY_CLASSIFIED",
              str(user.get('username', '') or ''),
              f"{case_id}|{payload.facility_security_type}|{payload.security_subtype}")
    return {"case": cam.get(case_id), "status": "facility_classified"}


# ─────────────────────────────────────────────────────────────────────
# P4-3: collateral linkage + coverage ratio
# ─────────────────────────────────────────────────────────────────────
class _LinkCollateralRequest(BaseModel):
    collateral_id: str
    collateral_type: str
    forced_sale_value: float
    currency: str = "KES"
    market_value: Optional[float] = None
    allocated_value_kes: Optional[float] = None
    valuation_date: Optional[str] = None
    model_config = ConfigDict(extra="allow")


@router.post("/cases/{case_id}/collateral/link",
             response_model=CreditAdminMutationResponse)
def credit_admin_link_collateral(
    case_id: str,
    payload: _LinkCollateralRequest,
    user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """Link a collateral item to the facility and recompute coverage ratio +
    security classification (against the admin Credit Policy Matrix)."""
    cam = _cam()
    case = cam.get(case_id)
    if not case:
        raise HTTPException(status_code=404, detail=f"Case '{case_id}' not found")
    if not _ca_manager_in_scope(user, case):
        raise HTTPException(status_code=403, detail="Case not in your cascade scope")
    ok = cam.link_collateral(
        case_id, collateral_id=payload.collateral_id,
        collateral_type=payload.collateral_type,
        forced_sale_value=payload.forced_sale_value, currency=payload.currency,
        market_value=payload.market_value,
        allocated_value_kes=payload.allocated_value_kes,
        valuation_date=payload.valuation_date)
    if not ok:
        raise HTTPException(status_code=400, detail="Failed to link collateral")
    updated = cam.get(case_id)
    audit_log("CREDIT_ADMIN_COLLATERAL_LINKED",
              str(user.get('username', '') or ''),
              f"{case_id}|{payload.collateral_id}|{payload.collateral_type}|"
              f"coverage={updated.get('coverage_ratio')}|"
              f"class={updated.get('security_classification')}")
    return {"case": updated, "status": "collateral_linked"}


@router.post("/cases/{case_id}/collateral/unlink",
             response_model=CreditAdminMutationResponse)
def credit_admin_unlink_collateral(
    case_id: str,
    payload: Dict[str, Any],
    user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """Unlink a collateral item and recompute coverage/classification."""
    cam = _cam()
    case = cam.get(case_id)
    if not case:
        raise HTTPException(status_code=404, detail=f"Case '{case_id}' not found")
    if not _ca_manager_in_scope(user, case):
        raise HTTPException(status_code=403, detail="Case not in your cascade scope")
    collateral_id = str(payload.get("collateral_id", "") or "")
    if not cam.unlink_collateral(case_id, collateral_id):
        raise HTTPException(status_code=400,
                            detail=f"Collateral '{collateral_id}' not linked to case")
    updated = cam.get(case_id)
    audit_log("CREDIT_ADMIN_COLLATERAL_UNLINKED",
              str(user.get('username', '') or ''),
              f"{case_id}|{collateral_id}")
    return {"case": updated, "status": "collateral_unlinked"}


@router.get("/policy-matrix")
def credit_admin_policy_matrix(user: Dict[str, Any] = Depends(get_current_user)):
    """Return the admin Credit Policy Matrix (required coverage ratios)."""
    from utils.collateral_coverage import CreditPolicyMatrix
    m = CreditPolicyMatrix()
    return {
        "required_coverage_pct": m._pct,
        "over_secured_multiple": float(m.over_secured_multiple),
        "valuation_max_age_days": m.valuation_max_age_days,
    }


# ─────────────────────────────────────────────────────────────────────
# POST /api/credit-admin/cases/{id}/disburse — clear for disbursement
# ─────────────────────────────────────────────────────────────────────


@router.post(
    "/cases/{case_id}/disburse",
    response_model=CreditAdminMutationResponse,
)
def credit_admin_disburse(
    case_id: str,
    payload: DisburseCaseRequest,
    user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """Clear a case for disbursement. Manager-tier only.

    Wraps CreditAdminManager.clear_for_disbursement() which sets
    ready_for_disbursement=True on the case. The actual fund transfer
    (setting disbursed=True + disbursement_date) is OUT OF SCOPE for
    α9 — that's a downstream finance-system step, not a credit-admin
    API responsibility.

    The endpoint is named /disburse for the user-facing verb. Internal
    method is clear_for_disbursement. Document this in Section 19.

    Returns:
      403 if not manager-tier OR out of scope
      404 if case doesn't exist
      400 if not all_conditions_met, already disbursed, or payload invalid
      500 if manager method fails
    """
    # Manager-tier check FIRST (cheapest gate)
    if not is_manager(user):
        raise HTTPException(
            status_code=403,
            detail="Manager authority required to clear cases for disbursement",
        )

    cam = _cam()
    case = cam.get(case_id)
    if not case:
        raise HTTPException(
            status_code=404,
            detail=f"Case '{case_id}' not found",
        )

    # Scope check
    visible_codes = get_visible_staff_codes(user)
    if not user.get('is_admin') and not is_case_in_scope(case, visible_codes):
        raise HTTPException(
            status_code=403,
            detail="Case not in your cascade scope",
        )

    # State guardrail
    ok, reason = case_can_be_disbursed(case)
    if not ok:
        raise HTTPException(status_code=400, detail=reason)

    # Payload validation
    payload_dict = payload.model_dump()
    ok, reason = validate_disburse_payload(payload_dict)
    if not ok:
        raise HTTPException(status_code=400, detail=reason)

    # Apply
    success = cam.clear_for_disbursement(case_id)
    if not success:
        raise HTTPException(
            status_code=500,
            detail="Disbursement clearance failed (manager method returned False)",
        )

    # Audit
    audit_log(
        "CREDIT_ADMIN_DISBURSED",
        str(user.get('username', '') or ''),
        f"{case_id}|{payload.authority}",
    )

    # P1 (2026-06-12): recompute BSC actuals from operational modules.
    # Best-effort — a recompute failure must not fail a successful
    # disbursement clearance. Clearing a case moves Disbursements /
    # Collection Throughput / downstream PAR on the clearer's scorecard.
    # Mirrors the Pipeline routes' wiring. See utils/api_bsc_bridge.py.
    # Phase 3 (hardening): credit the originating RM, not only the clearer.
    # The owner username is carried on the linked LMS application (created_by).
    from utils.api_bsc_bridge import emit_bsc_for
    _owner = ""
    try:
        from utils.core import LoanApplicationManager as _LAM
        _case = cam.get(case_id) or {}
        _app = _LAM().get(str(_case.get("application_id", "") or "")) or {}
        _owner = str(_app.get("created_by", "") or "")
    except Exception:
        _owner = ""
    emit_bsc_for([_owner, str(user.get('username', '') or '')])

    updated = cam.get(case_id)
    return {"case": updated, "status": "cleared_for_disbursement"}


# ─────────────────────────────────────────────────────────────────────
# Two-layer authorization (v10.585)
# ─────────────────────────────────────────────────────────────────────

@router.post(
    "/cases/{case_id}/request-authorization",
    response_model=CreditAdminMutationResponse,
)
def credit_admin_request_authorization(
    case_id: str,
    payload: RequestAuthorizationRequest,
    user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """Layer 1 — a credit-admin officer confirms the case is ready and
    requests manager authorization. Anyone in scope (operations action);
    requires all conditions met.

    Returns:
      403 out of scope
      404 case not found
      400 conditions not met / already disbursed / already requested
    """
    cam = _cam()
    case = cam.get(case_id)
    if not case:
        raise HTTPException(status_code=404, detail=f"Case '{case_id}' not found")
    visible_codes = get_visible_staff_codes(user)
    if not user.get('is_admin') and not is_case_in_scope(case, visible_codes):
        raise HTTPException(status_code=403, detail="Case not in your cascade scope")
    if case.get('disbursed'):
        raise HTTPException(status_code=400, detail="Case already disbursed")
    if not case.get('all_conditions_met'):
        raise HTTPException(status_code=400,
                            detail="Cannot request authorization — conditions not all met")
    if case.get('authorization_requested'):
        raise HTTPException(status_code=400, detail="Authorization already requested")

    by = str(user.get('full_name') or user.get('username', '') or '')
    success = cam.request_authorization(case_id, by=by, note=payload.note)
    if not success:
        raise HTTPException(status_code=500, detail="request-authorization failed")
    audit_log("CREDIT_ADMIN_AUTHORIZATION_REQUESTED",
              str(user.get('username', '') or ''), case_id)
    return {"case": cam.get(case_id), "status": "authorization_requested"}


@router.post(
    "/cases/{case_id}/authorize",
    response_model=CreditAdminMutationResponse,
)
def credit_admin_authorize(
    case_id: str,
    payload: AuthorizeRequest,
    user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """Layer 2 — a credit-admin MANAGER authorizes disbursement. Requires a
    pending authorization request. Sets ready_for_disbursement so the case
    can then be disbursed.

    Returns:
      403 not manager-tier OR out of scope
      404 case not found
      400 no pending request / already authorized / already disbursed
    """
    if not is_manager(user):
        raise HTTPException(status_code=403,
                            detail="Manager authority required to authorize disbursement")
    cam = _cam()
    case = cam.get(case_id)
    if not case:
        raise HTTPException(status_code=404, detail=f"Case '{case_id}' not found")
    visible_codes = get_visible_staff_codes(user)
    if not user.get('is_admin') and not is_case_in_scope(case, visible_codes):
        raise HTTPException(status_code=403, detail="Case not in your cascade scope")
    if case.get('disbursed'):
        raise HTTPException(status_code=400, detail="Case already disbursed")
    if not case.get('authorization_requested'):
        raise HTTPException(status_code=400,
                            detail="No pending authorization request to authorize")
    if case.get('authorized'):
        raise HTTPException(status_code=400, detail="Case already authorized")

    by = str(user.get('full_name') or user.get('username', '') or '')
    success = cam.authorize(case_id, by=by, note=payload.note)
    if not success:
        raise HTTPException(status_code=500, detail="authorize failed")
    audit_log("CREDIT_ADMIN_AUTHORIZED",
              str(user.get('username', '') or ''), case_id)
    return {"case": cam.get(case_id), "status": "authorized"}
