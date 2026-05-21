"""utils/scenarios/base.py — Scenario framework.

A Scenario is a named, categorised, seedable banking simulation. It
drives traffic through the channel simulators and produces observable
events.
"""

from __future__ import annotations

import hashlib
import random
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional


class ScenarioCategory(str, Enum):
    OPERATIONAL = "operational"
    FRAUD = "fraud"
    OPERATIONAL_RISK = "operational_risk"
    REGULATORY = "regulatory"
    CUSTOMER_BEHAVIOUR = "customer_behaviour"


class ScenarioSeverity(str, Enum):
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class ScenarioContext:
    """State passed to a scenario runner.

    The ``clock`` attribute is the global simulation clock. Scenarios
    that need to control time (e.g. fire at a specific cutoff moment)
    can call ``ctx.clock.set(...)`` or ``ctx.clock.advance(...)``.
    By default the clock is inactive — sim_now() falls through to
    wall-clock UTC and channels behave as before.
    """
    seed: int
    actor: str = "scenario_runner"
    rng: random.Random = field(default_factory=lambda: random.Random())
    started_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    correlation_root: str = ""

    @property
    def clock(self):
        """The global simulation clock (lazy-imported)."""
        from utils.simulation_clock import get_simulation_clock
        return get_simulation_clock()

    def submit_channel(self, channel: str, **kwargs) -> Any:
        """Convenience wrapper that injects the scenario context."""
        from utils.channels import submit_channel
        # Always provide a deterministic seed + actor
        kwargs.setdefault("seed", self.rng.randint(0, 2**31))
        kwargs.setdefault("actor", self.actor)
        if "reference" not in kwargs:
            kwargs["reference"] = (
                f"SCN-{self.correlation_root[:8]}-{int(time.time()*1000) % 10000}"
            )
        return submit_channel(channel, **kwargs)


@dataclass
class ScenarioResult:
    """Result of running a scenario."""
    scenario_name: str
    seed: int
    started_at: str
    ended_at: str
    duration_ms: float
    events_observed: int
    event_types_seen: List[str]
    channel_calls: int
    failures: int
    successes: int
    anomalies_detected: List[Dict[str, Any]] = field(default_factory=list)
    scenario_output: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Scenario:
    """A named banking scenario."""
    name: str
    category: ScenarioCategory
    description: str
    runner: Callable[[ScenarioContext], Dict[str, Any]]
    severity: ScenarioSeverity = ScenarioSeverity.INFO
    tags: List[str] = field(default_factory=list)
    expected_event_types: List[str] = field(default_factory=list)
    realistic_basis: str = ""

    def __post_init__(self):
        if not isinstance(self.category, ScenarioCategory):
            self.category = ScenarioCategory(self.category)
        if not isinstance(self.severity, ScenarioSeverity):
            self.severity = ScenarioSeverity(self.severity)


class ScenarioRunner:
    """Executes scenarios, observes events, returns ScenarioResult."""

    def __init__(self, *, detect_anomalies: bool = True):
        self.detect_anomalies = detect_anomalies

    def run(self, scenario: Scenario, seed: int = 0,
             actor: str = "scenario_runner") -> ScenarioResult:
        """Execute a scenario with the given seed."""
        from utils.event_bus import get_event_bus

        bus = get_event_bus()
        # Snapshot event count before
        before = bus.query(limit=1)
        before_count = bus.count_total()
        correlation_root = hashlib.sha256(
            f"{scenario.name}|{seed}|{time.time()}".encode("utf-8")
        ).hexdigest()[:20]
        ctx = ScenarioContext(
            seed=seed, actor=actor,
            rng=random.Random(seed),
            correlation_root=correlation_root,
        )
        start_t = time.time()

        try:
            output = scenario.runner(ctx) or {}
        except Exception as exc:
            output = {"error": str(exc), "scenario_crashed": True}

        end_t = time.time()
        duration_ms = (end_t - start_t) * 1000.0

        # Capture all events emitted during the scenario by time window
        # (channels generate their own correlation_ids — we observe by when
        # events occurred rather than by an arbitrary correlation chain).
        new_events = bus.query(since=ctx.started_at, limit=10_000)
        # Filter to scenario actor for additional isolation when concurrent
        # scenarios share the event bus; fall back to all-since if filter
        # collapses to zero (legacy scenarios may not set actor).
        actor_scoped = [e for e in new_events if e.actor == ctx.actor]
        if actor_scoped:
            new_events = actor_scoped

        observed = len(new_events) or (bus.count_total() - before_count)
        event_types = sorted({e.event_type for e in new_events})
        channel_calls = sum(
            1 for e in new_events if "integration." in e.event_type
            and e.event_type.endswith(".call")
        )
        failures = sum(
            1 for e in new_events if e.event_type.endswith(".failure")
        )
        successes = sum(
            1 for e in new_events if e.event_type.endswith(".success")
        )

        anomalies = []
        if self.detect_anomalies:
            try:
                from utils.anomaly_observer import detect_anomalies
                anomalies = detect_anomalies(window_seconds=300)
            except Exception:
                pass

        return ScenarioResult(
            scenario_name=scenario.name,
            seed=seed,
            started_at=ctx.started_at,
            ended_at=datetime.now(timezone.utc).isoformat(),
            duration_ms=duration_ms,
            events_observed=observed,
            event_types_seen=event_types,
            channel_calls=channel_calls,
            failures=failures,
            successes=successes,
            anomalies_detected=anomalies,
            scenario_output=output,
        )


__all__ = [
    "Scenario", "ScenarioCategory", "ScenarioSeverity",
    "ScenarioContext", "ScenarioResult", "ScenarioRunner",
]
