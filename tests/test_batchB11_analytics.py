"""Batch B11 (updated B15) — pipeline analytics aggregation.

Headline value is now validated-only (manager-assured), so active deals in
these fixtures carry manager_validated=True to keep the value assertions.
"""
from utils.api import _compute_pipeline_analytics

DEALS = [
    {"stage": "Lead",        "deal_value": 5_000_000,  "product_type": "Personal Loan", "manager_validated": True},
    {"stage": "Qualified",   "deal_value": 10_000_000, "product_type": "Business Loan", "manager_validated": True},
    {"stage": "Negotiation", "deal_value": 20_000_000, "product_type": "Business Loan", "manager_validated": True},
    {"stage": "Closed Won",  "deal_value": 8_000_000,  "product_type": "Personal Loan"},
    {"stage": "Closed Lost", "deal_value": 3_000_000,  "product_type": "Business Loan"},
    {"stage": "Qualified",   "deal_value": 2_000_000,  "product_type": "Current Account (CASA)", "manager_validated": True},
    {"stage": "Lead",        "deal_value": 1_000_000,  "product_type": "Fixed Deposit", "draft": True},
]


def test_totals_mirror_streamlit():
    t = _compute_pipeline_analytics(DEALS)["totals"]
    assert t["total_value"] == 37_000_000      # validated active, drafts excluded
    assert t["won_value"] == 8_000_000
    assert t["win_rate"] == 50.0
    assert t["active_count"] == 4
    assert t["won_count"] == 1 and t["lost_count"] == 1


def test_funnel_is_active_only_and_skips_empty():
    funnel = _compute_pipeline_analytics(DEALS)["funnel"]
    stages = {f["stage"]: f["count"] for f in funnel}
    assert stages.get("Qualified") == 2
    assert "Closed Won" not in stages
    assert all(f["count"] > 0 for f in funnel)


def test_by_category_present_and_sorted_by_value():
    cats = _compute_pipeline_analytics(DEALS)["by_category"]
    names = [c["category"] for c in cats]
    assert "Loan" in names
    values = [c["value"] for c in cats]
    assert values == sorted(values, reverse=True)
