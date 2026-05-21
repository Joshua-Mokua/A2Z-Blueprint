"""Integration tests for v10.357 — Virtual Bank Readiness Audit.

Reconnaissance batch. The audit module probes the existing virtual-bank
infrastructure (built up over v10.30-v10.314+) and produces a structured
readiness report consumed by v10.358+ work.

14 tests across 5 sections:
  Section 1 — Module + schema (3 tests)
  Section 2 — Individual probes (4 tests)
  Section 3 — Synthesis + reporting (3 tests)
  Section 4 — Save/load + schema validation (2 tests)
  Section 5 — G243 gate (2 tests)
"""

import json
import sys
from pathlib import Path

REPO = Path("/tmp/a2z_fix")
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


def _reimport(prefix):
    for k in list(sys.modules):
        if k.startswith(prefix):
            del sys.modules[k]


# ────────────────────────────────────────────────────────────────────
# Section 1 — Module + schema
# ────────────────────────────────────────────────────────────────────

def test_v10357_readiness_module_present():
    path = REPO / "utils" / "virtual_bank_readiness.py"
    assert path.exists()
    text = path.read_text()
    for sym in (
        "def capture_readiness_report",
        "def save_readiness_report",
        "def format_readiness_summary",
        "SIMULATOR_MODULES",
        "class ReadinessReport",
        "class FootballTeamChain",
    ):
        assert sym in text, f"Missing: {sym}"


def test_v10357_schema_registered():
    schema_path = REPO / "data" / "_schemas" / "virtual_bank_readiness.schema.json"
    assert schema_path.exists()
    schema = json.loads(schema_path.read_text())
    assert schema["title"] == "Virtual Bank Readiness Report"
    required = set(schema["required"])
    assert {"modules", "boot", "coverage", "scenarios", "chain", "overall_status"}.issubset(required)


def test_v10357_eight_modules_probed():
    """The simulator module list must cover all 8 virtual-bank-adjacent modules."""
    _reimport("utils.virtual_bank_readiness")
    from utils.virtual_bank_readiness import SIMULATOR_MODULES
    expected = {
        "utils.virtual_bank",
        "utils.virtual_bank_core",
        "utils.virtual_bank_simulator",
        "utils.scenario_simulator",
        "utils.stress_testing",
        "utils.strategy_simulator",
        "utils.hybrid_scheduling_simulator",
        "utils.liquidity_stress",
    }
    assert set(SIMULATOR_MODULES) == expected


# ────────────────────────────────────────────────────────────────────
# Section 2 — Individual probes
# ────────────────────────────────────────────────────────────────────

def test_v10357_all_modules_load():
    """All 8 simulator modules must load cleanly."""
    _reimport("utils.virtual_bank_readiness")
    from utils.virtual_bank_readiness import _probe_module, SIMULATOR_MODULES
    for m in SIMULATOR_MODULES:
        probe = _probe_module(m)
        assert probe.loaded, f"{m} fails to load: {probe.error}"


def test_v10357_all_self_tests_pass():
    """Every module with a self_test must pass it."""
    _reimport("utils.virtual_bank_readiness")
    from utils.virtual_bank_readiness import _probe_module, SIMULATOR_MODULES
    failures = []
    for m in SIMULATOR_MODULES:
        probe = _probe_module(m)
        if probe.has_self_test and probe.self_test_passed is False:
            failures.append((m, probe.error))
    assert not failures, f"Self-test failures: {failures}"


def test_v10357_boot_probe_runs_5_day_sim():
    _reimport("utils.virtual_bank_readiness")
    from utils.virtual_bank_readiness import _probe_boot
    probe = _probe_boot()
    assert probe.error is None, f"Boot probe error: {probe.error}"
    assert probe.bank_instantiated
    assert probe.simulator_instantiated
    assert probe.run_configured
    assert probe.run_executed


def test_v10357_scenarios_sample_runs():
    _reimport("utils.virtual_bank_readiness")
    from utils.virtual_bank_readiness import _probe_scenarios
    probe = _probe_scenarios()
    assert probe.error is None, f"Scenarios probe error: {probe.error}"
    assert probe.scenarios_attempted == 4
    assert probe.scenarios_passed == 4


# ────────────────────────────────────────────────────────────────────
# Section 3 — Synthesis + reporting
# ────────────────────────────────────────────────────────────────────

def test_v10357_capture_returns_complete_report():
    _reimport("utils.virtual_bank_readiness")
    from utils.virtual_bank_readiness import capture_readiness_report
    r = capture_readiness_report()
    assert r.captured_at, "captured_at must be set"
    assert len(r.modules) == 8
    assert r.overall_status in ("READY", "READY_BUT_NOT_VERIFIED", "BLOCKERS", "UNKNOWN")


def test_v10357_chain_has_seven_links():
    _reimport("utils.virtual_bank_readiness")
    from utils.virtual_bank_readiness import _probe_chain
    chain = _probe_chain()
    # All 7 links should have a status, not be UNKNOWN
    link_fields = [
        chain.teller_action_to_cbs,
        chain.cbs_to_actuals_engine,
        chain.actuals_engine_to_yoy_sidecar,
        chain.yoy_sidecar_to_bsc_display,
        chain.bsc_to_branch_score,
        chain.branch_to_regional_rollup,
        chain.regional_to_md_tile,
    ]
    for status in link_fields:
        assert status in ("WIRED", "PARTIAL", "MISSING"), f"Unexpected status: {status}"


def test_v10357_format_summary_includes_chain_section():
    _reimport("utils.virtual_bank_readiness")
    from utils.virtual_bank_readiness import capture_readiness_report, format_readiness_summary
    r = capture_readiness_report()
    text = format_readiness_summary(r)
    assert "Football Team Test chain:" in text
    assert "teller → CBS" in text
    assert "regional → MD tile" in text
    assert "End-to-end verified:" in text


# ────────────────────────────────────────────────────────────────────
# Section 4 — Save/load
# ────────────────────────────────────────────────────────────────────

def test_v10357_save_writes_canonical_path(tmp_path):
    _reimport("utils.virtual_bank_readiness")
    from utils.virtual_bank_readiness import capture_readiness_report, save_readiness_report
    r = capture_readiness_report()
    p = tmp_path / "vbr.json"
    saved = save_readiness_report(r, path=p)
    assert saved == p
    assert p.exists()
    data = json.loads(p.read_text())
    assert data["_schema_version"] == "1.0"
    assert "modules" in data
    assert "chain" in data


def test_v10357_canonical_readiness_validates():
    """The shipped canonical readiness JSON validates against schema."""
    _reimport("utils.schema_validator")
    from utils.schema_validator import validate_file
    r = validate_file("virtual_bank_readiness.json")
    assert r.get("valid"), f"Validation errors: {r.get('errors', [])[:3]}"


# ────────────────────────────────────────────────────────────────────
# Section 5 — G243 gate
# ────────────────────────────────────────────────────────────────────

def test_v10357_g243_gate_passes():
    sys.path.insert(0, str(REPO / "scripts"))
    _reimport("audit")
    from audit import gate_virtual_bank_readiness
    result = gate_virtual_bank_readiness()
    assert result["passed"], result.get("violations")
    assert result["id"] == "G243"


def test_v10357_g243_in_gates_list():
    text = (REPO / "scripts" / "audit.py").read_text()
    assert '("G243", gate_virtual_bank_readiness)' in text
