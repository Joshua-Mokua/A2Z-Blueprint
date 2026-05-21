"""tests/integration/test_v10_17_kesonia.py — v10.17 KESONIA enhancement.

Phase 2 enhancement: CBK KESONIA + Revised Risk-Based Credit Pricing Model.
Standard: ENH-CBK-KESONIA.

KESONIA was officially launched 1 Sept 2025 as a renaming of the existing
overnight interbank rate. New variable-rate KES loans must use it from
1 Dec 2025; existing variable-rate loans must migrate by 28 Feb 2026.
"""
from __future__ import annotations
import sys
import unittest
from decimal import Decimal
from pathlib import Path

_THIS = Path(__file__).resolve()
sys.path.insert(0, str(_THIS.parents[2]))


class TestV1017Imports(unittest.TestCase):
    def test_module_imports(self):
        from utils import benchmark_rates  # noqa

    def test_public_symbols(self):
        from utils import benchmark_rates as m
        for sym in (
            "RateCode", "RateType", "LoanRateType",
            "BenchmarkRateObservation", "CompoundedIndexObservation",
            "BenchmarkLookupResult", "CompoundedAccrualResult",
            "BenchmarkRateRegistry",
            "resolve_funding_rate_decimal", "derive_k_premium_pct",
            "KESONIA_LAUNCH_DATE",
            "KESONIA_NEW_LOAN_EFFECTIVE",
            "KESONIA_NEW_LOAN_PRACTICAL",
            "KESONIA_EXISTING_LOAN_DEADLINE",
            "KESONIA_DAY_COUNT_BASIS",
            "DEFAULT_FALLBACK_RATE_CODE",
        ):
            self.assertTrue(hasattr(m, sym), f"missing public: {sym}")


class TestV1017SelfTest(unittest.TestCase):
    def test_self_test_passes(self):
        from utils import benchmark_rates
        benchmark_rates.self_test()


class TestV1017RegistryAlignment(unittest.TestCase):
    def test_kesonia_standard_registered(self):
        from utils.standards_registry import STANDARDS_REGISTRY
        ids = {s.standard_id for s in STANDARDS_REGISTRY}
        self.assertIn("ENH-CBK-KESONIA", ids)

    def test_kesonia_standard_active(self):
        from utils.standards_registry import STANDARDS_REGISTRY
        kesonia = next(
            s for s in STANDARDS_REGISTRY
            if s.standard_id == "ENH-CBK-KESONIA")
        self.assertEqual(kesonia.status, "active")

    def test_g121_still_passes_with_kesonia_added(self):
        """G121 was forward-compatible-fixed — must still pass after
        ENH-CBK-KESONIA added the credit set to 20."""
        from scripts.audit import gate_credit_engines_implemented
        r = gate_credit_engines_implemented()
        self.assertTrue(
            r["passed"],
            f"G121 should still pass; violations: {r.get('violations')}")


class TestV1017RegulatoryDates(unittest.TestCase):
    """CBK regulatory dates match official rollout."""

    def test_launch_date_is_sept_1_2025(self):
        from utils.benchmark_rates import KESONIA_LAUNCH_DATE
        self.assertEqual(KESONIA_LAUNCH_DATE, "2025-09-01")

    def test_existing_loan_deadline_is_feb_28_2026(self):
        from utils.benchmark_rates import KESONIA_EXISTING_LOAN_DEADLINE
        self.assertEqual(KESONIA_EXISTING_LOAN_DEADLINE, "2026-02-28")

    def test_day_count_360(self):
        """CBK convention matches SONIA + SOFR — 360-day year."""
        from utils.benchmark_rates import KESONIA_DAY_COUNT_BASIS
        self.assertEqual(KESONIA_DAY_COUNT_BASIS, 360)


class TestV1017RateLookup(unittest.TestCase):
    """Rate lookup honors CBK methodology."""

    def test_exact_match_returns_rate(self):
        from utils.benchmark_rates import (
            BenchmarkRateRegistry, BenchmarkRateObservation,
            RateCode, RateType)
        reg = BenchmarkRateRegistry()
        reg.add_rate(BenchmarkRateObservation(
            rate_code=RateCode.KESONIA, observation_date="2026-04-23",
            rate_pct=Decimal("8.76"), rate_type=RateType.OVERNIGHT))
        r = reg.get_rate(rate_code=RateCode.KESONIA,
                          as_of_date="2026-04-23")
        self.assertTrue(r.is_resolved())
        self.assertEqual(r.rate_pct, Decimal("8.76"))

    def test_weekend_holdover(self):
        """CBK methodology: KESONIA held constant on weekends/holidays."""
        from utils.benchmark_rates import (
            BenchmarkRateRegistry, BenchmarkRateObservation,
            RateCode, RateType)
        reg = BenchmarkRateRegistry()
        reg.add_rate(BenchmarkRateObservation(
            rate_code=RateCode.KESONIA, observation_date="2026-04-23",
            rate_pct=Decimal("8.76"), rate_type=RateType.OVERNIGHT))
        # Saturday 2026-04-25
        r = reg.get_rate(rate_code=RateCode.KESONIA,
                          as_of_date="2026-04-25")
        self.assertTrue(r.is_resolved())
        self.assertEqual(r.rate_pct, Decimal("8.76"))

    def test_no_data_no_fabrication(self):
        """Rule 1: empty registry → unresolved, never fabricated."""
        from utils.benchmark_rates import (
            BenchmarkRateRegistry, RateCode)
        reg = BenchmarkRateRegistry()
        r = reg.get_rate(rate_code=RateCode.KESONIA,
                          as_of_date="2026-04-23")
        self.assertFalse(r.is_resolved())
        self.assertIsNone(r.rate_pct)

    def test_fetcher_hookable(self):
        """Rule 7: callable fetcher can be wired to CBK feed."""
        from utils.benchmark_rates import (
            BenchmarkRateRegistry, BenchmarkRateObservation,
            RateCode, RateType)
        calls = []
        def fetcher(code, dt):
            calls.append(dt)
            return BenchmarkRateObservation(
                rate_code=code, observation_date=dt,
                rate_pct=Decimal("8.50"),
                rate_type=RateType.OVERNIGHT,
                source="test_cbk_feed")
        reg = BenchmarkRateRegistry(rate_fetcher=fetcher)
        r = reg.get_rate(rate_code=RateCode.KESONIA,
                          as_of_date="2026-04-23")
        self.assertEqual(len(calls), 1)
        self.assertEqual(r.rate_pct, Decimal("8.50"))


class TestV1017RBCPMTotalRate(unittest.TestCase):
    """Total Rate = KESONIA + K per CBK RBCPM."""

    def test_kesonia_plus_k(self):
        from utils.benchmark_rates import (
            BenchmarkRateRegistry, BenchmarkRateObservation,
            RateCode, RateType)
        reg = BenchmarkRateRegistry()
        reg.add_rate(BenchmarkRateObservation(
            rate_code=RateCode.KESONIA, observation_date="2026-04-23",
            rate_pct=Decimal("8.76"), rate_type=RateType.OVERNIGHT))
        r = reg.compute_total_rate(
            as_of_date="2026-04-23",
            k_premium_pct=Decimal("4.50"))
        self.assertTrue(r["is_in_scope"])
        self.assertEqual(r["base_rate_pct"], Decimal("8.76"))
        self.assertEqual(r["total_rate_pct"], Decimal("13.26"))

    def test_fcy_loan_excluded(self):
        """Per CBK FAQ: foreign-currency loans not in scope."""
        from utils.benchmark_rates import (
            BenchmarkRateRegistry, LoanRateType)
        reg = BenchmarkRateRegistry()
        r = reg.compute_total_rate(
            as_of_date="2026-04-23",
            k_premium_pct=Decimal("4.50"),
            loan_rate_type=LoanRateType.VARIABLE_FCY)
        self.assertFalse(r["is_in_scope"])

    def test_fixed_rate_loan_excluded(self):
        from utils.benchmark_rates import (
            BenchmarkRateRegistry, LoanRateType)
        reg = BenchmarkRateRegistry()
        r = reg.compute_total_rate(
            as_of_date="2026-04-23",
            k_premium_pct=Decimal("4.50"),
            loan_rate_type=LoanRateType.FIXED_RATE)
        self.assertFalse(r["is_in_scope"])

    def test_cbr_fallback_visible(self):
        """When KESONIA unavailable, fallback to CBR is visible to caller."""
        from utils.benchmark_rates import (
            BenchmarkRateRegistry, BenchmarkRateObservation,
            RateCode, RateType)
        reg = BenchmarkRateRegistry()
        reg.add_rate(BenchmarkRateObservation(
            rate_code=RateCode.CBR, observation_date="2026-04-23",
            rate_pct=Decimal("9.00"), rate_type=RateType.POLICY))
        r = reg.compute_total_rate(
            as_of_date="2026-04-23",
            k_premium_pct=Decimal("4.50"))
        self.assertTrue(r["is_in_scope"])
        self.assertTrue(r["is_fallback"])
        self.assertEqual(r["rate_code_used"], "CBR")
        self.assertEqual(r["total_rate_pct"], Decimal("13.50"))


class TestV1017CompoundedIndex(unittest.TestCase):
    """KESONIA Compounded Index for compound-in-arrears."""

    def test_compounded_accrual_via_index_ratio(self):
        from utils.benchmark_rates import (
            BenchmarkRateRegistry, CompoundedIndexObservation)
        reg = BenchmarkRateRegistry()
        reg.add_compounded_index(CompoundedIndexObservation(
            observation_date="2026-01-01",
            index_value=Decimal("110.5000")))
        reg.add_compounded_index(CompoundedIndexObservation(
            observation_date="2026-04-01",
            index_value=Decimal("112.7000")))
        r = reg.compute_compounded_accrual(
            period_start="2026-01-01", period_end="2026-04-01")
        self.assertIsNotNone(r)
        self.assertEqual(r.days, 90)
        # Annualized rate should be in reasonable range (~7-10% for this data)
        self.assertGreater(r.annualized_rate_pct, Decimal("5"))
        self.assertLess(r.annualized_rate_pct, Decimal("12"))

    def test_compounded_accrual_unavailable_returns_none(self):
        from utils.benchmark_rates import BenchmarkRateRegistry
        reg = BenchmarkRateRegistry()
        r = reg.compute_compounded_accrual(
            period_start="2026-01-01", period_end="2026-04-01")
        self.assertIsNone(r)


class TestV1017BridgeToV1013Pricing(unittest.TestCase):
    """Composition with v10.13 risk_based_pricing engine."""

    def test_resolve_funding_rate_for_pricing_inputs(self):
        """Bridge: KESONIA 8.76% → 0.0876 decimal for v10.13.PricingInputs."""
        from utils.benchmark_rates import (
            BenchmarkRateRegistry, BenchmarkRateObservation,
            RateCode, RateType, resolve_funding_rate_decimal)
        reg = BenchmarkRateRegistry()
        reg.add_rate(BenchmarkRateObservation(
            rate_code=RateCode.KESONIA, observation_date="2026-04-23",
            rate_pct=Decimal("8.76"), rate_type=RateType.OVERNIGHT))
        rate, lookup = resolve_funding_rate_decimal(
            registry=reg, as_of_date="2026-04-23")
        self.assertEqual(rate, Decimal("0.0876"))

    def test_v10_13_pricing_consumes_kesonia_funding(self):
        """End-to-end: KESONIA funding rate → v10.13 price_loan → offered_rate."""
        from utils.benchmark_rates import (
            BenchmarkRateRegistry, BenchmarkRateObservation,
            RateCode, RateType, resolve_funding_rate_decimal)
        from utils.risk_based_pricing import (
            PricingInputs, price_loan, PricingDecision)

        reg = BenchmarkRateRegistry()
        reg.add_rate(BenchmarkRateObservation(
            rate_code=RateCode.KESONIA, observation_date="2026-04-23",
            rate_pct=Decimal("8.76"), rate_type=RateType.OVERNIGHT))

        kesonia_decimal, _ = resolve_funding_rate_decimal(
            registry=reg, as_of_date="2026-04-23")

        # Build v10.13 pricing inputs using KESONIA as funding rate
        inputs = PricingInputs(
            asset_id="L1", pd=Decimal("0.02"), lgd=Decimal("0.40"),
            ead_kes=Decimal("1000000"), tenor_months=12,
            funding_rate=kesonia_decimal)
        result = price_loan(inputs)

        # Pricing should succeed within normal band
        self.assertEqual(result.decision, PricingDecision.PRICE_OFFERED)
        # Funding cost in decomposition = KESONIA we passed in
        self.assertEqual(result.components.funding_cost, kesonia_decimal)

    def test_derive_k_premium_round_trip(self):
        """K = total - KESONIA. Bidirectional consistency."""
        from utils.benchmark_rates import derive_k_premium_pct
        # Total 13.26%, KESONIA 8.76% → K=4.50pp
        k = derive_k_premium_pct(
            offered_rate_decimal=Decimal("0.1326"),
            kesonia_pct=Decimal("8.76"))
        self.assertEqual(k, Decimal("4.50"))


class TestV1017Coexistence(unittest.TestCase):
    """v10.17 KESONIA coexists with all v10.6-v10.16 engines."""

    def test_coexistence_with_credit_engines(self):
        from utils.ai_underwriting import AIUnderwritingEngine
        from utils.applicant_data_sources import ApplicantDataAggregator
        from utils.credit_workflow import CreditWorkflowEngine
        from utils.benchmark_rates import BenchmarkRateRegistry
        u = AIUnderwritingEngine(entity_name="X")
        d = ApplicantDataAggregator(entity_name="X")
        w = CreditWorkflowEngine(entity_name="X")
        b = BenchmarkRateRegistry(entity_name="X")
        for e in (u, d, w, b):
            self.assertEqual(e.entity_name, "X")


if __name__ == "__main__":
    unittest.main()
