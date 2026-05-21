"""utils.tsl_optimization — Target Service Level (TSL) Optimization
Engine (ENH-158, v10.182).

Phase 5 Resource Optimization — third standard. Given a target
service level (e.g. "80% of calls answered within 30 seconds"),
forecast load (calls/hour, transactions/hour, etc.), and average
handle time, compute the minimum number of agents required using
Erlang C and report shortage/surplus vs. planned headcount.

DESIGN CONTRACT
---------------
1. Channel-scoped TSL targets — each channel has its own
   `pct_served_within_threshold_seconds` pair (e.g. (0.80, 30) or
   (0.95, 300)).
2. Erlang C steady-state model — computes probability of wait
   given offered traffic (Erlangs) and number of agents, then
   service-level for arbitrary threshold. Standard formula, no
   bespoke math.
3. Scenario comparison — same workload + service time, different
   TSL targets, side-by-side staffing requirements.
4. Honest about model assumptions — Erlang C assumes Poisson
   arrivals, exponential service, infinite queue, no
   abandonment. Real call centres have abandonment (Erlang A) —
   that's an explicit honest deferral.

CALCULATIONS
------------
- offered_traffic (Erlangs) = (arrivals_per_hour * AHT_seconds) / 3600
- Erlang C P(wait > 0) = (A^N / N!) * (N / (N - A)) /
    (sum_{k=0..N-1} A^k/k! + (A^N / N!) * N/(N-A))
- service_level = 1 - P(wait>0) * exp(-(N - A) * threshold / AHT)
- find smallest N where service_level >= target_pct

REGULATORY BASIS
----------------
- Internal Customer Experience Framework
- BSC Customer perspective — Right First Time / SLA adherence
- CBK Consumer Protection Guidelines §4 (timely service)

HONEST DEFERRALS
----------------
- ABANDONMENT_MODELLING_ERLANG_A: Erlang A (with abandonment
  probability) deferred — engine uses pure Erlang C
- SHRINKAGE_FACTOR_ROLLUP: agent shrinkage (breaks, training,
  coaching) calculation deferred — caller adjusts headcount
- INTRADAY_INTERVAL_OPTIMIZATION: 30-minute interval re-staffing
  deferred — engine produces hourly-equivalent staffing
- MULTI_SKILL_ROUTING: multi-skill / overflow routing deferred
  — single-skill agents only at v10.182
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple


class TSLChannelType(Enum):
    """Common TSL-tracked channels."""
    CALL_CENTER = "call_center"
    BRANCH_TELLER = "branch_teller"
    BRANCH_BACK_OFFICE = "branch_back_office"
    DIGITAL_SUPPORT = "digital_support"
    EMAIL_QUEUE = "email_queue"
    OTHER = "other"


class StaffingOutcome(Enum):
    SHORTAGE = "shortage"
    SURPLUS = "surplus"
    EXACT = "exact"


# ─── Erlang C math ─────────────────────────────────────────────


def erlang_b(traffic: float, agents: int) -> float:
    """Erlang B blocking probability — used as building block."""
    if agents < 0:
        raise ValueError("agents must be non-negative")
    if traffic < 0:
        raise ValueError("traffic must be non-negative")
    if agents == 0:
        return 1.0
    inv_b = 1.0
    for k in range(1, agents + 1):
        inv_b = 1.0 + (k / traffic) * inv_b if traffic > 0 else 1.0
    return 1.0 / inv_b


def erlang_c_wait_probability(traffic: float, agents: int) -> float:
    """P(wait > 0) under Erlang C steady-state."""
    if agents <= 0:
        return 1.0
    if traffic <= 0:
        return 0.0
    if traffic >= agents:
        # Unstable system — wait probability == 1 in steady state
        return 1.0
    b = erlang_b(traffic, agents)
    return (agents * b) / (agents - traffic * (1 - b))


def service_level(
    traffic: float,
    agents: int,
    aht_seconds: float,
    threshold_seconds: float,
) -> float:
    """Probability that wait time <= threshold under Erlang C."""
    if aht_seconds <= 0:
        raise ValueError("aht_seconds must be > 0")
    if threshold_seconds < 0:
        raise ValueError("threshold_seconds must be >= 0")
    if agents <= 0:
        return 0.0
    if traffic <= 0:
        return 1.0
    if traffic >= agents:
        # Unstable — service level effectively 0 for wait <= threshold
        return 0.0
    pwait = erlang_c_wait_probability(traffic, agents)
    decay = math.exp(
        -(agents - traffic) * threshold_seconds / aht_seconds)
    return 1.0 - pwait * decay


def required_agents(
    arrivals_per_hour: float,
    aht_seconds: float,
    target_pct: float,
    threshold_seconds: float,
    max_agents: int = 500,
) -> int:
    """Smallest agent count meeting target. Raises if not feasible
    within max_agents."""
    if not 0.0 < target_pct < 1.0:
        raise ValueError(
            "target_pct must be a fraction in (0, 1)")
    if arrivals_per_hour < 0:
        raise ValueError("arrivals_per_hour must be >= 0")
    if aht_seconds <= 0:
        raise ValueError("aht_seconds must be > 0")
    traffic = (arrivals_per_hour * aht_seconds) / 3600.0
    # Lower bound — must exceed traffic
    n_floor = max(1, int(math.ceil(traffic)) + 1)
    for n in range(n_floor, max_agents + 1):
        sl = service_level(traffic, n, aht_seconds, threshold_seconds)
        if sl >= target_pct:
            return n
    raise ValueError(
        f"target unreachable within {max_agents} agents — "
        f"check inputs")


# ─── Domain records ────────────────────────────────────────────


@dataclass(frozen=True)
class TSLTarget:
    """A TSL spec for a channel."""
    channel_key: str
    channel_type: TSLChannelType
    target_pct: float           # e.g. 0.80 means 80%
    threshold_seconds: float    # e.g. 30 means 30 seconds
    aht_seconds: float          # average handle time
    notes: Optional[str] = None

    def __post_init__(self):
        if not 0.0 < self.target_pct < 1.0:
            raise ValueError("target_pct must be in (0, 1)")
        if self.threshold_seconds < 0:
            raise ValueError("threshold_seconds must be >= 0")
        if self.aht_seconds <= 0:
            raise ValueError("aht_seconds must be > 0")
        if not self.channel_key:
            raise ValueError("channel_key required")


@dataclass(frozen=True)
class StaffingPlan:
    """Result of optimize_staffing()."""
    plan_id: str
    channel_key: str
    target_pct: float
    threshold_seconds: float
    aht_seconds: float
    arrivals_per_hour: float
    required_agents: int
    planned_agents: Optional[int]
    outcome: StaffingOutcome
    achieved_service_level: float
    achieved_with_planned: Optional[float]
    created_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "channel_key": self.channel_key,
            "target_pct": self.target_pct,
            "threshold_seconds": self.threshold_seconds,
            "aht_seconds": self.aht_seconds,
            "arrivals_per_hour": self.arrivals_per_hour,
            "required_agents": self.required_agents,
            "planned_agents": self.planned_agents,
            "outcome": self.outcome.value,
            "achieved_service_level": self.achieved_service_level,
            "achieved_with_planned": self.achieved_with_planned,
            "created_at": self.created_at.isoformat(),
        }


class TSLOptimizationEngine:
    """In-memory TSL targets + staffing plans store."""

    def __init__(self):
        self._targets: Dict[str, TSLTarget] = {}
        self._plans: Dict[str, StaffingPlan] = {}
        self._counter = 0

    # ─── target management ─────────────────────────────────────
    def set_target(self, target: TSLTarget) -> TSLTarget:
        self._targets[target.channel_key] = target
        return target

    def get_target(self, channel_key: str) -> Optional[TSLTarget]:
        return self._targets.get(channel_key)

    def list_targets(self) -> List[TSLTarget]:
        return list(self._targets.values())

    # ─── optimization ──────────────────────────────────────────
    def optimize_staffing(
        self,
        channel_key: str,
        arrivals_per_hour: float,
        planned_agents: Optional[int] = None,
        max_agents: int = 500,
    ) -> StaffingPlan:
        """Compute required agents to hit the channel's TSL given
        load + AHT. If planned_agents is given, also report the
        SL it actually achieves and shortage/surplus."""
        target = self._targets.get(channel_key)
        if target is None:
            raise ValueError(
                f"no TSL target set for channel {channel_key}")

        req = required_agents(
            arrivals_per_hour=arrivals_per_hour,
            aht_seconds=target.aht_seconds,
            target_pct=target.target_pct,
            threshold_seconds=target.threshold_seconds,
            max_agents=max_agents,
        )
        traffic = (arrivals_per_hour * target.aht_seconds) / 3600.0
        achieved = service_level(
            traffic, req, target.aht_seconds,
            target.threshold_seconds)

        achieved_planned: Optional[float] = None
        outcome: StaffingOutcome
        if planned_agents is None:
            outcome = StaffingOutcome.EXACT
        else:
            achieved_planned = service_level(
                traffic, planned_agents, target.aht_seconds,
                target.threshold_seconds)
            if planned_agents < req:
                outcome = StaffingOutcome.SHORTAGE
            elif planned_agents > req:
                outcome = StaffingOutcome.SURPLUS
            else:
                outcome = StaffingOutcome.EXACT

        self._counter += 1
        plan_id = f"TSP-{self._counter:06d}"
        plan = StaffingPlan(
            plan_id=plan_id,
            channel_key=channel_key,
            target_pct=target.target_pct,
            threshold_seconds=target.threshold_seconds,
            aht_seconds=target.aht_seconds,
            arrivals_per_hour=arrivals_per_hour,
            required_agents=req,
            planned_agents=planned_agents,
            outcome=outcome,
            achieved_service_level=achieved,
            achieved_with_planned=achieved_planned,
        )
        self._plans[plan_id] = plan
        return plan

    def compare_scenarios(
        self,
        channel_key: str,
        arrivals_per_hour: float,
        candidate_targets: List[Tuple[float, float]],
        # list of (target_pct, threshold_seconds)
        aht_seconds: float,
    ) -> List[Dict[str, Any]]:
        """Compare staffing implications of multiple TSL scenarios
        for the same load. Does NOT create plans — read-only
        what-if."""
        out = []
        for tpct, thr in candidate_targets:
            try:
                req = required_agents(
                    arrivals_per_hour=arrivals_per_hour,
                    aht_seconds=aht_seconds,
                    target_pct=tpct,
                    threshold_seconds=thr,
                )
                traffic = (
                    arrivals_per_hour * aht_seconds) / 3600.0
                sl = service_level(
                    traffic, req, aht_seconds, thr)
                feasible = True
                error = None
            except ValueError as e:
                req = None
                sl = None
                feasible = False
                error = str(e)
            out.append({
                "channel_key": channel_key,
                "target_pct": tpct,
                "threshold_seconds": thr,
                "aht_seconds": aht_seconds,
                "arrivals_per_hour": arrivals_per_hour,
                "feasible": feasible,
                "required_agents": req,
                "achieved_service_level": sl,
                "error": error,
            })
        return out

    # ─── queries ───────────────────────────────────────────────
    def get_plan(self, plan_id: str) -> Optional[StaffingPlan]:
        return self._plans.get(plan_id)

    def list_plans(
        self, channel_key: Optional[str] = None
    ) -> List[StaffingPlan]:
        out = list(self._plans.values())
        if channel_key:
            out = [p for p in out if p.channel_key == channel_key]
        return sorted(out, key=lambda p: p.created_at)

    # ─── board ─────────────────────────────────────────────────
    def board_summary(self) -> Dict[str, Any]:
        n_targets = len(self._targets)
        n_plans = len(self._plans)
        by_outcome: Dict[str, int] = {}
        n_shortage = 0
        for p in self._plans.values():
            by_outcome[p.outcome.value] = (
                by_outcome.get(p.outcome.value, 0) + 1)
            if p.outcome == StaffingOutcome.SHORTAGE:
                n_shortage += 1

        return {
            "engine": "ENH-158 TSLOptimizationEngine",
            "n_targets": n_targets,
            "n_plans": n_plans,
            "plans_by_outcome": by_outcome,
            "n_shortage_alerts": n_shortage,
            "regulatory_basis": (
                "Internal Customer Experience Framework + BSC "
                "Customer perspective + CBK Consumer Protection "
                "Guidelines §4"),
            "model": "Erlang C (M/M/N steady-state)",
            "deferrals": {
                "ABANDONMENT_MODELLING_ERLANG_A": (
                    "DEFERRED — engine uses pure Erlang C; real "
                    "call centres need Erlang A for abandonment"),
                "SHRINKAGE_FACTOR_ROLLUP": (
                    "DEFERRED — caller adjusts for shrinkage "
                    "(breaks, training, coaching)"),
                "INTRADAY_INTERVAL_OPTIMIZATION": (
                    "DEFERRED — engine yields hourly-equivalent "
                    "staffing; 30-min interval re-staffing TBD"),
                "MULTI_SKILL_ROUTING": (
                    "DEFERRED — single-skill agents only"),
            },
        }
