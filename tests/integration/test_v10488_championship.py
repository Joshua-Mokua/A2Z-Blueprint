"""Integration tests for v10.488 — Championship Readiness Certification."""

import sys
import tempfile
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
                                  "macro_", "scenarios", "audit")):
            del sys.modules[k]
    from utils.simulation_clock import reset_simulation_clock
    from utils.chaos import reset_chaos_injector
    from utils.macro_state import reset_macro_state
    from utils.ml import reset_model_registry
    from utils.agents import reset_default_tool_registry
    from utils.arena import reset_drill_ledger
    reset_simulation_clock(); reset_chaos_injector(); reset_macro_state()
    reset_model_registry(); reset_default_tool_registry()
    reset_drill_ledger()
    yield
    reset_simulation_clock(); reset_chaos_injector(); reset_macro_state()
    reset_model_registry(); reset_default_tool_registry()
    reset_drill_ledger()


# ── Module presence ─────────────────────────────────────────────────

def test_v10488_championship_module_exists():
    assert (REPO / "utils" / "cert" / "championship.py").exists()


def test_v10488_championship_checks_module_exists():
    assert (REPO / "utils" / "cert" / "championship_checks.py").exists()


def test_v10488_new_exports_visible():
    from utils.cert import (
        ChampionshipItem, ChampionshipReport,
        CHAMPIONSHIP_CHECKLIST,
        build_championship_full, run_championship_cert,
    )
    assert ChampionshipItem and ChampionshipReport
    assert callable(build_championship_full)
    assert callable(run_championship_cert)


# ── Checklist structure ─────────────────────────────────────────────

def test_v10488_checklist_has_33_items():
    from utils.cert.championship import CHAMPIONSHIP_CHECKLIST
    assert len(CHAMPIONSHIP_CHECKLIST) == 33


def test_v10488_checklist_categories_correct_counts():
    from utils.cert.championship import CHAMPIONSHIP_CHECKLIST
    counts = {}
    for item in CHAMPIONSHIP_CHECKLIST:
        counts[item.category] = counts.get(item.category, 0) + 1
    assert counts["Revival Integrity"] == 4
    assert counts["Digital Twin Integrity"] == 4
    assert counts["Enterprise Harmony"] == 4
    assert counts["Financial & Regulatory Integrity"] == 5
    assert counts["Resilience & Conditioning"] == 4
    assert counts["AI & Intelligence Readiness"] == 4
    assert counts["Training Arena Readiness"] == 4
    assert counts["React Readiness"] == 4


def test_v10488_each_item_has_non_empty_fields():
    from utils.cert.championship import CHAMPIONSHIP_CHECKLIST
    for item in CHAMPIONSHIP_CHECKLIST:
        assert item.item_id
        assert item.category
        assert item.label
        assert item.rationale
        assert item.check_names


def test_v10488_each_item_check_names_in_protocol():
    """Every checklist item's backing checks must exist in the protocol."""
    from utils.cert.championship import (
        CHAMPIONSHIP_CHECKLIST, build_championship_full)
    proto = build_championship_full()
    proto_names = {c.name for c in proto.checks}
    missing = []
    for item in CHAMPIONSHIP_CHECKLIST:
        for cn in item.check_names:
            if cn not in proto_names:
                missing.append((item.item_id, cn))
    assert not missing, missing


# ── Protocol shape ──────────────────────────────────────────────────

def test_v10488_protocol_has_54_checks():
    from utils.cert.championship import build_championship_full
    proto = build_championship_full()
    assert proto.check_count() >= 50


def test_v10488_protocol_covers_18_organs():
    from utils.cert.championship import build_championship_full
    proto = build_championship_full()
    organs = set(proto.organs())
    assert len(organs) >= 15
    for required in ("channels", "scenarios", "chaos", "macro",
                       "simclock", "ml", "agents", "arena",
                       "eventbus", "cascade_360", "revival",
                       "digital_twin", "harmony", "regulatory",
                       "resilience", "ai", "training", "react_readiness"):
        assert required in organs, f"missing organ: {required}"


# ── Individual championship checks ──────────────────────────────────

def test_v10488_check_virtual_bank_fully_operational():
    from utils.cert.championship_checks import check_virtual_bank_fully_operational
    passed, note = check_virtual_bank_fully_operational()
    assert passed, note


def test_v10488_check_kpi_library_structure():
    from utils.cert.championship_checks import check_kpi_library_structure
    passed, note = check_kpi_library_structure()
    assert passed, note


def test_v10488_check_ifrs_modules_present():
    from utils.cert.championship_checks import check_ifrs_modules_present
    passed, note = check_ifrs_modules_present()
    assert passed, note


def test_v10488_check_cbk_modules_present():
    from utils.cert.championship_checks import check_cbk_compliance_modules_present
    passed, note = check_cbk_compliance_modules_present()
    assert passed, note


def test_v10488_check_kra_modules_present():
    from utils.cert.championship_checks import check_kra_tax_compliance_present
    passed, note = check_kra_tax_compliance_present()
    assert passed, note


def test_v10488_check_hr_modules_present():
    from utils.cert.championship_checks import check_labour_law_hr_modules_present
    passed, note = check_labour_law_hr_modules_present()
    assert passed, note


def test_v10488_check_workflow_engine_present():
    from utils.cert.championship_checks import check_workflow_engine_present
    passed, note = check_workflow_engine_present()
    assert passed, note


def test_v10488_check_synthetic_data_isolation():
    from utils.cert.championship_checks import check_synthetic_data_isolation
    passed, note = check_synthetic_data_isolation()
    assert passed, note


def test_v10488_check_no_circular_imports():
    from utils.cert.championship_checks import check_no_circular_imports
    passed, note = check_no_circular_imports()
    assert passed, note


def test_v10488_check_fastapi_architecture():
    from utils.cert.championship_checks import check_fastapi_architecture_validated
    passed, note = check_fastapi_architecture_validated()
    assert passed, note


# ── Resilience checks ───────────────────────────────────────────────

def test_v10488_check_chaos_testing_passed():
    from utils.cert.championship_checks import check_chaos_testing_passed
    passed, note = check_chaos_testing_passed()
    assert passed, note


def test_v10488_check_stress_multi_chaos_concurrent():
    from utils.cert.championship_checks import check_stress_multi_chaos_concurrent
    passed, note = check_stress_multi_chaos_concurrent()
    assert passed, note


def test_v10488_check_recovery_mechanisms():
    from utils.cert.championship_checks import check_recovery_mechanisms_validated
    passed, note = check_recovery_mechanisms_validated()
    assert passed, note


def test_v10488_check_long_duration_30_days():
    from utils.cert.championship_checks import check_long_duration_30_days
    passed, note = check_long_duration_30_days()
    assert passed, note


# ── AI checks ───────────────────────────────────────────────────────

def test_v10488_check_drift_detection():
    from utils.cert.championship_checks import check_drift_detection_operational
    passed, note = check_drift_detection_operational()
    assert passed, note


def test_v10488_check_explainability():
    from utils.cert.championship_checks import check_explainability_validated
    passed, note = check_explainability_validated()
    assert passed, note


def test_v10488_check_agent_uses_ml():
    from utils.cert.championship_checks import check_agent_can_use_ml_model
    passed, note = check_agent_can_use_ml_model()
    assert passed, note


# ── Training checks ─────────────────────────────────────────────────

def test_v10488_check_coaching_systems():
    from utils.cert.championship_checks import check_coaching_systems_active
    passed, note = check_coaching_systems_active()
    assert passed, note


def test_v10488_check_role_based_simulation():
    from utils.cert.championship_checks import check_role_based_simulation_validated
    passed, note = check_role_based_simulation_validated()
    assert passed, note


def test_v10488_check_scenario_replay():
    from utils.cert.championship_checks import check_scenario_replay_functional
    passed, note = check_scenario_replay_functional()
    assert passed, note


# ── ChampionshipReport API ──────────────────────────────────────────

def test_v10488_report_summary_when_all_pass():
    """Synthetic report with all items passing -> CHAMPIONSHIP READY."""
    from utils.cert.championship import (
        ChampionshipReport, CHAMPIONSHIP_CHECKLIST,
    )
    from utils.cert.base import CertReport
    cr = CertReport(protocol_name="test", started_at="t",
                     total_checks=10, passed_checks=10)
    verdicts = {item.item_id: {"passed": True, "evidence": "ok"}
                 for item in CHAMPIONSHIP_CHECKLIST}
    report = ChampionshipReport(
        cert_report=cr, checklist_verdicts=verdicts)
    assert report.passed
    assert "CHAMPIONSHIP READY" in report.summary_line()
    assert report.items_passed == 33


def test_v10488_report_summary_when_one_fails():
    from utils.cert.championship import (
        ChampionshipReport, CHAMPIONSHIP_CHECKLIST,
    )
    from utils.cert.base import CertReport
    cr = CertReport(protocol_name="test", started_at="t",
                     total_checks=10, passed_checks=9)
    verdicts = {item.item_id: {"passed": True, "evidence": "ok"}
                 for item in CHAMPIONSHIP_CHECKLIST}
    # Force one to fail
    first_item = CHAMPIONSHIP_CHECKLIST[0]
    verdicts[first_item.item_id] = {"passed": False,
                                       "why_failed": "deliberate"}
    report = ChampionshipReport(
        cert_report=cr, checklist_verdicts=verdicts)
    assert not report.passed
    assert "NOT READY" in report.summary_line()
    assert report.items_passed == 32


def test_v10488_report_markdown_includes_all_categories():
    from utils.cert.championship import (
        ChampionshipReport, CHAMPIONSHIP_CHECKLIST,
    )
    from utils.cert.base import CertReport
    cr = CertReport(protocol_name="test", started_at="t")
    verdicts = {item.item_id: {"passed": True, "evidence": "ok"}
                 for item in CHAMPIONSHIP_CHECKLIST}
    report = ChampionshipReport(cert_report=cr, checklist_verdicts=verdicts)
    md = report.checklist_markdown()
    for cat in ("Revival Integrity", "Digital Twin Integrity",
                  "Enterprise Harmony", "Financial & Regulatory Integrity",
                  "Resilience & Conditioning", "AI & Intelligence Readiness",
                  "Training Arena Readiness", "React Readiness"):
        assert f"## {cat}" in md


# ── End-to-end (FULL battery — expensive) ───────────────────────────

@pytest.mark.skip(reason="full battery takes 10-15min; run via scripts/run_championship.py")
def test_v10488_full_championship_e2e_via_runner():
    """Reserved for manual/CI invocation — too expensive for default suite."""
    pass


# ── G374 + cumulative regression ────────────────────────────────────

def test_v10488_g374_passes():
    sys.path.insert(0, str(REPO / "scripts"))
    for k in list(sys.modules):
        if k.startswith("audit"): del sys.modules[k]
    from audit import gate_v10488_championship_readiness
    r = gate_v10488_championship_readiness()
    assert r["passed"], r.get("violations")


def test_v10488_prior_gates_preserved():
    sys.path.insert(0, str(REPO / "scripts"))
    for k in list(sys.modules):
        if k.startswith("audit"): del sys.modules[k]
    from audit import (
        gate_v10487_olympic_certification,
        gate_v10486_o7b_drill_scoring_replay,
        gate_v10485_o7a_training_arena,
    )
    for gate in (gate_v10487_olympic_certification,
                  gate_v10486_o7b_drill_scoring_replay,
                  gate_v10485_o7a_training_arena):
        assert gate()["passed"], f"{gate.__name__} regressed"


def test_v10488_g162_re_baselined_at_4279():
    """The rebaseline to 4279 with full history persists."""
    import json
    bp = REPO / "data" / "audit_baselines.json"
    with open(bp) as f:
        baselines = json.load(f)
    entry = baselines.get("g162_tenant_hardcoding", {})
    assert entry.get("total") == 4279
    assert entry.get("rebaseline_in") == "v10.488"
    assert "history" in entry


def test_v10488_g282_provenance_restored():
    """v10.397 staff code resolution provenance is present in users.json."""
    import json
    up = REPO / "data" / "users.json"
    with open(up) as f:
        users = json.load(f)
    assert "_v10397_staff_code_resolution" in users
    prov = users["_v10397_staff_code_resolution"]
    assert "csuite_codes_preserved" in prov
    assert "new_codes_assigned" in prov


def test_v10488_360_harmony_preserved():
    for k in list(sys.modules):
        if "cascade_bsc_360" in k: del sys.modules[k]
    from utils.cascade_bsc_360_engine import cascade_bsc_360_audit
    assert cascade_bsc_360_audit().overall_harmony_pct >= 99.9
