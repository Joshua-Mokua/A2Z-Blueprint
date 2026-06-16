"""Batch B16 — advance accepts the frontend's `target_stage` field.

The React client sends `target_stage`; the backend model required `new_stage`,
so advancing failed with a bare "Field required". The model now accepts both.
"""
from utils.api_pipeline_models import PipelineDealAdvance


def test_advance_accepts_target_stage_from_frontend():
    a = PipelineDealAdvance(**{"target_stage": "Negotiation", "note": "customer agreed"})
    assert a.new_stage == "Negotiation"
    assert a.note == "customer agreed"


def test_advance_still_accepts_new_stage():
    a = PipelineDealAdvance(**{"new_stage": "Qualified"})
    assert a.new_stage == "Qualified"
