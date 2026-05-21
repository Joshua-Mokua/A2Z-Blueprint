"""utils/transaction_lineage.py — End-to-end transaction lineage walker.

Per Joshua Master Prompt Phase O2:
    'transaction lineage' must be observable.

Given an entity_id (loan, transaction, account, BSC record), this
module walks the event_bus + audit_log to produce a full causal
chain — what happened, in what order, by whom, with what payload.

This is the engine that powers operational war-room replay.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set


@dataclass
class LineageNode:
    """One step in a transaction's lineage."""
    event_id: str
    timestamp: str
    event_type: str
    actor: str
    module: str
    entity_id: str
    payload: Dict[str, Any]
    severity: str = "info"
    correlation_id: Optional[str] = None
    parent_event_id: Optional[str] = None
    children: List["LineageNode"] = field(default_factory=list)


@dataclass
class Lineage:
    """Full lineage for an entity."""
    entity_id: str
    roots: List[LineageNode] = field(default_factory=list)
    flat: List[LineageNode] = field(default_factory=list)

    def event_count(self) -> int:
        return len(self.flat)

    def actors_involved(self) -> List[str]:
        return sorted({n.actor for n in self.flat if n.actor})

    def modules_involved(self) -> List[str]:
        return sorted({n.module for n in self.flat if n.module})

    def event_types(self) -> List[str]:
        return [n.event_type for n in self.flat]

    def summary(self) -> Dict[str, Any]:
        return {
            "entity_id": self.entity_id,
            "event_count": self.event_count(),
            "actors": self.actors_involved(),
            "modules": self.modules_involved(),
            "first_event": self.flat[0].timestamp if self.flat else None,
            "last_event": self.flat[-1].timestamp if self.flat else None,
            "event_types": list(set(self.event_types())),
        }


def trace_entity(entity_id: str,
                  *, include_correlated: bool = True,
                  limit: int = 500) -> Lineage:
    """Walk all events touching `entity_id`.

    If include_correlated=True, also pulls events sharing a
    correlation_id with any direct-match event — useful when a
    workflow chains across multiple entities (e.g. a loan creates a
    customer record creates an account).
    """
    from utils.event_bus import get_event_bus
    bus = get_event_bus()

    # Pass 1: direct matches
    direct = bus.query(entity_id=str(entity_id), limit=limit, from_disk=True)
    direct.sort(key=lambda e: e.timestamp)

    # Pass 2: pull correlated if requested
    correlated: List = []
    if include_correlated:
        seen_corr: Set[str] = set()
        for e in direct:
            if e.correlation_id and e.correlation_id not in seen_corr:
                seen_corr.add(e.correlation_id)
                corr_events = bus.query(
                    correlation_id=e.correlation_id,
                    limit=limit, from_disk=True,
                )
                correlated.extend(corr_events)

    # Dedupe by event id
    by_id: Dict[str, Any] = {}
    for e in direct + correlated:
        by_id[e.id] = e
    all_events = sorted(by_id.values(), key=lambda e: e.timestamp)

    # Build flat nodes
    nodes: Dict[str, LineageNode] = {}
    for e in all_events:
        nodes[e.id] = LineageNode(
            event_id=e.id, timestamp=e.timestamp,
            event_type=e.event_type, actor=e.actor,
            module=e.module, entity_id=e.entity_id,
            payload=e.payload, severity=e.severity,
            correlation_id=e.correlation_id,
            parent_event_id=e.parent_event_id,
        )

    # Build parent→child relationships
    roots: List[LineageNode] = []
    for node in nodes.values():
        if node.parent_event_id and node.parent_event_id in nodes:
            nodes[node.parent_event_id].children.append(node)
        else:
            roots.append(node)

    return Lineage(
        entity_id=str(entity_id),
        roots=roots,
        flat=sorted(nodes.values(), key=lambda n: n.timestamp),
    )


def render_lineage_text(lineage: Lineage,
                         *, indent: str = "  ") -> str:
    """Render a lineage as human-readable text (tree view)."""
    out = [f"Lineage: {lineage.entity_id}"]
    summary = lineage.summary()
    out.append(f"  Events: {summary['event_count']}")
    out.append(f"  Actors: {', '.join(summary['actors'])}")
    out.append(f"  Modules: {', '.join(summary['modules'])}")
    out.append(f"  First: {summary['first_event']}")
    out.append(f"  Last:  {summary['last_event']}")
    out.append("")
    out.append("Tree:")
    def _walk(node: LineageNode, depth: int) -> None:
        pad = indent * (depth + 1)
        out.append(
            f"{pad}[{node.timestamp[:19]}] {node.event_type:<30} "
            f"actor={node.actor} module={node.module}"
        )
        for c in node.children:
            _walk(c, depth + 1)
    for r in lineage.roots:
        _walk(r, 0)
    return "\n".join(out)


# ──────────────────────────────────────────────────────────────────────
# Self-tests
# ──────────────────────────────────────────────────────────────────────

def _test_trace_finds_direct_events():
    from utils.event_bus import get_event_bus
    bus = get_event_bus()
    ent = "TRACE_TEST_ENT_001"
    eid = bus.emit(event_type="workflow.created", actor="trace_test",
                    entity_id=ent, module="credit", payload={"x": 1})
    lin = trace_entity(ent)
    assert lin.event_count() >= 1
    assert any(n.event_id == eid for n in lin.flat)


def _test_trace_chains_parent_child():
    from utils.event_bus import get_event_bus
    bus = get_event_bus()
    ent = "TRACE_TEST_ENT_002"
    p = bus.emit(event_type="approval.requested", actor="trace_test",
                  entity_id=ent, module="credit", payload={"step": "request"})
    c = bus.emit(event_type="approval.granted", actor="trace_test",
                  entity_id=ent, module="credit", payload={"step": "grant"},
                  parent_event_id=p)
    lin = trace_entity(ent)
    parent_node = next(n for n in lin.flat if n.event_id == p)
    assert any(child.event_id == c for child in parent_node.children)


def _test_trace_with_correlation_id():
    from utils.event_bus import get_event_bus
    bus = get_event_bus()
    ent_a = "TRACE_TEST_ENT_003A"
    ent_b = "TRACE_TEST_ENT_003B"
    corr = "trace-test-corr-003"
    bus.emit(event_type="workflow.created", actor="trace_test",
             entity_id=ent_a, module="credit", correlation_id=corr)
    bus.emit(event_type="workflow.transition", actor="trace_test",
             entity_id=ent_b, module="credit", correlation_id=corr,
             payload={})
    lin = trace_entity(ent_a, include_correlated=True)
    # ent_b should appear via correlation
    assert any(n.entity_id == ent_b for n in lin.flat)


def _test_summary_aggregates():
    from utils.event_bus import get_event_bus
    bus = get_event_bus()
    ent = "TRACE_TEST_ENT_004"
    bus.emit(event_type="workflow.created", actor="alice",
             entity_id=ent, module="credit")
    bus.emit(event_type="workflow.transition", actor="bob",
             entity_id=ent, module="credit", payload={})
    lin = trace_entity(ent)
    s = lin.summary()
    assert s["event_count"] >= 2
    assert "alice" in s["actors"] and "bob" in s["actors"]


def _test_render_text_works():
    from utils.event_bus import get_event_bus
    bus = get_event_bus()
    ent = "TRACE_TEST_ENT_005"
    bus.emit(event_type="workflow.created", actor="render_test",
             entity_id=ent, module="credit")
    lin = trace_entity(ent)
    text = render_lineage_text(lin)
    assert "Lineage:" in text and ent in text


def self_test() -> None:
    _test_trace_finds_direct_events()
    _test_trace_chains_parent_child()
    _test_trace_with_correlation_id()
    _test_summary_aggregates()
    _test_render_text_works()


__all__ = ["LineageNode", "Lineage", "trace_entity", "render_lineage_text"]


if __name__ == "__main__":
    import sys as _sys
    from pathlib import Path as _P
    REPO = _P(__file__).parent.parent
    if str(REPO) not in _sys.path:
        _sys.path.insert(0, str(REPO))
    self_test()
    print("transaction_lineage self-test passed")
