"""Batch B18 — create form: segment/sector + product-class initial stages.

Backend slice:
  * PipelineDealCreate accepts segment + sector (auto-persisted via model_dump).
  * validate_create_payload accepts configured stage_flows stages (e.g. the
    loan-flow 'Application'), so the create form can offer per-class stages.
Run scripts/add_stage_flows.py first so stage_flows is in config.
"""
from utils.api_pipeline_models import PipelineDealCreate
from utils.api_pipeline_mutations import validate_create_payload

_BASE = {
    "client_name": "Test Client",
    "staff_code": "300731",
    "staff_name": "Frank Wanyama",
    "deal_value": 1_000_000,
    "product_type": "Business Loan",
}


def test_model_accepts_segment_and_sector():
    m = PipelineDealCreate(
        **_BASE, stage="Lead", segment="Affluent", sector="Manufacturing",
    )
    assert m.segment == "Affluent"
    assert m.sector == "Manufacturing"
    dumped = m.model_dump()
    assert dumped["segment"] == "Affluent"
    assert dumped["sector"] == "Manufacturing"


def test_create_accepts_configured_flow_stage():
    ok, reason = validate_create_payload({**_BASE, "stage": "Application"})
    assert ok, reason


def test_create_still_rejects_unknown_stage():
    ok, _ = validate_create_payload({**_BASE, "stage": "Totally Made Up Stage"})
    assert not ok
