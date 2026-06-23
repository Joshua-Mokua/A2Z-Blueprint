"""utils/api_lms_routes.py — LMS (Loan Application) FastAPI routes.

Authored v10.515 Phase 3 Arc α Batch α8 — LMS API.

Five endpoints mounted under /api/lms/applications:

  GET    /api/lms/applications                  List (cascade-scoped)
  GET    /api/lms/applications/{id}             Detail + permissions
  POST   /api/lms/applications/{id}/assign      Assign analyst (manager-only)
  PUT    /api/lms/applications/{id}             Partial update
  POST   /api/lms/applications/{id}/decision    Record decision (manager-only)

Mounted via APIRouter rather than @app.method decorators directly in
api.py. This is a NEW PATTERN for the codebase — the pipeline endpoints
predate it and live as raw @app decorators in api.py. APIRouter lets
α8 keep api.py changes to two lines (import + include_router), reducing
the risk of accidentally disturbing existing routes.

Doctrine: "Streamlit stays, React additive, FastAPI canonical." This
module exposes LoanApplicationManager (utils/core.py:5267) to React.
Streamlit continues to call LoanApplicationManager directly.

Authorization layers (defense in depth):
  1. Bearer JWT — verified by get_current_user dependency
  2. Cascade scope — get_visible_staff_codes + analyst-override
  3. Per-action gates — is_manager() for assign/decision; status
     guardrails for update/decision/assign
  4. Permission resolution — resolve_application_permissions returns
     the same flag set the React UI uses, so server and UI stay in sync

Audit events emitted (per α5/α6 convention — action, username, detail):
  LMS_ANALYST_ASSIGNED       detail: '{app_id}|{analyst_code}'
  LMS_APPLICATION_UPDATED    detail: '{app_id}'
  LMS_DECISION_APPROVED      detail: '{app_id}|{authority}'
  LMS_DECISION_DECLINED      detail: '{app_id}|{authority}'
  LMS_DECISION_RETURNED      detail: '{app_id}|{authority}'
"""
from __future__ import annotations

from typing import Dict, Any

from fastapi import APIRouter, Depends, HTTPException

from utils.auth_jwt import get_current_user, require_config_admin
from utils.core import LoanApplicationManager
from utils.core_audit import audit_log

from utils.api_pipeline_scope import get_visible_staff_codes
from utils.api_pipeline_manager_actions import is_manager

from utils.api_lms_models import (
    LoanApplicationsResponse,
    LoanApplicationDetailResponse,
    AssignAnalystRequest,
    LoanAppUpdateRequest,
    RecordDecisionRequest,
    LoanAppMutationResponse,
    RequestInfoRequest,
    ProvideInfoRequest,
    SignOfferRequest,
    ValidateOfferRequest,
    ConfirmToCreditAdminRequest,
    CommitteeVoteRequest,
    ResolveCommitteeRequest,
)
from utils.api_lms_scope import filter_apps_by_visibility, is_app_in_scope
from utils.api_lms_mutations import (
    validate_assign_payload,
    validate_update_payload,
    validate_decision_payload,
    normalize_verdict,
    STATUSES_PERMITTING_UPDATE,
    STATUSES_PERMITTING_DECISION,
    STATUSES_PERMITTING_ASSIGN,
    get_credit_workflow_config,
    is_valid_lms_transition,
    handoff_trigger_status,
)
from utils.api_lms_permissions import resolve_application_permissions


# ─────────────────────────────────────────────────────────────────────
# Router declaration
# ─────────────────────────────────────────────────────────────────────


router = APIRouter(
    prefix="/api/lms",
    tags=["LMS - Loan Applications"],
)


# ─────────────────────────────────────────────────────────────────────
# Helper: fresh LoanApplicationManager per request
# ─────────────────────────────────────────────────────────────────────


def _lam() -> LoanApplicationManager:
    """Fresh LoanApplicationManager per request.

    Matches the existing pipeline endpoint convention of constructing
    a fresh PipelineManager() per request (file-backed; reads on init).
    Cache hot-paths can be added later if profiling shows latency
    concerns.
    """
    return LoanApplicationManager()


# ─────────────────────────────────────────────────────────────────────
# GET /api/lms/applications — list (cascade-scoped)
# ─────────────────────────────────────────────────────────────────────


@router.get("/applications", response_model=LoanApplicationsResponse)
def lms_applications_list(
    user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """List loan applications visible to the caller.

    Scope rules (per api_lms_scope.filter_apps_by_visibility):
    - rm_code in caller's cascade visible-codes set, OR
    - analyst.code matches caller's staff_code

    Admins see everything (their visible_codes spans the entire roster).
    """
    lam = _lam()
    visible_codes = get_visible_staff_codes(user)
    caller_code = str(user.get('staff_code', '') or '')

    apps = filter_apps_by_visibility(
        lam.apps, visible_codes, caller_code,
        caller_role=str(user.get('role', '') or ''),
    )

    return {
        "applications": apps,
        "count": len(apps),
        "source": "loan_application_manager",
    }


# ─────────────────────────────────────────────────────────────────────
# GET /api/lms/applications/{app_id} — detail + permissions
# ─────────────────────────────────────────────────────────────────────


@router.get(
    "/applications/{app_id}",
    response_model=LoanApplicationDetailResponse,
)
def lms_application_detail(
    app_id: str,
    user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """Single application detail with per-caller permission flags.

    Returns 404 if the application doesn't exist.
    Returns 403 if the caller lacks view permission (out-of-scope and
    not the assigned analyst).
    """
    lam = _lam()
    app = lam.get(app_id)
    if not app:
        raise HTTPException(
            status_code=404,
            detail=f"Application '{app_id}' not found",
        )

    visible_codes = get_visible_staff_codes(user)
    permissions = resolve_application_permissions(user, app, visible_codes)

    if not permissions["can_view"]:
        raise HTTPException(
            status_code=403,
            detail="You do not have visibility to this application",
        )

    return {
        "application": app,
        "permissions": permissions,
        "source": "loan_application_manager",
    }


# ─────────────────────────────────────────────────────────────────────
# POST /api/lms/applications/{app_id}/assign — assign analyst
# ─────────────────────────────────────────────────────────────────────


@router.post(
    "/applications/{app_id}/assign",
    response_model=LoanAppMutationResponse,
)
def lms_application_assign(
    app_id: str,
    payload: AssignAnalystRequest,
    user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """Assign an analyst to a submitted application. Manager-tier only.

    Wraps LoanApplicationManager.submit_to_credit(). Sets analyst
    {code, name} and transitions status submitted → assigned.

    Returns:
      403 if caller is not manager-tier OR app is out of scope
      404 if application doesn't exist
      400 if status != 'submitted' or payload is invalid
      500 if the manager method returns False (file write failure, etc.)
    """
    # Tier check FIRST (cheapest gate)
    if not is_manager(user):
        raise HTTPException(
            status_code=403,
            detail="Manager authority required to assign analysts",
        )

    lam = _lam()
    app = lam.get(app_id)
    if not app:
        raise HTTPException(
            status_code=404,
            detail=f"Application '{app_id}' not found",
        )

    # Scope check
    visible_codes = get_visible_staff_codes(user)
    caller_code = str(user.get('staff_code', '') or '')
    if not user.get('is_admin') and not is_app_in_scope(app, visible_codes, caller_code):
        raise HTTPException(
            status_code=403,
            detail="Application not in your cascade scope",
        )

    # Status guardrail
    current_status = str(app.get('status', '') or '').lower()
    if current_status not in STATUSES_PERMITTING_ASSIGN:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Cannot assign analyst — application status is "
                f"'{current_status}', expected one of "
                f"{sorted(STATUSES_PERMITTING_ASSIGN)}"
            ),
        )

    # Payload validation
    payload_dict = payload.model_dump()
    ok, reason = validate_assign_payload(payload_dict)
    if not ok:
        raise HTTPException(status_code=400, detail=reason)

    # Apply
    success = lam.submit_to_credit(
        app_id,
        analyst_code=payload.analyst_code,
        analyst_name=payload.analyst_name,
    )
    if not success:
        raise HTTPException(
            status_code=500,
            detail="Assignment operation failed (manager method returned False)",
        )

    # Audit (action, username, detail) per core_audit.audit_log signature
    audit_log(
        "LMS_ANALYST_ASSIGNED",
        str(user.get('username', '') or ''),
        f"{app_id}|{payload.analyst_code}",
    )

    updated = lam.get(app_id)
    return {"application": updated, "status": "assigned"}


# ─────────────────────────────────────────────────────────────────────
# PUT /api/lms/applications/{app_id} — partial update
# ─────────────────────────────────────────────────────────────────────


@router.put(
    "/applications/{app_id}",
    response_model=LoanAppMutationResponse,
)
def lms_application_update(
    app_id: str,
    payload: LoanAppUpdateRequest,
    user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """Partial update to application fields.

    Status guardrail: only 'submitted' or 'assigned' applications can
    be updated. After a decision is recorded, the application is
    considered immutable for audit-trail purposes.

    Permission: caller must satisfy can_update from
    resolve_application_permissions — either RM owner, assigned
    analyst, manager-in-scope, or admin.
    """
    lam = _lam()
    app = lam.get(app_id)
    if not app:
        raise HTTPException(
            status_code=404,
            detail=f"Application '{app_id}' not found",
        )

    # Status guardrail FIRST (cheaper than permission resolution)
    current_status = str(app.get('status', '') or '').lower()
    if current_status not in STATUSES_PERMITTING_UPDATE:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Cannot update — application status is "
                f"'{current_status}'. Updates only allowed for: "
                f"{sorted(STATUSES_PERMITTING_UPDATE)}"
            ),
        )

    # Permission check
    visible_codes = get_visible_staff_codes(user)
    permissions = resolve_application_permissions(user, app, visible_codes)
    if not permissions["can_update"]:
        raise HTTPException(
            status_code=403,
            detail="Not authorized to update this application",
        )

    # Payload validation
    payload_dict = payload.model_dump(exclude_none=True)
    ok, reason = validate_update_payload(payload_dict)
    if not ok:
        raise HTTPException(status_code=400, detail=reason)

    # Apply
    success = lam.update(app_id, payload_dict)
    if not success:
        raise HTTPException(
            status_code=500,
            detail="Update operation failed",
        )

    # Audit
    audit_log(
        "LMS_APPLICATION_UPDATED",
        str(user.get('username', '') or ''),
        f"{app_id}",
    )

    updated = lam.get(app_id)
    return {"application": updated, "status": "updated"}


# ─────────────────────────────────────────────────────────────────────
# POST /api/lms/applications/{app_id}/decision — record decision
# ─────────────────────────────────────────────────────────────────────


@router.post(
    "/applications/{app_id}/decision",
    response_model=LoanAppMutationResponse,
)
def lms_application_decision(
    app_id: str,
    payload: RecordDecisionRequest,
    user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """Record approval/decline/return decision. Manager-tier only.

    Wraps LoanApplicationManager.record_decision(). Sets the decision
    block (verdict, date, authority, reason, conditions, comments) and
    transitions status to one of: approved | declined | returned.

    Audit event name includes the normalized verdict for clean event
    taxonomy:
      LMS_DECISION_APPROVED / DECLINED / RETURNED
    """
    # Tier check FIRST
    if not is_manager(user):
        raise HTTPException(
            status_code=403,
            detail="Manager authority required to record decisions",
        )

    lam = _lam()
    app = lam.get(app_id)
    if not app:
        raise HTTPException(
            status_code=404,
            detail=f"Application '{app_id}' not found",
        )

    # Scope check
    visible_codes = get_visible_staff_codes(user)
    caller_code = str(user.get('staff_code', '') or '')
    if not user.get('is_admin') and not is_app_in_scope(app, visible_codes, caller_code):
        raise HTTPException(
            status_code=403,
            detail="Application not in your cascade scope",
        )

    # Status guardrail
    current_status = str(app.get('status', '') or '').lower()
    if current_status not in STATUSES_PERMITTING_DECISION:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Cannot record decision — application status is "
                f"'{current_status}'. Decisions only allowed for: "
                f"{sorted(STATUSES_PERMITTING_DECISION)}"
            ),
        )

    # Committee guard (v10.586): when committee voting is on and the facility
    # is committee-tier, the decision must go through the committee flow, not a
    # direct approve/decline. No-op in authority_tier mode (back-compatible).
    try:
        from utils.api_lms_committee import committee_required, committee_mode_on
        if committee_mode_on() and committee_required(float(app.get("amount", 0) or 0)):
            raise HTTPException(status_code=400, detail=(
                "This facility is committee-tier under the bank's policy. Refer "
                "it to the credit committee (POST .../committee/refer), record "
                "votes, then resolve — rather than a direct decision."))
    except HTTPException:
        raise
    except Exception:
        pass

    # Payload validation
    payload_dict = payload.model_dump()
    ok, reason = validate_decision_payload(payload_dict)
    if not ok:
        raise HTTPException(status_code=400, detail=reason)

    # Normalize verdict to canonical form BEFORE passing to manager.
    # LoanApplicationManager.record_decision handles its own mapping,
    # but its mapping dict misses 'approve' (only has 'approved').
    # Passing the normalized form sidesteps that gap.
    verdict_normalized = normalize_verdict(payload.verdict)

    # Apply
    success = lam.record_decision(
        app_id,
        verdict=verdict_normalized,
        authority=payload.authority,
        reason=payload.reason or "",
        conditions=payload.conditions or [],
        comments=payload.comments or "",
    )
    if not success:
        raise HTTPException(
            status_code=500,
            detail="Decision recording failed",
        )

    # Audit — event name includes the normalized verdict
    audit_log(
        f"LMS_DECISION_{verdict_normalized.upper()}",
        str(user.get('username', '') or ''),
        f"{app_id}|{payload.authority}",
    )

    # P1 (2026-06-12): recompute BSC actuals from operational modules.
    # Best-effort — a recompute failure must not fail a recorded decision.
    # An approved/declined loan moves Disbursements / Loan Book Growth /
    # Number of Business Borrowers on the decider's scorecard. Mirrors the
    # Pipeline routes' emit_bsc_trigger wiring. See utils/api_bsc_bridge.py.
    # Phase 3 (hardening): credit the RM who OWNS the facility, not only the
    # caller. On approval the caller is usually the manager/analyst, but the
    # loan-book growth belongs on the originating RM's scorecard.
    from utils.api_bsc_bridge import emit_bsc_for
    emit_bsc_for([app.get('created_by'), str(user.get('username', '') or '')])

    # P2 (2026-06-12): live LMS-approval -> credit-admin handoff. On an
    # v10.584: on approval, route back to the deal owner to issue the
    # Letter of Offer (status offer_issued) instead of going straight to
    # credit admin. The CALMS case is created later, at the configured
    # handoff trigger (offer_signed / offer_validated / analyst_confirmed)
    # by the offer-workflow endpoints below. Conditions recorded on the
    # decision are carried into the CALMS case at handoff time.
    if verdict_normalized == "approved":
        try:
            lam.issue_offer(
                app_id,
                by=str(user.get("username", "") or ""),
                note="Auto-issued on approval",
            )
        except Exception:
            pass

    updated = lam.get(app_id)
    return {
        "application": updated,
        "status": f"decision_{verdict_normalized}",
        "credit_admin_case_id": "",
    }


# ─────────────────────────────────────────────────────────────────────
# Credit workflow endpoints (v10.584) — info-request loop + offer loop
# ─────────────────────────────────────────────────────────────────────
# The CALMS (credit-admin) case is created at the configured handoff
# trigger (offer_signed / offer_validated / analyst_confirmed) — never
# before the offer is signed. This helper centralizes that so every
# offer-progress endpoint agrees on where the handoff fires.

def _maybe_handoff_to_credit_admin(lam, app_id: str, user: Dict[str, Any]) -> str:
    """If the app has reached the configured handoff trigger status, create
    the CALMS case and move it to credit_admin. Idempotent + best-effort —
    a handoff failure must not fail the workflow action that preceded it."""
    cfg = get_credit_workflow_config()
    app = lam.get(app_id) or {}
    if app.get("status") != handoff_trigger_status(cfg):
        return ""
    if app.get("credit_admin_case_id"):
        return str(app.get("credit_admin_case_id"))
    try:
        from utils.core import CreditAdminManager
        decision = app.get("decision") or {}
        case_id = CreditAdminManager().create_case_from_application(
            app,
            conditions=(decision.get("conditions") or None),
            authority=str(decision.get("authority", "") or ""),
        )
        if case_id:
            lam.update(app_id, {"status": "credit_admin",
                                "credit_admin_case_id": case_id})
            lam._log_event(app_id, "handoff_to_credit_admin",
                           str(user.get("username", "") or ""),
                           f"CALMS case {case_id}")
        return case_id or ""
    except Exception:
        return ""


@router.post("/applications/{app_id}/request-info",
             response_model=LoanAppMutationResponse)
def lms_request_info(
    app_id: str,
    payload: RequestInfoRequest,
    user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """Analyst parks the case asking the deal owner for more docs (pre-decision)."""
    lam = _lam()
    app = lam.get(app_id)
    if not app:
        raise HTTPException(status_code=404, detail=f"Application '{app_id}' not found")
    if not user.get('is_admin') and not is_app_in_scope(
            app, get_visible_staff_codes(user), str(user.get('staff_code', '') or '')):
        raise HTTPException(status_code=403, detail="Application is out of scope")
    if not is_valid_lms_transition(str(app.get("status", "")), "info_requested"):
        raise HTTPException(status_code=400,
                            detail=f"Cannot request info from status '{app.get('status')}'")
    ok = lam.request_info(app_id, by=str(user.get("username", "") or ""),
                          reasons=payload.reasons, documents=payload.documents,
                          note=payload.note)
    if not ok:
        raise HTTPException(status_code=500, detail="request-info failed")
    audit_log("LMS_INFO_REQUESTED", str(user.get("username", "") or ""), app_id)
    return {"application": lam.get(app_id), "status": "info_requested"}


@router.post("/applications/{app_id}/provide-info",
             response_model=LoanAppMutationResponse)
def lms_provide_info(
    app_id: str,
    payload: ProvideInfoRequest,
    user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """Deal owner supplies the requested info; case returns to assigned."""
    lam = _lam()
    app = lam.get(app_id)
    if not app:
        raise HTTPException(status_code=404, detail=f"Application '{app_id}' not found")
    if not user.get('is_admin') and not is_app_in_scope(
            app, get_visible_staff_codes(user), str(user.get('staff_code', '') or '')):
        raise HTTPException(status_code=403, detail="Application is out of scope")
    if str(app.get("status", "")) != "info_requested":
        raise HTTPException(status_code=400,
                            detail="No outstanding info request on this application")
    ok = lam.provide_info(app_id, by=str(user.get("username", "") or ""),
                          note=payload.note, documents=payload.documents)
    if not ok:
        raise HTTPException(status_code=500, detail="provide-info failed")
    audit_log("LMS_INFO_PROVIDED", str(user.get("username", "") or ""), app_id)
    return {"application": lam.get(app_id), "status": "assigned"}


@router.post("/applications/{app_id}/sign-offer",
             response_model=LoanAppMutationResponse)
def lms_sign_offer(
    app_id: str,
    payload: SignOfferRequest,
    user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """Deal owner marks the letter of offer signed + attaches the signed copy."""
    lam = _lam()
    app = lam.get(app_id)
    if not app:
        raise HTTPException(status_code=404, detail=f"Application '{app_id}' not found")
    if not user.get('is_admin') and not is_app_in_scope(
            app, get_visible_staff_codes(user), str(user.get('staff_code', '') or '')):
        raise HTTPException(status_code=403, detail="Application is out of scope")
    if str(app.get("status", "")) != "offer_issued":
        raise HTTPException(status_code=400,
                            detail=f"Offer not in a signable state (status '{app.get('status')}')")
    cfg = get_credit_workflow_config()
    attachment = None
    if payload.attachment_filename or payload.attachment_ref:
        attachment = {
            "mode": cfg.get("signed_offer_attachment", "reference"),
            "filename": payload.attachment_filename or "",
            "ref": payload.attachment_ref or "",
            "uploaded_by": str(user.get("username", "") or ""),
            "uploaded_at": None,  # stamped by sign_offer's last_updated
        }
    ok = lam.sign_offer(app_id, by=str(user.get("username", "") or ""),
                        attachment=attachment, note=payload.note)
    if not ok:
        raise HTTPException(status_code=500, detail="sign-offer failed")
    audit_log("LMS_OFFER_SIGNED", str(user.get("username", "") or ""), app_id)
    case_id = _maybe_handoff_to_credit_admin(lam, app_id, user)
    return {"application": lam.get(app_id),
            "status": str(lam.get(app_id).get("status", "")),
            "credit_admin_case_id": case_id}


@router.post("/applications/{app_id}/validate-offer",
             response_model=LoanAppMutationResponse)
def lms_validate_offer(
    app_id: str,
    payload: ValidateOfferRequest,
    user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """Line manager validates the signed offer (checks & balances)."""
    if not is_manager(user):
        raise HTTPException(status_code=403,
                            detail="Manager authority required to validate the offer")
    lam = _lam()
    app = lam.get(app_id)
    if not app:
        raise HTTPException(status_code=404, detail=f"Application '{app_id}' not found")
    if not user.get('is_admin') and not is_app_in_scope(
            app, get_visible_staff_codes(user), str(user.get('staff_code', '') or '')):
        raise HTTPException(status_code=403, detail="Application is out of scope")
    if str(app.get("status", "")) != "offer_signed":
        raise HTTPException(status_code=400,
                            detail=f"Offer not awaiting validation (status '{app.get('status')}')")
    ok = lam.validate_offer(app_id, by=str(user.get("username", "") or ""),
                            approve=payload.approve, note=payload.note)
    if not ok:
        raise HTTPException(status_code=500, detail="validate-offer failed")
    audit_log("LMS_OFFER_VALIDATED" if payload.approve else "LMS_OFFER_VALIDATION_REJECTED",
              str(user.get("username", "") or ""), app_id)
    case_id = _maybe_handoff_to_credit_admin(lam, app_id, user)
    return {"application": lam.get(app_id),
            "status": str(lam.get(app_id).get("status", "")),
            "credit_admin_case_id": case_id}


@router.post("/applications/{app_id}/confirm-to-credit-admin",
             response_model=LoanAppMutationResponse)
def lms_confirm_to_credit_admin(
    app_id: str,
    payload: ConfirmToCreditAdminRequest,
    user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """Credit analyst confirms to credit admin to proceed; creates the CALMS case."""
    lam = _lam()
    app = lam.get(app_id)
    if not app:
        raise HTTPException(status_code=404, detail=f"Application '{app_id}' not found")
    if not user.get('is_admin') and not is_app_in_scope(
            app, get_visible_staff_codes(user), str(user.get('staff_code', '') or '')):
        raise HTTPException(status_code=403, detail="Application is out of scope")
    if not is_valid_lms_transition(str(app.get("status", "")), "analyst_confirmed"):
        raise HTTPException(status_code=400,
                            detail=f"Cannot confirm to credit admin from status '{app.get('status')}'")
    ok = lam.confirm_to_credit_admin(app_id, by=str(user.get("username", "") or ""),
                                     note=payload.note)
    if not ok:
        raise HTTPException(status_code=500, detail="confirm-to-credit-admin failed")
    audit_log("LMS_ANALYST_CONFIRMED", str(user.get("username", "") or ""), app_id)
    case_id = _maybe_handoff_to_credit_admin(lam, app_id, user)
    return {"application": lam.get(app_id),
            "status": str(lam.get(app_id).get("status", "")),
            "credit_admin_case_id": case_id}


# ─────────────────────────────────────────────────────────────────────
# Committee voting endpoints (v10.586) — committee_mode == committee_voting
# ─────────────────────────────────────────────────────────────────────
# Reuses the existing CreditCommitteeEngine via utils/api_lms_committee.py.

@router.post("/applications/{app_id}/committee/refer",
             response_model=LoanAppMutationResponse)
def lms_committee_refer(
    app_id: str,
    user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """Refer an application to the credit committee. Manager-tier."""
    if not is_manager(user):
        raise HTTPException(status_code=403,
                            detail="Manager authority required to refer to committee")
    lam = _lam()
    app = lam.get(app_id)
    if not app:
        raise HTTPException(status_code=404, detail=f"Application '{app_id}' not found")
    if not user.get('is_admin') and not is_app_in_scope(
            app, get_visible_staff_codes(user), str(user.get('staff_code', '') or '')):
        raise HTTPException(status_code=403, detail="Application is out of scope")
    if not is_valid_lms_transition(str(app.get("status", "")), "referred_to_committee"):
        raise HTTPException(status_code=400,
                            detail=f"Cannot refer to committee from status '{app.get('status')}'")
    lam.refer_to_committee(app_id, by=str(user.get("username", "") or ""))
    audit_log("LMS_REFERRED_TO_COMMITTEE", str(user.get("username", "") or ""), app_id)
    return {"application": lam.get(app_id), "status": "referred_to_committee"}


@router.post("/applications/{app_id}/committee/vote",
             response_model=LoanAppMutationResponse)
def lms_committee_vote(
    app_id: str,
    payload: CommitteeVoteRequest,
    user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """Record one committee member's vote (YES/NO/ABSTAIN/RECUSED)."""
    from utils.api_lms_committee import committee_member_ids
    lam = _lam()
    app = lam.get(app_id)
    if not app:
        raise HTTPException(status_code=404, detail=f"Application '{app_id}' not found")
    if not user.get('is_admin') and not is_app_in_scope(
            app, get_visible_staff_codes(user), str(user.get('staff_code', '') or '')):
        raise HTTPException(status_code=403, detail="Application is out of scope")
    if str(app.get("status", "")) != "referred_to_committee":
        raise HTTPException(status_code=400,
                            detail="Application is not before the committee")
    if payload.vote.upper() not in ("YES", "NO", "ABSTAIN", "RECUSED"):
        raise HTTPException(status_code=400,
                            detail="vote must be YES, NO, ABSTAIN, or RECUSED")
    if payload.member_id not in committee_member_ids():
        raise HTTPException(status_code=400,
                            detail=f"'{payload.member_id}' is not a charter member")
    lam.record_committee_vote(app_id, member_id=payload.member_id,
                              vote=payload.vote.upper(),
                              rationale=payload.rationale,
                              by=str(user.get("username", "") or ""))
    audit_log("LMS_COMMITTEE_VOTE", str(user.get("username", "") or ""),
              f"{app_id}|{payload.member_id}:{payload.vote}")
    return {"application": lam.get(app_id), "status": "referred_to_committee"}


@router.post("/applications/{app_id}/committee/resolve",
             response_model=LoanAppMutationResponse)
def lms_committee_resolve(
    app_id: str,
    payload: ResolveCommitteeRequest,
    user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """Run the committee engine over recorded votes and apply the outcome.
    Manager-tier. On approval, issues the Letter of Offer (offer loop)."""
    if not is_manager(user):
        raise HTTPException(status_code=403,
                            detail="Manager authority required to resolve the committee")
    from utils.api_lms_committee import evaluate_committee
    lam = _lam()
    app = lam.get(app_id)
    if not app:
        raise HTTPException(status_code=404, detail=f"Application '{app_id}' not found")
    if not user.get('is_admin') and not is_app_in_scope(
            app, get_visible_staff_codes(user), str(user.get('staff_code', '') or '')):
        raise HTTPException(status_code=403, detail="Application is out of scope")
    if str(app.get("status", "")) != "referred_to_committee":
        raise HTTPException(status_code=400,
                            detail="Application is not before the committee")
    result = evaluate_committee(app, attending_member_ids=tuple(payload.attending_member_ids))
    lam.resolve_committee(app_id, result=result,
                          by=str(user.get("username", "") or ""),
                          note=payload.note)
    audit_log("LMS_COMMITTEE_RESOLVED",
              str(user.get("username", "") or ""), f"{app_id}|{result.get('outcome')}")
    # On approval, continue into the offer loop (mirrors the decision route).
    if result.get("approved"):
        try:
            lam.issue_offer(app_id, by=str(user.get("username", "") or ""),
                            note="Auto-issued on committee approval")
        except Exception:
            pass
    # Phase 3 (hardening): committee resolution is an approval outcome; credit
    # the originating RM (app owner) plus the resolving manager. Best-effort.
    try:
        from utils.api_bsc_bridge import emit_bsc_for
        emit_bsc_for([app.get("created_by"), str(user.get("username", "") or "")])
    except Exception:
        pass
    return {"application": lam.get(app_id),
            "status": str(lam.get(app_id).get("status", "")),
            "committee_result": result}


# ─────────────────────────────────────────────────────────────────────
# Credit work-pool visibility config (admin-configurable)
# GET/POST /api/lms/config/pool-visibility — which credit roles see the
# work pool, and at which statuses. Admin-only write. Mirrors the
# config-not-hardcode pattern used across the platform.
# ─────────────────────────────────────────────────────────────────────


@router.get("/config/pool-visibility")
def lms_pool_visibility_get(
    user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """Read the credit work-pool visibility policy (roles + statuses).
    Readable by any authenticated user (so the UI can show it); only
    admins may write it."""
    from utils.api_lms_scope import get_pool_visibility_config
    return {"pool_visibility": get_pool_visibility_config()}


@router.post("/config/pool-visibility")
def lms_pool_visibility_set(
    payload: Dict[str, Any],
    user: Dict[str, Any] = Depends(require_config_admin),
) -> Dict[str, Any]:
    """Update the credit work-pool visibility policy. Admin only (uses the
    same require_config_admin gate as the other admin config endpoints).

    Body: { roles: [str], statuses: [str] }. Both optional; whichever is
    provided replaces that list. Atomic write + backup-before-mutation."""
    roles = payload.get("roles")
    statuses = payload.get("statuses")
    if roles is not None and not (isinstance(roles, list) and all(isinstance(r, str) for r in roles)):
        raise HTTPException(status_code=400, detail="roles must be a list of strings")
    if statuses is not None and not (isinstance(statuses, list) and all(isinstance(s, str) for s in statuses)):
        raise HTTPException(status_code=400, detail="statuses must be a list of strings")
    if roles is None and statuses is None:
        raise HTTPException(status_code=400, detail="Provide roles and/or statuses")

    import json as _json, os as _os, tempfile as _tempfile
    from datetime import datetime as _dt
    from pathlib import Path as _Path
    p = _Path(__file__).resolve().parent.parent / "data" / "lms_config.json"
    try:
        cfg = _json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    except Exception:
        cfg = {}
    if not isinstance(cfg, dict):
        cfg = {}
    section = cfg.get("pool_visibility")
    if not isinstance(section, dict):
        section = {}
    if roles is not None:
        section["roles"] = roles
    if statuses is not None:
        section["statuses"] = statuses
    cfg["pool_visibility"] = section

    # Backup-before-mutation + atomic write.
    try:
        if p.exists():
            backup = p.with_suffix(f".pre_poolvis_{_dt.now():%Y%m%d-%H%M%S}.json")
            backup.write_text(p.read_text(encoding="utf-8"), encoding="utf-8")
        fd, tmp = _tempfile.mkstemp(dir=str(p.parent), suffix=".tmp")
        with _os.fdopen(fd, "w", encoding="utf-8") as fh:
            _json.dump(cfg, fh, ensure_ascii=False, indent=2)
            fh.flush()
            _os.fsync(fh.fileno())
        _os.replace(tmp, str(p))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Could not save config: {e}")

    audit_log("LMS_POOL_VISIBILITY_SET",
              str(user.get("username", "") or ""),
              f"roles={section.get('roles')}|statuses={section.get('statuses')}")
    from utils.api_lms_scope import get_pool_visibility_config
    return {"pool_visibility": get_pool_visibility_config()}
