"""
================================================================================
A2Z MIS 360 — Standard #82: Internal Controls Framework Engine
================================================================================

Risk classification: Cat B (deterministic COSO + control testing per ISA 530)

Computes COSO-aligned internal controls metrics:
    - test_control(...)                     -- attribute sampling test outcome
    - sample_size(...)                      -- ISA 530 / AICPA AU-C 530
    - classify_deficiency(...)              -- deficiency / significant / material
    - coso_component_score(...)             -- 5 components × 17 principles
    - control_effectiveness_summary(...)    -- aggregated rating

COSO 2013 Framework — 5 Components byte-for-byte:
    CONTROL_ENVIRONMENT      : 5 principles
    RISK_ASSESSMENT          : 4 principles
    CONTROL_ACTIVITIES       : 3 principles
    INFORMATION_COMMUNICATION: 3 principles
    MONITORING_ACTIVITIES    : 2 principles
    Total                    : 17 principles

Sample size attribute thresholds (ISA 530 / AICPA AU-C 530) byte-for-byte:
    LOW risk control     : 25 samples
    MEDIUM risk control  : 40 samples
    HIGH risk control    : 60 samples
    KEY control          : 90 samples (financial reporting)

Control deficiency severity (PCAOB AS 2201 / SEC) byte-for-byte:
    DEFICIENCY              : single control failure, low impact
    SIGNIFICANT_DEFICIENCY  : reasonably possible material misstatement
    MATERIAL_WEAKNESS       : reasonably possible material misstatement that
                              would NOT be prevented or detected timely

Honesty rules applied:
    Rule 1: effectiveness_pct = None when sample_size <= 0
    Rule 6: tests with missing exception counts excluded with count surfaced

================================================================================
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, getcontext
from typing import Any, Dict, List, Optional, Tuple

getcontext().prec = 28

# COSO 2013 Framework — 5 components byte-for-byte
COSO_COMPONENTS: Tuple[str, ...] = (
    "CONTROL_ENVIRONMENT",
    "RISK_ASSESSMENT",
    "CONTROL_ACTIVITIES",
    "INFORMATION_COMMUNICATION",
    "MONITORING_ACTIVITIES",
)

# 17 COSO principles by component
COSO_PRINCIPLES: Dict[str, List[str]] = {
    "CONTROL_ENVIRONMENT": [
        "P1_INTEGRITY_AND_ETHICAL_VALUES",
        "P2_BOARD_OVERSIGHT",
        "P3_ORGANISATIONAL_STRUCTURE",
        "P4_HUMAN_RESOURCE_COMPETENCE",
        "P5_ACCOUNTABILITY_FOR_INTERNAL_CONTROL",
    ],
    "RISK_ASSESSMENT": [
        "P6_OBJECTIVES_SPECIFICATION",
        "P7_RISK_IDENTIFICATION_AND_ANALYSIS",
        "P8_FRAUD_RISK_CONSIDERATION",
        "P9_CHANGE_IDENTIFICATION_AND_ASSESSMENT",
    ],
    "CONTROL_ACTIVITIES": [
        "P10_CONTROL_ACTIVITY_SELECTION_AND_DEVELOPMENT",
        "P11_TECHNOLOGY_GENERAL_CONTROLS",
        "P12_POLICY_AND_PROCEDURE_DEPLOYMENT",
    ],
    "INFORMATION_COMMUNICATION": [
        "P13_QUALITY_INFORMATION_USED",
        "P14_INTERNAL_COMMUNICATION",
        "P15_EXTERNAL_COMMUNICATION",
    ],
    "MONITORING_ACTIVITIES": [
        "P16_ONGOING_AND_SEPARATE_EVALUATIONS",
        "P17_DEFICIENCY_EVALUATION_AND_COMMUNICATION",
    ],
}

TOTAL_COSO_PRINCIPLES = 17  # sanity check

# Sample sizes (ISA 530 / AICPA AU-C 530) byte-for-byte
SAMPLE_SIZES_BY_RISK: Dict[str, int] = {
    "LOW": 25,
    "MEDIUM": 40,
    "HIGH": 60,
    "KEY": 90,
}

# Control deficiency severity classifications byte-for-byte (PCAOB AS 2201)
DEFICIENCY_SEVERITIES: Tuple[str, ...] = (
    "DEFICIENCY",
    "SIGNIFICANT_DEFICIENCY",
    "MATERIAL_WEAKNESS",
)

# Test outcomes
TEST_OUTCOMES: Tuple[str, ...] = (
    "EFFECTIVE",          # 0 exceptions
    "PARTIALLY_EFFECTIVE", # exception rate within tolerance
    "INEFFECTIVE",        # exception rate exceeds tolerance
)

# Tolerable exception rates by control criticality byte-for-byte
TOLERABLE_EXCEPTION_RATE_PCT: Dict[str, Decimal] = {
    "LOW": Decimal("10"),     # 10% tolerance
    "MEDIUM": Decimal("5"),
    "HIGH": Decimal("2"),
    "KEY": Decimal("0"),      # zero-tolerance for key controls
}

# Materiality threshold for severity classification (% of total assets)
SIGNIFICANT_DEFICIENCY_THRESHOLD_PCT = Decimal("1")  # 1% of assets
MATERIAL_WEAKNESS_THRESHOLD_PCT = Decimal("5")       # 5% of assets


@dataclass
class ControlTest:
    test_id: str
    control_id: str
    coso_component: str
    risk_level: str  # LOW / MEDIUM / HIGH / KEY
    sample_size: Optional[int] = None
    exceptions_found: Optional[int] = None
    test_period_start: Optional[Any] = None
    test_period_end: Optional[Any] = None


@dataclass
class ControlDeficiency:
    deficiency_id: str
    control_id: str
    description: str
    estimated_financial_impact_kes: Optional[Decimal] = None
    affects_financial_reporting: bool = False
    compensating_controls_exist: bool = False
    total_assets_kes: Optional[Decimal] = None  # for severity classification


class InternalControlsEngine:
    """Deterministic COSO + control testing per ISA 530 / PCAOB AS 2201."""

    @staticmethod
    def sample_size(risk_level: str) -> Dict[str, Any]:
        """Return prescribed sample size by control risk level."""
        if risk_level not in SAMPLE_SIZES_BY_RISK:
            return {"error": f"unknown_risk_level:{risk_level}",
                    "valid_levels": list(SAMPLE_SIZES_BY_RISK.keys())}
        return {
            "risk_level": risk_level,
            "sample_size": SAMPLE_SIZES_BY_RISK[risk_level],
            "tolerable_exception_rate_pct": str(TOLERABLE_EXCEPTION_RATE_PCT[risk_level]),
        }

    @staticmethod
    def test_control(test: ControlTest) -> Dict[str, Any]:
        """
        Evaluate control test outcome.
        Rule 1: effectiveness_pct=None when sample_size<=0.
        Rule 6: missing exception count → return reason without rating.
        """
        if test.coso_component not in COSO_COMPONENTS:
            return {"test_id": test.test_id,
                    "error": f"unknown_coso_component:{test.coso_component}"}
        if test.risk_level not in SAMPLE_SIZES_BY_RISK:
            return {"test_id": test.test_id,
                    "error": f"unknown_risk_level:{test.risk_level}"}
        if test.sample_size is None or test.exceptions_found is None:
            return {
                "test_id": test.test_id,
                "control_id": test.control_id,
                "outcome": None,
                "effectiveness_pct": None,
                "reason": "missing_sample_or_exceptions",
            }
        if test.sample_size <= 0:
            return {
                "test_id": test.test_id,
                "control_id": test.control_id,
                "outcome": None,
                "effectiveness_pct": None,
                "reason": "sample_size_zero_or_negative",
            }
        if test.exceptions_found < 0:
            return {
                "test_id": test.test_id,
                "control_id": test.control_id,
                "outcome": None,
                "effectiveness_pct": None,
                "reason": "negative_exceptions",
            }
        # Check sample size meets minimum
        min_required = SAMPLE_SIZES_BY_RISK[test.risk_level]
        sample_adequate = test.sample_size >= min_required

        # Compute effectiveness
        exception_rate = (Decimal(test.exceptions_found) / Decimal(test.sample_size)
                          * Decimal("100"))
        effectiveness_pct = Decimal("100") - exception_rate
        tolerance = TOLERABLE_EXCEPTION_RATE_PCT[test.risk_level]

        if test.exceptions_found == 0:
            outcome = "EFFECTIVE"
        elif exception_rate <= tolerance:
            outcome = "PARTIALLY_EFFECTIVE"
        else:
            outcome = "INEFFECTIVE"

        return {
            "test_id": test.test_id,
            "control_id": test.control_id,
            "coso_component": test.coso_component,
            "risk_level": test.risk_level,
            "sample_size": test.sample_size,
            "min_required_sample": min_required,
            "sample_adequate": sample_adequate,
            "exceptions_found": test.exceptions_found,
            "exception_rate_pct": str(exception_rate.quantize(Decimal("0.01"))),
            "tolerance_pct": str(tolerance),
            "effectiveness_pct": str(effectiveness_pct.quantize(Decimal("0.01"))),
            "outcome": outcome,
        }

    @staticmethod
    def classify_deficiency(d: ControlDeficiency) -> Dict[str, Any]:
        """
        Classify deficiency severity per PCAOB AS 2201.
        Severity escalates based on financial impact + financial reporting effect
        + presence of compensating controls.
        """
        if d.estimated_financial_impact_kes is None or d.total_assets_kes is None:
            return {
                "deficiency_id": d.deficiency_id,
                "severity": None,
                "reason": "missing_impact_or_total_assets",
            }
        if d.total_assets_kes <= 0:
            return {
                "deficiency_id": d.deficiency_id,
                "severity": None,
                "reason": "total_assets_zero_or_negative",
            }
        impact_pct = (d.estimated_financial_impact_kes / d.total_assets_kes
                      * Decimal("100"))

        # Default classification by impact %
        if impact_pct >= MATERIAL_WEAKNESS_THRESHOLD_PCT:
            severity = "MATERIAL_WEAKNESS"
        elif impact_pct >= SIGNIFICANT_DEFICIENCY_THRESHOLD_PCT:
            severity = "SIGNIFICANT_DEFICIENCY"
        else:
            severity = "DEFICIENCY"

        # Escalate if affects financial reporting and no compensating controls
        if (severity == "DEFICIENCY"
                and d.affects_financial_reporting
                and not d.compensating_controls_exist):
            severity = "SIGNIFICANT_DEFICIENCY"

        return {
            "deficiency_id": d.deficiency_id,
            "control_id": d.control_id,
            "estimated_financial_impact_kes": str(d.estimated_financial_impact_kes.quantize(Decimal("0.01"))),
            "total_assets_kes": str(d.total_assets_kes.quantize(Decimal("0.01"))),
            "impact_pct": str(impact_pct.quantize(Decimal("0.0001"))),
            "affects_financial_reporting": d.affects_financial_reporting,
            "compensating_controls_exist": d.compensating_controls_exist,
            "severity": severity,
        }

    @classmethod
    def coso_component_score(
        cls,
        principle_ratings: Dict[str, Decimal],  # principle_id -> 0-100
    ) -> Dict[str, Any]:
        """
        Score each COSO component as average of its principles.
        Rule 6: missing principle ratings excluded.
        """
        component_scores = {}
        missing_principles = []
        for component, principles in COSO_PRINCIPLES.items():
            ratings = []
            for p in principles:
                rating = principle_ratings.get(p)
                if rating is None:
                    missing_principles.append(p)
                    continue
                ratings.append(rating)
            if not ratings:
                component_scores[component] = None
                continue
            avg = sum(ratings) / Decimal(len(ratings))
            component_scores[component] = str(avg.quantize(Decimal("0.01")))

        # Overall framework score
        scored = [Decimal(v) for v in component_scores.values() if v is not None]
        overall = (sum(scored) / Decimal(len(scored))) if scored else None

        return {
            "component_scores": component_scores,
            "overall_score": str(overall.quantize(Decimal("0.01"))) if overall is not None else None,
            "missing_principles": missing_principles,
            "missing_count": len(missing_principles),
            "scored_components": len(scored),
            "total_components": len(COSO_COMPONENTS),
        }

    @classmethod
    def control_effectiveness_summary(
        cls,
        test_results: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Aggregate test outcomes by COSO component."""
        by_component = {c: {"effective": 0, "partially_effective": 0, "ineffective": 0}
                        for c in COSO_COMPONENTS}
        excluded = 0
        for r in test_results:
            comp = r.get("coso_component")
            outcome = r.get("outcome")
            if comp not in COSO_COMPONENTS or outcome is None:
                excluded += 1
                continue
            if outcome == "EFFECTIVE":
                by_component[comp]["effective"] += 1
            elif outcome == "PARTIALLY_EFFECTIVE":
                by_component[comp]["partially_effective"] += 1
            elif outcome == "INEFFECTIVE":
                by_component[comp]["ineffective"] += 1

        # Total tests
        total_tests = sum(sum(v.values()) for v in by_component.values())
        total_effective = sum(v["effective"] for v in by_component.values())
        overall_effectiveness_pct = (
            (Decimal(total_effective) / Decimal(total_tests) * Decimal("100"))
            if total_tests > 0 else None
        )

        return {
            "by_component": by_component,
            "total_tests": total_tests,
            "total_effective": total_effective,
            "overall_effectiveness_pct": (str(overall_effectiveness_pct.quantize(Decimal("0.01")))
                                          if overall_effectiveness_pct is not None else None),
            "excluded_count": excluded,
        }


# ============================================================================
# Self-tests
# ============================================================================

def _test():
    pass  # placeholder


def _test_sample_size_low():
    r = InternalControlsEngine.sample_size("LOW")
    assert r["sample_size"] == 25


def _test_sample_size_key():
    r = InternalControlsEngine.sample_size("KEY")
    assert r["sample_size"] == 90


def _test_sample_size_unknown():
    r = InternalControlsEngine.sample_size("WEIRD")
    assert "error" in r


def _test_control_test_effective():
    test = ControlTest(test_id="T1", control_id="C1",
                       coso_component="CONTROL_ACTIVITIES",
                       risk_level="MEDIUM",
                       sample_size=40, exceptions_found=0)
    r = InternalControlsEngine.test_control(test)
    assert r["outcome"] == "EFFECTIVE"
    assert r["effectiveness_pct"] == "100.00"


def _test_control_test_partially_effective():
    """40 samples, 2 exceptions = 5% rate, MEDIUM tolerance = 5% → PARTIAL."""
    test = ControlTest(test_id="T1", control_id="C1",
                       coso_component="CONTROL_ACTIVITIES",
                       risk_level="MEDIUM",
                       sample_size=40, exceptions_found=2)
    r = InternalControlsEngine.test_control(test)
    assert r["outcome"] == "PARTIALLY_EFFECTIVE"


def _test_control_test_ineffective():
    """KEY has zero tolerance, any exception = ineffective."""
    test = ControlTest(test_id="T1", control_id="C1",
                       coso_component="CONTROL_ACTIVITIES",
                       risk_level="KEY",
                       sample_size=90, exceptions_found=1)
    r = InternalControlsEngine.test_control(test)
    assert r["outcome"] == "INEFFECTIVE"


def _test_control_test_sample_inadequate():
    """30 samples for KEY (needs 90)."""
    test = ControlTest(test_id="T1", control_id="C1",
                       coso_component="CONTROL_ACTIVITIES",
                       risk_level="KEY",
                       sample_size=30, exceptions_found=0)
    r = InternalControlsEngine.test_control(test)
    assert r["sample_adequate"] is False


def _test_control_test_zero_sample_rule1():
    test = ControlTest(test_id="T1", control_id="C1",
                       coso_component="CONTROL_ACTIVITIES",
                       risk_level="MEDIUM",
                       sample_size=0, exceptions_found=0)
    r = InternalControlsEngine.test_control(test)
    assert r["effectiveness_pct"] is None


def _test_control_test_missing_data_rule6():
    test = ControlTest(test_id="T1", control_id="C1",
                       coso_component="CONTROL_ACTIVITIES",
                       risk_level="MEDIUM")
    r = InternalControlsEngine.test_control(test)
    assert r["outcome"] is None


def _test_deficiency_classification_basic():
    d = ControlDeficiency(
        deficiency_id="D1", control_id="C1",
        description="Test",
        estimated_financial_impact_kes=Decimal("500000"),  # 0.05%
        total_assets_kes=Decimal("1000000000"),
    )
    r = InternalControlsEngine.classify_deficiency(d)
    assert r["severity"] == "DEFICIENCY"


def _test_deficiency_significant():
    d = ControlDeficiency(
        deficiency_id="D1", control_id="C1",
        description="Test",
        estimated_financial_impact_kes=Decimal("20000000"),  # 2%
        total_assets_kes=Decimal("1000000000"),
    )
    r = InternalControlsEngine.classify_deficiency(d)
    assert r["severity"] == "SIGNIFICANT_DEFICIENCY"


def _test_deficiency_material_weakness():
    d = ControlDeficiency(
        deficiency_id="D1", control_id="C1",
        description="Test",
        estimated_financial_impact_kes=Decimal("60000000"),  # 6%
        total_assets_kes=Decimal("1000000000"),
    )
    r = InternalControlsEngine.classify_deficiency(d)
    assert r["severity"] == "MATERIAL_WEAKNESS"


def _test_deficiency_escalates_no_compensating():
    """Small impact but affects financial reporting + no compensating → upgrade."""
    d = ControlDeficiency(
        deficiency_id="D1", control_id="C1",
        description="Test",
        estimated_financial_impact_kes=Decimal("100000"),
        total_assets_kes=Decimal("1000000000"),
        affects_financial_reporting=True,
        compensating_controls_exist=False,
    )
    r = InternalControlsEngine.classify_deficiency(d)
    assert r["severity"] == "SIGNIFICANT_DEFICIENCY"


def _test_deficiency_zero_assets_rule1():
    d = ControlDeficiency(
        deficiency_id="D1", control_id="C1",
        description="Test",
        estimated_financial_impact_kes=Decimal("100000"),
        total_assets_kes=Decimal("0"),
    )
    r = InternalControlsEngine.classify_deficiency(d)
    assert r["severity"] is None


def _test_coso_component_score_basic():
    ratings = {p: Decimal("80") for principles in COSO_PRINCIPLES.values()
               for p in principles}
    r = InternalControlsEngine.coso_component_score(ratings)
    assert r["overall_score"] == "80.00"
    assert r["missing_count"] == 0


def _test_coso_component_score_partial():
    ratings = {"P1_INTEGRITY_AND_ETHICAL_VALUES": Decimal("80")}
    r = InternalControlsEngine.coso_component_score(ratings)
    assert r["component_scores"]["CONTROL_ENVIRONMENT"] is not None
    assert r["component_scores"]["RISK_ASSESSMENT"] is None


def _test_effectiveness_summary():
    test_results = [
        {"coso_component": "CONTROL_ACTIVITIES", "outcome": "EFFECTIVE"},
        {"coso_component": "CONTROL_ACTIVITIES", "outcome": "EFFECTIVE"},
        {"coso_component": "MONITORING_ACTIVITIES", "outcome": "INEFFECTIVE"},
    ]
    r = InternalControlsEngine.control_effectiveness_summary(test_results)
    assert r["total_effective"] == 2
    # 2/3 = 66.67%
    assert r["overall_effectiveness_pct"] == "66.67"


def _test_coso_components_byte_for_byte():
    expected = ("CONTROL_ENVIRONMENT", "RISK_ASSESSMENT", "CONTROL_ACTIVITIES",
                "INFORMATION_COMMUNICATION", "MONITORING_ACTIVITIES")
    for c in expected:
        assert c in COSO_COMPONENTS


def _test_total_principles_byte_for_byte():
    total = sum(len(p) for p in COSO_PRINCIPLES.values())
    assert total == TOTAL_COSO_PRINCIPLES == 17


def _test_sample_sizes_byte_for_byte():
    assert SAMPLE_SIZES_BY_RISK["LOW"] == 25
    assert SAMPLE_SIZES_BY_RISK["MEDIUM"] == 40
    assert SAMPLE_SIZES_BY_RISK["HIGH"] == 60
    assert SAMPLE_SIZES_BY_RISK["KEY"] == 90


def _test_tolerance_byte_for_byte():
    assert TOLERABLE_EXCEPTION_RATE_PCT["LOW"] == Decimal("10")
    assert TOLERABLE_EXCEPTION_RATE_PCT["KEY"] == Decimal("0")


def _test_severity_thresholds_byte_for_byte():
    assert SIGNIFICANT_DEFICIENCY_THRESHOLD_PCT == Decimal("1")
    assert MATERIAL_WEAKNESS_THRESHOLD_PCT == Decimal("5")


def _test_deficiency_severities_byte_for_byte():
    expected = ("DEFICIENCY", "SIGNIFICANT_DEFICIENCY", "MATERIAL_WEAKNESS")
    for s in expected:
        assert s in DEFICIENCY_SEVERITIES


def self_test() -> bool:
    tests = [
        _test_sample_size_low,
        _test_sample_size_key,
        _test_sample_size_unknown,
        _test_control_test_effective,
        _test_control_test_partially_effective,
        _test_control_test_ineffective,
        _test_control_test_sample_inadequate,
        _test_control_test_zero_sample_rule1,
        _test_control_test_missing_data_rule6,
        _test_deficiency_classification_basic,
        _test_deficiency_significant,
        _test_deficiency_material_weakness,
        _test_deficiency_escalates_no_compensating,
        _test_deficiency_zero_assets_rule1,
        _test_coso_component_score_basic,
        _test_coso_component_score_partial,
        _test_effectiveness_summary,
        _test_coso_components_byte_for_byte,
        _test_total_principles_byte_for_byte,
        _test_sample_sizes_byte_for_byte,
        _test_tolerance_byte_for_byte,
        _test_severity_thresholds_byte_for_byte,
        _test_deficiency_severities_byte_for_byte,
    ]
    print("=" * 60)
    print("Internal Controls Engine — Self-Tests (#82)")
    print("=" * 60)
    failed = 0
    for t in tests:
        try:
            t()
            print(f"  PASS  {t.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"  FAIL  {t.__name__}: {e}")
        except Exception as e:
            failed += 1
            print(f"  ERROR {t.__name__}: {e}")
    print("-" * 60)
    if failed == 0:
        print(f"  ALL {len(tests)} TESTS PASSED")
        return True
    print(f"  {failed}/{len(tests)} FAILED")
    return False


if __name__ == "__main__":
    import sys
    sys.exit(0 if self_test() else 1)
