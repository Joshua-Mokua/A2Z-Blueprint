"""utils.executive_resource_dashboard — Executive Resource
Optimization Dashboard (ENH-165, v10.189).

Phase 5 Resource Optimization — TENTH and final arc standard.
Capstone aggregation engine that composes data from the prior
9 arc engines (ENH-156..164) into a single board-level
read-only snapshot.

DESIGN CONTRACT
---------------
1. **Aggregation only.** This engine reads the public methods
   of the upstream engines. It NEVER mutates them.
2. **Graceful degradation.** Every engine is optional at
   construction. If an engine is not attached, its dashboard
   section is `None`, not fabricated data, and the snapshot
   notes which engines were unavailable.
3. **Snapshot-in-time semantics.** Calling `snapshot()` returns
   the current state at that instant. The engine does NOT cache
   or stream — the operator calls again to refresh.
4. **Composite health index is transparent.** The
   `resource_optimization_health_index` (0–100) is a weighted
   composite of available sub-indices. Weights and the
   contributing components are surfaced on every snapshot so
   the math is auditable. If too few signals are available, the
   composite returns `None`, not a guess.
5. **No drill-down, no nav, no UI.** That belongs to the
   cockpit which lands at arc closure (v10.190). This engine
   produces data only.

REGULATORY BASIS
----------------
- BSC all four perspectives (Financial, Customer, People,
  Internal Process)
- CBK Prudential Guideline CBK/PG/01 (governance — board MIS)

HONEST DEFERRALS
----------------
- REAL_TIME_REFRESH: snapshot at call time only; no streaming
  or push notifications
- DRILL_DOWN_NAVIGATION: engine produces aggregated data;
  team-level navigation lives in the cockpit UI
- PREDICTIVE_FORECAST_OVERLAY: each upstream engine produces its
  own outlook; the dashboard does not blend or re-forecast
- CUSTOM_KPI_DEFINITIONS: KPIs are fixed; operator can extend
  via the cockpit by combining other module dashboards
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple


# Composite health-index weights — must sum to 1.0
HEALTH_INDEX_WEIGHTS = {
    "tsl_health": 0.25,            # service-level achievement
    "utilization_health": 0.25,    # capacity vs demand balance
    "wellbeing_health": 0.25,      # team risk bands
    "culture_health": 0.25,        # integrity culture score
}

# Minimum number of available sub-indices to publish a composite
MIN_COMPONENTS_FOR_COMPOSITE = 2


@dataclass(frozen=True)
class DashboardSection:
    """One section of the executive dashboard."""
    section_id: str
    title: str
    available: bool
    payload: Optional[Dict[str, Any]]
    notes: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "section_id": self.section_id,
            "title": self.title,
            "available": self.available,
            "payload": self.payload,
            "notes": self.notes,
        }


@dataclass(frozen=True)
class ExecutiveDashboard:
    """Full snapshot of the executive resource-optimisation view."""
    snapshot_id: str
    sections: Tuple[DashboardSection, ...]
    resource_optimization_health_index: Optional[float]
    health_index_components: Dict[str, float]
    health_index_weights: Dict[str, float]
    n_engines_attached: int
    n_engines_available: int
    snapshot_at: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "snapshot_id": self.snapshot_id,
            "sections": [s.to_dict() for s in self.sections],
            "resource_optimization_health_index": (
                self.resource_optimization_health_index
            ),
            "health_index_components": dict(self.health_index_components),
            "health_index_weights": dict(self.health_index_weights),
            "n_engines_attached": self.n_engines_attached,
            "n_engines_available": self.n_engines_available,
            "snapshot_at": self.snapshot_at,
        }


class ExecutiveResourceDashboard:
    """Capstone aggregator across the Resource Optimization arc.

    All 9 upstream engines are optional. Sections that don't
    have a source engine come back with `available=False`.
    """

    DEFERRALS = (
        "REAL_TIME_REFRESH",
        "DRILL_DOWN_NAVIGATION",
        "PREDICTIVE_FORECAST_OVERLAY",
        "CUSTOM_KPI_DEFINITIONS",
    )

    def __init__(
        self,
        work_mode_engine: Any = None,         # ENH-156
        workload_forecasting_engine: Any = None,  # ENH-157
        tsl_engine: Any = None,               # ENH-158
        balancing_engine: Any = None,         # ENH-159
        utilization_engine: Any = None,       # ENH-160
        wellbeing_engine: Any = None,         # ENH-161
        hybrid_simulator: Any = None,         # ENH-162
        investment_case_engine: Any = None,   # ENH-163
        integrity_culture_engine: Any = None,  # ENH-164
    ):
        self._work_mode = work_mode_engine
        self._forecast = workload_forecasting_engine
        self._tsl = tsl_engine
        self._balance = balancing_engine
        self._util = utilization_engine
        self._wellbeing = wellbeing_engine
        self._hybrid = hybrid_simulator
        self._invest = investment_case_engine
        self._culture = integrity_culture_engine
        self._snapshots: List[ExecutiveDashboard] = []

    # -------------------------------------- section builders

    @staticmethod
    def _safe_call(engine: Any, method: str, default=None):
        """Call engine.method() if available; return default on error.

        Used for graceful degradation when an upstream engine is
        attached but the requested method raises.
        """
        if engine is None:
            return None
        fn = getattr(engine, method, None)
        if fn is None:
            return default
        try:
            return fn()
        except Exception:
            return default

    def _section_work_mode(self) -> DashboardSection:
        if self._work_mode is None:
            return DashboardSection(
                section_id="work_mode", title="Work Mode Declarations",
                available=False, payload=None,
                notes="ENH-156 work_mode engine not attached",
            )
        bs = self._safe_call(self._work_mode, "board_summary", {})
        return DashboardSection(
            section_id="work_mode", title="Work Mode Declarations",
            available=bool(bs), payload=bs or None,
            notes="ENH-156",
        )

    def _section_forecast(self) -> DashboardSection:
        if self._forecast is None:
            return DashboardSection(
                section_id="forecast", title="Workload Outlook",
                available=False, payload=None,
                notes="ENH-157 forecasting engine not attached",
            )
        bs = self._safe_call(self._forecast, "board_summary", {})
        return DashboardSection(
            section_id="forecast", title="Workload Outlook",
            available=bool(bs), payload=bs or None,
            notes="ENH-157",
        )

    def _section_tsl(self) -> Tuple[DashboardSection, Optional[float]]:
        if self._tsl is None:
            return (DashboardSection(
                section_id="tsl", title="Service-Level Health",
                available=False, payload=None,
                notes="ENH-158 TSL engine not attached",
            ), None)
        bs = self._safe_call(self._tsl, "board_summary", {})
        # Extract a sub-index 0-100: % of plans with 'exact' outcome
        # ('exact' = staffing meets/exceeds target). Sourced from
        # plans_by_outcome dict.
        sub_index = None
        if bs:
            outcomes = bs.get("plans_by_outcome")
            n_total = bs.get("n_plans", 0)
            if isinstance(outcomes, dict) and n_total > 0:
                n_exact = outcomes.get("exact", 0) + outcomes.get(
                    "on_target", 0)
                sub_index = (n_exact / n_total) * 100.0
        return (DashboardSection(
            section_id="tsl", title="Service-Level Health",
            available=bool(bs), payload=bs or None,
            notes="ENH-158",
        ), sub_index)

    def _section_balancing(self) -> DashboardSection:
        if self._balance is None:
            return DashboardSection(
                section_id="balancing",
                title="Cross-Channel Balancing",
                available=False, payload=None,
                notes="ENH-159 balancing engine not attached",
            )
        bs = self._safe_call(self._balance, "board_summary", {})
        return DashboardSection(
            section_id="balancing",
            title="Cross-Channel Balancing",
            available=bool(bs), payload=bs or None,
            notes="ENH-159",
        )

    def _section_utilization(
        self,
    ) -> Tuple[DashboardSection, Optional[float]]:
        if self._util is None:
            return (DashboardSection(
                section_id="utilization",
                title="Utilisation Health",
                available=False, payload=None,
                notes="ENH-160 utilisation engine not attached",
            ), None)
        bs = self._safe_call(self._util, "board_summary", {})
        sub_index = None
        if bs:
            # ENH-160 emits 'current_band_distribution'; older or
            # alternative engines may emit 'bands_distribution'.
            dist = (bs.get("current_band_distribution")
                    or bs.get("bands_distribution") or {})
            if isinstance(dist, dict) and dist:
                total = sum(dist.values())
                if total > 0:
                    balanced = dist.get("balanced", 0)
                    sub_index = (balanced / total) * 100.0
        return (DashboardSection(
            section_id="utilization",
            title="Utilisation Health",
            available=bool(bs), payload=bs or None,
            notes="ENH-160",
        ), sub_index)

    def _section_wellbeing(
        self,
    ) -> Tuple[DashboardSection, Optional[float]]:
        if self._wellbeing is None:
            return (DashboardSection(
                section_id="wellbeing",
                title="Wellbeing Early-Warning",
                available=False, payload=None,
                notes="ENH-161 wellbeing engine not attached",
            ), None)
        bs = self._safe_call(self._wellbeing, "board_summary", {})
        sub_index = None
        if bs:
            dist = bs.get("bands_distribution", {})
            if isinstance(dist, dict) and dist:
                total = sum(dist.values())
                if total > 0:
                    green = dist.get("green", 0)
                    amber = dist.get("amber", 0)
                    # Green = 100, amber = 50, red = 0 weighted average
                    sub_index = (
                        (green * 100.0 + amber * 50.0) / total
                    )
        return (DashboardSection(
            section_id="wellbeing",
            title="Wellbeing Early-Warning",
            available=bool(bs), payload=bs or None,
            notes="ENH-161",
        ), sub_index)

    def _section_hybrid(self) -> DashboardSection:
        if self._hybrid is None:
            return DashboardSection(
                section_id="hybrid",
                title="What-If Scenario Pipeline",
                available=False, payload=None,
                notes="ENH-162 hybrid simulator not attached",
            )
        bs = self._safe_call(self._hybrid, "board_summary", {})
        return DashboardSection(
            section_id="hybrid",
            title="What-If Scenario Pipeline",
            available=bool(bs), payload=bs or None,
            notes="ENH-162",
        )

    def _section_invest(self) -> DashboardSection:
        if self._invest is None:
            return DashboardSection(
                section_id="invest",
                title="Investment Case Pipeline",
                available=False, payload=None,
                notes="ENH-163 investment engine not attached",
            )
        bs = self._safe_call(self._invest, "board_summary", {})
        return DashboardSection(
            section_id="invest",
            title="Investment Case Pipeline",
            available=bool(bs), payload=bs or None,
            notes="ENH-163",
        )

    def _section_culture(
        self,
    ) -> Tuple[DashboardSection, Optional[float]]:
        if self._culture is None:
            return (DashboardSection(
                section_id="culture",
                title="Integrity Culture Overview",
                available=False, payload=None,
                notes="ENH-164 culture engine not attached",
            ), None)
        bs = self._safe_call(self._culture, "board_summary", {})
        sub_index = None
        if bs:
            dist = bs.get("bands_distribution", {})
            if isinstance(dist, dict) and dist:
                total = sum(dist.values())
                if total > 0:
                    strong = dist.get("strong", 0)
                    developing = dist.get("developing", 0)
                    at_risk = dist.get("at_risk", 0)
                    # Strong = 100, developing = 75, at_risk = 50,
                    # critical = 0
                    sub_index = (
                        (strong * 100.0 + developing * 75.0
                         + at_risk * 50.0) / total
                    )
        return (DashboardSection(
            section_id="culture",
            title="Integrity Culture Overview",
            available=bool(bs), payload=bs or None,
            notes="ENH-164",
        ), sub_index)

    # ------------------------------------------- composite

    @staticmethod
    def _composite_health(components: Dict[str, float]) -> Optional[float]:
        """Weighted composite using HEALTH_INDEX_WEIGHTS.

        Returns None when fewer than MIN_COMPONENTS_FOR_COMPOSITE
        sub-indices are available.
        """
        available = {
            k: v for k, v in components.items() if v is not None
        }
        if len(available) < MIN_COMPONENTS_FOR_COMPOSITE:
            return None
        # Renormalise weights over what's available
        weights_avail = {
            k: HEALTH_INDEX_WEIGHTS[k] for k in available
        }
        total_weight = sum(weights_avail.values())
        if total_weight <= 0:
            return None
        return sum(
            available[k] * weights_avail[k] / total_weight
            for k in available
        )

    # ------------------------------------------ snapshot

    def snapshot(self, snapshot_id: str) -> ExecutiveDashboard:
        if not snapshot_id:
            raise ValueError("snapshot_id required")
        sections: List[DashboardSection] = []

        # Build all sections
        sections.append(self._section_work_mode())
        sections.append(self._section_forecast())
        tsl_sec, tsl_sub = self._section_tsl()
        sections.append(tsl_sec)
        sections.append(self._section_balancing())
        util_sec, util_sub = self._section_utilization()
        sections.append(util_sec)
        well_sec, well_sub = self._section_wellbeing()
        sections.append(well_sec)
        sections.append(self._section_hybrid())
        sections.append(self._section_invest())
        cult_sec, cult_sub = self._section_culture()
        sections.append(cult_sec)

        components = {
            "tsl_health": tsl_sub,
            "utilization_health": util_sub,
            "wellbeing_health": well_sub,
            "culture_health": cult_sub,
        }
        composite = self._composite_health(components)

        n_attached = sum(1 for e in (
            self._work_mode, self._forecast, self._tsl, self._balance,
            self._util, self._wellbeing, self._hybrid, self._invest,
            self._culture,
        ) if e is not None)
        n_available = sum(1 for s in sections if s.available)

        snap = ExecutiveDashboard(
            snapshot_id=snapshot_id,
            sections=tuple(sections),
            resource_optimization_health_index=composite,
            health_index_components={
                k: v for k, v in components.items() if v is not None
            },
            health_index_weights=dict(HEALTH_INDEX_WEIGHTS),
            n_engines_attached=n_attached,
            n_engines_available=n_available,
            snapshot_at=datetime.now(timezone.utc).isoformat(),
        )
        self._snapshots.append(snap)
        return snap

    # -------------------------------------------------- queries

    def list_snapshots(self) -> List[ExecutiveDashboard]:
        return list(self._snapshots)

    # ---------------------------------------------------- meta

    def board_summary(self) -> Dict[str, Any]:
        return {
            "engine": "ENH-165 ExecutiveResourceDashboard",
            "n_snapshots_lifetime": len(self._snapshots),
            "n_engines_attached": sum(1 for e in (
                self._work_mode, self._forecast, self._tsl,
                self._balance, self._util, self._wellbeing,
                self._hybrid, self._invest, self._culture,
            ) if e is not None),
            "health_index_weights": dict(HEALTH_INDEX_WEIGHTS),
            "min_components_for_composite": MIN_COMPONENTS_FOR_COMPOSITE,
            "regulatory_basis": (
                "BSC all four perspectives + "
                "CBK Prudential Guideline CBK/PG/01 (governance)"
            ),
            "deferrals": {
                "REAL_TIME_REFRESH": (
                    "DEFERRED — snapshot at call time only; no "
                    "streaming or push notifications"
                ),
                "DRILL_DOWN_NAVIGATION": (
                    "DEFERRED — aggregation engine produces data; "
                    "team-level nav lives in cockpit UI"
                ),
                "PREDICTIVE_FORECAST_OVERLAY": (
                    "DEFERRED — each upstream engine produces its "
                    "own outlook; dashboard does not re-forecast"
                ),
                "CUSTOM_KPI_DEFINITIONS": (
                    "DEFERRED — KPIs are fixed; cockpit can "
                    "compose with other module dashboards"
                ),
            },
        }
