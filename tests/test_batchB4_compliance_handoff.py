"""Batch B4 — advancing to 'Compliance' triggers the LMS handoff.

The frontend advance dropdown offers 'Compliance' and shows
'Loan application created'. The backend trigger set must include it, else
the toast lies and no application is created (no path from RM to credit).
"""
from utils.api_pipeline_mutations import (
    LMS_DEFERRED_STAGES, is_lms_handoff_transition,
)


def test_compliance_in_deferred_stages():
    assert "Compliance" in LMS_DEFERRED_STAGES


def test_advance_to_compliance_is_handoff():
    assert is_lms_handoff_transition("Negotiation", "Compliance") is True


def test_non_handoff_transitions_unchanged():
    assert is_lms_handoff_transition("Qualified", "Proposal") is False
    assert is_lms_handoff_transition("Lead", "Contacted") is False


def test_config_credit_stages_still_handoff():
    assert is_lms_handoff_transition("Proposal", "Credit Review") is True
