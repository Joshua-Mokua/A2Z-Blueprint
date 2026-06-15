"""utils/api_pipeline_permissions.py — Per-deal permission resolution.

Authored v10.509 Phase 3 Arc α Batch α7.

Purpose
-------
Compute the 6-permission object that the API returns alongside each
deal record. The React UI uses this to decide which buttons to show
on each deal card without duplicating authorization logic in
TypeScript or trial-and-erroring through 403 responses.

Doctrine context
----------------
Per ``PIPELINE_DOMAIN_AUDIT.md`` Section 15.6, every deal has a 4-tier
caller-vs-deal relationship that determines what actions are
permitted:

================ ===== ============== ============= ====================
 Role            View  Stage advance  Edit details  Approve cancel
================ ===== ============== ============= ====================
 Owner (RM)      yes   yes            yes           request only
 Backup          yes   yes            NO            no
 Manager (scope) yes   yes            yes           yes
 Out of scope    no    no             no            no
================ ===== ============== ============= ====================

α7 extends this with state-based filtering — a permission is only True
if BOTH the role allows it AND the deal's current state makes the
action sensible. For example, ``can_advance_stage`` is False for any
deal at ``Closed Won`` or ``Closed Lost`` regardless of who the caller
is. This is the "should the button be rendered" question, not the
"is the user authorized" question — but for a clean React UI both
need to be False before the button hides.

Streamlit edge case mirrored, not fixed
----------------------------------------
After a cancel request is *rejected* (manager hit Reject, not
Approve), Streamlit sets ``cancel_approved=False`` (explicit False,
not just clearing the flag). The queue filter
``cancel_requested AND not cancel_approved`` still matches False as
"not yet approved" — so the deal continues to show in the queue
after rejection. α7's ``can_approve_cancel`` mirrors this: True
whenever ``cancel_requested`` is set and ``cancel_approved`` is
falsy. Documented in REVIVAL_LEDGER as a finding; fix deferred.
"""
from __future__ import annotations

from typing import Any, Dict, Set


# Stages from which no further advance makes sense (terminal stages).
# Used to gate can_advance_stage and can_request_cancel.
TERMINAL_STAGES: Set[str] = {
    "Closed Won",
    "Closed Lost",
    "Account Opened",   # terminal for Account pipeline
    "Funded",           # terminal for Deposit pipeline
}


# Stages at which a deal becomes subject to manager validation. Matches
# the threshold from utils/core.py:1352 (PIPELINE_VALIDATE_STAGE =
# "Contacted") — deals at Contacted or further down the loan workflow
# need manager validation before they count in forecasts.
#
# This list mirrors what PipelineManager.get_pending_validations
# considers "post-validation-threshold" — see utils/core.py:4045-4053.
VALIDATION_STAGES: Set[str] = {
    "Lead",          # validate at creation (first defense against ghost deals)
    "Contacted",
    "Qualified",
    "Proposal",
    "Negotiation",
    "Compliance",
    "Credit Review",
    "Approval",
    "Bank Approval",
    "Credit Committee",
    "Documentation",
    "Vetting",
    "Disbursed",
    # Account + Deposit also need validation past first stage
    "Documentation Complete",
    "Negotiating",
}


# The full set of permissions α7 ships. Adding a new permission means
# updating both this constant and the resolve_deal_permissions function.
# G400 verifies the function returns exactly these keys.
PERMISSION_KEYS: tuple = (
    "can_view",
    "can_edit",
    "can_advance_stage",
    "can_request_cancel",
    "can_approve_cancel",
    "can_validate",
)


def _all_false() -> Dict[str, bool]:
    """Return a permissions dict with every key set to False.

    Used for out-of-scope deals and as the safe default if anything
    in the resolution logic fails unexpectedly.
    """
    return {k: False for k in PERMISSION_KEYS}


def resolve_deal_permissions(
    deal: Dict[str, Any],
    user: Dict[str, Any],
    visible_staff_codes: Set[str],
) -> Dict[str, bool]:
    """Compute the 6-permission object for a deal + caller.

    Parameters
    ----------
    deal : dict
        A pipeline deal record (from ``PipelineManager.get_deal()`` or
        similar). Must have at minimum ``staff_code``; may have
        ``backup_staff_codes``, ``stage``, ``cancel_requested``,
        ``cancel_approved``, ``manager_validated``, ``draft``.
    user : dict
        The authenticated user dict. Must have ``staff_code`` (or
        equivalent identifier); may have ``role`` and ``is_admin``.
    visible_staff_codes : set
        The set of staff codes the user can see per cascade scope
        (from ``utils.api_pipeline_scope.get_visible_staff_codes``).
        For admins this is effectively the whole bank.

    Returns
    -------
    dict
        Six boolean keys: ``can_view``, ``can_edit``,
        ``can_advance_stage``, ``can_request_cancel``,
        ``can_approve_cancel``, ``can_validate``.

    Notes
    -----
    Defensive on missing/None inputs — returns all-False rather than
    raising. This is intentional: a malformed deal record shouldn't
    crash the endpoint; the React UI just won't render any buttons.
    """
    # Defensive defaults
    if not deal or not user:
        return _all_false()

    # Lazy import to avoid cycles
    try:
        from utils.api_pipeline_manager_actions import is_manager
    except Exception:
        return _all_false()

    # Caller identifiers
    my_code = str(user.get("staff_code", "") or "").strip()
    is_admin = bool(user.get("is_admin", False))
    caller_is_manager = is_manager(user)

    # Deal facts
    deal_staff = str(deal.get("staff_code", "") or "").strip()
    backup_codes = deal.get("backup_staff_codes", []) or []
    backup_codes_str = {str(c).strip() for c in backup_codes if c}
    stage = str(deal.get("stage", "") or "")
    cancel_requested = bool(deal.get("cancel_requested", False))
    cancel_approved = deal.get("cancel_approved", None)
    manager_validated = bool(deal.get("manager_validated", False))
    is_draft = bool(deal.get("draft", False))

    # Relationship determination
    is_owner = bool(my_code) and my_code == deal_staff
    is_backup = bool(my_code) and my_code in backup_codes_str
    # Manager-in-scope: caller is a manager (or admin) AND the deal's
    # owner is visible in the caller's cascade. Admins always pass scope.
    if is_admin:
        is_manager_in_scope = True
    elif caller_is_manager:
        is_manager_in_scope = (
            bool(deal_staff) and deal_staff in visible_staff_codes
        )
    else:
        is_manager_in_scope = False

    # If none of owner/backup/manager-in-scope, treat as out-of-scope
    if not (is_owner or is_backup or is_manager_in_scope):
        return _all_false()

    # Stage gates
    in_terminal_stage = stage in TERMINAL_STAGES
    in_validation_stage = stage in VALIDATION_STAGES

    # ── Permission computation ─────────────────────────────────────
    can_view = is_owner or is_backup or is_manager_in_scope

    # Backup explicitly cannot edit (Section 15.6 line 656)
    can_edit = (is_owner or is_manager_in_scope) and not is_backup_only(
        is_owner, is_backup, is_manager_in_scope
    )

    # All three roles can advance, gated on non-terminal stage
    can_advance_stage = (
        (is_owner or is_backup or is_manager_in_scope)
        and not in_terminal_stage
    )

    # Anyone with view can request — but not on already-requested
    # or terminal deals
    can_request_cancel = (
        can_view
        and not cancel_requested
        and not in_terminal_stage
    )

    # Only managers approve. Streamlit's queue filter is mirrored:
    # cancel_requested AND not cancel_approved — note "not None" and
    # "not False" both evaluate True, so a rejected deal stays
    # "approvable" (Streamlit edge case carried forward).
    can_approve_cancel = (
        is_manager_in_scope
        and cancel_requested
        and not cancel_approved
    )

    # Validation: manager-only, in validation stage, not yet validated,
    # not in cancel flow, not a draft
    can_validate = (
        is_manager_in_scope
        and in_validation_stage
        and not manager_validated
        and not cancel_requested
        and not is_draft
    )

    return {
        "can_view":             can_view,
        "can_edit":             can_edit,
        "can_advance_stage":    can_advance_stage,
        "can_request_cancel":   can_request_cancel,
        "can_approve_cancel":   can_approve_cancel,
        "can_validate":         can_validate,
    }


def is_backup_only(
    is_owner: bool, is_backup: bool, is_manager_in_scope: bool
) -> bool:
    """Return True if the caller's ONLY relationship to the deal is
    being a backup (not also owner, not also a manager in scope).

    A backup who is also the owner gets owner-tier permissions.
    A backup who is also a manager-in-scope gets manager-tier
    permissions. The "backup only" case is the one with the
    no-edit restriction (Section 15.6 line 656).
    """
    return is_backup and not is_owner and not is_manager_in_scope


def enrich_deal_with_permissions(
    deal_dict: Dict[str, Any],
    user: Dict[str, Any],
    visible_staff_codes: Set[str],
) -> Dict[str, Any]:
    """Return a copy of ``deal_dict`` with a ``permissions`` field
    added, computed for ``user``.

    Convenience wrapper for API endpoints. Doesn't mutate input —
    returns a new dict. If the deal record already has a
    ``permissions`` key, it's overwritten (defensive against
    misshapen records).
    """
    if not deal_dict:
        return deal_dict
    enriched = dict(deal_dict)
    enriched["permissions"] = resolve_deal_permissions(
        deal_dict, user, visible_staff_codes
    )
    return enriched
