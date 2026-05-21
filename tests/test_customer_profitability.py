"""tests/test_customer_profitability.py — Standard #21 tests (v5.45).

Two test groups:

  1. Unit tests pinning the engine's contract:
       - calculate_customer_pnl returns spec-mandated keys
       - PBT math correctness (revenue - direct - indirect)
       - pbt_margin = pbt / total_revenue, None when revenue ≤ 0
       - All four allocation methods (equal/revenue/asset/activity)
       - Defensive contract (unknown customer, bad inputs)
       - Decimal precision at KES-scale (no float drift)
       - meta block traceability
       - Persistence helpers

  2. Excel-match harness:
       - test_excel_match_within_half_percent runs every fixture in
         tests/fixtures/customer_pnl_scenarios.json. Asserts
         |actual_pbt - expected_pbt| / |expected_pbt| ≤ 0.005
         (the spec's ≤0.5% bar) for ≥99.5% of cases.
         Writes customer_pnl_excel_match_results.json for G32.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest


ROOT = Path(__file__).parent.parent
FIXTURES = ROOT / "tests" / "fixtures" / "customer_pnl_scenarios.json"
RESULTS_FILE = ROOT / "customer_pnl_excel_match_results.json"


class TestStandard21Files:
    def test_engine_module_exists(self):
        assert (ROOT / "utils" / "customer_profitability.py").exists()

    def test_fixtures_exist(self):
        assert FIXTURES.exists()
        data = json.loads(FIXTURES.read_text())
        assert isinstance(data, list) and len(data) >= 20


@pytest.fixture
def basic_engine():
    from utils.customer_profitability import CustomerProfitabilityEngine
    customers = {"C100": {"cif": "C100", "segment": "Corporate"}}
    revenue = {("C100", "2026-04"): {
        "interest_income": Decimal("500000"),
        "fee_income":      Decimal("80000"),
        "other_income":    Decimal("20000"),
    }}
    direct = {("C100", "2026-04"): {
        "interest_expense":     Decimal("180000"),
        "loan_loss_provisions": Decimal("25000"),
        "transaction_costs":    Decimal("8000"),
    }}
    return CustomerProfitabilityEngine(
        customer_lookup_fn=lambda c: customers.get(c),
        revenue_fn=lambda c, p: revenue.get((c, p), {}),
        direct_costs_fn=lambda c, p: direct.get((c, p), {}),
        overhead_pool_fn=lambda p: Decimal("100000"),
        allocation_inputs_fn=lambda c, p: {
            "my_revenue": 600000, "total_revenue": 698501, "customer_count": 4,
        },
        allocation_method="revenue_weighted",
    )


class TestSpecContract:
    def test_returns_pbt(self, basic_engine):
        r = basic_engine.calculate_customer_pnl("C100", "2026-04")
        assert "pbt" in r

    def test_returns_pbt_margin(self, basic_engine):
        r = basic_engine.calculate_customer_pnl("C100", "2026-04")
        assert "pbt_margin" in r

    def test_returns_revenue_dict(self, basic_engine):
        r = basic_engine.calculate_customer_pnl("C100", "2026-04")
        assert isinstance(r["revenue"], dict)
        assert "interest_income" in r["revenue"]

    def test_returns_direct_costs_dict(self, basic_engine):
        r = basic_engine.calculate_customer_pnl("C100", "2026-04")
        assert "interest_expense" in r["direct_costs"]

    def test_returns_indirect_costs(self, basic_engine):
        r = basic_engine.calculate_customer_pnl("C100", "2026-04")
        assert "allocated_overhead" in r["indirect_costs"]


class TestPBTMath:
    def test_pbt_equals_revenue_minus_costs(self, basic_engine):
        r = basic_engine.calculate_customer_pnl("C100", "2026-04")
        # Within ±0.01 due to 2dp rounding on the components
        computed = r["total_revenue"] - r["total_direct_costs"] - r["total_indirect_costs"]
        assert abs(r["pbt"] - computed) < 0.02

    def test_total_revenue_sums_components(self, basic_engine):
        r = basic_engine.calculate_customer_pnl("C100", "2026-04")
        assert r["total_revenue"] == sum(r["revenue"].values())

    def test_total_direct_sums_components(self, basic_engine):
        r = basic_engine.calculate_customer_pnl("C100", "2026-04")
        assert r["total_direct_costs"] == sum(r["direct_costs"].values())

    def test_pbt_margin_equals_pbt_over_revenue(self, basic_engine):
        r = basic_engine.calculate_customer_pnl("C100", "2026-04")
        expected = round(r["pbt"] / r["total_revenue"], 4)
        assert abs(r["pbt_margin"] - expected) < 0.0001


class TestZeroRevenueHandling:
    def test_zero_revenue_margin_is_none(self):
        from utils.customer_profitability import CustomerProfitabilityEngine
        eng = CustomerProfitabilityEngine(
            customer_lookup_fn=lambda c: {"cif": c},
            revenue_fn=lambda c, p: {"interest_income": Decimal("0")},
            direct_costs_fn=lambda c, p: {"interest_expense": Decimal("100")},
            overhead_pool_fn=lambda p: Decimal("0"),
            allocation_inputs_fn=lambda c, p: {},
        )
        r = eng.calculate_customer_pnl("C", "2026-04")
        assert r["pbt_margin"] is None

    def test_zero_revenue_pbt_still_computed(self):
        from utils.customer_profitability import CustomerProfitabilityEngine
        eng = CustomerProfitabilityEngine(
            customer_lookup_fn=lambda c: {"cif": c},
            revenue_fn=lambda c, p: {"interest_income": Decimal("0")},
            direct_costs_fn=lambda c, p: {"interest_expense": Decimal("100")},
            overhead_pool_fn=lambda p: Decimal("0"),
            allocation_inputs_fn=lambda c, p: {},
        )
        r = eng.calculate_customer_pnl("C", "2026-04")
        assert r["pbt"] == -100.0


class TestAllocationMethods:
    def test_revenue_weighted(self):
        from utils.customer_profitability import CustomerProfitabilityEngine
        eng = CustomerProfitabilityEngine(
            customer_lookup_fn=lambda c: {"cif": c},
            revenue_fn=lambda c, p: {"interest_income": Decimal("100000")},
            direct_costs_fn=lambda c, p: {},
            overhead_pool_fn=lambda p: Decimal("100000"),
            allocation_inputs_fn=lambda c, p: {"my_revenue": 100000, "total_revenue": 1000000},
            allocation_method="revenue_weighted",
        )
        r = eng.calculate_customer_pnl("C", "2026-04")
        assert r["indirect_costs"]["allocated_overhead"] == 10000.0

    def test_equal_per_customer(self):
        from utils.customer_profitability import CustomerProfitabilityEngine
        eng = CustomerProfitabilityEngine(
            customer_lookup_fn=lambda c: {"cif": c},
            revenue_fn=lambda c, p: {"interest_income": Decimal("100000")},
            direct_costs_fn=lambda c, p: {},
            overhead_pool_fn=lambda p: Decimal("100000"),
            allocation_inputs_fn=lambda c, p: {"customer_count": 10},
            allocation_method="equal_per_customer",
        )
        r = eng.calculate_customer_pnl("C", "2026-04")
        assert r["indirect_costs"]["allocated_overhead"] == 10000.0

    def test_asset_weighted(self):
        from utils.customer_profitability import CustomerProfitabilityEngine
        eng = CustomerProfitabilityEngine(
            customer_lookup_fn=lambda c: {"cif": c},
            revenue_fn=lambda c, p: {"interest_income": Decimal("50000")},
            direct_costs_fn=lambda c, p: {},
            overhead_pool_fn=lambda p: Decimal("200000"),
            allocation_inputs_fn=lambda c, p: {"my_assets": 50_000_000, "total_assets": 1_000_000_000},
            allocation_method="asset_weighted",
        )
        r = eng.calculate_customer_pnl("C", "2026-04")
        # 200000 * 50M/1B = 10000
        assert r["indirect_costs"]["allocated_overhead"] == 10000.0

    def test_activity_weighted(self):
        from utils.customer_profitability import CustomerProfitabilityEngine
        eng = CustomerProfitabilityEngine(
            customer_lookup_fn=lambda c: {"cif": c},
            revenue_fn=lambda c, p: {"interest_income": Decimal("50000")},
            direct_costs_fn=lambda c, p: {},
            overhead_pool_fn=lambda p: Decimal("500000"),
            allocation_inputs_fn=lambda c, p: {"my_activity": 1500, "total_activity": 50000},
            allocation_method="activity_weighted",
        )
        r = eng.calculate_customer_pnl("C", "2026-04")
        # 500000 * 1500/50000 = 15000
        assert r["indirect_costs"]["allocated_overhead"] == 15000.0

    def test_invalid_method_raises(self):
        from utils.customer_profitability import CustomerProfitabilityEngine
        with pytest.raises(ValueError):
            CustomerProfitabilityEngine(allocation_method="bogus")

    def test_zero_pool_no_allocation(self):
        from utils.customer_profitability import CustomerProfitabilityEngine
        eng = CustomerProfitabilityEngine(
            customer_lookup_fn=lambda c: {"cif": c},
            revenue_fn=lambda c, p: {"interest_income": Decimal("100000")},
            direct_costs_fn=lambda c, p: {},
            overhead_pool_fn=lambda p: Decimal("0"),
            allocation_inputs_fn=lambda c, p: {"customer_count": 10},
            allocation_method="equal_per_customer",
        )
        r = eng.calculate_customer_pnl("C", "2026-04")
        assert r["indirect_costs"]["allocated_overhead"] == 0.0

    def test_zero_total_revenue_no_allocation(self):
        from utils.customer_profitability import CustomerProfitabilityEngine
        eng = CustomerProfitabilityEngine(
            customer_lookup_fn=lambda c: {"cif": c},
            revenue_fn=lambda c, p: {"interest_income": Decimal("100000")},
            direct_costs_fn=lambda c, p: {},
            overhead_pool_fn=lambda p: Decimal("100000"),
            allocation_inputs_fn=lambda c, p: {"my_revenue": 100000, "total_revenue": 0},
            allocation_method="revenue_weighted",
        )
        r = eng.calculate_customer_pnl("C", "2026-04")
        # No total revenue → 0 (refuse to divide by zero)
        assert r["indirect_costs"]["allocated_overhead"] == 0.0


class TestDefensiveContract:
    def test_unknown_customer_returns_empty(self, basic_engine):
        assert basic_engine.calculate_customer_pnl("UNKNOWN", "2026-04") == {}

    def test_empty_customer_id_returns_empty(self, basic_engine):
        assert basic_engine.calculate_customer_pnl("", "2026-04") == {}

    def test_empty_period_returns_empty(self, basic_engine):
        assert basic_engine.calculate_customer_pnl("C100", "") == {}


class TestDecimalPrecision:
    def test_kes_billion_scale(self):
        """Bank-scale numbers don't lose precision."""
        from utils.customer_profitability import CustomerProfitabilityEngine
        eng = CustomerProfitabilityEngine(
            customer_lookup_fn=lambda c: {"cif": c},
            revenue_fn=lambda c, p: {"interest_income": Decimal("4500000000")},
            direct_costs_fn=lambda c, p: {"interest_expense": Decimal("2700000000")},
            overhead_pool_fn=lambda p: Decimal("0"),
            allocation_inputs_fn=lambda c, p: {},
        )
        r = eng.calculate_customer_pnl("C", "2026-04")
        assert r["pbt"] == 1800000000.00

    def test_decimal_two_places_in_output(self, basic_engine):
        r = basic_engine.calculate_customer_pnl("C100", "2026-04")
        # All output money values should be 2dp
        assert isinstance(r["pbt"], float)
        # Check the decimal portion has at most 2 places
        s = f"{r['pbt']:.10f}".rstrip("0").rstrip(".")
        decimal_part = s.split(".")[1] if "." in s else ""
        assert len(decimal_part) <= 2, f"pbt has more than 2dp: {r['pbt']}"


class TestMetaBlock:
    def test_meta_records_allocation_method(self, basic_engine):
        r = basic_engine.calculate_customer_pnl("C100", "2026-04")
        assert r["meta"]["allocation_method"] == "revenue_weighted"

    def test_meta_records_customer_id(self, basic_engine):
        r = basic_engine.calculate_customer_pnl("C100", "2026-04")
        assert r["meta"]["customer_id"] == "C100"

    def test_meta_records_segment(self, basic_engine):
        r = basic_engine.calculate_customer_pnl("C100", "2026-04")
        assert r["meta"]["customer_segment"] == "Corporate"

    def test_meta_records_tolerance(self, basic_engine):
        r = basic_engine.calculate_customer_pnl("C100", "2026-04")
        assert r["meta"]["tolerance_excel_pct"] == 0.5


class TestFTPBehavior:
    """Standard #21 v5.46 — FTP mode tests.

    Validates the v5.45→v5.46 honesty fix: deposit-only customers
    are no longer treated as loss-making, loan-only customers don't
    keep the full coupon as profit, and missing FTP inputs are
    surfaced not silently swallowed.
    """

    def test_default_mode_is_off(self):
        from utils.customer_profitability import CustomerProfitabilityEngine
        eng = CustomerProfitabilityEngine(
            customer_lookup_fn=lambda c: {"cif": c, "segment": "X"},
            revenue_fn=lambda c, p: {"interest_income": Decimal("100")},
            direct_costs_fn=lambda c, p: {},
            overhead_pool_fn=lambda p: Decimal("0"),
            allocation_inputs_fn=lambda c, p: {},
        )
        r = eng.calculate_customer_pnl("C", "2026-04")
        assert r["meta"]["ftp_mode"] == "off"
        assert "ftp_credit_on_deposits" not in r["revenue"]
        assert "ftp_charge_on_loans" not in r["direct_costs"]

    def test_invalid_ftp_mode_raises(self):
        from utils.customer_profitability import CustomerProfitabilityEngine
        with pytest.raises(ValueError):
            CustomerProfitabilityEngine(ftp_mode="bogus")

    def test_invalid_balance_basis_raises(self):
        from utils.customer_profitability import CustomerProfitabilityEngine
        with pytest.raises(ValueError):
            CustomerProfitabilityEngine(balance_basis="quarterly")

    def test_ftp_on_deposit_only_is_profitable(self):
        """The canonical v5.45→v5.46 demonstration. Deposit-only
        customer that would have been -6,500 in v5.45 is +50,000
        with FTP."""
        from utils.customer_profitability import CustomerProfitabilityEngine
        eng = CustomerProfitabilityEngine(
            customer_lookup_fn=lambda c: {"cif": c, "segment": "X"},
            revenue_fn=lambda c, p: {},
            direct_costs_fn=lambda c, p: {"interest_expense": Decimal("8333.33")},
            overhead_pool_fn=lambda p: Decimal("0"),
            allocation_inputs_fn=lambda c, p: {},
            ftp_mode="on",
            ftp_inputs_fn=lambda c, p: {
                "ftp_rate":          Decimal("0.08"),
                "deposit_balance":   Decimal("10000000"),
                "deposit_rate_paid": Decimal("0.01"),
                "loan_balance":      Decimal("0"),
                "period_fraction":   Decimal("1") / Decimal("12"),
            },
        )
        r = eng.calculate_customer_pnl("C", "2026-04")
        assert "ftp_credit_on_deposits" in r["revenue"]
        assert abs(r["revenue"]["ftp_credit_on_deposits"] - 58333.33) < 0.5
        assert r["pbt"] > 0    # The fix: was negative in v5.45
        assert abs(r["pbt"] - 50000) < 1.0

    def test_ftp_on_loan_only_lending_margin(self):
        """Loan-only customer: ftp_charge eats most of the coupon,
        leaving only the lending spread."""
        from utils.customer_profitability import CustomerProfitabilityEngine
        eng = CustomerProfitabilityEngine(
            customer_lookup_fn=lambda c: {"cif": c, "segment": "X"},
            revenue_fn=lambda c, p: {"interest_income": Decimal("58333.33")},
            direct_costs_fn=lambda c, p: {},
            overhead_pool_fn=lambda p: Decimal("0"),
            allocation_inputs_fn=lambda c, p: {},
            ftp_mode="on",
            ftp_inputs_fn=lambda c, p: {
                "ftp_rate":          Decimal("0.08"),
                "deposit_balance":   Decimal("0"),
                "deposit_rate_paid": Decimal("0"),
                "loan_balance":      Decimal("5000000"),
                "period_fraction":   Decimal("1") / Decimal("12"),
            },
        )
        r = eng.calculate_customer_pnl("C", "2026-04")
        assert "ftp_charge_on_loans" in r["direct_costs"]
        assert abs(r["direct_costs"]["ftp_charge_on_loans"] - 33333.33) < 0.5
        # PBT is the lending spread only (5M × 6%/12 = 25,000)
        assert abs(r["pbt"] - 25000) < 1.0

    def test_ftp_missing_inputs_not_silent(self):
        """The new honesty rule: when ftp_mode='on' but inputs are
        incomplete, engine surfaces this in meta.ftp_missing rather
        than silently degrading."""
        from utils.customer_profitability import CustomerProfitabilityEngine
        eng = CustomerProfitabilityEngine(
            customer_lookup_fn=lambda c: {"cif": c, "segment": "X"},
            revenue_fn=lambda c, p: {"interest_income": Decimal("100")},
            direct_costs_fn=lambda c, p: {},
            overhead_pool_fn=lambda p: Decimal("0"),
            allocation_inputs_fn=lambda c, p: {},
            ftp_mode="on",
            ftp_inputs_fn=lambda c, p: {"deposit_balance": Decimal("1000000")},
        )
        r = eng.calculate_customer_pnl("C", "2026-04")
        assert "ftp_rate" in r["meta"]["ftp_missing"]
        assert "period_fraction" in r["meta"]["ftp_missing"]
        # Other components still compute
        assert r["pbt"] == 100.0

    def test_ftp_inputs_returns_none_logged(self):
        from utils.customer_profitability import CustomerProfitabilityEngine
        eng = CustomerProfitabilityEngine(
            customer_lookup_fn=lambda c: {"cif": c, "segment": "X"},
            revenue_fn=lambda c, p: {"interest_income": Decimal("100")},
            direct_costs_fn=lambda c, p: {},
            overhead_pool_fn=lambda p: Decimal("0"),
            allocation_inputs_fn=lambda c, p: {},
            ftp_mode="on",
            ftp_inputs_fn=lambda c, p: None,
        )
        r = eng.calculate_customer_pnl("C", "2026-04")
        assert "ftp_inputs_fn returned None" in r["meta"]["ftp_missing"]

    def test_meta_records_ftp_rate_and_basis(self):
        from utils.customer_profitability import CustomerProfitabilityEngine
        eng = CustomerProfitabilityEngine(
            customer_lookup_fn=lambda c: {"cif": c, "segment": "X"},
            revenue_fn=lambda c, p: {},
            direct_costs_fn=lambda c, p: {},
            overhead_pool_fn=lambda p: Decimal("0"),
            allocation_inputs_fn=lambda c, p: {},
            ftp_mode="on",
            ftp_inputs_fn=lambda c, p: {
                "ftp_rate": Decimal("0.085"),
                "deposit_balance": Decimal("1000000"),
                "deposit_rate_paid": Decimal("0.02"),
                "loan_balance": Decimal("0"),
                "period_fraction": Decimal("1") / Decimal("12"),
            },
            balance_basis="average",
        )
        r = eng.calculate_customer_pnl("C", "2026-04")
        assert r["meta"]["ftp_rate"] == 0.085
        assert r["meta"]["balance_basis"] == "average"
        assert "flat_ftp_rate (no curve lookup)" in r["meta"]["ftp_simplifications"]

    def test_zero_balances_no_ftp_buckets(self):
        """If both balances are zero, no FTP buckets get added — but
        no error either, and ftp_rate is still recorded in meta."""
        from utils.customer_profitability import CustomerProfitabilityEngine
        eng = CustomerProfitabilityEngine(
            customer_lookup_fn=lambda c: {"cif": c, "segment": "X"},
            revenue_fn=lambda c, p: {"fee_income": Decimal("500")},
            direct_costs_fn=lambda c, p: {},
            overhead_pool_fn=lambda p: Decimal("0"),
            allocation_inputs_fn=lambda c, p: {},
            ftp_mode="on",
            ftp_inputs_fn=lambda c, p: {
                "ftp_rate": Decimal("0.08"),
                "deposit_balance": Decimal("0"),
                "loan_balance": Decimal("0"),
                "period_fraction": Decimal("1") / Decimal("12"),
            },
        )
        r = eng.calculate_customer_pnl("C", "2026-04")
        assert "ftp_credit_on_deposits" not in r["revenue"]
        assert "ftp_charge_on_loans" not in r["direct_costs"]
        assert r["meta"]["ftp_rate"] == 0.08
        assert r["meta"]["ftp_missing"] == []

    def test_off_mode_unaffected_by_ftp_inputs(self):
        """Sanity check: ftp_inputs_fn supplied but mode='off' (default)
        → engine ignores it. Backward compat for v5.45 fixtures."""
        from utils.customer_profitability import CustomerProfitabilityEngine
        eng = CustomerProfitabilityEngine(
            customer_lookup_fn=lambda c: {"cif": c, "segment": "X"},
            revenue_fn=lambda c, p: {"interest_income": Decimal("100")},
            direct_costs_fn=lambda c, p: {},
            overhead_pool_fn=lambda p: Decimal("0"),
            allocation_inputs_fn=lambda c, p: {},
            ftp_inputs_fn=lambda c, p: {
                "ftp_rate": Decimal("0.99"),   # would dramatically alter
                "deposit_balance": Decimal("999999"),
                "loan_balance": Decimal("999999"),
                "period_fraction": Decimal("1"),
            },
            # ftp_mode defaults to "off"
        )
        r = eng.calculate_customer_pnl("C", "2026-04")
        assert "ftp_credit_on_deposits" not in r["revenue"]
        assert "ftp_charge_on_loans" not in r["direct_costs"]
        assert r["pbt"] == 100.0
        assert r["meta"]["ftp_mode"] == "off"


class TestPersistence:
    def test_save_and_get(self, tmp_path, monkeypatch):
        from utils import customer_profitability as cp
        monkeypatch.setattr(cp, "CUSTOMER_PNL_FILE", tmp_path / "pnl.json")
        snap = {"pbt": 100000.0, "pbt_margin": 0.30}
        ok = cp.save_pnl("C1", "2026-04", snap)
        assert ok is True
        got = cp.get_pnl("C1", "2026-04")
        assert got and got["pbt"] == 100000.0

    def test_save_empty_returns_false(self, tmp_path, monkeypatch):
        from utils import customer_profitability as cp
        monkeypatch.setattr(cp, "CUSTOMER_PNL_FILE", tmp_path / "pnl.json")
        assert cp.save_pnl("C1", "2026-04", {}) is False


# ═══════════════════════════════════════════════════════════════════════
# Excel-match harness — Standard #21 spec verification
# ═══════════════════════════════════════════════════════════════════════

def test_excel_match_within_half_percent():
    """Run every fixture; assert Excel-match ≥99.5% within ±0.5%; write G32 artifact.

    v5.46: harness now supports both ftp_mode='off' and 'on' fixtures.
    Old fixtures default to 'off' (gross-interest) and stay valid.
    New FTP fixtures (P021-P028) declare ftp_mode='on' + ftp_inputs
    and have hand-computed expected values that include
    ftp_credit_on_deposits and ftp_charge_on_loans.
    """
    from utils.customer_profitability import CustomerProfitabilityEngine

    scenarios = json.loads(FIXTURES.read_text())
    assert len(scenarios) >= 20

    within = 0
    margin_correct = 0
    indirect_correct = 0
    ftp_credit_correct = 0
    ftp_charge_correct = 0
    results = []
    for s in scenarios:
        inp = s["input"]
        ftp_mode = inp.get("ftp_mode", "off")
        ftp_inputs = inp.get("ftp_inputs")
        eng = CustomerProfitabilityEngine(
            customer_lookup_fn=lambda c: {"cif": c, "segment": "Test"},
            revenue_fn=lambda c, p, r=inp["revenue"]: {k: Decimal(str(v)) for k, v in r.items()},
            direct_costs_fn=lambda c, p, d=inp["direct_costs"]: {k: Decimal(str(v)) for k, v in d.items()},
            overhead_pool_fn=lambda p, op=inp["overhead_pool"]: Decimal(str(op)),
            allocation_inputs_fn=lambda c, p, ai=inp["allocation_inputs"]: ai,
            allocation_method=inp["allocation_method"],
            ftp_mode=ftp_mode,
            ftp_inputs_fn=lambda c, p, fi=ftp_inputs: (
                {k: Decimal(str(v)) for k, v in fi.items()} if fi else None
            ),
        )
        r = eng.calculate_customer_pnl("X", "2026-04")
        expected = s["expected"]

        # PBT match within 0.5%
        actual_pbt = r["pbt"]
        expected_pbt = expected["pbt"]
        if expected_pbt == 0:
            pbt_ok = abs(actual_pbt - expected_pbt) <= 0.01
            err_pct = abs(actual_pbt - expected_pbt) * 100
        else:
            err_pct = abs(actual_pbt - expected_pbt) / abs(expected_pbt) * 100
            pbt_ok = err_pct <= 0.5
        if pbt_ok:
            within += 1

        # Margin match within 0.001 absolute
        margin_ok = True
        if expected.get("pbt_margin") is not None and r.get("pbt_margin") is not None:
            margin_ok = abs(r["pbt_margin"] - expected["pbt_margin"]) <= 0.001
        if margin_ok:
            margin_correct += 1

        # Indirect overhead match within 0.5%
        ind_ok = True
        if "indirect_overhead" in expected:
            ai = r["indirect_costs"].get("allocated_overhead", 0)
            ei = expected["indirect_overhead"]
            if ei == 0:
                ind_ok = abs(ai - ei) <= 0.01
            else:
                ind_ok = abs(ai - ei) / abs(ei) <= 0.005
        if ind_ok:
            indirect_correct += 1

        # FTP credit match (when expected)
        ftp_credit_ok = True
        exp_credit = expected.get("ftp_credit_on_deposits")
        actual_credit = r["revenue"].get("ftp_credit_on_deposits")
        if exp_credit is None:
            ftp_credit_ok = actual_credit is None
        else:
            if actual_credit is None:
                ftp_credit_ok = False
            elif exp_credit == 0:
                ftp_credit_ok = abs(actual_credit) <= 0.01
            else:
                ftp_credit_ok = abs(actual_credit - exp_credit) / abs(exp_credit) <= 0.005
        if ftp_credit_ok:
            ftp_credit_correct += 1

        # FTP charge match (when expected)
        ftp_charge_ok = True
        exp_charge = expected.get("ftp_charge_on_loans")
        actual_charge = r["direct_costs"].get("ftp_charge_on_loans")
        if exp_charge is None:
            ftp_charge_ok = actual_charge is None
        else:
            if actual_charge is None:
                ftp_charge_ok = False
            else:
                ftp_charge_ok = abs(actual_charge - exp_charge) / abs(exp_charge) <= 0.005
        if ftp_charge_ok:
            ftp_charge_correct += 1

        # ftp_missing should contain expected keys (where declared)
        missing_ok = True
        if "ftp_missing_should_contain" in expected:
            for k in expected["ftp_missing_should_contain"]:
                if k not in r["meta"]["ftp_missing"]:
                    missing_ok = False

        results.append({
            "id": s["id"],
            "ftp_mode": ftp_mode,
            "actual_pbt": actual_pbt,
            "expected_pbt": expected_pbt,
            "error_pct": round(err_pct, 4),
            "pbt_within_tolerance": pbt_ok,
            "margin_correct": margin_ok,
            "indirect_correct": ind_ok,
            "ftp_credit_correct": ftp_credit_ok,
            "ftp_charge_correct": ftp_charge_ok,
            "missing_ok": missing_ok,
            "actual_margin": r.get("pbt_margin"),
            "expected_margin": expected.get("pbt_margin"),
            "actual_indirect": r["indirect_costs"].get("allocated_overhead"),
            "expected_indirect": expected.get("indirect_overhead"),
            "actual_ftp_credit": actual_credit,
            "expected_ftp_credit": exp_credit,
            "actual_ftp_charge": actual_charge,
            "expected_ftp_charge": exp_charge,
        })

    total = len(scenarios)
    accuracy = within / total * 100

    artifact = {
        "schema_version": 2,   # v5.46 added FTP fields
        "run_at": datetime.now(timezone.utc).isoformat(),
        "total_scenarios": total,
        "within_tolerance": within,
        "margin_correct": margin_correct,
        "indirect_correct": indirect_correct,
        "ftp_credit_correct": ftp_credit_correct,
        "ftp_charge_correct": ftp_charge_correct,
        "accuracy_pct": round(accuracy, 2),
        "spec_target_pct": 99.5,   # ≥99.5% within ±0.5%
        "tolerance_pct": 0.5,
        "all_passed": accuracy >= 99.5,
        "results": results,
    }
    RESULTS_FILE.write_text(json.dumps(artifact, indent=2))

    assert accuracy >= 99.5, (
        f"Excel match {accuracy:.1f}% < 99.5%; failures:\n"
        + "\n".join(
            f"  {r['id']}: actual={r['actual_pbt']}, expected={r['expected_pbt']}, "
            f"error={r['error_pct']}%"
            for r in results if not r["pbt_within_tolerance"]
        )
    )
    # All margins should match
    assert margin_correct == total, (
        f"Only {margin_correct}/{total} margins match"
    )
    # All indirects should match
    assert indirect_correct == total, (
        f"Only {indirect_correct}/{total} indirect overheads match"
    )
    # All FTP credits should match (where declared)
    assert ftp_credit_correct == total, (
        f"Only {ftp_credit_correct}/{total} FTP credits match"
    )
    # All FTP charges should match
    assert ftp_charge_correct == total, (
        f"Only {ftp_charge_correct}/{total} FTP charges match"
    )
