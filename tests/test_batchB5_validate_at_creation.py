"""Batch B5 — validation is the first gate at deal creation (Lead).

A newly created deal (stage 'Lead') must appear in the manager's validation
queue and be validatable — the first defense against ghost deals inflating
the pipeline. Previously validation began at 'Contacted', so new Leads never
surfaced.
"""
from utils.core import PipelineManager
from utils.api_pipeline_permissions import VALIDATION_STAGES


def test_new_lead_deal_appears_for_validation():
    pm = PipelineManager()
    pm.deals = [
        {"id": "D1", "stage": "Lead", "staff_code": "S1"},
        {"id": "D2", "stage": "Closed Lost", "staff_code": "S1"},
        {"id": "D3", "stage": "Proposal", "staff_code": "S1", "manager_validated": True},
    ]
    ids = {d["id"] for d in pm.get_pending_validations()}
    assert "D1" in ids          # new Lead now needs validation
    assert "D2" not in ids       # terminal excluded
    assert "D3" not in ids       # already validated


def test_lead_is_a_validation_stage():
    assert "Lead" in VALIDATION_STAGES
