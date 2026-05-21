"""utils.initiative_dependency — Initiative Dependency & Risk Intelligence
(Standard #51, v5.54). Volume Eight — Execute Enhancement.

Per v6 spec §8:
    DependencyIntelligenceEngine: critical-path computation, blocked-set
    detection, risk propagation across dependency graph.

WHAT THIS MODULE SHIPS
----------------------
1. DependencyIntelligenceEngine class with:
   - compute_critical_path(initiative_set) — longest dependency chain
   - identify_blocked_initiatives() — initiatives waiting on incomplete predecessors
   - risk_propagation(initiative_id) — what's blocked downstream if this slips
   - detect_cycles() — cycle detection (data integrity check)

2. RISK_LEVELS catalog: LOW, MEDIUM, HIGH, CRITICAL

HONESTY DISCIPLINE
------------------
Rule 6 — No silent fallback:
  - Cycle detection runs FIRST on any computation; if cycles exist, methods
    return error rather than hanging or silently picking a path
  - Missing dependencies (referenced but not in initiative set) surfaced
    explicitly in meta.unknown_dependencies
"""
from __future__ import annotations

import logging
from collections import defaultdict, deque
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Set, Tuple


logger = logging.getLogger("a2z.initiative_dependency")


# ─────────────────────────────────────────────────────────────────────
# Spec literals (v6 §8 #51)
# ─────────────────────────────────────────────────────────────────────

RISK_LEVELS: List[str] = ["LOW", "MEDIUM", "HIGH", "CRITICAL"]

# Risk propagation thresholds (downstream blocked count → risk level)
RISK_LOW_MAX      = 0   # 0 downstream → LOW
RISK_MEDIUM_MAX   = 2   # ≤2 downstream → MEDIUM
RISK_HIGH_MAX     = 5   # ≤5 downstream → HIGH
                        # >5 downstream → CRITICAL


# ─────────────────────────────────────────────────────────────────────
# Engine
# ─────────────────────────────────────────────────────────────────────

class DependencyIntelligenceEngine:
    """Initiative dependency graph + critical path + risk propagation."""

    RISK_LEVELS = RISK_LEVELS

    def __init__(
        self,
        initiative_lookup_fn:   Optional[Callable[[str], Optional[dict]]] = None,
        all_initiatives_fn:     Optional[Callable[[], List[dict]]]       = None,
        dependency_lookup_fn:   Optional[Callable[[str], List[str]]]     = None,
    ):
        """All collaborators injectable.

        initiative_lookup_fn(initiative_id) → dict | None
        all_initiatives_fn() → list of all initiative dicts
        dependency_lookup_fn(initiative_id) → list of initiative_ids this depends on
                                              (predecessors — must complete first)
        """
        self._init = initiative_lookup_fn  or (lambda i: None)
        self._all  = all_initiatives_fn    or (lambda: [])
        self._deps = dependency_lookup_fn  or (lambda i: [])

    # ──────────────────────────────────────────────────────────────────
    # Cycle detection (Rule 6 — runs FIRST)
    # ──────────────────────────────────────────────────────────────────

    def detect_cycles(self) -> Dict[str, Any]:
        """Detect dependency cycles (data-integrity check).

        Returns:
            {"has_cycles": bool, "cycles": [list of node lists], "checked_count": int}
        """
        all_inits = self._all() or []
        nodes = [i.get("initiative_id") for i in all_inits if isinstance(i, dict) and i.get("initiative_id")]
        adj: Dict[str, List[str]] = {n: list(self._deps(n) or []) for n in nodes}

        # DFS-based cycle detection
        WHITE, GRAY, BLACK = 0, 1, 2
        color: Dict[str, int] = {n: WHITE for n in nodes}
        cycles: List[List[str]] = []

        def dfs(n: str, path: List[str]):
            if color.get(n) == GRAY:
                # Found a cycle
                idx = path.index(n) if n in path else 0
                cycles.append(path[idx:] + [n])
                return
            if color.get(n) == BLACK:
                return
            color[n] = GRAY
            for next_node in adj.get(n, []):
                if next_node in color:    # only follow known nodes
                    dfs(next_node, path + [n])
            color[n] = BLACK

        for n in nodes:
            if color[n] == WHITE:
                dfs(n, [])

        # Dedup cycles (any rotation is the same cycle)
        unique_cycles: List[List[str]] = []
        seen: Set[frozenset] = set()
        for c in cycles:
            key = frozenset(c)
            if key not in seen:
                seen.add(key)
                unique_cycles.append(c)

        return {
            "has_cycles":     len(unique_cycles) > 0,
            "cycles":         unique_cycles,
            "checked_count":  len(nodes),
        }

    # ──────────────────────────────────────────────────────────────────
    # Spec entry: compute_critical_path
    # ──────────────────────────────────────────────────────────────────

    def compute_critical_path(
        self, initiative_set: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Find longest dependency chain.

        Returns:
            {"path": [initiative_ids in order], "length": int, "error": str | None}

        HONESTY: refuses to compute if cycles detected (Rule 6 — no silent hang).
        """
        cycles = self.detect_cycles()
        if cycles["has_cycles"]:
            return {
                "path":   [],
                "length": 0,
                "error":  f"cannot compute critical path with cycles: {cycles['cycles']}",
            }

        all_inits = self._all() or []
        if initiative_set is None:
            nodes = [i.get("initiative_id") for i in all_inits if isinstance(i, dict) and i.get("initiative_id")]
        else:
            nodes = list(initiative_set)

        if not nodes:
            return {"path": [], "length": 0, "error": None}

        # Topological sort + longest path DP
        adj: Dict[str, List[str]] = {n: list(self._deps(n) or []) for n in nodes}

        # Build successor map (reverse of predecessors)
        succ: Dict[str, List[str]] = defaultdict(list)
        in_degree: Dict[str, int] = {n: 0 for n in nodes}
        for n in nodes:
            for pred in adj[n]:
                if pred in in_degree:
                    succ[pred].append(n)
                    in_degree[n] += 1

        # Topological sort via Kahn's algorithm
        queue = deque([n for n in nodes if in_degree[n] == 0])
        topo: List[str] = []
        in_deg_copy = dict(in_degree)
        while queue:
            n = queue.popleft()
            topo.append(n)
            for s in succ[n]:
                in_deg_copy[s] -= 1
                if in_deg_copy[s] == 0:
                    queue.append(s)

        if len(topo) != len(nodes):
            # Should be caught by cycle detection — defensive
            return {"path": [], "length": 0, "error": "topo_sort_failed"}

        # Longest-path DP in topological order
        # dist[n] = length of longest chain ending at n
        # parent[n] = predecessor on that longest chain
        dist: Dict[str, int] = {n: 1 for n in nodes}
        parent: Dict[str, Optional[str]] = {n: None for n in nodes}
        for n in topo:
            for s in succ[n]:
                if dist[n] + 1 > dist[s]:
                    dist[s] = dist[n] + 1
                    parent[s] = n

        # Find the end node with max dist
        end = max(nodes, key=lambda x: dist[x])
        path = []
        cur = end
        while cur is not None:
            path.append(cur)
            cur = parent[cur]
        path.reverse()

        return {
            "path":   path,
            "length": len(path),
            "error":  None,
        }

    # ──────────────────────────────────────────────────────────────────
    # Spec entry: identify_blocked_initiatives
    # ──────────────────────────────────────────────────────────────────

    def identify_blocked_initiatives(self) -> Dict[str, Any]:
        """Find initiatives whose predecessors are not yet COMPLETED.

        Returns:
            {"blocked": [{initiative_id, blocked_by: [predecessor_ids]}],
             "summary": {total_initiatives, blocked_count, unblocked_count}}
        """
        all_inits = self._all() or []
        init_by_id = {i.get("initiative_id"): i for i in all_inits if isinstance(i, dict)}

        blocked: List[Dict[str, Any]] = []
        unknown_deps: Set[str] = set()

        for init in all_inits:
            if not isinstance(init, dict):
                continue
            init_id = init.get("initiative_id")
            if not init_id:
                continue
            # Skip already-completed initiatives — they're not blocked, they're done
            if init.get("status") in ("COMPLETED", "CANCELLED"):
                continue

            preds = self._deps(init_id) or []
            blocking_preds: List[str] = []
            for pred_id in preds:
                pred = init_by_id.get(pred_id)
                if pred is None:
                    unknown_deps.add(pred_id)
                    blocking_preds.append(pred_id)
                    continue
                if pred.get("status") != "COMPLETED":
                    blocking_preds.append(pred_id)

            if blocking_preds:
                blocked.append({
                    "initiative_id": init_id,
                    "current_stage": init.get("stage"),
                    "current_status": init.get("status"),
                    "blocked_by":    blocking_preds,
                })

        active_count = sum(1 for i in all_inits
                            if isinstance(i, dict)
                            and i.get("status") not in ("COMPLETED", "CANCELLED"))

        return {
            "blocked":           blocked,
            "summary": {
                "total_active":      active_count,
                "blocked_count":     len(blocked),
                "unblocked_count":   active_count - len(blocked),
            },
            "meta": {
                "unknown_dependencies": sorted(unknown_deps),
                "generated_at":         datetime.now(timezone.utc).isoformat(),
            },
        }

    # ──────────────────────────────────────────────────────────────────
    # Spec entry: risk_propagation
    # ──────────────────────────────────────────────────────────────────

    def risk_propagation(self, initiative_id: str) -> Dict[str, Any]:
        """What's blocked downstream if this initiative slips?

        Returns:
            {"initiative_id", "downstream_blocked": [ids],
             "downstream_count", "risk_level"}
        """
        if not initiative_id:
            return {}

        # Build successor graph from all initiatives
        all_inits = self._all() or []
        nodes = [i.get("initiative_id") for i in all_inits if isinstance(i, dict) and i.get("initiative_id")]
        succ: Dict[str, List[str]] = defaultdict(list)
        for n in nodes:
            for pred in (self._deps(n) or []):
                if pred in nodes:
                    succ[pred].append(n)

        # BFS forward from initiative_id
        downstream: Set[str] = set()
        queue = deque([initiative_id])
        visited = {initiative_id}
        while queue:
            cur = queue.popleft()
            for s in succ.get(cur, []):
                if s not in visited:
                    visited.add(s)
                    downstream.add(s)
                    queue.append(s)

        risk_level = self._classify_risk(len(downstream))
        return {
            "initiative_id":      initiative_id,
            "downstream_blocked": sorted(downstream),
            "downstream_count":   len(downstream),
            "risk_level":         risk_level,
            "meta": {
                "risk_thresholds": {
                    "MEDIUM": RISK_MEDIUM_MAX,
                    "HIGH":   RISK_HIGH_MAX,
                },
                "generated_at": datetime.now(timezone.utc).isoformat(),
            },
        }

    def _classify_risk(self, count: int) -> str:
        if count <= RISK_LOW_MAX:
            return "LOW"
        if count <= RISK_MEDIUM_MAX:
            return "MEDIUM"
        if count <= RISK_HIGH_MAX:
            return "HIGH"
        return "CRITICAL"


# ─────────────────────────────────────────────────────────────────────
# Self-test
# ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("A2Z MIS 360 — utils.initiative_dependency self-test")

    assert RISK_LEVELS == ["LOW", "MEDIUM", "HIGH", "CRITICAL"]
    print(f"  ✅ risk levels: {RISK_LEVELS}")

    # ── Empty initiative set ─────────────────────────────────────────
    eng = DependencyIntelligenceEngine()
    r = eng.compute_critical_path()
    assert r["path"] == []
    assert r["length"] == 0
    print(f"  ✅ empty initiative set → empty path")

    # ── Build dependency graph: A → B → C → D (linear) ───────────────
    inits = {
        "A": {"initiative_id": "A", "status": "COMPLETED"},
        "B": {"initiative_id": "B", "status": "COMPLETED", "stage": "BUILD"},
        "C": {"initiative_id": "C", "status": "IN_PROGRESS", "stage": "DESIGN"},
        "D": {"initiative_id": "D", "status": "PROPOSED", "stage": "IDEATION"},
    }
    deps = {"A": [], "B": ["A"], "C": ["B"], "D": ["C"]}
    eng2 = DependencyIntelligenceEngine(
        initiative_lookup_fn=lambda i: inits.get(i),
        all_initiatives_fn=lambda: list(inits.values()),
        dependency_lookup_fn=lambda i: deps.get(i, []),
    )

    # No cycles
    cyc = eng2.detect_cycles()
    assert cyc["has_cycles"] is False
    print(f"  ✅ no cycles in linear graph")

    # Critical path = A→B→C→D (length 4)
    r = eng2.compute_critical_path()
    assert r["path"] == ["A", "B", "C", "D"]
    assert r["length"] == 4
    print(f"  ✅ critical path: {' → '.join(r['path'])} (length {r['length']})")

    # ── Cycle detection ──────────────────────────────────────────────
    inits_cyc = {
        "X": {"initiative_id": "X", "status": "IN_PROGRESS"},
        "Y": {"initiative_id": "Y", "status": "IN_PROGRESS"},
        "Z": {"initiative_id": "Z", "status": "IN_PROGRESS"},
    }
    deps_cyc = {"X": ["Z"], "Y": ["X"], "Z": ["Y"]}    # cycle X→Z→Y→X
    eng_cyc = DependencyIntelligenceEngine(
        initiative_lookup_fn=lambda i: inits_cyc.get(i),
        all_initiatives_fn=lambda: list(inits_cyc.values()),
        dependency_lookup_fn=lambda i: deps_cyc.get(i, []),
    )
    cyc = eng_cyc.detect_cycles()
    assert cyc["has_cycles"] is True
    print(f"  ✅ cycle detected: {len(cyc['cycles'])} cycle(s) found")

    # Critical path with cycles → error (Rule 6)
    r = eng_cyc.compute_critical_path()
    assert r["error"] is not None
    assert "cycles" in r["error"]
    print(f"  ✅ cycles → critical_path returns error (no silent hang)")

    # ── identify_blocked_initiatives ─────────────────────────────────
    # In linear A→B→C→D: A,B done; C,D active
    # C's pred B is COMPLETED → C is unblocked
    # D's pred C is IN_PROGRESS → D is blocked
    r = eng2.identify_blocked_initiatives()
    blocked_ids = [b["initiative_id"] for b in r["blocked"]]
    assert "D" in blocked_ids
    assert "C" not in blocked_ids
    assert r["summary"]["total_active"] == 2
    assert r["summary"]["blocked_count"] == 1
    print(f"  ✅ blocked detection: D blocked by C; C is unblocked")

    # ── Unknown dependencies surfaced ────────────────────────────────
    inits_unk = {
        "P": {"initiative_id": "P", "status": "IN_PROGRESS"},
    }
    deps_unk = {"P": ["MISSING_INIT"]}
    eng_unk = DependencyIntelligenceEngine(
        initiative_lookup_fn=lambda i: inits_unk.get(i),
        all_initiatives_fn=lambda: list(inits_unk.values()),
        dependency_lookup_fn=lambda i: deps_unk.get(i, []),
    )
    r = eng_unk.identify_blocked_initiatives()
    assert "MISSING_INIT" in r["meta"]["unknown_dependencies"]
    print(f"  ✅ unknown dep surfaced in meta: {r['meta']['unknown_dependencies']}")

    # ── risk_propagation ─────────────────────────────────────────────
    # In A→B→C→D: if A slips, downstream = {B, C, D} = 3 initiatives blocked → HIGH
    r = eng2.risk_propagation("A")
    assert r["downstream_count"] == 3
    assert sorted(r["downstream_blocked"]) == ["B", "C", "D"]
    assert r["risk_level"] == "HIGH"   # 3 ≤ 5 → HIGH
    print(f"  ✅ risk_propagation(A): {r['downstream_count']} downstream → {r['risk_level']}")

    # ── Risk level classification ────────────────────────────────────
    # D has no successors → 0 → LOW
    r = eng2.risk_propagation("D")
    assert r["downstream_count"] == 0
    assert r["risk_level"] == "LOW"
    print(f"  ✅ leaf node: 0 downstream → LOW")

    # ── Critical risk: many successors ───────────────────────────────
    # Build a fan-out: HUB → 6 children
    inits_fan = {f"K{i}": {"initiative_id": f"K{i}", "status": "IN_PROGRESS"}
                  for i in range(7)}
    deps_fan = {"K0": []}
    deps_fan.update({f"K{i}": ["K0"] for i in range(1, 7)})
    eng_fan = DependencyIntelligenceEngine(
        initiative_lookup_fn=lambda i: inits_fan.get(i),
        all_initiatives_fn=lambda: list(inits_fan.values()),
        dependency_lookup_fn=lambda i: deps_fan.get(i, []),
    )
    r = eng_fan.risk_propagation("K0")
    assert r["downstream_count"] == 6
    assert r["risk_level"] == "CRITICAL"   # > 5
    print(f"  ✅ fan-out hub: 6 downstream → CRITICAL")

    print("\n  ALL TESTS PASSED")
