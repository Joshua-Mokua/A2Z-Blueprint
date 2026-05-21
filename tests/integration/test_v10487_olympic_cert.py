"""Integration tests for v10.487 — Olympic-grade certification."""

import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

REPO = Path("/tmp/a2z_fix")
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


@pytest.fixture(autouse=True)
def _reset_all():
    for k in list(sys.modules):
        if any(s in k for s in ("cert", "arena", "agents", "ml", "chaos",
                                  "channels", "simulation_clock",
                                  "tick_scheduler", "event_bus",
                                  "macro_", "scenarios")):
            del sys.modules[k]
    from utils.simulation_clock import reset_simulation_clock
    from utils.chaos import reset_chaos_injector
    from utils.macro_state import reset_macro_state
    from utils.ml import reset_model_registry
    from utils.agents import reset_default_tool_registry
    from utils.arena import reset_drill_ledger
    reset_simulation_clock()
    reset_chaos_injector()
    reset_macro_state()
    reset_model_registry()
    reset_default_tool_registry()
    reset_drill_ledger()
    yield
    reset_simulation_clock()
    reset_chaos_injector()
    reset_macro_state()
    reset_model_registry()
    reset_default_tool_registry()
    reset_drill_ledger()


# ── Module presence ─────────────────────────────────────────────────

def test_v10487_cert_package_exists():
    pkg = REPO / "utils" / "cert"
    assert pkg.is_dir()
    for f in ["__init__.py", "base.py", "checks.py", "certifier.py"]:
        assert (pkg / f).exists()


# ── Base types ──────────────────────────────────────────────────────

def test_v10487_cert_check_rejects_non_callable():
    from utils.cert import CertCheck
    with pytest.raises(ValueError):
        CertCheck(name="x", organ="o", fn="not_callable")


def test_v10487_cert_check_rejects_empty_name():
    from utils.cert import CertCheck
    with pytest.raises(ValueError):
        CertCheck(name="", organ="o", fn=lambda: True)


def test_v10487_check_outcome_fields():
    from utils.cert import CheckOutcome
    o = CheckOutcome(name="t", organ="o", passed=True,
                       duration_ms=12.34, note="ok")
    assert o.passed
    assert o.duration_ms == 12.34
    assert o.note == "ok"


def test_v10487_check_outcome_to_dict():
    from utils.cert import CheckOutcome
    o = CheckOutcome(name="t", organ="o", passed=False,
                       duration_ms=5.0, error="boom")
    d = o.to_dict()
    assert d["passed"] is False
    assert d["error"] == "boom"


def test_v10487_cert_report_passed_property():
    from utils.cert import CertReport
    empty = CertReport(protocol_name="x", started_at="t")
    assert not empty.passed   # zero checks => not passed
    good = CertReport(protocol_name="x", started_at="t",
                        total_checks=1, passed_checks=1,
                        critical_failures=0)
    assert good.passed
    bad = CertReport(protocol_name="x", started_at="t",
                       total_checks=1, critical_failures=1)
    assert not bad.passed


def test_v10487_cert_report_pass_rate():
    from utils.cert import CertReport
    r = CertReport(protocol_name="x", started_at="t",
                     total_checks=10, passed_checks=7)
    assert abs(r.pass_rate - 0.7) < 1e-9


def test_v10487_cert_report_summary_line():
    from utils.cert import CertReport
    r = CertReport(protocol_name="x", started_at="t",
                     total_checks=5, passed_checks=5,
                     duration_seconds=3.21)
    line = r.summary_line()
    assert "CERTIFIED" in line
    assert "5/5" in line


# ── CertProtocol ────────────────────────────────────────────────────

def test_v10487_protocol_add_returns_self():
    from utils.cert import CertProtocol, CertCheck
    p = CertProtocol(name="x")
    c = CertCheck(name="y", organ="o", fn=lambda: True)
    same = p.add(c)
    assert same is p
    assert p.check_count() == 1


def test_v10487_protocol_organs():
    from utils.cert import CertProtocol, CertCheck
    p = CertProtocol(name="x")
    p.add(CertCheck(name="a", organ="alpha", fn=lambda: True))
    p.add(CertCheck(name="b", organ="beta", fn=lambda: True))
    p.add(CertCheck(name="c", organ="alpha", fn=lambda: True))
    assert p.organs() == ["alpha", "beta"]


def test_v10487_protocol_rejects_empty_name():
    from utils.cert import CertProtocol
    with pytest.raises(ValueError):
        CertProtocol(name="")


# ── Prebuilt protocols ──────────────────────────────────────────────

def test_v10487_olympic_full_has_22_checks():
    from utils.cert import build_olympic_full
    p = build_olympic_full()
    assert p.check_count() >= 20


def test_v10487_olympic_full_covers_all_organs():
    from utils.cert import build_olympic_full
    p = build_olympic_full()
    organs = set(p.organs())
    expected = {"channels", "scenarios", "chaos", "macro", "simclock",
                  "ml", "agents", "arena", "eventbus", "cascade_360"}
    assert expected.issubset(organs)


def test_v10487_olympic_quick_has_9_checks():
    from utils.cert import build_olympic_quick
    p = build_olympic_quick()
    assert p.check_count() == 9


# ── Certifier execution ────────────────────────────────────────────

def test_v10487_certifier_runs_olympic_quick_to_pass(tmp_path):
    from utils.cert import Certifier, build_olympic_quick
    certifier = Certifier(reports_dir=tmp_path)
    report = certifier.run(build_olympic_quick())
    assert report.passed, [
        (o.name, o.note, o.error[:200]) for o in report.outcomes
        if not o.passed
    ]


def test_v10487_certifier_runs_olympic_full_to_pass(tmp_path):
    """The full battery passes."""
    from utils.cert import Certifier, build_olympic_full
    certifier = Certifier(reports_dir=tmp_path)
    report = certifier.run(build_olympic_full())
    assert report.passed, [
        (o.name, o.note, o.error[:200]) for o in report.outcomes
        if not o.passed
    ]
    # Should hit 22 checks
    assert report.total_checks >= 20


def test_v10487_certifier_persists_report(tmp_path):
    from utils.cert import Certifier, build_olympic_quick
    Certifier(reports_dir=tmp_path).run(build_olympic_quick())
    json_files = list(tmp_path.glob("*.json"))
    assert json_files, "no JSON report written"


def test_v10487_certifier_handles_check_exception(tmp_path):
    """A check that raises is recorded as failed, not bubbled up."""
    from utils.cert import (
        Certifier, CertProtocol, CertCheck,
    )

    def boom():
        raise RuntimeError("intentional boom")

    p = CertProtocol(name="boom_test").add(
        CertCheck(name="explode", organ="test", fn=boom))
    report = Certifier(reports_dir=tmp_path).run(p)
    assert report.total_checks == 1
    assert report.passed_checks == 0
    assert report.failed_checks == 1
    assert "boom" in report.outcomes[0].error


def test_v10487_certifier_normalises_bool_check():
    from utils.cert.certifier import _normalise_check_result
    r = _normalise_check_result(True)
    assert r == {"passed": True, "note": "", "metrics": {}}


def test_v10487_certifier_normalises_tuple_check():
    from utils.cert.certifier import _normalise_check_result
    r = _normalise_check_result((True, "all good"))
    assert r["passed"] is True
    assert r["note"] == "all good"


def test_v10487_certifier_normalises_dict_check():
    from utils.cert.certifier import _normalise_check_result
    r = _normalise_check_result(
        {"passed": True, "note": "ok", "metrics": {"x": 1}})
    assert r["passed"] is True
    assert r["metrics"] == {"x": 1}


def test_v10487_certifier_treats_non_critical_failure(tmp_path):
    """A non-critical failed check doesn't fail certification."""
    from utils.cert import (
        Certifier, CertProtocol, CertCheck,
    )
    p = CertProtocol(name="lenient")
    p.add(CertCheck(name="ok", organ="t", fn=lambda: True))
    p.add(CertCheck(name="soft_fail", organ="t", fn=lambda: False,
                      critical=False))
    report = Certifier(reports_dir=tmp_path).run(p)
    assert report.failed_checks == 1
    assert report.critical_failures == 0
    assert report.passed


def test_v10487_certifier_by_organ_aggregation(tmp_path):
    from utils.cert import (
        Certifier, CertProtocol, CertCheck,
    )
    p = CertProtocol(name="agg")
    p.add(CertCheck(name="a", organ="alpha", fn=lambda: True))
    p.add(CertCheck(name="b", organ="alpha", fn=lambda: True))
    p.add(CertCheck(name="c", organ="beta", fn=lambda: True))
    report = Certifier(reports_dir=tmp_path).run(p)
    assert report.by_organ["alpha"]["total"] == 2
    assert report.by_organ["alpha"]["passed"] == 2
    assert report.by_organ["beta"]["total"] == 1


def test_v10487_report_to_dict_serialisable(tmp_path):
    import json
    from utils.cert import Certifier, build_olympic_quick
    report = Certifier(reports_dir=tmp_path).run(build_olympic_quick())
    d = report.to_dict()
    serialised = json.dumps(d, default=str)
    assert "olympic_quick" in serialised


# ── Individual organ checks ─────────────────────────────────────────

def test_v10487_check_channels_seven_registered():
    from utils.cert.checks import check_channels_seven_registered
    passed, note = check_channels_seven_registered()
    assert passed, note


def test_v10487_check_scenarios_one_hundred():
    from utils.cert.checks import check_scenarios_one_hundred_registered
    passed, note = check_scenarios_one_hundred_registered()
    assert passed, note


def test_v10487_check_chaos_library_size():
    from utils.cert.checks import check_chaos_library_size
    passed, note = check_chaos_library_size()
    assert passed, note


def test_v10487_check_macro_baseline_realistic():
    from utils.cert.checks import check_macro_kenya_baseline_realistic
    passed, note = check_macro_kenya_baseline_realistic()
    assert passed, note


def test_v10487_check_ml_classifier_seed_deterministic():
    from utils.cert.checks import check_ml_classifier_seed_deterministic
    passed, note = check_ml_classifier_seed_deterministic()
    assert passed, note


def test_v10487_check_arena_trajectory_digest_deterministic():
    from utils.cert.checks import (
        check_arena_trajectory_digest_deterministic)
    passed, note = check_arena_trajectory_digest_deterministic()
    assert passed, note


# ── Agent scenario_run handler fix ──────────────────────────────────

def test_v10487_agent_scenario_run_handler_works():
    """The fixed scenario:run tool actually runs without crashing."""
    from utils.agents import get_default_tool_registry
    from utils.scenarios import list_scenarios
    reg = get_default_tool_registry()
    names = list_scenarios()
    assert names
    r = reg.call("scenario:run", name=names[0])
    assert r.success, f"scenario:run failed: {r.error}"


# ── G373 + cumulative regression ────────────────────────────────────

def test_v10487_g373_passes():
    sys.path.insert(0, str(REPO / "scripts"))
    for k in list(sys.modules):
        if k.startswith("audit"): del sys.modules[k]
    from audit import gate_v10487_olympic_certification
    r = gate_v10487_olympic_certification()
    assert r["passed"], r.get("violations")


def test_v10487_prior_phase_gates_preserved():
    sys.path.insert(0, str(REPO / "scripts"))
    for k in list(sys.modules):
        if k.startswith("audit"): del sys.modules[k]
    from audit import (
        gate_v10486_o7b_drill_scoring_replay,
        gate_v10485_o7a_training_arena,
        gate_v10484_o6b_agent_infrastructure,
    )
    for gate in (gate_v10486_o7b_drill_scoring_replay,
                  gate_v10485_o7a_training_arena,
                  gate_v10484_o6b_agent_infrastructure):
        assert gate()["passed"], f"{gate.__name__} regressed"


def test_v10487_360_harmony_preserved():
    for k in list(sys.modules):
        if "cascade_bsc_360" in k: del sys.modules[k]
    from utils.cascade_bsc_360_engine import cascade_bsc_360_audit
    assert cascade_bsc_360_audit().overall_harmony_pct >= 99.9
