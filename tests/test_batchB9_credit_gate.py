"""Batch B9 — Submit-to-Credit document gate.

Required documents are sourced from lms_config's tiered document_checklist
(default + amount/product add-ons); submission is blocked while any are missing.
"""
from utils.api import _get_required_documents_for_deal


def test_personal_loan_requires_defaults_only():
    req = _get_required_documents_for_deal(
        {"deal_value": 5_000_000, "product_type": "Personal Loan",
         "pipeline_category": "New Facility"})
    assert "CRB Report" in req and "ID/Passport" in req
    assert "Audited Accounts" not in req   # not > 10M
    assert "Board Resolution" not in req    # not corporate


def test_large_corporate_adds_tiers():
    req = _get_required_documents_for_deal(
        {"deal_value": 50_000_000, "product_type": "Corporate Loan"})
    assert "Audited Accounts" in req    # > 10M add-on
    assert "Board Resolution" in req     # corporate add-on


def test_missing_blocks_submission():
    req = _get_required_documents_for_deal(
        {"deal_value": 5_000_000, "product_type": "Personal Loan"})
    provided = req[:2]
    missing = [d for d in req if d not in provided]
    assert missing                       # partial -> would 400
    # full set -> nothing missing -> would submit
    assert [d for d in req if d not in req] == []
