"""utils/scenarios/registry.py — All 100 scenarios consolidated."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from utils.scenarios.base import (
    Scenario, ScenarioCategory, ScenarioSeverity, ScenarioResult, ScenarioRunner,
)
from utils.scenarios.operational import OPERATIONAL_SCENARIOS
from utils.scenarios.fraud import FRAUD_SCENARIOS
from utils.scenarios.operational_risk import OPRISK_SCENARIOS
from utils.scenarios.regulatory import REGULATORY_SCENARIOS
from utils.scenarios.customer_behaviour import CUSTOMER_SCENARIOS


SCENARIOS: List[Scenario] = (
    OPERATIONAL_SCENARIOS
    + FRAUD_SCENARIOS
    + OPRISK_SCENARIOS
    + REGULATORY_SCENARIOS
    + CUSTOMER_SCENARIOS
)


_SCENARIO_INDEX: Dict[str, Scenario] = {s.name: s for s in SCENARIOS}


def get_scenario(name: str) -> Optional[Scenario]:
    """Look up a scenario by name."""
    return _SCENARIO_INDEX.get(name)


def list_scenarios() -> List[str]:
    """Return all 100+ scenario names in registration order."""
    return [s.name for s in SCENARIOS]


def list_categories() -> List[str]:
    """Return all category labels."""
    return [c.value for c in ScenarioCategory]


def scenarios_by_category(category: str) -> List[Scenario]:
    """Filter scenarios by category."""
    target = category.lower()
    return [s for s in SCENARIOS if s.category.value == target]


def scenarios_by_severity(severity: str) -> List[Scenario]:
    """Filter scenarios by severity."""
    target = severity.lower()
    return [s for s in SCENARIOS if s.severity.value == target]


def scenarios_by_tag(tag: str) -> List[Scenario]:
    """Filter scenarios that include `tag` in their tags."""
    return [s for s in SCENARIOS if tag in s.tags]


def run_scenario(name: str, *, seed: int = 42,
                  actor: str = "scenario_runner",
                  detect_anomalies: bool = False) -> ScenarioResult:
    """Look up a scenario by name and run it."""
    sc = get_scenario(name)
    if sc is None:
        raise ValueError(
            f"unknown scenario {name!r}. Available: see list_scenarios()"
        )
    runner = ScenarioRunner(detect_anomalies=detect_anomalies)
    return runner.run(sc, seed=seed, actor=actor)


__all__ = [
    "SCENARIOS", "get_scenario", "list_scenarios", "list_categories",
    "scenarios_by_category", "scenarios_by_severity", "scenarios_by_tag",
    "run_scenario",
]
