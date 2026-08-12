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
    # KEPT for the global flows that still use these names. It is NOT the whole
    # answer any more - see _needs_validation below.
    "Lead", "Contacted", "Qualified", "Proposal", "Negotiation", "Negotiating",
    "Documentation", "Documentation Complete", "Credit Review",
    "Credit Committee", "Bank Approval", "Approval", "Vetting", "Compliance",
    "Disbursed",
}

# TERMINAL stages: a closed deal is never awaiting validation.
_TERMINAL_HINTS = ("closed", "disbursement", "trops")


def _needs_validation(stage: str) -> bool:
    """Is a deal at this stage still awaiting its manager's validation?

    THE FIXED LIST ABOVE IS NOT THE WHOLE TRUTH, and this is the second half of
    a fix that was only half made. PipelineManager._stage_needs_validation was
    widened so per-product stages appear in a manager's QUEUE - but this module
    still tested membership of the global list, so the PERMISSION stayed false.
    A Mortgage deal at 'Initiation', or at any of the six credit stages, showed
    in the queue with can_validate False: the manager saw it and the button did
    nothing.

    Same rule as the queue now: everything that is not terminal is validatable.
    A per-product stage cannot be ranked against a global list, but it is live
    and somebody must validate it.
    """
    st = str(stage or "").strip()
    if not st:
        return False
    low = st.lower()
    if any(h in low for h in _TERMINAL_HINTS):
        return False
    return True


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
    # Referral participant: the caller (or anyone in their visible scope — i.e. a
    # head/manager whose TEAM made the referral) referred this deal, or it was
    # referred TO them/their team. Grants read-only VIEW so they can track a
    # referred case to closure even though they don't own it (the deal is owned by
    # the recipient RM, who may be outside the caller's cascade scope). Uses
    # canon() so a zero-padded FLEXCUBE code (KE0439) matches the roster (KE439).
    try:
        from utils.staff_code import canon as _canon_pc
        _my = _canon_pc(my_code) if my_code else ""
        _rby = _canon_pc(str(deal.get("referred_by_code", "") or "").strip())
        _rto = _canon_pc(str(deal.get("referred_to_code", "") or "").strip())
        _vis_canon = {_canon_pc(str(c).strip()) for c in (visible_staff_codes or []) if str(c).strip()}
        is_referral_participant = bool(_rby or _rto) and (
            (bool(_my) and (_my == _rby or _my == _rto))
            or (_rby in _vis_canon) or (_rto in _vis_canon)
        )
    except Exception:
        _rby = str(deal.get("referred_by_code", "") or "").strip()
        _rto = str(deal.get("referred_to_code", "") or "").strip()
        _vis = {str(c).strip() for c in (visible_staff_codes or [])}
        is_referral_participant = bool(_rby or _rto) and (
            (bool(my_code) and (my_code == _rby or my_code == _rto))
            or (_rby in _vis) or (_rto in _vis)
        )
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

    # ── CREDIT ANALYST, READ ONLY, WITHIN THEIR SEGMENT ─────────────────────
    # RULING (2026-08-12): "Catherine, being in the consumer head office unit,
    # is supposed to also have view of all consumer pipeline - same case for the
    # other analysts."
    #
    # An analyst has no reports, so the reporting tree gives her nothing and
    # every deal but her own returned 404. She could be handed a case for
    # analysis and could not see the pipeline it came from.
    #
    # VIEW ONLY, and only within her own segment. She is not an owner, not a
    # backup and not a manager - so can_edit, can_advance and the rest are
    # untouched below and stay false. Widening the read is what was asked for;
    # widening the write was not, and would put a credit analyst in charge of
    # somebody else's deal.
    is_segment_viewer = False
    try:
        from utils.api_lms_scope import _analyst_segment
        _seg = _analyst_segment(str(user.get("role", "") or ""),
                                str(user.get("staff_code", "") or ""))
        if _seg:
            _ct = str(deal.get("client_type") or deal.get("segment") or "").lower()
            _prod = str(deal.get("product_type") or deal.get("product") or "").lower()
            _hay = _ct + " " + _prod
            _match = {"consumer": ("individual", "personal", "consumer", "retail"),
                      "commercial": ("business", "sme", "commercial"),
                      "cib": ("corporate", "institution", "cib")}.get(_seg, ())
            # A deal whose segment cannot be read is NOT shown. Guessing here
            # would leak a corporate deal to a consumer analyst, which is the
            # error that matters in this direction.
            is_segment_viewer = any(m in _hay for m in _match)
    except Exception:
        is_segment_viewer = False

    # ── SITTING ON A COMMITTEE THE CASE MUST PASS GRANTS SIGHT OF IT ────────
    # Found by testing (2026-08-12): a branch committee member could see their
    # cases because the branch is in their cascade, but a DEPARTMENT committee
    # member saw NOTHING. The DCC sits at head office and a branch RM is not in
    # their tree, so scope removed every case they were being asked to decide.
    #
    # Being asked to decide on a case implies being allowed to read it - less a
    # widening of scope than the missing half of it. The bank put these people
    # on the committee precisely so they would judge these deals.
    #
    # VIEW ONLY. They are not the owner, so can_edit and can_advance stay false
    # below; they read the case and record the committee's decision, which is a
    # separate endpoint with its own gate.
    #
    # THE CONFIG IS READ DIRECTLY, not through utils.api - that would be a
    # CIRCULAR import, and an earlier attempt had its exception swallowed by
    # the guard, so the whole branch silently did nothing.
    is_committee_member = False
    try:
        _my = str(user.get("staff_code", "") or "").strip()
        _myname = str(user.get("full_name", "") or "").strip().lower()
        if _my or _myname:
            import json as _json
            import os as _os
            with open(_os.path.join("data", "lms_config.json"), encoding="utf-8") as _fh:
                _cfg = _json.load(_fh) or {}
            _pal = ((_cfg.get("credit_workflow") or {}).get("committee_palette") or [])
            # The two rules that put a committee on a deal's journey, applied
            # here rather than imported: the deal's own BRANCH committee, and
            # the committee matching its CLIENT TYPE.
            _b = str(deal.get("branch") or deal.get("unit") or "").strip().lower()
            _ct = str(deal.get("client_type") or "").strip().lower()
            for _c in _pal:
                if str(_c.get("kind", "")).lower() == "branch":
                    if not (_b and str(_c.get("branch", "")).strip().lower() == _b):
                        continue
                else:
                    _nm = str(_c.get("name", "")).lower()
                    if not (_ct and (_ct in _nm or _nm.startswith(_ct))):
                        continue
                _mem = _c.get("members") or []
                _codes = {str(m.get("staff_code", "") or "").strip()
                          for m in _mem if isinstance(m, dict)}
                _names = {str(m.get("name", "") or "").strip().lower()
                          for m in _mem if isinstance(m, dict)}
                _chair = str(_c.get("chaired_by", "") or "").strip().lower()
                if ((_my and _my in _codes)
                        or (_myname and (_myname in _names or _myname == _chair))):
                    is_committee_member = True
                    break
    except Exception:
        is_committee_member = False

    # NOTE: this guard appeared TWICE on origin/main - identical blocks back to
    # back. Harmless, since it is idempotent, but dead. Collapsed to one.
    if not (is_owner or is_backup or is_manager_in_scope
            or is_referral_participant or is_segment_viewer
            or is_committee_member):
        return _all_false()

    # NOTE: this guard appeared TWICE on origin/main - identical blocks back to
    # back. Harmless, being idempotent, but dead. Collapsed to one.
    if not (is_owner or is_backup or is_manager_in_scope
            or is_referral_participant or is_segment_viewer
            or is_committee_member):
        return _all_false()

    # Stage gates
    in_terminal_stage = stage in TERMINAL_STAGES
    in_validation_stage = _needs_validation(stage)

    # ── Permission computation ─────────────────────────────────────
    can_view = (is_owner or is_backup or is_manager_in_scope
                or is_referral_participant or is_segment_viewer
                or is_committee_member)

    # B7: a non-admin manager oversees/validates/queries but does NOT operate a
    # subordinate's deal — the owner drives it (advance/edit). Admin retains
    # full operate rights and is the interim continuity path for reassigning a
    # departed RM's deals until the dedicated admin reassignment lands.
    is_admin_like = is_admin or "admin" in str(user.get("role", "")).lower()

    # Backup explicitly cannot edit (Section 15.6 line 656). Managers no longer
    # edit a subordinate's deal; owner + admin only.
    can_edit = (is_owner or is_admin_like) and not is_backup_only(
        is_owner, is_backup, is_manager_in_scope
    )

    # Owner + backup advance their own/covered deal; admin retains advance.
    # Non-admin managers validate/query instead of advancing.
    can_advance_stage = (
        (is_owner or is_backup or is_admin_like)
        and not in_terminal_stage
    )

    # Anyone with view can request — but not on already-requested
    # or terminal deals
    can_request_cancel = (
        (is_owner or is_backup or is_manager_in_scope)
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
