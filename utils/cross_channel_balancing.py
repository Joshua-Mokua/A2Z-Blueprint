"""utils.cross_channel_balancing — Cross-Channel Resource Balancing
Engine (ENH-159, v10.183).

Phase 5 Resource Optimization — fourth standard. Sits downstream
of ENH-157 (forecasts) and ENH-158 (TSL targets). Given multiple
channels each with forecast load, TSL target, current planned
agents, and a transferability profile, recommends agent shifts
from surplus channels to shortage channels.

DESIGN CONTRACT
---------------
1. Greedy shortage-first algorithm — at v10.183 the engine uses a
   deterministic greedy heuristic, not a full LP solver. It
   ranks shortage channels by gap severity, then ranks surplus
   channels by surplus magnitude, and proposes shifts subject to
   transferability rules. COST_OPTIMIZED_LP_SOLVER is honestly
   deferred.
2. Transferability is explicit — each channel declares which
   other channels its agents can serve (e.g. RETAIL_CC agents
   can serve EMAIL_QUEUE, but not BACK_OFFICE). The engine never
   silently moves agents across non-transferable boundaries.
3. Read-only recommendations — engine produces a Recommendation
   record. Actual headcount adjustments happen in the WFM /
   ops system; this engine does not push.
4. Idempotent — same input produces same recommendation. No
   randomness, no time-of-day side effects on the algorithm.

INPUTS
------
Per-channel:
- channel_key (matches ENH-158 TSLOptimizationEngine target)
- forecast_arrivals_per_hour (matches ENH-157 forecast point)
- planned_agents (current schedule)
- transferable_to (list of other channel_keys this channel's
  agents can also serve)

Engine pulls TSL specs from a TSLOptimizationEngine instance
passed at construction time, computes per-channel required
agents via Erlang C (ENH-158), and produces a balanced plan.

REGULATORY BASIS
----------------
- Internal Workforce Management Framework
- BSC People + Customer perspectives (combined: capacity and
  service)
- CBK Operational Risk Guidelines §6.4 (resource adequacy)

HONEST DEFERRALS
----------------
- REAL_TIME_SKILLS_MATRIX: HRIS skills feed not integrated;
  caller declares transferability lists explicitly per channel
- AUTO_REBALANCE_TRIGGER: no scheduled / event-triggered re-
  balancing — caller invokes balance() manually
- COST_OPTIMIZED_LP_SOLVER: greedy heuristic only — no LP /
  MILP optimisation across cost, SL, and shift constraints
- SKILL_DECAY_MODEL: no model of skill atrophy when agent moved
  away from primary channel for extended periods
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from utils.tsl_optimization import (
    TSLOptimizationEngine,
    required_agents,
    service_level,
)


class BalanceOutcome(Enum):
    """Per-channel outcome after rebalancing."""
    SHORTAGE_RESOLVED = "shortage_resolved"
    SHORTAGE_PARTIAL = "shortage_partial"
    SHORTAGE_UNRESOLVED = "shortage_unresolved"
    SURPLUS_GIVING = "surplus_giving"
    BALANCED = "balanced"


@dataclass(frozen=True)
class ChannelInput:
    """Per-channel input to the balancer."""
    channel_key: str
    forecast_arrivals_per_hour: float
    planned_agents: int
    transferable_to: Tuple[str, ...] = ()
    # Optional minimum agents floor (e.g. for compliance reasons)
    min_agents_after_giving: int = 0

    def __post_init__(self):
        if not self.channel_key:
            raise ValueError("channel_key required")
        if self.forecast_arrivals_per_hour < 0:
            raise ValueError("forecast_arrivals_per_hour must be >= 0")
        if self.planned_agents < 0:
            raise ValueError("planned_agents must be >= 0")
        if self.min_agents_after_giving < 0:
            raise ValueError("min_agents_after_giving must be >= 0")


@dataclass(frozen=True)
class AgentShift:
    """A proposed agent move from one channel to another."""
    from_channel: str
    to_channel: str
    n_agents: int
    rationale: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "from_channel": self.from_channel,
            "to_channel": self.to_channel,
            "n_agents": self.n_agents,
            "rationale": self.rationale,
        }


@dataclass(frozen=True)
class ChannelOutcome:
    """Post-rebalance per-channel summary."""
    channel_key: str
    required_agents: int
    planned_agents: int
    final_agents: int
    initial_gap: int    # required - planned (positive = shortage)
    final_gap: int      # required - final
    achieved_sl_initial: float
    achieved_sl_final: float
    outcome: BalanceOutcome

    def to_dict(self) -> Dict[str, Any]:
        return {
            "channel_key": self.channel_key,
            "required_agents": self.required_agents,
            "planned_agents": self.planned_agents,
            "final_agents": self.final_agents,
            "initial_gap": self.initial_gap,
            "final_gap": self.final_gap,
            "achieved_sl_initial": self.achieved_sl_initial,
            "achieved_sl_final": self.achieved_sl_final,
            "outcome": self.outcome.value,
        }


@dataclass(frozen=True)
class BalanceRecommendation:
    """Output of balance() — full plan."""
    recommendation_id: str
    channels: Tuple[ChannelOutcome, ...]
    shifts: Tuple[AgentShift, ...]
    n_unresolved_shortages: int
    n_partial_shortages: int
    n_resolved_shortages: int
    created_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "recommendation_id": self.recommendation_id,
            "channels": [c.to_dict() for c in self.channels],
            "shifts": [s.to_dict() for s in self.shifts],
            "n_unresolved_shortages": self.n_unresolved_shortages,
            "n_partial_shortages": self.n_partial_shortages,
            "n_resolved_shortages": self.n_resolved_shortages,
            "created_at": self.created_at.isoformat(),
        }


class CrossChannelBalancingEngine:
    """In-memory greedy balancer."""

    def __init__(self, tsl_engine: TSLOptimizationEngine):
        if tsl_engine is None:
            raise ValueError("tsl_engine required")
        self._tsl = tsl_engine
        self._recommendations: Dict[str, BalanceRecommendation] = {}
        self._counter = 0

    # ─── core algorithm ────────────────────────────────────────
    def balance(
        self, channels: List[ChannelInput]
    ) -> BalanceRecommendation:
        """Greedy rebalance: pull from surpluses to shortages
        respecting transferability."""
        if not channels:
            raise ValueError("channels list cannot be empty")

        # Detect duplicate channel keys
        seen = set()
        for ch in channels:
            if ch.channel_key in seen:
                raise ValueError(
                    f"duplicate channel_key: {ch.channel_key}")
            seen.add(ch.channel_key)

        # Step 1 — compute required per channel via ENH-158 math
        per_channel: Dict[str, Dict[str, Any]] = {}
        for ch in channels:
            target = self._tsl.get_target(ch.channel_key)
            if target is None:
                raise ValueError(
                    f"no TSL target set for {ch.channel_key} — "
                    f"set via TSLOptimizationEngine first")
            req = required_agents(
                arrivals_per_hour=ch.forecast_arrivals_per_hour,
                aht_seconds=target.aht_seconds,
                target_pct=target.target_pct,
                threshold_seconds=target.threshold_seconds,
            )
            traffic = (
                ch.forecast_arrivals_per_hour * target.aht_seconds
                / 3600.0)
            sl_initial = service_level(
                traffic, ch.planned_agents,
                target.aht_seconds, target.threshold_seconds)
            per_channel[ch.channel_key] = {
                "input": ch,
                "target": target,
                "traffic": traffic,
                "required": req,
                "current_agents": ch.planned_agents,
                "sl_initial": sl_initial,
            }

        # Step 2 — identify shortages (sorted by gap descending)
        # and surpluses (sorted by surplus descending)
        shortages = sorted(
            [k for k, v in per_channel.items()
             if v["current_agents"] < v["required"]],
            key=lambda k: per_channel[k]["required"] - per_channel[k]["current_agents"],
            reverse=True,
        )
        # We re-evaluate surpluses dynamically as shifts happen

        shifts: List[AgentShift] = []

        # Step 3 — greedy fill
        for sk in shortages:
            sv = per_channel[sk]
            while sv["current_agents"] < sv["required"]:
                # Find surplus channel willing & able to give
                donor_key = self._find_donor(per_channel, sk)
                if donor_key is None:
                    break
                shifts.append(AgentShift(
                    from_channel=donor_key,
                    to_channel=sk,
                    n_agents=1,
                    rationale=(
                        f"{donor_key} surplus → {sk} shortage; "
                        f"transferable per channel input"),
                ))
                per_channel[donor_key]["current_agents"] -= 1
                per_channel[sk]["current_agents"] += 1

        # Step 4 — coalesce 1-by-1 shifts into batched shifts
        coalesced = self._coalesce_shifts(shifts)

        # Step 5 — build outcomes
        outcomes = []
        n_resolved = n_partial = n_unresolved = 0
        for k, v in per_channel.items():
            initial_planned = v["input"].planned_agents
            final = v["current_agents"]
            req = v["required"]
            init_gap = req - initial_planned
            fin_gap = req - final
            sl_final = service_level(
                v["traffic"], final,
                v["target"].aht_seconds,
                v["target"].threshold_seconds)
            # Outcome classification
            if init_gap > 0 and fin_gap <= 0:
                outcome = BalanceOutcome.SHORTAGE_RESOLVED
                n_resolved += 1
            elif init_gap > 0 and 0 < fin_gap < init_gap:
                outcome = BalanceOutcome.SHORTAGE_PARTIAL
                n_partial += 1
            elif init_gap > 0 and fin_gap >= init_gap:
                outcome = BalanceOutcome.SHORTAGE_UNRESOLVED
                n_unresolved += 1
            elif final < initial_planned:
                outcome = BalanceOutcome.SURPLUS_GIVING
            else:
                outcome = BalanceOutcome.BALANCED
            outcomes.append(ChannelOutcome(
                channel_key=k,
                required_agents=req,
                planned_agents=initial_planned,
                final_agents=final,
                initial_gap=init_gap,
                final_gap=fin_gap,
                achieved_sl_initial=v["sl_initial"],
                achieved_sl_final=sl_final,
                outcome=outcome,
            ))

        self._counter += 1
        rec_id = f"BAL-{self._counter:06d}"
        rec = BalanceRecommendation(
            recommendation_id=rec_id,
            channels=tuple(outcomes),
            shifts=tuple(coalesced),
            n_unresolved_shortages=n_unresolved,
            n_partial_shortages=n_partial,
            n_resolved_shortages=n_resolved,
        )
        self._recommendations[rec_id] = rec
        return rec

    # ─── helpers ───────────────────────────────────────────────
    def _find_donor(
        self,
        per_channel: Dict[str, Dict[str, Any]],
        recipient_key: str,
    ) -> Optional[str]:
        """Find a channel willing to give 1 agent — must have
        surplus AND list recipient in its transferable_to."""
        candidates = []
        for k, v in per_channel.items():
            if k == recipient_key:
                continue
            ch_input: ChannelInput = v["input"]
            # Transferability gate
            if recipient_key not in ch_input.transferable_to:
                continue
            # Surplus check (after giving 1)
            after_giving = v["current_agents"] - 1
            if after_giving < ch_input.min_agents_after_giving:
                continue
            if after_giving < v["required"]:
                # Donor would itself become short
                continue
            # Bigger surplus = better donor (greedy)
            surplus_after = after_giving - v["required"]
            candidates.append((surplus_after, k))
        if not candidates:
            return None
        candidates.sort(reverse=True)
        return candidates[0][1]

    @staticmethod
    def _coalesce_shifts(
        shifts: List[AgentShift]
    ) -> List[AgentShift]:
        """Merge consecutive identical from→to shifts."""
        if not shifts:
            return []
        merged: Dict[Tuple[str, str], int] = {}
        rationales: Dict[Tuple[str, str], str] = {}
        for s in shifts:
            key = (s.from_channel, s.to_channel)
            merged[key] = merged.get(key, 0) + s.n_agents
            rationales[key] = s.rationale  # last one wins (same str)
        return [
            AgentShift(
                from_channel=k[0], to_channel=k[1],
                n_agents=v, rationale=rationales[k])
            for k, v in merged.items()
        ]

    # ─── queries ───────────────────────────────────────────────
    def get_recommendation(
        self, recommendation_id: str
    ) -> Optional[BalanceRecommendation]:
        return self._recommendations.get(recommendation_id)

    def list_recommendations(
        self
    ) -> List[BalanceRecommendation]:
        return sorted(self._recommendations.values(),
                       key=lambda r: r.created_at)

    # ─── board ─────────────────────────────────────────────────
    def board_summary(self) -> Dict[str, Any]:
        recs = list(self._recommendations.values())
        n = len(recs)
        unresolved_total = sum(
            r.n_unresolved_shortages for r in recs)
        resolved_total = sum(
            r.n_resolved_shortages for r in recs)
        return {
            "engine": "ENH-159 CrossChannelBalancingEngine",
            "n_recommendations": n,
            "shortages_resolved_lifetime": resolved_total,
            "shortages_unresolved_lifetime": unresolved_total,
            "regulatory_basis": (
                "Internal Workforce Management Framework + "
                "BSC People+Customer perspectives + CBK "
                "Operational Risk Guidelines §6.4"),
            "algorithm": "greedy shortage-first heuristic",
            "deferrals": {
                "REAL_TIME_SKILLS_MATRIX": (
                    "DEFERRED — caller declares transferable_to "
                    "explicitly; no HRIS skills feed integrated"),
                "AUTO_REBALANCE_TRIGGER": (
                    "DEFERRED — caller invokes balance() "
                    "manually; no scheduler"),
                "COST_OPTIMIZED_LP_SOLVER": (
                    "DEFERRED — greedy heuristic only; no LP/"
                    "MILP optimisation across cost+SL+shift "
                    "constraints"),
                "SKILL_DECAY_MODEL": (
                    "DEFERRED — no model of skill atrophy when "
                    "moved from primary channel"),
            },
        }
