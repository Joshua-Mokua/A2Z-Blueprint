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

from utils.auth_jwt import get_current_user
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

    apps = filter_apps_by_visibility(lam.apps, visible_codes, caller_code)

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
    from utils.api_bsc_bridge import emit_bsc_trigger
    emit_bsc_trigger(str(user.get('username', '') or ''))

    updated = lam.get(app_id)
    return {
        "application": updated,
        "status": f"decision_{verdict_normalized}",
    }
