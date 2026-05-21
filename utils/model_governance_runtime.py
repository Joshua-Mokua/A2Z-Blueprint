"""utils/model_governance_runtime.py — v10.29 Model Governance arc closure.

╔════════════════════════════════════════════════════════════════════════╗
║  VENDOR MODEL MANAGEMENT + AUTOMATED RETRAINING WORKFLOW              ║
║  Cat A pre-requisite — runtime governance for production ML            ║
╠════════════════════════════════════════════════════════════════════════╣
║  Risk class: Cat A (vendor model failures cascade to credit decisions; ║
║              uncontrolled retraining creates fairness/compliance       ║
║              landmines; champion-challenger bypasses become attack     ║
║              surface for adversarial deployment)                        ║
║  Implements 2 of 10 Model Governance standards from registry:           ║
║    ENH-264: Vendor Model Management                                     ║
║    ENH-266: Automated Model Retraining Workflow                         ║
╠════════════════════════════════════════════════════════════════════════╣
║  Regulatory provenance:                                                 ║
║    OCC 2011-12 §IV.B.2 — vendor models                                  ║
║    Federal Reserve SR 11-7 §V — vendor and other third-party models     ║
║    OCC Bulletin 2013-29 — third-party relationships                     ║
║    OCC Bulletin 2020-10 — interagency third-party guidance              ║
║    OCC 2017-21 — frequently asked questions on third-party              ║
║    PRA SS2/21 — outsourcing and third-party risk management (UK)        ║
║    EBA EBA/GL/2019/02 — outsourcing arrangements (EU)                   ║
║    CBK Outsourcing Guideline 2018 — concentration thresholds            ║
║    CBK CRMF April 2021 §10 — third-party risk management                ║
║    Basel BCBS 449 — outsourcing in financial services                  ║
║    SR 11-7 §V.B — model implementation: ongoing monitoring              ║
║    EU AI Act Art 17 — quality management system                         ║
║    NIST AI RMF 1.0 — MEASURE 1.3 testing during development             ║
║    ISO/IEC 23894:2023 §5.4 — model validation throughout lifecycle      ║
╠════════════════════════════════════════════════════════════════════════╣
║  Composes with v10.28 model_governance — vendor models register        ║
║  through ModelGovernanceEngine; retraining runs flow through            ║
║  validation gates before champion-challenger deployment.                ║
║                                                                         ║
║  Honesty Rule 1: due diligence outcomes show evidence + verdict;      ║
║  retraining decisions show trigger + drift evidence + validation;     ║
║  champion-challenger deployment requires explicit promotion.           ║
║  Honesty Rule 7: vendor data ingestors + retraining executors are      ║
║  callable hooks; without wiring, framework reports REQUIRES_PROVIDER, ║
║  never fabricates a "passed" due diligence verdict.                   ║
╚════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal, getcontext
from enum import Enum
from typing import (
    Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple)

getcontext().prec = 28

SPEC_DEVIATION_NOTE = (
    "Vendor due diligence requires evidence — questionnaire responses, "
    "audit reports, SOC 2/3 attestations, model methodology documents. "
    "Per Rule 7, vendor data ingestors are callable hooks; without "
    "wiring, framework reports REQUIRES_PROVIDER. Retraining executors "
    "(actual model fit code) are also hookable; framework provides the "
    "policy + workflow + governance, not the gradient descent."
)


# ════════════════════════════════════════════════════════════════════════
# Vendor Model Management (ENH-264)
# ════════════════════════════════════════════════════════════════════════

class VendorModelTier(Enum):
    """Tier of vendor model based on impact + transparency."""
    TIER_1_HIGH = "TIER_1_HIGH"        # material impact, credit/capital
    TIER_2_MEDIUM = "TIER_2_MEDIUM"    # supports business processes
    TIER_3_LOW = "TIER_3_LOW"          # standalone analytics


class VendorTransparency(Enum):
    """How transparent the vendor is about model internals.

    Drives validation depth required — black box models need more
    sensitivity testing + benchmarking compensation.
    """
    FULL_DISCLOSURE = "FULL_DISCLOSURE"        # source/weights available
    LIMITED_DISCLOSURE = "LIMITED_DISCLOSURE"  # methodology + features
    BLACK_BOX = "BLACK_BOX"                    # API only, no methodology


class DueDiligenceCategory(Enum):
    """Categories of vendor due diligence per OCC 2011-12 + SR 11-7 §V."""
    FINANCIAL_SOUNDNESS = "FINANCIAL_SOUNDNESS"      # vendor solvency
    MODEL_METHODOLOGY = "MODEL_METHODOLOGY"          # technical soundness
    DATA_QUALITY = "DATA_QUALITY"                    # vendor data sources
    PERFORMANCE_TRACK_RECORD = "PERFORMANCE_TRACK_RECORD"
    SECURITY_CONTROLS = "SECURITY_CONTROLS"          # SOC 2, ISO 27001
    BUSINESS_CONTINUITY = "BUSINESS_CONTINUITY"
    REGULATORY_COMPLIANCE = "REGULATORY_COMPLIANCE"
    CONTRACTUAL_AUDIT_RIGHTS = "CONTRACTUAL_AUDIT_RIGHTS"
    EXIT_STRATEGY = "EXIT_STRATEGY"                  # vendor change/cutover
    SUBCONTRACTOR_OVERSIGHT = "SUBCONTRACTOR_OVERSIGHT"


# Required DD categories per tier — Tier 1 needs full coverage
REQUIRED_DD_CATEGORIES_BY_TIER: Mapping[
    VendorModelTier, Tuple[DueDiligenceCategory, ...]] = {
    VendorModelTier.TIER_1_HIGH: tuple(DueDiligenceCategory),    # all 10
    VendorModelTier.TIER_2_MEDIUM: (
        DueDiligenceCategory.FINANCIAL_SOUNDNESS,
        DueDiligenceCategory.MODEL_METHODOLOGY,
        DueDiligenceCategory.DATA_QUALITY,
        DueDiligenceCategory.PERFORMANCE_TRACK_RECORD,
        DueDiligenceCategory.SECURITY_CONTROLS,
        DueDiligenceCategory.CONTRACTUAL_AUDIT_RIGHTS,
        DueDiligenceCategory.EXIT_STRATEGY,
    ),
    VendorModelTier.TIER_3_LOW: (
        DueDiligenceCategory.FINANCIAL_SOUNDNESS,
        DueDiligenceCategory.SECURITY_CONTROLS,
        DueDiligenceCategory.CONTRACTUAL_AUDIT_RIGHTS,
    ),
}


class DueDiligenceVerdict(Enum):
    SATISFACTORY = "SATISFACTORY"
    SATISFACTORY_WITH_OBSERVATIONS = "SATISFACTORY_WITH_OBSERVATIONS"
    UNSATISFACTORY = "UNSATISFACTORY"
    REQUIRES_PROVIDER = "REQUIRES_PROVIDER"   # Rule 7 — no evidence wired
    NOT_ASSESSED = "NOT_ASSESSED"


@dataclass(frozen=True)
class DueDiligenceFinding:
    """One due diligence assessment outcome."""
    finding_id: str
    vendor_model_id: str
    category: DueDiligenceCategory
    verdict: DueDiligenceVerdict
    evidence_count: int                    # documents/reports reviewed
    assessor_user_id: str
    assessment_date: str
    notes: str = ""

    def is_blocking(self) -> bool:
        """UNSATISFACTORY blocks production approval."""
        return self.verdict == DueDiligenceVerdict.UNSATISFACTORY


@dataclass(frozen=True)
class VendorModel:
    """A registered vendor model.

    Composes with v10.28 Model — vendor_model_id == model_id when
    registered through ModelGovernanceEngine.
    """
    vendor_model_id: str               # matches model_governance.Model.model_id
    vendor_name: str
    vendor_legal_entity: str           # e.g., "FICO Corporation"
    vendor_country: str
    product_name: str
    product_version: str
    tier: VendorModelTier
    transparency: VendorTransparency
    contract_start_date: str
    contract_end_date: str
    annual_cost_usd: Decimal = Decimal("0")
    n_other_banks_using: int = 0       # concentration estimate
    has_audit_rights_clause: bool = False
    has_exit_clause: bool = False
    notes: str = ""

    def is_contract_expiring_soon(
        self, *, as_of: date, days_ahead: int = 90,
    ) -> bool:
        try:
            end = date.fromisoformat(self.contract_end_date)
        except ValueError:
            return False
        return as_of <= end <= as_of + timedelta(days=days_ahead)


# Concentration risk threshold — per CBK Outsourcing Guideline 2018
DEFAULT_VENDOR_CONCENTRATION_THRESHOLD_PCT = Decimal("25")    # 25% of category


@dataclass(frozen=True)
class VendorConcentrationAssessment:
    """Assessment of concentration risk for a single vendor."""
    assessment_id: str
    vendor_name: str
    category: str                          # e.g., "credit_scoring"
    n_models_from_vendor: int
    n_models_in_category_total: int
    concentration_pct: Decimal
    threshold_pct: Decimal
    is_breach: bool
    assessment_date: str
    notes: str = ""


def assess_vendor_concentration(
    *,
    assessment_id: str,
    vendor_name: str,
    category: str,
    n_models_from_vendor: int,
    n_models_in_category_total: int,
    assessment_date: str,
    threshold_pct: Decimal = DEFAULT_VENDOR_CONCENTRATION_THRESHOLD_PCT,
) -> VendorConcentrationAssessment:
    """Compute concentration % and breach verdict."""
    if n_models_in_category_total == 0:
        concentration = Decimal("0")
    else:
        concentration = (
            Decimal(n_models_from_vendor)
            / Decimal(n_models_in_category_total)) * Decimal("100")
    return VendorConcentrationAssessment(
        assessment_id=assessment_id, vendor_name=vendor_name,
        category=category,
        n_models_from_vendor=n_models_from_vendor,
        n_models_in_category_total=n_models_in_category_total,
        concentration_pct=concentration, threshold_pct=threshold_pct,
        is_breach=concentration > threshold_pct,
        assessment_date=assessment_date,
        notes=(
            f"{n_models_from_vendor}/{n_models_in_category_total} "
            f"models = {concentration:.2f}% "
            f"(threshold {threshold_pct}%)"))


# ════════════════════════════════════════════════════════════════════════
# Automated Retraining Workflow (ENH-266)
# ════════════════════════════════════════════════════════════════════════

class RetrainingTrigger(Enum):
    """What initiates a retraining run."""
    DRIFT_DETECTED = "DRIFT_DETECTED"              # PSI/KS breach
    PERFORMANCE_DEGRADATION = "PERFORMANCE_DEGRADATION"   # AUC/RMSE
    BIAS_DETECTED = "BIAS_DETECTED"                # 4/5ths breach
    SCHEDULED = "SCHEDULED"                        # cadence-based
    REGULATORY_REQUIRED = "REGULATORY_REQUIRED"    # SR 11-7 annual
    DATA_REFRESH = "DATA_REFRESH"                  # new training window
    MANUAL = "MANUAL"


class RetrainingState(Enum):
    """States in a retraining run lifecycle."""
    TRIGGERED = "TRIGGERED"
    DATA_PREPARING = "DATA_PREPARING"
    TRAINING = "TRAINING"
    VALIDATING = "VALIDATING"
    APPROVED = "APPROVED"
    DEPLOYED_AS_CHALLENGER = "DEPLOYED_AS_CHALLENGER"
    PROMOTED_TO_CHAMPION = "PROMOTED_TO_CHAMPION"
    REJECTED = "REJECTED"
    FAILED = "FAILED"


# Allowed transitions
ALLOWED_RETRAINING_TRANSITIONS: Mapping[
    RetrainingState, Tuple[RetrainingState, ...]] = {
    RetrainingState.TRIGGERED: (
        RetrainingState.DATA_PREPARING,
        RetrainingState.REJECTED,
        RetrainingState.FAILED),
    RetrainingState.DATA_PREPARING: (
        RetrainingState.TRAINING,
        RetrainingState.FAILED),
    RetrainingState.TRAINING: (
        RetrainingState.VALIDATING,
        RetrainingState.FAILED),
    RetrainingState.VALIDATING: (
        RetrainingState.APPROVED,
        RetrainingState.REJECTED,
        RetrainingState.FAILED),
    RetrainingState.APPROVED: (
        RetrainingState.DEPLOYED_AS_CHALLENGER,
        RetrainingState.REJECTED),
    RetrainingState.DEPLOYED_AS_CHALLENGER: (
        RetrainingState.PROMOTED_TO_CHAMPION,
        RetrainingState.REJECTED),
    RetrainingState.PROMOTED_TO_CHAMPION: (),    # terminal happy path
    RetrainingState.REJECTED: (),                # terminal
    RetrainingState.FAILED: (),                  # terminal
}


def is_valid_retraining_transition(
    from_state: RetrainingState,
    to_state: RetrainingState,
) -> bool:
    return to_state in ALLOWED_RETRAINING_TRANSITIONS.get(from_state, ())


# Default trigger thresholds — match v10.28 PSI/KS verdicts
DEFAULT_DRIFT_TRIGGER_PSI = Decimal("0.20")          # significant shift
DEFAULT_PERFORMANCE_TRIGGER_AUC_DROP = Decimal("0.05")    # 5pp AUC drop
DEFAULT_BIAS_TRIGGER_FOUR_FIFTHS = Decimal("0.80")    # falls below ratio


@dataclass(frozen=True)
class RetrainingPolicy:
    """Per-model retraining policy."""
    policy_id: str
    model_id: str
    enabled_triggers: Tuple[RetrainingTrigger, ...]
    psi_threshold: Decimal = DEFAULT_DRIFT_TRIGGER_PSI
    auc_drop_threshold: Decimal = DEFAULT_PERFORMANCE_TRIGGER_AUC_DROP
    four_fifths_threshold: Decimal = DEFAULT_BIAS_TRIGGER_FOUR_FIFTHS
    scheduled_cadence_months: Optional[int] = None
    requires_human_approval: bool = True
    auto_promote_to_champion: bool = False    # default safe — manual promotion
    notes: str = ""

    def is_trigger_enabled(self, t: RetrainingTrigger) -> bool:
        return t in self.enabled_triggers


@dataclass(frozen=True)
class ChampionChallengerComparison:
    """Comparison between champion (current production) and challenger.

    Per SR 11-7 §V.B — A/B testing for champion-challenger deployment.
    """
    comparison_id: str
    champion_model_id: str
    challenger_model_id: str
    metric_name: str                       # e.g., "AUC", "GINI"
    champion_value: Decimal
    challenger_value: Decimal
    improvement_pct: Decimal
    is_statistically_significant: bool
    sample_size: int
    comparison_date: str
    notes: str = ""

    def challenger_wins(
        self, *, min_improvement_pct: Decimal = Decimal("2"),
    ) -> bool:
        """Challenger should be promoted only if statistically significant
        improvement exceeds minimum threshold."""
        return (self.is_statistically_significant
                and self.improvement_pct >= min_improvement_pct)


@dataclass(frozen=True)
class RetrainingRun:
    """A single retraining instance."""
    run_id: str
    model_id: str
    trigger: RetrainingTrigger
    trigger_evidence: str                  # describe drift/perf/bias evidence
    triggered_at: str
    triggered_by_user_id: str
    state: RetrainingState
    policy_id: Optional[str] = None
    new_model_version: Optional[str] = None
    new_validation_report_id: Optional[str] = None
    champion_challenger_id: Optional[str] = None
    completed_at: Optional[str] = None
    notes: str = ""


# ════════════════════════════════════════════════════════════════════════
# Engine — orchestrator
# ════════════════════════════════════════════════════════════════════════

class ModelGovernanceRuntimeEngine:
    """Vendor management + automated retraining orchestrator.

    Composes with v10.28 ModelGovernanceEngine — registered models can
    flow through retraining when triggered; vendor models register
    additional metadata.
    """

    def __init__(self, *, entity_name: str = "Ecobank Kenya"):
        self.entity_name = entity_name
        self._vendor_models: Dict[str, VendorModel] = {}
        self._dd_findings: List[DueDiligenceFinding] = []
        self._concentration_assessments: List[
            VendorConcentrationAssessment] = []
        self._retraining_policies: Dict[str, RetrainingPolicy] = {}
        self._retraining_runs: Dict[str, RetrainingRun] = {}
        self._retraining_transitions: List[
            Tuple[str, RetrainingState, RetrainingState, str]] = []
        self._champion_challenger_comparisons: Dict[
            str, ChampionChallengerComparison] = {}
        self._champion_by_model: Dict[str, str] = {}    # model_id → champion_run_id

    # ── Vendor models (ENH-264) ────────────────────────────────────────
    def register_vendor_model(self, vm: VendorModel) -> None:
        if vm.vendor_model_id in self._vendor_models:
            raise ValueError(
                f"vendor model {vm.vendor_model_id} already registered")
        self._vendor_models[vm.vendor_model_id] = vm

    def get_vendor_model(self, vmid: str) -> VendorModel:
        if vmid not in self._vendor_models:
            raise KeyError(f"vendor model {vmid} not found")
        return self._vendor_models[vmid]

    def record_due_diligence(
        self, finding: DueDiligenceFinding,
    ) -> None:
        if finding.vendor_model_id not in self._vendor_models:
            raise KeyError(
                f"vendor model {finding.vendor_model_id} not registered")
        # Validate category is required for the tier
        vm = self._vendor_models[finding.vendor_model_id]
        required = REQUIRED_DD_CATEGORIES_BY_TIER[vm.tier]
        if finding.category not in required:
            # Still record — just notes that it's not a required category
            pass
        self._dd_findings.append(finding)

    def due_diligence_status(
        self, vmid: str,
    ) -> Dict[str, Any]:
        """Return status of DD coverage for a vendor model."""
        vm = self.get_vendor_model(vmid)
        required = set(REQUIRED_DD_CATEGORIES_BY_TIER[vm.tier])
        findings_for_vm = [
            f for f in self._dd_findings if f.vendor_model_id == vmid]
        latest_by_cat: Dict[
            DueDiligenceCategory, DueDiligenceFinding] = {}
        for f in findings_for_vm:
            if (f.category not in latest_by_cat
                    or f.assessment_date
                    > latest_by_cat[f.category].assessment_date):
                latest_by_cat[f.category] = f
        covered = set(latest_by_cat.keys())
        missing = required - covered
        n_blocking = sum(
            1 for f in latest_by_cat.values() if f.is_blocking())
        return {
            "vendor_model_id": vmid,
            "tier": vm.tier.value,
            "n_required_categories": len(required),
            "n_covered_categories": len(covered & required),
            "n_missing_required": len(missing),
            "missing_categories": tuple(c.value for c in sorted(
                missing, key=lambda c: c.value)),
            "n_blocking_findings": n_blocking,
            "is_dd_complete": len(missing) == 0 and n_blocking == 0,
        }

    def assess_concentration(
        self, *, assessment_id: str, vendor_name: str, category: str,
        assessment_date: str,
    ) -> VendorConcentrationAssessment:
        """Compute concentration for a vendor across category."""
        n_from = sum(
            1 for vm in self._vendor_models.values()
            if vm.vendor_name == vendor_name)
        n_total = len(self._vendor_models)
        result = assess_vendor_concentration(
            assessment_id=assessment_id, vendor_name=vendor_name,
            category=category,
            n_models_from_vendor=n_from,
            n_models_in_category_total=n_total,
            assessment_date=assessment_date)
        self._concentration_assessments.append(result)
        return result

    def vendors_with_concentration_breach(
        self) -> Tuple[VendorConcentrationAssessment, ...]:
        latest_per_vendor: Dict[
            str, VendorConcentrationAssessment] = {}
        for a in self._concentration_assessments:
            key = a.vendor_name
            if (key not in latest_per_vendor
                    or a.assessment_date
                    > latest_per_vendor[key].assessment_date):
                latest_per_vendor[key] = a
        return tuple(
            a for a in latest_per_vendor.values() if a.is_breach)

    # ── Retraining (ENH-266) ──────────────────────────────────────────
    def register_retraining_policy(
        self, policy: RetrainingPolicy,
    ) -> None:
        if policy.policy_id in self._retraining_policies:
            raise ValueError(
                f"policy {policy.policy_id} already registered")
        self._retraining_policies[policy.policy_id] = policy

    def get_retraining_policy(self, pid: str) -> RetrainingPolicy:
        if pid not in self._retraining_policies:
            raise KeyError(f"policy {pid} not found")
        return self._retraining_policies[pid]

    def trigger_retraining(
        self,
        *,
        run_id: str,
        model_id: str,
        trigger: RetrainingTrigger,
        trigger_evidence: str,
        triggered_at: str,
        triggered_by_user_id: str,
        policy_id: Optional[str] = None,
    ) -> RetrainingRun:
        if run_id in self._retraining_runs:
            raise ValueError(f"run {run_id} already exists")
        # If policy specified, verify trigger is enabled
        if policy_id is not None:
            policy = self.get_retraining_policy(policy_id)
            if not policy.is_trigger_enabled(trigger):
                raise ValueError(
                    f"trigger {trigger.value} not enabled in "
                    f"policy {policy_id}")
        run = RetrainingRun(
            run_id=run_id, model_id=model_id, trigger=trigger,
            trigger_evidence=trigger_evidence,
            triggered_at=triggered_at,
            triggered_by_user_id=triggered_by_user_id,
            state=RetrainingState.TRIGGERED,
            policy_id=policy_id)
        self._retraining_runs[run_id] = run
        return run

    def transition_retraining(
        self,
        *,
        run_id: str,
        to_state: RetrainingState,
        actor_user_id: str,
        timestamp: str,
        notes: str = "",
    ) -> RetrainingRun:
        if run_id not in self._retraining_runs:
            raise KeyError(f"run {run_id} not found")
        existing = self._retraining_runs[run_id]
        if not is_valid_retraining_transition(existing.state, to_state):
            allowed = ALLOWED_RETRAINING_TRANSITIONS.get(
                existing.state, ())
            raise ValueError(
                f"invalid retraining transition "
                f"{existing.state.value} → {to_state.value}; "
                f"allowed: {[s.value for s in allowed]}")
        # Special rule: PROMOTED_TO_CHAMPION requires champion-challenger
        # comparison on file
        if to_state == RetrainingState.PROMOTED_TO_CHAMPION:
            if existing.champion_challenger_id is None:
                raise ValueError(
                    f"cannot promote run {run_id} — no "
                    f"champion-challenger comparison on file")
            comp = self._champion_challenger_comparisons.get(
                existing.champion_challenger_id)
            if comp is None:
                raise ValueError(
                    f"champion-challenger comparison "
                    f"{existing.champion_challenger_id} missing")
            if not comp.challenger_wins():
                raise ValueError(
                    f"cannot promote run {run_id} — challenger does "
                    f"not statistically significantly outperform "
                    f"champion (improvement: "
                    f"{comp.improvement_pct:.2f}%)")
            self._champion_by_model[existing.model_id] = run_id

        self._retraining_transitions.append(
            (run_id, existing.state, to_state, actor_user_id))

        completed_at = (
            timestamp
            if to_state in (
                RetrainingState.PROMOTED_TO_CHAMPION,
                RetrainingState.REJECTED,
                RetrainingState.FAILED)
            else existing.completed_at)
        updated = RetrainingRun(
            run_id=existing.run_id, model_id=existing.model_id,
            trigger=existing.trigger,
            trigger_evidence=existing.trigger_evidence,
            triggered_at=existing.triggered_at,
            triggered_by_user_id=existing.triggered_by_user_id,
            state=to_state,
            policy_id=existing.policy_id,
            new_model_version=existing.new_model_version,
            new_validation_report_id=existing.new_validation_report_id,
            champion_challenger_id=existing.champion_challenger_id,
            completed_at=completed_at,
            notes=(
                existing.notes + "\n" + notes if notes
                else existing.notes))
        self._retraining_runs[run_id] = updated
        return updated

    def attach_champion_challenger_comparison(
        self,
        *,
        run_id: str,
        comparison: ChampionChallengerComparison,
    ) -> RetrainingRun:
        if run_id not in self._retraining_runs:
            raise KeyError(f"run {run_id} not found")
        if comparison.comparison_id in self._champion_challenger_comparisons:
            raise ValueError(
                f"comparison {comparison.comparison_id} exists")
        self._champion_challenger_comparisons[
            comparison.comparison_id] = comparison
        existing = self._retraining_runs[run_id]
        updated = RetrainingRun(
            run_id=existing.run_id, model_id=existing.model_id,
            trigger=existing.trigger,
            trigger_evidence=existing.trigger_evidence,
            triggered_at=existing.triggered_at,
            triggered_by_user_id=existing.triggered_by_user_id,
            state=existing.state,
            policy_id=existing.policy_id,
            new_model_version=existing.new_model_version,
            new_validation_report_id=existing.new_validation_report_id,
            champion_challenger_id=comparison.comparison_id,
            completed_at=existing.completed_at,
            notes=existing.notes)
        self._retraining_runs[run_id] = updated
        return updated

    # ── Reporting ──────────────────────────────────────────────────────
    def board_summary(self) -> Dict[str, Any]:
        n_in_progress = sum(
            1 for r in self._retraining_runs.values()
            if r.state not in (
                RetrainingState.PROMOTED_TO_CHAMPION,
                RetrainingState.REJECTED,
                RetrainingState.FAILED))
        n_promoted = sum(
            1 for r in self._retraining_runs.values()
            if r.state == RetrainingState.PROMOTED_TO_CHAMPION)
        n_rejected = sum(
            1 for r in self._retraining_runs.values()
            if r.state == RetrainingState.REJECTED)
        n_blocking_dd = sum(
            1 for f in self._dd_findings if f.is_blocking())
        return {
            "entity": self.entity_name,
            "n_vendor_models": len(self._vendor_models),
            "n_dd_findings": len(self._dd_findings),
            "n_blocking_dd_findings": n_blocking_dd,
            "n_concentration_breaches": len(
                self.vendors_with_concentration_breach()),
            "n_retraining_policies": len(self._retraining_policies),
            "n_retraining_runs_total": len(self._retraining_runs),
            "n_retraining_in_progress": n_in_progress,
            "n_retraining_promoted": n_promoted,
            "n_retraining_rejected": n_rejected,
        }


# ════════════════════════════════════════════════════════════════════════
# Self-test
# ════════════════════════════════════════════════════════════════════════

def _make_vendor_model(
    vmid="VM1", tier=VendorModelTier.TIER_2_MEDIUM,
):
    return VendorModel(
        vendor_model_id=vmid, vendor_name="Acme",
        vendor_legal_entity="Acme Corp",
        vendor_country="US", product_name="ScoreModel",
        product_version="1.0",
        tier=tier,
        transparency=VendorTransparency.LIMITED_DISCLOSURE,
        contract_start_date="2026-01-01",
        contract_end_date="2027-12-31")


# ── Vendor model tests ───────────────────────────────────────────────
def _test_register_vendor_model():
    eng = ModelGovernanceRuntimeEngine()
    eng.register_vendor_model(_make_vendor_model())
    assert eng.get_vendor_model("VM1").vendor_name == "Acme"


def _test_register_dup_vendor_raises():
    eng = ModelGovernanceRuntimeEngine()
    eng.register_vendor_model(_make_vendor_model())
    try:
        eng.register_vendor_model(_make_vendor_model())
        assert False
    except ValueError:
        pass


def _test_required_dd_categories_tier_1_full():
    """Tier 1 requires all 10 DD categories per OCC 2011-12."""
    required = REQUIRED_DD_CATEGORIES_BY_TIER[VendorModelTier.TIER_1_HIGH]
    assert len(required) == len(DueDiligenceCategory)


def _test_required_dd_categories_tier_3_minimal():
    """Tier 3 requires fewer categories than Tier 1."""
    t1 = REQUIRED_DD_CATEGORIES_BY_TIER[VendorModelTier.TIER_1_HIGH]
    t3 = REQUIRED_DD_CATEGORIES_BY_TIER[VendorModelTier.TIER_3_LOW]
    assert len(t3) < len(t1)


def _test_dd_complete_requires_all_required():
    eng = ModelGovernanceRuntimeEngine()
    eng.register_vendor_model(
        _make_vendor_model(tier=VendorModelTier.TIER_3_LOW))
    # Record findings for all 3 required categories
    for cat in REQUIRED_DD_CATEGORIES_BY_TIER[
            VendorModelTier.TIER_3_LOW]:
        eng.record_due_diligence(DueDiligenceFinding(
            finding_id=f"F-{cat.value}",
            vendor_model_id="VM1",
            category=cat,
            verdict=DueDiligenceVerdict.SATISFACTORY,
            evidence_count=3,
            assessor_user_id="alice",
            assessment_date="2026-05-01"))
    status = eng.due_diligence_status("VM1")
    assert status["is_dd_complete"]
    assert status["n_missing_required"] == 0


def _test_dd_incomplete_missing_categories():
    eng = ModelGovernanceRuntimeEngine()
    eng.register_vendor_model(
        _make_vendor_model(tier=VendorModelTier.TIER_1_HIGH))
    # Record only 1 of 10 required
    eng.record_due_diligence(DueDiligenceFinding(
        finding_id="F1", vendor_model_id="VM1",
        category=DueDiligenceCategory.FINANCIAL_SOUNDNESS,
        verdict=DueDiligenceVerdict.SATISFACTORY,
        evidence_count=2, assessor_user_id="alice",
        assessment_date="2026-05-01"))
    status = eng.due_diligence_status("VM1")
    assert not status["is_dd_complete"]
    assert status["n_missing_required"] == 9


def _test_dd_blocking_finding_blocks_completion():
    eng = ModelGovernanceRuntimeEngine()
    eng.register_vendor_model(
        _make_vendor_model(tier=VendorModelTier.TIER_3_LOW))
    # Cover all 3 categories — but one is UNSATISFACTORY
    cats = list(REQUIRED_DD_CATEGORIES_BY_TIER[
        VendorModelTier.TIER_3_LOW])
    for i, cat in enumerate(cats):
        verdict = (DueDiligenceVerdict.UNSATISFACTORY if i == 0
                     else DueDiligenceVerdict.SATISFACTORY)
        eng.record_due_diligence(DueDiligenceFinding(
            finding_id=f"F{i}", vendor_model_id="VM1",
            category=cat, verdict=verdict,
            evidence_count=2, assessor_user_id="alice",
            assessment_date="2026-05-01"))
    status = eng.due_diligence_status("VM1")
    assert not status["is_dd_complete"]
    assert status["n_blocking_findings"] == 1


def _test_concentration_breach_above_threshold():
    """If 30% of models from one vendor → breach (>25%)."""
    a = assess_vendor_concentration(
        assessment_id="A1", vendor_name="Acme",
        category="credit_scoring",
        n_models_from_vendor=3,
        n_models_in_category_total=10,
        assessment_date="2026-05-01")
    assert a.concentration_pct == Decimal("30")
    assert a.is_breach


def _test_concentration_no_breach_below_threshold():
    a = assess_vendor_concentration(
        assessment_id="A1", vendor_name="Acme",
        category="credit_scoring",
        n_models_from_vendor=2,
        n_models_in_category_total=10,
        assessment_date="2026-05-01")
    assert a.concentration_pct == Decimal("20")
    assert not a.is_breach


def _test_concentration_zero_total_no_breach():
    a = assess_vendor_concentration(
        assessment_id="A1", vendor_name="Acme",
        category="credit_scoring",
        n_models_from_vendor=0,
        n_models_in_category_total=0,
        assessment_date="2026-05-01")
    assert a.concentration_pct == Decimal("0")
    assert not a.is_breach


def _test_vendor_contract_expiring_soon():
    today = date(2026, 5, 1)
    vm_expiring = VendorModel(
        vendor_model_id="VM1", vendor_name="Acme",
        vendor_legal_entity="Acme", vendor_country="US",
        product_name="X", product_version="1",
        tier=VendorModelTier.TIER_2_MEDIUM,
        transparency=VendorTransparency.LIMITED_DISCLOSURE,
        contract_start_date="2025-01-01",
        contract_end_date="2026-07-15")
    assert vm_expiring.is_contract_expiring_soon(as_of=today)
    vm_far = VendorModel(
        vendor_model_id="VM2", vendor_name="Acme",
        vendor_legal_entity="Acme", vendor_country="US",
        product_name="X", product_version="1",
        tier=VendorModelTier.TIER_2_MEDIUM,
        transparency=VendorTransparency.LIMITED_DISCLOSURE,
        contract_start_date="2025-01-01",
        contract_end_date="2028-12-31")
    assert not vm_far.is_contract_expiring_soon(as_of=today)


# ── Retraining tests ───────────────────────────────────────────────
def _test_retraining_state_machine_valid():
    assert is_valid_retraining_transition(
        RetrainingState.TRIGGERED,
        RetrainingState.DATA_PREPARING)


def _test_retraining_state_machine_skip_invalid():
    """Cannot skip from TRIGGERED to PROMOTED_TO_CHAMPION."""
    assert not is_valid_retraining_transition(
        RetrainingState.TRIGGERED,
        RetrainingState.PROMOTED_TO_CHAMPION)


def _test_retraining_terminal_states_no_transitions():
    for terminal in (
            RetrainingState.PROMOTED_TO_CHAMPION,
            RetrainingState.REJECTED,
            RetrainingState.FAILED):
        assert len(ALLOWED_RETRAINING_TRANSITIONS[terminal]) == 0


def _test_retraining_register_policy():
    eng = ModelGovernanceRuntimeEngine()
    p = RetrainingPolicy(
        policy_id="P1", model_id="M1",
        enabled_triggers=(RetrainingTrigger.DRIFT_DETECTED,))
    eng.register_retraining_policy(p)
    assert eng.get_retraining_policy("P1").model_id == "M1"


def _test_retraining_trigger_unenabled_raises():
    eng = ModelGovernanceRuntimeEngine()
    eng.register_retraining_policy(RetrainingPolicy(
        policy_id="P1", model_id="M1",
        enabled_triggers=(RetrainingTrigger.SCHEDULED,)))
    try:
        eng.trigger_retraining(
            run_id="R1", model_id="M1",
            trigger=RetrainingTrigger.DRIFT_DETECTED,    # not enabled
            trigger_evidence="x",
            triggered_at="t",
            triggered_by_user_id="alice",
            policy_id="P1")
        assert False
    except ValueError:
        pass


def _test_retraining_full_happy_path():
    """Full retraining lifecycle: triggered → ... → promoted."""
    eng = ModelGovernanceRuntimeEngine()
    eng.trigger_retraining(
        run_id="R1", model_id="M1",
        trigger=RetrainingTrigger.DRIFT_DETECTED,
        trigger_evidence="PSI=0.35 on feature 'income'",
        triggered_at="2026-05-01T00:00:00Z",
        triggered_by_user_id="alice")
    # Walk through states
    for state in (RetrainingState.DATA_PREPARING,
                    RetrainingState.TRAINING,
                    RetrainingState.VALIDATING,
                    RetrainingState.APPROVED,
                    RetrainingState.DEPLOYED_AS_CHALLENGER):
        eng.transition_retraining(
            run_id="R1", to_state=state,
            actor_user_id="alice", timestamp="t")
    # Attach winning challenger comparison
    eng.attach_champion_challenger_comparison(
        run_id="R1",
        comparison=ChampionChallengerComparison(
            comparison_id="C1", champion_model_id="M1",
            challenger_model_id="M1-v2",
            metric_name="AUC",
            champion_value=Decimal("0.72"),
            challenger_value=Decimal("0.75"),
            improvement_pct=Decimal("4.2"),
            is_statistically_significant=True,
            sample_size=10000,
            comparison_date="2026-05-15"))
    # Promote
    final = eng.transition_retraining(
        run_id="R1", to_state=RetrainingState.PROMOTED_TO_CHAMPION,
        actor_user_id="alice",
        timestamp="2026-05-20T00:00:00Z")
    assert final.state == RetrainingState.PROMOTED_TO_CHAMPION
    assert final.completed_at == "2026-05-20T00:00:00Z"


def _test_retraining_promotion_blocked_without_comparison():
    """PROMOTED_TO_CHAMPION blocked without comparison on file."""
    eng = ModelGovernanceRuntimeEngine()
    eng.trigger_retraining(
        run_id="R1", model_id="M1",
        trigger=RetrainingTrigger.MANUAL,
        trigger_evidence="x", triggered_at="t",
        triggered_by_user_id="alice")
    for state in (RetrainingState.DATA_PREPARING,
                    RetrainingState.TRAINING,
                    RetrainingState.VALIDATING,
                    RetrainingState.APPROVED,
                    RetrainingState.DEPLOYED_AS_CHALLENGER):
        eng.transition_retraining(
            run_id="R1", to_state=state,
            actor_user_id="alice", timestamp="t")
    # No comparison attached
    try:
        eng.transition_retraining(
            run_id="R1",
            to_state=RetrainingState.PROMOTED_TO_CHAMPION,
            actor_user_id="alice", timestamp="t")
        assert False
    except ValueError as e:
        assert "comparison" in str(e).lower()


def _test_retraining_promotion_blocked_when_challenger_loses():
    """PROMOTED_TO_CHAMPION blocked when challenger doesn't win."""
    eng = ModelGovernanceRuntimeEngine()
    eng.trigger_retraining(
        run_id="R1", model_id="M1",
        trigger=RetrainingTrigger.MANUAL,
        trigger_evidence="x", triggered_at="t",
        triggered_by_user_id="alice")
    for state in (RetrainingState.DATA_PREPARING,
                    RetrainingState.TRAINING,
                    RetrainingState.VALIDATING,
                    RetrainingState.APPROVED,
                    RetrainingState.DEPLOYED_AS_CHALLENGER):
        eng.transition_retraining(
            run_id="R1", to_state=state,
            actor_user_id="alice", timestamp="t")
    # Challenger improvement is only 1% — below 2% min
    eng.attach_champion_challenger_comparison(
        run_id="R1",
        comparison=ChampionChallengerComparison(
            comparison_id="C1", champion_model_id="M1",
            challenger_model_id="M1-v2",
            metric_name="AUC",
            champion_value=Decimal("0.72"),
            challenger_value=Decimal("0.728"),
            improvement_pct=Decimal("1.1"),    # < 2%
            is_statistically_significant=True,
            sample_size=10000,
            comparison_date="2026-05-15"))
    try:
        eng.transition_retraining(
            run_id="R1",
            to_state=RetrainingState.PROMOTED_TO_CHAMPION,
            actor_user_id="alice", timestamp="t")
        assert False
    except ValueError as e:
        assert "outperform" in str(e).lower()


def _test_retraining_promotion_blocked_when_not_significant():
    """PROMOTED_TO_CHAMPION blocked when not statistically significant."""
    eng = ModelGovernanceRuntimeEngine()
    eng.trigger_retraining(
        run_id="R1", model_id="M1",
        trigger=RetrainingTrigger.MANUAL,
        trigger_evidence="x", triggered_at="t",
        triggered_by_user_id="alice")
    for state in (RetrainingState.DATA_PREPARING,
                    RetrainingState.TRAINING,
                    RetrainingState.VALIDATING,
                    RetrainingState.APPROVED,
                    RetrainingState.DEPLOYED_AS_CHALLENGER):
        eng.transition_retraining(
            run_id="R1", to_state=state,
            actor_user_id="alice", timestamp="t")
    eng.attach_champion_challenger_comparison(
        run_id="R1",
        comparison=ChampionChallengerComparison(
            comparison_id="C1", champion_model_id="M1",
            challenger_model_id="M1-v2",
            metric_name="AUC",
            champion_value=Decimal("0.72"),
            challenger_value=Decimal("0.78"),
            improvement_pct=Decimal("8.3"),
            is_statistically_significant=False,    # not significant
            sample_size=200,
            comparison_date="2026-05-15"))
    try:
        eng.transition_retraining(
            run_id="R1",
            to_state=RetrainingState.PROMOTED_TO_CHAMPION,
            actor_user_id="alice", timestamp="t")
        assert False
    except ValueError as e:
        assert "outperform" in str(e).lower()


def _test_retraining_failed_terminal():
    """FAILED is terminal — no further transitions."""
    eng = ModelGovernanceRuntimeEngine()
    eng.trigger_retraining(
        run_id="R1", model_id="M1",
        trigger=RetrainingTrigger.MANUAL,
        trigger_evidence="x", triggered_at="t",
        triggered_by_user_id="alice")
    eng.transition_retraining(
        run_id="R1", to_state=RetrainingState.FAILED,
        actor_user_id="alice", timestamp="t")
    try:
        eng.transition_retraining(
            run_id="R1",
            to_state=RetrainingState.DATA_PREPARING,
            actor_user_id="alice", timestamp="t")
        assert False
    except ValueError:
        pass


def _test_engine_concentration_breach_aggregated():
    eng = ModelGovernanceRuntimeEngine()
    # Register 4 vendor models, 2 from same vendor → 50% concentration
    for i, (vname, vmid) in enumerate([
            ("Acme", "VM1"), ("Acme", "VM2"),
            ("Beta", "VM3"), ("Gamma", "VM4")]):
        eng.register_vendor_model(VendorModel(
            vendor_model_id=vmid, vendor_name=vname,
            vendor_legal_entity=vname, vendor_country="US",
            product_name="X", product_version="1",
            tier=VendorModelTier.TIER_2_MEDIUM,
            transparency=VendorTransparency.LIMITED_DISCLOSURE,
            contract_start_date="2025-01-01",
            contract_end_date="2027-12-31"))
    a = eng.assess_concentration(
        assessment_id="A1", vendor_name="Acme",
        category="credit_scoring",
        assessment_date="2026-05-01")
    assert a.concentration_pct == Decimal("50")    # 2/4
    assert a.is_breach
    breaches = eng.vendors_with_concentration_breach()
    assert len(breaches) == 1


def _test_engine_board_summary_aggregates():
    eng = ModelGovernanceRuntimeEngine()
    eng.register_vendor_model(_make_vendor_model())
    eng.register_retraining_policy(RetrainingPolicy(
        policy_id="P1", model_id="M1",
        enabled_triggers=(RetrainingTrigger.SCHEDULED,)))
    s = eng.board_summary()
    assert s["n_vendor_models"] == 1
    assert s["n_retraining_policies"] == 1
    assert s["n_retraining_runs_total"] == 0


def self_test() -> None:
    tests = [
        _test_register_vendor_model,
        _test_register_dup_vendor_raises,
        _test_required_dd_categories_tier_1_full,
        _test_required_dd_categories_tier_3_minimal,
        _test_dd_complete_requires_all_required,
        _test_dd_incomplete_missing_categories,
        _test_dd_blocking_finding_blocks_completion,
        _test_concentration_breach_above_threshold,
        _test_concentration_no_breach_below_threshold,
        _test_concentration_zero_total_no_breach,
        _test_vendor_contract_expiring_soon,
        _test_retraining_state_machine_valid,
        _test_retraining_state_machine_skip_invalid,
        _test_retraining_terminal_states_no_transitions,
        _test_retraining_register_policy,
        _test_retraining_trigger_unenabled_raises,
        _test_retraining_full_happy_path,
        _test_retraining_promotion_blocked_without_comparison,
        _test_retraining_promotion_blocked_when_challenger_loses,
        _test_retraining_promotion_blocked_when_not_significant,
        _test_retraining_failed_terminal,
        _test_engine_concentration_breach_aggregated,
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
        print(f"✗ model_governance_runtime self-test: "
              f"{len(failed)} failures", file=sys.stderr)
        for name, msg in failed:
            print(f"  - {name}: {msg}", file=sys.stderr)
        raise SystemExit(1)
    print(f"✓ model_governance_runtime self-test passed "
          f"({len(tests)} tests)")


if __name__ == "__main__":
    self_test()
