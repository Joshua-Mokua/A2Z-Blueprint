"""Integration tests for v10.479 — Phase O3-C Scenario Library (100 scenarios)."""

import sys
from pathlib import Path

import pytest

REPO = Path("/tmp/a2z_fix")
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


# ── Sub-package structure ───────────────────────────────────────────

def test_v10479_scenarios_package_exists():
    assert (REPO / "utils" / "scenarios").is_dir()
    assert (REPO / "utils" / "scenarios" / "__init__.py").exists()


def test_v10479_5_category_modules_exist():
    for mod in ["operational", "fraud", "operational_risk",
                "regulatory", "customer_behaviour"]:
        assert (REPO / "utils" / "scenarios" / f"{mod}.py").exists()


def test_v10479_base_module_exposes_framework():
    """Verify the public framework symbols are importable."""
    for k in list(sys.modules):
        if "scenarios" in k: del sys.modules[k]
    from utils.scenarios.base import (
        Scenario, ScenarioCategory, ScenarioSeverity,
        ScenarioContext, ScenarioResult, ScenarioRunner,
    )
    # Dataclass fields:
    import dataclasses
    scenario_fields = {f.name for f in dataclasses.fields(Scenario)}
    assert {"name", "category", "runner"}.issubset(scenario_fields)
    # ScenarioRunner is a regular class with .run method
    assert callable(getattr(ScenarioRunner, "run", None))


# ── 100-scenario invariant ──────────────────────────────────────────

def test_v10479_exactly_100_scenarios():
    for k in list(sys.modules):
        if "scenarios" in k: del sys.modules[k]
    from utils.scenarios import SCENARIOS
    assert len(SCENARIOS) == 100


def test_v10479_20_per_category():
    for k in list(sys.modules):
        if "scenarios" in k: del sys.modules[k]
    from utils.scenarios import scenarios_by_category
    for cat in ["operational", "fraud", "operational_risk",
                 "regulatory", "customer_behaviour"]:
        assert len(scenarios_by_category(cat)) == 20, cat


def test_v10479_all_scenario_names_unique():
    for k in list(sys.modules):
        if "scenarios" in k: del sys.modules[k]
    from utils.scenarios import SCENARIOS
    names = [s.name for s in SCENARIOS]
    assert len(set(names)) == len(names)


def test_v10479_all_scenarios_have_realistic_basis():
    for k in list(sys.modules):
        if "scenarios" in k: del sys.modules[k]
    from utils.scenarios import SCENARIOS
    missing = [s.name for s in SCENARIOS
                if not (s.realistic_basis or "").strip()]
    assert not missing, f"missing realistic_basis: {missing[:5]}"


def test_v10479_all_scenarios_have_tags():
    for k in list(sys.modules):
        if "scenarios" in k: del sys.modules[k]
    from utils.scenarios import SCENARIOS
    missing = [s.name for s in SCENARIOS if not s.tags]
    assert not missing, f"missing tags: {missing[:5]}"


# ── Lookup APIs ─────────────────────────────────────────────────────

def test_v10479_get_scenario_by_name():
    for k in list(sys.modules):
        if "scenarios" in k: del sys.modules[k]
    from utils.scenarios import SCENARIOS, get_scenario
    first = SCENARIOS[0]
    assert get_scenario(first.name).name == first.name


def test_v10479_list_scenarios_returns_100():
    for k in list(sys.modules):
        if "scenarios" in k: del sys.modules[k]
    from utils.scenarios import list_scenarios
    assert len(list_scenarios()) == 100


def test_v10479_list_categories_returns_5():
    for k in list(sys.modules):
        if "scenarios" in k: del sys.modules[k]
    from utils.scenarios import list_categories
    cats = list_categories()
    assert len(cats) == 5
    cat_vals = {c.value if hasattr(c, "value") else str(c) for c in cats}
    assert cat_vals == {"operational", "fraud", "operational_risk",
                          "regulatory", "customer_behaviour"}


def test_v10479_scenarios_by_severity_works():
    for k in list(sys.modules):
        if "scenarios" in k: del sys.modules[k]
    from utils.scenarios import scenarios_by_severity
    total = 0
    for sev in ["info", "low", "medium", "high", "critical"]:
        total += len(scenarios_by_severity(sev))
    assert total == 100


def test_v10479_scenarios_by_tag_works():
    for k in list(sys.modules):
        if "scenarios" in k: del sys.modules[k]
    from utils.scenarios import scenarios_by_tag
    kic_tagged = scenarios_by_tag("kic")
    assert len(kic_tagged) >= 3


# ── ScenarioRunner ──────────────────────────────────────────────────

def test_v10479_runner_returns_scenario_result():
    for k in list(sys.modules):
        if "scenarios" in k or "channels" in k or "event_bus" in k:
            del sys.modules[k]
    from utils.scenarios import SCENARIOS, ScenarioRunner, ScenarioResult
    runner = ScenarioRunner(detect_anomalies=False)
    r = runner.run(SCENARIOS[0], seed=42)
    assert isinstance(r, ScenarioResult)
    assert r.scenario_name == SCENARIOS[0].name
    assert r.seed == 42


def test_v10479_runner_result_has_all_fields():
    for k in list(sys.modules):
        if "scenarios" in k or "channels" in k or "event_bus" in k:
            del sys.modules[k]
    from utils.scenarios import SCENARIOS, ScenarioRunner
    runner = ScenarioRunner(detect_anomalies=False)
    r = runner.run(SCENARIOS[0], seed=42)
    for field in ("scenario_name", "seed", "started_at", "ended_at",
                   "duration_ms", "events_observed", "event_types_seen",
                   "channel_calls", "failures", "successes",
                   "anomalies_detected", "scenario_output"):
        assert hasattr(r, field)


def test_v10479_runner_captures_events_via_time_window():
    for k in list(sys.modules):
        if "scenarios" in k or "channels" in k or "event_bus" in k:
            del sys.modules[k]
    from utils.scenarios import SCENARIOS, ScenarioRunner
    runner = ScenarioRunner(detect_anomalies=False)
    r = runner.run(SCENARIOS[0], seed=42)
    assert r.events_observed > 0
    assert r.channel_calls > 0


def test_v10479_runner_deterministic_with_seed():
    for k in list(sys.modules):
        if "scenarios" in k or "channels" in k: del sys.modules[k]
    from utils.scenarios import SCENARIOS, ScenarioRunner
    runner = ScenarioRunner(detect_anomalies=False)
    r1 = runner.run(SCENARIOS[0], seed=999)
    r2 = runner.run(SCENARIOS[0], seed=999)
    assert r1.channel_calls == r2.channel_calls


# ── One scenario from each category executes successfully ───────────

@pytest.mark.parametrize("category", [
    "operational", "fraud", "operational_risk",
    "regulatory", "customer_behaviour",
])
def test_v10479_category_sample_emits_events(category):
    for k in list(sys.modules):
        if "scenarios" in k or "channels" in k or "event_bus" in k:
            del sys.modules[k]
    from utils.scenarios import scenarios_by_category, ScenarioRunner
    runner = ScenarioRunner(detect_anomalies=False)
    scenario = scenarios_by_category(category)[0]
    r = runner.run(scenario, seed=7)
    assert r.events_observed > 0, f"{category}/{scenario.name} silent"


# ── Run-time correctness ────────────────────────────────────────────

def test_v10479_run_scenario_entry_point():
    for k in list(sys.modules):
        if "scenarios" in k or "channels" in k or "event_bus" in k:
            del sys.modules[k]
    from utils.scenarios import SCENARIOS, run_scenario
    r = run_scenario(SCENARIOS[0].name, seed=42)
    assert r.scenario_name == SCENARIOS[0].name


def test_v10479_scenario_output_dict():
    """Every scenario runner must return a dict (or None)."""
    for k in list(sys.modules):
        if "scenarios" in k or "channels" in k or "event_bus" in k:
            del sys.modules[k]
    from utils.scenarios import SCENARIOS, ScenarioRunner
    runner = ScenarioRunner(detect_anomalies=False)
    samples = [SCENARIOS[i] for i in (0, 10, 20, 35, 50, 65, 75, 85, 95, 99)]
    for s in samples:
        r = runner.run(s, seed=1)
        assert isinstance(r.scenario_output, dict), s.name


# ── Severity / tag distribution sanity ──────────────────────────────

def test_v10479_severity_distribution_has_all_levels():
    for k in list(sys.modules):
        if "scenarios" in k: del sys.modules[k]
    from utils.scenarios import scenarios_by_severity
    for sev in ["info", "low", "medium", "high", "critical"]:
        n = len(scenarios_by_severity(sev))
        assert n >= 1, f"no scenarios at severity {sev}"


def test_v10479_high_severity_scenarios_exist():
    """Phase O3-C must cover serious scenarios (HIGH or CRITICAL)."""
    for k in list(sys.modules):
        if "scenarios" in k: del sys.modules[k]
    from utils.scenarios import scenarios_by_severity
    high = len(scenarios_by_severity("high"))
    crit = len(scenarios_by_severity("critical"))
    assert high + crit >= 30, (
        f"only {high} HIGH + {crit} CRITICAL — too benign"
    )


# ── G365 + cumulative regression ────────────────────────────────────

def test_v10479_g365_passes():
    sys.path.insert(0, str(REPO / "scripts"))
    for k in list(sys.modules):
        if k.startswith("audit"): del sys.modules[k]
    from audit import gate_v10479_o3c_scenario_library
    r = gate_v10479_o3c_scenario_library()
    assert r["passed"], r.get("violations")


def test_v10479_o3a_o3b_channels_still_work():
    sys.path.insert(0, str(REPO / "scripts"))
    for k in list(sys.modules):
        if k.startswith("audit"): del sys.modules[k]
    from audit import (
        gate_v10477_o3a_channel_simulators,
        gate_v10478_o3b_kic_cards_complete_7_channels,
    )
    assert gate_v10477_o3a_channel_simulators()["passed"]
    assert gate_v10478_o3b_kic_cards_complete_7_channels()["passed"]


def test_v10479_o2_telemetry_preserved():
    sys.path.insert(0, str(REPO / "scripts"))
    for k in list(sys.modules):
        if k.startswith("audit"): del sys.modules[k]
    from audit import (
        gate_v10475_o2a_telemetry_lineage_replay,
        gate_v10476_o2b_ai_heatmap_anomaly_telemetry,
    )
    assert gate_v10475_o2a_telemetry_lineage_replay()["passed"]
    assert gate_v10476_o2b_ai_heatmap_anomaly_telemetry()["passed"]


def test_v10479_o8_isolation_preserved():
    sys.path.insert(0, str(REPO / "scripts"))
    for k in list(sys.modules):
        if k.startswith("audit"): del sys.modules[k]
    from audit import gate_v10474_o8_environment_isolation
    assert gate_v10474_o8_environment_isolation()["passed"]


def test_v10479_360_harmony_preserved():
    for k in list(sys.modules):
        if "cascade_bsc_360" in k: del sys.modules[k]
    from utils.cascade_bsc_360_engine import cascade_bsc_360_audit
    assert cascade_bsc_360_audit().overall_harmony_pct >= 99.9
