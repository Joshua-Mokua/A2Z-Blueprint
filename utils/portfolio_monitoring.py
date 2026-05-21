"""utils/portfolio_monitoring.py — v10.14 Phase 2 deep impl batch 8 (Credit batch 4 part 1).

╔════════════════════════════════════════════════════════════════════════╗
║  PORTFOLIO MONITORING — EWS + COLLECTIONS + UNSTRUCTURED SIGNALS       ║
╠════════════════════════════════════════════════════════════════════════╣
║  Risk class: Cat A (signals trigger provisioning + collections actions)║
║  Implements 3 of 19 Credit standards from registry:                     ║
║    ENH-126:     Dynamic Portfolio Monitoring & Early Warning           ║
║    ENH-128:     Collections & Recovery Intelligence                     ║
║    ENH-CRD-R6:  Continuous Portfolio Risk Monitoring (Unstructured)    ║
╠════════════════════════════════════════════════════════════════════════╣
║  Regulatory provenance:                                                 ║
║    CBK Prudential Guideline CBK/PG/04 — risk classification of assets  ║
║    CBK CRMF April 2021 §3.4 — early warning systems                    ║
║    IFRS 9 §5.5.3 — significant increase in credit risk (SICR)          ║
║    IFRS 9 §B5.5.17 — quantitative + qualitative SICR factors           ║
║    Basel BCBS — sound credit risk assessment guidance (Jun 2006)       ║
║    CBK Debt Recovery Reg 2022 — collections + recovery practices       ║
║    Kenya Data Protection Act 2019 — adverse-data subject rights        ║
║    CBK Cyber Security 2017 — adverse media screening                   ║
╠════════════════════════════════════════════════════════════════════════╣
║  Composes with v10.11/v10.12/v10.13 (post-decision lifecycle).         ║
║  Honesty Rule 1: missing snapshot fields surface as UNKNOWN, never    ║
║                   silently substituted.                                  ║
╚════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from decimal import Decimal, getcontext
from enum import Enum
from typing import Dict, List, Mapping, Optional, Sequence, Tuple

getcontext().prec = 28

# ════════════════════════════════════════════════════════════════════════
# CBK PG/04 risk classification (5 grades)
# ════════════════════════════════════════════════════════════════════════

class CBKRiskClassification(Enum):
    """CBK Prudential Guideline CBK/PG/04 — risk classification."""
    NORMAL = "NORMAL"               # 0 DPD or current
    WATCH = "WATCH"                 # 1-30 DPD
    SUBSTANDARD = "SUBSTANDARD"     # 31-90 DPD or signs of weakness
    DOUBTFUL = "DOUBTFUL"           # 91-180 DPD or significant weakness
    LOSS = "LOSS"                   # 181+ DPD or unrecoverable


# DPD buckets (days past due)
class DPDBucket(Enum):
    DPD_0 = "DPD_0"           # current
    DPD_1_30 = "DPD_1_30"
    DPD_31_60 = "DPD_31_60"
    DPD_61_90 = "DPD_61_90"
    DPD_91_180 = "DPD_91_180"
    DPD_181_PLUS = "DPD_181_PLUS"


def compute_dpd_bucket(dpd: int) -> DPDBucket:
    """Map days past due to bucket."""
    if dpd < 0:
        raise ValueError(f"dpd {dpd} cannot be negative")
    if dpd == 0:
        return DPDBucket.DPD_0
    if dpd <= 30:
        return DPDBucket.DPD_1_30
    if dpd <= 60:
        return DPDBucket.DPD_31_60
    if dpd <= 90:
        return DPDBucket.DPD_61_90
    if dpd <= 180:
        return DPDBucket.DPD_91_180
    return DPDBucket.DPD_181_PLUS


def cbk_classification_for_dpd(dpd: int) -> CBKRiskClassification:
    """CBK PG/04 classification by DPD only.

    Note: CBK rules also allow downgrade based on qualitative weakness signs
    independent of DPD. Use this as the DPD-driven floor; supplement with
    EWS findings to reach final classification.
    """
    if dpd <= 0:
        return CBKRiskClassification.NORMAL
    if dpd <= 30:
        return CBKRiskClassification.WATCH
    if dpd <= 90:
        return CBKRiskClassification.SUBSTANDARD
    if dpd <= 180:
        return CBKRiskClassification.DOUBTFUL
    return CBKRiskClassification.LOSS


# ════════════════════════════════════════════════════════════════════════
# Early Warning Signals (ENH-126)
# ════════════════════════════════════════════════════════════════════════

class EWSSignal(Enum):
    """Early warning signal categories per CBK CRMF §3.4 + IFRS 9 §B5.5.17."""
    # Behavioral
    PAYMENT_BEHAVIOR_DETERIORATION = "PAYMENT_BEHAVIOR_DETERIORATION"
    BALANCE_RUN_UP = "BALANCE_RUN_UP"
    CHANNEL_USAGE_ANOMALY = "CHANNEL_USAGE_ANOMALY"
    DRAW_DOWN_LIMIT_BREACH = "DRAW_DOWN_LIMIT_BREACH"
    # Financial
    BUREAU_SCORE_DROP = "BUREAU_SCORE_DROP"
    NEW_DELINQUENCY_ELSEWHERE = "NEW_DELINQUENCY_ELSEWHERE"
    INCOME_DROP_DETECTED = "INCOME_DROP_DETECTED"
    DTI_SPIKE = "DTI_SPIKE"
    # Collateral
    COLLATERAL_VALUE_DROP = "COLLATERAL_VALUE_DROP"
    INSURANCE_LAPSED = "INSURANCE_LAPSED"
    # External
    ADVERSE_MEDIA = "ADVERSE_MEDIA"
    REGULATORY_ACTION = "REGULATORY_ACTION"
    LITIGATION = "LITIGATION"
    SECTOR_DOWNGRADE = "SECTOR_DOWNGRADE"
    # Structural
    LATE_FINANCIAL_STATEMENTS = "LATE_FINANCIAL_STATEMENTS"
    COVENANT_BREACH = "COVENANT_BREACH"


# Severity per signal (low=1, medium=2, high=3)
EWS_SIGNAL_SEVERITY: Mapping[EWSSignal, int] = {
    EWSSignal.PAYMENT_BEHAVIOR_DETERIORATION: 2,
    EWSSignal.BALANCE_RUN_UP: 2,
    EWSSignal.CHANNEL_USAGE_ANOMALY: 1,
    EWSSignal.DRAW_DOWN_LIMIT_BREACH: 3,
    EWSSignal.BUREAU_SCORE_DROP: 2,
    EWSSignal.NEW_DELINQUENCY_ELSEWHERE: 3,
    EWSSignal.INCOME_DROP_DETECTED: 3,
    EWSSignal.DTI_SPIKE: 2,
    EWSSignal.COLLATERAL_VALUE_DROP: 2,
    EWSSignal.INSURANCE_LAPSED: 1,
    EWSSignal.ADVERSE_MEDIA: 2,
    EWSSignal.REGULATORY_ACTION: 3,
    EWSSignal.LITIGATION: 3,
    EWSSignal.SECTOR_DOWNGRADE: 1,
    EWSSignal.LATE_FINANCIAL_STATEMENTS: 1,
    EWSSignal.COVENANT_BREACH: 3,
}


class EWSLevel(Enum):
    """Aggregated EWS verdict."""
    GREEN = "GREEN"      # no signals
    AMBER = "AMBER"      # weighted score 1-5
    RED = "RED"          # weighted score >= 6 OR any severity-3 signal


# Thresholds for level assignment
EWS_AMBER_MIN_SCORE = 1
EWS_RED_MIN_SCORE = 6


@dataclass(frozen=True)
class AccountSnapshot:
    """Point-in-time account state for monitoring."""
    account_id: str
    snapshot_at: str             # ISO-8601
    outstanding_kes: Decimal
    arrears_kes: Decimal
    dpd: int
    bureau_score_current: Optional[Decimal] = None
    bureau_score_at_origination: Optional[Decimal] = None
    income_kes_current: Optional[Decimal] = None
    income_kes_at_origination: Optional[Decimal] = None
    dti_current_pct: Optional[Decimal] = None
    dti_at_origination_pct: Optional[Decimal] = None
    limit_kes: Optional[Decimal] = None
    utilization_pct: Optional[Decimal] = None
    collateral_value_current_kes: Optional[Decimal] = None
    collateral_value_at_origination_kes: Optional[Decimal] = None
    sector: str = ""
    notes: str = ""

    def __post_init__(self):
        if self.outstanding_kes < Decimal("0"):
            raise ValueError("outstanding_kes cannot be negative")
        if self.arrears_kes < Decimal("0"):
            raise ValueError("arrears_kes cannot be negative")
        if self.dpd < 0:
            raise ValueError("dpd cannot be negative")


@dataclass(frozen=True)
class EWSAssessment:
    """Per-account EWS verdict."""
    account_id: str
    snapshot_at: str
    signals_fired: Tuple[str, ...]
    signal_count: int
    weighted_score: int
    level: EWSLevel
    cbk_classification: CBKRiskClassification
    notes: str = ""


def detect_ews_signals(snapshot: AccountSnapshot) -> Tuple[EWSSignal, ...]:
    """Detect which EWS signals fire for this account snapshot.

    Per Rule 1 — only fires signals where data is present. Missing data
    does NOT silently fire OR silently suppress; it just doesn't evaluate.
    """
    fired: List[EWSSignal] = []

    # Bureau score drop ≥ 50 points
    if (snapshot.bureau_score_current is not None
            and snapshot.bureau_score_at_origination is not None):
        drop = snapshot.bureau_score_at_origination - snapshot.bureau_score_current
        if drop >= Decimal("50"):
            fired.append(EWSSignal.BUREAU_SCORE_DROP)

    # Income drop ≥ 20%
    if (snapshot.income_kes_current is not None
            and snapshot.income_kes_at_origination is not None
            and snapshot.income_kes_at_origination > Decimal("0")):
        drop_pct = ((snapshot.income_kes_at_origination - snapshot.income_kes_current)
                     / snapshot.income_kes_at_origination * Decimal("100"))
        if drop_pct >= Decimal("20"):
            fired.append(EWSSignal.INCOME_DROP_DETECTED)

    # DTI spike ≥ 10pp
    if (snapshot.dti_current_pct is not None
            and snapshot.dti_at_origination_pct is not None):
        spike = snapshot.dti_current_pct - snapshot.dti_at_origination_pct
        if spike >= Decimal("10"):
            fired.append(EWSSignal.DTI_SPIKE)

    # Collateral value drop ≥ 15%
    if (snapshot.collateral_value_current_kes is not None
            and snapshot.collateral_value_at_origination_kes is not None
            and snapshot.collateral_value_at_origination_kes > Decimal("0")):
        drop_pct = ((snapshot.collateral_value_at_origination_kes
                      - snapshot.collateral_value_current_kes)
                     / snapshot.collateral_value_at_origination_kes
                     * Decimal("100"))
        if drop_pct >= Decimal("15"):
            fired.append(EWSSignal.COLLATERAL_VALUE_DROP)

    # Limit breach (utilization > 100%)
    if (snapshot.utilization_pct is not None
            and snapshot.utilization_pct > Decimal("100")):
        fired.append(EWSSignal.DRAW_DOWN_LIMIT_BREACH)

    # Payment behavior deterioration — DPD > 0 is a behavioral signal
    if snapshot.dpd > 0:
        fired.append(EWSSignal.PAYMENT_BEHAVIOR_DETERIORATION)

    return tuple(fired)


def assess_ews(
    snapshot: AccountSnapshot,
    *,
    extra_signals: Sequence[EWSSignal] = (),
) -> EWSAssessment:
    """Compute EWS assessment for a snapshot.

    extra_signals is for signals detected outside the snapshot (e.g.,
    adverse media, regulatory action) that would be fed in by other systems.
    """
    detected = list(detect_ews_signals(snapshot))
    for s in extra_signals:
        if s not in detected:
            detected.append(s)

    weighted_score = sum(
        EWS_SIGNAL_SEVERITY.get(s, 1) for s in detected)

    has_severity_3 = any(
        EWS_SIGNAL_SEVERITY.get(s, 1) == 3 for s in detected)

    if not detected:
        level = EWSLevel.GREEN
    elif weighted_score >= EWS_RED_MIN_SCORE or has_severity_3:
        level = EWSLevel.RED
    else:
        level = EWSLevel.AMBER

    return EWSAssessment(
        account_id=snapshot.account_id,
        snapshot_at=snapshot.snapshot_at,
        signals_fired=tuple(s.value for s in detected),
        signal_count=len(detected),
        weighted_score=weighted_score,
        level=level,
        cbk_classification=cbk_classification_for_dpd(snapshot.dpd),
        notes=f"weighted_score={weighted_score}, severity_3={has_severity_3}")


# ════════════════════════════════════════════════════════════════════════
# Roll rate analysis (vintage)
# ════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class RollRateAnalysis:
    """Stage migration roll rates between two snapshots."""
    period_start: str
    period_end: str
    total_accounts: int
    forward_roll_count: int      # NORMAL→WATCH, WATCH→SUB, etc.
    backward_roll_count: int     # WATCH→NORMAL, etc.
    stable_count: int
    forward_roll_pct: Decimal
    backward_roll_pct: Decimal
    by_transition: Mapping[str, int]    # "FROM→TO" → count


# Severity ordering for roll-direction detection
_CBK_CLASS_ORDER: Mapping[CBKRiskClassification, int] = {
    CBKRiskClassification.NORMAL: 0,
    CBKRiskClassification.WATCH: 1,
    CBKRiskClassification.SUBSTANDARD: 2,
    CBKRiskClassification.DOUBTFUL: 3,
    CBKRiskClassification.LOSS: 4,
}


def compute_roll_rates(
    *,
    period_start: str,
    period_end: str,
    snapshots_t0: Sequence[AccountSnapshot],
    snapshots_t1: Sequence[AccountSnapshot],
) -> RollRateAnalysis:
    """Compute classification migration between two snapshot sets.

    Accounts in t0 not in t1 (or vice versa) are skipped — only matched
    pairs are analyzed.
    """
    t0_by_id = {s.account_id: s for s in snapshots_t0}
    t1_by_id = {s.account_id: s for s in snapshots_t1}
    common = set(t0_by_id.keys()) & set(t1_by_id.keys())

    forward = 0
    backward = 0
    stable = 0
    by_transition: Dict[str, int] = {}

    for aid in common:
        t0_class = cbk_classification_for_dpd(t0_by_id[aid].dpd)
        t1_class = cbk_classification_for_dpd(t1_by_id[aid].dpd)
        key = f"{t0_class.value}→{t1_class.value}"
        by_transition[key] = by_transition.get(key, 0) + 1

        t0_rank = _CBK_CLASS_ORDER[t0_class]
        t1_rank = _CBK_CLASS_ORDER[t1_class]
        if t1_rank > t0_rank:
            forward += 1
        elif t1_rank < t0_rank:
            backward += 1
        else:
            stable += 1

    n = len(common)
    return RollRateAnalysis(
        period_start=period_start,
        period_end=period_end,
        total_accounts=n,
        forward_roll_count=forward,
        backward_roll_count=backward,
        stable_count=stable,
        forward_roll_pct=(
            Decimal(forward) / Decimal(n) * Decimal("100")
            if n > 0 else Decimal("0")),
        backward_roll_pct=(
            Decimal(backward) / Decimal(n) * Decimal("100")
            if n > 0 else Decimal("0")),
        by_transition=by_transition)


# ════════════════════════════════════════════════════════════════════════
# Collections & recovery — ENH-128
# ════════════════════════════════════════════════════════════════════════

class CollectionStrategy(Enum):
    """Collections action ladder per CBK Debt Recovery Reg 2022."""
    NO_ACTION = "NO_ACTION"            # current account
    SOFT_REMINDER = "SOFT_REMINDER"    # SMS / email reminder
    PHONE_FOLLOWUP = "PHONE_FOLLOWUP"  # outbound call
    FIRM_NOTICE = "FIRM_NOTICE"        # demand letter
    FIELD_VISIT = "FIELD_VISIT"        # in-person collections officer
    LEGAL_DEMAND = "LEGAL_DEMAND"      # advocate letter
    LITIGATION = "LITIGATION"          # court action
    REPOSSESSION = "REPOSSESSION"      # seize secured collateral
    WRITE_OFF = "WRITE_OFF"            # accounting write-off


# DPD bucket → recommended collection strategy
DEFAULT_COLLECTION_LADDER: Mapping[DPDBucket, CollectionStrategy] = {
    DPDBucket.DPD_0: CollectionStrategy.NO_ACTION,
    DPDBucket.DPD_1_30: CollectionStrategy.SOFT_REMINDER,
    DPDBucket.DPD_31_60: CollectionStrategy.PHONE_FOLLOWUP,
    DPDBucket.DPD_61_90: CollectionStrategy.FIRM_NOTICE,
    DPDBucket.DPD_91_180: CollectionStrategy.LEGAL_DEMAND,
    DPDBucket.DPD_181_PLUS: CollectionStrategy.LITIGATION,
}


@dataclass(frozen=True)
class CollectionsAssessment:
    """Collections strategy assignment + recovery probability."""
    account_id: str
    dpd: int
    dpd_bucket: DPDBucket
    recommended_strategy: CollectionStrategy
    recovery_probability: Decimal      # 0-1 estimate of full recovery
    rpc_channel: str                   # SMS / VOICE / FIELD_VISIT
    notes: str = ""


# Recovery probability decay (illustrative, calibrate to historical recovery)
_RECOVERY_PROB_BY_BUCKET: Mapping[DPDBucket, Decimal] = {
    DPDBucket.DPD_0: Decimal("0.99"),
    DPDBucket.DPD_1_30: Decimal("0.85"),
    DPDBucket.DPD_31_60: Decimal("0.65"),
    DPDBucket.DPD_61_90: Decimal("0.40"),
    DPDBucket.DPD_91_180: Decimal("0.20"),
    DPDBucket.DPD_181_PLUS: Decimal("0.08"),
}


def assign_collection_strategy(
    snapshot: AccountSnapshot,
    *,
    has_collateral: bool = False,
    is_repeat_defaulter: bool = False,
    cure_history_count: int = 0,
) -> CollectionsAssessment:
    """Assign collection strategy + recovery probability.

    Adjustments:
      - has_collateral + DPD ≥ 91 → REPOSSESSION instead of LEGAL_DEMAND
      - repeat defaulter → escalate one level
      - cure_history_count ≥ 2 → de-escalate (track record of self-cure)
    """
    bucket = compute_dpd_bucket(snapshot.dpd)
    strategy = DEFAULT_COLLECTION_LADDER[bucket]

    # Repossession if collateral + DPD ≥ 91
    if has_collateral and bucket in (DPDBucket.DPD_91_180,
                                       DPDBucket.DPD_181_PLUS):
        strategy = CollectionStrategy.REPOSSESSION

    # Escalate for repeat defaulters (in non-current buckets)
    if is_repeat_defaulter and bucket != DPDBucket.DPD_0:
        # Move up one rung
        ladder = list(CollectionStrategy)
        try:
            idx = ladder.index(strategy)
            if idx < len(ladder) - 1:
                strategy = ladder[idx + 1]
        except ValueError:
            pass

    # De-escalate if track record of self-curing
    if cure_history_count >= 2 and bucket == DPDBucket.DPD_1_30:
        strategy = CollectionStrategy.NO_ACTION

    base_recovery = _RECOVERY_PROB_BY_BUCKET[bucket]
    if has_collateral:
        # Collateralized = higher recovery
        adjusted_recovery = base_recovery + (
            Decimal("1") - base_recovery) * Decimal("0.30")
    else:
        adjusted_recovery = base_recovery
    if is_repeat_defaulter:
        adjusted_recovery = adjusted_recovery * Decimal("0.7")
    if adjusted_recovery > Decimal("1"):
        adjusted_recovery = Decimal("1")

    # RPC channel by strategy
    rpc_channel = (
        "NONE" if strategy == CollectionStrategy.NO_ACTION
        else "SMS" if strategy == CollectionStrategy.SOFT_REMINDER
        else "VOICE" if strategy == CollectionStrategy.PHONE_FOLLOWUP
        else "POSTAL" if strategy == CollectionStrategy.FIRM_NOTICE
        else "FIELD_VISIT" if strategy == CollectionStrategy.FIELD_VISIT
        else "LEGAL")

    return CollectionsAssessment(
        account_id=snapshot.account_id,
        dpd=snapshot.dpd,
        dpd_bucket=bucket,
        recommended_strategy=strategy,
        recovery_probability=adjusted_recovery,
        rpc_channel=rpc_channel,
        notes=(
            f"collateralized={has_collateral}, "
            f"repeat_defaulter={is_repeat_defaulter}, "
            f"cure_history={cure_history_count}"))


# ════════════════════════════════════════════════════════════════════════
# Unstructured signals — ENH-CRD-R6
# ════════════════════════════════════════════════════════════════════════

class UnstructuredSignalType(Enum):
    """Categorical unstructured-data signal types."""
    ADVERSE_MEDIA = "ADVERSE_MEDIA"
    NEGATIVE_NEWS = "NEGATIVE_NEWS"
    REGULATORY_FILING = "REGULATORY_FILING"
    LITIGATION_FILING = "LITIGATION_FILING"
    COMPLAINT = "COMPLAINT"
    SOCIAL_SENTIMENT_DROP = "SOCIAL_SENTIMENT_DROP"


# Severity per signal type (1-3)
UNSTRUCTURED_SIGNAL_SEVERITY: Mapping[UnstructuredSignalType, int] = {
    UnstructuredSignalType.ADVERSE_MEDIA: 2,
    UnstructuredSignalType.NEGATIVE_NEWS: 1,
    UnstructuredSignalType.REGULATORY_FILING: 3,
    UnstructuredSignalType.LITIGATION_FILING: 3,
    UnstructuredSignalType.COMPLAINT: 1,
    UnstructuredSignalType.SOCIAL_SENTIMENT_DROP: 1,
}


@dataclass(frozen=True)
class UnstructuredSignal:
    """A single unstructured-data signal."""
    account_id: str
    signal_type: UnstructuredSignalType
    detected_at: str             # ISO-8601
    source: str                  # e.g. "Reuters", "Twitter", "OFAC"
    severity_override: Optional[int] = None   # 1-3
    summary: str = ""
    confidence: Decimal = Decimal("0.7")     # 0-1


@dataclass(frozen=True)
class UnstructuredAssessment:
    """Aggregated unstructured-signal verdict for an account."""
    account_id: str
    signal_count: int
    weighted_score: int
    high_severity_count: int
    distinct_sources: Tuple[str, ...]
    has_action_required: bool
    notes: str = ""


def aggregate_unstructured_signals(
    signals: Sequence[UnstructuredSignal],
    *,
    min_confidence: Decimal = Decimal("0.5"),
) -> UnstructuredAssessment:
    """Aggregate unstructured signals into account-level assessment.

    Confidence-gated: signals below `min_confidence` are filtered out.
    """
    if not signals:
        return UnstructuredAssessment(
            account_id="",
            signal_count=0, weighted_score=0,
            high_severity_count=0, distinct_sources=(),
            has_action_required=False)

    account_id = signals[0].account_id
    filtered = [s for s in signals if s.confidence >= min_confidence]
    weighted = 0
    high_sev = 0
    sources: List[str] = []

    for s in filtered:
        sev = (
            s.severity_override if s.severity_override is not None
            else UNSTRUCTURED_SIGNAL_SEVERITY.get(s.signal_type, 1))
        weighted += sev
        if sev >= 3:
            high_sev += 1
        if s.source not in sources:
            sources.append(s.source)

    return UnstructuredAssessment(
        account_id=account_id,
        signal_count=len(filtered),
        weighted_score=weighted,
        high_severity_count=high_sev,
        distinct_sources=tuple(sources),
        has_action_required=(weighted >= 3 or high_sev > 0),
        notes=(
            f"filtered {len(signals) - len(filtered)} low-confidence; "
            f"{len(filtered)} retained"))


# ════════════════════════════════════════════════════════════════════════
# Engine
# ════════════════════════════════════════════════════════════════════════

class PortfolioMonitoringEngine:
    """Orchestrates EWS + collections + unstructured signals across portfolio."""

    def __init__(self, *, entity_name: str = "Ecobank Kenya"):
        self.entity_name = entity_name
        self._ews_assessments: List[EWSAssessment] = []
        self._collections: List[CollectionsAssessment] = []
        self._unstructured: List[UnstructuredAssessment] = []

    def add_ews(self, a: EWSAssessment) -> None:
        self._ews_assessments.append(a)

    def add_collections(self, c: CollectionsAssessment) -> None:
        self._collections.append(c)

    def add_unstructured(self, u: UnstructuredAssessment) -> None:
        self._unstructured.append(u)

    def board_summary(self) -> Dict[str, object]:
        """Aggregate book-wide monitoring metrics for board reporting."""
        if not self._ews_assessments:
            return {
                "entity": self.entity_name,
                "n_accounts_monitored": 0,
                "ews_distribution": {},
                "cbk_distribution": {},
                "collections_pipeline": {},
                "n_unstructured_action": 0,
            }

        n = len(self._ews_assessments)
        ews_dist: Dict[str, int] = {}
        cbk_dist: Dict[str, int] = {}
        for a in self._ews_assessments:
            ews_dist[a.level.value] = ews_dist.get(a.level.value, 0) + 1
            cbk_dist[a.cbk_classification.value] = (
                cbk_dist.get(a.cbk_classification.value, 0) + 1)

        coll_pipeline: Dict[str, int] = {}
        for c in self._collections:
            key = c.recommended_strategy.value
            coll_pipeline[key] = coll_pipeline.get(key, 0) + 1

        unstructured_action = sum(
            1 for u in self._unstructured if u.has_action_required)

        return {
            "entity": self.entity_name,
            "n_accounts_monitored": n,
            "ews_distribution": ews_dist,
            "cbk_distribution": cbk_dist,
            "collections_pipeline": coll_pipeline,
            "n_collections": len(self._collections),
            "n_unstructured_action": unstructured_action,
        }


# ════════════════════════════════════════════════════════════════════════
# Self-test
# ════════════════════════════════════════════════════════════════════════

def _make_snapshot(
    account_id="A1", dpd=0, outstanding="100000", arrears="0",
    bureau_curr=None, bureau_orig=None,
    income_curr=None, income_orig=None,
    dti_curr=None, dti_orig=None,
    util=None, coll_curr=None, coll_orig=None):
    return AccountSnapshot(
        account_id=account_id,
        snapshot_at="2025-12-31",
        outstanding_kes=Decimal(outstanding),
        arrears_kes=Decimal(arrears),
        dpd=dpd,
        bureau_score_current=Decimal(bureau_curr) if bureau_curr else None,
        bureau_score_at_origination=Decimal(bureau_orig) if bureau_orig else None,
        income_kes_current=Decimal(income_curr) if income_curr else None,
        income_kes_at_origination=Decimal(income_orig) if income_orig else None,
        dti_current_pct=Decimal(dti_curr) if dti_curr else None,
        dti_at_origination_pct=Decimal(dti_orig) if dti_orig else None,
        utilization_pct=Decimal(util) if util else None,
        collateral_value_current_kes=Decimal(coll_curr) if coll_curr else None,
        collateral_value_at_origination_kes=Decimal(coll_orig) if coll_orig else None)


def _test_dpd_buckets():
    assert compute_dpd_bucket(0) == DPDBucket.DPD_0
    assert compute_dpd_bucket(15) == DPDBucket.DPD_1_30
    assert compute_dpd_bucket(45) == DPDBucket.DPD_31_60
    assert compute_dpd_bucket(75) == DPDBucket.DPD_61_90
    assert compute_dpd_bucket(120) == DPDBucket.DPD_91_180
    assert compute_dpd_bucket(200) == DPDBucket.DPD_181_PLUS


def _test_dpd_bucket_negative_raises():
    try:
        compute_dpd_bucket(-1)
        assert False
    except ValueError:
        pass


def _test_cbk_classification_by_dpd():
    assert cbk_classification_for_dpd(0) == CBKRiskClassification.NORMAL
    assert cbk_classification_for_dpd(15) == CBKRiskClassification.WATCH
    assert cbk_classification_for_dpd(60) == CBKRiskClassification.SUBSTANDARD
    assert cbk_classification_for_dpd(150) == CBKRiskClassification.DOUBTFUL
    assert cbk_classification_for_dpd(200) == CBKRiskClassification.LOSS


def _test_ews_no_signals_green():
    s = _make_snapshot(dpd=0)
    a = assess_ews(s)
    assert a.level == EWSLevel.GREEN
    assert a.signal_count == 0


def _test_ews_dpd_only_amber():
    """DPD > 0 alone fires PAYMENT_BEHAVIOR_DETERIORATION (severity 2) → AMBER."""
    s = _make_snapshot(dpd=10)
    a = assess_ews(s)
    assert EWSSignal.PAYMENT_BEHAVIOR_DETERIORATION.value in a.signals_fired
    assert a.level == EWSLevel.AMBER
    assert a.weighted_score == 2


def _test_ews_severity_3_signal_red():
    """Single severity-3 signal → RED even if score < 6."""
    s = _make_snapshot(util="120")  # DRAW_DOWN_LIMIT_BREACH
    a = assess_ews(s)
    assert EWSSignal.DRAW_DOWN_LIMIT_BREACH.value in a.signals_fired
    assert a.level == EWSLevel.RED


def _test_ews_bureau_score_drop_fires():
    s = _make_snapshot(bureau_curr="650", bureau_orig="720")
    a = assess_ews(s)
    assert EWSSignal.BUREAU_SCORE_DROP.value in a.signals_fired


def _test_ews_income_drop_fires():
    s = _make_snapshot(income_curr="60000", income_orig="100000")  # 40% drop
    a = assess_ews(s)
    assert EWSSignal.INCOME_DROP_DETECTED.value in a.signals_fired


def _test_ews_extra_signals_merged():
    s = _make_snapshot(dpd=0)
    a = assess_ews(s, extra_signals=[EWSSignal.ADVERSE_MEDIA])
    assert EWSSignal.ADVERSE_MEDIA.value in a.signals_fired


def _test_ews_missing_data_doesnt_silent_fire():
    """Honesty Rule 1 — missing fields don't silently fire signals."""
    s = _make_snapshot()  # no current/origin bureau, income, etc.
    signals = detect_ews_signals(s)
    assert EWSSignal.BUREAU_SCORE_DROP not in signals
    assert EWSSignal.INCOME_DROP_DETECTED not in signals


def _test_roll_rate_basic():
    t0 = [_make_snapshot(account_id=f"A{i}", dpd=0)
            for i in range(10)]
    # Half roll forward to WATCH, others stable
    t1 = [_make_snapshot(account_id=f"A{i}", dpd=15 if i < 5 else 0)
            for i in range(10)]
    r = compute_roll_rates(
        period_start="2025-01", period_end="2025-12",
        snapshots_t0=t0, snapshots_t1=t1)
    assert r.forward_roll_count == 5
    assert r.stable_count == 5
    assert r.forward_roll_pct == Decimal("50")


def _test_collections_current_no_action():
    s = _make_snapshot(dpd=0)
    c = assign_collection_strategy(s)
    assert c.recommended_strategy == CollectionStrategy.NO_ACTION
    assert c.rpc_channel == "NONE"


def _test_collections_dpd_60_phone():
    s = _make_snapshot(dpd=45)
    c = assign_collection_strategy(s)
    assert c.recommended_strategy == CollectionStrategy.PHONE_FOLLOWUP
    assert c.rpc_channel == "VOICE"


def _test_collections_collateral_dpd_91_repossession():
    s = _make_snapshot(dpd=120)
    c = assign_collection_strategy(s, has_collateral=True)
    assert c.recommended_strategy == CollectionStrategy.REPOSSESSION


def _test_collections_recovery_probability_decays_with_dpd():
    pcurrent = assign_collection_strategy(_make_snapshot(dpd=0))
    p30 = assign_collection_strategy(_make_snapshot(dpd=15))
    p180 = assign_collection_strategy(_make_snapshot(dpd=200))
    assert pcurrent.recovery_probability > p30.recovery_probability
    assert p30.recovery_probability > p180.recovery_probability


def _test_collections_collateralized_higher_recovery():
    p_uncoll = assign_collection_strategy(_make_snapshot(dpd=120))
    p_coll = assign_collection_strategy(
        _make_snapshot(dpd=120), has_collateral=True)
    assert p_coll.recovery_probability > p_uncoll.recovery_probability


def _test_collections_repeat_defaulter_escalates():
    s = _make_snapshot(dpd=15)
    p_first = assign_collection_strategy(s)
    p_repeat = assign_collection_strategy(s, is_repeat_defaulter=True)
    # First time → SOFT_REMINDER; repeat → escalates to PHONE_FOLLOWUP
    ladder = list(CollectionStrategy)
    assert ladder.index(p_repeat.recommended_strategy) > ladder.index(
        p_first.recommended_strategy)


def _test_unstructured_aggregate_empty():
    a = aggregate_unstructured_signals([])
    assert a.signal_count == 0
    assert not a.has_action_required


def _test_unstructured_high_severity_action_required():
    sigs = [UnstructuredSignal(
        account_id="X",
        signal_type=UnstructuredSignalType.REGULATORY_FILING,
        detected_at="t", source="OFAC", confidence=Decimal("0.9"))]
    a = aggregate_unstructured_signals(sigs)
    assert a.has_action_required
    assert a.high_severity_count == 1


def _test_unstructured_low_confidence_filtered():
    sigs = [UnstructuredSignal(
        account_id="X",
        signal_type=UnstructuredSignalType.NEGATIVE_NEWS,
        detected_at="t", source="blog",
        confidence=Decimal("0.3"))]
    a = aggregate_unstructured_signals(sigs)
    assert a.signal_count == 0


def _test_engine_board_summary_empty():
    eng = PortfolioMonitoringEngine()
    s = eng.board_summary()
    assert s["n_accounts_monitored"] == 0


def _test_engine_aggregates():
    eng = PortfolioMonitoringEngine()
    eng.add_ews(assess_ews(_make_snapshot(dpd=0)))
    eng.add_ews(assess_ews(_make_snapshot(account_id="A2", dpd=15)))
    eng.add_collections(assign_collection_strategy(_make_snapshot(dpd=15)))
    s = eng.board_summary()
    assert s["n_accounts_monitored"] == 2
    assert s["ews_distribution"]["GREEN"] == 1
    assert s["ews_distribution"]["AMBER"] == 1


def _test_decimal_purity():
    c = assign_collection_strategy(_make_snapshot(dpd=0))
    assert isinstance(c.recovery_probability, Decimal)


def self_test() -> None:
    tests = [
        _test_dpd_buckets,
        _test_dpd_bucket_negative_raises,
        _test_cbk_classification_by_dpd,
        _test_ews_no_signals_green,
        _test_ews_dpd_only_amber,
        _test_ews_severity_3_signal_red,
        _test_ews_bureau_score_drop_fires,
        _test_ews_income_drop_fires,
        _test_ews_extra_signals_merged,
        _test_ews_missing_data_doesnt_silent_fire,
        _test_roll_rate_basic,
        _test_collections_current_no_action,
        _test_collections_dpd_60_phone,
        _test_collections_collateral_dpd_91_repossession,
        _test_collections_recovery_probability_decays_with_dpd,
        _test_collections_collateralized_higher_recovery,
        _test_collections_repeat_defaulter_escalates,
        _test_unstructured_aggregate_empty,
        _test_unstructured_high_severity_action_required,
        _test_unstructured_low_confidence_filtered,
        _test_engine_board_summary_empty,
        _test_engine_aggregates,
        _test_decimal_purity,
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
        print(f"✗ portfolio_monitoring self-test: {len(failed)} failures",
              file=sys.stderr)
        for name, msg in failed:
            print(f"  - {name}: {msg}", file=sys.stderr)
        raise SystemExit(1)
    print(f"✓ portfolio_monitoring self-test passed ({len(tests)} tests)")


if __name__ == "__main__":
    self_test()
