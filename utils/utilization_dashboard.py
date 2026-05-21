"""utils.utilization_dashboard — Real-Time Utilization Dashboard
data engine (ENH-160, v10.184).

Phase 5 Resource Optimization — fifth standard. Produces the
data layer for a manager-facing dashboard showing per-channel
and per-team utilization vs target service levels.

DESIGN CONTRACT
---------------
1. Read-only aggregation — engine takes raw observations
   (agents available, agents busy, observed arrivals/handle
   times) and produces structured dashboard snapshots. It does
   NOT read live telephony — caller is responsible for feeding
   observations.
2. Threshold band classification — utilization is bucketed into
   UNDER_USED / BALANCED / STRETCHED / BREACH against
   configurable thresholds (default 0.50 / 0.85 / 0.95).
3. Privacy on manager view — when a manager_id is passed,
   results are filtered to only that manager's teams.
4. Composes with ENH-156 (work mode), ENH-158 (TSL targets),
   ENH-159 (rebalance recs) when those engines are passed at
   construction. None are required — the dashboard works in
   stand-alone mode with just utilization observations.

REGULATORY BASIS
----------------
- Internal Workforce Management Framework
- BSC People perspective — utilization is a tier-1 KPI
- Data Protection Act 2019 §25 — manager scope-limited
  visibility over their own team's data only

HONEST DEFERRALS
----------------
- REAL_TIME_TELEPHONY_FEED: live ACD/PBX integration deferred —
  caller pushes observations explicitly
- BREAK_TIME_DETECTION: distinguishing "agent away on break"
  from "agent unavailable" deferred — observations report busy
  vs available only
- ADHERENCE_TRACKING: schedule adherence (was the agent logged
  in when scheduled) deferred — engine reports utilization, not
  adherence
- HISTORICAL_TREND_PERSISTENCE: trend analysis across days
  deferred — snapshots stored in-memory, no PG migration
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple


class UtilizationBand(Enum):
    """Threshold bands for utilization rates."""
    UNDER_USED = "under_used"     # < lower threshold
    BALANCED = "balanced"         # lower <= u < upper
    STRETCHED = "stretched"       # upper <= u < breach
    BREACH = "breach"             # u >= breach


# Default thresholds
DEFAULT_LOWER_THRESHOLD = 0.50
DEFAULT_UPPER_THRESHOLD = 0.85
DEFAULT_BREACH_THRESHOLD = 0.95


@dataclass(frozen=True)
class UtilizationObservation:
    """A single observation submitted by the caller."""
    channel_key: str
    team_key: str
    manager_id: str
    agents_available: int
    agents_busy: int
    observed_arrivals_per_hour: Optional[float] = None
    observed_aht_seconds: Optional[float] = None
    observed_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self):
        if not self.channel_key:
            raise ValueError("channel_key required")
        if not self.team_key:
            raise ValueError("team_key required")
        if not self.manager_id:
            raise ValueError("manager_id required")
        if self.agents_available < 0:
            raise ValueError("agents_available must be >= 0")
        if self.agents_busy < 0:
            raise ValueError("agents_busy must be >= 0")
        if self.agents_busy > self.agents_available:
            raise ValueError(
                f"agents_busy ({self.agents_busy}) > "
                f"agents_available ({self.agents_available})")


@dataclass(frozen=True)
class UtilizationSnapshot:
    """Per-channel utilization view — output of the dashboard."""
    snapshot_id: str
    channel_key: str
    team_key: str
    manager_id: str
    agents_available: int
    agents_busy: int
    utilization_pct: Optional[float]  # None if available == 0
    band: UtilizationBand
    observed_at: datetime
    target_sl: Optional[float] = None      # from TSL engine
    current_sl: Optional[float] = None     # computed if data avail
    sl_meets_target: Optional[bool] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "snapshot_id": self.snapshot_id,
            "channel_key": self.channel_key,
            "team_key": self.team_key,
            "manager_id": self.manager_id,
            "agents_available": self.agents_available,
            "agents_busy": self.agents_busy,
            "utilization_pct": self.utilization_pct,
            "band": self.band.value,
            "observed_at": self.observed_at.isoformat(),
            "target_sl": self.target_sl,
            "current_sl": self.current_sl,
            "sl_meets_target": self.sl_meets_target,
        }


@dataclass(frozen=True)
class TeamRollup:
    """Per-team aggregation."""
    team_key: str
    manager_id: str
    n_channels: int
    total_agents_available: int
    total_agents_busy: int
    weighted_utilization_pct: Optional[float]
    bands_count: Dict[str, int]   # band value -> count
    n_channels_meeting_target: int
    n_channels_with_target: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "team_key": self.team_key,
            "manager_id": self.manager_id,
            "n_channels": self.n_channels,
            "total_agents_available": self.total_agents_available,
            "total_agents_busy": self.total_agents_busy,
            "weighted_utilization_pct": self.weighted_utilization_pct,
            "bands_count": dict(self.bands_count),
            "n_channels_meeting_target": (
                self.n_channels_meeting_target),
            "n_channels_with_target": self.n_channels_with_target,
        }


def _classify_band(
    utilization: float,
    lower: float = DEFAULT_LOWER_THRESHOLD,
    upper: float = DEFAULT_UPPER_THRESHOLD,
    breach: float = DEFAULT_BREACH_THRESHOLD,
) -> UtilizationBand:
    if utilization < lower:
        return UtilizationBand.UNDER_USED
    if utilization < upper:
        return UtilizationBand.BALANCED
    if utilization < breach:
        return UtilizationBand.STRETCHED
    return UtilizationBand.BREACH


class UtilizationDashboardEngine:
    """In-memory dashboard data layer.

    Composes optionally with a TSLOptimizationEngine for SL
    enrichment. Observations are stored sequentially; snapshots
    are derived deterministically from observations.
    """

    def __init__(
        self,
        tsl_engine=None,
        lower_threshold: float = DEFAULT_LOWER_THRESHOLD,
        upper_threshold: float = DEFAULT_UPPER_THRESHOLD,
        breach_threshold: float = DEFAULT_BREACH_THRESHOLD,
    ):
        if not (0.0 < lower_threshold < upper_threshold
                 < breach_threshold <= 1.0):
            raise ValueError(
                f"thresholds must satisfy 0 < {lower_threshold} "
                f"< {upper_threshold} < {breach_threshold} <= 1")
        self._tsl = tsl_engine
        self._lower = lower_threshold
        self._upper = upper_threshold
        self._breach = breach_threshold
        self._observations: List[UtilizationObservation] = []
        self._snapshots: Dict[str, UtilizationSnapshot] = {}
        self._counter = 0

    # ─── ingest ────────────────────────────────────────────────
    def submit_observation(
        self, observation: UtilizationObservation
    ) -> UtilizationSnapshot:
        """Append observation + derive a snapshot."""
        self._observations.append(observation)

        # Compute utilization
        if observation.agents_available == 0:
            util = None
            band = UtilizationBand.UNDER_USED
        else:
            util = (observation.agents_busy
                     / observation.agents_available)
            band = _classify_band(
                util, self._lower, self._upper, self._breach)

        # Try SL enrichment via TSL engine
        target_sl: Optional[float] = None
        current_sl: Optional[float] = None
        sl_meets: Optional[bool] = None
        if self._tsl is not None:
            target = self._tsl.get_target(observation.channel_key)
            if target is not None:
                target_sl = target.target_pct
                if (observation.observed_arrivals_per_hour is not None
                        and observation.observed_aht_seconds is not None
                        and observation.agents_available > 0):
                    # Late import to avoid cyclic dependency
                    from utils.tsl_optimization import service_level
                    aht = observation.observed_aht_seconds
                    if aht > 0:
                        traffic = (
                            observation.observed_arrivals_per_hour
                            * aht / 3600.0)
                        current_sl = service_level(
                            traffic, observation.agents_available,
                            aht, target.threshold_seconds)
                        sl_meets = current_sl >= target_sl

        self._counter += 1
        snap_id = f"UTL-{self._counter:06d}"
        snap = UtilizationSnapshot(
            snapshot_id=snap_id,
            channel_key=observation.channel_key,
            team_key=observation.team_key,
            manager_id=observation.manager_id,
            agents_available=observation.agents_available,
            agents_busy=observation.agents_busy,
            utilization_pct=util,
            band=band,
            observed_at=observation.observed_at,
            target_sl=target_sl,
            current_sl=current_sl,
            sl_meets_target=sl_meets,
        )
        self._snapshots[snap_id] = snap
        return snap

    # ─── queries ───────────────────────────────────────────────
    def list_snapshots(
        self,
        manager_id: Optional[str] = None,
        team_key: Optional[str] = None,
        channel_key: Optional[str] = None,
    ) -> List[UtilizationSnapshot]:
        """Privacy-aware filter. If manager_id is passed, only
        snapshots whose manager_id matches are returned."""
        out = list(self._snapshots.values())
        if manager_id is not None:
            out = [s for s in out if s.manager_id == manager_id]
        if team_key is not None:
            out = [s for s in out if s.team_key == team_key]
        if channel_key is not None:
            out = [s for s in out
                   if s.channel_key == channel_key]
        return sorted(out, key=lambda s: s.observed_at)

    def latest_per_channel(
        self,
        manager_id: Optional[str] = None,
    ) -> List[UtilizationSnapshot]:
        """Most recent snapshot per (channel, team) pair."""
        candidates = self.list_snapshots(manager_id=manager_id)
        latest: Dict[Tuple[str, str], UtilizationSnapshot] = {}
        for s in candidates:
            key = (s.channel_key, s.team_key)
            if (key not in latest
                    or s.observed_at > latest[key].observed_at):
                latest[key] = s
        return sorted(
            latest.values(),
            key=lambda s: (s.team_key, s.channel_key))

    # ─── team rollup ───────────────────────────────────────────
    def team_rollup(
        self,
        team_key: str,
        manager_id: Optional[str] = None,
    ) -> TeamRollup:
        """Aggregate latest-per-channel for a team."""
        snaps = [s for s in self.latest_per_channel(
                  manager_id=manager_id)
                 if s.team_key == team_key]

        total_avail = sum(s.agents_available for s in snaps)
        total_busy = sum(s.agents_busy for s in snaps)
        weighted_util: Optional[float] = (
            total_busy / total_avail if total_avail > 0 else None)

        bands_count: Dict[str, int] = {}
        for s in snaps:
            bands_count[s.band.value] = (
                bands_count.get(s.band.value, 0) + 1)

        n_target = sum(1 for s in snaps if s.target_sl is not None)
        n_meeting = sum(
            1 for s in snaps
            if s.sl_meets_target is True)

        manager_id_resolved = (
            snaps[0].manager_id if snaps else (manager_id or ""))

        return TeamRollup(
            team_key=team_key,
            manager_id=manager_id_resolved,
            n_channels=len(snaps),
            total_agents_available=total_avail,
            total_agents_busy=total_busy,
            weighted_utilization_pct=weighted_util,
            bands_count=bands_count,
            n_channels_meeting_target=n_meeting,
            n_channels_with_target=n_target,
        )

    # ─── alerts ────────────────────────────────────────────────
    def list_breaches(
        self,
        manager_id: Optional[str] = None,
    ) -> List[UtilizationSnapshot]:
        """All latest snapshots in BREACH band."""
        latest = self.latest_per_channel(manager_id=manager_id)
        return [s for s in latest
                if s.band == UtilizationBand.BREACH]

    # ─── board ─────────────────────────────────────────────────
    def board_summary(self) -> Dict[str, Any]:
        latest = self.latest_per_channel()
        n_channels = len(latest)
        bands_count: Dict[str, int] = {}
        for s in latest:
            bands_count[s.band.value] = (
                bands_count.get(s.band.value, 0) + 1)

        return {
            "engine": "ENH-160 UtilizationDashboardEngine",
            "n_observations_lifetime": len(self._observations),
            "n_snapshots_lifetime": len(self._snapshots),
            "n_channels_active": n_channels,
            "current_band_distribution": bands_count,
            "thresholds": {
                "lower": self._lower,
                "upper": self._upper,
                "breach": self._breach,
            },
            "tsl_engine_attached": self._tsl is not None,
            "regulatory_basis": (
                "Internal Workforce Management Framework + BSC "
                "People perspective + DPA 2019 §25"),
            "deferrals": {
                "REAL_TIME_TELEPHONY_FEED": (
                    "DEFERRED — caller pushes observations; no "
                    "live ACD/PBX integration"),
                "BREAK_TIME_DETECTION": (
                    "DEFERRED — observations report busy vs "
                    "available only; no break-vs-unavailable "
                    "distinction"),
                "ADHERENCE_TRACKING": (
                    "DEFERRED — engine reports utilization, not "
                    "schedule adherence"),
                "HISTORICAL_TREND_PERSISTENCE": (
                    "DEFERRED — in-memory snapshots; PG "
                    "migration TBD"),
            },
        }
