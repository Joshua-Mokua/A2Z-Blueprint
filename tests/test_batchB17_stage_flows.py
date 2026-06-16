"""Batch B17 — per-product-class stage flows from admin config.

Loan (asset) and Deposit (liability) leads follow DISTINCT stage flows, sourced
from pipeline_settings.json stage_flows (run scripts/add_stage_flows.py first).
"""
from utils.api import _stage_flow_for


def test_asset_flow_has_loan_specific_stages():
    f = _stage_flow_for("Business Loan")
    assert "Application" in f
    assert "Credit Assessment" in f


def test_liability_flow_is_distinct_from_asset():
    asset = _stage_flow_for("Business Loan")
    liability = _stage_flow_for("Fixed Deposit")
    assert asset != liability
    assert "Credit Assessment" not in liability   # loan-only stage


def test_every_flow_starts_at_lead_and_ends_terminal():
    for product in ("Business Loan", "Fixed Deposit", "Bancassurance"):
        f = _stage_flow_for(product)
        assert f[0] == "Lead"
        assert f[-1] == "Closed Lost"
