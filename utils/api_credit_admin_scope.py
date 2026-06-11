"""utils/api_credit_admin_scope.py — Cascade-scope filtering for the
Credit Admin domain.

Authored v10.518 Phase 3 Arc α Batch α9 — Credit Admin API.

Delegates the cascade walk to api_pipeline_scope.get_visible_staff_codes
and filters cases on rm_code. Same shape as api_lms_scope but WITHOUT
the analyst-override layer — credit-admin cases don't have an analyst
field in the same way LMS applications do.

Deliberate scope exclusion (Section 19.4 of PIPELINE_DOMAIN_AUDIT):
Credit-admin officers in the conditions list may be outside the
originating RM's cascade. If they are, they currently can't see the
case via list/detail through this endpoint. This is acceptable for α9
because operations officers typically have department-level access via
their role (Credit Admin / Operations Manager), which already widens
their cascade scope. If officer-override becomes necessary, it would
be a small follow-up.
"""
from __future__ import annotations

from typing import List, Dict, Any, Set


def filter_cases_by_visible_codes(
    cases: List[Dict[str, Any]],
    visible_codes: Set[str],
) -> List[Dict[str, Any]]:
    """Filter credit-admin cases by RM cascade scope.

    Returns cases where rm_code is in visible_codes. Admins (whose
    visible_codes span the whole roster) get all cases.

    Parameters
    ----------
    cases : list of dict
        Case records (typically CreditAdminManager().cases)
    visible_codes : set of str
        Caller's cascade scope from get_visible_staff_codes(user)
    """
    return [
        c for c in cases
        if str(c.get('rm_code', '') or '') in visible_codes
    ]


def is_case_in_scope(
    case: Dict[str, Any],
    visible_codes: Set[str],
) -> bool:
    """Single-case scope check (same logic as filter, for one case)."""
    if not case:
        return False
    rm_code = str(case.get('rm_code', '') or '')
    return bool(rm_code) and (rm_code in visible_codes)
