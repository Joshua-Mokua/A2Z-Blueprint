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

from datetime import datetime
from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import BaseModel

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
        by=str(user.get('staff_code', '') or user.get('username', '') or ''),
        by_name=str(user.get('full_name', '') or ''),
        by_role=str(user.get('role', '') or ''),
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
    # Real-time email: tell the assigned analyst a case is now theirs. Best-effort,
    # never blocks or breaks the assignment if email is down/unconfigured.
    try:
        from utils.notifications import notify_staff
        _client = str((updated or app or {}).get("client_name", "") or "a client")
        notify_staff(
            str(payload.analyst_code or ""),
            "A2Z MIS 360 — a credit case has been assigned to you",
            f"<html><body style='font-family:Arial,sans-serif;max-width:520px;margin:auto'>"
            f"<div style='background:#0082BB;padding:16px;border-radius:8px 8px 0 0'>"
            f"<h2 style='color:#fff;margin:0'>A2Z MIS 360</h2></div>"
            f"<div style='padding:20px;border:1px solid #e0e0e0;border-top:none;border-radius:0 0 8px 8px'>"
            f"<p>Hi <strong>{payload.analyst_name or ''}</strong>,</p>"
            f"<p>Credit application <strong>{app_id}</strong> ({_client}) has been assigned to you "
            f"for analysis. Please log in to A2Z MIS 360 to begin.</p>"
            f"<p style='font-size:12px;color:#999'>Automated message — do not reply.</p>"
            f"</div></body></html>",
        )
    except Exception:
        pass
    updated = lam.get(app_id)
    return {"application": updated, "status": "assigned"}


@router.post(
    "/applications/{app_id}/pick",
    response_model=LoanAppMutationResponse,
)
def lms_application_pick(
    app_id: str,
    user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """Self-pick: an analyst pulls an UNALLOCATED case to themselves.

    Unlike /assign (manager-tier, chooses who), /pick lets a credit analyst or a
    segment-specific Department Analyst assign an unallocated case (submitted, no
    analyst) to THEMSELVES — so work doesn't stall when the assigning manager
    (e.g. the Chief Credit) is away. Gated by can_self_pick (config-driven via
    credit_workflow.self_pick; segment analysts limited to their own segment).
    Reuses submit_to_credit with the caller as the analyst.
    """
    lam = _lam()
    app = lam.get(app_id)
    if not app:
        raise HTTPException(status_code=404, detail=f"Application '{app_id}' not found")

    perms = resolve_application_permissions(user, app)
    if not perms.get("can_self_pick"):
        raise HTTPException(
            status_code=403,
            detail=("You cannot self-pick this case — it is not unallocated, "
                    "not in your segment, or self-pick is disabled."),
        )

    caller_code = str(user.get('staff_code', '') or '')
    caller_name = str(user.get('full_name', '') or '')
    if not caller_code:
        raise HTTPException(status_code=400, detail="Caller has no staff code; cannot self-pick.")

    success = lam.submit_to_credit(
        app_id,
        analyst_code=caller_code,
        analyst_name=caller_name,
        by=caller_code,
        by_name=caller_name,
        by_role=str(user.get('role', '') or ''),
    )
    if not success:
        raise HTTPException(status_code=500, detail="Self-pick failed (manager method returned False)")

    audit_log("LMS_ANALYST_SELF_PICKED", str(user.get('username', '') or ''), f"{app_id}|{caller_code}")
    try:
        lam.update(app_id, {"assignment_requests": [], "assignment_purpose": "decisioning"})
    except Exception:
        pass
    updated = lam.get(app_id)
    return {"application": updated, "status": "assigned"}


@router.post(
    "/applications/{app_id}/submit-to-dcc",
    response_model=LoanAppMutationResponse,
)
def lms_application_submit_to_dcc(
    app_id: str,
    payload: Dict[str, Any] = None,
    user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """Department Analyst: voice support + submit the case to the Department
    Credit Committee (DCC). The Department Analyst does NOT decide — this records
    their support opinion + PEP confirmation and refers the case onward to the
    committee. Completeness gate: the configured required attachments (e.g. the
    Call-Back Memo) must be present, and PEP compliance must be confirmed.
    Gated by can_submit_to_dcc.
    """
    import datetime as _dt
    lam = _lam()
    app = lam.get(app_id)
    if not app:
        raise HTTPException(status_code=404, detail=f"Application '{app_id}' not found")

    perms = resolve_application_permissions(user, app)
    if not perms.get("can_submit_to_dcc"):
        raise HTTPException(status_code=403, detail="Not permitted to submit this case to the DCC.")

    payload = payload if isinstance(payload, dict) else {}
    opinion = str(payload.get("opinion", "") or "").strip()
    pep_confirmed = bool(payload.get("pep_confirmed", False))

    # ── Completeness gate ──
    from utils.api_lms_mutations import get_credit_workflow_config
    da = (get_credit_workflow_config() or {}).get("department_analyst") or {}
    required_atts = [str(x).strip() for x in (da.get("required_attachments") or []) if str(x).strip()]
    atts = list(lam.list_attachments(app_id) or [])
    # The Department Analyst attaches the Call-Back Memo as a CASE DOCUMENT
    # (document_files) so it travels + is readable; count those toward the gate.
    for _k, _v in (app.get("document_files", {}) or {}).items():
        atts.append({"filename": f"{_k} {(_v or {}).get('filename', '')}", "kind": "document"})

    def _att_present(name: str) -> bool:
        toks = [t for t in name.lower().replace("-", " ").replace("_", " ").split() if t]
        for a in atts:
            hay = f"{a.get('filename', '')} {a.get('kind', '')} {a.get('label', '')}".lower().replace("-", " ").replace("_", " ")
            if toks and all(t in hay for t in toks):
                return True
        return False

    missing = [n for n in required_atts if not _att_present(n)]
    if missing:
        raise HTTPException(status_code=400,
                            detail=f"Missing required attachment(s): {', '.join(missing)}")
    pep_required = bool((da.get("compliance_confirmation") or {}).get("pep_check"))
    if pep_required and not pep_confirmed:
        raise HTTPException(status_code=400,
                            detail="Confirm PEP compliance (client is not a PEP / has no issues) before submitting.")

    # ── Record the Department Analyst's review, then refer to committee (DCC) ──
    if not is_valid_lms_transition(str(app.get("status", "")), "referred_to_committee"):
        raise HTTPException(status_code=400,
                            detail=f"Cannot submit to committee from status '{app.get('status')}'")
    review = {
        "opinion": opinion,
        "pep_confirmed": pep_confirmed,
        "by": str(user.get("staff_code", "") or ""),
        "by_name": str(user.get("full_name", "") or ""),
        "at": _dt.datetime.now().isoformat(timespec="seconds"),
    }
    try:
        # Mark the case as before the DEPARTMENT Credit Committee (distinct from
        # an authority-tier committee). P4b/c key off committee_kind to validate
        # votes against the DCC roster and route the resolution back to the
        # Department Analyst instead of auto-issuing the offer.
        lam.update(app_id, {"dept_analyst_review": review, "committee_kind": "dcc"})
    except Exception:
        pass
    lam.refer_to_committee(app_id, by=str(user.get("username", "") or ""), note=opinion)
    audit_log("LMS_SUBMITTED_TO_DCC", str(user.get("username", "") or ""), app_id)
    return {"application": lam.get(app_id), "status": "referred_to_committee"}


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
        by=str(user.get('staff_code', '') or user.get('username', '') or ''),
        by_name=str(user.get('full_name', '') or ''),
        by_role=str(user.get('role', '') or ''),
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

    # ── A DECISION MOVES THE CASE ───────────────────────────────────────────
    # RULING (2026-08-15). Until now a decision recorded a verdict and the case
    # sat where it was, waiting for somebody to find a separate button. That is
    # the same fault the committee had, one gate further on: the state changed
    # and the case did not move.
    #
    # APPROVED goes to credit admin, carrying its conditions so they can be
    # ticked there. Nobody re-submits what has just been approved.
    #
    # DECLINED GOES BACK TO THE OWNER, NOT TO CLOSED LOST. The ruling is
    # explicit: "it should probably go back to the owner who is to click on
    # appeal or accept the decision - if they accept it closes as lost."
    #
    # So a decline is not the end of the case; it is a question put to the
    # person who raised it. Closing it here would take that choice away, and
    # an appeal would then have to reopen a closed deal.
    # `datetime`, NOT `_dt`. _dt is imported locally inside two other
    # functions here and means different things in each - the module in one,
    # the class in the other. This function has neither, so datetime.now() raised a
    # NameError that my own except swallowed: the decision recorded, the case
    # did not move, and nothing said why. Exactly the shape of the two-year
    # NameError this codebase already carried once.
    try:
        if verdict_normalized == "approved":
            # PRE-APPROVAL falls back to the plain `conditions` list, because
            # that is what every decision recorded before today used it for.
            # Reading only the new field would make historic approvals look
            # unconditional.
            _pre = list(getattr(payload, "pre_approval_conditions", None)
                        or getattr(payload, "conditions", None) or [])
            _dis = list(getattr(payload, "pre_disbursement_conditions", None) or [])
            lam.update(app_id, {
                "status": "credit_admin",
                "awaiting_credit_admin": True,
                "approved_at": datetime.now().isoformat(timespec="seconds"),
                "approved_by_name": str(user.get("full_name", "") or ""),
                "decision_conditions": _pre,
                # Each condition is an object, not a string, so a tick can be
                # recorded against it with who and when. A bare string has
                # nowhere to put that.
                "pre_approval_conditions": [
                    {"text": c, "met": False, "kind": "pre_approval"}
                    for c in _pre],
                "pre_disbursement_conditions": [
                    {"text": c, "met": False, "kind": "pre_disbursement"}
                    for c in _dis],
            })
            _conds = _pre + _dis
            audit_log("LMS_APPROVED_TO_CREDIT_ADMIN",
                      str(user.get("username", "") or ""),
                      "%s|%d condition(s)" % (app_id, len(_conds)))
        elif verdict_normalized == "declined":
            lam.update(app_id, {
                "status": "declined",
                "awaiting_owner_response": True,
                "declined_at": datetime.now().isoformat(timespec="seconds"),
                "declined_by_name": str(user.get("full_name", "") or ""),
                "decline_reason": str(getattr(payload, "reason", "") or ""),
                # The owner chooses: appeal, or accept and close as lost.
                "appeal_window_open": True,
            })
            audit_log("LMS_DECLINED_TO_OWNER",
                      str(user.get("username", "") or ""), app_id)
    except Exception as _exc:
        # THIS MODULE HAS NO LOGGER. Calling one inside an except would raise a
        # NameError from the handler and lose the decision entirely - which is
        # exactly how a silent `except: pass` hid a NameError here for two
        # years. The audit trail is what this module has, so use it.
        try:
            audit_log("LMS_DECISION_MOVE_FAILED",
                      str(user.get("username", "") or ""),
                      "%s|%s: %s" % (app_id, type(_exc).__name__, str(_exc)[:80]))
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


@router.get("/applications/{app_id}/documents")
def lms_application_documents_list(
    app_id: str,
    user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """List the documents that travelled with the case from the pipeline deal.
    Visible to anyone who can view the application (analyst, DCC/BCC, Chief
    Credit). The credit side has no deal scope, so these are the app's carried
    files, not the deal document routes."""
    lam = _lam()
    app = lam.get(app_id)
    if not app:
        raise HTTPException(status_code=404, detail=f"Application '{app_id}' not found")
    if not resolve_application_permissions(user, app).get("can_view"):
        raise HTTPException(status_code=403, detail="Application is out of scope")
    # ── WHAT THE CASE NEEDS, not only what it has ───────────────────────────
    # RULING (2026-08-18): "this should have the documents listed for view -
    # even if not there, let us have a listing of the required documents."
    #
    # An empty card saying "nothing on file" tells a reviewer the case is bare.
    # A list of what it NEEDS tells them what is MISSING, which is the thing
    # they can act on.
    #
    # It comes from the same tiered checklist the submission gate enforces -
    # default, plus amount and product tiers - so the screen and the gate
    # cannot disagree about what is required.
    _required = []
    try:
        _cfg = get_credit_workflow_config() or {}
        _dc = _cfg.get("document_checklist") or {}
        if not _dc:
            import json as _json
            _dc = (_json.load(open("data/lms_config.json", encoding="utf-8"))
                   .get("document_checklist") or {})
        _required = list(_dc.get("default") or [])
        _amt = float(app.get("amount") or 0)
        if _amt >= 10_000_000:
            _required += list(_dc.get("above_10m") or [])
        _ct = str(app.get("client_type", "") or "").lower()
        if "cib" in _ct or "corporate" in _ct or "commercial" in _ct:
            _required += list(_dc.get("corporate") or [])
        _prod = str(app.get("product", "") or "").lower()
        if "mortgage" in _prod:
            _required += list(_dc.get("mortgage") or [])
        # Same name twice helps nobody.
        _seen, _out = set(), []
        for r in _required:
            k = str(r).strip().lower()
            if k and k not in _seen:
                _seen.add(k)
                _out.append(str(r).strip())
        _required = _out
    except Exception:
        _required = []

    return {"required": _required,
            "files": app.get("document_files", {}) or {},
            "provided": list(app.get("documents_provided", []) or []),
            # What has been asked for and not yet supplied, so one call answers
            # "what is on file and what is still owed".
            "requested": list(app.get("documents_requested", []) or [])}


class _AnalystDocUpload(BaseModel):
    doc_name: str
    filename: str = ""
    content_b64: str


class _DocRequest(BaseModel):
    doc_name: str
    note: str = ""


@router.post("/applications/{app_id}/documents/request", status_code=201)
def lms_application_document_request(
    app_id: str,
    body: _DocRequest,
    user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """The analyst asks for a document that is not on the case.

    RULING (2026-08-12): "we can add another feature to click on request
    document and she can also request for additional documentation - this is to
    happen across all the analysts."

    WHY A REQUEST RATHER THAN JUST ADDING IT TO THE REQUIRED LIST. The required
    list is per PRODUCT and set by an admin; it describes what every case of
    this kind needs. What one analyst wants on one case is a different thing,
    and writing it into the product config would quietly change the rules for
    every future deal.

    So a request is recorded ON THE CASE, with who asked and why. It appears as
    outstanding, and it is satisfied by the same upload route as anything else.
    """
    from datetime import datetime as _dt

    lam = _lam()
    app = lam.get(app_id)
    if not app:
        raise HTTPException(status_code=404, detail=f"Application '{app_id}' not found")
    perms = resolve_application_permissions(user, app)
    if not (perms.get("can_update") or perms.get("can_submit_to_dcc")
            or perms.get("can_decide") or perms.get("can_hand_to_credit_analyst")):
        raise HTTPException(status_code=403,
                            detail="Only somebody working this case can request documents.")

    name = str(body.doc_name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="doc_name is required")

    reqs = list(app.get("documents_requested", []) or [])
    if not any(str(r.get("name")) == name for r in reqs if isinstance(r, dict)):
        reqs.append({
            "name": name,
            "note": str(body.note or "").strip(),
            "requested_by": str(user.get("full_name") or user.get("username") or ""),
            "requested_role": str(user.get("role", "") or ""),
            "requested_at": _dt.now().isoformat(timespec="seconds"),
        })
        lam.update(app_id, {"documents_requested": reqs})
    audit_log("LMS_DOC_REQUESTED", str(user.get("username", "") or ""),
              detail=f"{app_id}: {name}")
    return {"ok": True, "documents_requested": reqs}


@router.post("/applications/{app_id}/documents", status_code=201)
def lms_application_document_upload(
    app_id: str,
    body: _AnalystDocUpload,
    user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """The analyst attaches a document to the case.

    RULING (2026-08-12): "Catherine is to also be able to attach a few
    documents, then submit to Department Credit Committee once she recommends."

    STORED ON THE APPLICATION, not the deal. The credit side has no deal scope
    by design - that is why the read route above serves the app's carried files
    rather than the deal document routes. Writing to the deal would need a
    scope the analyst deliberately does not have.

    WHO MAY ATTACH: anyone who can act on the case - the assigned analyst, and
    credit roles working it. Not merely anyone who can VIEW it: a committee
    member reading a case should not be able to add papers to it.
    """
    import base64 as _b64
    import hashlib as _hash
    from datetime import datetime as _dt
    from pathlib import Path as _Path

    lam = _lam()
    app = lam.get(app_id)
    if not app:
        raise HTTPException(status_code=404, detail=f"Application '{app_id}' not found")
    perms = resolve_application_permissions(user, app)
    if not (perms.get("can_edit") or perms.get("can_submit_to_dcc")
            or perms.get("can_decide") or perms.get("is_assigned_analyst")):
        raise HTTPException(
            status_code=403,
            detail="Only somebody working this case can attach documents to it.")

    doc_name = str(body.doc_name or "").strip()
    if not doc_name:
        raise HTTPException(status_code=400, detail="doc_name is required")
    try:
        raw = _b64.b64decode(body.content_b64)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"content_b64 invalid: {exc}")
    if not raw:
        raise HTTPException(status_code=400, detail="empty file")
    if len(raw) > 20 * 1024 * 1024:
        raise HTTPException(status_code=400,
                            detail=f"file too large ({len(raw)} bytes; max 20MB)")

    safe = "".join(c for c in (body.filename or doc_name)
                   if c.isalnum() or c in " ._-").strip() or "attachment"
    safe_app = "".join(c for c in app_id if c.isalnum() or c in "._-")
    safe_doc = "".join(c for c in doc_name if c.isalnum() or c in " ._-").strip()
    ddir = _Path("data") / "lms_documents" / safe_app
    ddir.mkdir(parents=True, exist_ok=True)
    stored = ddir / f"{safe_doc}__{safe}"
    stored.write_bytes(raw)

    files = dict(app.get("document_files", {}) or {})
    files[doc_name] = {
        "filename": safe,
        "path": str(stored),
        "sha256": _hash.sha256(raw).hexdigest(),
        "size": len(raw),
        "uploaded_by": str(user.get("username", "") or ""),
        "uploaded_by_name": str(user.get("full_name", "") or ""),
        # WHO attached it, in the record itself. An analyst's paper and the
        # owner's look identical once filed, and six weeks later somebody will
        # need to know which is which.
        "uploaded_role": str(user.get("role", "") or ""),
        "uploaded_at": _dt.now().isoformat(timespec="seconds"),
    }
    provided = list(app.get("documents_provided", []) or [])
    if doc_name not in provided:
        provided.append(doc_name)
    lam.update(app_id, {"document_files": files, "documents_provided": provided})

    audit_log("LMS_DOC_ATTACHED", str(user.get("username", "") or ""),
              detail=f"{app_id}: {doc_name}")
    return {"ok": True, "doc_name": doc_name, "filename": safe,
            "documents_provided": provided}


@router.get("/applications/{app_id}/documents/{doc_name:path}")
def lms_application_document_download(
    app_id: str,
    doc_name: str,
    user: Dict[str, Any] = Depends(get_current_user),
):
    """Stream one travelled document back, gated by LMS view permission."""
    from pathlib import Path as _P
    from fastapi.responses import StreamingResponse
    import io as _io
    lam = _lam()
    app = lam.get(app_id)
    if not app:
        raise HTTPException(status_code=404, detail=f"Application '{app_id}' not found")
    if not resolve_application_permissions(user, app).get("can_view"):
        raise HTTPException(status_code=403, detail="Application is out of scope")
    meta = (app.get("document_files", {}) or {}).get(doc_name)
    if not meta:
        raise HTTPException(status_code=404, detail=f"Document '{doc_name}' not found")
    root = _P(__file__).resolve().parent.parent
    fpath = root / str(meta.get("path", ""))
    if not fpath.exists():
        raise HTTPException(status_code=404, detail="Stored file missing")
    data = fpath.read_bytes()
    return StreamingResponse(
        _io.BytesIO(data), media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{meta.get("filename", "file")}"'})


def _dcc_for_app(app: dict) -> dict:
    """The department committee THIS case belongs to.

    credit_workflow.dcc is ONE COPY of ONE committee - whichever was last
    enabled. Three endpoints read it: the roster the panel renders, the vote,
    and the resolution. So a Commercial case would show CONSUMER's voters, be
    judged against Consumer's quorum, and require Consumer's chair - while the
    people actually entitled to decide it appeared nowhere.

    The palette already knows which committee a case belongs to. Resolve from
    the CASE, and fall back to the single copy only when nothing matches - so a
    bank with one department committee behaves exactly as before.
    """
    cfg = get_credit_workflow_config() or {}
    dcc = dict(cfg.get("dcc") or {})

    # A case referred to the BUSINESS CREDIT COMMITTEE resolves to it,
    # whatever the client type - it is a tier above the segment committees, not
    # one of them.
    if str((app or {}).get("committee_kind", "") or "").lower() == "mcc":
        for c in (cfg.get("committee_palette") or []):
            nm = str(c.get("name", "") or "").lower()
            if "management" in nm or "business credit" in nm or str(c.get("code")) == "B4":
                mem = [m for m in (c.get("members") or [])
                       if isinstance(m, dict)
                       and (str(m.get("staff_code", "")).strip()
                            or str(m.get("name", "")).strip())]
                if mem:
                    return {
                        "enabled": True,
                        "name": c.get("name") or "Business Credit Committee",
                        "members": mem,
                        "chaired_by": c.get("chaired_by", ""),
                        "chair_staff_code": c.get("chair_staff_code", ""),
                        "voting_rule": c.get("voting_rule", "SIMPLE_MAJORITY"),
                        "min_quorum_count": c.get("min_quorum_count"),
                        "source_committee": c.get("code"),
                    }

    seg = str((app or {}).get("client_type", "") or "").strip().lower()
    want = ""
    if "commercial" in seg:
        want = "commercial"
    elif seg == "cib" or "corporate" in seg or "investment" in seg:
        want = "corporate"
    elif ("consumer" in seg or "individual" in seg
          or seg in ("personal", "retail")):
        want = "consumer"
    if not want:
        return dcc

    for c in (cfg.get("committee_palette") or []):
        if str(c.get("kind", "")).lower() == "branch":
            continue
        if want not in str(c.get("name", "") or "").lower():
            continue
        members = [m for m in (c.get("members") or [])
                   if isinstance(m, dict)
                   and (str(m.get("staff_code", "")).strip()
                        or str(m.get("name", "")).strip())]
        if not members:
            # Named but unstaffed: keep the fallback rather than hand back a
            # committee nobody sits on.
            break
        return {
            "enabled": bool(dcc.get("enabled")),
            "name": c.get("name") or dcc.get("name"),
            "members": members,
            "chaired_by": c.get("chaired_by", ""),
            "chair_staff_code": c.get("chair_staff_code", ""),
            "voting_rule": c.get("voting_rule",
                                 dcc.get("voting_rule", "SIMPLE_MAJORITY")),
            "min_quorum_count": c.get("min_quorum_count"),
            "source_committee": c.get("code"),
        }
    return dcc


@router.get("/applications/{app_id}/dcc/roster")
def lms_dcc_roster(
    app_id: str,
    user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """The Department Credit Committee roster + recorded votes for a case.
    Self-contained (distinct from the authority-tier charter). Visible to anyone
    who can view the application."""
    lam = _lam()
    app = lam.get(app_id)
    if not app:
        raise HTTPException(status_code=404, detail=f"Application '{app_id}' not found")
    if not resolve_application_permissions(user, app).get("can_view"):
        raise HTTPException(status_code=403, detail="Application is out of scope")
    from utils.api_lms_mutations import get_credit_workflow_config
    dcc = _dcc_for_app(app)
    return {
        "enabled": bool(dcc.get("enabled")),
        "name": str(dcc.get("name", "Department Credit Committee")),
        "is_dcc_case": str(app.get("committee_kind", "")) == "dcc",
        "members": list(dcc.get("members") or []),
        "votes": list(app.get("dcc_votes", []) or []),
        "outcome": app.get("dcc_outcome"),
    }


@router.post("/applications/{app_id}/dcc/vote")
def lms_dcc_vote(
    app_id: str,
    payload: Dict[str, Any],
    user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """Record one DCC member's vote (YES/NO/ABSTAIN), validated against the DCC
    roster (not the authority-tier charter). Gated: DCC enabled + case before the
    DCC. One vote per member (re-voting replaces)."""
    import datetime as _dt
    lam = _lam()
    app = lam.get(app_id)
    if not app:
        raise HTTPException(status_code=404, detail=f"Application '{app_id}' not found")
    if not resolve_application_permissions(user, app).get("can_view"):
        raise HTTPException(status_code=403, detail="Application is out of scope")
    from utils.api_lms_mutations import get_credit_workflow_config
    dcc = _dcc_for_app(app)
    if not dcc.get("enabled"):
        raise HTTPException(status_code=400, detail="The Department Credit Committee is not enabled.")
    # The BUSINESS CREDIT COMMITTEE sits on the same machinery - it votes,
    # reaches quorum and records an outcome exactly as a department committee
    # does. What differs is only where its answer goes, handled below.
    if str(app.get("committee_kind", "")) not in ("dcc", "mcc"):
        raise HTTPException(status_code=400, detail="This case is not before a credit committee.")
    payload = payload if isinstance(payload, dict) else {}
    member_id = str(payload.get("member_id", "") or "").strip()
    vote = str(payload.get("vote", "") or "").strip().upper()
    roster_ids = {str(m.get("id") or m.get("member_id") or "").strip()
                  for m in (dcc.get("members") or []) if isinstance(m, dict)}
    if not member_id or member_id not in roster_ids:
        raise HTTPException(status_code=400, detail=f"'{member_id}' is not a committee member")
    # ── A VOTE IS PERSONAL ──────────────────────────────────────────────────
    # FOUND 2026-08-18, rehearsing the Business Credit Committee before the MD
    # sat on it. member_id arrived from the PAYLOAD and was checked only
    # against the roster - so any member could cast a vote in another member's
    # name, INCLUDING THE CHAIR'S. On a committee whose chair's vote is
    # mandatory, that is not a small thing: one member could complete a
    # decision alone.
    #
    # The audit log recorded who really sent it, so it was traceable after the
    # fact. That is not the same as preventable.
    #
    # The member voting must BE the person signed in. Matched by staff code,
    # then by name, which is how membership is matched everywhere else.
    _me = str(user.get("staff_code", "") or "").strip()
    _myname = str(user.get("full_name", "") or "").strip().lower()
    _mine = False
    for _m in (dcc.get("members") or []):
        if not isinstance(_m, dict):
            continue
        _mid = str(_m.get("id") or _m.get("member_id") or "").strip()
        if _mid != member_id:
            continue
        _mcode = str(_m.get("staff_code", "") or "").strip()
        _mname = str(_m.get("name", "") or "").strip().lower()
        _mine = bool((_me and (_mid == _me or _mcode == _me))
                     or (_myname and _mname == _myname))
        break
    if not _mine and not user.get("is_admin"):
        raise HTTPException(
            status_code=403,
            detail="You can only cast your own vote. This seat belongs to "
                   "somebody else on the committee.")
    if vote not in ("YES", "NO", "ABSTAIN"):
        raise HTTPException(status_code=400, detail="vote must be YES, NO, or ABSTAIN")
    # ── ONE VOTE PER MEMBER, AND IT STANDS ──────────────────────────────────
    # FOUND 2026-08-18, rehearsing before the MD sat on this committee. The
    # line below REMOVES the member's previous vote and the next re-adds it -
    # so a second vote silently replaced the first, with no record that a
    # member had changed their mind and no refusal.
    #
    # The branch committee has required one vote per member since VF1. The
    # department and business committees never did, and nobody noticed because
    # the panel hides the button after voting - so only somebody calling the
    # endpoint directly would find it. Which is what a rehearsal does.
    #
    # A vote quietly overwritten is worse than one refused: the record then
    # says the committee agreed, when a member may have been persuaded - or
    # pressed - to vote again.
    if (any(str(v.get("member_id")) == str(member_id)
            for v in (app.get("dcc_votes", []) or []))
            and not user.get("is_admin")):
        raise HTTPException(
            status_code=409,
            detail="You have already voted on this case. A vote stands once "
                   "cast - ask an administrator if it must be changed.")
    votes = [v for v in (app.get("dcc_votes", []) or []) if v.get("member_id") != member_id]
    votes.append({
        "member_id": member_id, "vote": vote,
        "rationale": str(payload.get("rationale", "") or ""),
        "by": str(user.get("staff_code", "") or ""),
        "at": _dt.datetime.now().isoformat(timespec="seconds"),
    })
    lam.update(app_id, {"dcc_votes": votes})
    audit_log("LMS_DCC_VOTE", str(user.get("username", "") or ""), f"{app_id}|{member_id}:{vote}")
    return {"dcc_votes": votes}


@router.post("/applications/{app_id}/dcc/resolve")
def lms_dcc_resolve(
    app_id: str,
    payload: Dict[str, Any] = None,
    user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """Close the DCC: tally the votes into an ADVISORY recommendation, record it,
    and route the case BACK to the Department Analyst (status -> assigned) so they
    can hand it to the Credit Analyst. The DCC does NOT approve/decline the loan —
    the Credit Analyst is the decision-maker. Gated: a manager or the assigned
    analyst, DCC enabled, case before the DCC."""
    import datetime as _dt
    lam = _lam()
    app = lam.get(app_id)
    if not app:
        raise HTTPException(status_code=404, detail=f"Application '{app_id}' not found")
    caller = str(user.get("staff_code", "") or "")
    analyst_code = str((app.get("analyst") or {}).get("code", "") or "")

    from utils.api_lms_mutations import get_credit_workflow_config
    dcc = _dcc_for_app(app)
    # ── A COMMITTEE CAN CLOSE ITS OWN SITTING ───────────────────────────────
    # FOUND 2026-08-18, rehearsing the Business Credit Committee. Closing was
    # restricted to a manager or the ASSIGNED ANALYST. That is right for a
    # department committee, which an analyst convenes about their own case.
    #
    # It is wrong for the business committee. That one is chaired by the
    # Managing Director and has NO assigned analyst - the case was referred to
    # it. Under the old rule the MD could sit, hear the case and vote, and then
    # not be allowed to record what the committee had decided.
    #
    # A member of the committee that just sat may close it. Nobody else.
    _closer = str(user.get("staff_code", "") or "").strip()
    _closer_name = str(user.get("full_name", "") or "").strip().lower()
    _on_committee = any(
        (_closer and (str(m.get("staff_code", "")).strip() == _closer
                      or str(m.get("id") or m.get("member_id") or "").strip() == _closer))
        or (_closer_name and str(m.get("name", "")).strip().lower() == _closer_name)
        for m in (dcc.get("members") or []) if isinstance(m, dict))
    if not (_on_committee or is_manager(user)
            or (caller and caller == analyst_code)):
        raise HTTPException(
            status_code=403,
            detail="Only a member of this committee, its analyst, or a "
                   "manager can record its decision.")
    if not dcc.get("enabled"):
        raise HTTPException(status_code=400, detail="The Department Credit Committee is not enabled.")
    # The BUSINESS CREDIT COMMITTEE sits on the same machinery - it votes,
    # reaches quorum and records an outcome exactly as a department committee
    # does. What differs is only where its answer goes, handled below.
    if str(app.get("committee_kind", "")) not in ("dcc", "mcc"):
        raise HTTPException(status_code=400, detail="This case is not before a credit committee.")
    votes = app.get("dcc_votes", []) or []
    yes = sum(1 for v in votes if str(v.get("vote", "")).upper() == "YES")
    no = sum(1 for v in votes if str(v.get("vote", "")).upper() == "NO")
    abstain = sum(1 for v in votes if str(v.get("vote", "")).upper() == "ABSTAIN")
    recommendation = "support" if yes > no else "oppose" if no > yes else "split"
    outcome = {
        "recommendation": recommendation,
        "tally": {"yes": yes, "no": no, "abstain": abstain},
        "by": caller, "by_name": str(user.get("full_name", "") or ""),
        "at": _dt.datetime.now().isoformat(timespec="seconds"),
        "note": str((payload or {}).get("note", "") or "") if isinstance(payload, dict) else "",
    }
    if not is_valid_lms_transition(str(app.get("status", "")), "assigned"):
        raise HTTPException(status_code=400,
                            detail=f"Cannot return to the analyst from '{app.get('status')}'")
    # Return to the Department Analyst (status -> assigned); clear committee_kind
    # so the case is no longer 'before the DCC'. dcc_outcome carries the advice.
    # ── AN APPROVAL GOES ON; ANYTHING ELSE COMES BACK ───────────────────────
    # RULING (2026-08-14): "since it also has the simple majority, once the
    # vote reaches that it should now autosubmit to the bank credit analysis
    # pool."
    #
    # Every outcome used to return the case to the department analyst. That is
    # right for a rejection or a deferral - somebody must act on it - and wrong
    # for an approval, which is finished business at this level: the committee
    # has recommended it, and making the analyst re-submit what a committee has
    # just approved is the delay the auto-advance rulings were about.
    #
    # AN APPROVED CASE IS RELEASED TO THE CREDIT POOL: status back to
    # submitted, the analyst cleared, awaiting_credit_analyst set - which is
    # exactly what hand-to-credit-analyst does, so a bank credit analyst
    # self-picks it in the ordinary way rather than through a special path.
    # outcome is a DICT - recommendation, tally, who and when - so the verdict
    # is outcome["recommendation"], not the dict stringified. Reading it wrongly
    # made every case take the "not approved" branch and go back to the
    # analyst, which is the behaviour this was meant to change.
    # THE COMMITTEE'S OWN WORDS. recommendation is derived from the votes -
    # "support" when yes beats no, "oppose" when no beats yes, "split" when
    # they tie - not from anything the caller sends. Matching on "approved"
    # here found nothing, so every case took the not-approved branch: the fix
    # looked applied and changed nothing.
    #
    # SPLIT IS NOT SUPPORT. A tied committee has not recommended anything, so
    # the case goes back to the analyst like a rejection.
    _verdict = str((outcome or {}).get("recommendation", "")).lower()
    _approved = _verdict == "support"
    if _approved:
        _next = {
            "dcc_outcome": outcome,
            "committee_kind": "",
            "status": "submitted",
            "analyst": None,
            "awaiting_credit_analyst": True,
            "dcc_cleared_at": _dt.datetime.now().isoformat(timespec="seconds"),
        }
    else:
        _next = {"dcc_outcome": outcome, "status": "assigned", "committee_kind": ""}
    # ── THE BUSINESS CREDIT COMMITTEE ANSWERS TO CREDIT RISK ────────────────
    # RULING (2026-08-18): "when they refer to the Management Credit Committee,
    # internally also called the Business Credit Committee ... once they
    # convene they also give their recommendation, and once the recommendation
    # is made it should still go back to the credit risk pool for progression
    # to credit admin. The approval for BCC-approved cases should be ticked as
    # approved by BCC and then progress to credit admin, but the conditions are
    # still to be ticked by the analyst."
    #
    # A DEPARTMENT committee recommending a case releases it to the credit
    # pool, where a bank analyst picks it up fresh. THE BCC IS DIFFERENT: it
    # was asked a question BY credit risk, or circulated a packaged case, and
    # its answer belongs back with whoever asked - not with the pool at large.
    #
    # AND IT DOES NOT SET CONDITIONS. The committee says yes; the analyst
    # writes the conditions and sends the case to credit admin. Keeping those
    # two acts separate is what keeps one person accountable for the terms.
    if str(app.get("committee_kind", "") or "").lower() == "mcc":
        _bcc = {
            "bcc_outcome": recommendation,
            "bcc_recommendation": recommendation,
            "bcc_resolved_at": datetime.now().isoformat(timespec="seconds"),
            "bcc_resolved_by": str(user.get("full_name", "") or ""),
            "bcc_tally": {"yes": yes, "no": no, "abstain": abstain},
            "escalated_pending": False,
            "committee_kind": "",
        }
        if recommendation == "support":
            # Back to credit risk, marked as carrying the committee's approval.
            _bcc.update({
                "status": "submitted",
                "awaiting_credit_analyst": True,
                "approved_by_bcc": True,
            })
        else:
            # Opposed or split: still back to credit risk, but without it. They
            # asked the question; they get the answer either way.
            _bcc.update({
                "status": "submitted",
                "awaiting_credit_analyst": True,
                "approved_by_bcc": False,
            })
        lam.update(app_id, _bcc)
        audit_log("LMS_BCC_RESOLVED", str(user.get("username", "") or ""),
                  f"{app_id}|{recommendation}|{yes}-{no}-{abstain}")
        return {"application": lam.get(app_id),
                "dcc_outcome": outcome, "bcc": True}

    lam.update(app_id, _next)
    audit_log("LMS_DCC_RESOLVED", str(user.get("username", "") or ""),
              f"{app_id}|{recommendation}|{yes}-{no}-{abstain}")
    return {"application": lam.get(app_id), "dcc_outcome": outcome}


@router.post("/applications/{app_id}/return-for-rework")
def lms_return_for_rework(
    app_id: str,
    payload: dict = Body(default_factory=dict),
    user: dict = Depends(get_current_user),
):
    """Send a case back to its owner with what needs doing.

    RULING (2026-08-14): "if it is returned for reworks, a window to detail the
    nature of reworks comes up and once filled they press return. A returned
    case reopens back to the branch on the owner, and once they complete the
    reworks they resubmit - this time back to the credit analyst to continue."

    THE REASON IS MANDATORY. A case returned without one sends somebody back to
    a branch to guess what was wrong, and they will guess wrong. The endpoint
    refuses an empty reason rather than accepting a blank field that costs a
    day at the other end.

    IT REMEMBERS WHO RETURNED IT. When the owner resubmits, the case goes back
    to that analyst rather than into the pool to be picked up by somebody with
    no memory of the conversation - which is the difference between a rework
    and starting again.
    """
    lam = _lam()
    app = lam.get(app_id)
    if not app:
        raise HTTPException(status_code=404, detail=f"Application '{app_id}' not found")

    reason = str(payload.get("reason", "") or "").strip()
    if not reason:
        raise HTTPException(
            status_code=400,
            detail=("Say what needs reworking. A case returned without a reason "
                    "sends somebody back to the branch to guess."))

    me = str(user.get("staff_code", "") or "").strip()
    myname = str(user.get("full_name", "") or "").strip()
    history = list(app.get("rework_history") or [])
    history.append({
        "reason": reason,
        "items": [str(x) for x in (payload.get("items") or []) if str(x).strip()],
        "by": me, "by_name": myname,
        "at": datetime.now().isoformat(timespec="seconds"),
    })

    lam.update(app_id, {
        "status": "returned",
        "rework_history": history,
        "rework_reasons": reason,
        # WHO TO COME BACK TO. Cleared when the owner resubmits.
        "returned_by_code": me,
        "returned_by_name": myname,
        "returned_at": datetime.now().isoformat(timespec="seconds"),
    })
    audit_log("LMS_RETURNED_FOR_REWORK", str(user.get("username", "") or ""),
              "%s|%s" % (app_id, reason[:80]))
    return {"application": lam.get(app_id), "status": "returned",
            "returned_to_owner": True}


@router.post("/applications/{app_id}/resubmit-after-rework")
def lms_resubmit_after_rework(
    app_id: str,
    payload: dict = Body(default_factory=dict),
    user: dict = Depends(get_current_user),
):
    """The owner has done the rework; the case goes BACK to the same analyst.

    Not into the pool. The analyst who returned it has the context, and making
    the case queue again behind everything else is how a two-hour correction
    becomes a two-day one.

    If that analyst cannot be identified the case falls back to the pool rather
    than being stranded - a case with nowhere to go is worse than one in the
    wrong queue.
    """
    lam = _lam()
    app = lam.get(app_id)
    if not app:
        raise HTTPException(status_code=404, detail=f"Application '{app_id}' not found")
    if str(app.get("status", "")) != "returned":
        raise HTTPException(
            status_code=400,
            detail="This case is not out for rework (status is %r)." % app.get("status"))

    back_to = str(app.get("returned_by_code", "") or "").strip()
    back_name = str(app.get("returned_by_name", "") or "").strip()
    note = str(payload.get("note", "") or "").strip()

    updates = {
        "status": "assigned" if back_to else "submitted",
        "rework_completed_at": datetime.now().isoformat(timespec="seconds"),
        "rework_completed_by": str(user.get("full_name", "") or ""),
        "rework_note": note,
        "returned_by_code": "",
        "returned_by_name": "",
    }
    if back_to:
        updates["analyst"] = {"code": back_to, "name": back_name, "role": ""}
    lam.update(app_id, updates)
    audit_log("LMS_REWORK_RESUBMITTED", str(user.get("username", "") or ""),
              "%s|back to %s" % (app_id, back_to or "the pool"))
    return {"application": lam.get(app_id),
            "status": updates["status"],
            "back_to": back_name or "the pool"}


# The tick endpoint that stood here is gone. utils/api_credit_admin_routes.py
# already carries `conditions/fulfill` alongside the disbursement gate,
# collateral, insurance and legal - credit admin ticks there. Two ways to tick
# one condition is worse than either: the gate watches one of them, so a case
# ticked in the wrong place looks satisfied and never moves.
#
# The two KINDS on the decision remain - see the approved branch above.


@router.post("/applications/{app_id}/hand-to-credit-analyst")
def lms_hand_to_credit_analyst(
    app_id: str,
    payload: Dict[str, Any] = None,
    user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """Department Analyst hands the case to the conventional Credit Analyst: the
    case is released to the credit pool (status -> submitted, analyst cleared,
    awaiting_credit_analyst set) so a Credit Analyst self-picks it and makes the
    final decision (which triggers the offer). Gated by can_hand_to_credit_analyst."""
    lam = _lam()
    app = lam.get(app_id)
    if not app:
        raise HTTPException(status_code=404, detail=f"Application '{app_id}' not found")
    if not resolve_application_permissions(user, app).get("can_hand_to_credit_analyst"):
        raise HTTPException(status_code=403,
                            detail="Not permitted to hand this case to the Credit Analyst.")
    if not is_valid_lms_transition(str(app.get("status", "")), "submitted"):
        raise HTTPException(status_code=400, detail=f"Cannot release from '{app.get('status')}'")
    lam.update(app_id, {
        "status": "submitted",
        "analyst": None,
        "awaiting_credit_analyst": True,
    })
    audit_log("LMS_HANDED_TO_CREDIT_ANALYST", str(user.get("username", "") or ""), app_id)
    return {"application": lam.get(app_id), "status": "submitted"}


@router.post("/applications/{app_id}/callback-memo")
def lms_callback_memo_upload(
    app_id: str,
    payload: Dict[str, Any],
    user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """The Department Analyst attaches the Call-Back Memo (their checker
    confirmation). Stored as a CASE DOCUMENT so it travels + is readable in the
    viewer, and satisfies the submit-to-DCC completeness gate. Gated: the
    assigned analyst on the case."""
    from pathlib import Path as _P
    import base64 as _b64, datetime as _dt, re as _re
    lam = _lam()
    app = lam.get(app_id)
    if not app:
        raise HTTPException(status_code=404, detail=f"Application '{app_id}' not found")
    caller = str(user.get("staff_code", "") or "")
    analyst_code = str((app.get("analyst") or {}).get("code", "") or "")
    if not (caller and caller == analyst_code):
        raise HTTPException(status_code=403,
                            detail="Only the assigned analyst can attach the Call-Back Memo.")
    payload = payload if isinstance(payload, dict) else {}
    filename = str(payload.get("filename", "") or "").strip() or "call_back_memo.pdf"
    try:
        raw = _b64.b64decode(str(payload.get("content_b64", "") or ""))
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid file content.")
    if not raw:
        raise HTTPException(status_code=400, detail="Empty file.")
    if len(raw) > 30 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File too large (max 30 MB).")
    root = _P(__file__).resolve().parent.parent
    safe = (_re.sub(r"[^A-Za-z0-9._-]", "_", filename)[:120]) or "memo"
    ddir = root / "data" / "uploads" / "credit_docs" / ("lms_" + _re.sub(r"[^A-Za-z0-9._-]", "_", app_id))
    ddir.mkdir(parents=True, exist_ok=True)
    stored = ddir / f"CallBackMemo__{safe}"
    stored.write_bytes(raw)
    files = dict(app.get("document_files", {}) or {})
    files["Call-Back Memo"] = {
        "filename": filename,
        "path": str(stored.relative_to(root)),
        "size": len(raw),
        "uploaded_by": caller,
        "uploaded_at": _dt.datetime.now().isoformat(timespec="seconds"),
    }
    provided = list(app.get("documents_provided", []) or [])
    if "Call-Back Memo" not in provided:
        provided.append("Call-Back Memo")
    lam.update(app_id, {"document_files": files, "documents_provided": provided})
    audit_log("LMS_CALLBACK_MEMO", str(user.get("username", "") or ""), app_id)
    return {"document_files": files}


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


# === DECLINE APPEAL ===
@router.post("/applications/{app_id}/escalate-to-chief")
def lms_escalate_to_chief(
    app_id: str,
    payload: dict = Body(default_factory=dict),
    user: dict = Depends(get_current_user),
):
    """Send a case up to the Chief Credit Risk for their approval.

    RULING (2026-08-15): the bank credit analyst may "approve with pre-approval
    conditions, pre-disbursement conditions, return for additional
    documentation or information, or push to the Chief Credit Risk for their
    approval as well."

    THE CHIEF IS A PERSON, RESOLVED FROM CONFIG, NOT A HARDCODED NAME. A bank
    changes its people more often than its software, and a name in the code is
    a name somebody has to find and edit later - so not even this comment names
    the current holder. Resolution order:

        credit_workflow.chief_credit_risk        an explicit setting
        the chair of committee B4                where the authority already sits
        a register role matching director/head of credit risk

    If none resolves, the escalation is REFUSED and says so. Sending a case to
    nobody is the Eldoret fault: it leaves the queue and arrives nowhere.

    THE CASE STAYS WHERE IT IS. Escalation asks a question of somebody senior;
    it does not hand the case over. The analyst still owns it, and the answer
    comes back to them.
    """
    lam = _lam()
    app = lam.get(app_id)
    if not app:
        raise HTTPException(status_code=404, detail=f"Application '{app_id}' not found")
    if not resolve_application_permissions(user, app).get("can_update"):
        raise HTTPException(status_code=403,
                            detail="You cannot escalate this case.")

    reason = str(payload.get("reason", "") or "").strip()
    if not reason:
        raise HTTPException(
            status_code=400,
            detail="Say why this needs a higher authority. A case arriving "
                   "with no question attached wastes the trip.")
    # ── UP TO A PERSON, OR UP TO A COMMITTEE ────────────────────────────────
    # RULING (2026-08-18): "another item is the Management Credit Committee, so
    # credit risk can also forward to the Management Credit Committee as well."
    #
    # Two different escalations: one asks an individual for their approval, the
    # other puts the case to a committee that will sit and vote on it. Same
    # endpoint, because from the analyst's side the act is identical - this is
    # above my authority, here is why - and the difference is only who answers.
    _target = str(payload.get("to", "chief") or "chief").strip().lower()
    if _target in ("mcc", "management", "management credit committee", "committee"):
        _cfg2 = get_credit_workflow_config() or {}
        _mcc = None
        for _c in (_cfg2.get("committee_palette") or []):
            _nm = str(_c.get("name", "") or "").lower()
            if "management" in _nm or str(_c.get("code")) == "B4":
                _members = [m for m in (_c.get("members") or [])
                            if isinstance(m, dict)
                            and (str(m.get("staff_code", "")).strip()
                                 or str(m.get("name", "")).strip())]
                if _members:
                    _mcc = _c
                    break
        if not _mcc:
            raise HTTPException(
                status_code=400,
                detail="No Management Credit Committee is configured with "
                       "members, so this case would be sent to nobody. Name "
                       "them in Administration > Credit Committees.")
        _esc = list(app.get("escalations") or [])
        _esc.append({
            "reason": reason,
            "by": str(user.get("staff_code", "") or ""),
            "by_name": str(user.get("full_name", "") or ""),
            "to": str(_mcc.get("code")),
            "to_name": str(_mcc.get("name")),
            "kind": "committee",
            # CIRCULATION NOTES: the committee reads the note before it sits.
            "note": str(payload.get("note", "") or "").strip(),
            "at": datetime.now().isoformat(timespec="seconds"),
            "outcome": "",
        })
        lam.update(app_id, {
            "escalations": _esc,
            "escalated_pending": True,
            "status": "referred_to_committee",
            "committee_kind": "mcc",
            "escalated_to_name": str(_mcc.get("name")),
            "escalated_at": datetime.now().isoformat(timespec="seconds"),
            "circulation_note": str(payload.get("note", "") or "").strip(),
            "circulated_by_name": str(user.get("full_name", "") or ""),
        })
        audit_log("LMS_ESCALATED_TO_MCC", str(user.get("username", "") or ""),
                  "%s|%s" % (app_id, _mcc.get("code")))
        return {"application": lam.get(app_id),
                "escalated_to": str(_mcc.get("name")), "status": "escalated"}

    # ── WHO IS THE CHIEF ────────────────────────────────────────────────────
    chief = {}
    try:
        cfg = get_credit_workflow_config() or {}
    except Exception:
        cfg = {}
    explicit = cfg.get("chief_credit_risk") or {}
    if isinstance(explicit, dict) and (explicit.get("staff_code") or explicit.get("name")):
        chief = {"code": str(explicit.get("staff_code", "") or ""),
                 "name": str(explicit.get("name", "") or "")}
    if not chief:
        for c in (cfg.get("committee_palette") or []):
            if str(c.get("code")) == "B4" and str(c.get("chaired_by", "") or "").strip():
                chief = {"code": str(c.get("chair_staff_code", "") or ""),
                         "name": str(c.get("chaired_by"))}
                break
    if not chief:
        try:
            from utils.api_pipeline_scope import get_staff_roster
            df = get_staff_roster()
            for _i, r in df.iterrows():
                role = str(r.get("Role") or "").lower()
                if ("credit risk" in role
                        and ("director" in role or "head" in role or "chief" in role)):
                    chief = {"code": str(r.get("Staff Code") or ""),
                             "name": str(r.get("Staff Name") or "")}
                    break
        except Exception:
            pass
    if not chief or not (chief.get("code") or chief.get("name")):
        raise HTTPException(
            status_code=400,
            detail="No Chief Credit Risk is configured, so this case would be "
                   "sent to nobody. Set credit_workflow.chief_credit_risk, or "
                   "name a chair on committee B4.")

    escalations = list(app.get("escalations") or [])
    escalations.append({
        "reason": reason,
        "by": str(user.get("staff_code", "") or ""),
        "by_name": str(user.get("full_name", "") or ""),
        "to": chief.get("code"),
        "to_name": chief.get("name"),
        "at": datetime.now().isoformat(timespec="seconds"),
        "outcome": "",
    })
    lam.update(app_id, {
        "escalations": escalations,
        "escalated_pending": True,
        "escalated_to_code": chief.get("code"),
        "escalated_to_name": chief.get("name"),
        "escalated_at": datetime.now().isoformat(timespec="seconds"),
    })
    audit_log("LMS_ESCALATED_TO_CHIEF", str(user.get("username", "") or ""),
              "%s|to %s" % (app_id, chief.get("name") or chief.get("code")))
    return {"application": lam.get(app_id), "escalated_to": chief.get("name"),
            "status": "escalated"}


@router.post("/applications/{app_id}/accept-decline")
def lms_accept_decline(
    app_id: str,
    payload: dict = Body(default_factory=dict),
    user: dict = Depends(get_current_user),
):
    """The owner accepts a decline, and the case closes as Lost.

    RULING (2026-08-15): "it should go back to the owner who is to click on
    appeal or accept the decision - if they accept it closes as lost."

    The appeal half already existed. This is the other half, and without it a
    declined case had one exit and no other: appeal, or sit there. Cases that
    sit are how a pipeline stops meaning anything.

    THE OWNER DECIDES, not credit. A decline is credit's answer; whether to
    contest it belongs to the person who raised the case. So this refuses
    anybody who is not the owner or their manager - accepting on somebody
    else's behalf closes their deal for them.

    IT CLOSES THE PIPELINE DEAL TOO. Leaving it open means the branch still
    sees work in progress and the funnel still counts it. Best effort, and
    audited if it fails: the acceptance stands either way, because the decision
    is the fact and the stage is bookkeeping about it.
    """
    lam = _lam()
    app = lam.get(app_id)
    if not app:
        raise HTTPException(status_code=404, detail=f"Application '{app_id}' not found")

    status = str(app.get("status", "") or "").lower()
    if status != "declined":
        raise HTTPException(
            status_code=400,
            detail="This case is not declined (it is %r), so there is nothing "
                   "to accept." % app.get("status"))
    if bool(app.get("appeal_pending")):
        raise HTTPException(
            status_code=400,
            detail="An appeal is already pending on this case. It cannot be "
                   "accepted until that is answered.")

    me = str(user.get("staff_code", "") or "").strip()
    owner = str(app.get("rm_code", "") or "").strip()
    visible = get_visible_staff_codes(user)
    if not (user.get("is_admin") or me == owner or owner in visible):
        raise HTTPException(
            status_code=403,
            detail="Only the case owner or their manager can accept a decline.")

    note = str(payload.get("note", "") or "").strip()
    lam.update(app_id, {
        "status": "declined_accepted",
        "appeal_window_open": False,
        "awaiting_owner_response": False,
        "decline_accepted_at": datetime.now().isoformat(timespec="seconds"),
        "decline_accepted_by": str(user.get("full_name", "") or ""),
        "decline_accepted_note": note,
    })

    closed = ""
    try:
        deal_id = str(app.get("pipeline_deal_id") or "")
        if deal_id:
            from utils.api import _write_deal as _wd
            from utils.core import PipelineManager as _PM
            pm = _PM()
            d = pm.get_deal(deal_id)
            if d and not str(d.get("stage", "")).lower().startswith("closed"):
                _wd(pm, deal_id, {
                    "stage": "Closed Lost",
                    "closed_reason": str(app.get("decline_reason", "")
                                         or "Credit declined"),
                    "closed_at": datetime.now().isoformat(timespec="seconds"),
                    "closed_by_name": str(user.get("full_name", "") or ""),
                }, str(user.get("username", "") or ""))
                closed = deal_id
    except Exception as exc:
        audit_log("PIPELINE_CLOSE_ON_ACCEPT_FAILED",
                  str(user.get("username", "") or ""),
                  "%s|%s: %s" % (app_id, type(exc).__name__, str(exc)[:70]))

    audit_log("LMS_DECLINE_ACCEPTED", str(user.get("username", "") or ""),
              "%s%s" % (app_id, "|closed %s" % closed if closed else ""))
    return {"application": lam.get(app_id), "status": "declined_accepted",
            "deal_closed": closed or None}


@router.post("/applications/{app_id}/appeal")
def lms_application_appeal(
    app_id: str,
    payload: Dict[str, Any] = None,
    user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """The originating side files an appeal against a DECLINED credit decision.
    Records the appeal reason and flags it pending; a manager reviews it via
    /appeal-decision (this does not itself reopen the case)."""
    lam = _lam()
    app = lam.get(app_id)
    if not app:
        raise HTTPException(status_code=404, detail=f"Application '{app_id}' not found")
    visible_codes = get_visible_staff_codes(user)
    caller_code = str(user.get('staff_code', '') or '')
    caller_role = str(user.get('role', '') or '')
    if not user.get('is_admin') and not is_app_in_scope(app, visible_codes, caller_code, caller_role=caller_role):
        raise HTTPException(status_code=403, detail="Application is out of scope")
    if str(app.get('status', '') or '').lower() != 'declined':
        raise HTTPException(status_code=400, detail="Only a declined application can be appealed")
    if bool(app.get('appeal_pending')):
        raise HTTPException(status_code=400, detail="An appeal is already pending on this application")
    reason = str((payload or {}).get('reason', '') or '').strip()
    if not reason:
        raise HTTPException(status_code=400, detail="An appeal reason is required")
    from datetime import datetime as _dt
    appeals = list(app.get('appeals', []) or [])
    appeals.append({
        "reason": reason,
        "by_code": caller_code,
        "by_name": str(user.get('full_name', '') or user.get('username', '') or ''),
        "at": _dt.now().isoformat(timespec="seconds"),
        "outcome": "PENDING",
    })
    lam.update(app_id, {"appeals": appeals, "appeal_pending": True})
    try:
        lam._log_event(app_id, "decline_appealed", caller_code, note=reason,
                       by_name=str(user.get('full_name', '') or ''), by_role=caller_role)
    except Exception:
        pass
    return {"status": "appealed", "appeals": appeals, "appeal_pending": True}


@router.post("/applications/{app_id}/appeal-decision")
def lms_application_appeal_decision(
    app_id: str,
    payload: Dict[str, Any] = None,
    user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """A manager reviews a pending decline appeal: 'uphold' (decline stands) or
    'grant' (reopen the case for a fresh decision — status back to 'assigned')."""
    if not is_manager(user) and not user.get('is_admin'):
        raise HTTPException(status_code=403, detail="Manager authority required to decide appeals")
    lam = _lam()
    app = lam.get(app_id)
    if not app:
        raise HTTPException(status_code=404, detail=f"Application '{app_id}' not found")
    visible_codes = get_visible_staff_codes(user)
    caller_code = str(user.get('staff_code', '') or '')
    caller_role = str(user.get('role', '') or '')
    if not user.get('is_admin') and not is_app_in_scope(app, visible_codes, caller_code, caller_role=caller_role):
        raise HTTPException(status_code=403, detail="Application is out of scope")
    if not bool(app.get('appeal_pending')):
        raise HTTPException(status_code=400, detail="No appeal is pending on this application")
    outcome = str((payload or {}).get('outcome', '') or '').lower()  # "grant" | "uphold"
    if outcome not in ("grant", "uphold"):
        raise HTTPException(status_code=400, detail="outcome must be 'grant' or 'uphold'")
    note = str((payload or {}).get('note', '') or '').strip()
    from datetime import datetime as _dt
    appeals = list(app.get('appeals', []) or [])
    for a in reversed(appeals):
        if str(a.get('outcome', '')).upper() == 'PENDING':
            a["outcome"] = "GRANTED" if outcome == "grant" else "UPHELD"
            a["reviewed_by_code"] = caller_code
            a["reviewed_by_name"] = str(user.get('full_name', '') or user.get('username', '') or '')
            a["reviewed_at"] = _dt.now().isoformat(timespec="seconds")
            a["review_note"] = note
            break
    fields = {"appeals": appeals, "appeal_pending": False}
    if outcome == "grant":
        fields["status"] = "assigned"  # reopen for a fresh decision
    lam.update(app_id, fields)
    try:
        lam._log_event(app_id, "appeal_granted" if outcome == "grant" else "appeal_upheld",
                       caller_code, note=note, by_name=str(user.get('full_name', '') or ''), by_role=caller_role)
    except Exception:
        pass
    return {"status": "appeal_" + ("granted" if outcome == "grant" else "upheld"),
            "appeals": appeals, "reopened": outcome == "grant"}


# === C2: CORRECTNESS STAGING ===
@router.get("/rework-reasons")
def lms_rework_reasons(
    user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """The configured rework reason codes (lms_config -> rework_reasons), so the
    correctness reviewer can pick specific reasons when returning a case for rework."""
    from pathlib import Path as _Path
    import json as _json
    p = _Path(__file__).resolve().parent.parent / "data" / "lms_config.json"
    reasons = []
    try:
        if p.exists():
            cfg = _json.loads(p.read_text(encoding="utf-8")) or {}
            r = cfg.get("rework_reasons")
            if isinstance(r, list):
                reasons = [str(x) for x in r if str(x).strip()]
    except Exception:
        reasons = []
    return {"rework_reasons": reasons}


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
    # ── A VERDICT IS GIVEN ONCE ─────────────────────────────────────────────
    # RULING (2026-08-14): "I was able to mark it ready twice, it should be
    # once." A recommendation is a position on a credit decision, and being
    # able to record it twice makes the journey read as though the analyst
    # changed their mind - or worse, as though the system lost the first one.
    _prev = app.get("committee_readiness") or {}
    if isinstance(_prev, dict) and _prev.get("state") == "ready_for_committee" \
            and decision == "ready":
        raise HTTPException(
            status_code=409,
            detail=("This case was already recommended for committee by %s on "
                    "%s. A recommendation is recorded once."
                    % (_prev.get("by_name") or "an analyst",
                       str(_prev.get("at", ""))[:16])))

    _updates = {"committee_readiness": readiness}

    # ── READY MEANS SUBMITTED ───────────────────────────────────────────────
    # RULING (2026-08-14): "when marked ready, it did not flow to the
    # department review ... once the analyst confirms that the case is
    # recommended for department committee it should autosubmit."
    #
    # It did not, because this recorded a READINESS STATE and stopped. The case
    # kept its status, never became a committee case, and the committee tab
    # correctly reported that it had not been submitted - because it had not.
    #
    # A recommendation IS the submission. Making the analyst then find another
    # button to send what they have just recommended is the delay the ruling
    # was about.
    if decision == "ready":
        _updates.update({
            "status": "referred_to_committee",
            "committee_kind": "dcc",
            "referred_to_committee_at": _dt.now().isoformat(timespec="seconds"),
            "referred_by_name": str(user.get("full_name", "") or ""),
        })

    # ── A REWORK MUST ACTUALLY GO BACK ──────────────────────────────────────
    # RULING (2026-08-14): "a returned case reopens back to the branch on the
    # owner, and once they complete the reworks they resubmit - this time back
    # to the credit analyst to continue."
    #
    # This endpoint recorded a READINESS STATE and nothing else: the case kept
    # its status, stayed in the analyst's queue, and the branch was never told.
    # An analyst could mark a case "returned for rework" and it would sit
    # exactly where it was, which is the shape of a case quietly stalling.
    #
    # The state was right and the movement was missing. A rework now sets the
    # status to `returned` and remembers WHO returned it, so
    # resubmit-after-rework brings it back to that analyst rather than to the
    # pool - they have the context, and re-queueing turns a two-hour correction
    # into a two-day one.
    # ── A REWORK MUST ACTUALLY GO BACK ──────────────────────────────────────
    # RULING (2026-08-14): "a returned case reopens back to the branch on the
    # owner, and once they complete the reworks they resubmit - this time back
    # to the credit analyst to continue."
    #
    # This endpoint recorded a READINESS STATE and nothing else: the case kept
    # its status, stayed in the analyst's queue, and the branch was never told.
    # An analyst could mark a case "returned for rework" and it would sit
    # exactly where it was, which is the shape of a case quietly stalling.
    #
    # The state was right and the movement was missing. A rework now sets the
    # status to `returned` and remembers WHO returned it, so
    # resubmit-after-rework brings it back to that analyst rather than to the
    # pool - they have the context, and re-queueing turns a two-hour correction
    # into a two-day one.
    if decision == "rework":
        _me = str(user.get("staff_code", "") or "").strip()
        _myname = str(user.get("full_name", "") or "").strip()
        _reason = str(p.get("opinion", "") or "").strip()
        _items = [str(x) for x in (p.get("reasons") or []) if str(x).strip()]
        _history = list(app.get("rework_history") or [])
        _history.append({
            "reason": _reason or "; ".join(_items) or "Returned for rework",
            "items": _items,
            "by": _me, "by_name": _myname,
            "at": datetime.now().isoformat(timespec="seconds"),
        })
        _updates.update({
            "status": "returned",
            "rework_history": _history,
            "rework_reasons": _reason or "; ".join(_items),
            "returned_by_code": _me,
            "returned_by_name": _myname,
            "returned_at": datetime.now().isoformat(timespec="seconds"),
        })

    lam.update(app_id, _updates)
    # Phase C part 3: record the correctness reviewer's verdict on the journey
    # (ready_for_committee | returned_for_rework) with their name/role + reason,
    # so the travelling document shows the rework loop, not just the outcome.
    try:
        _rnote = readiness["opinion"] or (
            "; ".join(str(r) for r in readiness["reasons"]) if readiness["reasons"] else ""
        )
        lam._log_event(
            app_id, readiness["state"], caller_code,
            note=_rnote, by_name=readiness["by_name"], by_role=caller_role,
        )
    except Exception:
        pass
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

