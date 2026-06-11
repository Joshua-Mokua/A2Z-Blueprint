"""utils/api_lms_mutations.py — Payload validators and constants for
the LMS mutation endpoints.

Authored v10.515 Phase 3 Arc α Batch α8 — LMS API.

Pattern mirrors api_pipeline_mutations.py — every validator returns
(ok: bool, reason: str), and the endpoint handler translates
non-ok results to HTTP 400 with the reason in the detail field.

Status guardrails are exported as module-level constants so they're
visible to:
- The endpoint handlers (enforcement)
- The api_lms_permissions module (permission resolution)
- Future tests and gates
"""
from __future__ import annotations

from typing import Dict, Any, Tuple, Set


# ─────────────────────────────────────────────────────────────────────
# Status guardrails
# ─────────────────────────────────────────────────────────────────────


# PUT update permitted only for these statuses. After a decision is
# recorded (approved/declined/returned) the application is considered
# resolved and field edits would corrupt the audit trail.
STATUSES_PERMITTING_UPDATE: Set[str] = {'submitted', 'assigned'}

# Decision recording permitted only for these statuses. Re-deciding a
# resolved application would also corrupt the audit trail; if a
# decision needs reversal, that's a separate operation (not in α8).
STATUSES_PERMITTING_DECISION: Set[str] = {'submitted', 'assigned'}

# Analyst assignment permitted only from 'submitted'. Re-assigning an
# already-assigned application would lose the prior analyst's audit
# trail without an explicit "reassign" operation (not in α8).
STATUSES_PERMITTING_ASSIGN: Set[str] = {'submitted'}


# ─────────────────────────────────────────────────────────────────────
# Decision verdict vocabulary
# ─────────────────────────────────────────────────────────────────────


# Case-insensitive set of accepted verdict values. The verdict input
# is normalized via normalize_verdict() to one of the canonical three:
# {'approved', 'declined', 'returned'}. Both the short form
# (approve/decline/return) and the long form are accepted to match
# LoanApplicationManager.record_decision's own input tolerance.
ALLOWED_DECISION_VERDICTS: Set[str] = {
    'approve', 'approved',
    'decline', 'declined',
    'return',  'returned',
}

# Canonical verdicts that downstream consumers (audit events, status
# transitions) should see.
CANONICAL_VERDICTS: Set[str] = {'approved', 'declined', 'returned'}


# Common decision-making authority roles (informational only — no
# enforcement here; is_manager() at endpoint level enforces who CAN
# call the decision endpoint). This list helps frontend offer a
# dropdown of common choices but accepts free-text too.
COMMON_AUTHORITY_ROLES = (
    "Branch Manager",
    "Branch Credit Manager",
    "Credit Manager",
    "Head Of Retail",
    "Head Of SME",
    "Head Of Corporate",
    "Director Retail Banking",
    "Director Commercial Banking",
    "Managing Director",
)


# ─────────────────────────────────────────────────────────────────────
# Updatable fields whitelist
# ─────────────────────────────────────────────────────────────────────


# Fields that PUT /api/lms/applications/{id} is permitted to modify.
# Used by validate_update_payload to reject silently-ignored keys
# and provide a helpful error message if the caller supplies wrong ones.
UPDATABLE_FIELDS: Set[str] = {
    'docs_submitted',
    'docs_required',
    'completeness_score',
    'compliance_flag',
    'compliance_type',
    'appraisal_notes',
    'is_repeat_borrower',
    'clean_repayment_history',
}


# ─────────────────────────────────────────────────────────────────────
# Validators
# ─────────────────────────────────────────────────────────────────────


def validate_assign_payload(payload: Dict[str, Any]) -> Tuple[bool, str]:
    """Validate analyst assignment payload.

    Required: analyst_code (non-empty), analyst_name (non-empty).
    Both fields are referenced by audit downstream — without them,
    the operation has no traceability.
    """
    if not isinstance(payload, dict):
        return False, "Payload must be an object"
    analyst_code = str(payload.get('analyst_code', '') or '').strip()
    analyst_name = str(payload.get('analyst_name', '') or '').strip()
    if not analyst_code:
        return False, "Missing required field: analyst_code"
    if not analyst_name:
        return False, "Missing required field: analyst_name"
    return True, ""


def validate_update_payload(payload: Dict[str, Any]) -> Tuple[bool, str]:
    """Validate PUT update payload.

    Rules:
    - Payload must be a dict
    - At least one updatable field must be present (else this is a no-op)
    - completeness_score, if present, must be a number 0-100
    - Any other field types are passed through to LoanApplicationManager.update()
      without strict shape validation (extra="allow" upstream in Pydantic)
    """
    if not isinstance(payload, dict):
        return False, "Payload must be an object"

    present_updatable = [
        k for k in payload
        if k in UPDATABLE_FIELDS and payload[k] is not None
    ]
    if not present_updatable:
        return False, (
            f"No updatable fields provided. "
            f"Permitted fields: {sorted(UPDATABLE_FIELDS)}"
        )

    # Completeness score range check
    if 'completeness_score' in payload and payload['completeness_score'] is not None:
        try:
            score = float(payload['completeness_score'])
            if score < 0 or score > 100:
                return False, "completeness_score must be in range 0-100"
        except (TypeError, ValueError):
            return False, "completeness_score must be a number"

    return True, ""


def validate_decision_payload(payload: Dict[str, Any]) -> Tuple[bool, str]:
    """Validate decision recording payload.

    Required:
    - verdict (case-insensitive, in ALLOWED_DECISION_VERDICTS)
    - authority (non-empty)

    Optional but recommended:
    - reason (especially for declined/returned)
    - conditions (especially for conditional approvals)
    - comments
    """
    if not isinstance(payload, dict):
        return False, "Payload must be an object"

    verdict_raw = str(payload.get('verdict', '') or '').strip().lower()
    if not verdict_raw:
        return False, "Missing required field: verdict"
    if verdict_raw not in ALLOWED_DECISION_VERDICTS:
        return False, (
            f"verdict must be one of: {sorted(ALLOWED_DECISION_VERDICTS)} "
            f"(got '{verdict_raw}')"
        )

    authority = str(payload.get('authority', '') or '').strip()
    if not authority:
        return False, "Missing required field: authority"

    # Optional: if conditions provided, must be a list
    conditions = payload.get('conditions')
    if conditions is not None and not isinstance(conditions, list):
        return False, "conditions must be a list of strings"

    return True, ""


# ─────────────────────────────────────────────────────────────────────
# Verdict normalization
# ─────────────────────────────────────────────────────────────────────


_VERDICT_NORMALIZATION: Dict[str, str] = {
    'approve':  'approved',
    'approved': 'approved',
    'decline':  'declined',
    'declined': 'declined',
    'return':   'returned',
    'returned': 'returned',
}


def normalize_verdict(verdict: str) -> str:
    """Map a verdict input to its canonical form.

    Returns one of: 'approved' | 'declined' | 'returned'.
    Unknown verdicts return the lowercase input unchanged — the
    validator should have rejected those before reaching here, so this
    is a defensive fallback rather than a silent passthrough vector.
    """
    v = str(verdict or '').strip().lower()
    return _VERDICT_NORMALIZATION.get(v, v)
