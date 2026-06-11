"""utils/api_lms_scope.py — Cascade-scope filtering for the LMS domain.

Authored v10.515 Phase 3 Arc α Batch α8 — LMS API.

Purpose
-------
Filters LoanApplication records to those the caller can see, based on
two signals:
1. RM cascade — applications where `rm_code` is in the caller's
   visible-staff-codes set (per get_visible_staff_codes in
   api_pipeline_scope.py). This covers RMs seeing their own apps and
   managers seeing apps from staff under them.
2. Analyst override — applications where the caller IS the assigned
   analyst (analyst.code matches), regardless of cascade. Without this
   override, credit analysts at HQ would not see applications from
   branch RMs because their cascade typically doesn't span branches.

Doctrine note
-------------
This module DELEGATES the cascade walk to api_pipeline_scope. The
cascade-tree logic is canonical there and reused here rather than
duplicated. The α2 batch (commit 9778b2a) established that pattern;
α8 just adds the analyst-override layer on top.

The function get_visible_staff_codes returns codes (not deals/apps),
so it's domain-agnostic. The filter functions here apply those codes
against the application records' `rm_code` field.
"""
from __future__ import annotations

from typing import List, Dict, Any, Set


def filter_apps_by_visibility(
    apps: List[Dict[str, Any]],
    visible_codes: Set[str],
    caller_staff_code: str = "",
) -> List[Dict[str, Any]]:
    """Filter LMS applications by cascade scope OR analyst assignment.

    Returns apps where EITHER:
    - rm_code is in visible_codes (RM-cascade scope), OR
    - analyst.code matches caller_staff_code (analyst override)

    Parameters
    ----------
    apps : list of dict
        Application records (typically LoanApplicationManager().apps)
    visible_codes : set of str
        From get_visible_staff_codes(user) — the caller's cascade scope
    caller_staff_code : str, optional
        Caller's own staff code. Used for the analyst override. Empty
        string disables the override (the cascade filter alone applies).

    Returns
    -------
    list of dict
        Filtered subset of apps that the caller can see.
    """
    visible: List[Dict[str, Any]] = []
    for a in apps:
        rm_code = str(a.get('rm_code', '') or '')
        if rm_code and rm_code in visible_codes:
            visible.append(a)
            continue
        if caller_staff_code:
            analyst = a.get('analyst') or {}
            if isinstance(analyst, dict):
                analyst_code = str(analyst.get('code', '') or '')
                if analyst_code and analyst_code == caller_staff_code:
                    visible.append(a)
                    continue
    return visible


def is_app_in_scope(
    app: Dict[str, Any],
    visible_codes: Set[str],
    caller_staff_code: str = "",
) -> bool:
    """Single-application scope check (same logic as filter, for one app).

    Used by endpoint handlers that need to scope-check a specific app
    (detail/update/assign/decision) rather than filter a list.

    Returns True iff the caller can see this application.
    """
    if not app:
        return False
    rm_code = str(app.get('rm_code', '') or '')
    if rm_code and rm_code in visible_codes:
        return True
    if caller_staff_code:
        analyst = app.get('analyst') or {}
        if isinstance(analyst, dict):
            analyst_code = str(analyst.get('code', '') or '')
            if analyst_code and analyst_code == caller_staff_code:
                return True
    return False
