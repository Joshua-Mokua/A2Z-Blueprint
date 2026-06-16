"""Batch B14 — analytics split into asset / liability / insurance / other,
classification sourced from pipeline_settings.json product_catalogue (admin
config). Closes the bug where loans + deposits were summed into one total.
"""
from utils.api import _classify_product, _compute_pipeline_analytics


def test_classify_from_admin_catalogue():
    assert _classify_product("Business Loan") == "asset"
    assert _classify_product("Fixed Deposit") == "liability"
    assert _classify_product("Motor Comprehensive") == "insurance"
    assert _classify_product("Mobile Banking") == "other"        # Transactional
    assert _classify_product("Treasury Bonds") == "other"        # Investments
    # config wins over keywords
    assert _classify_product("Credit Card") == "other"           # not 'asset'
    assert _classify_product("Credit Life") == "insurance"
    # naming drift still classifies
    assert _classify_product("Mortgage / Home Loan") == "asset"
    assert _classify_product("Current Account (CASA)") == "liability"


def test_asset_and_liability_are_separated():
    deals = [
        {"stage": "Lead", "deal_value": 6_000_000,  "product_type": "Business Loan"},
        {"stage": "Lead", "deal_value": 50_000_000, "product_type": "Fixed Deposit"},
    ]
    p = _compute_pipeline_analytics(deals)["pipelines"]
    assert p["asset"]["value"] == 6_000_000
    assert p["liability"]["value"] == 50_000_000
    assert p["asset"]["label"] == "Asset Pipeline"
    assert p["liability"]["label"] == "Liability Pipeline"


def test_other_bucket_has_drilldown():
    deals = [
        {"stage": "Lead", "deal_value": 1_000_000, "product_type": "Mobile Banking"},
        {"stage": "Lead", "deal_value": 2_000_000, "product_type": "Treasury Bonds"},
    ]
    other = _compute_pipeline_analytics(deals)["pipelines"]["other"]
    subs = {b["subclass"] for b in other["breakdown"]}
    assert "Transactional" in subs and "Investments" in subs
