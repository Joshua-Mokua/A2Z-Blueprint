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

    from utils.api import _attach_sla_to_apps as _attach_sla
    _attach_sla(apps)
    return {
        "applications": apps,
        "count": len(apps),
        "source": "loan_application_manager",
    }


# ─────────────────────────────────────────────────────────────────────
# GET /api/lms/applications/{app_id} — detail + permissions
# ─────────────────────────────────────────────────────────────────────


@router.get("/flow-by-stage")
def lms_flow_by_stage(
    user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """Pipeline-origin credit flow grouped by workflow stage — the live credit
    workload for Operations to prep against, scoped to the caller's cascade.

    This is deliberately NOT the loan book / NPL view (that's deferred to the
    Phase-2 Credit Monitoring module). It only reflects in-flight credit cases
    that originated from the pipeline, bucketed by their lifecycle stage so a
    team can see how much work sits at each step.

    Returns ordered stages, each with {key, label, count, value}, plus totals.
    """
    lam = _lam()
    visible_codes = get_visible_staff_codes(user)
    caller_code = str(user.get('staff_code', '') or '')
    apps = filter_apps_by_visibility(
        lam.apps, visible_codes, caller_code,
        caller_role=str(user.get('role', '') or ''),
    )

    # Operations-facing stage buckets (ordered along the credit workflow). Each
    # raw LMS status maps to exactly one bucket; terminal/closed outcomes are
    # surfaced separately so the live work-in-progress is clear.
    STAGE_ORDER = [
        ("intake",        "Intake / submitted",      {"submitted"}),
        ("assessment",    "Under assessment",        {"assigned", "updated"}),
        ("decision",      "Decisioned",              {"decision_approved", "decision_returned", "returned"}),
        ("offer",         "Offer & acceptance",      {"offer_issued", "offer_signed", "offer_validated"}),
        ("credit_admin",  "Credit admin / security", {"credit_admin"}),
        ("disbursement",  "Cleared for disbursement",{"cleared_for_disbursement"}),
        ("disbursed",     "Disbursed",               {"disbursed"}),
        ("declined",      "Declined",                {"declined"}),
    ]
    status_to_bucket = {}
    for key, _label, statuses in STAGE_ORDER:
        for s in statuses:
            status_to_bucket[s] = key

    buckets = {key: {"key": key, "label": label, "count": 0, "value": 0.0}
               for key, label, _ in STAGE_ORDER}
    other = {"key": "other", "label": "Other / unmapped", "count": 0, "value": 0.0}

    for a in apps:
        st = str(a.get("status", "") or "").strip().lower()
        try:
            amt = float(a.get("amount") or 0)
        except (TypeError, ValueError):
            amt = 0.0
        target = buckets.get(status_to_bucket.get(st)) if st in status_to_bucket else other
        if target is None:
            target = other
        target["count"] += 1
        target["value"] += amt

    stages = [buckets[key] for key, _, _ in STAGE_ORDER]
    if other["count"]:
        stages.append(other)

    # "In flight" = everything not yet terminal (disbursed/declined).
    terminal = {"disbursed", "declined"}
    in_flight = [s for s in stages if s["key"] not in terminal]
    return {
        "stages": stages,
        "totals": {
            "count": sum(s["count"] for s in stages),
            "value": sum(s["value"] for s in stages),
            "in_flight_count": sum(s["count"] for s in in_flight),
            "in_flight_value": sum(s["value"] for s in in_flight),
        },
        "source": "loan_application_manager",
    }


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

    try:
        from utils.api import _app_sla_status as _app_sla
        app["sla"] = _app_sla(app) or None
    except Exception:
        pass

    # Phase C part 1: compute the merged Case Journey (application history
    # + the linked pipeline deal's creation / committee / appeal / stage
    # events), normalised to the Timeline shape and ordered oldest-first.
    # Non-persisted — attached to the in-memory record like `sla` above.
    # Never fails the read: build_case_journey swallows deal-fetch errors.
    try:
        from utils.api_lms_journey import build_case_journey
        app["journey"] = build_case_journey(app)
    except Exception:
        app["journey"] = list(app.get("history") or [])

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
    if not user.get('is_admin') and not is_app_in_scope(
            app, visible_codes, caller_code,
            caller_role=str(user.get('role', '') or '')):
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

    # B2: clear any pending assignment requests now the case is assigned.
    # C2: stamp the assignment purpose (decisioning | correctness) from the payload.
    try:
        _purpose = str(payload_dict.get("purpose", "") or "decisioning").lower()
        if _purpose not in ("decisioning", "correctness"):
            _purpose = "decisioning"
        lam.update(app_id, {"assignment_requests": [], "assignment_purpose": _purpose})
    except Exception:
        pass
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
    if not user.get('is_admin') and not is_app_in_scope(
            app, visible_codes, caller_code,
            caller_role=str(user.get('role', '') or '')):
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
    payload: Dict[str, Any] = None,
    user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """Refer an application to the credit committee. Manager-tier.

    CF-8: an optional `entry_tier` (number) lets CIB / head-office cases enter
    ABOVE the branch tier (skip the Branch Credit Committee). Omitted = enters
    at the first tier."""
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
    entry_tier = None
    if isinstance(payload, dict) and payload.get("entry_tier") is not None:
        try:
            entry_tier = int(payload.get("entry_tier"))
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="entry_tier must be a number")
    lam.refer_to_committee(app_id, by=str(user.get("username", "") or ""), entry_tier=entry_tier)
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


# ─────────────────────────────────────────────────────────────────────
# Analyst escalation ("seek guidance") + line-manager input
# POST /applications/{id}/escalate        — analyst routes to line manager
# POST /applications/{id}/manager-view    — line manager records input
# ─────────────────────────────────────────────────────────────────────


@router.post("/applications/{app_id}/escalate",
             response_model=LoanAppMutationResponse)
def lms_application_escalate(
    app_id: str,
    payload: Dict[str, Any],
    user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """Assigned analyst seeks guidance / cannot decide alone — routes the
    case to their line manager for input. Gated by can_escalate."""
    lam = _lam()
    app = lam.get(app_id)
    if not app:
        raise HTTPException(status_code=404, detail=f"Application '{app_id}' not found")
    visible_codes = get_visible_staff_codes(user)
    perms = resolve_application_permissions(user, app, visible_codes)
    if not perms.get("can_escalate"):
        raise HTTPException(status_code=403,
                            detail="You cannot escalate this application")
    reason = str(payload.get("reason", "") or "").strip()
    if len(reason) < 3:
        raise HTTPException(status_code=400,
                            detail="An escalation reason is required")
    ok = lam.escalate(app_id, by=str(user.get("username", "") or ""),
                      reason=reason, to_manager=str(payload.get("to_manager", "") or ""))
    if not ok:
        raise HTTPException(status_code=500, detail="escalate failed")
    audit_log("LMS_ESCALATED", str(user.get("username", "") or ""), f"{app_id}|{reason[:60]}")
    return {"application": lam.get(app_id), "status": str(lam.get(app_id).get("status", ""))}


@router.post("/applications/{app_id}/manager-view",
             response_model=LoanAppMutationResponse)
def lms_application_manager_view(
    app_id: str,
    payload: Dict[str, Any],
    user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """Line manager records their input/views on an escalated case. The
    manager must have the app in scope (manager-tier or admin)."""
    lam = _lam()
    app = lam.get(app_id)
    if not app:
        raise HTTPException(status_code=404, detail=f"Application '{app_id}' not found")
    visible_codes = get_visible_staff_codes(user)
    caller_code = str(user.get('staff_code', '') or '')
    if not user.get('is_admin') and not is_app_in_scope(
            app, visible_codes, caller_code,
            caller_role=str(user.get('role', '') or '')):
        raise HTTPException(status_code=403, detail="Application is out of scope")
    view = str(payload.get("view", "") or "").strip()
    if len(view) < 3:
        raise HTTPException(status_code=400, detail="A manager view is required")
    ok = lam.add_manager_view(app_id, by=str(user.get("username", "") or ""), view=view)
    if not ok:
        raise HTTPException(status_code=500, detail="manager-view failed")
    audit_log("LMS_MANAGER_VIEW", str(user.get("username", "") or ""), f"{app_id}|{view[:60]}")
    return {"application": lam.get(app_id), "status": str(lam.get(app_id).get("status", ""))}


# ─────────────────────────────────────────────────────────────────────
# Attachments (reference mode) + Branch Credit Committee (BCC) record
# GET  /applications/{id}/attachments        — list attachment refs
# POST /applications/{id}/attachments        — add an attachment ref
# POST /applications/{id}/bcc                 — record the BCC outcome
# Files live in the bank's document store; we record filename + ref, the
# platform's established attachment pattern (signed_offer_attachment).
# ─────────────────────────────────────────────────────────────────────

ATTACHMENT_KINDS = {
    "bcc_minutes", "financials", "kyc", "valuation", "collateral",
    "bank_statements", "board_resolution", "other",
}


@router.get("/applications/{app_id}/attachments")
def lms_application_attachments_list(
    app_id: str,
    user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """List a case's attachment references. Visible to anyone who can view
    the application (cascade / assigned analyst / credit pool / admin)."""
    lam = _lam()
    app = lam.get(app_id)
    if not app:
        raise HTTPException(status_code=404, detail=f"Application '{app_id}' not found")
    visible_codes = get_visible_staff_codes(user)
    perms = resolve_application_permissions(user, app, visible_codes)
    if not perms.get("can_view"):
        raise HTTPException(status_code=403, detail="Application is out of scope")
    return {"attachments": lam.list_attachments(app_id), "bcc": app.get("bcc")}


@router.post("/applications/{app_id}/attachments")
def lms_application_attachment_add(
    app_id: str,
    payload: Dict[str, Any],
    user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """Add an attachment reference (filename + storage ref). The caller must
    be able to view the application. `kind` categorises it."""
    lam = _lam()
    app = lam.get(app_id)
    if not app:
        raise HTTPException(status_code=404, detail=f"Application '{app_id}' not found")
    visible_codes = get_visible_staff_codes(user)
    perms = resolve_application_permissions(user, app, visible_codes)
    if not perms.get("can_view"):
        raise HTTPException(status_code=403, detail="Application is out of scope")
    kind = str(payload.get("kind", "other") or "other").strip().lower()
    if kind not in ATTACHMENT_KINDS:
        kind = "other"
    filename = str(payload.get("filename", "") or "").strip()
    ref = str(payload.get("ref", "") or "").strip()
    if not filename and not ref:
        raise HTTPException(status_code=400, detail="Provide a filename and/or ref")
    rec = lam.add_attachment(app_id, by=str(user.get("username", "") or ""),
                             kind=kind, filename=filename, ref=ref,
                             meta=payload.get("meta") if isinstance(payload.get("meta"), dict) else None)
    if rec is None:
        raise HTTPException(status_code=500, detail="attachment add failed")
    audit_log("LMS_ATTACHMENT_ADDED", str(user.get("username", "") or ""), f"{app_id}|{kind}|{filename}")
    return {"attachment": rec, "attachments": lam.list_attachments(app_id)}


@router.post("/applications/{app_id}/bcc")
def lms_application_bcc_record(
    app_id: str,
    payload: Dict[str, Any],
    user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """Record the Branch Credit Committee (BCC) outcome at branch origin —
    verdict, chair (branch manager), attendees/signatories, minutes, and a
    reference to the signed minutes file. Caller must be able to view the
    application (branch-side staff in cascade)."""
    lam = _lam()
    app = lam.get(app_id)
    if not app:
        raise HTTPException(status_code=404, detail=f"Application '{app_id}' not found")
    visible_codes = get_visible_staff_codes(user)
    perms = resolve_application_permissions(user, app, visible_codes)
    if not perms.get("can_view"):
        raise HTTPException(status_code=403, detail="Application is out of scope")
    verdict = str(payload.get("verdict", "") or "").strip()
    if verdict.lower() not in {"approved", "declined", "recommended", "deferred"}:
        raise HTTPException(status_code=400,
                            detail="BCC verdict must be approved / declined / recommended / deferred")
    attendees = payload.get("attendees")
    if attendees is not None and not isinstance(attendees, list):
        raise HTTPException(status_code=400, detail="attendees must be a list")
    bcc = lam.add_bcc_record(
        app_id, by=str(user.get("username", "") or ""),
        verdict=verdict, branch=str(payload.get("branch", "") or ""),
        chaired_by=str(payload.get("chaired_by", "") or ""),
        attendees=attendees or [], minutes=str(payload.get("minutes", "") or ""),
        filename=str(payload.get("filename", "") or ""),
        ref=str(payload.get("ref", "") or ""))
    if bcc is None:
        raise HTTPException(status_code=500, detail="bcc record failed")
    audit_log("LMS_BCC_RECORDED", str(user.get("username", "") or ""), f"{app_id}|{verdict}")
    return {"bcc": bcc, "attachments": lam.list_attachments(app_id)}


# ─────────────────────────────────────────────────────────────────────
# Credit Report (CR) — hybrid auto-populated appraisal memo
# GET  /applications/{id}/cr   — template + auto/CBS values + saved RM values
# POST /applications/{id}/cr   — relationship owner saves filled fields
# ─────────────────────────────────────────────────────────────────────


@router.get("/applications/{app_id}/cr")
def lms_application_cr_get(
    app_id: str,
    user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """Return the Credit Report for a case: the (config-driven) template, the
    auto-populated values from the application + best-effort CBS, and any
    RM-saved values. Visible to anyone who can view the application."""
    from utils.api_lms_cr import build_cr_view
    lam = _lam()
    app = lam.get(app_id)
    if not app:
        raise HTTPException(status_code=404, detail=f"Application '{app_id}' not found")
    visible_codes = get_visible_staff_codes(user)
    perms = resolve_application_permissions(user, app, visible_codes)
    if not perms.get("can_view"):
        raise HTTPException(status_code=403, detail="Application is out of scope")
    return {"cr": build_cr_view(app)}


@router.post("/applications/{app_id}/cr")
def lms_application_cr_save(
    app_id: str,
    payload: Dict[str, Any],
    user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """Save the relationship owner's CR field values. The caller must be able
    to view the application (RM owner / analyst / credit pool / admin). If
    `completed` is true, required fields are enforced."""
    from utils.api_lms_cr import build_cr_view, missing_required
    lam = _lam()
    app = lam.get(app_id)
    if not app:
        raise HTTPException(status_code=404, detail=f"Application '{app_id}' not found")
    visible_codes = get_visible_staff_codes(user)
    perms = resolve_application_permissions(user, app, visible_codes)
    if not perms.get("can_view"):
        raise HTTPException(status_code=403, detail="Application is out of scope")
    values = payload.get("values")
    if not isinstance(values, dict):
        raise HTTPException(status_code=400, detail="values must be an object")
    completed = bool(payload.get("completed"))
    if completed:
        missing = missing_required(app, values)
        if missing:
            raise HTTPException(
                status_code=400,
                detail="Cannot mark CR complete — required fields missing: "
                       + ", ".join(missing))
    cr = lam.save_cr(app_id, by=str(user.get("username", "") or ""),
                     values=values, completed=completed)
    if cr is None:
        raise HTTPException(status_code=500, detail="CR save failed")
    audit_log("LMS_CR_SAVED", str(user.get("username", "") or ""), f"{app_id}|completed={completed}")
    return {"cr": build_cr_view(lam.get(app_id))}


# ─────────────────────────────────────────────────────────────────────
# CF-8 — Multi-tier credit committee ladder
# GET  /committee/tiers                         — the ordered tier ladder
# POST /applications/{id}/committee/submit-upward — push case to next tier
# ─────────────────────────────────────────────────────────────────────


@router.get("/committee/tiers")
def lms_committee_tiers(
    user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """The ordered committee tier ladder (Branch CC → Management CC → Board CC
    → Group). Admin-configurable via lms_config.json -> committee_tiers."""
    from utils.api_lms_committee_tiers import get_committee_tiers
    return {"tiers": get_committee_tiers()}


@router.post("/committee/tiers")
def lms_committee_tiers_set(
    payload: Dict[str, Any],
    user: Dict[str, Any] = Depends(require_config_admin),
) -> Dict[str, Any]:
    """Replace the committee tier ladder. Admin only (require_config_admin,
    same gate as the other admin-config endpoints).

    Body: { tiers: [ {tier:int, key?:str, name:str, authority_limit_kes?:num|null,
    can_be_entry?:bool}, ... ] }. The list must be non-empty. Tiers are
    normalised + sorted by tier number. Atomic write + backup-before-mutation.
    """
    tiers = payload.get("tiers")
    if not isinstance(tiers, list) or not tiers:
        raise HTTPException(status_code=400,
                            detail="tiers must be a non-empty list")
    # Validate + normalise each tier entry.
    norm: List[Dict[str, Any]] = []
    seen_numbers = set()
    for entry in tiers:
        if not isinstance(entry, dict):
            raise HTTPException(status_code=400,
                                detail="each tier must be an object")
        try:
            tn = int(entry.get("tier"))
        except (TypeError, ValueError):
            raise HTTPException(status_code=400,
                                detail="each tier needs an integer 'tier' number")
        if tn in seen_numbers:
            raise HTTPException(status_code=400,
                                detail=f"duplicate tier number {tn}")
        seen_numbers.add(tn)
        name = str(entry.get("name", "") or "").strip()
        if not name:
            raise HTTPException(status_code=400,
                                detail=f"tier {tn} needs a name")
        lim = entry.get("authority_limit_kes")
        if lim is not None:
            try:
                lim = float(lim)
            except (TypeError, ValueError):
                raise HTTPException(status_code=400,
                                    detail=f"tier {tn} authority_limit_kes must be a number or null")
        norm.append({
            "tier": tn,
            "key": str(entry.get("key", f"tier_{tn}")),
            "name": name,
            "authority_limit_kes": lim,
            "can_be_entry": bool(entry.get("can_be_entry", True)),
        })
    norm.sort(key=lambda x: x["tier"])

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
    cfg["committee_tiers"] = norm

    # Backup-before-mutation + atomic write.
    try:
        if p.exists():
            backup = p.with_suffix(f".pre_tiers_{_dt.now():%Y%m%d-%H%M%S}.json")
            backup.write_text(p.read_text(encoding="utf-8"), encoding="utf-8")
        fd, tmp = _tempfile.mkstemp(dir=str(p.parent), suffix=".tmp")
        with _os.fdopen(fd, "w", encoding="utf-8") as fh:
            _json.dump(cfg, fh, ensure_ascii=False, indent=2)
            fh.flush()
            _os.fsync(fh.fileno())
        _os.replace(tmp, str(p))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Could not save config: {e}")

    audit_log("LMS_COMMITTEE_TIERS_SET",
              str(user.get("username", "") or ""),
              f"tiers={len(norm)}")
    from utils.api_lms_committee_tiers import get_committee_tiers
    return {"tiers": get_committee_tiers(), "status": "saved"}


@router.post("/applications/{app_id}/committee/submit-upward",
             response_model=LoanAppMutationResponse)
def lms_committee_submit_upward(
    app_id: str,
    payload: Dict[str, Any] = None,
    user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """The current tier's committee submits the case UP to the next tier.
    Manager-tier. The prior tier's deliberation is preserved in tier_history;
    the new tier starts with a fresh vote slate."""
    if not is_manager(user):
        raise HTTPException(status_code=403,
                            detail="Manager authority required to submit upward")
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
    note = str((payload or {}).get("note", "") or "")
    res = lam.submit_committee_upward(app_id, by=str(user.get("username", "") or ""), note=note)
    if not res.get("ok"):
        raise HTTPException(status_code=400, detail=res.get("reason", "cannot submit upward"))
    audit_log("LMS_COMMITTEE_SUBMITTED_UPWARD",
              str(user.get("username", "") or ""), f"{app_id}|tier={res.get('tier')}")
    return {"application": lam.get(app_id), "status": "referred_to_committee"}


# === B2: ASSIGNMENT REQUESTS ===
@router.post("/applications/{app_id}/request-assignment",
             response_model=LoanAppMutationResponse)
def lms_request_assignment(
    app_id: str,
    payload: Dict[str, Any] = None,
    user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """An analyst requests to be assigned an unassigned (pool) case. The caller
    must be able to see the case (pool visibility) and the case must be
    unassigned + submitted. Records the request on the app; the Chief resolves it."""
    lam = _lam()
    app = lam.get(app_id)
    if not app:
        raise HTTPException(status_code=404, detail=f"Application '{app_id}' not found")
    visible_codes = get_visible_staff_codes(user)
    caller_code = str(user.get('staff_code', '') or '')
    caller_role = str(user.get('role', '') or '')
    if not user.get('is_admin') and not is_app_in_scope(app, visible_codes, caller_code, caller_role=caller_role):
        raise HTTPException(status_code=403, detail="Application is out of scope")
    if (app.get('analyst') or {}).get('code'):
        raise HTTPException(status_code=400, detail="This case is already assigned.")
    if str(app.get('status', '') or '').lower() != 'submitted':
        raise HTTPException(status_code=400, detail="Only submitted (unassigned) cases can be requested.")
    from datetime import datetime as _dt
    reqs = list(app.get('assignment_requests', []) or [])
    if any(str(r.get('by_code')) == caller_code for r in reqs):
        raise HTTPException(status_code=400, detail="You have already requested this case.")
    reqs.append({
        "by_code": caller_code,
        "by_name": str(user.get('full_name', '') or user.get('username', '') or ''),
        "at": _dt.now().isoformat(timespec="seconds"),
        "note": str((payload or {}).get('note', '') or ''),
    })
    lam.update(app_id, {"assignment_requests": reqs})
    audit_log("LMS_ASSIGNMENT_REQUESTED", str(user.get('username', '') or ''),
              f"{app_id}|by={caller_code}")
    return {"application": lam.get(app_id), "status": "requested"}


@router.get("/applications/assignment-requests")
def lms_assignment_requests(
    user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """The consolidated list of cases with pending assignment requests, for a
    manager to resolve. Manager-tier only. Scoped to the caller's visibility."""
    if not is_manager(user):
        raise HTTPException(status_code=403, detail="Manager authority required")
    lam = _lam()
    visible_codes = get_visible_staff_codes(user)
    caller_code = str(user.get('staff_code', '') or '')
    caller_role = str(user.get('role', '') or '')
    out = []
    for app in lam.apps:
        reqs = app.get('assignment_requests') or []
        if not reqs:
            continue
        if (app.get('analyst') or {}).get('code'):
            continue  # already assigned — requests are moot
        if not user.get('is_admin') and not is_app_in_scope(app, visible_codes, caller_code, caller_role=caller_role):
            continue
        out.append({
            "id": app.get("id"),
            "client_name": app.get("client_name"),
            "product": app.get("product"),
            "amount": app.get("amount"),
            "rm_name": app.get("rm_name"),
            "status": app.get("status"),
            "requests": reqs,
        })
    return {"cases": out, "count": len(out)}
# === END B2: ASSIGNMENT REQUESTS ===


# === C1: COMMITTEE ROUTING (suggest tier by limit) ===
def _suggest_committee_tier(amount_kes: float) -> dict:
    """First tier whose authority_limit_kes >= amount (i.e. can decide it).
    A tier with authority_limit_kes None (uncapped) catches everything above the
    highest limit. Returns the suggested tier dict, or the highest tier."""
    from utils.api_lms_committee_tiers import get_committee_tiers
    tiers = get_committee_tiers()
    if not tiers:
        return {}
    # tiers sorted ascending by tier number; limits generally increase.
    for t in tiers:
        lim = t.get("authority_limit_kes")
        if lim is None:
            return t  # uncapped — decides anything
        try:
            if amount_kes <= float(lim):
                return t
        except (TypeError, ValueError):
            continue
    return tiers[-1]  # above all limits -> highest tier


@router.get("/applications/{app_id}/committee-routing")
def lms_committee_routing(
    app_id: str,
    user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """Routing helper for the Chief: the tier ladder + the tier suggested by the
    case amount + whether it can be referred now. Manager-tier."""
    from utils.api_lms_committee_tiers import get_committee_tiers
    lam = _lam()
    app = lam.get(app_id)
    if not app:
        raise HTTPException(status_code=404, detail=f"Application '{app_id}' not found")
    visible_codes = get_visible_staff_codes(user)
    caller_code = str(user.get('staff_code', '') or '')
    caller_role = str(user.get('role', '') or '')
    if not user.get('is_admin') and not is_app_in_scope(app, visible_codes, caller_code, caller_role=caller_role):
        raise HTTPException(status_code=403, detail="Application is out of scope")
    try:
        amount = float(app.get("amount") or 0)
    except (TypeError, ValueError):
        amount = 0.0
    final = _suggest_committee_tier(amount)
    entry = _committee_entry_tier(amount)
    can_refer = is_manager(user) and is_valid_lms_transition(
        str(app.get("status", "")), "referred_to_committee")
    return {
        "tiers": get_committee_tiers(),
        "amount": amount,
        # C1b: entry (where it starts) vs final (ultimate authority). The case
        # climbs from entry to final, capturing each verdict.
        "entry_tier": entry.get("tier"),
        "entry_name": entry.get("name"),
        "final_tier": final.get("tier"),
        "final_name": final.get("name"),
        "require_mcc": _committee_require_mcc(),
        "must_climb": bool(entry.get("tier") and final.get("tier")
                           and entry.get("tier") != final.get("tier")),
        # back-compat: suggested_* now points at the ENTRY tier (what to pre-select).
        "suggested_tier": entry.get("tier"),
        "suggested_name": entry.get("name"),
        "can_refer": bool(can_refer),
        "current_status": app.get("status"),
    }
# === END C1: COMMITTEE ROUTING ===


# === C1b: CLIMB LADDER + MCC-MANDATORY ===
def _committee_require_mcc() -> bool:
    """Admin toggle: cases needing Board/Group must pass MCC first. Default True."""
    try:
        from pathlib import Path as _Path
        p = _Path(__file__).resolve().parent.parent / "data" / "lms_config.json"
        if p.exists():
            import json as _json
            cfg = _json.loads(p.read_text(encoding="utf-8")) or {}
            v = cfg.get("require_mcc_before_higher")
            if v is not None:
                return bool(v)
    except Exception:
        pass
    return True


def _committee_mcc_tier() -> dict:
    """The MCC tier (key management_cc), or the middle tier as a fallback."""
    from utils.api_lms_committee_tiers import get_committee_tiers
    tiers = get_committee_tiers()
    for t in tiers:
        if str(t.get("key", "")).lower() in ("management_cc", "mcc"):
            return t
    # fallback: second tier if present
    return tiers[1] if len(tiers) > 1 else (tiers[0] if tiers else {})


def _committee_entry_tier(amount_kes: float) -> dict:
    """The tier the case ENTERS at. If the final authority is above MCC and the
    require-MCC rule is on, entry = MCC (the case then climbs). Otherwise entry =
    the final authority tier (small cases enter directly at their committee)."""
    final = _suggest_committee_tier(amount_kes)
    if not final:
        return {}
    if not _committee_require_mcc():
        return final
    mcc = _committee_mcc_tier()
    if not mcc:
        return final
    try:
        # if the final authority sits ABOVE MCC, the case must enter at MCC.
        if int(final.get("tier", 0)) > int(mcc.get("tier", 0)):
            return mcc
    except (TypeError, ValueError):
        pass
    return final
# === END C1b ===



@router.post("/committee/require-mcc")
def lms_committee_set_require_mcc(
    payload: Dict[str, Any] = None,
    user: Dict[str, Any] = Depends(require_config_admin),
) -> Dict[str, Any]:
    """Admin toggle: require MCC before Board/Group. Config-admin gated."""
    enabled = bool((payload or {}).get("enabled", True))
    from pathlib import Path as _Path
    p = _Path(__file__).resolve().parent.parent / "data" / "lms_config.json"
    import json as _json
    cfg = {}
    try:
        if p.exists():
            cfg = _json.loads(p.read_text(encoding="utf-8")) or {}
    except Exception:
        cfg = {}
    cfg["require_mcc_before_higher"] = enabled
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(_json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    import os as _os
    _os.replace(str(tmp), str(p))
    return {"status": "saved", "require_mcc_before_higher": enabled}


# === C2: CORRECTNESS STAGING ===
@router.post("/applications/{app_id}/committee-readiness",
             response_model=LoanAppMutationResponse)
def lms_committee_readiness(
    app_id: str,
    payload: Dict[str, Any] = None,
    user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """A correctness reviewer marks a case ready_for_committee or returns it for
    rework, optionally keying an opinion for the Chief. The assigned reviewer OR a
    manager may act. Ready cases become routable to committee; rework cases stay in
    staging with a reason so they can be fixed and re-submitted."""
    lam = _lam()
    app = lam.get(app_id)
    if not app:
        raise HTTPException(status_code=404, detail=f"Application '{app_id}' not found")
    visible_codes = get_visible_staff_codes(user)
    caller_code = str(user.get('staff_code', '') or '')
    caller_role = str(user.get('role', '') or '')
    if not user.get('is_admin') and not is_app_in_scope(app, visible_codes, caller_code, caller_role=caller_role):
        raise HTTPException(status_code=403, detail="Application is out of scope")
    # Only the assigned reviewer or a manager may set readiness.
    is_assignee = str((app.get('analyst') or {}).get('code') or '') == caller_code
    if not (is_assignee or is_manager(user) or user.get('is_admin')):
        raise HTTPException(status_code=403, detail="Only the assigned reviewer or a manager can set readiness")
    p = payload or {}
    decision = str(p.get("decision", "") or "").lower()  # "ready" | "rework"
    if decision not in ("ready", "rework"):
        raise HTTPException(status_code=400, detail="decision must be 'ready' or 'rework'")
    from datetime import datetime as _dt
    readiness = {
        "state": "ready_for_committee" if decision == "ready" else "returned_for_rework",
        "by_code": caller_code,
        "by_name": str(user.get('full_name', '') or user.get('username', '') or ''),
        "at": _dt.now().isoformat(timespec="seconds"),
        "opinion": str(p.get("opinion", "") or ""),
        "reasons": p.get("reasons") if isinstance(p.get("reasons"), list) else [],
    }
    lam.update(app_id, {"committee_readiness": readiness})
    audit_log("LMS_COMMITTEE_READINESS",
              str(user.get('username', '') or ''), f"{app_id}|{readiness['state']}")
    return {"application": lam.get(app_id), "status": readiness["state"]}
# === END C2: CORRECTNESS STAGING ===


# === C3a: COMMITTEE PRE-READ ===
_PREREAD_VIEWS = ("leaning_approve", "leaning_decline", "questions")

@router.post("/applications/{app_id}/committee/pre-read",
             response_model=LoanAppMutationResponse)
def lms_committee_pre_read(
    app_id: str,
    payload: Dict[str, Any] = None,
    user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """A committee member records an independent, NON-BINDING pre-read on a case
    that is before the committee. This informs the convened meeting; it is not the
    binding vote. One pre-read per member (re-submitting updates it)."""
    lam = _lam()
    app = lam.get(app_id)
    if not app:
        raise HTTPException(status_code=404, detail=f"Application '{app_id}' not found")
    if str(app.get("status", "") or "") != "referred_to_committee":
        raise HTTPException(status_code=400, detail="Case is not before the committee")
    p = payload or {}
    view = str(p.get("view", "") or "").lower()
    if view not in _PREREAD_VIEWS:
        raise HTTPException(status_code=400,
                            detail=f"view must be one of {list(_PREREAD_VIEWS)}")
    caller_code = str(user.get('staff_code', '') or '')
    from datetime import datetime as _dt
    prereads = list(app.get("committee_prereads", []) or [])
    entry = {
        "by_code": caller_code,
        "by_name": str(user.get('full_name', '') or user.get('username', '') or ''),
        "view": view,
        "note": str(p.get("note", "") or ""),
        "at": _dt.now().isoformat(timespec="seconds"),
        "tier": (app.get("committee") or {}).get("current_tier"),
    }
    # replace this member's prior pre-read at the current tier, if any.
    prereads = [r for r in prereads
                if not (str(r.get("by_code")) == caller_code and r.get("tier") == entry["tier"])]
    prereads.append(entry)
    lam.update(app_id, {"committee_prereads": prereads})
    audit_log("LMS_COMMITTEE_PREREAD", str(user.get('username', '') or ''),
              f"{app_id}|{view}")
    return {"application": lam.get(app_id), "status": "pre_read_recorded"}


@router.get("/applications/{app_id}/committee/pre-reads")
def lms_committee_pre_reads(
    app_id: str,
    user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """The collected pre-reads for a case (for the Chief / MD to see leanings)."""
    lam = _lam()
    app = lam.get(app_id)
    if not app:
        raise HTTPException(status_code=404, detail=f"Application '{app_id}' not found")
    prereads = app.get("committee_prereads", []) or []
    cur_tier = (app.get("committee") or {}).get("current_tier")
    at_tier = [r for r in prereads if r.get("tier") == cur_tier]
    tally = {v: sum(1 for r in at_tier if r.get("view") == v) for v in _PREREAD_VIEWS}
    return {"pre_reads": at_tier, "all": prereads, "tally": tally,
            "current_tier": cur_tier}
# === END C3a ===


# === C3b: MEMBER PRE-READ QUEUE ===
def _member_committee_names(staff_code: str) -> set:
    """Committee names (palette) whose members include this staff_code."""
    try:
        from utils.api import _read_committee_palette
        pal = _read_committee_palette() or []
    except Exception:
        pal = []
    names = set()
    for c in pal:
        for m in (c.get("members") or []):
            if str(m.get("staff_code", "") or "") == str(staff_code):
                names.add(str(c.get("name", "") or "").strip().lower())
    return names


@router.get("/committee/my-pre-read-queue")
def lms_member_pre_read_queue(
    user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """Referred cases awaiting THIS member's non-binding pre-read. A member sees
    cases at a committee they belong to (by name match to current tier), plus (as a
    scope-safe fallback) referred cases visible to them. Each case flags whether the
    member has already pre-read it at the current tier."""
    lam = _lam()
    caller_code = str(user.get('staff_code', '') or '')
    my_committees = _member_committee_names(caller_code)
    visible_codes = get_visible_staff_codes(user)
    caller_role = str(user.get('role', '') or '')
    out = []
    for app in lam.apps:
        if str(app.get("status", "") or "") != "referred_to_committee":
            continue
        committee = app.get("committee") or {}
        tier_name = str(committee.get("current_tier_name", "") or "").strip().lower()
        in_my_committee = bool(my_committees and tier_name in my_committees)
        in_scope = user.get('is_admin') or is_app_in_scope(
            app, visible_codes, caller_code, caller_role=caller_role)
        # Show if it's my committee, OR (fallback) it's referred and in my scope.
        if not (in_my_committee or in_scope):
            continue
        prereads = app.get("committee_prereads", []) or []
        cur_tier = committee.get("current_tier")
        mine = next((r for r in prereads
                     if str(r.get("by_code")) == caller_code and r.get("tier") == cur_tier), None)
        out.append({
            "id": app.get("id"),
            "client_name": app.get("client_name"),
            "product": app.get("product"),
            "amount": app.get("amount"),
            "current_tier": cur_tier,
            "current_tier_name": committee.get("current_tier_name"),
            "in_my_committee": in_my_committee,
            "my_pre_read": mine,
            "sla": app.get("sla"),
        })
    return {"cases": out, "count": len(out),
            "pending": sum(1 for c in out if not c["my_pre_read"])}
# === END C3b ===


# === C4: MD CONVENING QUEUE ===
@router.get("/committee/convening-queue")
def lms_convening_queue(
    user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """Referred cases grouped by committee tier, for the MD to see what's awaiting
    convening. Each case carries its pre-read tally + whether it's convened yet.
    Manager-tier (the MD is a manager)."""
    if not is_manager(user):
        raise HTTPException(status_code=403, detail="Manager authority required")
    lam = _lam()
    visible_codes = get_visible_staff_codes(user)
    caller_code = str(user.get('staff_code', '') or '')
    caller_role = str(user.get('role', '') or '')
    _PREREAD_V = ("leaning_approve", "leaning_decline", "questions")
    tiers_map: Dict[Any, Dict[str, Any]] = {}
    for app in lam.apps:
        if str(app.get("status", "") or "") != "referred_to_committee":
            continue
        if not user.get('is_admin') and not is_app_in_scope(app, visible_codes, caller_code, caller_role=caller_role):
            continue
        committee = app.get("committee") or {}
        tier = committee.get("current_tier")
        tier_name = committee.get("current_tier_name")
        prereads = [r for r in (app.get("committee_prereads") or []) if r.get("tier") == tier]
        tally = {v: sum(1 for r in prereads if r.get("view") == v) for v in _PREREAD_V}
        case = {
            "id": app.get("id"),
            "client_name": app.get("client_name"),
            "product": app.get("product"),
            "amount": app.get("amount"),
            "pre_read_count": len(prereads),
            "pre_read_tally": tally,
            "convened": bool(committee.get("convened", False)),
            "sla": app.get("sla"),
        }
        key = tier if tier is not None else 0
        if key not in tiers_map:
            tiers_map[key] = {"tier": tier, "name": tier_name, "count": 0, "cases": []}
        tiers_map[key]["count"] += 1
        tiers_map[key]["cases"].append(case)
    tiers = [tiers_map[k] for k in sorted(tiers_map.keys(), key=lambda x: (x is None, x))]
    return {"tiers": tiers,
            "total": sum(t["count"] for t in tiers),
            "awaiting": sum(1 for t in tiers for c in t["cases"] if not c["convened"])}


@router.post("/applications/{app_id}/committee/convene",
             response_model=LoanAppMutationResponse)
def lms_committee_convene(
    app_id: str,
    payload: Dict[str, Any] = None,
    user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """The MD convenes the committee for a case — stamps committee.convened, opening
    the binding vote. Manager-tier."""
    if not is_manager(user):
        raise HTTPException(status_code=403, detail="Manager authority required to convene")
    lam = _lam()
    app = lam.get(app_id)
    if not app:
        raise HTTPException(status_code=404, detail=f"Application '{app_id}' not found")
    if str(app.get("status", "") or "") != "referred_to_committee":
        raise HTTPException(status_code=400, detail="Case is not before a committee")
    committee = dict(app.get("committee") or {})
    from datetime import datetime as _dt
    committee["convened"] = True
    committee["convened_by"] = str(user.get('full_name', '') or user.get('username', '') or '')
    committee["convened_at"] = _dt.now().isoformat(timespec="seconds")
    lam.update(app_id, {"committee": committee})
    audit_log("LMS_COMMITTEE_CONVENED", str(user.get('username', '') or ''), app_id)
    return {"application": lam.get(app_id), "status": "referred_to_committee"}
# === END C4 ===

