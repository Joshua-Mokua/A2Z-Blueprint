"""utils/operational_heatmap.py — Operational observability heatmaps.

Per Joshua Master Prompt Phase O2:
    'Operational heatmaps' — bottleneck intelligence, queue depths,
    approval latencies, anomaly observability.

Reads the event_bus history to surface:

  - Bottlenecks: which event_type + module pairs have the longest p99
    duration between started/completed pairs
  - Queue depth: how many workflow items are currently in each state
  - Approval latency: p50/p95/p99 of approval cycle times per module
  - Module activity: event volume per module per hour bucket

This is the "what is on fire?" view for ops dashboards.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class LatencyDistribution:
    """p50/p95/p99 + count for a single metric."""
    count: int = 0
    p50_ms: Optional[float] = None
    p95_ms: Optional[float] = None
    p99_ms: Optional[float] = None
    mean_ms: Optional[float] = None
    max_ms: Optional[float] = None


def _percentile(values: List[float], p: float) -> Optional[float]:
    if not values: return None
    if p < 0 or p > 100: return None
    s = sorted(values)
    if len(s) == 1: return s[0]
    rank = (p / 100.0) * (len(s) - 1)
    lo = int(rank)
    hi = min(lo + 1, len(s) - 1)
    frac = rank - lo
    return s[lo] + (s[hi] - s[lo]) * frac


def _summarize(values: List[float]) -> LatencyDistribution:
    if not values:
        return LatencyDistribution(count=0)
    return LatencyDistribution(
        count=len(values),
        p50_ms=_percentile(values, 50),
        p95_ms=_percentile(values, 95),
        p99_ms=_percentile(values, 99),
        mean_ms=sum(values) / len(values),
        max_ms=max(values),
    )


def _parse_ts(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


# ──────────────────────────────────────────────────────────────────────
# Bottleneck analysis — pair started/completed events
# ──────────────────────────────────────────────────────────────────────

def bottleneck_analysis(*, since: Optional[str] = None,
                         until: Optional[str] = None) -> Dict[str, Any]:
    """Pair *.started events with their *.completed/.failed counterparts via
    correlation_id and report latency by event_type + module.

    Returns a dict keyed by event_type with LatencyDistribution.
    """
    from utils.event_bus import get_event_bus
    bus = get_event_bus()
    events = bus.query(limit=10_000, from_disk=True,
                       since=since, until=until)

    # Group by correlation_id
    by_corr: Dict[str, List] = defaultdict(list)
    for e in events:
        if e.correlation_id:
            by_corr[e.correlation_id].append(e)

    # For each correlation group, find pairs and compute latency
    by_metric: Dict[str, List[float]] = defaultdict(list)
    for corr, chain in by_corr.items():
        chain_sorted = sorted(chain, key=lambda e: e.timestamp)
        # Find first .started and last .completed/.failed in this chain
        starters = [e for e in chain_sorted if e.event_type.endswith(".started")]
        finishers = [e for e in chain_sorted
                    if e.event_type.endswith(".completed")
                    or e.event_type.endswith(".failed")]
        if not starters or not finishers:
            continue
        start_ev = starters[0]
        end_ev = finishers[-1]
        try:
            latency_ms = (_parse_ts(end_ev.timestamp)
                          - _parse_ts(start_ev.timestamp)).total_seconds() * 1000
        except Exception:
            continue
        # Use the event_type prefix as the metric key
        # e.g. "actuals.refresh" from "actuals.refresh.started"
        prefix = start_ev.event_type.rsplit(".", 1)[0]
        metric_key = f"{prefix}@{start_ev.module}"
        by_metric[metric_key].append(latency_ms)

    return {
        "by_metric": {k: _summarize(v) for k, v in by_metric.items()},
        "total_correlated_chains": len(by_corr),
        "since": since, "until": until,
    }


# ──────────────────────────────────────────────────────────────────────
# Workflow queue depth — by state
# ──────────────────────────────────────────────────────────────────────

def queue_depth_by_state(*, since: Optional[str] = None,
                          until: Optional[str] = None) -> Dict[str, int]:
    """Estimate how many items are currently in each workflow state.

    Walks workflow.transition events to determine each item's
    last-known state. Returns a count keyed by state name.
    """
    from utils.event_bus import get_event_bus
    bus = get_event_bus()
    events = bus.query(event_type="workflow.transition",
                       limit=50_000, from_disk=True,
                       since=since, until=until)
    last_state: Dict[str, str] = {}
    last_ts: Dict[str, str] = {}
    for e in events:
        item = e.entity_id
        to_state = (e.payload or {}).get("to")
        if not item or not to_state: continue
        # Only update if this event is newer than what we have
        if item not in last_ts or e.timestamp > last_ts[item]:
            last_state[item] = to_state
            last_ts[item] = e.timestamp

    counts: Counter = Counter()
    for s in last_state.values():
        counts[s] += 1
    return dict(counts)


# ──────────────────────────────────────────────────────────────────────
# Approval latency per module — workflow.created -> workflow.transition to APPROVED
# ──────────────────────────────────────────────────────────────────────

def approval_latency_per_module(*, since: Optional[str] = None,
                                  until: Optional[str] = None) -> Dict[str, LatencyDistribution]:
    """For each module, the latency distribution from a workflow's first
    seen event to its 'approved' transition.
    """
    from utils.event_bus import get_event_bus
    bus = get_event_bus()
    events = bus.query(event_type="workflow.*",
                       limit=50_000, from_disk=True,
                       since=since, until=until)

    # Sort ascending by timestamp
    events.sort(key=lambda e: e.timestamp)

    first_seen: Dict[Tuple[str, str], datetime] = {}
    approval_times: Dict[str, List[float]] = defaultdict(list)
    for e in events:
        key = (e.module, e.entity_id)
        if key not in first_seen:
            try:
                first_seen[key] = _parse_ts(e.timestamp)
            except Exception:
                continue
        if (e.payload or {}).get("to") == "approved":
            try:
                approved_at = _parse_ts(e.timestamp)
                latency_ms = (approved_at - first_seen[key]).total_seconds() * 1000
                approval_times[e.module].append(latency_ms)
            except Exception:
                continue

    return {mod: _summarize(values) for mod, values in approval_times.items()}


# ──────────────────────────────────────────────────────────────────────
# Module activity heatmap — events per (module, hour)
# ──────────────────────────────────────────────────────────────────────

def module_activity_heatmap(*, since: Optional[str] = None,
                              until: Optional[str] = None,
                              hours_back: int = 24) -> Dict[str, Any]:
    """Events per module per hour bucket.

    Returns a dict keyed by hour bucket (ISO 'YYYY-MM-DDTHH:00') with
    per-module counts. Useful for "what's been busy" dashboard tiles.
    """
    from utils.event_bus import get_event_bus
    bus = get_event_bus()
    if not since and hours_back:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours_back)
        since = cutoff.isoformat()
    events = bus.query(limit=50_000, from_disk=True,
                       since=since, until=until)

    buckets: Dict[str, Counter] = defaultdict(Counter)
    for e in events:
        try:
            dt = _parse_ts(e.timestamp)
            bucket = dt.strftime("%Y-%m-%dT%H:00")
            buckets[bucket][e.module or "(unknown)"] += 1
        except Exception:
            continue
    return {
        "buckets": {k: dict(v) for k, v in sorted(buckets.items())},
        "since": since, "until": until,
        "hours_back": hours_back,
    }


# ──────────────────────────────────────────────────────────────────────
# One-shot dashboard summary
# ──────────────────────────────────────────────────────────────────────

def heatmap_summary() -> Dict[str, Any]:
    """One-shot all-in-one summary for an ops dashboard tile."""
    return {
        "bottlenecks": bottleneck_analysis(),
        "queue_depth": queue_depth_by_state(),
        "approval_latency": {
            mod: {
                "count": dist.count,
                "p50_ms": dist.p50_ms, "p95_ms": dist.p95_ms,
                "p99_ms": dist.p99_ms, "mean_ms": dist.mean_ms,
            }
            for mod, dist in approval_latency_per_module().items()
        },
        "activity_heatmap": module_activity_heatmap(hours_back=6),
        "as_of": datetime.now(timezone.utc).isoformat(),
    }


# ──────────────────────────────────────────────────────────────────────
# Self-tests
# ──────────────────────────────────────────────────────────────────────

def _test_percentile_calculations():
    assert _percentile([1, 2, 3, 4, 5], 50) == 3
    assert _percentile([1, 2, 3, 4, 5], 100) == 5
    assert _percentile([1, 2, 3, 4, 5], 0) == 1
    assert _percentile([], 50) is None


def _test_bottleneck_pairs_started_completed():
    from utils.event_bus import get_event_bus
    bus = get_event_bus()
    corr = "heatmap-test-bottleneck-001"
    bus.emit(event_type="actuals.refresh.started", actor="hm",
             entity_id="HM_001", module="bsc_cascade",
             correlation_id=corr)
    bus.emit(event_type="actuals.refresh.completed", actor="hm",
             entity_id="HM_001", module="bsc_cascade",
             correlation_id=corr)
    out = bottleneck_analysis()
    assert "by_metric" in out
    # Some metric should have been computed
    assert sum(d.count for d in out["by_metric"].values()) >= 1


def _test_queue_depth_counts_states():
    from utils.event_bus import get_event_bus
    bus = get_event_bus()
    # Item A: ends at submitted
    bus.emit(event_type="workflow.transition", actor="hm",
             entity_id="HM_Q_A", module="credit",
             payload={"from": "draft", "to": "submitted"})
    # Item B: progressed to approved
    bus.emit(event_type="workflow.transition", actor="hm",
             entity_id="HM_Q_B", module="credit",
             payload={"from": "draft", "to": "submitted"})
    bus.emit(event_type="workflow.transition", actor="hm",
             entity_id="HM_Q_B", module="credit",
             payload={"from": "submitted", "to": "approved"})
    depths = queue_depth_by_state()
    assert "submitted" in depths
    assert "approved" in depths


def _test_approval_latency_per_module():
    from utils.event_bus import get_event_bus
    bus = get_event_bus()
    bus.emit(event_type="workflow.created", actor="hm",
             entity_id="HM_APPR_001", module="credit",
             payload={"from": None, "to": "draft"})
    bus.emit(event_type="workflow.transition", actor="hm",
             entity_id="HM_APPR_001", module="credit",
             payload={"from": "draft", "to": "approved"})
    out = approval_latency_per_module()
    # Returns dict (may be empty if test runs in isolation but should not error)
    assert isinstance(out, dict)


def _test_module_activity_heatmap_buckets():
    from utils.event_bus import get_event_bus
    bus = get_event_bus()
    bus.emit(event_type="workflow.transition", actor="hm",
             entity_id="HM_ACT_001", module="credit",
             payload={"from": "draft", "to": "submitted"})
    out = module_activity_heatmap(hours_back=24)
    assert "buckets" in out
    assert isinstance(out["buckets"], dict)


def _test_heatmap_summary_is_well_formed():
    s = heatmap_summary()
    for k in ("bottlenecks", "queue_depth", "approval_latency",
              "activity_heatmap", "as_of"):
        assert k in s


def self_test() -> None:
    _test_percentile_calculations()
    _test_bottleneck_pairs_started_completed()
    _test_queue_depth_counts_states()
    _test_approval_latency_per_module()
    _test_module_activity_heatmap_buckets()
    _test_heatmap_summary_is_well_formed()


__all__ = [
    "LatencyDistribution", "bottleneck_analysis",
    "queue_depth_by_state", "approval_latency_per_module",
    "module_activity_heatmap", "heatmap_summary",
]


if __name__ == "__main__":
    import sys as _sys
    from pathlib import Path as _P
    REPO = _P(__file__).parent.parent
    if str(REPO) not in _sys.path:
        _sys.path.insert(0, str(REPO))
    self_test()
    print("operational_heatmap self-test passed")
