"""tests/test_volume_nine_batch.py — Standards #53-#56 (v5.55).

Coverage:
  Standard #53 — Credit Risk Scoring (Cat D, third Rule 7 application)
  Standard #54 — Market Risk (Cat B)
  Standard #55 — Operational Risk (Cat A schema + Cat B/C)
  Standard #56 — Regulatory Risk Reporting (Cat A/B)

Plus one artifact-handoff harness:
  test_credit_risk_correctness_meets_99_percent →
    credit_risk_scoring_results.json (G56)
"""
from __future__ import annotations
import json
from pathlib import Path
import pytest

ROOT = Path(__file__).parent.parent
FIXTURES_DIR = ROOT / "tests" / "fixtures"


# ═══════════════════════════════════════════════════════════════════════
# Standard #53 — Credit Risk Scoring
# ═══════════════════════════════════════════════════════════════════════

class TestStandard53:
    def test_module_exists(self):
        from utils.credit_risk_scoring import CreditRiskScoringEngine
        eng = CreditRiskScoringEngine()
        assert hasattr(eng, "score_borrower")
        assert hasattr(eng, "portfolio_pd_summary")

    def test_spec_literal_grades(self):
        from utils.credit_risk_scoring import RISK_GRADES
        assert RISK_GRADES == ["AAA", "AA", "A", "BBB", "BB", "B", "CCC", "CC", "C", "D"]

    def test_pd_bands(self):
        from utils.credit_risk_scoring import PD_BANDS
        assert PD_BANDS["AAA"] == 0.0001
        assert PD_BANDS["D"] == 1.0
        assert PD_BANDS["BBB"] == 0.02

    def test_basel_lgd(self):
        from utils.credit_risk_scoring import DEFAULT_LGD_SENIOR_UNSECURED, DEFAULT_LGD_SUBORDINATED
        assert DEFAULT_LGD_SENIOR_UNSECURED == 0.45
        assert DEFAULT_LGD_SUBORDINATED == 0.75

    def test_rule7_no_model_returns_ml_pd_none(self):
        """Rule 7 — third application after #41, #48."""
        from utils.credit_risk_scoring import CreditRiskScoringEngine
        eng = CreditRiskScoringEngine()
        r = eng.score_borrower(features={"debt_to_income": 0.7})
        assert r["ml_pd"] is None
        assert r["reason"] == "no_ml_model_loaded"
        assert r["meta"]["spec_deviation"] is not None

    def test_rule_based_pd_deterministic(self):
        from utils.credit_risk_scoring import CreditRiskScoringEngine
        features = {"debt_to_income": 0.4}
        eng = CreditRiskScoringEngine()
        r1 = eng.score_borrower(features=features)
        r2 = eng.score_borrower(features=features)
        assert r1["rule_based_pd"] == r2["rule_based_pd"]

    def test_ml_loaded_returns_basis_ml(self):
        from utils.credit_risk_scoring import CreditRiskScoringEngine
        class FM:
            def predict(self, f): return 0.30
        eng = CreditRiskScoringEngine(model_loader_fn=lambda: FM())
        r = eng.score_borrower(features={})
        assert r["ml_pd"] == 0.30
        assert r["meta"]["spec_deviation"] is None

    def test_spec_deviation_byte_for_byte(self):
        from utils.credit_risk_scoring import SPEC_DEVIATION_NOTE
        assert SPEC_DEVIATION_NOTE == "ML credit-risk-scoring model training is downstream work; v6 ships rule-based PD"


# ═══════════════════════════════════════════════════════════════════════
# Standard #54 — Market Risk
# ═══════════════════════════════════════════════════════════════════════

class TestStandard54:
    def test_module_exists(self):
        from utils.market_risk import MarketRiskEngine
        eng = MarketRiskEngine()
        assert hasattr(eng, "value_at_risk")
        assert hasattr(eng, "sensitivity_analysis")
        assert hasattr(eng, "stress_test")

    def test_spec_literal_confidence(self):
        from utils.market_risk import CONFIDENCE_LEVELS
        assert CONFIDENCE_LEVELS == [0.95, 0.99, 0.999]

    def test_default_horizon_basel(self):
        from utils.market_risk import DEFAULT_HORIZON_DAYS
        assert DEFAULT_HORIZON_DAYS == 10

    def test_min_observations(self):
        from utils.market_risk import MIN_OBSERVATIONS_FOR_VAR
        assert MIN_OBSERVATIONS_FOR_VAR == 30

    def test_stress_scenarios_catalog(self):
        from utils.market_risk import STRESS_SCENARIOS
        assert "KES_DEVALUATION_20PCT" in STRESS_SCENARIOS
        assert "RATE_HIKE_200BP" in STRESS_SCENARIOS
        assert STRESS_SCENARIOS["RATE_HIKE_200BP"]["interest_rate_shock_bp"] == 200

    def test_var_with_insufficient_history_surfaces(self):
        """Rule 6 — no silent fallback."""
        from utils.market_risk import MarketRiskEngine
        eng = MarketRiskEngine(history_lookup_fn=lambda i: [0.001] * 5)
        r = eng.value_at_risk([{"instrument_id": "X", "notional": 1000}])
        assert "X" in r["unscored_positions"]

    def test_invalid_confidence_rejected(self):
        from utils.market_risk import MarketRiskEngine
        eng = MarketRiskEngine()
        r = eng.value_at_risk([], confidence=0.50)
        assert "error" in r

    def test_unknown_scenario_rejected(self):
        from utils.market_risk import MarketRiskEngine
        eng = MarketRiskEngine()
        r = eng.stress_test([], "BANANA_REPUBLIC")
        assert "error" in r


# ═══════════════════════════════════════════════════════════════════════
# Standard #55 — Operational Risk
# ═══════════════════════════════════════════════════════════════════════

class TestStandard55:
    def test_module_exists(self):
        from utils.operational_risk import OperationalRiskEngine
        eng = OperationalRiskEngine()
        assert hasattr(eng, "log_loss_event")
        assert hasattr(eng, "aggregate_losses_by_category")
        assert hasattr(eng, "compute_kri_metrics")

    def test_basel_7_categories(self):
        from utils.operational_risk import ORM_CATEGORIES
        assert len(ORM_CATEGORIES) == 7
        assert "INTERNAL_FRAUD" in ORM_CATEGORIES
        assert "EXTERNAL_FRAUD" in ORM_CATEGORIES
        assert "EXECUTION_DELIVERY" in ORM_CATEGORIES

    def test_severity_levels(self):
        from utils.operational_risk import SEVERITY_LEVELS
        assert SEVERITY_LEVELS == ["LOW", "MEDIUM", "HIGH", "SEVERE"]

    def test_schema_complete(self):
        from utils.operational_risk import build_schema_ddl, ddl_contains_required_columns
        ddl = build_schema_ddl()
        missing = ddl_contains_required_columns(ddl)
        for table, cols in missing.items():
            assert cols == [], f"{table} missing: {cols}"

    def test_invalid_category_rejected(self):
        """Rule 6 — no silent re-bucketing."""
        from utils.operational_risk import OperationalRiskEngine
        eng = OperationalRiskEngine()
        r = eng.log_loss_event("UNKNOWN_CAT", "2026-04-15", "test")
        assert r["success"] is False

    def test_severity_classification(self):
        from utils.operational_risk import OperationalRiskEngine
        eng = OperationalRiskEngine()
        assert eng._classify_severity(50_000) == "LOW"
        assert eng._classify_severity(500_000) == "MEDIUM"
        assert eng._classify_severity(5_000_000) == "HIGH"
        assert eng._classify_severity(50_000_000) == "SEVERE"

    def test_no_impact_event_tracked_separately(self):
        """Rule 1 — average_loss=None when zero events have impact."""
        from utils.operational_risk import OperationalRiskEngine
        eng = OperationalRiskEngine()
        eng.log_loss_event("EXECUTION_DELIVERY", "2026-04-15", "Settlement glitch")
        r = eng.aggregate_losses_by_category("2026-04-01", "2026-04-30")
        cat = r["by_category"]["EXECUTION_DELIVERY"]
        assert cat["events_no_impact"] == 1
        assert cat["events_with_impact"] == 0
        assert cat["average_loss"] is None


# ═══════════════════════════════════════════════════════════════════════
# Standard #56 — Regulatory Risk Reporting
# ═══════════════════════════════════════════════════════════════════════

class TestStandard56:
    def test_module_exists(self):
        from utils.regulatory_reporting import RegulatoryReportingEngine
        eng = RegulatoryReportingEngine()
        assert hasattr(eng, "compute_capital_adequacy")
        assert hasattr(eng, "large_exposures_report")
        assert hasattr(eng, "liquidity_coverage_report")
        assert hasattr(eng, "build_report")

    def test_8_cbk_reports_catalog(self):
        from utils.regulatory_reporting import CBK_REPORTS
        assert len(CBK_REPORTS) == 8
        for r in ["CAPITAL_ADEQUACY_RATIO", "LARGE_EXPOSURES_RETURN",
                  "LIQUIDITY_COVERAGE_RATIO", "FX_NET_OPEN_POSITION"]:
            assert r in CBK_REPORTS

    def test_basel_thresholds_byte_for_byte(self):
        from utils.regulatory_reporting import (
            CAR_MIN_PCT, TIER1_MIN_PCT, LCR_MIN_PCT, LARGE_EXPOSURE_LIMIT_PCT,
        )
        assert CAR_MIN_PCT == 10.5
        assert TIER1_MIN_PCT == 8.5
        assert LCR_MIN_PCT == 100.0
        assert LARGE_EXPOSURE_LIMIT_PCT == 25.0

    def test_car_passing(self):
        from utils.regulatory_reporting import RegulatoryReportingEngine
        eng = RegulatoryReportingEngine()
        r = eng.compute_capital_adequacy(10_000_000_000, 2_000_000_000, 80_000_000_000)
        assert r["car_pct"] == 15.0
        assert r["passes_threshold"] is True

    def test_car_failing(self):
        from utils.regulatory_reporting import RegulatoryReportingEngine
        eng = RegulatoryReportingEngine()
        r = eng.compute_capital_adequacy(2_000_000_000, 500_000_000, 50_000_000_000)
        assert r["passes_threshold"] is False

    def test_rwa_zero_returns_none(self):
        """Rule 1 — None when denominator zero."""
        from utils.regulatory_reporting import RegulatoryReportingEngine
        eng = RegulatoryReportingEngine()
        r = eng.compute_capital_adequacy(1_000_000, 0, 0)
        assert r["car_pct"] is None
        assert r["passes_threshold"] is None

    def test_large_exposure_aggregation(self):
        """Multiple loans to same counterparty aggregate."""
        from utils.regulatory_reporting import RegulatoryReportingEngine
        eng = RegulatoryReportingEngine()
        loans = [
            {"counterparty_id": "CP1", "outstanding": 3_000_000_000},
            {"counterparty_id": "CP1", "outstanding": 200_000_000},
        ]
        r = eng.large_exposures_report(loans, 10_000_000_000)
        # 3.2B / 10B = 32% → exceeds 25%
        assert r["exceeds_count"] == 1
        assert r["large_exposures"][0]["pct_of_capital"] == 32.0

    def test_lcr_threshold(self):
        from utils.regulatory_reporting import RegulatoryReportingEngine
        eng = RegulatoryReportingEngine()
        r = eng.liquidity_coverage_report(50_000_000_000, 40_000_000_000)
        assert r["lcr_pct"] == 125.0
        assert r["passes_threshold"] is True

    def test_unknown_report_rejected(self):
        from utils.regulatory_reporting import RegulatoryReportingEngine
        eng = RegulatoryReportingEngine()
        r = eng.build_report("UNKNOWN_REPORT")
        assert "error" in r


# ═══════════════════════════════════════════════════════════════════════
# G56 harness — Credit Risk correctness
# ═══════════════════════════════════════════════════════════════════════

def test_credit_risk_correctness_meets_99_percent():
    """Run all CR fixtures and produce credit_risk_scoring_results.json."""
    from utils.credit_risk_scoring import CreditRiskScoringEngine

    fixtures_path = FIXTURES_DIR / "credit_risk_scoring_scenarios.json"
    assert fixtures_path.exists()
    with open(fixtures_path) as f:
        data = json.load(f)
    fixtures = data["fixtures"]

    eng = CreditRiskScoringEngine()
    results = []
    matches = 0
    total = len(fixtures)

    for fx in fixtures:
        r = eng.score_borrower(features=fx["features"])
        exp = fx["expected"]
        ok = True
        for field in ("rule_based_pd", "rule_based_grade", "lgd", "ead"):
            if field not in exp:
                continue
            actual = r.get(field)
            expected = exp[field]
            if isinstance(expected, (int, float)) and isinstance(actual, (int, float)):
                if abs(actual - expected) > 0.0001:
                    ok = False
            else:
                if actual != expected:
                    ok = False

        if ok:
            matches += 1
        results.append({
            "id": fx["id"],
            "label": fx["label"],
            "matched": ok,
            "diffs": [] if ok else [f"mismatch on fixture {fx['id']}"],
        })

    accuracy = (matches / total * 100) if total > 0 else 0
    artifact = {
        "total_scenarios":  total,
        "correct":          matches,
        "accuracy_pct":     accuracy,
        "spec_target_pct":  99.0,
        "results":          results,
        "fixtures_total":   total,
        "fixtures_matched": matches,
        "match_rate_pct":   accuracy,
    }

    out_path = ROOT / "credit_risk_scoring_results.json"
    with open(out_path, "w") as f:
        json.dump(artifact, f, indent=2)

    assert accuracy >= 99.0, \
        f"credit risk correctness {accuracy:.1f}% < 99%; see {out_path}"
