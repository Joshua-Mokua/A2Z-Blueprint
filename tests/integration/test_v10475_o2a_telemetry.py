"""Integration tests for v10.475 — Phase O2-A Truth, Telemetry & Observability.

Per Joshua Master Prompt Phase O2: every state-changing operation must
be observable, traceable, replayable.
"""

import json
import sys
from pathlib import Path

import pytest

REPO = Path("/tmp/a2z_fix")
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


# ── Event Bus ───────────────────────────────────────────────────────

def test_v10475_event_bus_module_exists():
    assert (REPO / "utils" / "event_bus.py").exists()


def test_v10475_event_bus_singleton():
    for k in list(sys.modules):
        if "event_bus" in k: del sys.modules[k]
    from utils.event_bus import EventBus, get_event_bus
    b1 = get_event_bus()
    b2 = EventBus()
    assert b1 is b2


def test_v10475_emit_persists_to_disk():
    for k in list(sys.modules):
        if "event_bus" in k: del sys.modules[k]
    from utils.event_bus import get_event_bus
    bus = get_event_bus()
    eid = bus.emit(
        event_type="system.event_bus.started",
        actor="test_v10475", entity_id="DISK_TEST_001",
        module="system", payload={"test": True},
    )
    # Read from disk to confirm persistence
    found = bus.query(entity_id="DISK_TEST_001", from_disk=True, limit=5)
    assert any(e.id == eid for e in found)


def test_v10475_emit_rejects_empty_event_type():
    for k in list(sys.modules):
        if "event_bus" in k: del sys.modules[k]
    from utils.event_bus import get_event_bus
    with pytest.raises(ValueError):
        get_event_bus().emit(event_type="", actor="test")


def test_v10475_subscribe_wildcard():
    for k in list(sys.modules):
        if "event_bus" in k: del sys.modules[k]
    from utils.event_bus import get_event_bus
    bus = get_event_bus()
    received = []
    bus.subscribe("workflow.*", lambda e: received.append(e))
    bus.emit(event_type="workflow.transition", actor="sub_test",
             entity_id="SUB_TEST_001", module="credit",
             payload={"from": "draft", "to": "submitted"})
    assert any(e.entity_id == "SUB_TEST_001" for e in received)


def test_v10475_correlation_id_chains_events():
    for k in list(sys.modules):
        if "event_bus" in k: del sys.modules[k]
    from utils.event_bus import get_event_bus
    bus = get_event_bus()
    corr = "test-corr-v10475-chain"
    bus.emit(event_type="workflow.created", actor="chain_test",
             entity_id="CHAIN_001", module="credit", correlation_id=corr)
    bus.emit(event_type="workflow.transition", actor="chain_test",
             entity_id="CHAIN_002", module="credit", correlation_id=corr,
             payload={"from": "draft", "to": "submitted"})
    related = bus.query(correlation_id=corr, limit=10)
    assert len(related) >= 2
    assert all(e.correlation_id == corr for e in related)


def test_v10475_events_jsonl_is_valid_jsonl():
    for k in list(sys.modules):
        if "event_bus" in k: del sys.modules[k]
    from utils.event_bus import EventBus, get_event_bus
    bus = get_event_bus()
    bus.emit(event_type="system.event_bus.started",
             actor="jsonl_test", entity_id="JSONL_TEST_001",
             module="system")
    path = bus._events_path()
    assert path.exists()
    # Every line must parse as JSON
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line: continue
            data = json.loads(line)  # raises if malformed
            assert "id" in data and "event_type" in data


# ── Transaction Lineage ─────────────────────────────────────────────

def test_v10475_transaction_lineage_module_exists():
    assert (REPO / "utils" / "transaction_lineage.py").exists()


def test_v10475_lineage_traces_direct_events():
    for k in list(sys.modules):
        if "event_bus" in k or "transaction_lineage" in k: del sys.modules[k]
    from utils.event_bus import get_event_bus
    from utils.transaction_lineage import trace_entity
    bus = get_event_bus()
    bus.emit(event_type="workflow.created", actor="lin_test",
             entity_id="LIN_TEST_001", module="credit")
    lin = trace_entity("LIN_TEST_001")
    assert lin.event_count() >= 1


def test_v10475_lineage_summary_aggregates():
    for k in list(sys.modules):
        if "event_bus" in k or "transaction_lineage" in k: del sys.modules[k]
    from utils.event_bus import get_event_bus
    from utils.transaction_lineage import trace_entity
    bus = get_event_bus()
    bus.emit(event_type="workflow.created", actor="alice",
             entity_id="LIN_TEST_002", module="credit")
    bus.emit(event_type="workflow.transition", actor="bob",
             entity_id="LIN_TEST_002", module="credit",
             payload={"from": "draft", "to": "submitted"})
    lin = trace_entity("LIN_TEST_002")
    s = lin.summary()
    assert "alice" in s["actors"] and "bob" in s["actors"]
    assert s["event_count"] >= 2


# ── Workflow Replay ─────────────────────────────────────────────────

def test_v10475_workflow_replay_module_exists():
    assert (REPO / "utils" / "workflow_replay.py").exists()


def test_v10475_replay_reconstructs_state_sequence():
    for k in list(sys.modules):
        if "event_bus" in k or "workflow_replay" in k: del sys.modules[k]
    from utils.event_bus import get_event_bus
    from utils.workflow_replay import replay_workflow
    bus = get_event_bus()
    item = "REPLAY_v10475_001"
    bus.emit(event_type="workflow.transition", actor="x",
             entity_id=item, module="credit",
             payload={"from": "draft", "to": "submitted"})
    bus.emit(event_type="workflow.transition", actor="y",
             entity_id=item, module="credit",
             payload={"from": "submitted", "to": "approved"})
    r = replay_workflow(item)
    assert r.current_state() == "approved"
    assert r.reached("submitted")


def test_v10475_replay_time_in_state():
    for k in list(sys.modules):
        if "event_bus" in k or "workflow_replay" in k: del sys.modules[k]
    from utils.event_bus import get_event_bus
    from utils.workflow_replay import replay_workflow
    bus = get_event_bus()
    item = "REPLAY_v10475_002"
    bus.emit(event_type="workflow.transition", actor="x",
             entity_id=item, module="credit",
             payload={"from": "draft", "to": "submitted"})
    bus.emit(event_type="workflow.transition", actor="y",
             entity_id=item, module="credit",
             payload={"from": "submitted", "to": "approved"})
    r = replay_workflow(item)
    # Item passed through 'submitted' so time_in_state should be a number
    t = r.time_in_state("submitted")
    assert t is not None and t >= 0


# ── Wired emitters ──────────────────────────────────────────────────

def test_v10475_workflow_engine_emits_on_transition():
    for k in list(sys.modules):
        if "workflow_engine" in k or "event_bus" in k: del sys.modules[k]
    from utils.workflow_engine import (
        ApplicationState, WorkflowState, WorkflowEngine,
    )
    from utils.event_bus import get_event_bus
    engine = WorkflowEngine()
    state = WorkflowState(item_id="WE_EMIT_TEST_001",
                          current_state=ApplicationState.DRAFT)
    engine.transition(state, ApplicationState.SUBMITTED,
                       actor="emit_test", note="auto-emit")
    found = get_event_bus().query(entity_id="WE_EMIT_TEST_001", limit=5)
    assert any(e.event_type == "workflow.transition" for e in found)


def test_v10475_workflow_engine_emits_on_rollback():
    for k in list(sys.modules):
        if "workflow_engine" in k or "event_bus" in k: del sys.modules[k]
    from utils.workflow_engine import (
        ApplicationState, WorkflowState, WorkflowEngine,
    )
    from utils.event_bus import get_event_bus
    engine = WorkflowEngine()
    state = WorkflowState(item_id="WE_RB_TEST_001",
                          current_state=ApplicationState.DRAFT)
    engine.transition(state, ApplicationState.SUBMITTED, actor="rb_test")
    engine.rollback(state, actor="rb_test", reason="test rollback")
    found = get_event_bus().query(entity_id="WE_RB_TEST_001", limit=5)
    assert any(e.event_type == "workflow.rollback" for e in found)


def test_v10475_bridge_emits_started_and_completed():
    for k in list(sys.modules):
        if "vb_actuals_bridge" in k or "event_bus" in k: del sys.modules[k]
    from utils.vb_actuals_bridge import preview_actuals_from_virtual_bank
    from utils.event_bus import get_event_bus
    r = preview_actuals_from_virtual_bank(target_period="2026-Q1")
    found = get_event_bus().query(event_type="actuals.*",
                                   entity_id="2026-Q1", limit=10)
    types = {e.event_type for e in found}
    assert "actuals.refresh.started" in types
    assert ("actuals.refresh.completed" in types
            or "actuals.refresh.failed" in types)


def test_v10475_bridge_correlation_chains_started_to_completed():
    for k in list(sys.modules):
        if "vb_actuals_bridge" in k or "event_bus" in k: del sys.modules[k]
    from utils.vb_actuals_bridge import preview_actuals_from_virtual_bank
    from utils.event_bus import get_event_bus
    r = preview_actuals_from_virtual_bank(target_period="2026-Q2")
    events = get_event_bus().query(event_type="actuals.*",
                                    entity_id="2026-Q2", limit=10)
    correlation_ids = {e.correlation_id for e in events
                       if e.correlation_id}
    assert len(correlation_ids) >= 1
    # Each correlation_id should have both started AND completed/failed
    for corr in correlation_ids:
        chain = [e for e in events if e.correlation_id == corr]
        types = {e.event_type for e in chain}
        if "actuals.refresh.started" in types:
            assert ("actuals.refresh.completed" in types
                    or "actuals.refresh.failed" in types)


def test_v10475_events_persist_in_environment_aware_path():
    """SIM mode events should land in data/sim/events.jsonl."""
    import os
    os.environ["A2Z_ENV"] = "sim"
    try:
        for k in list(sys.modules):
            if "event_bus" in k or "environment" in k: del sys.modules[k]
        from utils.event_bus import EventBus, get_event_bus
        from utils.environment import get_environment, Environment
        assert get_environment() == Environment.SIM
        bus = get_event_bus()
        path = bus._events_path()
        assert "sim" in str(path), f"path {path} not under sim/"
    finally:
        os.environ.pop("A2Z_ENV", None)


# ── G361 + regression ──────────────────────────────────────────────

def test_v10475_g361_passes():
    sys.path.insert(0, str(REPO / "scripts"))
    for k in list(sys.modules):
        if k.startswith("audit"): del sys.modules[k]
    from audit import gate_v10475_o2a_telemetry_lineage_replay
    r = gate_v10475_o2a_telemetry_lineage_replay()
    assert r["passed"], r.get("violations")


def test_v10475_prior_gates_preserved():
    """v10.474 isolation gate must still pass."""
    sys.path.insert(0, str(REPO / "scripts"))
    for k in list(sys.modules):
        if k.startswith("audit"): del sys.modules[k]
    from audit import gate_v10474_o8_environment_isolation
    assert gate_v10474_o8_environment_isolation()["passed"]


def test_v10475_360_harmony_preserved():
    for k in list(sys.modules):
        if "cascade_bsc_360" in k: del sys.modules[k]
    from utils.cascade_bsc_360_engine import cascade_bsc_360_audit
    assert cascade_bsc_360_audit().overall_harmony_pct >= 99.9
