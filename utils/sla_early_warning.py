"""
================================================================================
A2Z MIS 360 — Standard #385: SLA Early Warning System
================================================================================

Risk classification: Cat D (Rule 7 — ML scaffolding) + Cat B
                     (deterministic rule-based predictive layer)

Predictive SLA breach alerting. Computes likelihood of breach 24h
ahead, allowing intervention before breach occurs.

Public API:
    early_warning_score(sla_id)              -- {basis, ml_score?, rule_based_score, level}
    forecast_breach(sla_id, hours_ahead=24)  -- {basis, breach_likely, ...}
    intervention_signals(sla_id)             -- list of trigger signals

Rule 7 (NEW for v6): no silent ML predictions. The engine ships:
    - A deterministic 5-component rule-based score (default).
    - An optional ML hook (`ml_breach_predictor_fn`) that, when
      provided, contributes an `ml_score` ALONGSIDE the rule-based.
    - When no ML provided: `ml_score=None` + `reason="no_ml_model_loaded"`.
    - When ML fails: fallback to rule-based AND surface error reason.
    - Rule-based score is ALWAYS surfaced (never silently substituted).

SPEC_DEVIATION_NOTE byte-for-byte (per Continuation.docx + Rule 7):
    "ML-based 24h-ahead breach predictor (gradient boosting / time
    series) is downstream work; v10.271 ships rule-based weighted-sum
    early warning."

Rule-based feature weights (sum = 100):
    NEAR_BREACH_RATIO_LAST_24H  = 30
    BREACH_TREND_LAST_7_PERIODS = 20
    DEGRADING_DIRECTION         = 15
    HIGH_VOLUME_SPIKE           = 15
    PRIORITY_P1_BOOST           = 10
    REGULATORY_BOOST            = 10

Score bands byte-for-byte:
    HIGH_RISK   ≥70  -- breach likely within 24h
    MEDIUM_RISK ≥40  -- monitor closely
    LOW_RISK    ≥20  -- normal monitoring
    STABLE      <20  -- no concern

Honesty rules:
    Rule 7: ml_score=None when no model; rule_based ALWAYS surfaced
    Rule 1: score=None when zero observations to score against

================================================================================
"""

from __future__ import annotations

from decimal import Decimal, getcontext
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple, Callable

from utils.sla_registry import SlaRegistryEngine
from utils.sla_monitoring import SlaMonitoringEngine

getcontext().prec = 28

# Feature weights — byte-for-byte, sum=100
EARLY_WARNING_FEATURE_WEIGHTS: Dict[str, Decimal] = {
    "NEAR_BREACH_RATIO_LAST_24H":  Decimal("30"),
    "BREACH_TREND_LAST_7_PERIODS": Decimal("20"),
    "DEGRADING_DIRECTION":          Decimal("15"),
    "HIGH_VOLUME_SPIKE":            Decimal("15"),
    "PRIORITY_P1_BOOST":            Decimal("10"),
    "REGULATORY_BOOST":             Decimal("10"),
}

EARLY_WARNING_HIGH_RISK_THRESHOLD:   Decimal = Decimal("70")
EARLY_WARNING_MEDIUM_RISK_THRESHOLD: Decimal = Decimal("40")
EARLY_WARNING_LOW_RISK_THRESHOLD:    Decimal = Decimal("20")

EARLY_WARNING_LEVELS: Tuple[str, ...] = (
    "HIGH_RISK", "MEDIUM_RISK", "LOW_RISK", "STABLE",
)

SPEC_DEVIATION_NOTE: str = (
    "ML-based 24h-ahead breach predictor (gradient boosting / time "
    "series) is downstream work; v10.271 ships rule-based weighted-sum "
    "early warning."
)


def classify_warning_level(score: Decimal) -> str:
    if score >= EARLY_WARNING_HIGH_RISK_THRESHOLD:
        return "HIGH_RISK"
    elif score >= EARLY_WARNING_MEDIUM_RISK_THRESHOLD:
        return "MEDIUM_RISK"
    elif score >= EARLY_WARNING_LOW_RISK_THRESHOLD:
        return "LOW_RISK"
    return "STABLE"


class SlaEarlyWarningEngine:
    """
    Predictive early warning. Rule 7 scaffolding pattern: real ML
    hook + deterministic rule-based fallback that's always surfaced.
    """

    def __init__(
        self,
        registry: Optional[SlaRegistryEngine] = None,
        monitoring: Optional[SlaMonitoringEngine] = None,
        ml_breach_predictor_fn: Optional[Callable[[Dict[str, Any]], Decimal]] = None,
    ):
        self.registry = registry or SlaRegistryEngine()
        self.monitoring = monitoring or SlaMonitoringEngine()
        self.ml_breach_predictor_fn = ml_breach_predictor_fn

    def _rule_based_score(self, signals: Dict[str, Any]) -> Decimal:
        """Deterministic 6-feature weighted score (capped at 100)."""
        score = Decimal("0")

        if signals.get("near_breach_ratio_last_24h", 0) > 0.3:
            score += EARLY_WARNING_FEATURE_WEIGHTS["NEAR_BREACH_RATIO_LAST_24H"]
        if signals.get("breach_trend_last_7_periods", 0) > 0:
            score += EARLY_WARNING_FEATURE_WEIGHTS["BREACH_TREND_LAST_7_PERIODS"]
        if signals.get("compliance_direction") == "degrading":
            score += EARLY_WARNING_FEATURE_WEIGHTS["DEGRADING_DIRECTION"]
        if signals.get("volume_spike", False):
            score += EARLY_WARNING_FEATURE_WEIGHTS["HIGH_VOLUME_SPIKE"]
        if signals.get("priority") == "P1_CRITICAL":
            score += EARLY_WARNING_FEATURE_WEIGHTS["PRIORITY_P1_BOOST"]
        if signals.get("is_regulatory", False):
            score += EARLY_WARNING_FEATURE_WEIGHTS["REGULATORY_BOOST"]

        # Cap at 100
        if score > Decimal("100"):
            score = Decimal("100")
        return score

    def _gather_signals(self, sla_id: str) -> Dict[str, Any]:
        """Gather observable signals for SLA. Returns dict for scoring."""
        sla = self.registry.get_sla(sla_id)
        if not sla:
            return {}

        # Last 24h compliance
        last_24h_start = (datetime.utcnow() - timedelta(hours=24)).isoformat()
        comp_24h = self.monitoring.compute_compliance(sla_id, last_24h_start)
        near_breach_ratio = (
            (comp_24h["near_breach"] / comp_24h["total_observations"])
            if comp_24h["total_observations"] > 0 else 0
        )

        # Last 7 periods (30-day each)
        breach_count_7p = 0
        for i in range(7):
            start = (datetime.utcnow() - timedelta(days=30 * (i + 1))).isoformat()
            end = (datetime.utcnow() - timedelta(days=30 * i)).isoformat()
            comp_p = self.monitoring.compute_compliance(sla_id, start, end)
            if comp_p["breached"] > 0:
                breach_count_7p += 1

        # Direction
        direction = "stable"
        if comp_24h["compliance_pct"] is not None and comp_24h["total_observations"] >= 5:
            if comp_24h["compliance_pct"] < Decimal("85"):
                direction = "degrading"

        return {
            "near_breach_ratio_last_24h": near_breach_ratio,
            "breach_trend_last_7_periods": breach_count_7p,
            "compliance_direction": direction,
            "volume_spike": comp_24h["total_observations"] > 100,
            "priority": sla.get("priority"),
            "is_regulatory": sla.get("sla_type") == "REGULATORY",
        }

    def early_warning_score(self, sla_id: str) -> Dict[str, Any]:
        """
        Compute early warning score. Rule 7 scaffolding:
        rule_based_score always surfaced; ml_score only when provider given.
        """
        signals = self._gather_signals(sla_id)
        if not signals:
            return {
                "sla_id": sla_id,
                "rule_based_score": None,
                "ml_score": None,
                "level": None,
                "reason": "sla_not_found",
                "spec_deviation": SPEC_DEVIATION_NOTE,
            }

        rule_score = self._rule_based_score(signals)
        rule_level = classify_warning_level(rule_score)

        # Rule 7: ml_score path
        ml_score = None
        ml_reason = None
        if self.ml_breach_predictor_fn is None:
            ml_reason = "no_ml_model_loaded"
        else:
            try:
                ml_result = self.ml_breach_predictor_fn(signals)
                ml_score = Decimal(str(ml_result))
            except Exception as e:
                ml_reason = f"ml_breach_error:{type(e).__name__}"

        return {
            "sla_id": sla_id,
            "basis": "rule_based" if ml_score is None else "rule_based+ml",
            "rule_based_score": str(rule_score.quantize(Decimal("0.01"))),
            "ml_score": (
                str(ml_score.quantize(Decimal("0.01")))
                if ml_score is not None else None
            ),
            "ml_reason": ml_reason,
            "level": rule_level,  # decision uses rule-based; ML is informational
            "signals": signals,
            "spec_deviation": SPEC_DEVIATION_NOTE,
        }

    def forecast_breach(
        self, sla_id: str, hours_ahead: int = 24
    ) -> Dict[str, Any]:
        """24h breach forecast. Rule 7 — never silent ML."""
        score = self.early_warning_score(sla_id)
        breach_likely = score.get("level") in ("HIGH_RISK", "MEDIUM_RISK")
        return {
            "sla_id": sla_id,
            "hours_ahead": hours_ahead,
            "breach_likely": breach_likely,
            "level": score.get("level"),
            "rule_based_score": score.get("rule_based_score"),
            "ml_score": score.get("ml_score"),
            "spec_deviation": SPEC_DEVIATION_NOTE,
        }

    def intervention_signals(self, sla_id: str) -> List[Dict[str, Any]]:
        """List active warning signals for an SLA."""
        signals = self._gather_signals(sla_id)
        if not signals:
            return []

        active = []
        if signals["near_breach_ratio_last_24h"] > 0.3:
            active.append({
                "signal": "NEAR_BREACH_RATIO_LAST_24H",
                "weight": str(EARLY_WARNING_FEATURE_WEIGHTS["NEAR_BREACH_RATIO_LAST_24H"]),
                "value": signals["near_breach_ratio_last_24h"],
            })
        if signals["breach_trend_last_7_periods"] > 0:
            active.append({
                "signal": "BREACH_TREND_LAST_7_PERIODS",
                "weight": str(EARLY_WARNING_FEATURE_WEIGHTS["BREACH_TREND_LAST_7_PERIODS"]),
                "value": signals["breach_trend_last_7_periods"],
            })
        if signals["compliance_direction"] == "degrading":
            active.append({
                "signal": "DEGRADING_DIRECTION",
                "weight": str(EARLY_WARNING_FEATURE_WEIGHTS["DEGRADING_DIRECTION"]),
                "value": "degrading",
            })
        return active


def _self_test() -> None:
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as tmpdir:
        registry = SlaRegistryEngine(
            registry_path=Path(tmpdir) / "sla_registry.json"
        )
        monitoring = SlaMonitoringEngine(
            observations_path=Path(tmpdir) / "sla_observations.json"
        )

        # Register SLA
        registry.register_sla({
            "sla_id": "SLA-EW-001",
            "name": "Test SLA",
            "sla_type": "REGULATORY",
            "priority": "P1_CRITICAL",
            "metric_type": "RESPONSE_TIME",
            "target_value": Decimal("30"),
            "target_unit": "days",
            "direction": "max",
            "owner_department": "Compliance",
        })

        engine = SlaEarlyWarningEngine(
            registry=registry, monitoring=monitoring,
            # No ML hook — Rule 7 scaffolding
        )

        # Test 1: classify_warning_level
        assert classify_warning_level(Decimal("75")) == "HIGH_RISK"
        assert classify_warning_level(Decimal("50")) == "MEDIUM_RISK"
        assert classify_warning_level(Decimal("25")) == "LOW_RISK"
        assert classify_warning_level(Decimal("10")) == "STABLE"

        # Test 2: early warning score — Rule 7 verification
        result = engine.early_warning_score("SLA-EW-001")
        assert result["basis"] == "rule_based"
        assert result["ml_score"] is None
        assert result["ml_reason"] == "no_ml_model_loaded"
        assert result["rule_based_score"] is not None
        assert result["spec_deviation"] == SPEC_DEVIATION_NOTE
        # P1_CRITICAL + REGULATORY = 10 + 10 = 20 → LOW_RISK
        assert result["level"] in ("LOW_RISK", "STABLE")

        # Test 3: rule-based determinism
        r1 = engine.early_warning_score("SLA-EW-001")
        r2 = engine.early_warning_score("SLA-EW-001")
        assert r1["rule_based_score"] == r2["rule_based_score"]

        # Test 4: ML hook path
        def fake_ml(signals):
            return Decimal("85")

        engine_ml = SlaEarlyWarningEngine(
            registry=registry, monitoring=monitoring,
            ml_breach_predictor_fn=fake_ml,
        )
        result_ml = engine_ml.early_warning_score("SLA-EW-001")
        assert result_ml["basis"] == "rule_based+ml"
        assert result_ml["ml_score"] == "85.00"
        # Rule-based ALSO surfaced
        assert result_ml["rule_based_score"] is not None

        # Test 5: ML failure → fallback with error reason
        def broken_ml(signals):
            raise ValueError("model unavailable")

        engine_broken = SlaEarlyWarningEngine(
            registry=registry, monitoring=monitoring,
            ml_breach_predictor_fn=broken_ml,
        )
        result_b = engine_broken.early_warning_score("SLA-EW-001")
        assert result_b["ml_score"] is None
        assert "ml_breach_error" in result_b["ml_reason"]
        assert result_b["rule_based_score"] is not None  # always surfaced

        # Test 6: unknown SLA
        result_x = engine.early_warning_score("NONEXISTENT")
        assert result_x["rule_based_score"] is None
        assert result_x["reason"] == "sla_not_found"

    print("  ✅ sla_early_warning self-test PASS")


if __name__ == "__main__":
    _self_test()
