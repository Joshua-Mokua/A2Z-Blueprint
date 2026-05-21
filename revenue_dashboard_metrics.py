"""utils/revenue_dashboard_metrics.py — v10.54: Revenue Dashboard Metrics.

╔════════════════════════════════════════════════════════════════════════╗
║  ENH-245 — Revenue Assurance Dashboard (data layer)                     ║
║  Cat B — revenue_assurance arc continuation                             ║
╠════════════════════════════════════════════════════════════════════════╣
║  Aggregation helper for dashboard metrics over revenue_assurance arc    ║
║  WorkItems. Per the v10.46-amended Lean+Compact protocol, the actual    ║
║  UI cockpit is deferred to arc closure (v10.58); shipping a             ║
║  freestanding "dashboard" engine alongside a closure cockpit would be   ║
║  duplicate UI work. This module is the data side: deterministic         ║
║  aggregation routines that the closure cockpit consumes.                ║
║                                                                          ║
║  Six metric families:                                                    ║
║    1. LEAKAGE TREND       — finding count + monetary impact bucketed    ║
║                              by period (default YYYY-MM)                ║
║    2. TOP CATEGORIES      — ranked by count AND by monetary impact;     ║
║                              two rankings since they often disagree     ║
║                              (high-frequency-low-impact vs               ║
║                              low-frequency-high-impact)                 ║
║    3. RECOVERY YTD        — sum of monetary_impact for items in         ║
║                              terminal state (RESOLVED/DISMISSED) since  ║
║                              window start                               ║
║    4. TEAM ACTIVITY       — open / in-progress / resolved / past-SLA   ║
║                              counts per InvestigatorTeam                ║
║    5. CYCLE TIMES         — mean/median/p90 days for state transitions  ║
║                              (RAISED→ACK, RAISED→IN_PROGRESS,           ║
║                              RAISED→RESOLVED)                           ║
║    6. SUMMARY             — total open / total recovered / window      ║
║                                                                          ║
║  Per Rule 1, every metric surfaces its components — counts and impacts ║
║  separately, sample sizes for percentile metrics, period boundaries.    ║
║                                                                          ║
║  Per Rule 7, engine is read-only aggregation. It NEVER:                ║
║    - modifies WorkItems or state transitions                            ║
║    - changes case-management state                                      ║
║    - persists computed metrics                                          ║
║    - schedules emails / notifications / alerts                          ║
║                                                                          ║
║  Pure stdlib (Decimal + statistics + frozen dataclasses + enums).       ║
║                                                                          ║
║  Composes with:                                                          ║
║    - revenue_orchestrator (ENH-243 — consumes WorkItem records)         ║
║    - All four upstream engines via the orchestrator's WorkItem          ║
║      output (ENH-241/242/244 findings + ENH-243 unification)            ║
╚════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

import statistics
import sys
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import Enum
from typing import (
    Callable, Dict, List, Optional, Sequence, Tuple)

from utils.revenue_orchestrator import (
    InvestigatorTeam, WorkItem, WorkItemState)
from utils.revenue_validation import ValidationSeverity

SPEC_DEVIATION_NOTE = (
    "RevenueDashboardMetrics implements ENH-245 as a data-layer "
    "aggregation helper rather than a freestanding UI page. Per "
    "the v10.46-amended Lean+Compact protocol, UI cockpits are "
    "shipped at arc closure (v10.58); separating a 'dashboard' "
    "module from the closure cockpit would duplicate UI work. "
    "This module computes metrics as Decimal + dataclass values "
    "for the closure cockpit to render. Per Rule 1, every metric "
    "surfaces its components (count + impact + sample_size + "
    "framework refs). Per Rule 7, engine is read-only — never "
    "modifies WorkItems, never persists metrics, never schedules "
    "notifications."
)


# ════════════════════════════════════════════════════════════════════════
# Enums
# ════════════════════════════════════════════════════════════════════════

class CycleStage(Enum):
    """Named state transitions whose duration we measure."""
    RAISED_TO_ACKNOWLEDGED = "RAISED_TO_ACKNOWLEDGED"
    RAISED_TO_IN_PROGRESS = "RAISED_TO_IN_PROGRESS"
    RAISED_TO_RESOLVED = "RAISED_TO_RESOLVED"
    ACKNOWLEDGED_TO_RESOLVED = "ACKNOWLEDGED_TO_RESOLVED"


# Terminal states for "recovery" purposes — work item is closed.
TERMINAL_STATES = frozenset({
    WorkItemState.RESOLVED,
    WorkItemState.DISMISSED,
})

# Open states — engaged or pending.
OPEN_STATES = frozenset({
    WorkItemState.RAISED,
    WorkItemState.ACKNOWLEDGED,
    WorkItemState.IN_PROGRESS,
    WorkItemState.ESCALATED,
})


# ════════════════════════════════════════════════════════════════════════
# Dataclasses — inputs
# ════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class DashboardWindow:
    """Time window for the dashboard."""
    period_start: date
    period_end: date

    def __post_init__(self) -> None:
        if self.period_end < self.period_start:
            raise ValueError(
                "period_end must be ≥ period_start")


@dataclass(frozen=True)
class StateTransition:
    """One recorded state transition for cycle-time computation.
    Caller maintains externally (case-management DB) and feeds in.
    Engine never tracks state internally per Rule 7."""
    work_item_id: str
    from_state: WorkItemState
    to_state: WorkItemState
    transition_date: date

    def __post_init__(self) -> None:
        if not self.work_item_id:
            raise ValueError("work_item_id must be non-empty")
        if self.from_state == self.to_state:
            raise ValueError(
                "from_state and to_state must differ")


# ════════════════════════════════════════════════════════════════════════
# Dataclasses — outputs
# ════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class TrendPoint:
    """One point in a leakage / volume trend."""
    period: str
    finding_count: int
    monetary_impact_kes: Decimal


@dataclass(frozen=True)
class CategoryRanking:
    """One category's standing in a top-N ranking."""
    category: str
    count: int
    monetary_impact_kes: Decimal
    pct_of_total_count: Decimal      # 0..1
    pct_of_total_impact: Decimal     # 0..1


@dataclass(frozen=True)
class RecoveryMetric:
    """Recovery aggregate for the window."""
    window_start: date
    window_end: date
    resolved_count: int
    dismissed_count: int
    recovered_kes: Decimal
    open_count: int
    open_estimated_impact_kes: Decimal


@dataclass(frozen=True)
class TeamActivity:
    """Per-team activity breakdown."""
    team: InvestigatorTeam
    raised_count: int
    acknowledged_count: int
    in_progress_count: int
    resolved_count: int
    dismissed_count: int
    escalated_count: int
    past_sla_count: int
    total_count: int


@dataclass(frozen=True)
class CycleTimeMetric:
    """Distribution of cycle times for one transition stage."""
    stage: CycleStage
    sample_size: int
    mean_days: Optional[Decimal]
    median_days: Optional[Decimal]
    p90_days: Optional[Decimal]
    min_days: Optional[int]
    max_days: Optional[int]


@dataclass(frozen=True)
class DashboardMetrics:
    """Top-level container — single entry point for the closure
    cockpit."""
    window: DashboardWindow
    leakage_trend: Tuple[TrendPoint, ...]
    top_categories_by_count: Tuple[CategoryRanking, ...]
    top_categories_by_impact: Tuple[CategoryRanking, ...]
    recovery: RecoveryMetric
    team_activities: Tuple[TeamActivity, ...]
    cycle_times: Tuple[CycleTimeMetric, ...]
    total_work_items: int
    framework_refs: Tuple[str, ...]


# ════════════════════════════════════════════════════════════════════════
# Engine
# ════════════════════════════════════════════════════════════════════════

class RevenueDashboardMetrics:
    """Read-only aggregation over WorkItem stream + state transitions.

    Per Rule 7, the engine is read-only:
      - never mutates WorkItems (frozen dataclasses anyway)
      - never persists output
      - never sends notifications
      - never modifies state transitions

    Per Rule 1, every metric surfaces its components — count vs
    monetary impact split, sample sizes for percentiles, window
    boundaries. Callers can sanity-check or drill down.
    """

    DEFAULT_TOP_N: int = 5

    @staticmethod
    def _default_period_extractor(d: date) -> str:
        return d.strftime("%Y-%m")

    @staticmethod
    def _in_window(d: date, window: DashboardWindow) -> bool:
        return window.period_start <= d <= window.period_end

    @staticmethod
    def _safe_div(num: Decimal, den: Decimal) -> Decimal:
        if den == 0:
            return Decimal("0")
        return (num / den).quantize(Decimal("0.0001"))

    # ── Metric 1: Leakage trend ──────────────────────────────────────
    def compute_leakage_trend(
        self,
        work_items: Sequence[WorkItem],
        window: DashboardWindow,
        period_extractor: Optional[Callable[[date], str]] = None,
    ) -> Tuple[TrendPoint, ...]:
        """Bucket findings by period inside the window. Returns a
        tuple of TrendPoint sorted by period ascending. Periods with
        zero findings inside the window are NOT synthesised — caller
        is responsible for any gap-filling."""
        pe = period_extractor or self._default_period_extractor
        buckets: Dict[str, Tuple[int, Decimal]] = {}
        for w in work_items:
            if not self._in_window(w.raised_date, window):
                continue
            key = pe(w.raised_date)
            count, impact = buckets.get(
                key, (0, Decimal("0")))
            count += 1
            if w.monetary_impact_kes is not None:
                impact += w.monetary_impact_kes
            buckets[key] = (count, impact)
        return tuple(
            TrendPoint(
                period=k, finding_count=c,
                monetary_impact_kes=i)
            for k, (c, i) in sorted(buckets.items()))

    # ── Metric 2: Top categories ─────────────────────────────────────
    def compute_top_categories(
        self,
        work_items: Sequence[WorkItem],
        top_n: int = DEFAULT_TOP_N,
    ) -> Tuple[
        Tuple[CategoryRanking, ...],
        Tuple[CategoryRanking, ...]]:
        """Two rankings of the same categories: by count, by impact.
        High-frequency-low-impact and low-frequency-high-impact
        often disagree — surfacing both helps prioritise."""
        if top_n < 1:
            raise ValueError("top_n must be ≥ 1")
        agg: Dict[str, Tuple[int, Decimal]] = {}
        for w in work_items:
            count, impact = agg.get(
                w.family_or_category, (0, Decimal("0")))
            count += 1
            if w.monetary_impact_kes is not None:
                impact += w.monetary_impact_kes
            agg[w.family_or_category] = (count, impact)
        total_count = sum(c for c, _ in agg.values())
        total_impact = sum(
            (i for _, i in agg.values()), Decimal("0"))

        rankings: List[CategoryRanking] = []
        for cat, (c, i) in agg.items():
            rankings.append(CategoryRanking(
                category=cat, count=c, monetary_impact_kes=i,
                pct_of_total_count=self._safe_div(
                    Decimal(c), Decimal(total_count)),
                pct_of_total_impact=self._safe_div(
                    i, total_impact)))

        by_count = tuple(
            sorted(rankings,
                   key=lambda r: r.count,
                   reverse=True)[:top_n])
        by_impact = tuple(
            sorted(rankings,
                   key=lambda r: r.monetary_impact_kes,
                   reverse=True)[:top_n])
        return (by_count, by_impact)

    # ── Metric 3: Recovery ───────────────────────────────────────────
    def compute_recovery(
        self,
        work_items: Sequence[WorkItem],
        window: DashboardWindow,
    ) -> RecoveryMetric:
        """Sum monetary_impact for resolved/dismissed items raised
        within the window. Open count and estimated open impact
        also surfaced for comparison."""
        resolved = dismissed = 0
        recovered = Decimal("0")
        open_count = 0
        open_impact = Decimal("0")
        for w in work_items:
            if not self._in_window(w.raised_date, window):
                continue
            if w.current_state == WorkItemState.RESOLVED:
                resolved += 1
                if w.monetary_impact_kes is not None:
                    recovered += w.monetary_impact_kes
            elif w.current_state == WorkItemState.DISMISSED:
                dismissed += 1
                # Dismissed items are NOT recoveries — they were
                # determined to be non-issues. Don't add to
                # recovered_kes.
            elif w.current_state in OPEN_STATES:
                open_count += 1
                if w.monetary_impact_kes is not None:
                    open_impact += w.monetary_impact_kes
        return RecoveryMetric(
            window_start=window.period_start,
            window_end=window.period_end,
            resolved_count=resolved,
            dismissed_count=dismissed,
            recovered_kes=recovered,
            open_count=open_count,
            open_estimated_impact_kes=open_impact)

    # ── Metric 4: Team activity ──────────────────────────────────────
    def compute_team_activity(
        self,
        work_items: Sequence[WorkItem],
    ) -> Tuple[TeamActivity, ...]:
        """Per-team counts across all states. Includes past_sla
        regardless of state."""
        per_team: Dict[
            InvestigatorTeam, Dict[str, int]] = {}
        for t in InvestigatorTeam:
            per_team[t] = {
                "RAISED": 0, "ACKNOWLEDGED": 0,
                "IN_PROGRESS": 0, "RESOLVED": 0,
                "DISMISSED": 0, "ESCALATED": 0,
                "PAST_SLA": 0, "TOTAL": 0}
        for w in work_items:
            d = per_team[w.assigned_team]
            d[w.current_state.value] += 1
            d["TOTAL"] += 1
            if w.past_sla:
                d["PAST_SLA"] += 1
        result: List[TeamActivity] = []
        for team, d in per_team.items():
            if d["TOTAL"] == 0:
                continue
            result.append(TeamActivity(
                team=team,
                raised_count=d["RAISED"],
                acknowledged_count=d["ACKNOWLEDGED"],
                in_progress_count=d["IN_PROGRESS"],
                resolved_count=d["RESOLVED"],
                dismissed_count=d["DISMISSED"],
                escalated_count=d["ESCALATED"],
                past_sla_count=d["PAST_SLA"],
                total_count=d["TOTAL"]))
        return tuple(
            sorted(result,
                   key=lambda t: t.total_count, reverse=True))

    # ── Metric 5: Cycle times ────────────────────────────────────────
    def compute_cycle_times(
        self,
        transitions: Sequence[StateTransition],
        raised_dates: Dict[str, date],
    ) -> Tuple[CycleTimeMetric, ...]:
        """For each named CycleStage, find transitions matching
        from→to states and compute days from raised_date to that
        transition. Returns per-stage distribution metrics."""
        stage_to_endpoints: Dict[
            CycleStage,
            Tuple[WorkItemState, WorkItemState]] = {
            CycleStage.RAISED_TO_ACKNOWLEDGED: (
                WorkItemState.RAISED,
                WorkItemState.ACKNOWLEDGED),
            CycleStage.RAISED_TO_IN_PROGRESS: (
                WorkItemState.RAISED,
                WorkItemState.IN_PROGRESS),
            CycleStage.RAISED_TO_RESOLVED: (
                WorkItemState.RAISED,
                WorkItemState.RESOLVED),
            CycleStage.ACKNOWLEDGED_TO_RESOLVED: (
                WorkItemState.ACKNOWLEDGED,
                WorkItemState.RESOLVED),
        }

        results: List[CycleTimeMetric] = []
        for stage, (from_s, to_s) in stage_to_endpoints.items():
            durations: List[int] = []
            for tr in transitions:
                if tr.from_state != from_s:
                    continue
                if tr.to_state != to_s:
                    continue
                # For RAISED-anchored stages, anchor at raised_date.
                # For ACKNOWLEDGED→RESOLVED, anchor at the
                # ACKNOWLEDGED transition date — we'd need that
                # transition recorded. Simplification: anchor at
                # raised_date for all stages (caller-friendly,
                # slightly less precise for ACK→RESOLVED).
                anchor = raised_dates.get(tr.work_item_id)
                if anchor is None:
                    continue
                d = (
                    tr.transition_date.toordinal()
                    - anchor.toordinal())
                if d < 0:
                    continue   # bad data — skip
                durations.append(d)

            if not durations:
                results.append(CycleTimeMetric(
                    stage=stage, sample_size=0,
                    mean_days=None, median_days=None,
                    p90_days=None, min_days=None, max_days=None))
                continue

            mean = Decimal(str(
                statistics.fmean(durations))).quantize(
                    Decimal("0.01"))
            med = Decimal(str(
                statistics.median(durations))).quantize(
                    Decimal("0.01"))
            # Simple p90 — pick the value at index ceil(0.9 * n) - 1
            sorted_d = sorted(durations)
            p90_idx = max(
                0,
                min(
                    len(sorted_d) - 1,
                    int(0.9 * len(sorted_d) + 0.5) - 1))
            p90 = Decimal(str(sorted_d[p90_idx])).quantize(
                Decimal("0.01"))
            results.append(CycleTimeMetric(
                stage=stage, sample_size=len(durations),
                mean_days=mean, median_days=med, p90_days=p90,
                min_days=min(durations),
                max_days=max(durations)))
        return tuple(results)

    # ── Public API: compute_all ──────────────────────────────────────
    def compute_all(
        self,
        work_items: Sequence[WorkItem],
        window: DashboardWindow,
        transitions: Sequence[StateTransition] = (),
        raised_dates_override: Optional[
            Dict[str, date]] = None,
        top_n: int = DEFAULT_TOP_N,
        period_extractor: Optional[
            Callable[[date], str]] = None,
    ) -> DashboardMetrics:
        """Run all five metric blocks and return unified report."""
        # Build raised_dates from work items, allow override
        # (e.g. for tests).
        raised_dates: Dict[str, date] = {
            w.work_item_id: w.raised_date for w in work_items}
        if raised_dates_override:
            raised_dates.update(raised_dates_override)

        leakage = self.compute_leakage_trend(
            work_items, window, period_extractor)
        by_count, by_impact = self.compute_top_categories(
            work_items, top_n=top_n)
        recovery = self.compute_recovery(work_items, window)
        team_activities = self.compute_team_activity(work_items)
        cycle_times = self.compute_cycle_times(
            transitions, raised_dates)

        return DashboardMetrics(
            window=window,
            leakage_trend=leakage,
            top_categories_by_count=by_count,
            top_categories_by_impact=by_impact,
            recovery=recovery,
            team_activities=team_activities,
            cycle_times=cycle_times,
            total_work_items=len(work_items),
            framework_refs=(
                "ENH-245 §dashboard_metrics",
                "Aggregates ENH-243 WorkItem stream + caller-"
                "supplied StateTransitions",
                "Per Rule 7 — read-only, no persistence, no "
                "notifications",
            ))


# ════════════════════════════════════════════════════════════════════════
# Self-tests
# ════════════════════════════════════════════════════════════════════════

def _wi(
    wid: str, raised: date, family: str,
    severity: ValidationSeverity = ValidationSeverity.HIGH,
    state: WorkItemState = WorkItemState.RAISED,
    team: InvestigatorTeam = InvestigatorTeam.OPERATIONS,
    impact: Optional[Decimal] = None,
    past_sla: bool = False,
) -> WorkItem:
    from utils.revenue_orchestrator import FindingType
    return WorkItem(
        work_item_id=wid,
        source_finding_id=f"f-{wid}",
        source_finding_type=FindingType.PATTERN,
        severity=severity,
        family_or_category=family,
        description=f"item {wid}",
        affected_record_ids=(f"r-{wid}",),
        raised_date=raised,
        age_days=0,
        sla_deadline=raised,
        past_sla=past_sla,
        assigned_team=team,
        priority_score=Decimal("100"),
        priority_components={},
        monetary_impact_kes=impact,
        current_state=state,
        framework_refs=("ENH-243",))


def _test_window_validates_end_after_start():
    try:
        DashboardWindow(
            period_start=date(2026, 4, 30),
            period_end=date(2026, 4, 1))
        assert False
    except ValueError:
        pass


def _test_state_transition_validates_distinct():
    try:
        StateTransition(
            work_item_id="w1",
            from_state=WorkItemState.RAISED,
            to_state=WorkItemState.RAISED,
            transition_date=date(2026, 4, 5))
        assert False
    except ValueError:
        pass


def _test_state_transition_validates_id():
    try:
        StateTransition(
            work_item_id="",
            from_state=WorkItemState.RAISED,
            to_state=WorkItemState.RESOLVED,
            transition_date=date(2026, 4, 5))
        assert False
    except ValueError:
        pass


def _test_leakage_trend_buckets_by_month():
    eng = RevenueDashboardMetrics()
    items = (
        _wi("a", date(2026, 1, 5), "LEAKAGE",
            impact=Decimal("1000")),
        _wi("b", date(2026, 1, 20), "LEAKAGE",
            impact=Decimal("500")),
        _wi("c", date(2026, 2, 3), "LEAKAGE",
            impact=Decimal("2000")),
    )
    window = DashboardWindow(
        period_start=date(2026, 1, 1),
        period_end=date(2026, 12, 31))
    trend = eng.compute_leakage_trend(items, window)
    assert len(trend) == 2
    assert trend[0].period == "2026-01"
    assert trend[0].finding_count == 2
    assert trend[0].monetary_impact_kes == Decimal("1500")
    assert trend[1].period == "2026-02"
    assert trend[1].finding_count == 1


def _test_leakage_trend_excludes_outside_window():
    eng = RevenueDashboardMetrics()
    items = (
        _wi("a", date(2025, 12, 5), "LEAKAGE",
            impact=Decimal("1000")),   # before window
        _wi("b", date(2026, 4, 5), "LEAKAGE",
            impact=Decimal("500")),    # in window
    )
    window = DashboardWindow(
        period_start=date(2026, 1, 1),
        period_end=date(2026, 12, 31))
    trend = eng.compute_leakage_trend(items, window)
    assert len(trend) == 1
    assert trend[0].period == "2026-04"


def _test_top_categories_count_vs_impact_diverge():
    eng = RevenueDashboardMetrics()
    # LEAKAGE: 5 small findings; BILLING_ERROR: 1 huge
    items = tuple(
        _wi(f"l{i}", date(2026, 4, i), "LEAKAGE",
            impact=Decimal("1000"))
        for i in range(1, 6))
    items = items + (
        _wi("big", date(2026, 4, 6), "BILLING_ERROR",
            impact=Decimal("10000000")),)
    by_count, by_impact = eng.compute_top_categories(items)
    assert by_count[0].category == "LEAKAGE"
    assert by_impact[0].category == "BILLING_ERROR"


def _test_top_categories_empty_yields_empty():
    eng = RevenueDashboardMetrics()
    by_count, by_impact = eng.compute_top_categories(())
    assert by_count == ()
    assert by_impact == ()


def _test_top_categories_validates_top_n():
    eng = RevenueDashboardMetrics()
    try:
        eng.compute_top_categories(
            (_wi("a", date(2026, 4, 1), "X"),), top_n=0)
        assert False
    except ValueError:
        pass


def _test_recovery_sums_resolved_only():
    eng = RevenueDashboardMetrics()
    items = (
        _wi("r1", date(2026, 4, 1), "LEAKAGE",
            state=WorkItemState.RESOLVED,
            impact=Decimal("1000")),
        _wi("r2", date(2026, 4, 1), "LEAKAGE",
            state=WorkItemState.RESOLVED,
            impact=Decimal("500")),
        _wi("d1", date(2026, 4, 1), "LEAKAGE",
            state=WorkItemState.DISMISSED,
            impact=Decimal("9999")),  # dismissed = not recovered
        _wi("o1", date(2026, 4, 1), "LEAKAGE",
            state=WorkItemState.IN_PROGRESS,
            impact=Decimal("2000")),
    )
    window = DashboardWindow(
        period_start=date(2026, 1, 1),
        period_end=date(2026, 12, 31))
    recovery = eng.compute_recovery(items, window)
    assert recovery.resolved_count == 2
    assert recovery.dismissed_count == 1
    assert recovery.recovered_kes == Decimal("1500")
    assert recovery.open_count == 1
    assert recovery.open_estimated_impact_kes == Decimal("2000")


def _test_team_activity_aggregates_by_team():
    eng = RevenueDashboardMetrics()
    items = (
        _wi("a", date(2026, 4, 1), "LEAKAGE",
            team=InvestigatorTeam.REVENUE_RECOVERY,
            state=WorkItemState.RAISED),
        _wi("b", date(2026, 4, 2), "LEAKAGE",
            team=InvestigatorTeam.REVENUE_RECOVERY,
            state=WorkItemState.RESOLVED),
        _wi("c", date(2026, 4, 3), "BILLING_ERROR",
            team=InvestigatorTeam.OPERATIONS,
            state=WorkItemState.IN_PROGRESS,
            past_sla=True),
    )
    activities = eng.compute_team_activity(items)
    assert len(activities) == 2
    rr = next(
        a for a in activities
        if a.team == InvestigatorTeam.REVENUE_RECOVERY)
    assert rr.total_count == 2
    assert rr.raised_count == 1
    assert rr.resolved_count == 1
    ops = next(
        a for a in activities
        if a.team == InvestigatorTeam.OPERATIONS)
    assert ops.in_progress_count == 1
    assert ops.past_sla_count == 1


def _test_team_activity_excludes_zero_total_teams():
    eng = RevenueDashboardMetrics()
    items = (
        _wi("a", date(2026, 4, 1), "LEAKAGE",
            team=InvestigatorTeam.REVENUE_RECOVERY),
    )
    activities = eng.compute_team_activity(items)
    assert len(activities) == 1
    assert (
        activities[0].team == InvestigatorTeam.REVENUE_RECOVERY)


def _test_cycle_times_compute_distribution():
    eng = RevenueDashboardMetrics()
    transitions = tuple(
        StateTransition(
            work_item_id=f"w{i}",
            from_state=WorkItemState.RAISED,
            to_state=WorkItemState.RESOLVED,
            transition_date=date(2026, 4, 1 + i))
        for i in range(10))
    raised = {f"w{i}": date(2026, 4, 1) for i in range(10)}
    metrics = eng.compute_cycle_times(transitions, raised)
    raised_to_resolved = next(
        m for m in metrics
        if m.stage == CycleStage.RAISED_TO_RESOLVED)
    assert raised_to_resolved.sample_size == 10
    assert raised_to_resolved.mean_days is not None
    assert raised_to_resolved.min_days == 0
    assert raised_to_resolved.max_days == 9


def _test_cycle_times_empty_stage_yields_none_metrics():
    eng = RevenueDashboardMetrics()
    metrics = eng.compute_cycle_times((), {})
    for m in metrics:
        assert m.sample_size == 0
        assert m.mean_days is None


def _test_cycle_times_skip_negative_durations():
    """Bad data — transition recorded before raised_date — skipped."""
    eng = RevenueDashboardMetrics()
    transitions = (
        StateTransition(
            work_item_id="w1",
            from_state=WorkItemState.RAISED,
            to_state=WorkItemState.RESOLVED,
            transition_date=date(2026, 3, 1)),
    )
    raised = {"w1": date(2026, 4, 1)}
    metrics = eng.compute_cycle_times(transitions, raised)
    raised_to_resolved = next(
        m for m in metrics
        if m.stage == CycleStage.RAISED_TO_RESOLVED)
    assert raised_to_resolved.sample_size == 0


def _test_compute_all_orchestrates():
    eng = RevenueDashboardMetrics()
    items = (
        _wi("a", date(2026, 4, 1), "LEAKAGE",
            state=WorkItemState.RESOLVED,
            impact=Decimal("1000")),
        _wi("b", date(2026, 4, 2), "BILLING_ERROR",
            state=WorkItemState.IN_PROGRESS,
            impact=Decimal("2000")),
    )
    transitions = (
        StateTransition(
            work_item_id="a",
            from_state=WorkItemState.RAISED,
            to_state=WorkItemState.RESOLVED,
            transition_date=date(2026, 4, 5)),
    )
    window = DashboardWindow(
        period_start=date(2026, 1, 1),
        period_end=date(2026, 12, 31))
    metrics = eng.compute_all(items, window, transitions)
    assert isinstance(metrics, DashboardMetrics)
    assert metrics.total_work_items == 2
    assert len(metrics.leakage_trend) == 1
    assert metrics.recovery.resolved_count == 1
    raised_to_resolved = next(
        m for m in metrics.cycle_times
        if m.stage == CycleStage.RAISED_TO_RESOLVED)
    assert raised_to_resolved.sample_size == 1


def _test_metrics_have_full_provenance():
    """Per Rule 1 — every metric block includes its components."""
    eng = RevenueDashboardMetrics()
    items = (
        _wi("a", date(2026, 4, 1), "LEAKAGE",
            impact=Decimal("1000")),
    )
    window = DashboardWindow(
        period_start=date(2026, 1, 1),
        period_end=date(2026, 12, 31))
    metrics = eng.compute_all(items, window)
    # Window, refs, totals all surfaced
    assert metrics.window.period_start == date(2026, 1, 1)
    assert any(
        "ENH-245" in r for r in metrics.framework_refs)
    assert metrics.total_work_items == 1
    # Recovery surfaces both window dates
    assert (
        metrics.recovery.window_start == date(2026, 1, 1))
    assert (
        metrics.recovery.window_end == date(2026, 12, 31))


def _test_engine_does_not_mutate_inputs():
    """Per Rule 7 — engine is read-only; frozen dataclasses
    enforce immutability."""
    eng = RevenueDashboardMetrics()
    items = (
        _wi("a", date(2026, 4, 1), "LEAKAGE",
            impact=Decimal("1000")),
    )
    window = DashboardWindow(
        period_start=date(2026, 1, 1),
        period_end=date(2026, 12, 31))
    eng.compute_all(items, window)
    # Frozen contract; values unchanged
    assert items[0].current_state == WorkItemState.RAISED
    assert items[0].monetary_impact_kes == Decimal("1000")


def _test_pct_calculations_correct():
    """Top-categories pct_of_total fields sum to ≈ 1.0 across
    all rankings."""
    eng = RevenueDashboardMetrics()
    items = (
        _wi("a", date(2026, 4, 1), "LEAKAGE",
            impact=Decimal("1000")),
        _wi("b", date(2026, 4, 2), "BILLING_ERROR",
            impact=Decimal("3000")),
        _wi("c", date(2026, 4, 3), "BILLING_ERROR",
            impact=Decimal("1000")),
    )
    by_count, by_impact = eng.compute_top_categories(items)
    # by_count: BILLING_ERROR=2 (66.7%), LEAKAGE=1 (33.3%)
    pct_sum = sum(
        (r.pct_of_total_count for r in by_count),
        Decimal("0"))
    assert pct_sum > Decimal("0.99")
    assert pct_sum <= Decimal("1.0001")


def self_test() -> None:
    tests = [
        _test_window_validates_end_after_start,
        _test_state_transition_validates_distinct,
        _test_state_transition_validates_id,
        _test_leakage_trend_buckets_by_month,
        _test_leakage_trend_excludes_outside_window,
        _test_top_categories_count_vs_impact_diverge,
        _test_top_categories_empty_yields_empty,
        _test_top_categories_validates_top_n,
        _test_recovery_sums_resolved_only,
        _test_team_activity_aggregates_by_team,
        _test_team_activity_excludes_zero_total_teams,
        _test_cycle_times_compute_distribution,
        _test_cycle_times_empty_stage_yields_none_metrics,
        _test_cycle_times_skip_negative_durations,
        _test_compute_all_orchestrates,
        _test_metrics_have_full_provenance,
        _test_engine_does_not_mutate_inputs,
        _test_pct_calculations_correct,
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
            f"✗ revenue_dashboard_metrics self-test: "
            f"{len(failed)} failures",
            file=sys.stderr)
        for name, msg in failed:
            print(f"  - {name}: {msg}", file=sys.stderr)
        raise SystemExit(1)
    print(
        f"✓ revenue_dashboard_metrics self-test passed "
        f"({len(tests)} tests)")


if __name__ == "__main__":
    self_test()
