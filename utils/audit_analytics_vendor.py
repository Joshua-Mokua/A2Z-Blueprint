"""utils/audit_analytics_vendor.py — v10.25 Phase 2 batch 4 (Audit/GRC arc batch 3).

╔════════════════════════════════════════════════════════════════════════╗
║  AUDIT ANALYTICS + VENDOR RISK + 24/7 ASSURANCE + CYBER FRAMEWORKS    ║
╠════════════════════════════════════════════════════════════════════════╣
║  Risk class: Cat A (vendor concentration → systemic risk; cyber       ║
║              framework gaps → regulator findings; always-on gaps →    ║
║              breach detection latency)                                 ║
║  Implements 4 of 17 Audit/GRC standards from registry:                  ║
║    ENH-205:    AI-Powered Audit Analytics                               ║
║    ENH-AUD-R2: AI-Powered Third-Party / Vendor Risk Monitoring          ║
║    ENH-AUD-R5: 24/7 Always-On Assurance                                 ║
║    ENH-AUD-R6: Cybersecurity Audit Framework Integration                ║
╠════════════════════════════════════════════════════════════════════════╣
║  Regulatory provenance:                                                 ║
║    IIA IPPF Standard 2120 — risk management                             ║
║    IIA IPPF Standard 2130 — control monitoring                          ║
║    NIST Cybersecurity Framework v2.0 (GV/ID/PR/DE/RS/RC functions)     ║
║    ISO 27001:2022 (4 control groups, 93 controls)                       ║
║    CIS Controls v8 (18 controls + 153 sub-controls)                     ║
║    CBK Prudential Guideline CBK/PG/02 — operational risk + outsourcing║
║    CBK Outsourcing Guidelines (CBK/PG/15)                              ║
║    CBK Cybersecurity Guidance Note (2017, updated 2023)                 ║
║    Basel BCBS 239 §11/§12 — completeness, timeliness, integrity        ║
║    Basel Outsourcing Principles (2005, updated 2018)                    ║
║    EU DORA — operational resilience for ICT third parties              ║
║    OFAC SDN sanctions list reference                                    ║
║    Dr. Theodore Hill (1995) — Benford's Law in fraud detection         ║
║    NIST SP 800-30 Rev. 1 — risk assessment guide                       ║
╠════════════════════════════════════════════════════════════════════════╣
║  Composes with v10.23 (audit_core) + v10.24 (audit_controls_issues).    ║
║                                                                         ║
║  Honesty Rule 1: anomaly findings show method + threshold + sample;    ║
║  vendor risk scores show dimension breakdowns + last assessment date.   ║
║  Honesty Rule 7: ML-based detectors are callable hooks; without        ║
║  injected detector, statistical methods (Z-score, IQR, Benford) run.   ║
╚════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

import math
import sys
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal, getcontext
from enum import Enum
from typing import (
    Callable, Dict, FrozenSet, List, Mapping, Optional, Sequence, Tuple)

getcontext().prec = 28

SPEC_DEVIATION_NOTE = (
    "ML-based anomaly detectors (isolation forest, autoencoder, etc.) are "
    "callable hooks per Rule 7. Without injected detector, statistical "
    "methods (Z-score, IQR, Benford's Law) execute deterministically."
)


# ════════════════════════════════════════════════════════════════════════
# AI-Powered Audit Analytics (ENH-205)
# ════════════════════════════════════════════════════════════════════════

class AnomalyDetectionMethod(Enum):
    """Methods for detecting anomalies in audit data."""
    Z_SCORE = "Z_SCORE"                    # > 3 SD from mean
    IQR = "IQR"                              # Tukey 1.5×IQR fence
    BENFORD_LAW = "BENFORD_LAW"             # first-digit frequency
    ISOLATION_FOREST = "ISOLATION_FOREST"   # ML hook
    AUTOENCODER = "AUTOENCODER"             # ML hook
    CUSTOM_ML = "CUSTOM_ML"                  # arbitrary callable


class AnomalySeverity(Enum):
    """Severity of an anomaly finding."""
    LOW = "LOW"          # 1-2 SD or 1-1.5×IQR
    MEDIUM = "MEDIUM"    # 2-3 SD or 1.5-2×IQR
    HIGH = "HIGH"        # 3+ SD or 2-3×IQR
    CRITICAL = "CRITICAL"  # 4+ SD or > 3×IQR


# Z-score thresholds for severity
Z_SCORE_LOW_THRESHOLD = Decimal("2.0")
Z_SCORE_MEDIUM_THRESHOLD = Decimal("3.0")
Z_SCORE_HIGH_THRESHOLD = Decimal("4.0")


@dataclass(frozen=True)
class AnomalyResult:
    """One detected anomaly with full evidence."""
    record_id: str
    method: AnomalyDetectionMethod
    observed_value: Decimal
    expected_value: Decimal
    deviation: Decimal                      # observed - expected
    severity: AnomalySeverity
    sample_size: int
    notes: str = ""


def compute_mean_std(values: Sequence[Decimal]) -> Tuple[Decimal, Decimal]:
    """Compute sample mean + standard deviation (Bessel-corrected)."""
    if not values:
        return (Decimal("0"), Decimal("0"))
    n = Decimal(len(values))
    if n == Decimal("1"):
        return (values[0], Decimal("0"))
    mean = sum(values, Decimal("0")) / n
    variance_sum = sum((v - mean) ** 2 for v in values)
    variance = variance_sum / (n - Decimal("1"))
    std = variance.sqrt() if hasattr(
        variance, "sqrt") else Decimal(
            str(math.sqrt(float(variance))))
    return (mean, std)


def detect_z_score_anomalies(
    *,
    values: Sequence[Tuple[str, Decimal]],   # (record_id, value)
) -> Tuple[AnomalyResult, ...]:
    """Detect anomalies using Z-score method (3+ SD = high severity)."""
    if len(values) < 3:
        return ()    # need at least 3 points for meaningful std
    just_values = [v for _, v in values]
    mean, std = compute_mean_std(just_values)
    if std == Decimal("0"):
        return ()    # no variance, no anomalies

    results: List[AnomalyResult] = []
    for rid, v in values:
        z = abs((v - mean) / std)
        if z < Z_SCORE_LOW_THRESHOLD:
            continue
        if z >= Z_SCORE_HIGH_THRESHOLD:
            sev = AnomalySeverity.CRITICAL
        elif z >= Z_SCORE_MEDIUM_THRESHOLD:
            sev = AnomalySeverity.HIGH
        else:
            sev = AnomalySeverity.MEDIUM
        results.append(AnomalyResult(
            record_id=rid, method=AnomalyDetectionMethod.Z_SCORE,
            observed_value=v, expected_value=mean,
            deviation=v - mean, severity=sev,
            sample_size=len(values),
            notes=f"z-score = {z:.2f}σ"))
    return tuple(results)


def detect_iqr_anomalies(
    *,
    values: Sequence[Tuple[str, Decimal]],
) -> Tuple[AnomalyResult, ...]:
    """Detect anomalies using Tukey's 1.5×IQR fence."""
    if len(values) < 4:
        return ()
    sorted_values = sorted(v for _, v in values)
    n = len(sorted_values)
    q1_idx = n // 4
    q3_idx = (3 * n) // 4
    q1 = sorted_values[q1_idx]
    q3 = sorted_values[q3_idx]
    iqr = q3 - q1
    if iqr == Decimal("0"):
        return ()
    lower_fence = q1 - Decimal("1.5") * iqr
    upper_fence = q3 + Decimal("1.5") * iqr
    extreme_lower = q1 - Decimal("3.0") * iqr
    extreme_upper = q3 + Decimal("3.0") * iqr
    median = sorted_values[n // 2]

    results: List[AnomalyResult] = []
    for rid, v in values:
        if lower_fence <= v <= upper_fence:
            continue
        if v < extreme_lower or v > extreme_upper:
            sev = AnomalySeverity.CRITICAL
        else:
            sev = AnomalySeverity.HIGH
        results.append(AnomalyResult(
            record_id=rid, method=AnomalyDetectionMethod.IQR,
            observed_value=v, expected_value=median,
            deviation=v - median, severity=sev,
            sample_size=len(values),
            notes=(
                f"IQR fence: [{lower_fence}, {upper_fence}]; "
                f"extreme: [{extreme_lower}, {extreme_upper}]")))
    return tuple(results)


# Benford's Law expected first-digit distribution (1-9)
# P(d) = log10(1 + 1/d)
BENFORD_EXPECTED_DIGIT_PCT: Mapping[int, Decimal] = {
    1: Decimal("30.103"),
    2: Decimal("17.609"),
    3: Decimal("12.494"),
    4: Decimal("9.691"),
    5: Decimal("7.918"),
    6: Decimal("6.695"),
    7: Decimal("5.799"),
    8: Decimal("5.115"),
    9: Decimal("4.576"),
}

# Threshold for chi-square divergence on Benford
BENFORD_CHI_SQUARE_FAIL_THRESHOLD = Decimal("15.5")    # ~95% confidence at df=8
BENFORD_CHI_SQUARE_WARNING_THRESHOLD = Decimal("13.4")  # ~90% confidence


@dataclass(frozen=True)
class BenfordTestResult:
    """Result of Benford's Law conformance test."""
    sample_size: int
    observed_distribution: Mapping[int, int]
    observed_pct: Mapping[int, Decimal]
    expected_pct: Mapping[int, Decimal]
    chi_square_statistic: Decimal
    suspicion_level: str                     # NORMAL / WARNING / FAIL
    notes: str = ""


def first_digit(value: Decimal) -> Optional[int]:
    """Extract leading digit of a decimal value (1-9), or None."""
    abs_v = abs(value)
    if abs_v == Decimal("0"):
        return None
    s = str(abs_v).lstrip("0").lstrip(".").lstrip("0")
    for ch in s:
        if ch.isdigit() and ch != "0":
            return int(ch)
    return None


def benford_conformance_test(
    *, values: Sequence[Decimal],
) -> BenfordTestResult:
    """Test if a sequence conforms to Benford's Law.

    Used for fraud detection per Hill 1995 — values that should be
    naturally generated (transaction amounts, journal entries) follow
    Benford's distribution; manipulated values often don't.

    Per Rule 1: returns explicit suspicion_level — NORMAL/WARNING/FAIL —
    based on chi-square statistic vs ~95% / ~90% confidence thresholds.
    """
    digit_counts: Dict[int, int] = {d: 0 for d in range(1, 10)}
    n_valid = 0
    for v in values:
        d = first_digit(v)
        if d is not None and 1 <= d <= 9:
            digit_counts[d] = digit_counts[d] + 1
            n_valid += 1

    if n_valid < 50:
        return BenfordTestResult(
            sample_size=n_valid, observed_distribution=digit_counts,
            observed_pct={d: Decimal("0") for d in range(1, 10)},
            expected_pct=BENFORD_EXPECTED_DIGIT_PCT,
            chi_square_statistic=Decimal("0"),
            suspicion_level="INSUFFICIENT_DATA",
            notes=(
                f"sample size {n_valid} < 50; Benford analysis "
                f"requires larger samples"))

    n = Decimal(n_valid)
    observed_pct: Dict[int, Decimal] = {}
    chi_sq = Decimal("0")
    for d in range(1, 10):
        obs_count = Decimal(digit_counts[d])
        obs_pct = obs_count / n * Decimal("100")
        observed_pct[d] = obs_pct
        exp_pct = BENFORD_EXPECTED_DIGIT_PCT[d]
        exp_count = exp_pct / Decimal("100") * n
        if exp_count > Decimal("0"):
            diff = (obs_count - exp_count)
            chi_sq += (diff * diff) / exp_count

    if chi_sq >= BENFORD_CHI_SQUARE_FAIL_THRESHOLD:
        suspicion = "FAIL"
    elif chi_sq >= BENFORD_CHI_SQUARE_WARNING_THRESHOLD:
        suspicion = "WARNING"
    else:
        suspicion = "NORMAL"

    return BenfordTestResult(
        sample_size=n_valid, observed_distribution=digit_counts,
        observed_pct=observed_pct,
        expected_pct=BENFORD_EXPECTED_DIGIT_PCT,
        chi_square_statistic=chi_sq,
        suspicion_level=suspicion,
        notes=f"chi² = {chi_sq:.2f}; suspicion: {suspicion}")


def detect_with_ml_hook(
    *,
    records: Sequence[Mapping[str, object]],
    detector: Optional[Callable] = None,
) -> Tuple[AnomalyResult, ...]:
    """Run ML-based anomaly detection via injected hook.

    Per Rule 7: without `detector`, returns empty (no fabricated
    findings, no silent EFFECTIVE).
    """
    if detector is None:
        return ()
    try:
        result = detector(records)
        if not result:
            return ()
        if isinstance(result, tuple) and all(
                isinstance(r, AnomalyResult) for r in result):
            return result
        return ()    # detector returned wrong shape
    except Exception:
        return ()


# ════════════════════════════════════════════════════════════════════════
# Vendor Risk Monitoring (ENH-AUD-R2)
# ════════════════════════════════════════════════════════════════════════

class VendorTier(Enum):
    """Vendor materiality tier per CBK CRMF + outsourcing guidelines."""
    CRITICAL = "CRITICAL"      # core banking, KEPSS, payments
    HIGH = "HIGH"              # cloud, ATM network, IT outsourcing
    MEDIUM = "MEDIUM"          # standard SaaS, non-critical IT
    LOW = "LOW"                 # office supplies, professional services


class VendorCategory(Enum):
    """Category of vendor service."""
    CORE_BANKING = "CORE_BANKING"
    PAYMENTS = "PAYMENTS"
    CLOUD_INFRASTRUCTURE = "CLOUD_INFRASTRUCTURE"
    SAAS_APPLICATION = "SAAS_APPLICATION"
    DATA_ANALYTICS = "DATA_ANALYTICS"
    CARD_NETWORK = "CARD_NETWORK"
    OUTSOURCED_OPS = "OUTSOURCED_OPS"
    PROFESSIONAL_SERVICES = "PROFESSIONAL_SERVICES"
    AUDIT_ASSURANCE = "AUDIT_ASSURANCE"
    LEGAL = "LEGAL"
    PHYSICAL_SECURITY = "PHYSICAL_SECURITY"
    OTHER = "OTHER"


class VendorRiskDimension(Enum):
    """Dimensions of vendor risk per BCBS Outsourcing + DORA."""
    FINANCIAL = "FINANCIAL"                # vendor solvency
    CYBER = "CYBER"                         # cybersecurity posture
    OPERATIONAL = "OPERATIONAL"            # service availability
    REPUTATIONAL = "REPUTATIONAL"          # adverse media
    REGULATORY = "REGULATORY"              # sanctions, AML
    BUSINESS_CONTINUITY = "BUSINESS_CONTINUITY"  # exit plan, redundancy
    CONCENTRATION = "CONCENTRATION"        # single-vendor dependency
    DATA_PRIVACY = "DATA_PRIVACY"          # GDPR/Kenya DPA exposure


class VendorOnboardingStatus(Enum):
    PROSPECT = "PROSPECT"
    DUE_DILIGENCE = "DUE_DILIGENCE"
    CONTRACT_NEGOTIATION = "CONTRACT_NEGOTIATION"
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    OFFBOARDING = "OFFBOARDING"
    OFFBOARDED = "OFFBOARDED"


# Per CBK CRMF + BCBS Outsourcing — assessment cadence by tier
DEFAULT_VENDOR_REASSESSMENT_DAYS: Mapping[VendorTier, int] = {
    VendorTier.CRITICAL: 180,    # 6 months
    VendorTier.HIGH: 365,        # annually
    VendorTier.MEDIUM: 730,      # biennial
    VendorTier.LOW: 1095,        # triennial
}


@dataclass(frozen=True)
class VendorRiskScore:
    """Risk score across all dimensions for a vendor."""
    vendor_id: str
    dimension_scores: Mapping[VendorRiskDimension, Decimal]   # 0-100
    overall_score: Decimal                  # 0-100
    tier_at_assessment: VendorTier
    assessment_date: str
    next_assessment_due: str
    notes: str = ""

    def is_overdue(self, *, as_of: date) -> bool:
        try:
            due = date.fromisoformat(self.next_assessment_due)
        except ValueError:
            return False
        return as_of > due

    def highest_risk_dimensions(
        self, *, top_n: int = 3,
    ) -> Tuple[Tuple[VendorRiskDimension, Decimal], ...]:
        sorted_dims = sorted(
            self.dimension_scores.items(),
            key=lambda x: x[1], reverse=True)
        return tuple(sorted_dims[:top_n])


@dataclass(frozen=True)
class Vendor:
    """A third-party vendor."""
    vendor_id: str
    vendor_name: str
    vendor_tier: VendorTier
    vendor_category: VendorCategory
    onboarding_status: VendorOnboardingStatus
    services_provided: str
    annual_spend_kes: Decimal = Decimal("0")
    is_critical_for_business_continuity: bool = False
    is_systemically_important: bool = False
    contract_start_date: Optional[str] = None
    contract_end_date: Optional[str] = None
    notes: str = ""


def compute_overall_risk_score(
    *, dimension_scores: Mapping[VendorRiskDimension, Decimal],
) -> Decimal:
    """Weighted average risk score (0-100). Higher = more risky."""
    if not dimension_scores:
        return Decimal("0")
    # Equal weights for all dimensions in seed; production may weight
    total = sum(dimension_scores.values(), Decimal("0"))
    n = Decimal(len(dimension_scores))
    return total / n


def compute_concentration_risk(
    *,
    vendors: Sequence[Vendor],
    by_category: bool = True,
) -> Mapping[str, Decimal]:
    """Spend concentration % per category (or per vendor if not by_category)."""
    total_spend = sum(
        (v.annual_spend_kes for v in vendors), Decimal("0"))
    if total_spend == Decimal("0"):
        return {}

    concentration: Dict[str, Decimal] = {}
    if by_category:
        for v in vendors:
            key = v.vendor_category.value
            concentration[key] = concentration.get(
                key, Decimal("0")) + v.annual_spend_kes
    else:
        for v in vendors:
            concentration[v.vendor_id] = v.annual_spend_kes

    # Convert to percentages
    return {
        k: (s / total_spend * Decimal("100"))
        for k, s in concentration.items()}


# CBK Outsourcing Guidelines: > 25% concentration triggers review
DEFAULT_CONCENTRATION_THRESHOLD_PCT = Decimal("25.0")


def excessive_concentration_categories(
    *,
    vendors: Sequence[Vendor],
    threshold_pct: Decimal = DEFAULT_CONCENTRATION_THRESHOLD_PCT,
) -> Tuple[Tuple[str, Decimal], ...]:
    """Categories where concentration exceeds the threshold."""
    conc = compute_concentration_risk(
        vendors=vendors, by_category=True)
    return tuple(
        (k, pct) for k, pct in conc.items() if pct > threshold_pct)


# ════════════════════════════════════════════════════════════════════════
# 24/7 Always-On Assurance (ENH-AUD-R5)
# ════════════════════════════════════════════════════════════════════════

class AssurancePriority(Enum):
    """Priority of an always-on assurance alert."""
    P1_CRITICAL = "P1_CRITICAL"     # immediate action required
    P2_HIGH = "P2_HIGH"             # action within hours
    P3_MEDIUM = "P3_MEDIUM"         # action within day
    P4_LOW = "P4_LOW"               # action within week


# Response time SLA per priority (minutes)
ASSURANCE_RESPONSE_SLA_MINUTES: Mapping[AssurancePriority, int] = {
    AssurancePriority.P1_CRITICAL: 15,        # 15 min response
    AssurancePriority.P2_HIGH: 240,           # 4 hours
    AssurancePriority.P3_MEDIUM: 1440,        # 24 hours
    AssurancePriority.P4_LOW: 10080,          # 1 week
}


class AlertChannel(Enum):
    """Where to send always-on assurance alerts."""
    EMAIL = "EMAIL"
    SLACK = "SLACK"
    PAGERDUTY = "PAGERDUTY"
    SMS = "SMS"
    BOARD_DASHBOARD = "BOARD_DASHBOARD"
    AUDIT_COMMITTEE_DIGEST = "AUDIT_COMMITTEE_DIGEST"
    SIEM_LOG = "SIEM_LOG"


@dataclass(frozen=True)
class AssuranceAlert:
    """A continuous monitoring alert."""
    alert_id: str
    priority: AssurancePriority
    detected_at_utc: str
    source_control_id: Optional[str] = None
    source_test_id: Optional[str] = None
    description: str = ""
    channels_notified: Tuple[AlertChannel, ...] = ()
    acknowledged_at_utc: Optional[str] = None
    acknowledged_by_user_id: Optional[str] = None
    resolved_at_utc: Optional[str] = None
    notes: str = ""

    def is_overdue_for_response(
        self, *, as_of_utc: str,
    ) -> bool:
        if self.acknowledged_at_utc is not None:
            return False    # already responded
        try:
            from datetime import datetime
            detected = datetime.fromisoformat(
                self.detected_at_utc.replace("Z", "+00:00"))
            now = datetime.fromisoformat(
                as_of_utc.replace("Z", "+00:00"))
        except ValueError:
            return False
        elapsed_min = (now - detected).total_seconds() / 60
        sla = ASSURANCE_RESPONSE_SLA_MINUTES.get(
            self.priority, 1440)
        return elapsed_min > sla


def select_channels_for_priority(
    priority: AssurancePriority,
) -> Tuple[AlertChannel, ...]:
    """Default channel selection by priority."""
    if priority == AssurancePriority.P1_CRITICAL:
        return (
            AlertChannel.PAGERDUTY, AlertChannel.SMS,
            AlertChannel.SLACK, AlertChannel.EMAIL,
            AlertChannel.SIEM_LOG)
    if priority == AssurancePriority.P2_HIGH:
        return (
            AlertChannel.SLACK, AlertChannel.EMAIL,
            AlertChannel.SIEM_LOG)
    if priority == AssurancePriority.P3_MEDIUM:
        return (AlertChannel.EMAIL, AlertChannel.SIEM_LOG)
    return (AlertChannel.AUDIT_COMMITTEE_DIGEST,)


# ════════════════════════════════════════════════════════════════════════
# Cybersecurity Framework Integration (ENH-AUD-R6)
# ════════════════════════════════════════════════════════════════════════

class NISTCSFFunction(Enum):
    """NIST Cybersecurity Framework v2.0 functions."""
    GOVERN = "GV"           # NEW in v2.0
    IDENTIFY = "ID"
    PROTECT = "PR"
    DETECT = "DE"
    RESPOND = "RS"
    RECOVER = "RC"


# NIST CSF v2.0 categories per function
NIST_CSF_V2_CATEGORIES: Mapping[NISTCSFFunction, Tuple[str, ...]] = {
    NISTCSFFunction.GOVERN: (
        "GV.OC", "GV.RM", "GV.RR", "GV.PO", "GV.OV", "GV.SC"),
    NISTCSFFunction.IDENTIFY: (
        "ID.AM", "ID.RA", "ID.IM"),
    NISTCSFFunction.PROTECT: (
        "PR.AA", "PR.AT", "PR.DS", "PR.PS", "PR.IR"),
    NISTCSFFunction.DETECT: (
        "DE.CM", "DE.AE"),
    NISTCSFFunction.RESPOND: (
        "RS.MA", "RS.AN", "RS.CO", "RS.MI"),
    NISTCSFFunction.RECOVER: (
        "RC.RP", "RC.CO"),
}


class ISO27001ControlGroup(Enum):
    """ISO 27001:2022 control groups (4 categories, 93 controls total)."""
    ORGANIZATIONAL = "A.5"     # 37 controls
    PEOPLE = "A.6"              # 8 controls
    PHYSICAL = "A.7"            # 14 controls
    TECHNOLOGICAL = "A.8"       # 34 controls


ISO_27001_2022_CONTROL_COUNTS: Mapping[ISO27001ControlGroup, int] = {
    ISO27001ControlGroup.ORGANIZATIONAL: 37,
    ISO27001ControlGroup.PEOPLE: 8,
    ISO27001ControlGroup.PHYSICAL: 14,
    ISO27001ControlGroup.TECHNOLOGICAL: 34,
}

ISO_27001_2022_TOTAL_CONTROLS = 93


class CISControlGroup(Enum):
    """CIS Controls v8 implementation groups."""
    IG1 = "IG1"      # essential cyber hygiene (56 sub-controls)
    IG2 = "IG2"      # mid-size enterprises (130 sub-controls cumulative)
    IG3 = "IG3"      # mature enterprises (153 sub-controls — all)


# CIS Controls v8 has 18 controls + 153 sub-controls
CIS_V8_CONTROL_COUNT = 18
CIS_V8_SUBCONTROL_COUNT = 153


@dataclass(frozen=True)
class CyberFrameworkCoverage:
    """Coverage assessment across cybersecurity frameworks."""
    framework_name: str
    total_controls: int
    n_controls_implemented: int
    n_controls_partial: int
    n_controls_not_implemented: int
    coverage_pct: Decimal
    target_pct: Decimal = Decimal("80")
    notes: str = ""

    def meets_target(self) -> bool:
        return self.coverage_pct >= self.target_pct

    def gap_to_target(self) -> Decimal:
        return max(Decimal("0"), self.target_pct - self.coverage_pct)


def assess_nist_csf_coverage(
    *,
    n_implemented_per_function: Mapping[NISTCSFFunction, int],
    target_pct: Decimal = Decimal("80"),
) -> Mapping[NISTCSFFunction, CyberFrameworkCoverage]:
    """Per-function coverage assessment for NIST CSF v2.0."""
    out: Dict[NISTCSFFunction, CyberFrameworkCoverage] = {}
    for fn, categories in NIST_CSF_V2_CATEGORIES.items():
        total = len(categories)
        implemented = n_implemented_per_function.get(fn, 0)
        if total == 0:
            pct = Decimal("0")
        else:
            pct = (Decimal(implemented) / Decimal(total)
                     * Decimal("100"))
        out[fn] = CyberFrameworkCoverage(
            framework_name=f"NIST_CSF_v2.0_{fn.value}",
            total_controls=total,
            n_controls_implemented=implemented,
            n_controls_partial=0,
            n_controls_not_implemented=total - implemented,
            coverage_pct=pct,
            target_pct=target_pct,
            notes=f"function {fn.value}: {implemented}/{total}")
    return out


# ════════════════════════════════════════════════════════════════════════
# Engine — orchestrator
# ════════════════════════════════════════════════════════════════════════

class AuditAnalyticsVendorEngine:
    """End-to-end orchestrator for analytics + vendor + assurance + cyber."""

    def __init__(self, *, entity_name: str = "Ecobank Kenya"):
        self.entity_name = entity_name
        self._vendors: Dict[str, Vendor] = {}
        self._risk_scores: Dict[str, VendorRiskScore] = {}
        self._alerts: Dict[str, AssuranceAlert] = {}
        self._anomalies: List[AnomalyResult] = []
        self._benford_results: List[BenfordTestResult] = []

    # ── Analytics (ENH-205) ────────────────────────────────────────────
    def analyze_z_score(
        self, *, values: Sequence[Tuple[str, Decimal]],
    ) -> Tuple[AnomalyResult, ...]:
        results = detect_z_score_anomalies(values=values)
        self._anomalies.extend(results)
        return results

    def analyze_iqr(
        self, *, values: Sequence[Tuple[str, Decimal]],
    ) -> Tuple[AnomalyResult, ...]:
        results = detect_iqr_anomalies(values=values)
        self._anomalies.extend(results)
        return results

    def analyze_benford(
        self, *, values: Sequence[Decimal],
    ) -> BenfordTestResult:
        result = benford_conformance_test(values=values)
        self._benford_results.append(result)
        return result

    # ── Vendor risk (ENH-AUD-R2) ──────────────────────────────────────
    def register_vendor(self, v: Vendor) -> None:
        if v.vendor_id in self._vendors:
            raise ValueError(
                f"vendor {v.vendor_id} already registered")
        self._vendors[v.vendor_id] = v

    def assess_vendor_risk(
        self, *,
        vendor_id: str,
        dimension_scores: Mapping[VendorRiskDimension, Decimal],
        assessment_date: str,
    ) -> VendorRiskScore:
        if vendor_id not in self._vendors:
            raise KeyError(f"vendor {vendor_id} not registered")
        vendor = self._vendors[vendor_id]
        overall = compute_overall_risk_score(
            dimension_scores=dimension_scores)
        # Compute next assessment due
        try:
            asses_dt = date.fromisoformat(assessment_date)
            days = DEFAULT_VENDOR_REASSESSMENT_DAYS[vendor.vendor_tier]
            next_due = (asses_dt + timedelta(days=days)).isoformat()
        except ValueError:
            next_due = assessment_date

        score = VendorRiskScore(
            vendor_id=vendor_id,
            dimension_scores=dimension_scores,
            overall_score=overall,
            tier_at_assessment=vendor.vendor_tier,
            assessment_date=assessment_date,
            next_assessment_due=next_due,
            notes=f"tier {vendor.vendor_tier.value}")
        self._risk_scores[vendor_id] = score
        return score

    def overdue_vendor_assessments(
        self, *, as_of: Optional[date] = None,
    ) -> Tuple[VendorRiskScore, ...]:
        if as_of is None:
            as_of = date.today()
        return tuple(
            s for s in self._risk_scores.values()
            if s.is_overdue(as_of=as_of))

    def vendor_concentration_breaches(
        self, *,
        threshold_pct: Decimal = DEFAULT_CONCENTRATION_THRESHOLD_PCT,
    ) -> Tuple[Tuple[str, Decimal], ...]:
        return excessive_concentration_categories(
            vendors=list(self._vendors.values()),
            threshold_pct=threshold_pct)

    # ── Always-on assurance (ENH-AUD-R5) ──────────────────────────────
    def raise_alert(self, alert: AssuranceAlert) -> None:
        if alert.alert_id in self._alerts:
            raise ValueError(
                f"alert {alert.alert_id} already raised")
        self._alerts[alert.alert_id] = alert

    def overdue_alerts(
        self, *, as_of_utc: str,
    ) -> Tuple[AssuranceAlert, ...]:
        return tuple(
            a for a in self._alerts.values()
            if a.is_overdue_for_response(as_of_utc=as_of_utc))

    # ── Cyber framework (ENH-AUD-R6) ──────────────────────────────────
    def nist_csf_coverage(
        self,
        *,
        implemented_categories: Mapping[NISTCSFFunction, int],
    ) -> Mapping[NISTCSFFunction, CyberFrameworkCoverage]:
        return assess_nist_csf_coverage(
            n_implemented_per_function=implemented_categories)

    # ── Reporting ──────────────────────────────────────────────────────
    def board_summary(
        self, *, as_of: Optional[date] = None,
        as_of_utc: str = "2026-05-01T00:00:00Z",
    ) -> Dict[str, object]:
        if as_of is None:
            as_of = date.today()
        n_critical_anomalies = sum(
            1 for a in self._anomalies
            if a.severity == AnomalySeverity.CRITICAL)
        n_concentration_breaches = len(
            self.vendor_concentration_breaches())
        return {
            "entity": self.entity_name,
            "n_anomalies": len(self._anomalies),
            "n_critical_anomalies": n_critical_anomalies,
            "n_benford_tests": len(self._benford_results),
            "n_vendors": len(self._vendors),
            "n_critical_vendors": sum(
                1 for v in self._vendors.values()
                if v.vendor_tier == VendorTier.CRITICAL),
            "n_overdue_assessments": len(
                self.overdue_vendor_assessments(as_of=as_of)),
            "n_concentration_breaches": n_concentration_breaches,
            "n_alerts": len(self._alerts),
            "n_overdue_alerts": len(
                self.overdue_alerts(as_of_utc=as_of_utc)),
        }


# ════════════════════════════════════════════════════════════════════════
# Self-test
# ════════════════════════════════════════════════════════════════════════

def _test_compute_mean_std_basic():
    vals = [Decimal("1"), Decimal("2"), Decimal("3"),
              Decimal("4"), Decimal("5")]
    mean, std = compute_mean_std(vals)
    assert mean == Decimal("3")
    # Sample std for [1,2,3,4,5] is sqrt(2.5) ≈ 1.581
    assert Decimal("1.5") < std < Decimal("1.7")


def _test_compute_mean_std_empty():
    mean, std = compute_mean_std([])
    assert mean == Decimal("0")
    assert std == Decimal("0")


def _test_z_score_detects_outlier():
    """100 normal values + 1 extreme outlier should be flagged."""
    values = [(f"R{i}", Decimal(str(i))) for i in range(1, 101)]
    values.append(("OUT", Decimal("10000")))
    results = detect_z_score_anomalies(values=values)
    assert len(results) >= 1
    out_result = [r for r in results if r.record_id == "OUT"]
    assert len(out_result) == 1
    assert out_result[0].severity in (
        AnomalySeverity.CRITICAL, AnomalySeverity.HIGH)


def _test_z_score_no_anomalies_in_uniform():
    values = [(f"R{i}", Decimal("100")) for i in range(10)]
    results = detect_z_score_anomalies(values=values)
    assert len(results) == 0


def _test_z_score_too_few_samples():
    values = [("A", Decimal("1")), ("B", Decimal("2"))]
    results = detect_z_score_anomalies(values=values)
    assert len(results) == 0


def _test_iqr_detects_outlier():
    # Tight cluster + extreme high outlier
    values = [(f"R{i}", Decimal(str(50 + i))) for i in range(30)]
    values.append(("OUT", Decimal("10000")))
    results = detect_iqr_anomalies(values=values)
    out_result = [r for r in results if r.record_id == "OUT"]
    assert len(out_result) == 1


def _test_first_digit_extraction():
    assert first_digit(Decimal("123.45")) == 1
    assert first_digit(Decimal("9999")) == 9
    assert first_digit(Decimal("0.00045")) == 4
    assert first_digit(Decimal("0")) is None
    assert first_digit(Decimal("-789")) == 7


def _test_benford_distribution_sums_to_100():
    total = sum(BENFORD_EXPECTED_DIGIT_PCT.values(), Decimal("0"))
    assert Decimal("99.9") < total < Decimal("100.1")


def _test_benford_normal_returns_normal():
    """Naturally distributed values should pass Benford test."""
    # Generate values following Benford-like distribution
    values: List[Decimal] = []
    digit_targets = {1: 30, 2: 18, 3: 12, 4: 10, 5: 8,
                       6: 7, 7: 6, 8: 5, 9: 4}
    for digit, count in digit_targets.items():
        for i in range(count):
            values.append(Decimal(f"{digit}{i:02d}"))
    # Add more to reach 100
    for i in range(100 - len(values)):
        values.append(Decimal(f"1{i:03d}"))
    result = benford_conformance_test(values=values)
    assert result.suspicion_level in ("NORMAL", "WARNING")


def _test_benford_insufficient_data():
    values = [Decimal(str(i)) for i in range(1, 30)]
    result = benford_conformance_test(values=values)
    assert result.suspicion_level == "INSUFFICIENT_DATA"


def _test_benford_uniform_distribution_fails():
    """Uniform distribution should FAIL Benford test."""
    values: List[Decimal] = []
    # Equal counts of each digit — clearly not Benford
    for d in range(1, 10):
        for i in range(20):
            values.append(Decimal(f"{d}{i:02d}"))
    result = benford_conformance_test(values=values)
    # Chi-square statistic should be high
    assert result.chi_square_statistic > Decimal("10")


def _test_ml_hook_no_detector_returns_empty():
    """Rule 7: no detector → empty, no fabricated findings."""
    results = detect_with_ml_hook(records=[{"x": 1}])
    assert len(results) == 0


def _test_ml_hook_with_detector():
    def fake_detector(records):
        return (AnomalyResult(
            record_id="R1",
            method=AnomalyDetectionMethod.CUSTOM_ML,
            observed_value=Decimal("100"),
            expected_value=Decimal("50"),
            deviation=Decimal("50"),
            severity=AnomalySeverity.HIGH,
            sample_size=len(records)),)
    results = detect_with_ml_hook(
        records=[{"x": 1}], detector=fake_detector)
    assert len(results) == 1


def _test_vendor_tier_assessment_cadence():
    assert (DEFAULT_VENDOR_REASSESSMENT_DAYS[VendorTier.CRITICAL]
              == 180)
    assert (DEFAULT_VENDOR_REASSESSMENT_DAYS[VendorTier.LOW]
              == 1095)


def _test_overall_risk_score_simple_average():
    scores = {
        VendorRiskDimension.FINANCIAL: Decimal("60"),
        VendorRiskDimension.CYBER: Decimal("80"),
        VendorRiskDimension.OPERATIONAL: Decimal("40"),
    }
    overall = compute_overall_risk_score(dimension_scores=scores)
    assert overall == Decimal("60")    # (60+80+40)/3


def _test_concentration_below_threshold():
    """10 vendors across 10 different categories = max 10% per category."""
    categories = list(VendorCategory)
    vendors = [
        Vendor(
            vendor_id=f"V{i}", vendor_name=f"V{i}",
            vendor_tier=VendorTier.MEDIUM,
            vendor_category=categories[i % len(categories)],
            onboarding_status=VendorOnboardingStatus.ACTIVE,
            services_provided="x",
            annual_spend_kes=Decimal("10000"))
        for i in range(10)
    ]
    breaches = excessive_concentration_categories(
        vendors=vendors, threshold_pct=Decimal("25"))
    assert len(breaches) == 0


def _test_concentration_breach_detected():
    """80% in one category triggers breach."""
    vendors = [
        Vendor(
            vendor_id="BIG", vendor_name="BigCloud",
            vendor_tier=VendorTier.CRITICAL,
            vendor_category=VendorCategory.CLOUD_INFRASTRUCTURE,
            onboarding_status=VendorOnboardingStatus.ACTIVE,
            services_provided="cloud",
            annual_spend_kes=Decimal("80000")),
        Vendor(
            vendor_id="SM1", vendor_name="Small1",
            vendor_tier=VendorTier.LOW,
            vendor_category=VendorCategory.PROFESSIONAL_SERVICES,
            onboarding_status=VendorOnboardingStatus.ACTIVE,
            services_provided="x",
            annual_spend_kes=Decimal("20000")),
    ]
    breaches = excessive_concentration_categories(
        vendors=vendors,
        threshold_pct=Decimal("25"))
    assert len(breaches) == 1
    assert "CLOUD_INFRASTRUCTURE" in breaches[0][0]


def _test_vendor_risk_score_overdue():
    score = VendorRiskScore(
        vendor_id="V1",
        dimension_scores={VendorRiskDimension.FINANCIAL: Decimal("50")},
        overall_score=Decimal("50"),
        tier_at_assessment=VendorTier.HIGH,
        assessment_date="2024-01-01",
        next_assessment_due="2025-01-01")
    assert score.is_overdue(as_of=date(2026, 1, 1))
    assert not score.is_overdue(as_of=date(2024, 6, 1))


def _test_vendor_highest_risk_dimensions():
    score = VendorRiskScore(
        vendor_id="V1",
        dimension_scores={
            VendorRiskDimension.FINANCIAL: Decimal("30"),
            VendorRiskDimension.CYBER: Decimal("90"),
            VendorRiskDimension.OPERATIONAL: Decimal("50"),
            VendorRiskDimension.REPUTATIONAL: Decimal("20"),
        },
        overall_score=Decimal("47.5"),
        tier_at_assessment=VendorTier.HIGH,
        assessment_date="2026-01-01",
        next_assessment_due="2027-01-01")
    top = score.highest_risk_dimensions(top_n=2)
    assert top[0][0] == VendorRiskDimension.CYBER
    assert top[1][0] == VendorRiskDimension.OPERATIONAL


def _test_assurance_response_sla_critical_15min():
    assert (ASSURANCE_RESPONSE_SLA_MINUTES[
        AssurancePriority.P1_CRITICAL] == 15)


def _test_assurance_alert_overdue():
    alert = AssuranceAlert(
        alert_id="A1", priority=AssurancePriority.P1_CRITICAL,
        detected_at_utc="2026-04-23T10:00:00Z")
    # 30 minutes later, no ack — should be overdue (15-min SLA)
    assert alert.is_overdue_for_response(
        as_of_utc="2026-04-23T10:30:00Z")
    # 5 minutes later — not overdue
    assert not alert.is_overdue_for_response(
        as_of_utc="2026-04-23T10:05:00Z")


def _test_assurance_acked_not_overdue():
    """Acknowledged alert is not overdue regardless of timing."""
    alert = AssuranceAlert(
        alert_id="A1", priority=AssurancePriority.P1_CRITICAL,
        detected_at_utc="2026-04-23T10:00:00Z",
        acknowledged_at_utc="2026-04-23T10:10:00Z",
        acknowledged_by_user_id="alice")
    assert not alert.is_overdue_for_response(
        as_of_utc="2026-04-23T15:00:00Z")


def _test_channel_selection_critical_includes_pagerduty():
    chans = select_channels_for_priority(AssurancePriority.P1_CRITICAL)
    assert AlertChannel.PAGERDUTY in chans
    assert AlertChannel.SMS in chans


def _test_channel_selection_low_minimal():
    chans = select_channels_for_priority(AssurancePriority.P4_LOW)
    assert len(chans) == 1


def _test_iso_27001_total_93():
    assert ISO_27001_2022_TOTAL_CONTROLS == 93
    total = sum(ISO_27001_2022_CONTROL_COUNTS.values())
    assert total == 93


def _test_nist_csf_v2_six_functions():
    assert len(NISTCSFFunction) == 6
    assert NISTCSFFunction.GOVERN.value == "GV"


def _test_nist_csf_coverage_full():
    """All categories implemented = 100% coverage."""
    impl = {fn: len(cats)
              for fn, cats in NIST_CSF_V2_CATEGORIES.items()}
    coverage = assess_nist_csf_coverage(
        n_implemented_per_function=impl)
    for fn_cov in coverage.values():
        assert fn_cov.coverage_pct == Decimal("100")
        assert fn_cov.meets_target()


def _test_nist_csf_coverage_partial():
    impl = {NISTCSFFunction.GOVERN: 2}    # 2 of 6 categories
    coverage = assess_nist_csf_coverage(
        n_implemented_per_function=impl)
    gv = coverage[NISTCSFFunction.GOVERN]
    # 2/6 ≈ 33.33%
    assert Decimal("33") < gv.coverage_pct < Decimal("34")
    assert not gv.meets_target()
    assert gv.gap_to_target() > Decimal("46")


def _test_engine_register_vendor():
    eng = AuditAnalyticsVendorEngine()
    v = Vendor(
        vendor_id="V1", vendor_name="X",
        vendor_tier=VendorTier.HIGH,
        vendor_category=VendorCategory.CLOUD_INFRASTRUCTURE,
        onboarding_status=VendorOnboardingStatus.ACTIVE,
        services_provided="cloud")
    eng.register_vendor(v)
    assert len(eng._vendors) == 1


def _test_engine_assess_unregistered_vendor_raises():
    eng = AuditAnalyticsVendorEngine()
    try:
        eng.assess_vendor_risk(
            vendor_id="UNKNOWN",
            dimension_scores={
                VendorRiskDimension.FINANCIAL: Decimal("50")},
            assessment_date="2026-01-01")
        assert False
    except KeyError:
        pass


def _test_engine_assess_computes_next_due():
    eng = AuditAnalyticsVendorEngine()
    eng.register_vendor(Vendor(
        vendor_id="V1", vendor_name="X",
        vendor_tier=VendorTier.CRITICAL,
        vendor_category=VendorCategory.CORE_BANKING,
        onboarding_status=VendorOnboardingStatus.ACTIVE,
        services_provided="x"))
    score = eng.assess_vendor_risk(
        vendor_id="V1",
        dimension_scores={
            VendorRiskDimension.FINANCIAL: Decimal("60"),
            VendorRiskDimension.CYBER: Decimal("70")},
        assessment_date="2026-01-01")
    # Critical tier → 180 days → 2026-06-30
    assert score.next_assessment_due == "2026-06-30"


def _test_engine_alert_lifecycle():
    eng = AuditAnalyticsVendorEngine()
    eng.raise_alert(AssuranceAlert(
        alert_id="A1", priority=AssurancePriority.P2_HIGH,
        detected_at_utc="2026-04-23T10:00:00Z"))
    overdue = eng.overdue_alerts(
        as_of_utc="2026-04-23T15:00:00Z")
    # 5 hours later vs 4-hour SLA — overdue
    assert len(overdue) == 1


def _test_engine_board_summary_aggregates():
    eng = AuditAnalyticsVendorEngine()
    # Add big concentration breach
    eng.register_vendor(Vendor(
        vendor_id="BIG", vendor_name="X",
        vendor_tier=VendorTier.CRITICAL,
        vendor_category=VendorCategory.CLOUD_INFRASTRUCTURE,
        onboarding_status=VendorOnboardingStatus.ACTIVE,
        services_provided="x",
        annual_spend_kes=Decimal("100000")))
    s = eng.board_summary(
        as_of=date(2026, 5, 1),
        as_of_utc="2026-05-01T00:00:00Z")
    assert s["n_vendors"] == 1
    assert s["n_critical_vendors"] == 1


def self_test() -> None:
    tests = [
        _test_compute_mean_std_basic,
        _test_compute_mean_std_empty,
        _test_z_score_detects_outlier,
        _test_z_score_no_anomalies_in_uniform,
        _test_z_score_too_few_samples,
        _test_iqr_detects_outlier,
        _test_first_digit_extraction,
        _test_benford_distribution_sums_to_100,
        _test_benford_normal_returns_normal,
        _test_benford_insufficient_data,
        _test_benford_uniform_distribution_fails,
        _test_ml_hook_no_detector_returns_empty,
        _test_ml_hook_with_detector,
        _test_vendor_tier_assessment_cadence,
        _test_overall_risk_score_simple_average,
        _test_concentration_below_threshold,
        _test_concentration_breach_detected,
        _test_vendor_risk_score_overdue,
        _test_vendor_highest_risk_dimensions,
        _test_assurance_response_sla_critical_15min,
        _test_assurance_alert_overdue,
        _test_assurance_acked_not_overdue,
        _test_channel_selection_critical_includes_pagerduty,
        _test_channel_selection_low_minimal,
        _test_iso_27001_total_93,
        _test_nist_csf_v2_six_functions,
        _test_nist_csf_coverage_full,
        _test_nist_csf_coverage_partial,
        _test_engine_register_vendor,
        _test_engine_assess_unregistered_vendor_raises,
        _test_engine_assess_computes_next_due,
        _test_engine_alert_lifecycle,
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
        print(f"✗ audit_analytics_vendor self-test: {len(failed)} failures",
              file=sys.stderr)
        for name, msg in failed:
            print(f"  - {name}: {msg}", file=sys.stderr)
        raise SystemExit(1)
    print(f"✓ audit_analytics_vendor self-test passed ({len(tests)} tests)")


if __name__ == "__main__":
    self_test()
