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
    "Director Consumer & Commercial Banking (CCB)",
    "Director Corporate & Investment Banking (CIB)",
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


# ─────────────────────────────────────────────────────────────────────
# Credit workflow state machine (v10.584)
# ─────────────────────────────────────────────────────────────────────
# HARDCODED: the transition graph + guards. Integrity-critical — a config
# edit must never let an unsigned offer reach disbursement. What the BANK
# configures (committee mode, attachment mode, which optional steps are
# required, offer-letter settings) is read from lms_config.json's
# `credit_workflow` section by get_credit_workflow_config() below.

import json as _json
from pathlib import Path as _Path

_CREDIT_WORKFLOW_DEFAULTS: Dict[str, Any] = {
    "committee_mode": "authority_tier",          # or "committee_voting"
    "signed_offer_attachment": "reference",      # or "file_upload"
    "require_line_manager_offer_validation": True,
    "require_analyst_confirmation": True,
    "credit_admin_two_layer_authorization": True,
    "offer_letter": {
        "template_label": "Letter of Offer",
        "validity_days": 14,
        "sla_days": 5,
    },
    # ── Department Analyst layer (P1 scaffold) ──────────────────────────────
    # DISABLED by default = zero behaviour change. P2+ reads this to wire the
    # earlier, segment-routed handoff, the RM edit-lock shift and auto stage
    # travel. Per-institution: Ecobank runs the layer; others may leave it off.
    "department_analyst": {
        "enabled": False,
        # The case routes to a Department Analyst on entering this stage (ahead
        # of the DCC); then to the Credit Analyst at the credit-analysis stage.
        "handoff_stage": "Department Credit Committee Review",
        "credit_analyst_handoff_stage": "Credit Analysis",
        # segment -> department-analyst role title (substring-matched like the
        # rest of the role handling).
        "segment_roles": {
            "consumer":   "Consumer Credit Analyst",
            "commercial": "Commercial Credit Analyst",
            "cib":        "CIB Credit Analyst",
        },
        "routing": "queue",            # all segment analysts see + pick (no assign)
        "can_decide": False,           # completeness + support only; no decision
        "required_attachments": ["Call-Back Memo"],
        "compliance_confirmation": {"pep_check": True},
        "auto_stage_travel": True,     # advance stages on real actions
    },
    # ── Self-pick (P1 scaffold) ─────────────────────────────────────────────
    # Credit analysts may pull unallocated cases so work never stalls when the
    # Chief Credit is away; department analysts pick from the segment queue.
    "self_pick": {
        "credit_analyst": True,
        "department_analyst": True,
    },
}


def get_credit_workflow_config() -> Dict[str, Any]:
    """Admin policy for the credit workflow. Falls back to hardcoded
    defaults if lms_config.json lacks the `credit_workflow` section.
    Reads the file directly (no core import) to stay cycle-free."""
    cfg = dict(_CREDIT_WORKFLOW_DEFAULTS)
    try:
        p = _Path(__file__).resolve().parent.parent / "data" / "lms_config.json"
        if p.exists():
            section = (_json.loads(p.read_text(encoding="utf-8")) or {}).get(
                "credit_workflow") or {}
            if isinstance(section, dict):
                cfg.update(section)
    except Exception:
        pass
    return cfg


# Explicit transition graph (defensible vs free-form). offer_signed and
# offer_validated each list multiple targets so the config toggles can skip
# optional steps — the endpoint guards enforce which target is legal given
# the bank's policy.
LMS_WORKFLOW_TRANSITIONS: Dict[str, Tuple[str, ...]] = {
    "submitted":                  ("assigned", "declined"),
    "assigned":                   ("info_requested", "approved", "declined",
                                   "referred_to_committee"),
    "info_requested":             ("assigned",),
    "referred_to_committee":      ("approved", "declined"),
    "approved":                   ("offer_issued",),
    "offer_issued":               ("offer_signed", "declined"),
    "offer_signed":               ("offer_validated", "analyst_confirmed",
                                   "credit_admin"),
    "offer_validated":            ("analyst_confirmed", "credit_admin"),
    "analyst_confirmed":          ("credit_admin",),
    "credit_admin":               ("ca_authorization_requested", "disbursed"),
    "ca_authorization_requested": ("ca_authorized",),
    "ca_authorized":              ("disbursed",),
    "returned":                   ("assigned",),
    "declined":                   (),
    "disbursed":                  (),
}


def is_valid_lms_transition(from_status: str, to_status: str) -> bool:
    """True if from_status -> to_status is an allowed workflow transition."""
    return to_status in LMS_WORKFLOW_TRANSITIONS.get(from_status, ())


def handoff_trigger_status(cfg: Dict[str, Any] = None) -> str:
    """The status at which the CALMS (credit-admin) case is created, given
    which optional post-approval steps the bank requires. Single source of
    truth so the routes and the frontend agree on where the handoff fires."""
    cfg = cfg or get_credit_workflow_config()
    if cfg.get("require_analyst_confirmation", True):
        return "analyst_confirmed"
    if cfg.get("require_line_manager_offer_validation", True):
        return "offer_validated"
    return "offer_signed"


def next_offer_status_after_sign(cfg: Dict[str, Any] = None) -> str:
    """After an offer is signed, the next required status per policy."""
    cfg = cfg or get_credit_workflow_config()
    if cfg.get("require_line_manager_offer_validation", True):
        return "offer_validated"
    if cfg.get("require_analyst_confirmation", True):
        return "analyst_confirmed"
    return "credit_admin"
