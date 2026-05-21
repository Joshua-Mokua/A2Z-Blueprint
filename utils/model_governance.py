"""utils/model_governance.py — v10.28 Model Governance arc batch 1.

╔════════════════════════════════════════════════════════════════════════╗
║  MODEL GOVERNANCE FOUNDATION                                           ║
║  Cat A pre-requisite — safety net before ANY ML pilot                  ║
╠════════════════════════════════════════════════════════════════════════╣
║  Risk class: Cat A (model failures cascade to credit decisions, capital║
║              calculations, regulatory reporting; uncontrolled ML       ║
║              creates fairness/compliance landmines)                     ║
║  Implements 5 of 10 Model Governance standards from registry:           ║
║    ENH-259: Model Risk Governance Framework                             ║
║    ENH-261: Continuous Model Monitoring (drift detection)               ║
║    ENH-262: AI Model Validation & Testing Suite                         ║
║    ENH-263: Credit Decision Explainability (Enhanced)                   ║
║    ENH-265: Continuous Bias Monitoring                                  ║
╠════════════════════════════════════════════════════════════════════════╣
║  Regulatory provenance:                                                 ║
║    Federal Reserve SR 11-7 — model risk management                      ║
║    OCC 2011-12 — sound practices for model risk management              ║
║    PRA SS1/23 — model risk management principles (UK)                   ║
║    EU AI Act (Regulation 2024/1689) — Art 9, 13, 14, 15                 ║
║    NIST AI Risk Management Framework (AI RMF 1.0)                       ║
║    CFPB Reg B (ECOA) — Appendix C adverse action codes                  ║
║    CBK CRMF April 2021 §5 — operational risk includes model risk       ║
║    Basel BCBS 449 — fintech developments for banks                      ║
║    ISO/IEC 23894:2023 — AI Risk Management                              ║
║    Singapore MAS FEAT — Fairness Ethics Accountability Transparency    ║
║    Population Stability Index (Siddiqi 2017) — credit scoring         ║
║    Kolmogorov-Smirnov test (Kolmogorov 1933, Smirnov 1948)             ║
║    Wasserstein distance (Vaserstein 1969) — distribution comparison    ║
║    SHAP (Lundberg & Lee 2017) — Shapley additive explanations          ║
║    LIME (Ribeiro et al. 2016) — local interpretable model-agnostic     ║
║    EEOC 4/5ths rule — disparate impact (29 CFR §1607.4)                 ║
╠════════════════════════════════════════════════════════════════════════╣
║  Composes with v10.27 audit_trail_certification — every model         ║
║  governance event flows into the cryptographic audit chain.            ║
║                                                                         ║
║  Honesty Rule 1: drift findings show method + threshold + sample;     ║
║  bias findings show protected class + 4/5ths verdict; lifecycle      ║
║  transitions block on missing validation evidence.                     ║
║  Honesty Rule 7: SHAP/LIME explainers are callable hooks; without      ║
║  hook wired, framework reports REQUIRES_PROVIDER, never fabricates.   ║
╚════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

import math
import sys
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, getcontext
from enum import Enum
from typing import (
    Any, Callable, Dict, FrozenSet, List, Mapping, Optional, Sequence, Tuple)

getcontext().prec = 28

SPEC_DEVIATION_NOTE = (
    "SHAP / LIME / SHAP-equivalent ML explainers are callable hooks per "
    "Rule 7. Without injected explainer, explanation requests return "
    "REQUIRES_PROVIDER verdict — framework never fabricates a SHAP value. "
    "Bias detection runs deterministic statistical tests (4/5ths rule, "
    "demographic parity, equal opportunity); ML-based bias detectors are "
    "additionally hookable."
)


# ════════════════════════════════════════════════════════════════════════
# Model Inventory + Taxonomy (ENH-259)
# ════════════════════════════════════════════════════════════════════════

class ModelType(Enum):
    """Categories of models used across the bank."""
    CREDIT_SCORECARD = "CREDIT_SCORECARD"          # logistic regression, scorecards
    CREDIT_AI = "CREDIT_AI"                          # GBM/NN credit models
    FRAUD_DETECTION = "FRAUD_DETECTION"
    AML_SANCTIONS = "AML_SANCTIONS"
    KYC_RISK = "KYC_RISK"
    PRICING = "PRICING"
    COLLECTIONS = "COLLECTIONS"
    CHURN_PROPENSITY = "CHURN_PROPENSITY"
    CROSS_SELL = "CROSS_SELL"
    NEXT_BEST_ACTION = "NEXT_BEST_ACTION"
    LIQUIDITY = "LIQUIDITY"
    MARKET_RISK_VAR = "MARKET_RISK_VAR"
    OPERATIONAL_RISK = "OPERATIONAL_RISK"
    CLIMATE_PD_OVERLAY = "CLIMATE_PD_OVERLAY"     # from v10.6-v10.10
    REGULATORY_REPORTING = "REGULATORY_REPORTING"
    OTHER = "OTHER"


class ModelTier(Enum):
    """Risk-tiered classification per SR 11-7 + EU AI Act mapping."""
    TIER_1_HIGH = "TIER_1_HIGH"        # material capital/credit/reg impact
    TIER_2_MEDIUM = "TIER_2_MEDIUM"    # supports business processes
    TIER_3_LOW = "TIER_3_LOW"          # standalone analytics/descriptive


# EU AI Act risk classification (separate from SR 11-7 tier)
class EUAIActRiskCategory(Enum):
    UNACCEPTABLE = "UNACCEPTABLE"          # banned uses (social scoring, etc.)
    HIGH_RISK = "HIGH_RISK"                  # Annex III — credit scoring, etc.
    LIMITED_RISK = "LIMITED_RISK"          # transparency obligations
    MINIMAL_RISK = "MINIMAL_RISK"          # no obligations


# Validation cadence per tier (months)
DEFAULT_VALIDATION_CADENCE_MONTHS: Mapping[ModelTier, int] = {
    ModelTier.TIER_1_HIGH: 12,             # annual
    ModelTier.TIER_2_MEDIUM: 24,           # biennial
    ModelTier.TIER_3_LOW: 36,              # triennial
}


class ModelLifecycleState(Enum):
    """States in a model's governance lifecycle."""
    DEVELOPMENT = "DEVELOPMENT"
    INTERNAL_TESTING = "INTERNAL_TESTING"
    INDEPENDENT_VALIDATION = "INDEPENDENT_VALIDATION"
    APPROVED_FOR_PRODUCTION = "APPROVED_FOR_PRODUCTION"
    IN_PRODUCTION = "IN_PRODUCTION"
    UNDER_REMEDIATION = "UNDER_REMEDIATION"   # drift/issue detected
    SUSPENDED = "SUSPENDED"                    # paused pending review
    RETIRED = "RETIRED"                        # terminal


# Allowed transitions per SR 11-7 governance principles
ALLOWED_LIFECYCLE_TRANSITIONS: Mapping[
    ModelLifecycleState, Tuple[ModelLifecycleState, ...]] = {
    ModelLifecycleState.DEVELOPMENT: (
        ModelLifecycleState.INTERNAL_TESTING,
        ModelLifecycleState.RETIRED),
    ModelLifecycleState.INTERNAL_TESTING: (
        ModelLifecycleState.INDEPENDENT_VALIDATION,
        ModelLifecycleState.DEVELOPMENT,
        ModelLifecycleState.RETIRED),
    ModelLifecycleState.INDEPENDENT_VALIDATION: (
        ModelLifecycleState.APPROVED_FOR_PRODUCTION,
        ModelLifecycleState.DEVELOPMENT,
        ModelLifecycleState.RETIRED),
    ModelLifecycleState.APPROVED_FOR_PRODUCTION: (
        ModelLifecycleState.IN_PRODUCTION,
        ModelLifecycleState.SUSPENDED,
        ModelLifecycleState.RETIRED),
    ModelLifecycleState.IN_PRODUCTION: (
        ModelLifecycleState.UNDER_REMEDIATION,
        ModelLifecycleState.SUSPENDED,
        ModelLifecycleState.RETIRED),
    ModelLifecycleState.UNDER_REMEDIATION: (
        ModelLifecycleState.IN_PRODUCTION,
        ModelLifecycleState.SUSPENDED,
        ModelLifecycleState.RETIRED),
    ModelLifecycleState.SUSPENDED: (
        ModelLifecycleState.UNDER_REMEDIATION,
        ModelLifecycleState.IN_PRODUCTION,
        ModelLifecycleState.RETIRED),
    ModelLifecycleState.RETIRED: (),    # terminal
}


def is_valid_lifecycle_transition(
    from_state: ModelLifecycleState,
    to_state: ModelLifecycleState,
) -> bool:
    return to_state in ALLOWED_LIFECYCLE_TRANSITIONS.get(from_state, ())


@dataclass(frozen=True)
class Model:
    """A registered model in the inventory."""
    model_id: str
    model_name: str
    model_type: ModelType
    model_tier: ModelTier
    eu_ai_act_category: EUAIActRiskCategory
    current_state: ModelLifecycleState
    owner_business_unit: str
    owner_user_id: str
    development_date: str                  # ISO-8601
    deployment_date: Optional[str] = None
    last_validation_date: Optional[str] = None
    next_validation_due: Optional[str] = None
    is_vendor_model: bool = False
    vendor_name: Optional[str] = None
    description: str = ""
    feature_count: int = 0
    training_sample_size: int = 0
    framework_refs: Tuple[str, ...] = ()
    notes: str = ""

    def is_validation_overdue(self, *, as_of: date) -> bool:
        if self.next_validation_due is None:
            return False
        try:
            due = date.fromisoformat(self.next_validation_due)
        except ValueError:
            return False
        return as_of > due

    def requires_independent_validation(self) -> bool:
        """SR 11-7: Tier 1 + Tier 2 require independent validation."""
        return self.model_tier in (
            ModelTier.TIER_1_HIGH, ModelTier.TIER_2_MEDIUM)


# ════════════════════════════════════════════════════════════════════════
# Drift Detection (ENH-261)
# ════════════════════════════════════════════════════════════════════════

class DriftDetectionMethod(Enum):
    """Statistical methods for distribution drift."""
    PSI = "PSI"                            # Population Stability Index
    KOLMOGOROV_SMIRNOV = "KS"
    WASSERSTEIN = "WASSERSTEIN"            # Earth mover's distance
    CHI_SQUARE = "CHI_SQUARE"
    JENSEN_SHANNON = "JENSEN_SHANNON"
    PERFORMANCE_AUC = "PERFORMANCE_AUC"   # output-distribution AUC drift
    PERFORMANCE_RMSE = "PERFORMANCE_RMSE"


class DriftSeverity(Enum):
    NO_DRIFT = "NO_DRIFT"
    SMALL_SHIFT = "SMALL_SHIFT"
    SIGNIFICANT_SHIFT = "SIGNIFICANT_SHIFT"
    MAJOR_DRIFT = "MAJOR_DRIFT"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


# Industry-standard PSI thresholds (Siddiqi 2017, credit scoring practice)
PSI_NO_DRIFT_THRESHOLD = Decimal("0.10")        # < 0.10 stable
PSI_SMALL_SHIFT_THRESHOLD = Decimal("0.20")      # 0.10 - 0.20 minor
PSI_SIGNIFICANT_THRESHOLD = Decimal("0.25")     # > 0.20 significant


@dataclass(frozen=True)
class DriftResult:
    """Outcome of one drift detection test."""
    test_id: str
    model_id: str
    feature_name: Optional[str]            # None for output drift
    method: DriftDetectionMethod
    statistic_value: Decimal
    threshold_used: Decimal
    severity: DriftSeverity
    n_baseline: int
    n_current: int
    test_date: str
    notes: str = ""

    def is_actionable(self) -> bool:
        """Drift requires remediation action."""
        return self.severity in (
            DriftSeverity.SIGNIFICANT_SHIFT,
            DriftSeverity.MAJOR_DRIFT)


def compute_psi(
    *,
    baseline_distribution: Sequence[Decimal],   # bin proportions sum to 1
    current_distribution: Sequence[Decimal],
) -> Decimal:
    """Compute Population Stability Index.

    PSI = sum over bins of (current_pct - baseline_pct) * ln(current/baseline)

    Per Siddiqi 2017: < 0.10 stable, 0.10-0.20 minor shift, > 0.20 significant.
    """
    if len(baseline_distribution) != len(current_distribution):
        raise ValueError(
            f"baseline + current must have same number of bins; "
            f"got {len(baseline_distribution)} vs "
            f"{len(current_distribution)}")
    if not baseline_distribution:
        return Decimal("0")

    psi = Decimal("0")
    epsilon = Decimal("0.0001")    # smoothing for empty bins
    for b, c in zip(baseline_distribution, current_distribution):
        b_safe = max(b, epsilon)
        c_safe = max(c, epsilon)
        ratio = c_safe / b_safe
        # PSI uses natural log
        ln_ratio = Decimal(str(math.log(float(ratio))))
        psi += (c_safe - b_safe) * ln_ratio
    return psi


def detect_drift_psi(
    *,
    test_id: str,
    model_id: str,
    feature_name: Optional[str],
    baseline_distribution: Sequence[Decimal],
    current_distribution: Sequence[Decimal],
    n_baseline: int,
    n_current: int,
    test_date: str,
) -> DriftResult:
    """Run PSI drift detection."""
    if n_baseline < 100 or n_current < 100:
        return DriftResult(
            test_id=test_id, model_id=model_id,
            feature_name=feature_name,
            method=DriftDetectionMethod.PSI,
            statistic_value=Decimal("0"),
            threshold_used=PSI_SIGNIFICANT_THRESHOLD,
            severity=DriftSeverity.INSUFFICIENT_DATA,
            n_baseline=n_baseline, n_current=n_current,
            test_date=test_date,
            notes=f"insufficient samples (need ≥100 each)")

    psi = compute_psi(
        baseline_distribution=baseline_distribution,
        current_distribution=current_distribution)

    if psi < PSI_NO_DRIFT_THRESHOLD:
        sev = DriftSeverity.NO_DRIFT
    elif psi < PSI_SMALL_SHIFT_THRESHOLD:
        sev = DriftSeverity.SMALL_SHIFT
    elif psi < PSI_SIGNIFICANT_THRESHOLD:
        sev = DriftSeverity.SIGNIFICANT_SHIFT
    else:
        sev = DriftSeverity.MAJOR_DRIFT

    return DriftResult(
        test_id=test_id, model_id=model_id,
        feature_name=feature_name,
        method=DriftDetectionMethod.PSI,
        statistic_value=psi,
        threshold_used=PSI_SIGNIFICANT_THRESHOLD,
        severity=sev,
        n_baseline=n_baseline, n_current=n_current,
        test_date=test_date,
        notes=f"PSI = {psi:.4f}")


def compute_ks_statistic(
    *,
    baseline_samples: Sequence[Decimal],
    current_samples: Sequence[Decimal],
) -> Decimal:
    """Compute Kolmogorov-Smirnov statistic.

    KS = max |F_baseline(x) - F_current(x)| over all x.
    """
    if not baseline_samples or not current_samples:
        return Decimal("0")
    # Sort both samples
    sorted_b = sorted(baseline_samples)
    sorted_c = sorted(current_samples)
    nb = len(sorted_b)
    nc = len(sorted_c)
    # Walk through merged sample, computing CDF differences
    all_values = sorted(set(list(sorted_b) + list(sorted_c)))
    max_diff = Decimal("0")
    for v in all_values:
        cdf_b = Decimal(sum(1 for x in sorted_b if x <= v)) / Decimal(nb)
        cdf_c = Decimal(sum(1 for x in sorted_c if x <= v)) / Decimal(nc)
        diff = abs(cdf_b - cdf_c)
        if diff > max_diff:
            max_diff = diff
    return max_diff


# KS critical value at α=0.05 (Smirnov 1948 — large-sample approximation)
def ks_critical_value(*, n_baseline: int, n_current: int,
                          alpha: Decimal = Decimal("0.05")) -> Decimal:
    """Critical KS value at significance α."""
    if n_baseline == 0 or n_current == 0:
        return Decimal("1")
    # c(α) values: 0.05 → 1.36, 0.01 → 1.63
    c_alpha = Decimal("1.36") if alpha >= Decimal("0.05") else Decimal("1.63")
    factor = Decimal(str(math.sqrt(
        (n_baseline + n_current) / (n_baseline * n_current))))
    return c_alpha * factor


def detect_drift_ks(
    *,
    test_id: str,
    model_id: str,
    feature_name: Optional[str],
    baseline_samples: Sequence[Decimal],
    current_samples: Sequence[Decimal],
    test_date: str,
    alpha: Decimal = Decimal("0.05"),
) -> DriftResult:
    """Run Kolmogorov-Smirnov drift detection."""
    nb = len(baseline_samples)
    nc = len(current_samples)
    if nb < 30 or nc < 30:
        return DriftResult(
            test_id=test_id, model_id=model_id,
            feature_name=feature_name,
            method=DriftDetectionMethod.KOLMOGOROV_SMIRNOV,
            statistic_value=Decimal("0"),
            threshold_used=Decimal("0"),
            severity=DriftSeverity.INSUFFICIENT_DATA,
            n_baseline=nb, n_current=nc,
            test_date=test_date,
            notes=f"insufficient samples (need ≥30 each)")

    ks = compute_ks_statistic(
        baseline_samples=baseline_samples,
        current_samples=current_samples)
    critical = ks_critical_value(
        n_baseline=nb, n_current=nc, alpha=alpha)

    if ks < critical:
        sev = DriftSeverity.NO_DRIFT
    elif ks < critical * Decimal("1.5"):
        sev = DriftSeverity.SMALL_SHIFT
    elif ks < critical * Decimal("2"):
        sev = DriftSeverity.SIGNIFICANT_SHIFT
    else:
        sev = DriftSeverity.MAJOR_DRIFT

    return DriftResult(
        test_id=test_id, model_id=model_id,
        feature_name=feature_name,
        method=DriftDetectionMethod.KOLMOGOROV_SMIRNOV,
        statistic_value=ks, threshold_used=critical,
        severity=sev, n_baseline=nb, n_current=nc,
        test_date=test_date,
        notes=f"KS = {ks:.4f}; critical = {critical:.4f} at α={alpha}")


def compute_wasserstein_distance(
    *,
    baseline_samples: Sequence[Decimal],
    current_samples: Sequence[Decimal],
) -> Decimal:
    """1-Wasserstein distance (Earth Mover's Distance) for 1D distributions.

    For 1D, W₁ = ∫ |F_baseline(x) - F_current(x)| dx.
    Approximated as sum over sorted samples of absolute CDF differences.
    """
    if not baseline_samples or not current_samples:
        return Decimal("0")
    sorted_b = sorted(baseline_samples)
    sorted_c = sorted(current_samples)
    # Approximate integral using equal-weight sampled points
    n = max(len(sorted_b), len(sorted_c))
    total = Decimal("0")
    for i in range(n):
        # Quantile-based approximation
        idx_b = min(int(i * len(sorted_b) / n), len(sorted_b) - 1)
        idx_c = min(int(i * len(sorted_c) / n), len(sorted_c) - 1)
        total += abs(sorted_b[idx_b] - sorted_c[idx_c])
    return total / Decimal(n)


# ════════════════════════════════════════════════════════════════════════
# Validation Framework (ENH-262)
# ════════════════════════════════════════════════════════════════════════

class ValidationGate(Enum):
    """Pre-production validation gates per SR 11-7."""
    DATA_QUALITY = "DATA_QUALITY"
    CONCEPTUAL_SOUNDNESS = "CONCEPTUAL_SOUNDNESS"
    DEVELOPMENT_TESTING = "DEVELOPMENT_TESTING"
    OUT_OF_TIME_TESTING = "OUT_OF_TIME_TESTING"
    OUT_OF_SAMPLE_TESTING = "OUT_OF_SAMPLE_TESTING"
    BENCHMARKING = "BENCHMARKING"
    SENSITIVITY_ANALYSIS = "SENSITIVITY_ANALYSIS"
    STRESS_TESTING = "STRESS_TESTING"
    FAIRNESS_TESTING = "FAIRNESS_TESTING"
    EXPLAINABILITY = "EXPLAINABILITY"
    PRODUCTION_READINESS = "PRODUCTION_READINESS"


class ValidationVerdict(Enum):
    PASS = "PASS"
    PASS_WITH_OBSERVATIONS = "PASS_WITH_OBSERVATIONS"
    FAIL = "FAIL"
    NOT_TESTED = "NOT_TESTED"
    INCONCLUSIVE = "INCONCLUSIVE"


@dataclass(frozen=True)
class ValidationTestResult:
    """One gate's test outcome."""
    test_result_id: str
    model_id: str
    gate: ValidationGate
    verdict: ValidationVerdict
    metric_name: Optional[str] = None      # e.g., "AUC", "GINI"
    metric_value: Optional[Decimal] = None
    threshold: Optional[Decimal] = None
    test_date: str = ""
    validator_user_id: str = ""
    notes: str = ""

    def is_blocking(self) -> bool:
        """A FAIL on a required gate blocks production."""
        return self.verdict == ValidationVerdict.FAIL


# Required gates per tier — Tier 1 needs full validation
REQUIRED_VALIDATION_GATES_BY_TIER: Mapping[
    ModelTier, Tuple[ValidationGate, ...]] = {
    ModelTier.TIER_1_HIGH: (
        ValidationGate.DATA_QUALITY,
        ValidationGate.CONCEPTUAL_SOUNDNESS,
        ValidationGate.DEVELOPMENT_TESTING,
        ValidationGate.OUT_OF_TIME_TESTING,
        ValidationGate.OUT_OF_SAMPLE_TESTING,
        ValidationGate.BENCHMARKING,
        ValidationGate.SENSITIVITY_ANALYSIS,
        ValidationGate.STRESS_TESTING,
        ValidationGate.FAIRNESS_TESTING,
        ValidationGate.EXPLAINABILITY,
        ValidationGate.PRODUCTION_READINESS,
    ),
    ModelTier.TIER_2_MEDIUM: (
        ValidationGate.DATA_QUALITY,
        ValidationGate.CONCEPTUAL_SOUNDNESS,
        ValidationGate.DEVELOPMENT_TESTING,
        ValidationGate.OUT_OF_TIME_TESTING,
        ValidationGate.FAIRNESS_TESTING,
        ValidationGate.PRODUCTION_READINESS,
    ),
    ModelTier.TIER_3_LOW: (
        ValidationGate.DATA_QUALITY,
        ValidationGate.DEVELOPMENT_TESTING,
        ValidationGate.PRODUCTION_READINESS,
    ),
}


@dataclass(frozen=True)
class ValidationReport:
    """Aggregated validation outcome."""
    report_id: str
    model_id: str
    model_tier: ModelTier
    test_results: Tuple[ValidationTestResult, ...]
    overall_verdict: ValidationVerdict
    n_gates_passed: int
    n_gates_failed: int
    n_gates_not_tested: int
    report_date: str
    notes: str = ""


def assemble_validation_report(
    *,
    report_id: str,
    model: Model,
    test_results: Sequence[ValidationTestResult],
    report_date: str,
) -> ValidationReport:
    """Assemble validation report; verdict = FAIL if any required gate FAIL."""
    required_gates = REQUIRED_VALIDATION_GATES_BY_TIER[model.model_tier]
    results_by_gate: Dict[ValidationGate, ValidationTestResult] = {}
    for r in test_results:
        results_by_gate[r.gate] = r

    n_passed = 0
    n_failed = 0
    n_not_tested = 0
    has_blocking_failure = False

    for gate in required_gates:
        result = results_by_gate.get(gate)
        if result is None:
            n_not_tested += 1
        elif result.verdict in (
                ValidationVerdict.PASS,
                ValidationVerdict.PASS_WITH_OBSERVATIONS):
            n_passed += 1
        elif result.verdict == ValidationVerdict.FAIL:
            n_failed += 1
            has_blocking_failure = True
        else:
            n_not_tested += 1

    if has_blocking_failure:
        overall = ValidationVerdict.FAIL
    elif n_not_tested > 0:
        overall = ValidationVerdict.INCONCLUSIVE
    elif n_passed == len(required_gates):
        # Check for any PASS_WITH_OBSERVATIONS
        any_observations = any(
            r.verdict == ValidationVerdict.PASS_WITH_OBSERVATIONS
            for r in test_results
            if r.gate in required_gates)
        overall = (ValidationVerdict.PASS_WITH_OBSERVATIONS
                     if any_observations
                     else ValidationVerdict.PASS)
    else:
        overall = ValidationVerdict.INCONCLUSIVE

    return ValidationReport(
        report_id=report_id, model_id=model.model_id,
        model_tier=model.model_tier,
        test_results=tuple(test_results),
        overall_verdict=overall,
        n_gates_passed=n_passed, n_gates_failed=n_failed,
        n_gates_not_tested=n_not_tested,
        report_date=report_date,
        notes=(
            f"required gates: {len(required_gates)}; passed: {n_passed}; "
            f"failed: {n_failed}; not tested: {n_not_tested}"))


# ════════════════════════════════════════════════════════════════════════
# Explainability (ENH-263)
# ════════════════════════════════════════════════════════════════════════

class ExplanationMethod(Enum):
    """Methods for model explainability."""
    SHAP = "SHAP"                          # Lundberg & Lee 2017
    LIME = "LIME"                          # Ribeiro et al. 2016
    PERMUTATION_IMPORTANCE = "PERMUTATION_IMPORTANCE"
    PARTIAL_DEPENDENCE = "PARTIAL_DEPENDENCE"
    INTEGRATED_GRADIENTS = "INTEGRATED_GRADIENTS"
    COUNTERFACTUAL = "COUNTERFACTUAL"
    RULE_EXTRACTION = "RULE_EXTRACTION"


# CFPB Reg B Appendix C adverse action codes (subset)
ADVERSE_ACTION_CODES: Mapping[str, str] = {
    "01": "Credit application incomplete",
    "02": "Insufficient credit references",
    "03": "Insufficient or no credit file",
    "04": "Length of credit history",
    "05": "Number of recent inquiries on credit bureau report",
    "06": "Insufficient or no checking/savings",
    "07": "Excessive obligations in relation to income",
    "08": "Insufficient income for amount of credit requested",
    "09": "Length of employment",
    "10": "Temporary or irregular employment",
    "11": "Unable to verify income",
    "12": "Unable to verify residence",
    "13": "Unable to verify employment",
    "14": "Garnishment, attachment, foreclosure, repossession",
    "15": "Bankruptcy",
    "16": "Delinquent past or present credit obligations",
    "17": "Number of recent inquiries on credit bureau report",
    "18": "Value or type of collateral not sufficient",
    "19": "We do not grant credit to any applicant on the terms requested",
    "20": "We do not grant credit on the terms requested",
}


@dataclass(frozen=True)
class ExplanationResult:
    """Result of an explainability request."""
    explanation_id: str
    model_id: str
    decision_id: str                       # the decision being explained
    method: ExplanationMethod
    feature_contributions: Mapping[str, Decimal]
    base_value: Decimal
    predicted_value: Decimal
    top_n_positive: Tuple[str, ...] = ()
    top_n_negative: Tuple[str, ...] = ()
    adverse_action_codes: Tuple[str, ...] = ()
    notes: str = ""


def explain_decision(
    *,
    explanation_id: str,
    model_id: str,
    decision_id: str,
    method: ExplanationMethod,
    features: Mapping[str, Decimal],
    explainer: Optional[Callable[
        [Mapping[str, Decimal]], Tuple[Mapping[str, Decimal], Decimal, Decimal]
    ]] = None,
    top_n: int = 5,
) -> ExplanationResult:
    """Generate explanation for a model decision.

    Per Rule 7 — without explainer hook, returns REQUIRES_PROVIDER state
    (empty contributions, notes flag). Never fabricates SHAP values.
    """
    if explainer is None:
        return ExplanationResult(
            explanation_id=explanation_id,
            model_id=model_id, decision_id=decision_id,
            method=method, feature_contributions={},
            base_value=Decimal("0"), predicted_value=Decimal("0"),
            notes=(
                f"REQUIRES_PROVIDER: no {method.value} explainer wired. "
                f"Per Rule 7, framework does not fabricate explanations."))

    try:
        contributions, base_val, pred_val = explainer(features)
    except Exception as e:
        return ExplanationResult(
            explanation_id=explanation_id,
            model_id=model_id, decision_id=decision_id,
            method=method, feature_contributions={},
            base_value=Decimal("0"), predicted_value=Decimal("0"),
            notes=f"explainer failed: {type(e).__name__}: {e}")

    sorted_contribs = sorted(
        contributions.items(), key=lambda x: x[1], reverse=True)
    top_pos = tuple(name for name, val in sorted_contribs[:top_n] if val > 0)
    top_neg = tuple(name for name, val in sorted_contribs[-top_n:] if val < 0)

    return ExplanationResult(
        explanation_id=explanation_id,
        model_id=model_id, decision_id=decision_id,
        method=method,
        feature_contributions=dict(contributions),
        base_value=base_val, predicted_value=pred_val,
        top_n_positive=top_pos, top_n_negative=top_neg,
        notes=f"explained via {method.value}; "
                  f"{len(contributions)} features")


def map_features_to_adverse_action(
    *,
    explanation: ExplanationResult,
    feature_to_aa_code_map: Mapping[str, str],
) -> Tuple[str, ...]:
    """Map top negative-contribution features to CFPB Reg B codes."""
    codes: List[str] = []
    for feat in explanation.top_n_negative:
        code = feature_to_aa_code_map.get(feat)
        if code and code not in codes:
            codes.append(code)
    return tuple(codes)


# ════════════════════════════════════════════════════════════════════════
# Bias Monitoring (ENH-265)
# ════════════════════════════════════════════════════════════════════════

class BiasMetric(Enum):
    """Fairness/bias metrics."""
    FOUR_FIFTHS_RULE = "FOUR_FIFTHS_RULE"          # EEOC disparate impact
    DEMOGRAPHIC_PARITY = "DEMOGRAPHIC_PARITY"      # P(approved | A) ≈ P(approved | ¬A)
    EQUAL_OPPORTUNITY = "EQUAL_OPPORTUNITY"        # TPR equal across groups
    EQUALIZED_ODDS = "EQUALIZED_ODDS"              # TPR + FPR equal
    PREDICTIVE_PARITY = "PREDICTIVE_PARITY"        # PPV equal
    CALIBRATION = "CALIBRATION"                    # P(positive | score, group)


class BiasVerdict(Enum):
    NO_BIAS_DETECTED = "NO_BIAS_DETECTED"
    POTENTIAL_BIAS = "POTENTIAL_BIAS"
    DISPARATE_IMPACT = "DISPARATE_IMPACT"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


# 4/5ths rule threshold per EEOC (29 CFR §1607.4)
FOUR_FIFTHS_RULE_THRESHOLD = Decimal("0.80")
# Demographic parity tolerance
DEMOGRAPHIC_PARITY_TOLERANCE = Decimal("0.05")    # 5 percentage points
# Equal opportunity TPR tolerance
EQUAL_OPPORTUNITY_TOLERANCE = Decimal("0.05")


@dataclass(frozen=True)
class BiasResult:
    """Outcome of one bias test."""
    test_id: str
    model_id: str
    metric: BiasMetric
    protected_class: str                   # e.g., "gender", "ethnicity"
    reference_group: str                    # the favored/majority group
    comparison_group: str                   # the protected group
    statistic_value: Decimal
    threshold: Decimal
    verdict: BiasVerdict
    n_reference: int
    n_comparison: int
    test_date: str
    notes: str = ""


def four_fifths_rule_test(
    *,
    test_id: str,
    model_id: str,
    protected_class: str,
    reference_group: str,
    comparison_group: str,
    n_reference_total: int,
    n_reference_positive: int,
    n_comparison_total: int,
    n_comparison_positive: int,
    test_date: str,
) -> BiasResult:
    """4/5ths rule per EEOC 29 CFR §1607.4.

    Adverse impact exists when selection rate for protected group is
    less than 80% of selection rate for reference group.
    """
    if n_reference_total < 30 or n_comparison_total < 30:
        return BiasResult(
            test_id=test_id, model_id=model_id,
            metric=BiasMetric.FOUR_FIFTHS_RULE,
            protected_class=protected_class,
            reference_group=reference_group,
            comparison_group=comparison_group,
            statistic_value=Decimal("0"),
            threshold=FOUR_FIFTHS_RULE_THRESHOLD,
            verdict=BiasVerdict.INSUFFICIENT_DATA,
            n_reference=n_reference_total,
            n_comparison=n_comparison_total,
            test_date=test_date,
            notes=f"insufficient samples (need ≥30 each)")

    rate_ref = (Decimal(n_reference_positive)
                  / Decimal(n_reference_total))
    rate_comp = (Decimal(n_comparison_positive)
                   / Decimal(n_comparison_total))
    if rate_ref == Decimal("0"):
        ratio = Decimal("0")
    else:
        ratio = rate_comp / rate_ref

    if ratio >= FOUR_FIFTHS_RULE_THRESHOLD:
        verdict = BiasVerdict.NO_BIAS_DETECTED
    elif ratio >= Decimal("0.70"):
        verdict = BiasVerdict.POTENTIAL_BIAS
    else:
        verdict = BiasVerdict.DISPARATE_IMPACT

    return BiasResult(
        test_id=test_id, model_id=model_id,
        metric=BiasMetric.FOUR_FIFTHS_RULE,
        protected_class=protected_class,
        reference_group=reference_group,
        comparison_group=comparison_group,
        statistic_value=ratio,
        threshold=FOUR_FIFTHS_RULE_THRESHOLD,
        verdict=verdict,
        n_reference=n_reference_total,
        n_comparison=n_comparison_total,
        test_date=test_date,
        notes=(
            f"selection rate ref={rate_ref:.3f}, "
            f"comp={rate_comp:.3f}, ratio={ratio:.3f}"))


def demographic_parity_test(
    *,
    test_id: str,
    model_id: str,
    protected_class: str,
    reference_group: str,
    comparison_group: str,
    rate_reference: Decimal,
    rate_comparison: Decimal,
    n_reference: int,
    n_comparison: int,
    test_date: str,
    tolerance: Decimal = DEMOGRAPHIC_PARITY_TOLERANCE,
) -> BiasResult:
    """Demographic parity: |P(approved|ref) - P(approved|comp)| ≤ tolerance."""
    if n_reference < 30 or n_comparison < 30:
        return BiasResult(
            test_id=test_id, model_id=model_id,
            metric=BiasMetric.DEMOGRAPHIC_PARITY,
            protected_class=protected_class,
            reference_group=reference_group,
            comparison_group=comparison_group,
            statistic_value=Decimal("0"),
            threshold=tolerance,
            verdict=BiasVerdict.INSUFFICIENT_DATA,
            n_reference=n_reference, n_comparison=n_comparison,
            test_date=test_date)

    diff = abs(rate_reference - rate_comparison)
    if diff <= tolerance:
        verdict = BiasVerdict.NO_BIAS_DETECTED
    elif diff <= tolerance * Decimal("2"):
        verdict = BiasVerdict.POTENTIAL_BIAS
    else:
        verdict = BiasVerdict.DISPARATE_IMPACT

    return BiasResult(
        test_id=test_id, model_id=model_id,
        metric=BiasMetric.DEMOGRAPHIC_PARITY,
        protected_class=protected_class,
        reference_group=reference_group,
        comparison_group=comparison_group,
        statistic_value=diff, threshold=tolerance,
        verdict=verdict,
        n_reference=n_reference, n_comparison=n_comparison,
        test_date=test_date,
        notes=f"|{rate_reference:.3f} - {rate_comparison:.3f}| = {diff:.3f}")


# ════════════════════════════════════════════════════════════════════════
# Engine — orchestrator
# ════════════════════════════════════════════════════════════════════════

class ModelGovernanceEngine:
    """End-to-end orchestrator for model inventory + lifecycle + drift +
    validation + explainability + bias.

    Composes with v10.27 audit_trail_certification — every transition
    can be hashed into the cryptographic chain via append_event hook.
    """

    def __init__(self, *, entity_name: str = "Ecobank Kenya"):
        self.entity_name = entity_name
        self._models: Dict[str, Model] = {}
        self._lifecycle_transitions: List[
            Tuple[str, ModelLifecycleState, ModelLifecycleState, str]] = []
        self._drift_results: List[DriftResult] = []
        self._validation_results: List[ValidationTestResult] = []
        self._validation_reports: Dict[str, ValidationReport] = {}
        self._explanations: List[ExplanationResult] = []
        self._bias_results: List[BiasResult] = []

    # ── Inventory (ENH-259) ────────────────────────────────────────────
    def register_model(self, model: Model) -> None:
        if model.model_id in self._models:
            raise ValueError(
                f"model {model.model_id} already registered")
        self._models[model.model_id] = model

    def get_model(self, model_id: str) -> Model:
        if model_id not in self._models:
            raise KeyError(f"model {model_id} not found")
        return self._models[model_id]

    def models_by_tier(
        self, tier: ModelTier,
    ) -> Tuple[Model, ...]:
        return tuple(
            m for m in self._models.values() if m.model_tier == tier)

    def models_with_overdue_validation(
        self, *, as_of: Optional[date] = None,
    ) -> Tuple[Model, ...]:
        if as_of is None:
            as_of = date.today()
        return tuple(
            m for m in self._models.values()
            if m.is_validation_overdue(as_of=as_of))

    # ── Lifecycle ──────────────────────────────────────────────────────
    def transition_model(
        self,
        *,
        model_id: str,
        to_state: ModelLifecycleState,
        actor_user_id: str,
        timestamp: str,
        notes: str = "",
    ) -> Model:
        existing = self.get_model(model_id)
        if not is_valid_lifecycle_transition(
                existing.current_state, to_state):
            allowed = ALLOWED_LIFECYCLE_TRANSITIONS.get(
                existing.current_state, ())
            raise ValueError(
                f"invalid lifecycle transition "
                f"{existing.current_state.value} → {to_state.value}; "
                f"allowed: {[s.value for s in allowed]}")

        # Special rule: Tier 1/2 IN_PRODUCTION requires passed validation
        if (to_state == ModelLifecycleState.IN_PRODUCTION
                and existing.requires_independent_validation()):
            # Find latest validation report for this model
            latest_report = None
            for rep in self._validation_reports.values():
                if (rep.model_id == model_id
                        and (latest_report is None
                             or rep.report_date > latest_report.report_date)):
                    latest_report = rep
            if latest_report is None:
                raise ValueError(
                    f"cannot transition {model_id} to IN_PRODUCTION — "
                    f"Tier {existing.model_tier.value} requires independent "
                    f"validation report (none on file)")
            if latest_report.overall_verdict not in (
                    ValidationVerdict.PASS,
                    ValidationVerdict.PASS_WITH_OBSERVATIONS):
                raise ValueError(
                    f"cannot transition {model_id} to IN_PRODUCTION — "
                    f"latest validation report verdict is "
                    f"{latest_report.overall_verdict.value}")

        self._lifecycle_transitions.append(
            (model_id, existing.current_state, to_state, actor_user_id))

        updated = Model(
            model_id=existing.model_id,
            model_name=existing.model_name,
            model_type=existing.model_type,
            model_tier=existing.model_tier,
            eu_ai_act_category=existing.eu_ai_act_category,
            current_state=to_state,
            owner_business_unit=existing.owner_business_unit,
            owner_user_id=existing.owner_user_id,
            development_date=existing.development_date,
            deployment_date=(
                timestamp[:10]
                if to_state == ModelLifecycleState.IN_PRODUCTION
                and existing.deployment_date is None
                else existing.deployment_date),
            last_validation_date=existing.last_validation_date,
            next_validation_due=existing.next_validation_due,
            is_vendor_model=existing.is_vendor_model,
            vendor_name=existing.vendor_name,
            description=existing.description,
            feature_count=existing.feature_count,
            training_sample_size=existing.training_sample_size,
            framework_refs=existing.framework_refs,
            notes=(
                existing.notes + "\n" + notes if notes
                else existing.notes))
        self._models[model_id] = updated
        return updated

    # ── Drift (ENH-261) ────────────────────────────────────────────────
    def run_psi_drift(
        self,
        *,
        test_id: str,
        model_id: str,
        feature_name: Optional[str],
        baseline_distribution: Sequence[Decimal],
        current_distribution: Sequence[Decimal],
        n_baseline: int,
        n_current: int,
        test_date: str,
    ) -> DriftResult:
        if model_id not in self._models:
            raise KeyError(f"model {model_id} not found")
        result = detect_drift_psi(
            test_id=test_id, model_id=model_id,
            feature_name=feature_name,
            baseline_distribution=baseline_distribution,
            current_distribution=current_distribution,
            n_baseline=n_baseline, n_current=n_current,
            test_date=test_date)
        self._drift_results.append(result)
        return result

    def run_ks_drift(
        self,
        *,
        test_id: str,
        model_id: str,
        feature_name: Optional[str],
        baseline_samples: Sequence[Decimal],
        current_samples: Sequence[Decimal],
        test_date: str,
    ) -> DriftResult:
        if model_id not in self._models:
            raise KeyError(f"model {model_id} not found")
        result = detect_drift_ks(
            test_id=test_id, model_id=model_id,
            feature_name=feature_name,
            baseline_samples=baseline_samples,
            current_samples=current_samples,
            test_date=test_date)
        self._drift_results.append(result)
        return result

    def actionable_drift_results(
        self) -> Tuple[DriftResult, ...]:
        return tuple(r for r in self._drift_results if r.is_actionable())

    # ── Validation (ENH-262) ──────────────────────────────────────────
    def record_validation_test(
        self, result: ValidationTestResult,
    ) -> None:
        if result.model_id not in self._models:
            raise KeyError(f"model {result.model_id} not found")
        self._validation_results.append(result)

    def assemble_report(
        self,
        *,
        report_id: str,
        model_id: str,
        report_date: str,
    ) -> ValidationReport:
        model = self.get_model(model_id)
        model_results = tuple(
            r for r in self._validation_results
            if r.model_id == model_id)
        report = assemble_validation_report(
            report_id=report_id, model=model,
            test_results=model_results, report_date=report_date)
        self._validation_reports[report_id] = report
        return report

    # ── Explainability (ENH-263) ──────────────────────────────────────
    def explain(
        self,
        *,
        explanation_id: str,
        model_id: str,
        decision_id: str,
        method: ExplanationMethod,
        features: Mapping[str, Decimal],
        explainer: Optional[Callable] = None,
    ) -> ExplanationResult:
        if model_id not in self._models:
            raise KeyError(f"model {model_id} not found")
        result = explain_decision(
            explanation_id=explanation_id, model_id=model_id,
            decision_id=decision_id, method=method,
            features=features, explainer=explainer)
        self._explanations.append(result)
        return result

    # ── Bias Monitoring (ENH-265) ─────────────────────────────────────
    def run_four_fifths_test(
        self, *, test_id: str, model_id: str,
        protected_class: str, reference_group: str,
        comparison_group: str,
        n_reference_total: int, n_reference_positive: int,
        n_comparison_total: int, n_comparison_positive: int,
        test_date: str,
    ) -> BiasResult:
        if model_id not in self._models:
            raise KeyError(f"model {model_id} not found")
        result = four_fifths_rule_test(
            test_id=test_id, model_id=model_id,
            protected_class=protected_class,
            reference_group=reference_group,
            comparison_group=comparison_group,
            n_reference_total=n_reference_total,
            n_reference_positive=n_reference_positive,
            n_comparison_total=n_comparison_total,
            n_comparison_positive=n_comparison_positive,
            test_date=test_date)
        self._bias_results.append(result)
        return result

    def models_with_disparate_impact(
        self) -> Tuple[BiasResult, ...]:
        return tuple(
            b for b in self._bias_results
            if b.verdict == BiasVerdict.DISPARATE_IMPACT)

    # ── Reporting ──────────────────────────────────────────────────────
    def board_summary(
        self, *, as_of: Optional[date] = None,
    ) -> Dict[str, Any]:
        if as_of is None:
            as_of = date.today()
        return {
            "entity": self.entity_name,
            "n_models_total": len(self._models),
            "n_tier_1": len(self.models_by_tier(ModelTier.TIER_1_HIGH)),
            "n_tier_2": len(self.models_by_tier(ModelTier.TIER_2_MEDIUM)),
            "n_tier_3": len(self.models_by_tier(ModelTier.TIER_3_LOW)),
            "n_in_production": sum(
                1 for m in self._models.values()
                if m.current_state == ModelLifecycleState.IN_PRODUCTION),
            "n_overdue_validation": len(
                self.models_with_overdue_validation(as_of=as_of)),
            "n_actionable_drift": len(self.actionable_drift_results()),
            "n_disparate_impact": len(
                self.models_with_disparate_impact()),
            "n_validation_reports": len(self._validation_reports),
            "n_explanations": len(self._explanations),
        }


# ════════════════════════════════════════════════════════════════════════
# Self-test
# ════════════════════════════════════════════════════════════════════════

def _make_model(mid="M1", tier=ModelTier.TIER_2_MEDIUM,
                  state=ModelLifecycleState.DEVELOPMENT):
    return Model(
        model_id=mid, model_name=f"Model {mid}",
        model_type=ModelType.CREDIT_SCORECARD,
        model_tier=tier,
        eu_ai_act_category=EUAIActRiskCategory.HIGH_RISK,
        current_state=state,
        owner_business_unit="Credit",
        owner_user_id="alice",
        development_date="2026-01-01")


# ── Lifecycle tests ──────────────────────────────────────────────────
def _test_lifecycle_valid_path():
    assert is_valid_lifecycle_transition(
        ModelLifecycleState.DEVELOPMENT,
        ModelLifecycleState.INTERNAL_TESTING)


def _test_lifecycle_cannot_skip_to_production():
    """Cannot go DEV → IN_PRODUCTION directly."""
    assert not is_valid_lifecycle_transition(
        ModelLifecycleState.DEVELOPMENT,
        ModelLifecycleState.IN_PRODUCTION)


def _test_lifecycle_retired_terminal():
    """RETIRED has no allowed transitions."""
    allowed = ALLOWED_LIFECYCLE_TRANSITIONS[
        ModelLifecycleState.RETIRED]
    assert len(allowed) == 0


def _test_tier_validation_cadence():
    assert (DEFAULT_VALIDATION_CADENCE_MONTHS[ModelTier.TIER_1_HIGH]
              == 12)
    assert (DEFAULT_VALIDATION_CADENCE_MONTHS[ModelTier.TIER_3_LOW]
              == 36)


# ── PSI drift tests ──────────────────────────────────────────────────
def _test_psi_no_drift():
    """Identical distributions → PSI = 0 → NO_DRIFT."""
    base = [Decimal("0.2"), Decimal("0.3"), Decimal("0.3"), Decimal("0.2")]
    curr = [Decimal("0.2"), Decimal("0.3"), Decimal("0.3"), Decimal("0.2")]
    psi = compute_psi(
        baseline_distribution=base, current_distribution=curr)
    assert psi < Decimal("0.001")


def _test_psi_major_drift():
    """Very different distributions → high PSI → MAJOR_DRIFT."""
    base = [Decimal("0.5"), Decimal("0.5"),
              Decimal("0"), Decimal("0")]
    curr = [Decimal("0"), Decimal("0"),
              Decimal("0.5"), Decimal("0.5")]
    psi = compute_psi(
        baseline_distribution=base, current_distribution=curr)
    assert psi > Decimal("1.0")    # massive drift


def _test_psi_bins_mismatch_raises():
    try:
        compute_psi(
            baseline_distribution=[Decimal("0.5"), Decimal("0.5")],
            current_distribution=[Decimal("0.3"), Decimal("0.3"),
                                       Decimal("0.4")])
        assert False
    except ValueError:
        pass


def _test_psi_drift_severity_thresholds():
    assert PSI_NO_DRIFT_THRESHOLD == Decimal("0.10")
    assert PSI_SMALL_SHIFT_THRESHOLD == Decimal("0.20")
    assert PSI_SIGNIFICANT_THRESHOLD == Decimal("0.25")


def _test_detect_psi_insufficient_data():
    result = detect_drift_psi(
        test_id="T1", model_id="M1", feature_name="age",
        baseline_distribution=[Decimal("0.5"), Decimal("0.5")],
        current_distribution=[Decimal("0.5"), Decimal("0.5")],
        n_baseline=50, n_current=50,
        test_date="2026-05-01")
    assert result.severity == DriftSeverity.INSUFFICIENT_DATA


def _test_detect_psi_no_drift():
    base = [Decimal("0.25")] * 4
    result = detect_drift_psi(
        test_id="T1", model_id="M1", feature_name="age",
        baseline_distribution=base, current_distribution=base,
        n_baseline=1000, n_current=1000,
        test_date="2026-05-01")
    assert result.severity == DriftSeverity.NO_DRIFT
    assert not result.is_actionable()


def _test_detect_psi_major_drift_actionable():
    base = [Decimal("0.5"), Decimal("0.5"),
              Decimal("0.001"), Decimal("0.001")]
    curr = [Decimal("0.001"), Decimal("0.001"),
              Decimal("0.5"), Decimal("0.5")]
    result = detect_drift_psi(
        test_id="T1", model_id="M1", feature_name="age",
        baseline_distribution=base, current_distribution=curr,
        n_baseline=1000, n_current=1000,
        test_date="2026-05-01")
    assert result.severity == DriftSeverity.MAJOR_DRIFT
    assert result.is_actionable()


# ── KS drift tests ────────────────────────────────────────────────────
def _test_ks_identical_zero():
    samples = [Decimal(str(i)) for i in range(100)]
    ks = compute_ks_statistic(
        baseline_samples=samples, current_samples=samples)
    assert ks == Decimal("0")


def _test_ks_disjoint_max():
    """Completely disjoint distributions → KS = 1."""
    base = [Decimal(str(i)) for i in range(100)]
    curr = [Decimal(str(i + 1000)) for i in range(100)]
    ks = compute_ks_statistic(
        baseline_samples=base, current_samples=curr)
    assert ks == Decimal("1")


def _test_ks_critical_decreases_with_n():
    """Larger samples → tighter critical value."""
    cv_small = ks_critical_value(n_baseline=50, n_current=50)
    cv_large = ks_critical_value(n_baseline=5000, n_current=5000)
    assert cv_small > cv_large


def _test_ks_insufficient_returns_insufficient():
    result = detect_drift_ks(
        test_id="T1", model_id="M1", feature_name="x",
        baseline_samples=[Decimal("1"), Decimal("2")],
        current_samples=[Decimal("1"), Decimal("2")],
        test_date="2026-05-01")
    assert result.severity == DriftSeverity.INSUFFICIENT_DATA


# ── Validation tests ──────────────────────────────────────────────────
def _test_required_gates_tier_1_more():
    t1_gates = REQUIRED_VALIDATION_GATES_BY_TIER[ModelTier.TIER_1_HIGH]
    t3_gates = REQUIRED_VALIDATION_GATES_BY_TIER[ModelTier.TIER_3_LOW]
    assert len(t1_gates) > len(t3_gates)


def _test_validation_pass_all_gates():
    model = _make_model(tier=ModelTier.TIER_3_LOW)
    results = []
    for gate in REQUIRED_VALIDATION_GATES_BY_TIER[ModelTier.TIER_3_LOW]:
        results.append(ValidationTestResult(
            test_result_id=f"VR-{gate.value}",
            model_id="M1", gate=gate,
            verdict=ValidationVerdict.PASS,
            test_date="2026-05-01"))
    report = assemble_validation_report(
        report_id="REP1", model=model,
        test_results=results, report_date="2026-05-01")
    assert report.overall_verdict == ValidationVerdict.PASS


def _test_validation_fail_blocks():
    model = _make_model(tier=ModelTier.TIER_3_LOW)
    results = []
    for gate in REQUIRED_VALIDATION_GATES_BY_TIER[ModelTier.TIER_3_LOW]:
        verdict = (ValidationVerdict.FAIL
                     if gate == ValidationGate.DATA_QUALITY
                     else ValidationVerdict.PASS)
        results.append(ValidationTestResult(
            test_result_id=f"VR-{gate.value}",
            model_id="M1", gate=gate, verdict=verdict,
            test_date="2026-05-01"))
    report = assemble_validation_report(
        report_id="REP1", model=model,
        test_results=results, report_date="2026-05-01")
    assert report.overall_verdict == ValidationVerdict.FAIL


def _test_validation_missing_gate_inconclusive():
    model = _make_model(tier=ModelTier.TIER_3_LOW)
    # Only test 1 of 3 required gates
    results = [ValidationTestResult(
        test_result_id="VR1", model_id="M1",
        gate=ValidationGate.DATA_QUALITY,
        verdict=ValidationVerdict.PASS,
        test_date="2026-05-01")]
    report = assemble_validation_report(
        report_id="REP1", model=model,
        test_results=results, report_date="2026-05-01")
    assert report.overall_verdict == ValidationVerdict.INCONCLUSIVE


# ── Explainability tests ──────────────────────────────────────────────
def _test_explain_no_provider_requires_provider():
    """Rule 7 — no explainer hook → REQUIRES_PROVIDER."""
    result = explain_decision(
        explanation_id="E1", model_id="M1",
        decision_id="D1", method=ExplanationMethod.SHAP,
        features={"age": Decimal("25"), "income": Decimal("50000")})
    assert "REQUIRES_PROVIDER" in result.notes
    assert len(result.feature_contributions) == 0


def _test_explain_with_hook():
    def fake_shap(features):
        return ({"age": Decimal("0.3"),
                  "income": Decimal("-0.2")},
                  Decimal("0.5"), Decimal("0.6"))

    result = explain_decision(
        explanation_id="E1", model_id="M1", decision_id="D1",
        method=ExplanationMethod.SHAP,
        features={"age": Decimal("25"), "income": Decimal("50000")},
        explainer=fake_shap)
    assert "age" in result.feature_contributions
    assert result.predicted_value == Decimal("0.6")
    assert "age" in result.top_n_positive
    assert "income" in result.top_n_negative


def _test_adverse_action_codes_loaded():
    assert "01" in ADVERSE_ACTION_CODES
    assert "Bankruptcy" in ADVERSE_ACTION_CODES["15"]
    assert len(ADVERSE_ACTION_CODES) >= 15


def _test_map_features_to_adverse_action():
    explanation = ExplanationResult(
        explanation_id="E1", model_id="M1", decision_id="D1",
        method=ExplanationMethod.SHAP,
        feature_contributions={
            "delinquency_history": Decimal("-0.5"),
            "income_to_debt": Decimal("-0.3")},
        base_value=Decimal("0.5"), predicted_value=Decimal("0.2"),
        top_n_negative=("delinquency_history", "income_to_debt"))
    feature_map = {
        "delinquency_history": "16",
        "income_to_debt": "07"}
    codes = map_features_to_adverse_action(
        explanation=explanation,
        feature_to_aa_code_map=feature_map)
    assert "16" in codes
    assert "07" in codes


# ── Bias tests ────────────────────────────────────────────────────────
def _test_four_fifths_no_bias():
    """Equal selection rates → no bias."""
    result = four_fifths_rule_test(
        test_id="B1", model_id="M1",
        protected_class="gender",
        reference_group="male", comparison_group="female",
        n_reference_total=1000, n_reference_positive=500,
        n_comparison_total=1000, n_comparison_positive=500,
        test_date="2026-05-01")
    assert result.verdict == BiasVerdict.NO_BIAS_DETECTED


def _test_four_fifths_disparate_impact():
    """Comparison rate < 80% of reference → DISPARATE_IMPACT."""
    result = four_fifths_rule_test(
        test_id="B1", model_id="M1",
        protected_class="gender",
        reference_group="male", comparison_group="female",
        n_reference_total=1000, n_reference_positive=500,    # 50%
        n_comparison_total=1000, n_comparison_positive=200,  # 20%
        test_date="2026-05-01")
    # Ratio = 20/50 = 0.4 < 0.7 → DISPARATE_IMPACT
    assert result.verdict == BiasVerdict.DISPARATE_IMPACT


def _test_four_fifths_potential_bias():
    """Ratio between 0.7 and 0.8 → POTENTIAL_BIAS."""
    result = four_fifths_rule_test(
        test_id="B1", model_id="M1",
        protected_class="gender",
        reference_group="male", comparison_group="female",
        n_reference_total=1000, n_reference_positive=500,    # 50%
        n_comparison_total=1000, n_comparison_positive=375,  # 37.5%
        test_date="2026-05-01")
    # Ratio = 37.5/50 = 0.75 → POTENTIAL_BIAS (between 0.70 and 0.80)
    assert result.verdict == BiasVerdict.POTENTIAL_BIAS


def _test_four_fifths_insufficient_data():
    result = four_fifths_rule_test(
        test_id="B1", model_id="M1",
        protected_class="gender",
        reference_group="male", comparison_group="female",
        n_reference_total=20, n_reference_positive=10,
        n_comparison_total=20, n_comparison_positive=8,
        test_date="2026-05-01")
    assert result.verdict == BiasVerdict.INSUFFICIENT_DATA


def _test_demographic_parity_within_tolerance():
    result = demographic_parity_test(
        test_id="B1", model_id="M1",
        protected_class="gender",
        reference_group="male", comparison_group="female",
        rate_reference=Decimal("0.50"),
        rate_comparison=Decimal("0.48"),
        n_reference=1000, n_comparison=1000,
        test_date="2026-05-01")
    assert result.verdict == BiasVerdict.NO_BIAS_DETECTED


def _test_demographic_parity_disparate():
    result = demographic_parity_test(
        test_id="B1", model_id="M1",
        protected_class="gender",
        reference_group="male", comparison_group="female",
        rate_reference=Decimal("0.50"),
        rate_comparison=Decimal("0.20"),     # 30 pp difference
        n_reference=1000, n_comparison=1000,
        test_date="2026-05-01")
    assert result.verdict == BiasVerdict.DISPARATE_IMPACT


# ── Engine tests ──────────────────────────────────────────────────────
def _test_engine_register_dup_raises():
    eng = ModelGovernanceEngine()
    eng.register_model(_make_model())
    try:
        eng.register_model(_make_model())
        assert False
    except ValueError:
        pass


def _test_engine_invalid_transition_raises():
    eng = ModelGovernanceEngine()
    eng.register_model(_make_model())
    try:
        eng.transition_model(
            model_id="M1",
            to_state=ModelLifecycleState.IN_PRODUCTION,
            actor_user_id="alice", timestamp="t")
        assert False
    except ValueError:
        pass


def _test_engine_tier1_production_blocked_without_validation():
    """Tier 1/2 → IN_PRODUCTION blocked without validation report."""
    eng = ModelGovernanceEngine()
    model = _make_model(tier=ModelTier.TIER_1_HIGH,
                          state=ModelLifecycleState.APPROVED_FOR_PRODUCTION)
    eng.register_model(model)
    try:
        eng.transition_model(
            model_id="M1",
            to_state=ModelLifecycleState.IN_PRODUCTION,
            actor_user_id="alice", timestamp="2026-05-01T00:00:00Z")
        assert False
    except ValueError as e:
        assert "validation" in str(e).lower()


def _test_engine_tier1_production_allowed_after_pass():
    """Tier 1 → IN_PRODUCTION allowed after PASS validation."""
    eng = ModelGovernanceEngine()
    model = _make_model(tier=ModelTier.TIER_1_HIGH,
                          state=ModelLifecycleState.APPROVED_FOR_PRODUCTION)
    eng.register_model(model)
    # Record PASS results for all required gates
    for gate in REQUIRED_VALIDATION_GATES_BY_TIER[ModelTier.TIER_1_HIGH]:
        eng.record_validation_test(ValidationTestResult(
            test_result_id=f"VR-{gate.value}",
            model_id="M1", gate=gate,
            verdict=ValidationVerdict.PASS,
            test_date="2026-05-01"))
    eng.assemble_report(
        report_id="REP1", model_id="M1",
        report_date="2026-05-01")
    # Now transition allowed
    updated = eng.transition_model(
        model_id="M1",
        to_state=ModelLifecycleState.IN_PRODUCTION,
        actor_user_id="alice", timestamp="2026-05-01T00:00:00Z")
    assert updated.current_state == ModelLifecycleState.IN_PRODUCTION
    assert updated.deployment_date == "2026-05-01"


def _test_engine_tier3_no_validation_required():
    """Tier 3 → IN_PRODUCTION doesn't require validation report."""
    eng = ModelGovernanceEngine()
    model = _make_model(tier=ModelTier.TIER_3_LOW,
                          state=ModelLifecycleState.APPROVED_FOR_PRODUCTION)
    eng.register_model(model)
    # No validation record — but Tier 3 doesn't require it
    updated = eng.transition_model(
        model_id="M1",
        to_state=ModelLifecycleState.IN_PRODUCTION,
        actor_user_id="alice", timestamp="2026-05-01T00:00:00Z")
    assert updated.current_state == ModelLifecycleState.IN_PRODUCTION


def _test_engine_run_psi_drift_unknown_model():
    eng = ModelGovernanceEngine()
    try:
        eng.run_psi_drift(
            test_id="T1", model_id="UNKNOWN",
            feature_name="x",
            baseline_distribution=[Decimal("0.5"), Decimal("0.5")],
            current_distribution=[Decimal("0.5"), Decimal("0.5")],
            n_baseline=1000, n_current=1000,
            test_date="2026-05-01")
        assert False
    except KeyError:
        pass


def _test_engine_actionable_drift_filter():
    eng = ModelGovernanceEngine()
    eng.register_model(_make_model())
    base = [Decimal("0.25")] * 4
    eng.run_psi_drift(
        test_id="T1", model_id="M1", feature_name="x",
        baseline_distribution=base, current_distribution=base,
        n_baseline=1000, n_current=1000,
        test_date="2026-05-01")
    # Major drift
    base_drift = [Decimal("0.5"), Decimal("0.5"),
                       Decimal("0.001"), Decimal("0.001")]
    curr_drift = [Decimal("0.001"), Decimal("0.001"),
                       Decimal("0.5"), Decimal("0.5")]
    eng.run_psi_drift(
        test_id="T2", model_id="M1", feature_name="y",
        baseline_distribution=base_drift,
        current_distribution=curr_drift,
        n_baseline=1000, n_current=1000,
        test_date="2026-05-01")
    actionable = eng.actionable_drift_results()
    assert len(actionable) == 1
    assert actionable[0].test_id == "T2"


def _test_engine_disparate_impact_filter():
    eng = ModelGovernanceEngine()
    eng.register_model(_make_model())
    eng.run_four_fifths_test(
        test_id="B1", model_id="M1",
        protected_class="gender", reference_group="male",
        comparison_group="female",
        n_reference_total=1000, n_reference_positive=500,
        n_comparison_total=1000, n_comparison_positive=200,
        test_date="2026-05-01")
    di = eng.models_with_disparate_impact()
    assert len(di) == 1


def _test_engine_board_summary_empty():
    eng = ModelGovernanceEngine()
    s = eng.board_summary()
    assert s["n_models_total"] == 0


def _test_engine_board_summary_aggregates():
    eng = ModelGovernanceEngine()
    eng.register_model(_make_model(
        mid="M1", tier=ModelTier.TIER_1_HIGH))
    eng.register_model(_make_model(
        mid="M2", tier=ModelTier.TIER_3_LOW))
    s = eng.board_summary()
    assert s["n_models_total"] == 2
    assert s["n_tier_1"] == 1
    assert s["n_tier_3"] == 1


def self_test() -> None:
    tests = [
        _test_lifecycle_valid_path,
        _test_lifecycle_cannot_skip_to_production,
        _test_lifecycle_retired_terminal,
        _test_tier_validation_cadence,
        _test_psi_no_drift,
        _test_psi_major_drift,
        _test_psi_bins_mismatch_raises,
        _test_psi_drift_severity_thresholds,
        _test_detect_psi_insufficient_data,
        _test_detect_psi_no_drift,
        _test_detect_psi_major_drift_actionable,
        _test_ks_identical_zero,
        _test_ks_disjoint_max,
        _test_ks_critical_decreases_with_n,
        _test_ks_insufficient_returns_insufficient,
        _test_required_gates_tier_1_more,
        _test_validation_pass_all_gates,
        _test_validation_fail_blocks,
        _test_validation_missing_gate_inconclusive,
        _test_explain_no_provider_requires_provider,
        _test_explain_with_hook,
        _test_adverse_action_codes_loaded,
        _test_map_features_to_adverse_action,
        _test_four_fifths_no_bias,
        _test_four_fifths_disparate_impact,
        _test_four_fifths_potential_bias,
        _test_four_fifths_insufficient_data,
        _test_demographic_parity_within_tolerance,
        _test_demographic_parity_disparate,
        _test_engine_register_dup_raises,
        _test_engine_invalid_transition_raises,
        _test_engine_tier1_production_blocked_without_validation,
        _test_engine_tier1_production_allowed_after_pass,
        _test_engine_tier3_no_validation_required,
        _test_engine_run_psi_drift_unknown_model,
        _test_engine_actionable_drift_filter,
        _test_engine_disparate_impact_filter,
        _test_engine_board_summary_empty,
        _test_engine_board_summary_aggregates,
    ]
    failed = []
    for t in tests:
        try:
            t()
        except AssertionError as e:
            failed.append((t.__name__, str(e)))
        except Exception as e:
            failed.append((t.__name__, f"{type(e).__name__}: {e}"))
    if failed:
        print(f"✗ model_governance self-test: {len(failed)} failures",
              file=sys.stderr)
        for name, msg in failed:
            print(f"  - {name}: {msg}", file=sys.stderr)
        raise SystemExit(1)
    print(f"✓ model_governance self-test passed ({len(tests)} tests)")


if __name__ == "__main__":
    self_test()
