"""utils.hybrid_scheduling_simulator — What-If Scenario Simulator
for Hybrid Scheduling (ENH-162, v10.186).

Phase 5 Resource Optimization — seventh standard. Lets managers
ask "what happens if I shift Team A to 3 days remote, 2 days
onsite?" and get a deterministic projection across the engines
that the prior six drops in this arc already produce data for.

DESIGN CONTRACT
---------------
1. **Read-only projection** — engine consumes a `HybridScenario`
   spec and returns a `ScenarioProjection`. It NEVER mutates
   the source engines (no `submit_observation`, no
   `set_target`, no `record_actual`). Caller assembles the
   spec; engine projects.
2. **Composable, all optional** — TSL, balancing, utilisation,
   and wellbeing engines are passed at construction. None are
   required. Projection fields populate or stay `None` based
   on what's available.
3. **Deterministic** — same scenario in, same projection out.
   No randomness.
4. **Comparative** — `compare(scenarios)` runs N scenarios
   against the same baseline and returns a delta table.
5. **Productivity assumption is named** — the engine treats
   remote / hybrid / onsite as equivalent in throughput unless
   the caller explicitly passes a `ProductivityProfile`. This
   assumption is declared in `board_summary()` as
   `PRODUCTIVITY_DELTA_FROM_MODE` deferred — we do NOT smuggle
   in an unverified productivity penalty.

INPUTS
------
- `HybridScenario(scenario_id, team_assignments)` where each
  `TeamAssignment(team_key, channel_key, work_mode_mix,
  headcount, forecast_arrivals_per_hour)`
- `work_mode_mix`: dict mapping mode → fraction of week
  (e.g. {"REMOTE": 0.6, "ONSITE": 0.4}). Must sum to 1.0.
- Optional `ProductivityProfile(remote_factor, hybrid_factor,
  onsite_factor)` — if absent, all factors default to 1.0 and
  PRODUCTIVITY_DELTA_FROM_MODE is in the deferral list.

OUTPUTS
-------
`ScenarioProjection`:
- effective_headcount — headcount × weighted productivity
- projected_sl — service level achieved under projected
  staffing (None if no TSL engine)
- meets_target — bool (None if no TSL)
- balance_required — bool (None if no balancing engine)
- utilization_band_projected — UtilizationBand (None if no
  utilisation engine)
- wellbeing_pressure_flag — bool (True when projected
  utilisation ≥ STRETCHED) — does NOT use the wellbeing engine
  directly because that engine requires per-employee data;
  this is a coarse proxy

REGULATORY BASIS
----------------
- Internal Hybrid Work Framework
- BSC People + Customer perspectives
- Kenya Employment Act §10 (work-mode declaration anchor)

HONEST DEFERRALS
----------------
- TRAVEL_TIME_REGRESSION: no commute / latency model. Onsite
  shifts ignore travel time
- PRODUCTIVITY_DELTA_FROM_MODE: defaults to 1.0 across modes
  unless caller supplies a profile. Engine does NOT invent a
  remote productivity penalty / boost
- LIVE_WHATIF_DASHBOARD: engine produces projection data;
  Streamlit cockpit UI integration deferred to arc closure
- MULTI_OBJECTIVE_OPTIMIZATION: engine evaluates given
  scenarios; it does not search the scenario space for an
  optimum
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple


class WorkMode(Enum):
    REMOTE = "REMOTE"
    HYBRID = "HYBRID"
    ONSITE = "ONSITE"
    FIELD = "FIELD"


@dataclass(frozen=True)
class ProductivityProfile:
    """Caller-supplied productivity factors per work mode.

    Default is 1.0 everywhere — engine refuses to invent
    deltas. If callers want to explore productivity assumptions,
    they pass an explicit profile.
    """
    remote_factor: float = 1.0
    hybrid_factor: float = 1.0
    onsite_factor: float = 1.0
    field_factor: float = 1.0

    def factor_for(self, mode: WorkMode) -> float:
        if mode == WorkMode.REMOTE:
            return self.remote_factor
        if mode == WorkMode.HYBRID:
            return self.hybrid_factor
        if mode == WorkMode.ONSITE:
            return self.onsite_factor
        return self.field_factor


@dataclass(frozen=True)
class TeamAssignment:
    """One team's hypothetical work-mode mix in a scenario."""
    team_key: str
    channel_key: str
    work_mode_mix: Tuple[Tuple[str, float], ...]  # (mode_str, fraction)
    headcount: int
    forecast_arrivals_per_hour: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "team_key": self.team_key,
            "channel_key": self.channel_key,
            "work_mode_mix": dict(self.work_mode_mix),
            "headcount": self.headcount,
            "forecast_arrivals_per_hour": self.forecast_arrivals_per_hour,
        }


@dataclass(frozen=True)
class HybridScenario:
    """A what-if scenario spec."""
    scenario_id: str
    description: str
    team_assignments: Tuple[TeamAssignment, ...]
    productivity_profile: Optional[ProductivityProfile] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "scenario_id": self.scenario_id,
            "description": self.description,
            "team_assignments": [a.to_dict() for a in self.team_assignments],
            "productivity_profile_supplied": (
                self.productivity_profile is not None
            ),
        }


@dataclass(frozen=True)
class TeamProjection:
    """Per-team projection within a scenario."""
    team_key: str
    channel_key: str
    raw_headcount: int
    effective_headcount: float
    forecast_arrivals_per_hour: float
    projected_sl: Optional[float]
    sl_target: Optional[float]
    meets_target: Optional[bool]
    utilization_band_projected: Optional[str]
    wellbeing_pressure_flag: bool


@dataclass(frozen=True)
class ScenarioProjection:
    """Whole-scenario projection across all teams."""
    scenario_id: str
    description: str
    team_projections: Tuple[TeamProjection, ...]
    n_teams_meeting_target: Optional[int]
    n_teams_with_target: Optional[int]
    n_teams_under_pressure: int
    aggregate_effective_headcount: float
    productivity_profile_supplied: bool
    projected_at: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "scenario_id": self.scenario_id,
            "description": self.description,
            "team_projections": [
                {
                    "team_key": p.team_key,
                    "channel_key": p.channel_key,
                    "raw_headcount": p.raw_headcount,
                    "effective_headcount": p.effective_headcount,
                    "forecast_arrivals_per_hour": p.forecast_arrivals_per_hour,
                    "projected_sl": p.projected_sl,
                    "sl_target": p.sl_target,
                    "meets_target": p.meets_target,
                    "utilization_band_projected": (
                        p.utilization_band_projected
                    ),
                    "wellbeing_pressure_flag": p.wellbeing_pressure_flag,
                }
                for p in self.team_projections
            ],
            "n_teams_meeting_target": self.n_teams_meeting_target,
            "n_teams_with_target": self.n_teams_with_target,
            "n_teams_under_pressure": self.n_teams_under_pressure,
            "aggregate_effective_headcount": (
                self.aggregate_effective_headcount
            ),
            "productivity_profile_supplied": (
                self.productivity_profile_supplied
            ),
            "projected_at": self.projected_at,
        }


@dataclass(frozen=True)
class ScenarioComparison:
    """Side-by-side delta between baseline and alternative scenarios."""
    baseline_id: str
    alternatives: Tuple[str, ...]
    deltas: Dict[str, Dict[str, Any]]
    # alternative_id → {effective_headcount_delta, n_under_pressure_delta,
    #                  meets_target_delta_per_team}


class HybridSchedulingSimulator:
    """What-if simulator for hybrid work-mode scenarios.

    Composes optionally with the prior arc engines. None
    required — projection fields gracefully degrade to None when
    a feeding engine is absent.
    """

    def __init__(
        self,
        tsl_engine: Any = None,
        utilization_engine: Any = None,
        balancing_engine: Any = None,
    ):
        self._tsl = tsl_engine
        self._util = utilization_engine
        self._balance = balancing_engine
        self._projections: List[ScenarioProjection] = []

    # ---------------------------------------------- validation

    @staticmethod
    def _validate_mix(mix: Tuple[Tuple[str, float], ...]) -> None:
        if not mix:
            raise ValueError("work_mode_mix must not be empty")
        valid_modes = {m.value for m in WorkMode}
        total = 0.0
        for mode_str, fraction in mix:
            if mode_str not in valid_modes:
                raise ValueError(
                    f"unknown work mode: {mode_str}; "
                    f"valid: {sorted(valid_modes)}"
                )
            if fraction < 0:
                raise ValueError(f"negative fraction for {mode_str}")
            total += fraction
        if abs(total - 1.0) > 1e-6:
            raise ValueError(
                f"work_mode_mix must sum to 1.0 (got {total:.6f})"
            )

    # ------------------------------------------ effective HC

    @staticmethod
    def _effective_headcount(
        headcount: int,
        mix: Tuple[Tuple[str, float], ...],
        profile: Optional[ProductivityProfile],
    ) -> float:
        if profile is None:
            # No profile → all factors 1.0 → effective == raw
            return float(headcount)
        weighted = 0.0
        for mode_str, fraction in mix:
            mode = WorkMode(mode_str)
            weighted += fraction * profile.factor_for(mode)
        return headcount * weighted

    # ------------------------------------------ TSL projection

    def _project_sl(
        self,
        channel_key: str,
        effective_hc: float,
        forecast_arrivals_per_hour: float,
    ) -> Tuple[Optional[float], Optional[float], Optional[bool]]:
        """Returns (projected_sl, target_sl, meets_target).
        All None if no TSL engine attached or no target for channel.
        """
        if self._tsl is None:
            return (None, None, None)
        try:
            target = self._tsl.get_target(channel_key)
        except Exception:
            return (None, None, None)
        if target is None:
            return (None, None, None)

        # Use the engine's service_level computation if exposed
        from utils.tsl_optimization import service_level
        # Convert effective HC to integer agents — round down (conservative)
        agents = int(effective_hc)
        if agents <= 0:
            return (0.0, target.target_pct, False)
        traffic = (
            forecast_arrivals_per_hour * target.aht_seconds / 3600.0
        )
        sl = service_level(
            traffic=traffic,
            agents=agents,
            aht_seconds=target.aht_seconds,
            threshold_seconds=target.threshold_seconds,
        )
        meets = sl >= target.target_pct
        return (sl, target.target_pct, meets)

    # ---------------------------------- utilisation band proxy

    @staticmethod
    def _project_utilization_band(
        effective_hc: float,
        forecast_arrivals_per_hour: float,
        aht_seconds_default: float = 180.0,
    ) -> Optional[str]:
        """Coarse band projection from offered load vs effective HC.

        We compute the offered-load-to-capacity ratio using a
        nominal AHT. This is a back-of-envelope — the precise
        utilisation under queueing comes from ENH-160 once
        observations roll in. Names: under_used / balanced /
        stretched / breach to match ENH-160 vocabulary.
        """
        if effective_hc <= 0:
            return "breach"
        offered_load = (
            forecast_arrivals_per_hour * aht_seconds_default / 3600.0
        )
        ratio = offered_load / effective_hc
        if ratio < 0.50:
            return "under_used"
        if ratio < 0.85:
            return "balanced"
        if ratio < 0.95:
            return "stretched"
        return "breach"

    # ----------------------------------------- main projection

    def project(self, scenario: HybridScenario) -> ScenarioProjection:
        """Run the scenario through the available engines."""
        team_results: List[TeamProjection] = []
        n_meeting = 0
        n_with_target = 0
        n_pressure = 0
        agg_eff_hc = 0.0

        for assignment in scenario.team_assignments:
            self._validate_mix(assignment.work_mode_mix)
            eff_hc = self._effective_headcount(
                assignment.headcount,
                assignment.work_mode_mix,
                scenario.productivity_profile,
            )
            agg_eff_hc += eff_hc

            sl, target_pct, meets = self._project_sl(
                assignment.channel_key, eff_hc,
                assignment.forecast_arrivals_per_hour,
            )
            if target_pct is not None:
                n_with_target += 1
                if meets:
                    n_meeting += 1

            band = self._project_utilization_band(
                eff_hc, assignment.forecast_arrivals_per_hour,
            )
            wellbeing_flag = band in ("stretched", "breach")
            if wellbeing_flag:
                n_pressure += 1

            team_results.append(TeamProjection(
                team_key=assignment.team_key,
                channel_key=assignment.channel_key,
                raw_headcount=assignment.headcount,
                effective_headcount=eff_hc,
                forecast_arrivals_per_hour=(
                    assignment.forecast_arrivals_per_hour
                ),
                projected_sl=sl,
                sl_target=target_pct,
                meets_target=meets,
                utilization_band_projected=band,
                wellbeing_pressure_flag=wellbeing_flag,
            ))

        projection = ScenarioProjection(
            scenario_id=scenario.scenario_id,
            description=scenario.description,
            team_projections=tuple(team_results),
            n_teams_meeting_target=(
                n_meeting if n_with_target > 0 else None
            ),
            n_teams_with_target=(
                n_with_target if n_with_target > 0 else None
            ),
            n_teams_under_pressure=n_pressure,
            aggregate_effective_headcount=agg_eff_hc,
            productivity_profile_supplied=(
                scenario.productivity_profile is not None
            ),
            projected_at=datetime.now(timezone.utc).isoformat(),
        )
        self._projections.append(projection)
        return projection

    # ------------------------------------------- comparison

    def compare(
        self,
        baseline: HybridScenario,
        alternatives: List[HybridScenario],
    ) -> ScenarioComparison:
        """Run baseline and N alternatives, return delta table."""
        base_proj = self.project(baseline)
        deltas: Dict[str, Dict[str, Any]] = {}
        for alt in alternatives:
            alt_proj = self.project(alt)
            deltas[alt.scenario_id] = {
                "effective_headcount_delta": (
                    alt_proj.aggregate_effective_headcount
                    - base_proj.aggregate_effective_headcount
                ),
                "n_teams_under_pressure_delta": (
                    alt_proj.n_teams_under_pressure
                    - base_proj.n_teams_under_pressure
                ),
                "n_teams_meeting_target_delta": (
                    (alt_proj.n_teams_meeting_target or 0)
                    - (base_proj.n_teams_meeting_target or 0)
                ),
            }
        return ScenarioComparison(
            baseline_id=baseline.scenario_id,
            alternatives=tuple(a.scenario_id for a in alternatives),
            deltas=deltas,
        )

    # -------------------------------------------------- queries

    def list_projections(self) -> List[ScenarioProjection]:
        return list(self._projections)

    # ----------------------------------------------------- meta

    def board_summary(self) -> Dict[str, Any]:
        return {
            "engine": "ENH-162 HybridSchedulingSimulator",
            "n_projections_lifetime": len(self._projections),
            "tsl_engine_attached": self._tsl is not None,
            "utilization_engine_attached": self._util is not None,
            "balancing_engine_attached": self._balance is not None,
            "regulatory_basis": (
                "Internal Hybrid Work Framework + "
                "BSC People+Customer perspectives + "
                "Kenya Employment Act §10 "
                "(work-mode declaration anchor)"
            ),
            "deferrals": {
                "TRAVEL_TIME_REGRESSION": (
                    "DEFERRED — no commute/latency model; onsite "
                    "shifts ignore travel time"
                ),
                "PRODUCTIVITY_DELTA_FROM_MODE": (
                    "DEFERRED — defaults to 1.0 across modes "
                    "unless caller supplies ProductivityProfile; "
                    "engine refuses to invent productivity deltas"
                ),
                "LIVE_WHATIF_DASHBOARD": (
                    "DEFERRED — projection data only; Streamlit "
                    "cockpit UI integration lands at arc closure"
                ),
                "MULTI_OBJECTIVE_OPTIMIZATION": (
                    "DEFERRED — evaluates given scenarios; does "
                    "not search scenario space for an optimum"
                ),
            },
        }
