"""utils/api_credit_admin_mutations.py — Payload validators for the
credit-admin mutation endpoints.

Authored v10.518 Phase 3 Arc α Batch α9 — Credit Admin API.

Same shape as api_pipeline_mutations / api_lms_mutations — validators
return (ok: bool, reason: str) tuples that endpoints translate to
HTTP 400 with the reason in the detail field.
"""
from __future__ import annotations

from typing import Dict, Any, Tuple


def validate_fulfill_condition_payload(payload: Dict[str, Any]) -> Tuple[bool, str]:
    """Validate fulfill-condition payload.

    Required:
    - condition_type (non-empty) — matches a condition's 'type' field
    - officer_name (non-empty) — recorded on the condition for audit
    """
    if not isinstance(payload, dict):
        return False, "Payload must be an object"

    condition_type = str(payload.get('condition_type', '') or '').strip()
    if not condition_type:
        return False, "Missing required field: condition_type"

    officer_name = str(payload.get('officer_name', '') or '').strip()
    if not officer_name:
        return False, "Missing required field: officer_name"

    return True, ""


def validate_disburse_payload(payload: Dict[str, Any]) -> Tuple[bool, str]:
    """Validate disburse-clearance payload.

    Required:
    - authority (non-empty) — decision-maker role/title for audit
    """
    if not isinstance(payload, dict):
        return False, "Payload must be an object"

    authority = str(payload.get('authority', '') or '').strip()
    if not authority:
        return False, "Missing required field: authority"

    return True, ""


def case_can_be_disbursed(case: Dict[str, Any]) -> Tuple[bool, str]:
    """Check if a case is in a state where disburse-clearance is valid.

    Returns (ok, reason) — endpoint uses reason as the 400 detail when
    blocked.

    Rules:
    - Case must exist (caller checks)
    - case.disbursed must be False (can't re-disburse)
    - case.all_conditions_met must be True (can't clear before
      conditions are met)
    """
    if not case:
        return False, "Case not found"

    if case.get('disbursed', False):
        return False, "Case is already disbursed; cannot re-clear"

    if not case.get('all_conditions_met', False):
        # Compute the unmet conditions for a helpful message
        unmet = [
            c.get('type', '?')
            for c in (case.get('conditions') or [])
            if c.get('required', True) and not c.get('fulfilled', False)
        ]
        return False, (
            "Cannot disburse — not all required conditions are met. "
            f"Unmet: {', '.join(unmet) if unmet else '(unknown)'}"
        )

    return True, ""


def case_can_have_condition_fulfilled(case: Dict[str, Any]) -> Tuple[bool, str]:
    """Check if a case accepts further condition fulfillment.

    Rules:
    - Case must exist
    - Case must not be disbursed (no edits to closed cases)
    """
    if not case:
        return False, "Case not found"

    if case.get('disbursed', False):
        return False, "Case is already disbursed; cannot modify conditions"

    return True, ""


def condition_exists_on_case(case: Dict[str, Any], condition_type: str) -> bool:
    """Helper: check if a condition with the given type exists on the case.

    Used by the endpoint BEFORE calling the manager method, so we can
    return a clear 400 ("Condition X not found on this case") rather
    than the manager method silently returning False.
    """
    if not case or not condition_type:
        return False
    for c in (case.get('conditions') or []):
        if str(c.get('type', '') or '').strip().lower() == condition_type.strip().lower():
            return True
    return False
