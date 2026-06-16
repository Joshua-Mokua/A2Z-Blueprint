"""Phase 4-3 — coverage ratio + security classification."""
import json
from decimal import Decimal
from pathlib import Path
import pytest
from utils.collateral_coverage import (
    CreditPolicyMatrix, compute_coverage_ratio, classify_security, assess_facility,
    UNSECURED, PARTIALLY, FULLY, OVER,
)


@pytest.fixture
def matrix(tmp_path):
    p = tmp_path / "credit_policy_matrix.json"
    p.write_text(json.dumps({
        "required_coverage_pct": {
            "Cash / Fixed Deposit": 100, "Residential Property": 125,
            "Commercial Property": 120, "Motor Vehicle": 130,
            "Debenture": 150, "Stock / Inventory": 150,
        },
        "over_secured_multiple": 1.25,
        "valuation_max_age_days": 365,
    }), encoding="utf-8")
    return CreditPolicyMatrix(p)


def test_required_ratio_lookup(matrix):
    assert matrix.required_ratio("Residential Property") == Decimal("1.25")
    assert matrix.required_ratio("Debenture") == Decimal("1.50")
    assert matrix.required_ratio("Unknown") is None


def test_required_ratio_for_conservative_max(matrix):
    # multiple types -> highest required ratio applies
    r = matrix.required_ratio_for(["Residential Property", "Debenture"])
    assert r == Decimal("1.50")
    # explicit override wins
    r2 = matrix.required_ratio_for(["Residential Property"], subtype_override="Motor Vehicle")
    assert r2 == Decimal("1.30")
    # nothing known -> never below par
    assert matrix.required_ratio_for(["Mystery"]) == Decimal("1.0")


def test_compute_coverage_ratio_basic():
    # 130M FSV against 100M facility -> 1.30
    linked = [{"forced_sale_value_kes": 130_000_000, "collateral_type": "Motor Vehicle"}]
    assert compute_coverage_ratio(100_000_000, linked) == Decimal("1.3000")


def test_coverage_allocation_cap():
    # allocated value caps the contribution below FSV
    linked = [{"forced_sale_value_kes": 200_000_000, "allocated_value_kes": 120_000_000,
               "collateral_type": "Commercial Property"}]
    assert compute_coverage_ratio(100_000_000, linked) == Decimal("1.2000")


def test_coverage_zero_facility_is_zero():
    assert compute_coverage_ratio(0, [{"forced_sale_value_kes": 1}]) == Decimal("0")


def test_classify_gradient():
    om = Decimal("1.25")
    assert classify_security(Decimal("0"),    Decimal("1.25"), om) == UNSECURED
    assert classify_security(Decimal("1.10"), Decimal("1.25"), om) == PARTIALLY
    assert classify_security(Decimal("1.25"), Decimal("1.25"), om) == FULLY
    assert classify_security(Decimal("1.50"), Decimal("1.25"), om) == FULLY   # == req*1.25 boundary
    assert classify_security(Decimal("1.60"), Decimal("1.25"), om) == OVER


def test_assess_facility_end_to_end(matrix):
    # Residential, required 125%. 120M FSV / 100M = 1.20 -> partially.
    a = assess_facility(100_000_000,
                        [{"forced_sale_value_kes": 120_000_000, "collateral_type": "Residential Property"}],
                        matrix=matrix)
    assert a["required_ratio"] == 1.25
    assert a["coverage_ratio"] == 1.20
    assert a["security_classification"] == PARTIALLY

    # add more collateral -> 160M / 100M = 1.60 -> over (1.60 > 1.25*1.25=1.5625)
    a2 = assess_facility(100_000_000, [
        {"forced_sale_value_kes": 120_000_000, "collateral_type": "Residential Property"},
        {"forced_sale_value_kes": 40_000_000,  "collateral_type": "Residential Property"},
    ], matrix=matrix)
    assert a2["coverage_ratio"] == 1.60
    assert a2["security_classification"] == OVER


def test_assess_no_collateral_is_unsecured(matrix):
    a = assess_facility(100_000_000, [], matrix=matrix)
    assert a["coverage_ratio"] == 0.0
    assert a["security_classification"] == UNSECURED


def test_native_currency_normalized(matrix):
    # FSV given in native USD should normalize via fx_engine (uses real
    # data/fx_rates.json USD mid). We only assert it produced a positive ratio.
    linked = [{"forced_sale_value": 1_000_000, "currency": "USD", "collateral_type": "Commercial Property"}]
    cov = compute_coverage_ratio(100_000_000, linked)
    assert cov > 0
