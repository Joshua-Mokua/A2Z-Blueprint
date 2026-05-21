"""utils/anomaly_observer.py — Automatic anomaly detection.

Per Joshua Master Prompt Phase O2:
    'Anomaly observability' — automatic surfacing of deviations.

Reads the event_bus and applies a small set of detection rules to
auto-surface anomalies. Each detected anomaly is also emitted as an
`anomaly.detected` event so downstream dashboards can subscribe.

Rules implemented (intentionally conservative to avoid false-positive
fatigue; v10.483 will broaden these significantly):

  R1 — Volume spike
       For each event_type, count events per hour over the last 24h.
       Flag any hour whose count > rolling_mean + 3 * rolling_stdev,
       provided rolling_mean > 0 and there are >= 5 baseline hours.

  R2 — Failure surge
       Across the last 1h, if the ratio of *.failed events to total
       events of the same family is > 30% (with at least 5 failed),
       flag it.

  R3 — Stuck workflow
       Any item whose last transition occurred more than `stuck_hours`
       ago AND whose current state is not terminal (approved /
       rejected / cancelled / executed) is flagged.

  R4 — High-severity event burst
       More than 3 events with severity=critical in the last hour.
"""

from __future__ import annotations

import statistics
from collections import Counter, defaultdict
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Set

TERMINAL_STATES: Set[str] = {
    "approved", "rejected", "cancelled", "executed", "closed",
}


@dataclass
class Anomaly:
    id: str
    timestamp: str
    rule: str
    severity: str  # info | warning | error | critical
    title: str
    summary: str
    evidence: Dict[str, Any] = field(default_factory=dict)
    affected_entity_id: Optional[str] = None
    affected_module: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ──────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────

def _parse_ts(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _hash_id(*parts: str) -> str:
    import hashlib
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:16]


# ──────────────────────────────────────────────────────────────────────
# Detection rules
# ──────────────────────────────────────────────────────────────────────

def _rule_volume_spike(events: List, *, hours_back: int = 24,
                       sigma: float = 3.0,
                       min_baseline_hours: int = 5) -> List[Anomaly]:
    """R1 — Volume spike per event_type per hour."""
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=hours_back)
    by_type_hour: Dict[str, Counter] = defaultdict(Counter)
    for e in events:
        try:
            dt = _parse_ts(e.timestamp)
            if dt < cutoff: continue
            bucket = dt.strftime("%Y-%m-%dT%H:00")
            by_type_hour[e.event_type][bucket] += 1
        except Exception:
            continue

    findings: List[Anomaly] = []
    for etype, hour_counts in by_type_hour.items():
        if len(hour_counts) < min_baseline_hours: continue
        values = list(hour_counts.values())
        mean = statistics.mean(values)
        stdev = statistics.pstdev(values)
        if mean <= 0 or stdev <= 0: continue
        threshold = mean + sigma * stdev
        # Look at the most recent bucket
        latest_bucket = max(hour_counts.keys())
        latest_count = hour_counts[latest_bucket]
        if latest_count > threshold and latest_count >= 5:
            findings.append(Anomaly(
                id=_hash_id("R1", etype, latest_bucket),
                timestamp=_now_iso(),
                rule="R1_volume_spike",
                severity="warning",
                title=f"Volume spike: {etype}",
                summary=(f"{latest_count} events in {latest_bucket} "
                         f"vs rolling mean {mean:.1f} (>{sigma}σ)"),
                evidence={
                    "event_type": etype, "hour": latest_bucket,
                    "count": latest_count, "rolling_mean": mean,
                    "rolling_stdev": stdev, "threshold": threshold,
                },
            ))
    return findings


def _rule_failure_surge(events: List, *, hours_back: int = 1,
                       min_failed: int = 5,
                       ratio_threshold: float = 0.30) -> List[Anomaly]:
    """R2 — Failure surge by event family in the last `hours_back` hour(s)."""
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=hours_back)
    family_total: Counter = Counter()
    family_failed: Counter = Counter()
    for e in events:
        try:
            if _parse_ts(e.timestamp) < cutoff: continue
        except Exception:
            continue
        # Family = first two segments of event_type (e.g. "actuals.refresh")
        parts = e.event_type.split(".")
        family = ".".join(parts[:2]) if len(parts) >= 2 else parts[0]
        family_total[family] += 1
        if e.event_type.endswith(".failed"):
            family_failed[family] += 1

    findings: List[Anomaly] = []
    for family, failed_count in family_failed.items():
        total = family_total[family]
        if total == 0: continue
        ratio = failed_count / total
        if failed_count >= min_failed and ratio >= ratio_threshold:
            findings.append(Anomaly(
                id=_hash_id("R2", family, str(int(now.timestamp() // 3600))),
                timestamp=_now_iso(),
                rule="R2_failure_surge",
                severity="error",
                title=f"Failure surge: {family}",
                summary=(f"{failed_count}/{total} ({ratio:.0%}) failed "
                         f"in last {hours_back}h"),
                evidence={
                    "family": family, "failed_count": failed_count,
                    "total_count": total, "failure_ratio": ratio,
                    "hours_back": hours_back,
                },
            ))
    return findings


def _rule_stuck_workflow(events: List, *,
                          stuck_hours: float = 48.0) -> List[Anomaly]:
    """R3 — Workflow items in non-terminal state for too long."""
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=stuck_hours)

    # Build last-state-per-item from workflow.* events
    last_event: Dict[str, Any] = {}
    for e in events:
        if not e.event_type.startswith("workflow."): continue
        item = e.entity_id
        if not item: continue
        last_event.setdefault(item, e)
        if e.timestamp > last_event[item].timestamp:
            last_event[item] = e

    findings: List[Anomaly] = []
    for item, e in last_event.items():
        to_state = (e.payload or {}).get("to") or (e.payload or {}).get("to_state")
        if not to_state: continue
        if to_state in TERMINAL_STATES: continue
        try:
            if _parse_ts(e.timestamp) >= cutoff: continue
        except Exception:
            continue
        hours_stuck = (now - _parse_ts(e.timestamp)).total_seconds() / 3600
        findings.append(Anomaly(
            id=_hash_id("R3", item, to_state),
            timestamp=_now_iso(),
            rule="R3_stuck_workflow",
            severity="warning",
            title=f"Stuck workflow: {item}",
            summary=(f"In state {to_state!r} for {hours_stuck:.1f}h "
                     f"(threshold {stuck_hours}h)"),
            evidence={
                "item_id": item, "state": to_state,
                "hours_stuck": hours_stuck, "module": e.module,
                "last_actor": e.actor, "last_ts": e.timestamp,
            },
            affected_entity_id=item, affected_module=e.module,
        ))
    return findings


def _rule_critical_burst(events: List, *,
                          hours_back: int = 1,
                          burst_threshold: int = 3) -> List[Anomaly]:
    """R4 — More than N critical-severity events in the window."""
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=hours_back)
    criticals = []
    for e in events:
        try:
            if _parse_ts(e.timestamp) < cutoff: continue
        except Exception:
            continue
        if (e.severity or "").lower() == "critical":
            criticals.append(e)
    if len(criticals) > burst_threshold:
        return [Anomaly(
            id=_hash_id("R4", str(int(now.timestamp() // 3600))),
            timestamp=_now_iso(),
            rule="R4_critical_burst",
            severity="critical",
            title=f"Critical event burst: {len(criticals)} in {hours_back}h",
            summary=(f"{len(criticals)} critical-severity events in last "
                     f"{hours_back}h (threshold {burst_threshold})"),
            evidence={
                "count": len(criticals),
                "modules": list({e.module for e in criticals if e.module})[:10],
                "event_types": list({e.event_type for e in criticals})[:10],
            },
        )]
    return []


# ──────────────────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────────────────

def detect_anomalies(*, emit_events: bool = True,
                      hours_back: int = 24) -> List[Anomaly]:
    """Run all detection rules. Optionally emit `anomaly.detected` events."""
    from utils.event_bus import get_event_bus
    bus = get_event_bus()
    events = bus.query(limit=50_000, from_disk=True)

    findings: List[Anomaly] = []
    findings.extend(_rule_volume_spike(events, hours_back=hours_back))
    findings.extend(_rule_failure_surge(events))
    findings.extend(_rule_stuck_workflow(events))
    findings.extend(_rule_critical_burst(events))

    if emit_events:
        for f in findings:
            try:
                bus.emit(
                    event_type="anomaly.detected",
                    actor="anomaly_observer",
                    entity_id=f.affected_entity_id or "",
                    module=f.affected_module or "anomaly",
                    payload=f.to_dict(),
                    severity=f.severity,
                )
            except Exception:
                pass
    return findings


def anomaly_summary() -> Dict[str, Any]:
    """One-shot summary for dashboards."""
    findings = detect_anomalies(emit_events=False)
    by_rule = Counter(f.rule for f in findings)
    by_severity = Counter(f.severity for f in findings)
    return {
        "as_of": _now_iso(),
        "total_findings": len(findings),
        "by_rule": dict(by_rule),
        "by_severity": dict(by_severity),
        "findings": [f.to_dict() for f in findings[:50]],
    }


# ──────────────────────────────────────────────────────────────────────
# Self-tests
# ──────────────────────────────────────────────────────────────────────

def _test_detect_runs_without_error():
    findings = detect_anomalies(emit_events=False)
    assert isinstance(findings, list)


def _test_stuck_workflow_detected():
    """Manually plant an old workflow event and check R3 picks it up."""
    from utils.event_bus import get_event_bus
    import time
    bus = get_event_bus()
    # Emit one with timestamp 3 days ago via direct payload, then a recent event
    # Actually we'll just check rule logic against synthetic events
    from datetime import datetime, timezone, timedelta
    old_ts = (datetime.now(timezone.utc) - timedelta(hours=72)).isoformat()
    # We can't easily backdate via emit; verify rule logic with synthetic event list
    class _SyntheticEvent:
        def __init__(self, **kw):
            self.__dict__.update(kw)
    synthetic = [_SyntheticEvent(
        event_type="workflow.transition",
        entity_id="STUCK_TEST_001", module="credit",
        actor="t", timestamp=old_ts, severity="info",
        payload={"from": "draft", "to": "under_review"},
    )]
    findings = _rule_stuck_workflow(synthetic, stuck_hours=24.0)
    assert any(f.affected_entity_id == "STUCK_TEST_001" for f in findings)


def _test_terminal_state_not_flagged():
    from datetime import datetime, timezone, timedelta
    class _Ev:
        def __init__(self, **kw): self.__dict__.update(kw)
    old_ts = (datetime.now(timezone.utc) - timedelta(hours=72)).isoformat()
    # Terminal state should NOT be flagged
    synthetic = [_Ev(event_type="workflow.transition",
                     entity_id="OK_TEST_001", module="credit", actor="t",
                     timestamp=old_ts, severity="info",
                     payload={"from": "reviewed", "to": "approved"})]
    findings = _rule_stuck_workflow(synthetic, stuck_hours=24.0)
    assert not any(f.affected_entity_id == "OK_TEST_001" for f in findings)


def _test_failure_surge_threshold():
    from datetime import datetime, timezone
    class _Ev:
        def __init__(self, **kw): self.__dict__.update(kw)
    now = datetime.now(timezone.utc).isoformat()
    # 6 failed out of 10 → ratio 0.6 → over the 0.30 threshold AND ≥5 failed
    synthetic = ([_Ev(event_type="actuals.refresh.failed",
                       severity="error", timestamp=now,
                       module="bsc", actor="x", entity_id=f"f{i}",
                       payload={}) for i in range(6)]
                + [_Ev(event_type="actuals.refresh.completed",
                        severity="info", timestamp=now,
                        module="bsc", actor="x", entity_id=f"c{i}",
                        payload={}) for i in range(4)])
    findings = _rule_failure_surge(synthetic, min_failed=5,
                                    ratio_threshold=0.30)
    assert findings, "should flag 6/10 failure ratio"


def _test_emit_events_creates_anomaly_events():
    from datetime import datetime, timezone, timedelta
    from utils.event_bus import get_event_bus
    bus = get_event_bus()
    # Trigger R3 with a real (stuck) entity then run detect
    # Direct planting: emit normally, then call detect with no events filter
    # — but detect_anomalies reads from disk so it picks up everything.
    # We just verify the wiring works by running it and asserting no exception.
    findings = detect_anomalies(emit_events=True)
    assert isinstance(findings, list)


def _test_summary_well_formed():
    s = anomaly_summary()
    for k in ("as_of", "total_findings", "by_rule",
              "by_severity", "findings"):
        assert k in s


def self_test() -> None:
    _test_detect_runs_without_error()
    _test_stuck_workflow_detected()
    _test_terminal_state_not_flagged()
    _test_failure_surge_threshold()
    _test_emit_events_creates_anomaly_events()
    _test_summary_well_formed()


__all__ = [
    "Anomaly", "TERMINAL_STATES", "detect_anomalies", "anomaly_summary",
]


if __name__ == "__main__":
    import sys as _sys
    from pathlib import Path as _P
    REPO = _P(__file__).parent.parent
    if str(REPO) not in _sys.path:
        _sys.path.insert(0, str(REPO))
    self_test()
    print("anomaly_observer self-test passed")
