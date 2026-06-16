"""Batch B15 — validated (assured) vs pending-assurance split.

Management anchors on validated deals; unvalidated active deals are surfaced
separately. The funnel is validated-only.
"""
from utils.api import _compute_pipeline_analytics


def test_headline_is_validated_pending_is_separate():
    deals = [
        {"stage": "Qualified", "deal_value": 10_000_000, "product_type": "Business Loan", "manager_validated": True},
        {"stage": "Qualified", "deal_value": 4_000_000,  "product_type": "Business Loan"},  # pending
    ]
    out = _compute_pipeline_analytics(deals)
    assert out["totals"]["total_value"] == 10_000_000     # validated only
    assert out["totals"]["pending_value"] == 4_000_000    # pending assurance
    assert out["pipelines"]["asset"]["value"] == 10_000_000
    assert out["pipelines"]["asset"]["pending_value"] == 4_000_000


def test_funnel_excludes_unvalidated():
    deals = [
        {"stage": "Negotiation", "deal_value": 9_000_000, "product_type": "Business Loan", "manager_validated": True},
        {"stage": "Lead",        "deal_value": 1_000_000, "product_type": "Business Loan"},  # unvalidated
    ]
    funnel = _compute_pipeline_analytics(deals)["funnel"]
    stages = {f["stage"] for f in funnel}
    assert "Negotiation" in stages      # validated -> shown
    assert "Lead" not in stages          # unvalidated -> excluded
