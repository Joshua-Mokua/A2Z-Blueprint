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
# P4-4: Legal Review workflow (Legal Officer)
# ─────────────────────────────────────────────────────────────────────
def _can_perform_legal(user: Dict[str, Any]) -> bool:
    """Legal actions: admin, a Legal-Officer role, or manager-tier (pilot —
    until the canonical Legal Officer role is added in the hierarchy rework)."""
    if user.get("is_admin"):
        return True
    if "legal" in str(user.get("role", "") or "").lower():
        return True
    return is_manager(user)


class _AssignLegalRequest(BaseModel):
    officer_code: str
    officer_name: Optional[str] = ""
    model_config = ConfigDict(extra="allow")


class _LegalCommentRequest(BaseModel):
    text: str
    raises_query: Optional[bool] = False
    model_config = ConfigDict(extra="allow")


class _LegalOutcomeRequest(BaseModel):
    outcome: str   # approved | approved_with_conditions | rejected
    note: Optional[str] = ""
    model_config = ConfigDict(extra="allow")


def _legal_case_or_403(case_id: str, user):
    cam = _cam()
    case = cam.get(case_id)
    if not case:
        raise HTTPException(status_code=404, detail=f"Case '{case_id}' not found")
    if not _can_perform_legal(user):
        raise HTTPException(status_code=403,
                            detail="Legal review requires Legal Officer or manager authority")
    if not _ca_manager_in_scope(user, case):
        raise HTTPException(status_code=403, detail="Case not in your cascade scope")
    return cam, case


@router.post("/cases/{case_id}/legal/assign",
             response_model=CreditAdminMutationResponse)
def credit_admin_legal_assign(case_id: str, payload: _AssignLegalRequest,
                              user: Dict[str, Any] = Depends(get_current_user)):
    cam, _ = _legal_case_or_403(case_id, user)
    cam.assign_legal_officer(case_id, payload.officer_code, payload.officer_name or "")
    audit_log("CREDIT_ADMIN_LEGAL_ASSIGNED", str(user.get('username', '') or ''),
              f"{case_id}|{payload.officer_code}")
    return {"case": cam.get(case_id), "status": "legal_assigned"}


@router.post("/cases/{case_id}/legal/comment",
             response_model=CreditAdminMutationResponse)
def credit_admin_legal_comment(case_id: str, payload: _LegalCommentRequest,
                               user: Dict[str, Any] = Depends(get_current_user)):
    cam, _ = _legal_case_or_403(case_id, user)
    if not cam.add_legal_comment(case_id, str(user.get('username', '') or ''),
                                 payload.text, bool(payload.raises_query)):
        raise HTTPException(status_code=400, detail="Comment text is required")
    audit_log("CREDIT_ADMIN_LEGAL_COMMENT", str(user.get('username', '') or ''),
              f"{case_id}|query={payload.raises_query}")
    return {"case": cam.get(case_id), "status": "legal_comment_added"}


@router.post("/cases/{case_id}/legal/outcome",
             response_model=CreditAdminMutationResponse)
def credit_admin_legal_outcome(case_id: str, payload: _LegalOutcomeRequest,
                               user: Dict[str, Any] = Depends(get_current_user)):
    cam, _ = _legal_case_or_403(case_id, user)
    if not cam.set_legal_outcome(case_id, payload.outcome,
                                 by=str(user.get('username', '') or '')):
        raise HTTPException(
            status_code=400,
            detail="outcome must be approved, approved_with_conditions, or rejected")
    audit_log("CREDIT_ADMIN_LEGAL_OUTCOME", str(user.get('username', '') or ''),
              f"{case_id}|{payload.outcome}")
    return {"case": cam.get(case_id), "status": "legal_outcome_set"}


# ─────────────────────────────────────────────────────────────────────
# P4-5: Security Perfection + Insurance
# ─────────────────────────────────────────────────────────────────────
class _AddPerfectionRequest(BaseModel):
    security_type: str
    registration_reference: Optional[str] = ""
    registration_status: Optional[str] = "pending"
    registration_date: Optional[str] = None
    perfection_status: Optional[str] = "unperfected"
    officer_code: Optional[str] = ""
    notes: Optional[str] = ""
    model_config = ConfigDict(extra="allow")


class _UpdatePerfectionRequest(BaseModel):
    registration_status: Optional[str] = None
    registration_reference: Optional[str] = None
    registration_date: Optional[str] = None
    perfection_status: Optional[str] = None
    perfecting_officer_code: Optional[str] = None
    notes: Optional[str] = None
    model_config = ConfigDict(extra="allow")


class _AddInsuranceRequest(BaseModel):
    insurer: str
    policy_number: str
    sum_insured: Optional[float] = None
    currency: Optional[str] = "KES"
    effective_date: Optional[str] = None
    expiry_date: Optional[str] = None
    bank_interest_noted: Optional[bool] = False
    collateral_id: Optional[str] = ""
    status: Optional[str] = "active"
    renewal_alert_days: Optional[int] = 30
    model_config = ConfigDict(extra="allow")


@router.post("/cases/{case_id}/perfection",
             response_model=CreditAdminMutationResponse)
def credit_admin_add_perfection(case_id: str, payload: _AddPerfectionRequest,
                                user: Dict[str, Any] = Depends(get_current_user)):
    cam, _ = _legal_case_or_403(case_id, user)
    pid = cam.add_security_perfection(
        case_id, security_type=payload.security_type,
        registration_reference=payload.registration_reference or "",
        registration_status=payload.registration_status or "pending",
        registration_date=payload.registration_date,
        perfection_status=payload.perfection_status or "unperfected",
        officer_code=payload.officer_code or "", notes=payload.notes or "")
    audit_log("CREDIT_ADMIN_PERFECTION_ADDED", str(user.get('username', '') or ''),
              f"{case_id}|{pid}|{payload.security_type}")
    return {"case": cam.get(case_id), "status": "perfection_added"}


@router.post("/cases/{case_id}/perfection/{perfection_id}/update",
             response_model=CreditAdminMutationResponse)
def credit_admin_update_perfection(case_id: str, perfection_id: str,
                                   payload: _UpdatePerfectionRequest,
                                   user: Dict[str, Any] = Depends(get_current_user)):
    cam, _ = _legal_case_or_403(case_id, user)
    fields = {k: v for k, v in payload.model_dump().items() if v is not None}
    if not cam.update_security_perfection(case_id, perfection_id, **fields):
        raise HTTPException(status_code=400,
                            detail="Perfection not found or invalid status value")
    audit_log("CREDIT_ADMIN_PERFECTION_UPDATED", str(user.get('username', '') or ''),
              f"{case_id}|{perfection_id}|{fields}")
    return {"case": cam.get(case_id), "status": "perfection_updated"}


@router.post("/cases/{case_id}/insurance",
             response_model=CreditAdminMutationResponse)
def credit_admin_add_insurance(case_id: str, payload: _AddInsuranceRequest,
                               user: Dict[str, Any] = Depends(get_current_user)):
    cam, _ = _legal_case_or_403(case_id, user)
    iid = cam.add_insurance_policy(
        case_id, insurer=payload.insurer, policy_number=payload.policy_number,
        sum_insured=payload.sum_insured, currency=payload.currency or "KES",
        effective_date=payload.effective_date, expiry_date=payload.expiry_date,
        bank_interest_noted=bool(payload.bank_interest_noted),
        collateral_id=payload.collateral_id or "", status=payload.status or "active",
        renewal_alert_days=payload.renewal_alert_days or 30)
    audit_log("CREDIT_ADMIN_INSURANCE_ADDED", str(user.get('username', '') or ''),
              f"{case_id}|{iid}|{payload.insurer}|{payload.policy_number}")
    return {"case": cam.get(case_id), "status": "insurance_added"}


@router.post("/cases/{case_id}/insurance/{policy_id}/update",
             response_model=CreditAdminMutationResponse)
def credit_admin_update_insurance(case_id: str, policy_id: str,
                                  payload: Dict[str, Any],
                                  user: Dict[str, Any] = Depends(get_current_user)):
    cam, _ = _legal_case_or_403(case_id, user)
    fields = {k: v for k, v in (payload or {}).items() if v is not None}
    if not cam.update_insurance_policy(case_id, policy_id, **fields):
        raise HTTPException(status_code=400,
                            detail="Policy not found or invalid status value")
    audit_log("CREDIT_ADMIN_INSURANCE_UPDATED", str(user.get('username', '') or ''),
              f"{case_id}|{policy_id}")
    return {"case": cam.get(case_id), "status": "insurance_updated"}


# ─────────────────────────────────────────────────────────────────────
# P4-6: disbursement gate status + controlled override
# ─────────────────────────────────────────────────────────────────────
class _OverrideRequestBody(BaseModel):
    justification: str
    model_config = ConfigDict(extra="allow")


@router.get("/cases/{case_id}/disbursement-gate")
def credit_admin_gate_status(case_id: str,
                             user: Dict[str, Any] = Depends(get_current_user)):
    """Read the disbursement gate result for a case (drives the React gate
    checklist). Does not mutate."""
    cam = _cam()
    case = cam.get(case_id)
    if not case:
        raise HTTPException(status_code=404, detail=f"Case '{case_id}' not found")
    if not _ca_manager_in_scope(user, case):
        raise HTTPException(status_code=403, detail="Case not in your cascade scope")
    gate = cam.evaluate_disbursement_gate(case)
    gate["high_value"] = cam.is_high_value(case)
    gate["override"] = case.get("perfection_override")
    return gate


@router.post("/cases/{case_id}/perfection-override/request",
             response_model=CreditAdminMutationResponse)
def credit_admin_override_request(case_id: str, payload: _OverrideRequestBody,
                                  user: Dict[str, Any] = Depends(get_current_user)):
    """Open an override request, snapshotting the CURRENT gate failures. Manager
    or legal authority may open; approval requires override authority."""
    cam, case = _legal_case_or_403(case_id, user)
    gate = cam.evaluate_disbursement_gate(case)
    if gate["passed"]:
        raise HTTPException(status_code=400,
                            detail="Gate already passes — no override needed")
    if not cam.request_perfection_override(
            case_id, by=str(user.get('username', '') or ''),
            justification=payload.justification, failures=gate["failures"]):
        raise HTTPException(status_code=400, detail="Justification is required")
    audit_log("CREDIT_ADMIN_OVERRIDE_REQUESTED", str(user.get('username', '') or ''),
              f"{case_id}|{[f['check'] for f in gate['failures']]}")
    return {"case": cam.get(case_id), "status": "override_requested"}


@router.post("/cases/{case_id}/perfection-override/approve",
             response_model=CreditAdminMutationResponse)
def credit_admin_override_approve(case_id: str,
                                  user: Dict[str, Any] = Depends(get_current_user)):
    """Add an override approval. Authority comes from the caller's role:
    Head of Credit, Chief Risk Officer, or Managing Director. Standard
    facilities need any one of {Head of Credit, CRO}; high-value need all of
    {Head of Credit, CRO, MD}."""
    cam = _cam()
    case = cam.get(case_id)
    if not case:
        raise HTTPException(status_code=404, detail=f"Case '{case_id}' not found")
    role = cam._override_role(user)
    if role is None and not user.get("is_admin"):
        raise HTTPException(
            status_code=403,
            detail="Override approval requires Head of Credit, CRO, or MD authority")
    # A real role wins; otherwise an admin records as the 'admin' superuser role
    # (documented pilot affordance — satisfies any tier, fully audited).
    eff_role = role or "admin"
    result = cam.add_override_approval(case_id, eff_role,
                                       str(user.get('username', '') or ''))
    if not result.get("ok"):
        raise HTTPException(status_code=400,
                            detail=result.get("reason", "override approval failed"))
    audit_log("CREDIT_ADMIN_OVERRIDE_APPROVED", str(user.get('username', '') or ''),
              f"{case_id}|role={eff_role}|status={result['status']}|"
              f"have={result['have_roles']}|need={result['required_roles']}")
    return {"case": cam.get(case_id), "status": f"override_{result['status']}"}


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

    # P4-6: secured-lending disbursement HARD-GATE. Unsecured facilities check
    # only mandatory Conditions Precedent (unchanged); secured facilities must
    # additionally clear legal review, perfection, insurance (where required),
    # coverage threshold, and valuation freshness. An authorized override that
    # covers the current failures clears the gate (and flags the disbursement).
    gate = cam.evaluate_disbursement_gate(case)
    if not gate["passed"]:
        raise HTTPException(status_code=400, detail={
            "message": "Disbursement blocked by secured-lending controls",
            "failures": gate["failures"],
            "override": "POST /perfection-override/request then /approve with the "
                        "required authority (Head of Credit/CRO" +
                        (" + MD for high-value" if cam.is_high_value(case) else "") + ")",
        })

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

    # P4-6: flag disbursements that proceeded under an authorized override —
    # surfaced on the MD dashboard as a governance indicator (never a quiet bypass).
    if gate.get("overridden"):
        _c = cam.get(case_id)
        if _c is not None:
            _c["disbursed_under_override"] = True
            cam.save()
        audit_log("CREDIT_ADMIN_DISBURSED_UNDER_OVERRIDE",
                  str(user.get('username', '') or ''), f"{case_id}|{payload.authority}")

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
# TROOPS — Treasury Back Office disbursement completion (Batch C2)
#
# Credit-admin "disburse" RELEASES a case to Treasury (sets
# cleared_for_disbursement=True via clear_for_disbursement) — it no longer
# flips disbursed=True. The actual fund movement — booking the facility to
# core banking, setting the value date, posting to the GL and flipping
# disbursed=True — is owned by the central Treasury Back Office unit
# ("Troops") under Head Office Operations. Bank-wide function, so these routes
# are NOT cascade-scoped (Troops actions any released case).
#
# Ordered ops workflow:  book  ->  value-date  ->  disburse (disbursed=True)
#
# Authority is config-driven (pipeline_settings.json -> disbursement_roles,
# default ["Treasury Back Office"]) so the role can be listed/edited from the
# admin Configuration console rather than hardcoded.
# ─────────────────────────────────────────────────────────────────────

_DEFAULT_DISBURSEMENT_ROLES = ["Treasury Back Office"]


def _now_iso() -> str:
    import datetime as _dt
    return _dt.datetime.now(_dt.timezone.utc).isoformat()


def _disbursement_roles() -> list:
    """Roles permitted to complete disbursement (Troops). Admin-tunable via
    pipeline_settings.json -> disbursement_roles."""
    try:
        from utils.core import get_pipeline_settings
        cfg = get_pipeline_settings() or {}
        roles = cfg.get("disbursement_roles")
        if isinstance(roles, list) and roles:
            return [str(r) for r in roles]
    except Exception:
        pass
    return list(_DEFAULT_DISBURSEMENT_ROLES)


def _is_troops(user: Dict[str, Any]) -> bool:
    """True if the caller may perform Treasury Back Office disbursement ops.
    Admins and the executive tier always may; otherwise the caller's role must
    match a configured disbursement role (lenient substring, case-insensitive)."""
    if user.get("is_admin"):
        return True
    role = str(user.get("role") or "").lower()
    if any(k in role for k in ("chief", "managing", "director")):
        return True
    return any(str(r).lower() in role for r in _disbursement_roles() if str(r).strip())


def _troops_view(c: Dict[str, Any]) -> Dict[str, Any]:
    """Compact projection of a case for the Troops queue."""
    return {
        "case_id": c.get("case_id") or c.get("id"),
        "application_id": c.get("application_id"),
        "client_name": c.get("client_name") or c.get("borrower_name"),
        "amount": c.get("amount") or c.get("facility_amount") or c.get("loan_amount"),
        "rm_code": c.get("rm_code"),
        "troops_status": c.get("troops_status") or "queued",
        "cbs_account_no": c.get("cbs_account_no"),
        "value_date": c.get("value_date"),
        "disbursed": bool(c.get("disbursed")),
        "disbursement_date": c.get("disbursement_date"),
        "disbursed_under_override": bool(c.get("disbursed_under_override")),
    }


class TroopsBookRequest(BaseModel):
    model_config = ConfigDict(extra="allow")
    cbs_account_no: Optional[str] = None
    note: Optional[str] = ""


class TroopsValueDateRequest(BaseModel):
    model_config = ConfigDict(extra="allow")
    value_date: str = ""   # ISO date funds take value; validated in the endpoint
    note: Optional[str] = ""


class TroopsDisburseRequest(BaseModel):
    model_config = ConfigDict(extra="allow")
    gl_reference: Optional[str] = None
    note: Optional[str] = ""


@router.get("/troops/queue")
def troops_queue(user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    """Cases cleared for disbursement but not yet disbursed — the Treasury
    Back Office work queue. Bank-wide (not cascade-scoped)."""
    if not _is_troops(user):
        raise HTTPException(status_code=403,
                            detail="Treasury Back Office (disbursement) authority required")
    cam = _cam()
    out = [_troops_view(c) for c in cam.cases
           if c.get("cleared_for_disbursement") and not c.get("disbursed")]
    return {"cases": out, "count": len(out), "source": "troops_queue"}


@router.get("/troops/flow-by-stage")
def troops_flow_by_stage(user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    """Disbursement case flow grouped by Treasury Back Office (Troops) stage —
    the live disbursement workload so Operations can prep against what sits at
    each step. Buckets cleared-but-not-yet-disbursed cases by troops_status
    (queued → booked → value-dated), plus a disbursed bucket for recently
    completed work. Bank-wide, like the queue itself."""
    if not _is_troops(user):
        raise HTTPException(status_code=403,
                            detail="Treasury Back Office (disbursement) authority required")
    cam = _cam()

    STAGE_ORDER = [
        ("queued",      "Cleared — awaiting booking", {"queued"}),
        ("booked",      "Booked to core banking",     {"booked"}),
        ("value_dated", "Value-dated — ready",        {"value_dated"}),
        ("disbursed",   "Disbursed",                  {"disbursed"}),
    ]
    buckets = {key: {"key": key, "label": label, "count": 0, "value": 0.0}
               for key, label, _ in STAGE_ORDER}

    def _amt(c):
        try:
            return float(c.get("amount") or c.get("facility_amount") or c.get("loan_amount") or 0)
        except (TypeError, ValueError):
            return 0.0

    for c in cam.cases:
        if not c.get("cleared_for_disbursement"):
            continue
        if c.get("disbursed"):
            tgt = buckets["disbursed"]
        else:
            st = str(c.get("troops_status") or "queued").strip().lower()
            tgt = buckets.get(st, buckets["queued"])
        tgt["count"] += 1
        tgt["value"] += _amt(c)

    stages = [buckets[key] for key, _, _ in STAGE_ORDER]
    pending = [s for s in stages if s["key"] != "disbursed"]
    return {
        "stages": stages,
        "totals": {
            "count": sum(s["count"] for s in stages),
            "value": sum(s["value"] for s in stages),
            "pending_count": sum(s["count"] for s in pending),
            "pending_value": sum(s["value"] for s in pending),
        },
        "source": "troops_flow_by_stage",
    }


@router.post("/cases/{case_id}/troops/book")
def troops_book(case_id: str, payload: TroopsBookRequest,
                user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    """Step 1 — book the facility to core banking (open the loan account)."""
    if not _is_troops(user):
        raise HTTPException(status_code=403, detail="Treasury Back Office authority required")
    cam = _cam()
    acct = (payload.cbs_account_no or "").strip() or f"ECO{str(case_id)[-10:].zfill(10)}"
    uname = str(user.get("username", "") or "")
    res = cam.troops_book(case_id, acct, uname, _now_iso())  # serialized (CA-3)
    if not res.get("ok"):
        raise HTTPException(status_code=res["code"], detail=res["detail"])
    audit_log("TROOPS_BOOKED", uname, f"{case_id}|{acct}")
    return {"case": cam.get(case_id), "troops_status": "booked"}


@router.post("/cases/{case_id}/troops/value-date")
def troops_value_date(case_id: str, payload: TroopsValueDateRequest,
                      user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    """Step 2 — set the value date for the disbursement (requires booked)."""
    if not _is_troops(user):
        raise HTTPException(status_code=403, detail="Treasury Back Office authority required")
    vd = (payload.value_date or "").strip()
    if not vd:
        raise HTTPException(status_code=400, detail="value_date is required")
    cam = _cam()
    uname = str(user.get("username", "") or "")
    res = cam.troops_set_value_date(case_id, vd, uname, _now_iso())  # serialized (CA-3)
    if not res.get("ok"):
        raise HTTPException(status_code=res["code"], detail=res["detail"])
    audit_log("TROOPS_VALUE_DATED", uname, f"{case_id}|{vd}")
    return {"case": cam.get(case_id), "troops_status": "value_dated"}


@router.post("/cases/{case_id}/troops/disburse")
def troops_disburse(case_id: str, payload: TroopsDisburseRequest,
                    user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    """Step 3 (final) — post to GL and complete the disbursement: disbursed=True
    + disbursement_date. Requires the facility booked and value-dated first."""
    if not _is_troops(user):
        raise HTTPException(status_code=403, detail="Treasury Back Office authority required")
    cam = _cam()
    gl = (payload.gl_reference or "").strip() or f"GL{_now_iso()[:19].replace('-', '').replace(':', '').replace('T', '')}"
    uname = str(user.get("username", "") or "")
    res = cam.troops_disburse(case_id, gl, uname, _now_iso())  # serialized (CA-3): one winner
    if not res.get("ok"):
        raise HTTPException(status_code=res["code"], detail=res["detail"])
    # Autopopulate the BSC: flip the linked loan application to 'disbursed' so the
    # K001 "Loans Disbursed" aggregation rule (SUM amount where status in
    # loan_approved_disbursed) credits the originating RM in the disbursement
    # period. Best-effort — a failure here must never block the disbursement.
    try:
        app_id = str(res.get("application_id") or "")
        if app_id:
            from utils.core import LoanApplicationManager
            lam = LoanApplicationManager()
            app = lam.get(app_id)
            if app and app.get("status") != "disbursed":
                fields = {"status": "disbursed",
                          "disbursement_date": res["disbursement_date"]}
                if not app.get("amount") and res.get("amount"):
                    fields["amount"] = res.get("amount")
                lam.update(app_id, fields)
    except Exception:
        import logging
        logging.getLogger("a2z.creditadmin").warning(
            "K001 autopopulate (loan-app status flip) failed for %s", case_id, exc_info=True)
    audit_log("TROOPS_DISBURSED", uname, f"{case_id}|{gl}")
    return {"case": cam.get(case_id), "troops_status": "disbursed", "disbursed": True}


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
