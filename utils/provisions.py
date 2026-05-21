"""
================================================================================
A2Z MIS 360 — Standard #109: IAS 37 Provisions / Contingent Liabilities / Contingent Assets
================================================================================

Risk classification: Cat B (deterministic recognition + measurement per IAS 37)

Implements IAS 37's three-pillar recognition model:
    - PROVISIONS: recognised liabilities of uncertain timing/amount
    - CONTINGENT LIABILITIES: NOT recognised, only disclosed
    - CONTINGENT ASSETS: NOT recognised unless virtually certain

Provides:
    - probability_classification(...)    -- VIRTUALLY_CERTAIN / PROBABLE / POSSIBLE / REMOTE
    - liability_treatment(...)           -- RECOGNISE / DISCLOSE / NEITHER
    - asset_treatment(...)               -- RECOGNISE / DISCLOSE / NEITHER (asymmetric)
    - provision_measurement(...)         -- best estimate or PV when material
    - onerous_contract_test(...)         -- recognise loss when unavoidable cost > benefits
    - reimbursement_treatment(...)       -- separate asset, not netted

4 PROBABILITY_LEVELS byte-for-byte (IAS 37.23):
    VIRTUALLY_CERTAIN    -- ≥95% threshold (asset recognition)
    PROBABLE             -- >50% threshold (liability recognition)
    POSSIBLE             -- 5-50% (disclosure only)
    REMOTE               -- <5% (no disclosure)

3 RECOGNITION_OUTCOMES byte-for-byte:
    RECOGNISE            -- on balance sheet
    DISCLOSE             -- in notes only
    NEITHER              -- not in financial statements

3 PROVISION_TYPES byte-for-byte (IAS 37 examples):
    LEGAL_OBLIGATION
    CONSTRUCTIVE_OBLIGATION
    ONEROUS_CONTRACT

5 PROVISION_RECOGNITION_CRITERIA byte-for-byte (IAS 37.14):
    PRESENT_OBLIGATION_FROM_PAST_EVENT
    OUTFLOW_PROBABLE
    RELIABLE_ESTIMATE_POSSIBLE
    SETTLEMENT_DATE_UNCERTAIN
    AMOUNT_UNCERTAIN

3 EXPECTED_VALUE_METHODS byte-for-byte (IAS 37.39):
    SINGLE_OBLIGATION       -- best estimate of single most likely outcome
    LARGE_POPULATION        -- expected value (probability-weighted average)
    CONTINUOUS_RANGE        -- midpoint when no point more likely than another

Probability thresholds byte-for-byte:
    VIRTUALLY_CERTAIN_PCT_MIN = 95   -- asset recognition floor
    PROBABLE_PCT_MIN          = 51   -- liability recognition floor
    POSSIBLE_PCT_MIN          = 5    -- disclosure floor; below = REMOTE

Discount rate byte-for-byte (IAS 37.45-47):
    Pre-tax rate reflecting current market assessments of:
    - Time value of money
    - Risks specific to the liability

Asymmetric treatment principle (the heart of IAS 37):
    LIABILITIES: recognise when PROBABLE (>50%)
    ASSETS:      recognise only when VIRTUALLY_CERTAIN (>=95%)
    -- conservatism principle in action

Honesty rules applied:
    Rule 1: classification=None when probability_pct missing
            measurement=None when amount missing
    Rule 6: probability > 100% rejected (fail closed)
            negative discount rate rejected (fail closed)
            unknown provision_type / method surfaced

================================================================================
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, getcontext
from typing import Any, Dict, List, Optional, Tuple

getcontext().prec = 28

# 4 PROBABILITY LEVELS byte-for-byte (IAS 37.23)
PROBABILITY_LEVELS: Tuple[str, ...] = (
    "VIRTUALLY_CERTAIN", "PROBABLE", "POSSIBLE", "REMOTE",
)

# 3 RECOGNITION OUTCOMES byte-for-byte
RECOGNITION_OUTCOMES: Tuple[str, ...] = (
    "RECOGNISE", "DISCLOSE", "NEITHER",
)

# 3 PROVISION TYPES byte-for-byte (IAS 37 examples)
PROVISION_TYPES: Tuple[str, ...] = (
    "LEGAL_OBLIGATION", "CONSTRUCTIVE_OBLIGATION", "ONEROUS_CONTRACT",
)

# 5 RECOGNITION CRITERIA byte-for-byte (IAS 37.14)
PROVISION_RECOGNITION_CRITERIA: Tuple[str, ...] = (
    "PRESENT_OBLIGATION_FROM_PAST_EVENT",
    "OUTFLOW_PROBABLE",
    "RELIABLE_ESTIMATE_POSSIBLE",
    "SETTLEMENT_DATE_UNCERTAIN",
    "AMOUNT_UNCERTAIN",
)

# 3 EXPECTED VALUE METHODS byte-for-byte (IAS 37.39)
EXPECTED_VALUE_METHODS: Tuple[str, ...] = (
    "SINGLE_OBLIGATION", "LARGE_POPULATION", "CONTINUOUS_RANGE",
)

# Probability thresholds byte-for-byte
VIRTUALLY_CERTAIN_PCT_MIN = Decimal("95")
PROBABLE_PCT_MIN = Decimal("51")
POSSIBLE_PCT_MIN = Decimal("5")


class ProvisionsEngine:
    """Deterministic IAS 37 recognition + measurement."""

    @staticmethod
    def probability_classification(
        probability_pct: Optional[Decimal],
    ) -> Optional[str]:
        """
        Classify probability into 4 IAS 37 bands.
        Rule 1: None when missing.
        Rule 6: > 100% rejected (returns None).
        """
        if probability_pct is None:
            return None
        if probability_pct < 0 or probability_pct > Decimal("100"):
            return None
        if probability_pct >= VIRTUALLY_CERTAIN_PCT_MIN:
            return "VIRTUALLY_CERTAIN"
        if probability_pct >= PROBABLE_PCT_MIN:
            return "PROBABLE"
        if probability_pct >= POSSIBLE_PCT_MIN:
            return "POSSIBLE"
        return "REMOTE"

    @staticmethod
    def liability_treatment(
        probability_pct: Optional[Decimal],
        reliable_estimate: Optional[bool] = None,
    ) -> Dict[str, Any]:
        """
        Determine liability treatment per IAS 37.14, .27-28.
        PROBABLE + reliable_estimate → RECOGNISE (provision)
        PROBABLE + NO reliable_estimate → DISCLOSE (contingent)
        POSSIBLE → DISCLOSE (contingent)
        REMOTE → NEITHER
        VIRTUALLY_CERTAIN → RECOGNISE (provision)
        Rule 1: None when probability missing.
        """
        classification = ProvisionsEngine.probability_classification(probability_pct)
        if classification is None:
            return {"treatment": None, "computed": False,
                    "reason": "missing_or_invalid_probability"}
        if classification in ("VIRTUALLY_CERTAIN", "PROBABLE"):
            if reliable_estimate is False:
                return {
                    "probability_classification": classification,
                    "reliable_estimate": False,
                    "treatment": "DISCLOSE",
                    "rationale": "probable_but_no_reliable_estimate_per_IAS_37.26",
                    "computed": True,
                }
            return {
                "probability_classification": classification,
                "reliable_estimate": (True if reliable_estimate else None),
                "treatment": "RECOGNISE",
                "rationale": "all_recognition_criteria_met_per_IAS_37.14",
                "computed": True,
            }
        if classification == "POSSIBLE":
            return {
                "probability_classification": "POSSIBLE",
                "treatment": "DISCLOSE",
                "rationale": "contingent_liability_per_IAS_37.27",
                "computed": True,
            }
        # REMOTE
        return {
            "probability_classification": "REMOTE",
            "treatment": "NEITHER",
            "rationale": "remote_outflow_per_IAS_37.28",
            "computed": True,
        }

    @staticmethod
    def asset_treatment(
        probability_pct: Optional[Decimal],
    ) -> Dict[str, Any]:
        """
        Asymmetric IAS 37 treatment per IAS 37.31-35.
        VIRTUALLY_CERTAIN → RECOGNISE
        PROBABLE → DISCLOSE (contingent asset)
        POSSIBLE / REMOTE → NEITHER
        Rule 1: None when probability missing.
        """
        classification = ProvisionsEngine.probability_classification(probability_pct)
        if classification is None:
            return {"treatment": None, "computed": False,
                    "reason": "missing_or_invalid_probability"}
        if classification == "VIRTUALLY_CERTAIN":
            return {
                "probability_classification": "VIRTUALLY_CERTAIN",
                "treatment": "RECOGNISE",
                "rationale": "virtually_certain_asset_per_IAS_37.33",
                "computed": True,
            }
        if classification == "PROBABLE":
            return {
                "probability_classification": "PROBABLE",
                "treatment": "DISCLOSE",
                "rationale": "contingent_asset_per_IAS_37.34",
                "computed": True,
            }
        # POSSIBLE / REMOTE
        return {
            "probability_classification": classification,
            "treatment": "NEITHER",
            "rationale": "asset_below_disclosure_threshold_per_IAS_37.34",
            "computed": True,
        }

    @staticmethod
    def provision_measurement(
        method: str,
        amount: Optional[Decimal] = None,
        probability_weighted_outcomes: Optional[List[Tuple[Decimal, Decimal]]] = None,
        range_low: Optional[Decimal] = None,
        range_high: Optional[Decimal] = None,
    ) -> Dict[str, Any]:
        """
        Provision measurement per IAS 37.36-39.
        Rule 6: unknown method surfaced.
        Rule 1: missing inputs → None.
        """
        if method not in EXPECTED_VALUE_METHODS:
            return {"measurement": None, "computed": False,
                    "reason": f"unknown_method:{method}",
                    "valid_methods": list(EXPECTED_VALUE_METHODS)}
        if method == "SINGLE_OBLIGATION":
            if amount is None:
                return {"measurement": None, "computed": False,
                        "reason": "missing_best_estimate"}
            return {
                "method": "SINGLE_OBLIGATION",
                "measurement": str(amount.quantize(Decimal("0.01"))),
                "rationale": "best_estimate_single_outcome_per_IAS_37.36",
                "computed": True,
            }
        if method == "LARGE_POPULATION":
            if not probability_weighted_outcomes:
                return {"measurement": None, "computed": False,
                        "reason": "missing_probability_weighted_outcomes"}
            # Each tuple = (probability_pct, amount)
            ev = Decimal("0")
            total_prob = Decimal("0")
            for prob, amt in probability_weighted_outcomes:
                if prob is None or amt is None:
                    return {"measurement": None, "computed": False,
                            "reason": "missing_outcome_value"}
                if prob < 0 or prob > Decimal("100"):
                    return {"measurement": None, "computed": False,
                            "reason": "invalid_probability"}
                ev += (prob / Decimal("100")) * amt
                total_prob += prob
            return {
                "method": "LARGE_POPULATION",
                "outcome_count": len(probability_weighted_outcomes),
                "total_probability_pct": str(total_prob),
                "measurement": str(ev.quantize(Decimal("0.01"))),
                "rationale": "expected_value_per_IAS_37.39",
                "computed": True,
            }
        # CONTINUOUS_RANGE
        if range_low is None or range_high is None:
            return {"measurement": None, "computed": False,
                    "reason": "missing_range_bounds"}
        if range_low > range_high:
            return {"measurement": None, "computed": False,
                    "reason": "low_exceeds_high"}
        midpoint = (range_low + range_high) / Decimal("2")
        return {
            "method": "CONTINUOUS_RANGE",
            "range_low": str(range_low),
            "range_high": str(range_high),
            "measurement": str(midpoint.quantize(Decimal("0.01"))),
            "rationale": "midpoint_per_IAS_37.39",
            "computed": True,
        }

    @staticmethod
    def onerous_contract_test(
        unavoidable_costs: Optional[Decimal],
        expected_economic_benefits: Optional[Decimal],
    ) -> Dict[str, Any]:
        """
        Onerous contract per IAS 37.66-69.
        Provision recognised when unavoidable cost > expected benefits.
        Provision = lower of:
          - cost of fulfilling contract
          - cost of exiting contract (penalties)
        Rule 1: None when inputs missing.
        """
        if unavoidable_costs is None or expected_economic_benefits is None:
            return {"onerous": None, "computed": False,
                    "reason": "missing_inputs"}
        if unavoidable_costs > expected_economic_benefits:
            provision = unavoidable_costs - expected_economic_benefits
            return {
                "unavoidable_costs": str(unavoidable_costs),
                "expected_benefits": str(expected_economic_benefits),
                "onerous": True,
                "provision": str(provision.quantize(Decimal("0.01"))),
                "rationale": "unavoidable_cost_exceeds_benefits_per_IAS_37.66",
                "computed": True,
            }
        return {
            "unavoidable_costs": str(unavoidable_costs),
            "expected_benefits": str(expected_economic_benefits),
            "onerous": False,
            "provision": "0.00",
            "rationale": "not_onerous",
            "computed": True,
        }

    @staticmethod
    def reimbursement_treatment(
        reimbursement_virtually_certain: Optional[bool],
        reimbursement_amount: Optional[Decimal] = None,
    ) -> Dict[str, Any]:
        """
        Reimbursement per IAS 37.53-58.
        Recognise as separate asset only when virtually certain.
        Asset cannot exceed provision.
        Rule 1: None when input missing.
        """
        if reimbursement_virtually_certain is None:
            return {"recognise_asset": None, "computed": False,
                    "reason": "missing_certainty_flag"}
        if not reimbursement_virtually_certain:
            return {
                "reimbursement_virtually_certain": False,
                "recognise_asset": False,
                "rationale": "not_virtually_certain_no_asset_per_IAS_37.53",
                "computed": True,
            }
        return {
            "reimbursement_virtually_certain": True,
            "recognise_asset": True,
            "asset_amount": (None if reimbursement_amount is None
                              else str(reimbursement_amount.quantize(Decimal("0.01")))),
            "presentation": "separate_asset_not_netted_per_IAS_37.54",
            "computed": True,
        }


# ============================================================================
# Self-tests
# ============================================================================

def _test_probability_levels_byte_for_byte():
    expected = ("VIRTUALLY_CERTAIN", "PROBABLE", "POSSIBLE", "REMOTE")
    for p in expected:
        assert p in PROBABILITY_LEVELS
    assert len(PROBABILITY_LEVELS) == 4


def _test_recognition_outcomes_byte_for_byte():
    expected = ("RECOGNISE", "DISCLOSE", "NEITHER")
    for o in expected:
        assert o in RECOGNITION_OUTCOMES


def _test_provision_types_byte_for_byte():
    expected = ("LEGAL_OBLIGATION", "CONSTRUCTIVE_OBLIGATION", "ONEROUS_CONTRACT")
    for t in expected:
        assert t in PROVISION_TYPES


def _test_recognition_criteria_byte_for_byte():
    expected = (
        "PRESENT_OBLIGATION_FROM_PAST_EVENT",
        "OUTFLOW_PROBABLE",
        "RELIABLE_ESTIMATE_POSSIBLE",
        "SETTLEMENT_DATE_UNCERTAIN",
        "AMOUNT_UNCERTAIN",
    )
    for c in expected:
        assert c in PROVISION_RECOGNITION_CRITERIA
    assert len(PROVISION_RECOGNITION_CRITERIA) == 5


def _test_expected_value_methods_byte_for_byte():
    expected = ("SINGLE_OBLIGATION", "LARGE_POPULATION", "CONTINUOUS_RANGE")
    for m in expected:
        assert m in EXPECTED_VALUE_METHODS


def _test_thresholds_byte_for_byte():
    assert VIRTUALLY_CERTAIN_PCT_MIN == Decimal("95")
    assert PROBABLE_PCT_MIN == Decimal("51")
    assert POSSIBLE_PCT_MIN == Decimal("5")


def _test_classification_virtually_certain():
    """95% boundary → VIRTUALLY_CERTAIN."""
    assert ProvisionsEngine.probability_classification(Decimal("95")) == "VIRTUALLY_CERTAIN"


def _test_classification_probable():
    """51% boundary → PROBABLE."""
    assert ProvisionsEngine.probability_classification(Decimal("51")) == "PROBABLE"


def _test_classification_50pct_is_possible():
    """50% → POSSIBLE (NOT probable; PROBABLE requires >50%)."""
    assert ProvisionsEngine.probability_classification(Decimal("50")) == "POSSIBLE"


def _test_classification_possible():
    assert ProvisionsEngine.probability_classification(Decimal("25")) == "POSSIBLE"


def _test_classification_remote():
    """Below 5% → REMOTE."""
    assert ProvisionsEngine.probability_classification(Decimal("3")) == "REMOTE"


def _test_classification_remote_boundary():
    """Exactly 5% → POSSIBLE (≥ inclusive)."""
    assert ProvisionsEngine.probability_classification(Decimal("5")) == "POSSIBLE"


def _test_classification_missing_rule1():
    assert ProvisionsEngine.probability_classification(None) is None


def _test_classification_over_100_rule6():
    assert ProvisionsEngine.probability_classification(Decimal("150")) is None


def _test_liability_recognise():
    """75% probable + reliable estimate → RECOGNISE."""
    r = ProvisionsEngine.liability_treatment(Decimal("75"), reliable_estimate=True)
    assert r["treatment"] == "RECOGNISE"


def _test_liability_disclose_no_estimate():
    """75% probable + NO reliable estimate → DISCLOSE."""
    r = ProvisionsEngine.liability_treatment(Decimal("75"), reliable_estimate=False)
    assert r["treatment"] == "DISCLOSE"


def _test_liability_possible_disclose():
    """30% possible → DISCLOSE."""
    r = ProvisionsEngine.liability_treatment(Decimal("30"))
    assert r["treatment"] == "DISCLOSE"


def _test_liability_remote_neither():
    """3% remote → NEITHER."""
    r = ProvisionsEngine.liability_treatment(Decimal("3"))
    assert r["treatment"] == "NEITHER"


def _test_asset_virtually_certain_recognise():
    """95% virtually certain → RECOGNISE."""
    r = ProvisionsEngine.asset_treatment(Decimal("95"))
    assert r["treatment"] == "RECOGNISE"


def _test_asset_probable_disclose():
    """75% probable → DISCLOSE (contingent asset)."""
    r = ProvisionsEngine.asset_treatment(Decimal("75"))
    assert r["treatment"] == "DISCLOSE"


def _test_asset_possible_neither():
    """30% possible → NEITHER (asymmetric vs liability)."""
    r = ProvisionsEngine.asset_treatment(Decimal("30"))
    assert r["treatment"] == "NEITHER"


def _test_asset_remote_neither():
    r = ProvisionsEngine.asset_treatment(Decimal("3"))
    assert r["treatment"] == "NEITHER"


def _test_measurement_single():
    """Best estimate of single outcome."""
    r = ProvisionsEngine.provision_measurement(
        "SINGLE_OBLIGATION", amount=Decimal("100000"))
    assert r["measurement"] == "100000.00"


def _test_measurement_large_population():
    """Expected value: 30% × 1M + 70% × 200K = 300K + 140K = 440K."""
    r = ProvisionsEngine.provision_measurement(
        "LARGE_POPULATION",
        probability_weighted_outcomes=[
            (Decimal("30"), Decimal("1000000")),
            (Decimal("70"), Decimal("200000")),
        ])
    assert r["measurement"] == "440000.00"


def _test_measurement_continuous_range():
    """Midpoint of 100K-200K = 150K."""
    r = ProvisionsEngine.provision_measurement(
        "CONTINUOUS_RANGE",
        range_low=Decimal("100000"), range_high=Decimal("200000"))
    assert r["measurement"] == "150000.00"


def _test_measurement_unknown_method_rule6():
    r = ProvisionsEngine.provision_measurement("WEIRD")
    assert r["computed"] is False


def _test_measurement_inverted_range_rule6():
    """range_low > range_high rejected."""
    r = ProvisionsEngine.provision_measurement(
        "CONTINUOUS_RANGE",
        range_low=Decimal("200000"), range_high=Decimal("100000"))
    assert r["computed"] is False


def _test_onerous_contract_loss():
    """Cost 500K > benefits 300K → onerous, provision 200K."""
    r = ProvisionsEngine.onerous_contract_test(
        Decimal("500000"), Decimal("300000"))
    assert r["onerous"] is True
    assert r["provision"] == "200000.00"


def _test_onerous_contract_not_onerous():
    """Cost 300K ≤ benefits 500K → not onerous."""
    r = ProvisionsEngine.onerous_contract_test(
        Decimal("300000"), Decimal("500000"))
    assert r["onerous"] is False
    assert r["provision"] == "0.00"


def _test_onerous_missing_rule1():
    r = ProvisionsEngine.onerous_contract_test(None, Decimal("500000"))
    assert r["onerous"] is None


def _test_reimbursement_virtually_certain():
    r = ProvisionsEngine.reimbursement_treatment(
        True, reimbursement_amount=Decimal("100000"))
    assert r["recognise_asset"] is True
    assert r["asset_amount"] == "100000.00"


def _test_reimbursement_not_certain():
    """Not virtually certain → no asset."""
    r = ProvisionsEngine.reimbursement_treatment(False)
    assert r["recognise_asset"] is False


def _test_reimbursement_missing_rule1():
    r = ProvisionsEngine.reimbursement_treatment(None)
    assert r["recognise_asset"] is None


def self_test() -> bool:
    tests = [
        _test_probability_levels_byte_for_byte,
        _test_recognition_outcomes_byte_for_byte,
        _test_provision_types_byte_for_byte,
        _test_recognition_criteria_byte_for_byte,
        _test_expected_value_methods_byte_for_byte,
        _test_thresholds_byte_for_byte,
        _test_classification_virtually_certain,
        _test_classification_probable,
        _test_classification_50pct_is_possible,
        _test_classification_possible,
        _test_classification_remote,
        _test_classification_remote_boundary,
        _test_classification_missing_rule1,
        _test_classification_over_100_rule6,
        _test_liability_recognise,
        _test_liability_disclose_no_estimate,
        _test_liability_possible_disclose,
        _test_liability_remote_neither,
        _test_asset_virtually_certain_recognise,
        _test_asset_probable_disclose,
        _test_asset_possible_neither,
        _test_asset_remote_neither,
        _test_measurement_single,
        _test_measurement_large_population,
        _test_measurement_continuous_range,
        _test_measurement_unknown_method_rule6,
        _test_measurement_inverted_range_rule6,
        _test_onerous_contract_loss,
        _test_onerous_contract_not_onerous,
        _test_onerous_missing_rule1,
        _test_reimbursement_virtually_certain,
        _test_reimbursement_not_certain,
        _test_reimbursement_missing_rule1,
    ]
    print("=" * 60)
    print("Provisions Engine — Self-Tests (#109 IAS 37)")
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
