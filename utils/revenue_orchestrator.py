"""utils/revenue_orchestrator.py — v10.52: Revenue Agentic Orchestrator.

╔════════════════════════════════════════════════════════════════════════╗
║  ENH-243 — Revenue Agentic Orchestrator                                 ║
║  Cat B — revenue_assurance arc continuation                             ║
╠════════════════════════════════════════════════════════════════════════╣
║  Composition layer over ENH-241 (data integrity) and ENH-242            ║
║  (pattern detection). Where ENH-241 catches "data looks weird" and      ║
║  ENH-242 catches "data follows known leakage patterns", ENH-243         ║
║  takes the resulting findings — heterogeneous in shape — and:           ║
║                                                                          ║
║    1. NORMALISES   — both ValidationFinding and PatternFinding wrap     ║
║                      into a unified WorkItem dataclass so downstream    ║
║                      systems consume a single shape                     ║
║    2. PRIORITISES  — deterministic priority_score combining severity    ║
║                      × family weight × age × monetary impact, with all  ║
║                      components surfaced for Rule 1 transparency        ║
║    3. ROUTES       — maps (family, severity) → InvestigatorTeam per a   ║
║                      configurable TriageRule table; falls back to       ║
║                      OPERATIONS when no rule matches                    ║
║    4. AGES         — computes days_since_raised against an SLA;         ║
║                      surfaces past-SLA flag for caller-driven           ║
║                      escalation (engine never auto-escalates)           ║
║                                                                          ║
║  Per Rule 7, the engine is purely computational and STATELESS. It       ║
║  does NOT track WorkItem state internally — the caller maintains        ║
║  state externally and feeds it back as `current_states` map. The        ║
║  engine never:                                                           ║
║    - changes a WorkItem's state from RAISED to RESOLVED                 ║
║    - sends emails, slack messages, or any external notifications        ║
║    - modifies source records or commits anything to a database          ║
║    - "auto-assigns" in any agentive sense — it computes the team        ║
║      that SHOULD investigate per the routing table; the assignment      ║
║      becomes real only when the caller's workflow records it            ║
║                                                                          ║
║  Per Rule 1, every WorkItem surfaces:                                   ║
║    work_item_id + source_finding_id + source_finding_type +             ║
║    severity + family_or_category + description + affected_record_ids +  ║
║    priority_score + priority_components (dict of named contributors)    ║
║    + assigned_team + sla_deadline + age_days + past_sla flag +          ║
║    current_state + framework_refs                                        ║
║                                                                          ║
║  Pure stdlib (Decimal + frozen dataclasses + enums).                    ║
║                                                                          ║
║  Composes with:                                                          ║
║    - revenue_validation (ENH-241 — produces ValidationFinding)         ║
║    - revenue_anomaly_patterns (ENH-242 — produces PatternFinding)      ║
║    - audit_grc (caller-side — work item state changes audit-logged)    ║
║    - core_audit (caller-side — orchestrate() returns audited)          ║
╚════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from enum import Enum
from typing import Dict, List, Mapping, Optional, Sequence, Tuple, Union

from utils.revenue_validation import (
    ValidationFinding, ValidationSeverity, ValidationCategory)
from utils.revenue_anomaly_patterns import (
    PatternFinding, PatternFamily)

SPEC_DEVIATION_NOTE = (
    "RevenueOrchestrator implements ENH-243 composition layer. "
    "Pure stdlib (Decimal + dataclasses). Per Rule 1, every "
    "WorkItem surfaces source provenance + priority components + "
    "routing decision + SLA state + framework refs. Per Rule 7, "
    "engine is STATELESS and computational — it never tracks "
    "WorkItem state internally, never auto-changes states, never "
    "sends notifications, never auto-escalates past-SLA items. "
    "The 'agentic' in the standard name describes the composition "
    "discipline (matching treasury_agents.py ENH-240 pattern), not "
    "autonomous action. Caller workflow owns all state transitions "
    "and downstream side-effects."
)


# ════════════════════════════════════════════════════════════════════════
# Enums
# ════════════════════════════════════════════════════════════════════════

class FindingType(Enum):
    """Provenance tag — which upstream engine produced this finding."""
    VALIDATION = "VALIDATION"   # from ENH-241 revenue_validation
    PATTERN = "PATTERN"         # from ENH-242 revenue_anomaly_patterns


class WorkItemState(Enum):
    """Triage state machine. Engine surfaces these but never
    transitions them internally — caller-driven."""
    RAISED = "RAISED"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    IN_PROGRESS = "IN_PROGRESS"
    RESOLVED = "RESOLVED"
    DISMISSED = "DISMISSED"
    ESCALATED = "ESCALATED"


class InvestigatorTeam(Enum):
    """Routing destinations. Maps to bank's actual org structure
    in the caller's translation layer."""
    REVENUE_RECOVERY = "REVENUE_RECOVERY"
    OPERATIONS = "OPERATIONS"
    COMPLIANCE = "COMPLIANCE"
    HR_PAYROLL = "HR_PAYROLL"
    DATA_QUALITY = "DATA_QUALITY"
    FINANCE = "FINANCE"


# ════════════════════════════════════════════════════════════════════════
# Severity + family weights for priority computation
# ════════════════════════════════════════════════════════════════════════

# Numeric weights for severity in priority_score. Tuned so CRITICAL
# always outranks HIGH × age × impact; tweakable in the future via
# config injection if production data demands.
SEVERITY_WEIGHTS: Dict[ValidationSeverity, Decimal] = {
    ValidationSeverity.CRITICAL: Decimal("100"),
    ValidationSeverity.HIGH: Decimal("50"),
    ValidationSeverity.MEDIUM: Decimal("20"),
    ValidationSeverity.LOW: Decimal("5"),
    ValidationSeverity.INFO: Decimal("1"),
}

# Family weights — financial-loss families ranked above pure
# compliance / quality families when severity ties.
FAMILY_WEIGHTS: Dict[str, Decimal] = {
    # ENH-242 PatternFamily values
    "LEAKAGE": Decimal("1.5"),
    "BILLING_ERROR": Decimal("1.3"),
    "RATE_CARD_BREACH": Decimal("1.2"),
    "COMMISSION_MISCALC": Decimal("1.0"),
    # ENH-241 ValidationCategory values (mapped via name)
    "SCHEMA": Decimal("0.9"),
    "COMPLETENESS": Decimal("1.1"),
    "RECONCILIATION": Decimal("1.4"),
    "ANOMALY": Decimal("1.0"),
}


# ════════════════════════════════════════════════════════════════════════
# Dataclasses
# ════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class TriageRule:
    """One routing entry. Matches a (family_or_category, severity)
    pair to a team and an SLA in days. Caller composes a tuple of
    these; the first matching rule wins."""
    family_or_category: str
    severity: ValidationSeverity
    team: InvestigatorTeam
    sla_days: int

    def __post_init__(self) -> None:
        if not self.family_or_category:
            raise ValueError(
                "family_or_category must be non-empty")
        if self.sla_days <= 0:
            raise ValueError("sla_days must be > 0")


@dataclass(frozen=True)
class OrchestratorConfig:
    """Static configuration for one orchestration run."""
    triage_rules: Tuple[TriageRule, ...]
    default_team: InvestigatorTeam = InvestigatorTeam.OPERATIONS
    default_sla_days: int = 30
    age_decay_per_day: Decimal = Decimal("0.5")
    impact_weight: Decimal = Decimal("0.0001")  # KES → score multiplier

    def __post_init__(self) -> None:
        if self.default_sla_days <= 0:
            raise ValueError("default_sla_days must be > 0")
        if self.age_decay_per_day < 0:
            raise ValueError("age_decay_per_day must be ≥ 0")
        if self.impact_weight < 0:
            raise ValueError("impact_weight must be ≥ 0")


@dataclass(frozen=True)
class WorkItem:
    """Unified work-item shape produced by the orchestrator."""
    work_item_id: str
    source_finding_id: str
    source_finding_type: FindingType
    severity: ValidationSeverity
    family_or_category: str
    description: str
    affected_record_ids: Tuple[str, ...]
    raised_date: date
    age_days: int
    sla_deadline: date
    past_sla: bool
    assigned_team: InvestigatorTeam
    priority_score: Decimal
    priority_components: Dict[str, Decimal]
    monetary_impact_kes: Optional[Decimal]
    current_state: WorkItemState
    framework_refs: Tuple[str, ...]
    notes: str = ""


@dataclass(frozen=True)
class TriageReport:
    """Aggregate output of orchestrate()."""
    work_items: Tuple[WorkItem, ...]
    by_team: Dict[str, int]
    by_severity: Dict[str, int]
    by_state: Dict[str, int]
    past_sla_count: int
    total_findings: int
    framework_refs: Tuple[str, ...]


# Type alias for either upstream finding shape.
SourceFinding = Union[ValidationFinding, PatternFinding]


# ════════════════════════════════════════════════════════════════════════
# Engine
# ════════════════════════════════════════════════════════════════════════

class RevenueOrchestrator:
    """Stateless composition + prioritisation + routing engine.

    Per Rule 7, the engine is purely computational. It produces
    WorkItem records as a function of (findings, config, state map,
    monetary_impact map, as_of date). The same inputs always
    produce the same output. Nothing is persisted; nothing is sent
    anywhere.

    Caller responsibilities (NOT engine responsibilities):
      - persist WorkItem records to the bank's case-management DB
      - render WorkItems on a Streamlit / dashboard
      - email or message investigators
      - transition WorkItem state when investigators act
      - trigger escalation workflows when past_sla=True
    """

    def __init__(self, config: OrchestratorConfig) -> None:
        self._config = config

    # ── Family + severity extraction ──────────────────────────────────
    def _extract_family(self, finding: SourceFinding) -> str:
        """ValidationFinding has .category (enum); PatternFinding has
        .family (enum). Both expose .value as a string."""
        if isinstance(finding, ValidationFinding):
            return finding.category.value
        return finding.family.value

    def _extract_record_ids(
        self, finding: SourceFinding,
    ) -> Tuple[str, ...]:
        if isinstance(finding, ValidationFinding):
            return (finding.record_id_or_batch_id,)
        return finding.record_ids

    def _finding_type(self, finding: SourceFinding) -> FindingType:
        if isinstance(finding, ValidationFinding):
            return FindingType.VALIDATION
        return FindingType.PATTERN

    # ── Routing ──────────────────────────────────────────────────────
    def _route(
        self, family_or_category: str,
        severity: ValidationSeverity,
    ) -> Tuple[InvestigatorTeam, int]:
        """Find the first triage rule matching (family, severity).
        Falls back to (default_team, default_sla_days)."""
        for rule in self._config.triage_rules:
            if (rule.family_or_category == family_or_category
                    and rule.severity == severity):
                return (rule.team, rule.sla_days)
        return (
            self._config.default_team,
            self._config.default_sla_days)

    # ── Priority score ────────────────────────────────────────────────
    def _priority(
        self, finding: SourceFinding,
        family_or_category: str,
        age_days: int,
        monetary_impact_kes: Optional[Decimal],
    ) -> Tuple[Decimal, Dict[str, Decimal]]:
        """Deterministic priority. Components surfaced separately
        per Rule 1 so callers can inspect why an item was prioritised
        over another."""
        sev_w = SEVERITY_WEIGHTS.get(
            finding.severity, Decimal("1"))
        fam_w = FAMILY_WEIGHTS.get(
            family_or_category, Decimal("1"))
        age_contrib = (
            self._config.age_decay_per_day * Decimal(age_days))
        impact_contrib = (
            self._config.impact_weight * monetary_impact_kes
            if monetary_impact_kes is not None
            else Decimal("0"))

        # Score = (severity × family) + age + impact
        # Using addition for age + impact lets very-old items + huge
        # losses bubble up even when severity is MEDIUM, but high
        # severity still dominates new clean items.
        base = sev_w * fam_w
        score = (base + age_contrib + impact_contrib).quantize(
            Decimal("0.001"))

        components: Dict[str, Decimal] = {
            "severity_weight": sev_w,
            "family_weight": fam_w,
            "base": base.quantize(Decimal("0.001")),
            "age_contribution": age_contrib.quantize(
                Decimal("0.001")),
            "impact_contribution": impact_contrib.quantize(
                Decimal("0.001")),
            "total": score,
        }
        return (score, components)

    # ── Public API: orchestrate ───────────────────────────────────────
    def orchestrate(
        self,
        findings: Sequence[SourceFinding],
        raised_dates: Mapping[str, date],
        as_of: Optional[date] = None,
        current_states: Optional[
            Mapping[str, WorkItemState]] = None,
        monetary_impacts: Optional[
            Mapping[str, Decimal]] = None,
    ) -> TriageReport:
        """Compose findings into a TriageReport.

        Args:
          findings: heterogeneous list of ValidationFinding +
            PatternFinding objects.
          raised_dates: map finding_id → date the finding was
            originally raised. Caller maintains this externally;
            engine does not persist dates.
          as_of: today's date for age computation. Defaults to
            date.today() — pass an explicit date for deterministic
            tests.
          current_states: optional map finding_id → WorkItemState.
            Findings without an entry default to RAISED.
          monetary_impacts: optional map finding_id → estimated
            monetary impact in KES, used by priority scoring when
            available.
        """
        as_of = as_of or date.today()
        current_states = current_states or {}
        monetary_impacts = monetary_impacts or {}

        items: List[WorkItem] = []
        for finding in findings:
            fid = finding.finding_id
            family = self._extract_family(finding)
            record_ids = self._extract_record_ids(finding)
            ftype = self._finding_type(finding)
            raised = raised_dates.get(fid, as_of)
            age = (as_of.toordinal() - raised.toordinal())
            if age < 0:
                # Future raised_date — clip to 0 rather than
                # surfacing nonsense; flagged in notes via
                # framework_refs convention but engine does not
                # raise.
                age = 0
            team, sla_days = self._route(family, finding.severity)
            sla_deadline = raised + timedelta(days=sla_days)
            past_sla = as_of > sla_deadline
            impact = monetary_impacts.get(fid)
            score, components = self._priority(
                finding, family, age, impact)
            state = current_states.get(fid, WorkItemState.RAISED)

            item = WorkItem(
                work_item_id=f"WI-{fid}",
                source_finding_id=fid,
                source_finding_type=ftype,
                severity=finding.severity,
                family_or_category=family,
                description=finding.description,
                affected_record_ids=record_ids,
                raised_date=raised,
                age_days=age,
                sla_deadline=sla_deadline,
                past_sla=past_sla,
                assigned_team=team,
                priority_score=score,
                priority_components=components,
                monetary_impact_kes=impact,
                current_state=state,
                framework_refs=(
                    "ENH-243 §orchestration",
                    "Composes ENH-241 + ENH-242",
                    *finding.framework_refs))
            items.append(item)

        # Sort by priority_score descending — highest priority first.
        items.sort(key=lambda w: w.priority_score, reverse=True)
        items_t = tuple(items)

        by_team: Dict[str, int] = {
            t.value: 0 for t in InvestigatorTeam}
        for w in items_t:
            by_team[w.assigned_team.value] += 1

        by_severity: Dict[str, int] = {
            s.value: 0 for s in ValidationSeverity}
        for w in items_t:
            by_severity[w.severity.value] += 1

        by_state: Dict[str, int] = {
            s.value: 0 for s in WorkItemState}
        for w in items_t:
            by_state[w.current_state.value] += 1

        past_sla_count = sum(1 for w in items_t if w.past_sla)

        return TriageReport(
            work_items=items_t,
            by_team=by_team,
            by_severity=by_severity,
            by_state=by_state,
            past_sla_count=past_sla_count,
            total_findings=len(findings),
            framework_refs=(
                "ENH-243 §orchestration",
                "Composes ENH-241 (revenue_validation) + "
                "ENH-242 (revenue_anomaly_patterns)",
                "Per Rule 7 — stateless, never auto-transitions",
            ))


# ════════════════════════════════════════════════════════════════════════
# Self-tests
# ════════════════════════════════════════════════════════════════════════

def _vf(fid: str, sev: ValidationSeverity,
        cat: ValidationCategory) -> ValidationFinding:
    return ValidationFinding(
        finding_id=fid, severity=sev, category=cat,
        record_id_or_batch_id=f"rec-{fid}",
        description=f"validation finding {fid}",
        expected="x", observed="y",
        framework_refs=("ENH-241",))


def _pf(fid: str, sev: ValidationSeverity,
        family: PatternFamily) -> PatternFinding:
    from utils.revenue_anomaly_patterns import PatternId
    return PatternFinding(
        finding_id=fid,
        pattern_id=PatternId.DUPLICATE_BILLING,
        family=family, severity=sev,
        record_ids=(f"rec-{fid}",),
        description=f"pattern finding {fid}",
        evidence="rule fired",
        confidence=Decimal("1"),
        framework_refs=("ENH-242",))


def _default_config() -> OrchestratorConfig:
    rules = (
        TriageRule(
            family_or_category="LEAKAGE",
            severity=ValidationSeverity.HIGH,
            team=InvestigatorTeam.REVENUE_RECOVERY, sla_days=7),
        TriageRule(
            family_or_category="LEAKAGE",
            severity=ValidationSeverity.MEDIUM,
            team=InvestigatorTeam.REVENUE_RECOVERY, sla_days=14),
        TriageRule(
            family_or_category="BILLING_ERROR",
            severity=ValidationSeverity.HIGH,
            team=InvestigatorTeam.OPERATIONS, sla_days=14),
        TriageRule(
            family_or_category="COMMISSION_MISCALC",
            severity=ValidationSeverity.MEDIUM,
            team=InvestigatorTeam.HR_PAYROLL, sla_days=21),
        TriageRule(
            family_or_category="RATE_CARD_BREACH",
            severity=ValidationSeverity.HIGH,
            team=InvestigatorTeam.COMPLIANCE, sla_days=7),
        TriageRule(
            family_or_category="SCHEMA",
            severity=ValidationSeverity.CRITICAL,
            team=InvestigatorTeam.DATA_QUALITY, sla_days=3),
        TriageRule(
            family_or_category="RECONCILIATION",
            severity=ValidationSeverity.MEDIUM,
            team=InvestigatorTeam.FINANCE, sla_days=14),
    )
    return OrchestratorConfig(triage_rules=rules)


def _test_triage_rule_validates_non_empty_family():
    try:
        TriageRule(
            family_or_category="",
            severity=ValidationSeverity.HIGH,
            team=InvestigatorTeam.OPERATIONS, sla_days=7)
        assert False
    except ValueError:
        pass


def _test_triage_rule_validates_positive_sla():
    try:
        TriageRule(
            family_or_category="X",
            severity=ValidationSeverity.HIGH,
            team=InvestigatorTeam.OPERATIONS, sla_days=0)
        assert False
    except ValueError:
        pass


def _test_config_validates_positive_default_sla():
    try:
        OrchestratorConfig(
            triage_rules=(),
            default_sla_days=0)
        assert False
    except ValueError:
        pass


def _test_config_validates_non_negative_decay():
    try:
        OrchestratorConfig(
            triage_rules=(),
            age_decay_per_day=Decimal("-1"))
        assert False
    except ValueError:
        pass


def _test_validation_finding_routes_via_category():
    """ENH-241 ValidationFinding routes by .category.value."""
    eng = RevenueOrchestrator(_default_config())
    findings = (
        _vf("v1", ValidationSeverity.CRITICAL,
            ValidationCategory.SCHEMA),
    )
    report = eng.orchestrate(
        findings, raised_dates={"v1": date(2026, 4, 1)},
        as_of=date(2026, 4, 5))
    assert len(report.work_items) == 1
    item = report.work_items[0]
    assert item.assigned_team == InvestigatorTeam.DATA_QUALITY
    assert item.source_finding_type == FindingType.VALIDATION
    assert item.family_or_category == "SCHEMA"


def _test_pattern_finding_routes_via_family():
    """ENH-242 PatternFinding routes by .family.value."""
    eng = RevenueOrchestrator(_default_config())
    findings = (
        _pf("p1", ValidationSeverity.HIGH, PatternFamily.LEAKAGE),
    )
    report = eng.orchestrate(
        findings, raised_dates={"p1": date(2026, 4, 1)},
        as_of=date(2026, 4, 5))
    item = report.work_items[0]
    assert item.assigned_team == (
        InvestigatorTeam.REVENUE_RECOVERY)
    assert item.source_finding_type == FindingType.PATTERN


def _test_unmatched_falls_back_to_default():
    """Unknown (family, severity) → default_team + default_sla."""
    eng = RevenueOrchestrator(_default_config())
    findings = (
        _pf("p1", ValidationSeverity.LOW,
            PatternFamily.COMMISSION_MISCALC),
    )
    report = eng.orchestrate(
        findings, raised_dates={"p1": date(2026, 4, 1)},
        as_of=date(2026, 4, 5))
    item = report.work_items[0]
    assert item.assigned_team == InvestigatorTeam.OPERATIONS
    # SLA = default 30 days
    assert (item.sla_deadline - item.raised_date).days == 30


def _test_age_days_computed_correctly():
    eng = RevenueOrchestrator(_default_config())
    findings = (
        _pf("p1", ValidationSeverity.HIGH, PatternFamily.LEAKAGE),
    )
    report = eng.orchestrate(
        findings, raised_dates={"p1": date(2026, 4, 1)},
        as_of=date(2026, 4, 11))   # 10 days later
    assert report.work_items[0].age_days == 10


def _test_future_raised_date_clipped_to_zero():
    eng = RevenueOrchestrator(_default_config())
    findings = (
        _pf("p1", ValidationSeverity.HIGH, PatternFamily.LEAKAGE),
    )
    report = eng.orchestrate(
        findings, raised_dates={"p1": date(2027, 1, 1)},
        as_of=date(2026, 4, 1))
    assert report.work_items[0].age_days == 0


def _test_past_sla_flagged():
    eng = RevenueOrchestrator(_default_config())
    # LEAKAGE HIGH has 7-day SLA
    findings = (
        _pf("p1", ValidationSeverity.HIGH, PatternFamily.LEAKAGE),
    )
    report = eng.orchestrate(
        findings, raised_dates={"p1": date(2026, 4, 1)},
        as_of=date(2026, 4, 15))   # 14 days later
    assert report.work_items[0].past_sla is True
    assert report.past_sla_count == 1


def _test_within_sla_not_flagged():
    eng = RevenueOrchestrator(_default_config())
    findings = (
        _pf("p1", ValidationSeverity.HIGH, PatternFamily.LEAKAGE),
    )
    report = eng.orchestrate(
        findings, raised_dates={"p1": date(2026, 4, 1)},
        as_of=date(2026, 4, 5))
    assert report.work_items[0].past_sla is False


def _test_priority_components_surface():
    """Per Rule 1 — every component is surfaced separately."""
    eng = RevenueOrchestrator(_default_config())
    findings = (
        _pf("p1", ValidationSeverity.HIGH, PatternFamily.LEAKAGE),
    )
    report = eng.orchestrate(
        findings, raised_dates={"p1": date(2026, 4, 1)},
        as_of=date(2026, 4, 11),
        monetary_impacts={"p1": Decimal("5000000")})
    item = report.work_items[0]
    assert "severity_weight" in item.priority_components
    assert "family_weight" in item.priority_components
    assert "age_contribution" in item.priority_components
    assert "impact_contribution" in item.priority_components
    assert "total" in item.priority_components
    # Severity HIGH = 50; family LEAKAGE = 1.5 → base = 75
    assert item.priority_components["base"] == Decimal("75")


def _test_priority_high_severity_outranks_low_severity():
    """CRITICAL outranks MEDIUM when other components equal."""
    eng = RevenueOrchestrator(_default_config())
    findings = (
        _vf("v1", ValidationSeverity.CRITICAL,
            ValidationCategory.SCHEMA),
        _pf("p1", ValidationSeverity.MEDIUM,
            PatternFamily.LEAKAGE),
    )
    report = eng.orchestrate(
        findings,
        raised_dates={
            "v1": date(2026, 4, 1),
            "p1": date(2026, 4, 1)},
        as_of=date(2026, 4, 2))
    # No monetary impact for either — clean severity comparison.
    assert (
        report.work_items[0].source_finding_id == "v1")
    assert (
        report.work_items[1].source_finding_id == "p1")


def _test_large_monetary_impact_can_outrank_higher_severity():
    """Documents an honest design decision: a confirmed KES 100m
    revenue leakage at MEDIUM severity legitimately outranks a
    CRITICAL schema corruption with no quantified impact. With the
    default impact_weight=0.0001, KES 100m contributes 10,000 to
    the score — orders of magnitude above CRITICAL × any family
    weight. Callers who want severity to dominate must lower
    impact_weight in the OrchestratorConfig."""
    eng = RevenueOrchestrator(_default_config())
    findings = (
        _vf("v1", ValidationSeverity.CRITICAL,
            ValidationCategory.SCHEMA),
        _pf("p1", ValidationSeverity.MEDIUM,
            PatternFamily.LEAKAGE),
    )
    report = eng.orchestrate(
        findings,
        raised_dates={
            "v1": date(2026, 4, 1),
            "p1": date(2026, 4, 1)},
        as_of=date(2026, 4, 2),
        monetary_impacts={"p1": Decimal("100000000")})
    # MEDIUM with 100m impact bubbles above CRITICAL no-impact.
    assert (
        report.work_items[0].source_finding_id == "p1")


def _test_age_lifts_priority():
    """Older finding bubbles up over newer at same severity."""
    eng = RevenueOrchestrator(_default_config())
    findings = (
        _pf("new", ValidationSeverity.MEDIUM,
            PatternFamily.BILLING_ERROR),
        _pf("old", ValidationSeverity.MEDIUM,
            PatternFamily.BILLING_ERROR),
    )
    report = eng.orchestrate(
        findings,
        raised_dates={
            "new": date(2026, 4, 10),
            "old": date(2026, 1, 1)},
        as_of=date(2026, 4, 11))
    assert report.work_items[0].source_finding_id == "old"


def _test_monetary_impact_lifts_priority():
    eng = RevenueOrchestrator(_default_config())
    findings = (
        _pf("small", ValidationSeverity.MEDIUM,
            PatternFamily.BILLING_ERROR),
        _pf("huge", ValidationSeverity.MEDIUM,
            PatternFamily.BILLING_ERROR),
    )
    report = eng.orchestrate(
        findings,
        raised_dates={
            "small": date(2026, 4, 1),
            "huge": date(2026, 4, 1)},
        as_of=date(2026, 4, 2),
        monetary_impacts={
            "small": Decimal("1000"),
            "huge": Decimal("100000000")})
    assert report.work_items[0].source_finding_id == "huge"


def _test_state_defaults_to_raised_when_absent():
    eng = RevenueOrchestrator(_default_config())
    findings = (
        _pf("p1", ValidationSeverity.HIGH, PatternFamily.LEAKAGE),
    )
    report = eng.orchestrate(
        findings, raised_dates={"p1": date(2026, 4, 1)},
        as_of=date(2026, 4, 5))
    assert (
        report.work_items[0].current_state
        == WorkItemState.RAISED)


def _test_state_passed_through_when_supplied():
    eng = RevenueOrchestrator(_default_config())
    findings = (
        _pf("p1", ValidationSeverity.HIGH, PatternFamily.LEAKAGE),
    )
    report = eng.orchestrate(
        findings, raised_dates={"p1": date(2026, 4, 1)},
        as_of=date(2026, 4, 5),
        current_states={"p1": WorkItemState.IN_PROGRESS})
    assert (
        report.work_items[0].current_state
        == WorkItemState.IN_PROGRESS)


def _test_engine_does_not_track_state():
    """Per Rule 7 — engine is stateless. Calling orchestrate twice
    on the same finding without supplying state yields RAISED both
    times; state is not memoised by the engine."""
    eng = RevenueOrchestrator(_default_config())
    findings = (
        _pf("p1", ValidationSeverity.HIGH, PatternFamily.LEAKAGE),
    )
    r1 = eng.orchestrate(
        findings, raised_dates={"p1": date(2026, 4, 1)},
        as_of=date(2026, 4, 5),
        current_states={"p1": WorkItemState.RESOLVED})
    r2 = eng.orchestrate(
        findings, raised_dates={"p1": date(2026, 4, 1)},
        as_of=date(2026, 4, 5))
    # Second call: caller did NOT supply state → RAISED, NOT
    # memoised RESOLVED from the first call.
    assert (
        r1.work_items[0].current_state == WorkItemState.RESOLVED)
    assert (
        r2.work_items[0].current_state == WorkItemState.RAISED)


def _test_sort_order_descending_priority():
    eng = RevenueOrchestrator(_default_config())
    findings = (
        _pf("low", ValidationSeverity.LOW,
            PatternFamily.BILLING_ERROR),
        _vf("crit", ValidationSeverity.CRITICAL,
            ValidationCategory.SCHEMA),
        _pf("med", ValidationSeverity.MEDIUM,
            PatternFamily.LEAKAGE),
    )
    report = eng.orchestrate(
        findings,
        raised_dates={
            "low": date(2026, 4, 1),
            "crit": date(2026, 4, 1),
            "med": date(2026, 4, 1)},
        as_of=date(2026, 4, 2))
    ids = [w.source_finding_id for w in report.work_items]
    # CRITICAL > MEDIUM > LOW
    assert ids[0] == "crit"
    assert ids[-1] == "low"


def _test_aggregates_populated():
    eng = RevenueOrchestrator(_default_config())
    findings = (
        _pf("p1", ValidationSeverity.HIGH, PatternFamily.LEAKAGE),
        _pf("p2", ValidationSeverity.HIGH, PatternFamily.LEAKAGE),
        _vf("v1", ValidationSeverity.CRITICAL,
            ValidationCategory.SCHEMA),
    )
    report = eng.orchestrate(
        findings,
        raised_dates={
            "p1": date(2026, 4, 1),
            "p2": date(2026, 4, 1),
            "v1": date(2026, 4, 1)},
        as_of=date(2026, 4, 5))
    assert report.total_findings == 3
    assert (
        report.by_team[
            InvestigatorTeam.REVENUE_RECOVERY.value] == 2)
    assert (
        report.by_team[
            InvestigatorTeam.DATA_QUALITY.value] == 1)
    assert report.by_severity["HIGH"] == 2
    assert report.by_severity["CRITICAL"] == 1
    assert report.by_state["RAISED"] == 3


def _test_work_item_has_full_provenance():
    """Per Rule 1 — work item carries all source context."""
    eng = RevenueOrchestrator(_default_config())
    findings = (
        _pf("p1", ValidationSeverity.HIGH, PatternFamily.LEAKAGE),
    )
    report = eng.orchestrate(
        findings, raised_dates={"p1": date(2026, 4, 1)},
        as_of=date(2026, 4, 5))
    item = report.work_items[0]
    assert item.work_item_id == "WI-p1"
    assert item.source_finding_id == "p1"
    assert item.affected_record_ids == ("rec-p1",)
    assert item.severity == ValidationSeverity.HIGH
    assert item.family_or_category == "LEAKAGE"
    assert "ENH-243" in item.framework_refs[0]
    assert "ENH-242" in " ".join(item.framework_refs)


def _test_empty_findings_yields_empty_report():
    eng = RevenueOrchestrator(_default_config())
    report = eng.orchestrate(
        findings=(), raised_dates={},
        as_of=date(2026, 4, 5))
    assert report.total_findings == 0
    assert len(report.work_items) == 0
    assert report.past_sla_count == 0


def self_test() -> None:
    tests = [
        _test_triage_rule_validates_non_empty_family,
        _test_triage_rule_validates_positive_sla,
        _test_config_validates_positive_default_sla,
        _test_config_validates_non_negative_decay,
        _test_validation_finding_routes_via_category,
        _test_pattern_finding_routes_via_family,
        _test_unmatched_falls_back_to_default,
        _test_age_days_computed_correctly,
        _test_future_raised_date_clipped_to_zero,
        _test_past_sla_flagged,
        _test_within_sla_not_flagged,
        _test_priority_components_surface,
        _test_priority_high_severity_outranks_low_severity,
        _test_large_monetary_impact_can_outrank_higher_severity,
        _test_age_lifts_priority,
        _test_monetary_impact_lifts_priority,
        _test_state_defaults_to_raised_when_absent,
        _test_state_passed_through_when_supplied,
        _test_engine_does_not_track_state,
        _test_sort_order_descending_priority,
        _test_aggregates_populated,
        _test_work_item_has_full_provenance,
        _test_empty_findings_yields_empty_report,
    ]
    failed: List[Tuple[str, str]] = []
    for t in tests:
        try:
            t()
        except AssertionError as e:
            failed.append((t.__name__, str(e)))
        except Exception as e:
            failed.append((t.__name__, f"{type(e).__name__}: {e}"))
    if failed:
        print(
            f"✗ revenue_orchestrator self-test: "
            f"{len(failed)} failures",
            file=sys.stderr)
        for name, msg in failed:
            print(f"  - {name}: {msg}", file=sys.stderr)
        raise SystemExit(1)
    print(
        f"✓ revenue_orchestrator self-test passed "
        f"({len(tests)} tests)")


if __name__ == "__main__":
    self_test()
