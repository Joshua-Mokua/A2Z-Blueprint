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
import json as _json
from pathlib import Path as _Path


# ── Credit work-pool visibility (admin-configurable) ────────────────────
# Beyond cascade + assigned-analyst, certain CREDIT-FUNCTION roles need to
# see the live credit work pool (e.g. a Credit Analyst seeing submitted
# applications so their line manager can assign them, and so they have
# visibility of the credit factory). WHICH roles, and WHICH statuses they
# see, varies by bank — so it is config, not hardcode. Defaults below ship
# a sensible Ecobank-shaped policy; lms_config.json -> pool_visibility
# overrides it. Matching is case-insensitive + lenient (substring), to align
# with the rest of the role handling (full role titles vary).
_POOL_VISIBILITY_DEFAULTS: Dict[str, Any] = {
    # Roles (substring match, case-insensitive) that see the credit pool.
    "roles": [
        "credit analyst",
        "credit administrator",
        "chief credit officer",
        "branch credit manager",
        "head of credit",
        "credit manager",
    ],
    # Application statuses considered part of the visible work pool.
    "statuses": [
        "submitted", "assigned", "info_requested",
        "referred_to_committee", "approved", "offer_issued",
        "offer_signed", "offer_validated", "analyst_confirmed",
    ],
}


def get_pool_visibility_config() -> Dict[str, Any]:
    """Admin policy for credit work-pool visibility. Falls back to the
    defaults above if lms_config.json lacks a `pool_visibility` section.
    Reads the file directly (no core import) to stay cycle-free, mirroring
    get_credit_workflow_config in api_lms_mutations."""
    cfg = {
        "roles": list(_POOL_VISIBILITY_DEFAULTS["roles"]),
        "statuses": list(_POOL_VISIBILITY_DEFAULTS["statuses"]),
    }
    try:
        p = _Path(__file__).resolve().parent.parent / "data" / "lms_config.json"
        if p.exists():
            section = (_json.loads(p.read_text(encoding="utf-8")) or {}).get(
                "pool_visibility") or {}
            if isinstance(section, dict):
                if isinstance(section.get("roles"), list):
                    cfg["roles"] = [str(r) for r in section["roles"]]
                if isinstance(section.get("statuses"), list):
                    cfg["statuses"] = [str(s) for s in section["statuses"]]
    except Exception:
        pass
    return cfg


def _role_sees_pool(role: str, pool_roles: List[str]) -> bool:
    """Lenient case-insensitive substring match — a caller's role grants
    pool visibility if any configured pool-role is a substring of it (or
    vice-versa), so full role titles like 'Credit Analyst - SME' still match."""
    rl = (role or "").strip().lower()
    if not rl:
        return False
    for pr in pool_roles:
        prl = str(pr).strip().lower()
        if prl and (prl in rl or rl in prl):
            return True
    return False


def _analyst_segment(role: str) -> str:
    """Segment ('consumer' / 'commercial' / 'cib') for a segment-specific
    Department Analyst role; '' for any other role (no segment constraint).
    Substring + case-insensitive, matching the rest of the role handling."""
    rl = (role or "").strip().lower()
    if "consumer credit analyst" in rl:
        return "consumer"
    if "commercial credit analyst" in rl:
        return "commercial"
    if "cib credit analyst" in rl:
        return "cib"
    return ""


def _app_segment(app: Dict[str, Any]) -> str:
    """Segment of an application, derived from its client_type
    ('consumer' / 'commercial' / 'cib'); '' when unknown (e.g. legacy apps
    created before client_type was stamped — deliberately NOT hidden)."""
    ct = str(app.get("client_type", "") or "").strip().lower()
    if not ct:
        return ""
    if "consumer" in ct:
        return "consumer"
    if "commercial" in ct:
        return "commercial"
    if ct == "cib" or "corporate" in ct or "investment" in ct:
        return "cib"
    return ""


def filter_apps_by_visibility(
    apps: List[Dict[str, Any]],
    visible_codes: Set[str],
    caller_staff_code: str = "",
    caller_role: str = "",
) -> List[Dict[str, Any]]:
    """Filter LMS applications by cascade scope OR analyst assignment OR
    (for credit-function roles) the admin-configured credit work pool.

    Returns apps where ANY of:
    - rm_code is in visible_codes (RM-cascade scope), OR
    - analyst.code matches caller_staff_code (analyst override), OR
    - caller_role is a configured pool role AND the app's status is in the
      configured pool statuses (credit work-pool visibility).

    Parameters
    ----------
    apps : list of dict
        Application records (typically LoanApplicationManager().apps)
    visible_codes : set of str
        From get_visible_staff_codes(user) — the caller's cascade scope
    caller_staff_code : str, optional
        Caller's own staff code. Used for the analyst override.
    caller_role : str, optional
        Caller's role. Used for credit work-pool visibility (config-driven).
        Empty disables the pool branch.

    Returns
    -------
    list of dict
        Filtered subset of apps that the caller can see.
    """
    pool_cfg = get_pool_visibility_config()
    pool_ok = _role_sees_pool(caller_role, pool_cfg["roles"])
    pool_statuses = {s.strip().lower() for s in pool_cfg["statuses"]}
    caller_segment = _analyst_segment(caller_role)  # '' unless segment-specific

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
        if pool_ok:
            status = str(a.get('status', '') or '').strip().lower()
            if status in pool_statuses:
                # Segment-specific Department Analysts (Consumer / Commercial /
                # CIB Credit Analyst) see ONLY their segment's cases. Cases whose
                # segment is unknown (legacy, no client_type) are not hidden.
                if caller_segment:
                    seg = _app_segment(a)
                    if seg and seg != caller_segment:
                        continue
                visible.append(a)
                continue
    return visible


def is_app_in_scope(
    app: Dict[str, Any],
    visible_codes: Set[str],
    caller_staff_code: str = "",
    caller_role: str = "",
) -> bool:
    """Single-application scope check (same logic as filter, for one app).

    Used by endpoint handlers that need to scope-check a specific app
    (detail/update/assign/decision) rather than filter a list. Mirrors
    filter_apps_by_visibility including the credit work-pool branch, so a
    credit role that sees a pool app in the list can also open it.

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
    if caller_role:
        pool_cfg = get_pool_visibility_config()
        if _role_sees_pool(caller_role, pool_cfg["roles"]):
            status = str(app.get('status', '') or '').strip().lower()
            if status in {s.strip().lower() for s in pool_cfg["statuses"]}:
                return True
    return False
