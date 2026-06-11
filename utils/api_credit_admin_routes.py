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

from typing import Dict, Any

from fastapi import APIRouter, Depends, HTTPException

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

    updated = cam.get(case_id)
    return {"case": updated, "status": "cleared_for_disbursement"}
