"""utils/api_lms_permissions.py — Per-application permissions resolution.

Authored v10.515 Phase 3 Arc α Batch α8 — LMS API.

Mirrors api_pipeline_permissions.py for the LMS domain. Returns a flag
set the React UI uses to enable/disable controls. The server still
enforces the same checks at each mutation endpoint — these flags are
UX hints, not the security boundary.

Authorization tiers (precedence order):
  1. Admin (is_admin=True) → everything True
  2. Manager-in-scope (is_manager() + app in cascade) → most things True
  3. Owner / Analyst (in scope on the deal) → can_view + can_update
  4. Out-of-scope → all False (and the endpoint should 403)

Status guardrails further constrain can_update and can_record_decision.
"""
from __future__ import annotations

from typing import Dict, Any, Optional, Set

from utils.api_pipeline_manager_actions import is_manager
from utils.api_lms_scope import is_app_in_scope
from utils.api_lms_mutations import (
    STATUSES_PERMITTING_UPDATE,
    STATUSES_PERMITTING_DECISION,
    STATUSES_PERMITTING_ASSIGN,
)


def _all_false() -> Dict[str, bool]:
    """Default permissions: everything denied."""
    return {
        "can_view": False,
        "can_update": False,
        "can_assign": False,
        "can_record_decision": False,
        "can_escalate": False,
        "can_request_info": False,
        "can_provide_info": False,
        "can_sign_offer": False,
        "can_validate_offer": False,
        "can_confirm_to_credit_admin": False,
        "can_refer_committee": False,
        "can_vote_committee": False,
        "can_resolve_committee": False,
    }


def resolve_application_permissions(
    user: Dict[str, Any],
    app: Dict[str, Any],
    visible_codes: Optional[Set[str]] = None,
) -> Dict[str, bool]:
    """Compute permission flags for caller-vs-application pair.

    Parameters
    ----------
    user : dict
        The authenticated user (from get_current_user dependency).
        Expected keys: staff_code, role, is_admin.
    app : dict
        The application record from LoanApplicationManager.
    visible_codes : set of str, optional
        Pre-computed cascade scope. If None, the function recomputes
        it via get_visible_staff_codes — but callers that already
        have it should pass it to avoid the extra computation.

    Returns
    -------
    dict
        Four boolean flags: can_view, can_update, can_assign,
        can_record_decision.
    """
    if not app or not user:
        return _all_false()

    caller_code = str(user.get('staff_code', '') or '')
    is_admin = bool(user.get('is_admin', False))
    is_mgr = is_manager(user)

    if visible_codes is None:
        # Lazy import to avoid a circular if api_pipeline_scope ever
        # imports something that ends up importing this module.
        from utils.api_pipeline_scope import get_visible_staff_codes
        visible_codes = get_visible_staff_codes(user)

    in_scope = is_app_in_scope(
        app, visible_codes, caller_code,
        caller_role=str(user.get('role', '') or ''),
    )

    # Stake-holders on the application
    rm_code = str(app.get('rm_code', '') or '')
    is_owner = bool(caller_code) and (rm_code == caller_code)

    analyst = app.get('analyst') or {}
    analyst_code = str(analyst.get('code', '') or '') if isinstance(analyst, dict) else ''
    is_assigned_analyst = bool(caller_code) and (analyst_code == caller_code)

    status = str(app.get('status', '') or '').lower()

    # ── can_view ──
    # Admin sees all. Manager sees their cascade. Owner sees their own.
    # Assigned analyst sees their assignments.
    can_view = is_admin or in_scope or (is_mgr and in_scope)

    # ── can_update ──
    # Status guardrail FIRST. Then either:
    #   - admin, OR
    #   - assigned analyst, OR
    #   - manager-tier with the app in their cascade
    # NOTE: the deal owner (RM) is deliberately NOT granted can_update. Once a
    # case is in credit, the RM/owner can VIEW its progress but not edit the
    # analysis (workbench, appraisal, completeness). Their own touchpoints —
    # provide-info and sign-offer — are granted separately below.
    can_update = (
        status in STATUSES_PERMITTING_UPDATE
        and (is_admin or is_assigned_analyst or (is_mgr and in_scope))
    )

    # ── can_assign ──
    # Manager-tier-only (per Q1 decision in α8 planning). Status must
    # be 'submitted' (no re-assignment of already-assigned apps).
    can_assign = (
        status in STATUSES_PERMITTING_ASSIGN
        and (is_admin or (is_mgr and in_scope))
    )

    # ── can_record_decision ──
    # The assigned analyst records the verdict (approve / decline / return-
    # for-rework) on their case. Manager-tier and admin also retain this
    # (oversight / acting on behalf). Status must permit a decision.
    can_record_decision = (
        status in STATUSES_PERMITTING_DECISION
        and (is_admin or is_assigned_analyst or (is_mgr and in_scope))
    )

    # ── can_escalate ──
    # When the assigned analyst cannot decide alone, they escalate / seek
    # guidance — routing the case to their line manager for input. Available
    # to the assigned analyst (and admin) while the case is in an analysable
    # state. The line manager then picks it up in their cascade.
    can_escalate = (
        status in STATUSES_PERMITTING_DECISION
        and (is_admin or is_assigned_analyst)
    )

    # ── Credit workflow flags (v10.587) ──
    try:
        from utils.api_lms_mutations import get_credit_workflow_config
        cfg = get_credit_workflow_config()
    except Exception:
        cfg = {}
    require_validation = bool(cfg.get("require_line_manager_offer_validation", True))
    require_confirm = bool(cfg.get("require_analyst_confirmation", True))

    can_request_info = (
        status == "assigned"
        and (is_admin or is_assigned_analyst or (is_mgr and in_scope))
    )
    can_provide_info = (
        status == "info_requested" and (is_admin or is_owner or in_scope)
    )
    can_sign_offer = (
        status == "offer_issued" and (is_admin or is_owner or in_scope)
    )
    can_validate_offer = (
        status == "offer_signed" and require_validation
        and (is_admin or (is_mgr and in_scope))
    )
    _confirm_status_ok = (
        status == "offer_validated"
        or (status == "offer_signed" and not require_validation)
    )
    can_confirm_to_credit_admin = (
        _confirm_status_ok and require_confirm
        and (is_admin or is_assigned_analyst or in_scope)
    )

    try:
        from utils.api_lms_committee import committee_mode_on, committee_required
        _amount = float(app.get("amount", 0) or 0)
        _committee_on = committee_mode_on()
        _committee_tier = committee_required(_amount)
    except Exception:
        _committee_on = False
        _committee_tier = False
    can_refer_committee = (
        _committee_on and _committee_tier
        and status in ("submitted", "assigned")
        and (is_admin or (is_mgr and in_scope))
    )
    can_vote_committee = (
        status == "referred_to_committee" and (is_admin or in_scope)
    )
    can_resolve_committee = (
        status == "referred_to_committee" and (is_admin or (is_mgr and in_scope))
    )

    return {
        "can_view": bool(can_view),
        "can_update": bool(can_update),
        "can_assign": bool(can_assign),
        "can_record_decision": bool(can_record_decision),
        "can_escalate": bool(can_escalate),
        "can_request_info": bool(can_request_info),
        "can_provide_info": bool(can_provide_info),
        "can_sign_offer": bool(can_sign_offer),
        "can_validate_offer": bool(can_validate_offer),
        "can_confirm_to_credit_admin": bool(can_confirm_to_credit_admin),
        "can_refer_committee": bool(can_refer_committee),
        "can_vote_committee": bool(can_vote_committee),
        "can_resolve_committee": bool(can_resolve_committee),
    }


def enrich_app_with_permissions(
    user: Dict[str, Any],
    app: Dict[str, Any],
    visible_codes: Optional[Set[str]] = None,
) -> Dict[str, Any]:
    """Convenience wrapper that returns app + permissions in one dict.

    Useful for endpoints that want to inline permissions into the
    application record (e.g. list endpoints that don't have a separate
    permissions field per record).

    Returns the original app dict with an added '_permissions' key.
    Non-destructive — returns a new dict, doesn't mutate the input.
    """
    perms = resolve_application_permissions(user, app, visible_codes)
    return {**app, "_permissions": perms}
