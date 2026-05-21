"""Integration tests for v10.471 — Enterprise Discharge Readiness.

Per Joshua doctrine: 'The mission is not partial recovery. The mission is
permanent enterprise vitality, synchronization, resilience, intelligence,
and operational excellence.'

Validates all 10 phases + 32 release-gate items + 8 infrastructure modules.
"""

import json
import sys
from pathlib import Path

import pytest

REPO = Path("/tmp/a2z_fix")
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


# ── 1. ENTERPRISE DISCHARGE AUDIT PASSES ────────────────────────────

def test_v10471_discharge_audit_runs():
    for k in list(sys.modules):
        if 'enterprise_discharge' in k: del sys.modules[k]
    from utils.enterprise_discharge_audit import enterprise_discharge_audit
    a = enterprise_discharge_audit()
    assert a is not None


def test_v10471_discharge_ready_true():
    for k in list(sys.modules):
        if 'enterprise_discharge' in k or 'cascade_bsc_360' in k:
            del sys.modules[k]
    from utils.enterprise_discharge_audit import enterprise_discharge_audit
    a = enterprise_discharge_audit()
    assert a.discharge_ready, f"Blocking: {a.blocking_issues}"


def test_v10471_all_10_phases_above_80():
    for k in list(sys.modules):
        if 'enterprise_discharge' in k or 'cascade_bsc_360' in k:
            del sys.modules[k]
    from utils.enterprise_discharge_audit import enterprise_discharge_audit
    a = enterprise_discharge_audit()
    failing = [(k, p.score_pct) for k, p in a.phases.items()
              if p.score_pct < 80]
    assert not failing, f"Phases below 80%: {failing}"


def test_v10471_all_32_gate_items_pass():
    for k in list(sys.modules):
        if 'enterprise_discharge' in k or 'cascade_bsc_360' in k:
            del sys.modules[k]
    from utils.enterprise_discharge_audit import enterprise_discharge_audit
    a = enterprise_discharge_audit()
    assert a.gate_passed == a.total_gate_items, \
        f"{a.gate_passed}/{a.total_gate_items}"


# ── 2. NEW INFRASTRUCTURE MODULES ───────────────────────────────────

def test_v10471_workflow_engine_module():
    from utils.workflow_engine import (ApplicationState, ALLOWED_TRANSITIONS,
                                       WorkflowState, WorkflowEngine)
    assert ApplicationState.DRAFT.value == "draft"
    assert ApplicationState.SUBMITTED in ALLOWED_TRANSITIONS[ApplicationState.DRAFT]


def test_v10471_workflow_engine_transitions():
    from utils.workflow_engine import (ApplicationState, WorkflowState,
                                       WorkflowEngine)
    engine = WorkflowEngine()
    state = WorkflowState(item_id="TEST001",
                         current_state=ApplicationState.DRAFT)
    ok, msg = engine.transition(state, ApplicationState.SUBMITTED,
                                actor="300011")
    assert ok
    assert state.current_state == ApplicationState.SUBMITTED
    # Illegal transition
    ok, msg = engine.transition(state, ApplicationState.EXECUTED,
                                actor="300011")
    assert not ok


def test_v10471_workflow_engine_rollback():
    from utils.workflow_engine import (ApplicationState, WorkflowState,
                                       WorkflowEngine)
    engine = WorkflowEngine()
    state = WorkflowState(item_id="TEST002",
                         current_state=ApplicationState.DRAFT)
    engine.transition(state, ApplicationState.SUBMITTED, actor="300011")
    ok, msg = engine.rollback(state, actor="300011", reason="test")
    assert ok
    assert state.current_state == ApplicationState.DRAFT


def test_v10471_auth_module():
    from utils.auth import (require_access, has_access, is_admin,
                           get_current_user)
    # Outside Streamlit, get_current_user returns None
    user = get_current_user()
    assert user is None or isinstance(user, dict)


def test_v10471_audit_log_module():
    from utils.audit_log import audit_log, query_audit
    entry_id = audit_log("test_action", "test_actor", "ict",
                         details={"test": True})
    assert entry_id
    # Should be retrievable
    entries = query_audit(actor="test_actor", limit=5)
    assert any(e.get("action") == "test_action" for e in entries)


def test_v10471_notifications_module():
    from utils.notifications import notify, send_email, sms_send
    assert notify("test@x", "subject", "body", channel="inapp") is True
    assert send_email("test@x", "s", "b") is True


def test_v10471_flexcube_adapter_class():
    from utils.flexcube_adapter import FlexcubeAdapter
    adapter = FlexcubeAdapter(mode="synthetic")
    result = adapter.get_customer("100000001")
    assert result is not None
    assert result.get("cif") == "100000001"


# ── 3. INFRASTRUCTURE DOCS ──────────────────────────────────────────

def test_v10471_stress_test_doc():
    p = REPO / "docs" / "stress_test.md"
    assert p.exists()
    text = p.read_text(encoding="utf-8")
    assert "Peak Operational Volumes" in text
    assert "Benchmark Targets" in text


def test_v10471_capacity_plan_doc():
    p = REPO / "docs" / "capacity_plan.md"
    assert p.exists()
    text = p.read_text(encoding="utf-8")
    assert "Horizontal Scale" in text


def test_v10471_per_organ_capacity_plan_docs():
    organs = ("admin", "hr", "bsc_cascade", "credit", "ict", "finance",
              "treasury", "legal", "risk", "compliance", "operations",
              "crm", "reporting_analytics")
    missing = []
    for o in organs:
        if not (REPO / "docs" / f"{o}_capacity_plan.md").exists():
            missing.append(o)
    assert not missing


# ── 4. 100% RBAC COVERAGE ───────────────────────────────────────────

def test_v10471_100pct_pages_have_require_access():
    pages = list((REPO / "pages").glob("*.py"))
    rbac = sum(1 for p in pages
              if "require_access" in p.read_text(encoding="utf-8"))
    pct = rbac / len(pages)
    assert pct >= 0.99, f"RBAC coverage {pct:.1%}"


# ── 5. 100% ENGINES HAVE try/except ─────────────────────────────────

def test_v10471_engines_have_exception_handling():
    engines = list((REPO / "utils").glob("*_engine.py"))
    no_try = [e.name for e in engines
             if "try:" not in e.read_text(encoding="utf-8")]
    assert not no_try


# ── 6. G357 PASSES ──────────────────────────────────────────────────

def test_v10471_g357_passes():
    sys.path.insert(0, str(REPO / "scripts"))
    for k in list(sys.modules):
        if k.startswith("audit"): del sys.modules[k]
    from audit import gate_v10471_enterprise_discharge_ready
    r = gate_v10471_enterprise_discharge_ready()
    assert r["passed"], r.get("violations")


# ── 7. NO REGRESSION (G354, G355, G356) ─────────────────────────────

def test_v10471_g354_still_passes():
    sys.path.insert(0, str(REPO / "scripts"))
    for k in list(sys.modules):
        if k.startswith("audit"): del sys.modules[k]
    from audit import gate_v10468_revival_data_population
    assert gate_v10468_revival_data_population()["passed"]


def test_v10471_g355_still_passes():
    sys.path.insert(0, str(REPO / "scripts"))
    for k in list(sys.modules):
        if k.startswith("audit"): del sys.modules[k]
    from audit import gate_v10469_doctrine_certification
    assert gate_v10469_doctrine_certification()["passed"]


def test_v10471_g356_still_passes():
    sys.path.insert(0, str(REPO / "scripts"))
    for k in list(sys.modules):
        if k.startswith("audit"): del sys.modules[k]
    from audit import gate_v10470_certified_13_organs
    assert gate_v10470_certified_13_organs()["passed"]


def test_v10471_360_harmony_100():
    for k in list(sys.modules):
        if 'cascade_bsc_360' in k: del sys.modules[k]
    from utils.cascade_bsc_360_engine import cascade_bsc_360_audit
    assert cascade_bsc_360_audit().overall_harmony_pct == 100.0


def test_v10471_bsc_rescue_100():
    for k in list(sys.modules):
        if 'bsc_audit_engine' in k: del sys.modules[k]
    from utils.bsc_audit_engine import bsc_full_audit
    assert bsc_full_audit().overall_health_pct == 100.0
