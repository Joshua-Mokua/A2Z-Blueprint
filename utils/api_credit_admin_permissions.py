"""utils/api_credit_admin_permissions.py — Per-case permissions resolver.

Authored v10.518 Phase 3 Arc α Batch α9 — Credit Admin API.

Mirrors api_lms_permissions.py for the credit-admin domain. Returns
permission flags consumed by both the React UI (control enable/disable)
and the server endpoints (enforcement).

Permission tiers (per α9 planning decisions):
  can_view              — in cascade scope OR admin
  can_fulfill_condition — in cascade scope AND case not disbursed
                          (anyone in scope, operations-level action)
  can_disburse          — manager-tier AND in scope AND
                          all_conditions_met AND not disbursed
                          (financially significant — manager-only)
"""
from __future__ import annotations

from typing import Dict, Any, Optional, Set

from utils.api_pipeline_manager_actions import is_manager
from utils.api_credit_admin_scope import is_case_in_scope


def _all_false() -> Dict[str, bool]:
    return {
        "can_view": False,
        "can_fulfill_condition": False,
        "can_disburse": False,
    }


def resolve_case_permissions(
    user: Dict[str, Any],
    case: Dict[str, Any],
    visible_codes: Optional[Set[str]] = None,
) -> Dict[str, bool]:
    """Compute permission flags for caller-vs-case pair.

    Parameters
    ----------
    user : dict
        Authenticated user from get_current_user dependency
    case : dict
        Credit-admin case record from CreditAdminManager
    visible_codes : set of str, optional
        Pre-computed cascade scope; recomputes if not provided

    Returns
    -------
    dict with can_view, can_fulfill_condition, can_disburse
    """
    if not case or not user:
        return _all_false()

    is_admin = bool(user.get('is_admin', False))
    is_mgr = is_manager(user)

    if visible_codes is None:
        from utils.api_pipeline_scope import get_visible_staff_codes
        visible_codes = get_visible_staff_codes(user)

    in_scope = is_case_in_scope(case, visible_codes)

    disbursed = bool(case.get('disbursed', False))
    all_conditions_met = bool(case.get('all_conditions_met', False))

    # ── can_view ──
    # Admin sees all. In-scope sees their cascade's cases.
    can_view = is_admin or in_scope

    # ── can_fulfill_condition ──
    # Anyone in scope can fulfill (operations action). Blocked once
    # the case is disbursed (no edits to closed cases).
    can_fulfill_condition = (is_admin or in_scope) and not disbursed

    # ── can_disburse ──
    # Manager-tier + in scope, AND all conditions must already be met,
    # AND case not already disbursed.
    can_disburse = (
        (is_admin or (is_mgr and in_scope))
        and all_conditions_met
        and not disbursed
    )

    return {
        "can_view": bool(can_view),
        "can_fulfill_condition": bool(can_fulfill_condition),
        "can_disburse": bool(can_disburse),
    }
