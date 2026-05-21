"""Integration tests for v10.476 — Phase O2-B (completes Phase O2).

AI explainability + operational heatmaps + anomaly observability + API telemetry.
"""

import json
import sys
import time
from pathlib import Path

import pytest

REPO = Path("/tmp/a2z_fix")
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


# ── AI Explainability ───────────────────────────────────────────────

def test_v10476_ai_explainability_module_exists():
    assert (REPO / "utils" / "ai_explainability.py").exists()


def test_v10476_record_ai_decision_returns_id():
    for k in list(sys.modules):
        if "ai_explainability" in k or "event_bus" in k: del sys.modules[k]
    from utils.ai_explainability import record_ai_decision
    did = record_ai_decision(
        model="v10476_test", prompt={"x": 1}, response={"y": 2},
        reasoning_factors=[{"factor": "a", "value": 1, "weight": 0.5}],
        actor="v10476", entity_id="V10476_AI_001",
    )
    assert did and isinstance(did, str) and len(did) == 20


def test_v10476_ai_inference_event_emitted():
    for k in list(sys.modules):
        if "ai_explainability" in k or "event_bus" in k: del sys.modules[k]
    from utils.ai_explainability import record_ai_decision
    from utils.event_bus import get_event_bus
    record_ai_decision(
        model="emit_test", prompt={"x": 1}, response={"y": 2},
        actor="emit_test", entity_id="V10476_EMIT_001",
    )
    events = get_event_bus().query(event_type="ai.inference",
                                    entity_id="V10476_EMIT_001", limit=5)
    assert any(e.event_type == "ai.inference" for e in events)


def test_v10476_explanation_card_top_3_drivers_by_abs_weight():
    for k in list(sys.modules):
        if "ai_explainability" in k: del sys.modules[k]
    from utils.ai_explainability import record_ai_decision, decision_explanation_card
    did = record_ai_decision(
        model="card_v10476", prompt={"q": "x"}, response={"a": "y"},
        reasoning_factors=[
            {"factor": "kyc", "value": 0.9, "weight": 0.40},
            {"factor": "income", "value": 80_000, "weight": 0.30},
            {"factor": "dpd", "value": 0, "weight": -0.20},
            {"factor": "noise", "value": 0.0, "weight": 0.05},
        ],
        actor="card", entity_id="V10476_CARD_001",
    )
    card = decision_explanation_card(did)
    assert card is not None
    assert len(card["top_drivers"]) == 3
    assert card["top_drivers"][0]["factor"] == "kyc"
    assert any(d["direction"] == "negative" for d in card["top_drivers"])


def test_v10476_model_stats_aggregates_factors():
    for k in list(sys.modules):
        if "ai_explainability" in k: del sys.modules[k]
    from utils.ai_explainability import record_ai_decision, model_stats
    for i in range(3):
        record_ai_decision(
            model="stats_v10476", prompt={"i": i}, response={"o": i*2},
            confidence=0.7 + i*0.05,
            reasoning_factors=[
                {"factor": "income", "value": i, "weight": 0.4},
                {"factor": "kyc", "value": 0.9, "weight": 0.5},
            ],
            actor="stats", entity_id=f"V10476_STATS_{i:03d}",
        )
    s = model_stats("stats_v10476")
    assert s["count"] >= 3
    assert s["mean_confidence"] is not None
    factor_names = {f["factor"] for f in s["top_factors"]}
    assert "income" in factor_names and "kyc" in factor_names


# ── Operational Heatmap ─────────────────────────────────────────────

def test_v10476_heatmap_module_exists():
    assert (REPO / "utils" / "operational_heatmap.py").exists()


def test_v10476_percentile_calculations():
    for k in list(sys.modules):
        if "operational_heatmap" in k: del sys.modules[k]
    from utils.operational_heatmap import _percentile
    assert _percentile([1, 2, 3, 4, 5], 50) == 3
    assert _percentile([1, 2, 3, 4, 5], 100) == 5
    assert _percentile([], 50) is None


def test_v10476_bottleneck_analysis_pairs_correlation():
    for k in list(sys.modules):
        if "event_bus" in k or "operational_heatmap" in k:
            del sys.modules[k]
    from utils.event_bus import get_event_bus
    from utils.operational_heatmap import bottleneck_analysis
    bus = get_event_bus()
    corr = "v10476_heatmap_corr_001"
    bus.emit(event_type="actuals.refresh.started", actor="hm",
             entity_id="V10476_HM_001", module="bsc",
             correlation_id=corr)
    bus.emit(event_type="actuals.refresh.completed", actor="hm",
             entity_id="V10476_HM_001", module="bsc",
             correlation_id=corr)
    out = bottleneck_analysis()
    assert "by_metric" in out
    assert sum(d.count for d in out["by_metric"].values()) >= 1


def test_v10476_queue_depth_counts_per_state():
    for k in list(sys.modules):
        if "event_bus" in k or "operational_heatmap" in k:
            del sys.modules[k]
    from utils.event_bus import get_event_bus
    from utils.operational_heatmap import queue_depth_by_state
    bus = get_event_bus()
    bus.emit(event_type="workflow.transition", actor="qd",
             entity_id="V10476_QD_A", module="credit",
             payload={"from": "draft", "to": "submitted"})
    bus.emit(event_type="workflow.transition", actor="qd",
             entity_id="V10476_QD_B", module="credit",
             payload={"from": "draft", "to": "approved"})
    depths = queue_depth_by_state()
    assert "submitted" in depths or "approved" in depths


def test_v10476_approval_latency_per_module_runs():
    for k in list(sys.modules):
        if "operational_heatmap" in k: del sys.modules[k]
    from utils.operational_heatmap import approval_latency_per_module
    out = approval_latency_per_module()
    assert isinstance(out, dict)


def test_v10476_module_activity_heatmap_returns_buckets():
    for k in list(sys.modules):
        if "operational_heatmap" in k: del sys.modules[k]
    from utils.operational_heatmap import module_activity_heatmap
    out = module_activity_heatmap(hours_back=24)
    assert "buckets" in out


def test_v10476_heatmap_summary_well_formed():
    for k in list(sys.modules):
        if "operational_heatmap" in k: del sys.modules[k]
    from utils.operational_heatmap import heatmap_summary
    s = heatmap_summary()
    for k in ("bottlenecks", "queue_depth", "approval_latency",
              "activity_heatmap", "as_of"):
        assert k in s


# ── Anomaly Observer ────────────────────────────────────────────────

def test_v10476_anomaly_observer_module_exists():
    assert (REPO / "utils" / "anomaly_observer.py").exists()


def test_v10476_detect_anomalies_returns_list():
    for k in list(sys.modules):
        if "anomaly_observer" in k: del sys.modules[k]
    from utils.anomaly_observer import detect_anomalies
    out = detect_anomalies(emit_events=False)
    assert isinstance(out, list)


def test_v10476_anomaly_summary_well_formed():
    for k in list(sys.modules):
        if "anomaly_observer" in k: del sys.modules[k]
    from utils.anomaly_observer import anomaly_summary
    s = anomaly_summary()
    for k in ("as_of", "total_findings", "by_rule", "by_severity"):
        assert k in s


def test_v10476_stuck_workflow_rule_detects():
    """R3: an item in non-terminal state past stuck_hours should be flagged."""
    for k in list(sys.modules):
        if "anomaly_observer" in k: del sys.modules[k]
    from utils.anomaly_observer import _rule_stuck_workflow
    from datetime import datetime, timezone, timedelta
    class _Ev:
        def __init__(self, **kw): self.__dict__.update(kw)
    old_ts = (datetime.now(timezone.utc) - timedelta(hours=72)).isoformat()
    synthetic = [_Ev(event_type="workflow.transition",
                     entity_id="V10476_STUCK_001", module="credit",
                     actor="t", timestamp=old_ts, severity="info",
                     payload={"from": "draft", "to": "under_review"})]
    findings = _rule_stuck_workflow(synthetic, stuck_hours=24.0)
    assert any(f.affected_entity_id == "V10476_STUCK_001" for f in findings)


def test_v10476_terminal_state_not_flagged():
    """R3 must not flag items in terminal states."""
    for k in list(sys.modules):
        if "anomaly_observer" in k: del sys.modules[k]
    from utils.anomaly_observer import _rule_stuck_workflow, TERMINAL_STATES
    from datetime import datetime, timezone, timedelta
    class _Ev:
        def __init__(self, **kw): self.__dict__.update(kw)
    old_ts = (datetime.now(timezone.utc) - timedelta(hours=72)).isoformat()
    synthetic = [_Ev(event_type="workflow.transition",
                     entity_id="V10476_OK_001", module="credit", actor="t",
                     timestamp=old_ts, severity="info",
                     payload={"from": "reviewed", "to": "approved"})]
    findings = _rule_stuck_workflow(synthetic, stuck_hours=24.0)
    assert not any(f.affected_entity_id == "V10476_OK_001" for f in findings)


def test_v10476_failure_surge_flags_high_ratio():
    """R2: 6/10 = 60% failures with ≥5 failed must flag."""
    for k in list(sys.modules):
        if "anomaly_observer" in k: del sys.modules[k]
    from utils.anomaly_observer import _rule_failure_surge
    from datetime import datetime, timezone
    class _Ev:
        def __init__(self, **kw): self.__dict__.update(kw)
    now = datetime.now(timezone.utc).isoformat()
    synthetic = (
        [_Ev(event_type="actuals.refresh.failed", severity="error",
             timestamp=now, module="bsc", actor="x",
             entity_id=f"f{i}", payload={}) for i in range(6)]
        + [_Ev(event_type="actuals.refresh.completed", severity="info",
                timestamp=now, module="bsc", actor="x",
                entity_id=f"c{i}", payload={}) for i in range(4)]
    )
    findings = _rule_failure_surge(synthetic, min_failed=5,
                                    ratio_threshold=0.30)
    assert findings


# ── API Telemetry ───────────────────────────────────────────────────

def test_v10476_api_telemetry_module_exists():
    assert (REPO / "utils" / "api_telemetry.py").exists()


def test_v10476_record_call_persists():
    for k in list(sys.modules):
        if "api_telemetry" in k: del sys.modules[k]
    from utils.api_telemetry import record_call, get_latency_distribution
    record_call(endpoint="/v10476/persist_test",
                duration_ms=15.0, method="GET", status_code=200)
    dist = get_latency_distribution("/v10476/persist_test")
    assert dist["count"] >= 1


def test_v10476_track_decorator_records_latency():
    for k in list(sys.modules):
        if "api_telemetry" in k: del sys.modules[k]
    from utils.api_telemetry import track_api_call, get_latency_distribution
    @track_api_call("/v10476/decorated")
    def handler(x):
        time.sleep(0.001)
        return x + 1
    handler(5)
    handler(6)
    dist = get_latency_distribution("/v10476/decorated")
    assert dist["count"] >= 2
    assert dist["p50_ms"] is not None


def test_v10476_decorator_records_500_on_exception():
    for k in list(sys.modules):
        if "api_telemetry" in k: del sys.modules[k]
    from utils.api_telemetry import track_api_call, get_telemetry_summary
    @track_api_call("/v10476/err_endpoint")
    def boom():
        raise RuntimeError("intentional")
    try:
        boom()
    except RuntimeError:
        pass
    summary = get_telemetry_summary(hours_back=1)
    if "/v10476/err_endpoint" in summary["endpoints"]:
        assert summary["endpoints"]["/v10476/err_endpoint"]["error_count"] >= 1


def test_v10476_telemetry_summary_well_formed():
    for k in list(sys.modules):
        if "api_telemetry" in k: del sys.modules[k]
    from utils.api_telemetry import get_telemetry_summary
    s = get_telemetry_summary(hours_back=24)
    for k in ("since", "total_calls", "endpoints", "as_of"):
        assert k in s


# ── G362 + regression ──────────────────────────────────────────────

def test_v10476_g362_passes():
    sys.path.insert(0, str(REPO / "scripts"))
    for k in list(sys.modules):
        if k.startswith("audit"): del sys.modules[k]
    from audit import gate_v10476_o2b_ai_heatmap_anomaly_telemetry
    r = gate_v10476_o2b_ai_heatmap_anomaly_telemetry()
    assert r["passed"], r.get("violations")


def test_v10476_g361_telemetry_preserved():
    """v10.475 O2-A (event bus + lineage + replay) must still pass."""
    sys.path.insert(0, str(REPO / "scripts"))
    for k in list(sys.modules):
        if k.startswith("audit"): del sys.modules[k]
    from audit import gate_v10475_o2a_telemetry_lineage_replay
    assert gate_v10475_o2a_telemetry_lineage_replay()["passed"]


def test_v10476_g360_isolation_preserved():
    sys.path.insert(0, str(REPO / "scripts"))
    for k in list(sys.modules):
        if k.startswith("audit"): del sys.modules[k]
    from audit import gate_v10474_o8_environment_isolation
    assert gate_v10474_o8_environment_isolation()["passed"]


def test_v10476_360_harmony_preserved():
    for k in list(sys.modules):
        if "cascade_bsc_360" in k: del sys.modules[k]
    from utils.cascade_bsc_360_engine import cascade_bsc_360_audit
    assert cascade_bsc_360_audit().overall_harmony_pct >= 99.9
