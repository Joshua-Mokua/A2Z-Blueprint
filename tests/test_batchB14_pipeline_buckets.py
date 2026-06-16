"""Batch B14 (updated B15) — asset/liability/insurance/other split from admin
product_catalogue. Headline value is validated-only; pending shown separately.
"""
from utils.api import _classify_product, _compute_pipeline_analytics


def test_classify_from_admin_catalogue():
    assert _classify_product("Business Loan") == "asset"
    assert _classify_product("Fixed Deposit") == "liability"
    assert _classify_product("Motor Comprehensive") == "insurance"
    assert _classify_product("Bancassurance") == "insurance"   # now in config
    assert _classify_product("Mobile Banking") == "other"
    assert _classify_product("Treasury Bonds") == "other"
    assert _classify_product("Credit Card") == "other"
    assert _classify_product("Mortgage / Home Loan") == "asset"
    assert _classify_product("Current Account (CASA)") == "liability"


def test_validated_is_headline_pending_separate():
    deals = [
        {"stage": "Lead", "deal_value": 6_000_000,  "product_type": "Business Loan", "manager_validated": True},
        {"stage": "Lead", "deal_value": 50_000_000, "product_type": "Fixed Deposit", "manager_validated": True},
        {"stage": "Lead", "deal_value": 230_000,    "product_type": "Bancassurance"},  # unvalidated
    ]
    p = _compute_pipeline_analytics(deals)["pipelines"]
    assert p["asset"]["value"] == 6_000_000          # assured
    assert p["liability"]["value"] == 50_000_000     # assured
    assert p["insurance"]["value"] == 0              # not yet validated
    assert p["insurance"]["pending_value"] == 230_000  # pending assurance


def test_other_bucket_has_drilldown():
    deals = [
        {"stage": "Lead", "deal_value": 1_000_000, "product_type": "Mobile Banking", "manager_validated": True},
        {"stage": "Lead", "deal_value": 2_000_000, "product_type": "Treasury Bonds", "manager_validated": True},
    ]
    other = _compute_pipeline_analytics(deals)["pipelines"]["other"]
    subs = {b["subclass"] for b in other["breakdown"]}
    assert "Transactional" in subs and "Investments" in subs
