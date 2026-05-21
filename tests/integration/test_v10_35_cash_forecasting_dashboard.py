"""tests/integration/test_v10_35_cash_forecasting_dashboard.py — v10.35.

Treasury arc batch 3: ENH-237 AI Cash Forecasting + ENH-238 Treasury
Dashboard. Activates 2 of 16 Treasury standards (now 8/16 active = 50%).
"""
from __future__ import annotations
import sys
import unittest
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

_THIS = Path(__file__).resolve()
sys.path.insert(0, str(_THIS.parents[2]))


class TestV1035Imports(unittest.TestCase):
    def test_cash_forecasting_imports(self):
        from utils import cash_forecasting  # noqa

    def test_treasury_dashboard_imports(self):
        from utils import treasury_dashboard  # noqa

    def test_cash_forecasting_public_symbols(self):
        from utils import cash_forecasting as m
        for sym in (
            "DEFAULT_HORIZON_DAYS",
            "MIN_HISTORY_DAYS_FOR_SEASONALITY",
            "Z_80_PCT", "Z_95_PCT",
            "DEFAULT_SMOOTHING_ALPHA",
            "FlowDriver",
            "ScheduledCashFlow",
            "HistoricalDayNetFlow",
            "SeasonalityModel",
            "fit_seasonality_model",
            "exponential_smoothing_baseline",
            "DailyForecastPoint", "ForecastResult",
            "compute_forecast",
            "MLForecastProvider",
            "TreasuryCashForecastingEngine",
            "SPEC_DEVIATION_NOTE",
        ):
            self.assertTrue(hasattr(m, sym), f"missing: {sym}")

    def test_treasury_dashboard_public_symbols(self):
        from utils import treasury_dashboard as m
        for sym in (
            "ReportType", "SectionStatus",
            "DashboardSection", "DashboardReport",
            "aggregate_status",
            "build_alm_lcr_section", "build_alm_nsfr_section",
            "build_irrbb_outlier_section",
            "build_capital_ratios_section",
            "build_fx_exposure_section",
            "build_nim_section", "build_cash_forecast_section",
            "TreasuryDashboardEngine",
            "SPEC_DEVIATION_NOTE",
        ):
            self.assertTrue(hasattr(m, sym), f"missing: {sym}")


class TestV1035SelfTests(unittest.TestCase):
    def test_cash_forecasting_self_test(self):
        from utils import cash_forecasting
        cash_forecasting.self_test()

    def test_treasury_dashboard_self_test(self):
        from utils import treasury_dashboard
        treasury_dashboard.self_test()


class TestV1035StandardsAlignment(unittest.TestCase):
    def test_two_new_treasury_standards_active(self):
        from utils.standards_registry import STANDARDS_REGISTRY
        active_ids = {
            s.standard_id for s in STANDARDS_REGISTRY
            if s.subcategory.startswith("treasury")
            and s.status == "active"}
        for sid in ("ENH-237", "ENH-238"):
            self.assertIn(sid, active_ids)

    def test_eight_treasury_standards_active(self):
        """3 + 3 + 2 = 8 of 16 (50%)."""
        from utils.standards_registry import STANDARDS_REGISTRY
        active = [
            s for s in STANDARDS_REGISTRY
            if s.subcategory.startswith("treasury")
            and s.status == "active"]
        self.assertGreaterEqual(len(active), 8)


# ════════════════════════════════════════════════════════════════════════
# ENH-237: Cash Forecasting
# ════════════════════════════════════════════════════════════════════════

class TestV1035CashForecastingHorizon(unittest.TestCase):
    def test_default_horizon_91_days(self):
        from utils.cash_forecasting import DEFAULT_HORIZON_DAYS
        self.assertEqual(DEFAULT_HORIZON_DAYS, 91)

    def test_z_scores_match_normal(self):
        from utils.cash_forecasting import Z_80_PCT, Z_95_PCT
        self.assertEqual(Z_80_PCT, Decimal("1.28"))
        self.assertEqual(Z_95_PCT, Decimal("1.96"))


class TestV1035Seasonality(unittest.TestCase):
    def _synth_history(self, n=60):
        from utils.cash_forecasting import HistoricalDayNetFlow
        out = []
        d = date(2026, 1, 1)
        for i in range(n):
            day = d + timedelta(days=i)
            base = Decimal("1000000")
            if day.weekday() >= 5:
                base = base * Decimal("0.5")
            out.append(HistoricalDayNetFlow(
                observation_date=day.isoformat(),
                net_flow_kes=base))
        return out

    def test_seasonality_requires_min_30_days(self):
        from utils.cash_forecasting import (
            fit_seasonality_model, HistoricalDayNetFlow)
        short = [HistoricalDayNetFlow(
            observation_date="2026-05-01",
            net_flow_kes=Decimal("1000"))] * 10
        with self.assertRaises(ValueError):
            fit_seasonality_model(model_id="M1", history=short)

    def test_seasonality_dow_fits_weekend_lower(self):
        from utils.cash_forecasting import fit_seasonality_model
        history = self._synth_history(60)
        model = fit_seasonality_model(
            model_id="M1", history=history)
        # Weekend (5, 6) lower than 1.0
        self.assertLess(model.dow_multipliers[5], Decimal("1"))
        self.assertLess(model.dow_multipliers[6], Decimal("1"))


class TestV1035Forecast(unittest.TestCase):
    def _synth_history(self, n=60):
        from utils.cash_forecasting import HistoricalDayNetFlow
        out = []
        d = date(2026, 1, 1)
        for i in range(n):
            day = d + timedelta(days=i)
            base = Decimal("1000000")
            if day.weekday() >= 5:
                base = base * Decimal("0.5")
            out.append(HistoricalDayNetFlow(
                observation_date=day.isoformat(),
                net_flow_kes=base))
        return out

    def test_forecast_horizon_matches_input(self):
        from utils.cash_forecasting import (
            fit_seasonality_model,
            exponential_smoothing_baseline,
            compute_forecast)
        history = self._synth_history(60)
        season = fit_seasonality_model(
            model_id="M1", history=history)
        baseline = exponential_smoothing_baseline(history=history)
        result = compute_forecast(
            forecast_id="F1",
            start_date="2026-05-01",
            horizon_days=91,
            seasonality=season,
            baseline=baseline)
        self.assertEqual(result.horizon_days, 91)
        self.assertEqual(len(result.points), 91)

    def test_forecast_scheduled_appears_on_correct_day(self):
        from utils.cash_forecasting import (
            fit_seasonality_model,
            exponential_smoothing_baseline,
            compute_forecast,
            ScheduledCashFlow, FlowDriver)
        history = self._synth_history(60)
        season = fit_seasonality_model(
            model_id="M1", history=history)
        baseline = exponential_smoothing_baseline(history=history)
        flows = [ScheduledCashFlow(
            flow_id="F1", flow_date="2026-05-05",
            amount_kes=Decimal("10000000"),
            driver=FlowDriver.BOND_MATURITY)]
        result = compute_forecast(
            forecast_id="F1",
            start_date="2026-05-01",
            horizon_days=14,
            seasonality=season,
            baseline=baseline,
            scheduled_flows=flows)
        # Day 4 (May 5) → +10M deterministic
        self.assertEqual(
            result.points[4].deterministic_kes,
            Decimal("10000000.00"))

    def test_forecast_ml_overlay_flag(self):
        from utils.cash_forecasting import (
            fit_seasonality_model,
            compute_forecast)
        history = self._synth_history(60)
        season = fit_seasonality_model(
            model_id="M1", history=history)
        # No overlay
        result = compute_forecast(
            forecast_id="F1",
            start_date="2026-05-01",
            horizon_days=7,
            seasonality=season,
            baseline=Decimal("1000000"))
        self.assertFalse(result.ml_overlay_applied)
        self.assertIn("baseline", result.valuation_basis)

        # With overlay
        result2 = compute_forecast(
            forecast_id="F2",
            start_date="2026-05-01",
            horizon_days=7,
            seasonality=season,
            baseline=Decimal("1000000"),
            ml_overlay={"2026-05-01": Decimal("999999")})
        self.assertTrue(result2.ml_overlay_applied)
        self.assertIn("ml", result2.valuation_basis)


class TestV1035CashForecastingEngine(unittest.TestCase):
    def test_ml_without_provider_raises_provider(self):
        """Per Rule 7: REQUIRES_PROVIDER when ML provider unwired."""
        from utils.cash_forecasting import (
            TreasuryCashForecastingEngine,
            HistoricalDayNetFlow)
        eng = TreasuryCashForecastingEngine()
        # Add 60 days of history
        d = date(2026, 1, 1)
        for i in range(60):
            day = d + timedelta(days=i)
            eng.add_history(HistoricalDayNetFlow(
                observation_date=day.isoformat(),
                net_flow_kes=Decimal("1000000")))
        eng.fit_seasonality("S1")
        with self.assertRaises(ValueError) as ctx:
            eng.forecast_with_ml_overlay(
                forecast_id="F1",
                start_date="2026-05-01",
                horizon_days=7,
                seasonality_model_id="S1")
        self.assertIn("REQUIRES_PROVIDER", str(ctx.exception))

    def test_baseline_without_history_raises(self):
        from utils.cash_forecasting import (
            TreasuryCashForecastingEngine)
        eng = TreasuryCashForecastingEngine()
        with self.assertRaises(ValueError):
            eng.baseline()


# ════════════════════════════════════════════════════════════════════════
# ENH-238: Treasury Dashboard
# ════════════════════════════════════════════════════════════════════════

class TestV1035DashboardSectionAggregation(unittest.TestCase):
    def test_breach_dominates_in_aggregation(self):
        from utils.treasury_dashboard import (
            DashboardSection, SectionStatus, aggregate_status)
        sections = (
            DashboardSection(
                section_id="A", section_title="A",
                source_engine="x", status=SectionStatus.OK,
                metrics={}, thresholds={}),
            DashboardSection(
                section_id="B", section_title="B",
                source_engine="x", status=SectionStatus.BREACH,
                metrics={}, thresholds={}),
        )
        overall, nb, nw = aggregate_status(sections)
        self.assertEqual(overall, SectionStatus.BREACH)
        self.assertEqual(nb, 1)


class TestV1035DashboardWiringOptional(unittest.TestCase):
    def test_no_wiring_emits_zero_sections_no_error(self):
        from utils.treasury_dashboard import (
            TreasuryDashboardEngine)
        eng = TreasuryDashboardEngine()
        report = eng.generate_daily_treasury(
            report_id="R1", as_of_date="2026-05-01")
        self.assertEqual(len(report.sections), 0)


class TestV1035DashboardWithLiveEngines(unittest.TestCase):
    """Wire real upstream engines and verify report flows."""

    def test_live_treasury_alm_to_dashboard(self):
        """Real TreasuryALMEngine → dashboard LCR section."""
        from utils.treasury_alm import (
            TreasuryALMEngine, HQLAPosition, HQLALevel,
            CashFlow)
        from utils.treasury_dashboard import (
            TreasuryDashboardEngine, SectionStatus)
        # Build an LCR-compliant ALM
        alm = TreasuryALMEngine()
        alm.register_hqla(HQLAPosition(
            position_id="H1", asset_class="cash",
            level=HQLALevel.LEVEL_1,
            notional=Decimal("200000000"),
            currency="KES"))
        alm.add_outflow(CashFlow(
            flow_id="O1", direction="OUTFLOW",
            amount=Decimal("100000000"),
            bucket_days=30))
        alm.run_lcr(result_id="L1", as_of_date="2026-05-01")
        dashboard = TreasuryDashboardEngine(alm_engine=alm)
        report = dashboard.generate_daily_treasury(
            report_id="R1", as_of_date="2026-05-01")
        lcr = report.section_by_id("alm_lcr")
        self.assertIsNotNone(lcr)
        self.assertEqual(lcr.status, SectionStatus.OK)

    def test_live_breach_propagates_to_overall(self):
        """LCR breach → dashboard overall_status BREACH."""
        from utils.treasury_alm import (
            TreasuryALMEngine, HQLAPosition, HQLALevel,
            CashFlow)
        from utils.treasury_dashboard import (
            TreasuryDashboardEngine, SectionStatus)
        alm = TreasuryALMEngine()
        # Insufficient HQLA
        alm.register_hqla(HQLAPosition(
            position_id="H1", asset_class="cash",
            level=HQLALevel.LEVEL_1,
            notional=Decimal("50000000"),
            currency="KES"))
        alm.add_outflow(CashFlow(
            flow_id="O1", direction="OUTFLOW",
            amount=Decimal("100000000"),
            bucket_days=30))
        alm.run_lcr(result_id="L1", as_of_date="2026-05-01")
        dashboard = TreasuryDashboardEngine(alm_engine=alm)
        report = dashboard.generate_daily_treasury(
            report_id="R1", as_of_date="2026-05-01")
        self.assertEqual(report.overall_status, SectionStatus.BREACH)
        self.assertGreaterEqual(report.n_breaches, 1)

    def test_full_stack_board_pack(self):
        """Wire all 5 engines → full board pack."""
        from utils.treasury_alm import (
            TreasuryALMEngine, HQLAPosition, HQLALevel,
            CashFlow, RatesGapPosition, MaturityBucket,
            IRRBBScenario)
        from utils.treasury_products import TreasuryProductsEngine
        from utils.rwa_optimization import (
            RWAOptimizationEngine, Exposure, AssetClass,
            CapitalComponents)
        from utils.fund_transfer_pricing import (
            FTPEngine, FTPProductCategory)
        from utils.cash_forecasting import (
            TreasuryCashForecastingEngine,
            HistoricalDayNetFlow)
        from utils.treasury_dashboard import (
            TreasuryDashboardEngine, ReportType)
        # Setup all 5 engines
        alm = TreasuryALMEngine()
        alm.register_hqla(HQLAPosition(
            position_id="H1", asset_class="cash",
            level=HQLALevel.LEVEL_1,
            notional=Decimal("200000000"), currency="KES"))
        alm.add_outflow(CashFlow(
            flow_id="O1", direction="OUTFLOW",
            amount=Decimal("100000000"), bucket_days=30))
        alm.run_lcr(result_id="L1", as_of_date="2026-05-01")
        alm.run_nsfr(
            result_id="N1",
            asf_components={"retail": Decimal("950000")},
            rsf_components={"loans": Decimal("700000")},
            as_of_date="2026-05-01")
        alm.register_rates_position(RatesGapPosition(
            position_id="P1",
            bucket=MaturityBucket.MONTHS_1_3,
            is_asset=True, notional=Decimal("100000000"),
            currency="KES"))
        alm.run_repricing_gap(
            result_id="G1", as_of_date="2026-05-01")
        alm.run_all_irrbb_scenarios(
            result_id_prefix="ALL", gap_result_id="G1",
            base_nii_kes=Decimal("10000000"),
            base_eve_kes=Decimal("0"),
            tier_1_capital_kes=Decimal("10000000000"),
            as_of_date="2026-05-01")

        products = TreasuryProductsEngine()

        rwa = RWAOptimizationEngine()
        rwa.register_exposure(Exposure(
            exposure_id="E1", counterparty="A",
            asset_class=AssetClass.CORPORATE_UNRATED,
            on_bs_amount=Decimal("1000000000")))
        rwa.compute_all_rwa()
        capital = CapitalComponents(
            cet1_capital=Decimal("200000000"),    # 20%
            additional_t1_capital=Decimal("0"),
            tier_2_capital=Decimal("100000000"))
        rwa.compute_capital_ratios(
            result_id="C1", capital=capital,
            as_of_date="2026-05-01")

        ftp = FTPEngine()
        ftp.decompose_nim(
            decomposition_id="D1", product_id="L1",
            product_category=FTPProductCategory.LOAN_TERM,
            is_asset=True,
            customer_rate_pct=Decimal("15"),
            ftp_rate_pct=Decimal("10"))

        forecast = TreasuryCashForecastingEngine()
        d = date(2026, 1, 1)
        for i in range(60):
            day = d + timedelta(days=i)
            forecast.add_history(HistoricalDayNetFlow(
                observation_date=day.isoformat(),
                net_flow_kes=Decimal("1000000")))
        forecast.fit_seasonality("S1")
        forecast.forecast(
            forecast_id="F1", start_date="2026-05-01",
            horizon_days=91, seasonality_model_id="S1")

        dashboard = TreasuryDashboardEngine(
            alm_engine=alm, products_engine=products,
            rwa_engine=rwa, ftp_engine=ftp,
            forecast_engine=forecast)
        report = dashboard.generate_board_pack(
            report_id="BP-202605", as_of_date="2026-05-01")

        # All 6 sections present
        self.assertEqual(report.report_type, ReportType.BOARD_PACK)
        self.assertGreaterEqual(len(report.sections), 6)
        section_ids = {s.section_id for s in report.sections}
        self.assertIn("alm_lcr", section_ids)
        self.assertIn("alm_nsfr", section_ids)
        self.assertIn("irrbb_outliers", section_ids)
        self.assertIn("capital_ratios", section_ids)
        self.assertIn("nim", section_ids)
        self.assertIn("cash_forecast", section_ids)


class TestV1035CoexistenceWithFullStack(unittest.TestCase):
    def test_all_engines_coexist(self):
        from utils.audit_core import AuditCoreEngine
        from utils.model_governance import ModelGovernanceEngine
        from utils.virtual_bank_core import VirtualBankCore
        from utils.cross_sell_bandit import (
            BanditConfig, CrossSellBanditEngine,
            DEFAULT_OFFER_CATALOG)
        from utils.treasury_alm import TreasuryALMEngine
        from utils.treasury_products import TreasuryProductsEngine
        from utils.rwa_optimization import RWAOptimizationEngine
        from utils.fund_transfer_pricing import FTPEngine
        from utils.cash_forecasting import (
            TreasuryCashForecastingEngine)
        from utils.treasury_dashboard import (
            TreasuryDashboardEngine)
        engines = [
            AuditCoreEngine(entity_name="X"),
            ModelGovernanceEngine(entity_name="X"),
            VirtualBankCore(
                entity_name="X", base_seed="s",
                base_date="2026-01-01"),
            CrossSellBanditEngine(
                entity_name="X",
                config=BanditConfig(
                    config_id="C1", model_id="M",
                    feature_names=("balance_log", "intercept"),
                    offer_catalog=DEFAULT_OFFER_CATALOG,
                    alpha=1.0, base_seed="t")),
            TreasuryALMEngine(entity_name="X"),
            TreasuryProductsEngine(entity_name="X"),
            RWAOptimizationEngine(entity_name="X"),
            FTPEngine(entity_name="X"),
            TreasuryCashForecastingEngine(entity_name="X"),
            TreasuryDashboardEngine(entity_name="X"),
        ]
        for e in engines:
            self.assertEqual(e.entity_name, "X")


if __name__ == "__main__":
    unittest.main()
