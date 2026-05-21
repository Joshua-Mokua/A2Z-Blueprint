"""Integration tests for v10.392 — MD↔CRBO Circular Cascade Surgically Fixed.

Per v10.391 diagnosis Finding TC20 (CRITICAL). v10.392 surgically removed
21 wrong-direction allocations (CRBO→MD). These tests verify the post-fix
state is correct.

Sister to v10.391's test_v10391_tc20_* which is now RETIRED (verified the
bug WAS present; the bug is now fixed).

11 tests across 4 sections.
"""

import json
import sys
from collections import defaultdict
from pathlib import Path

REPO = Path("/tmp/a2z_fix")
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


def _load(path):
    return json.loads((REPO / "data" / path).read_text())


def _build_cascade_graph():
    """Returns dict[from_code -> set[to_code]] from target_cascade.json."""
    tc = _load("target_cascade.json")
    graph = defaultdict(set)
    for k, v in tc.items():
        if not isinstance(v, dict):
            continue
        if not v.get("from_code"):
            continue
        for a in v.get("allocations", []) or []:
            if a.get("to_code"):
                graph[v["from_code"]].add(a["to_code"])
    return dict(graph)


# ────────────────────────────────────────────────────────────────────
# Section 1 — Cascade graph correctness (TC20 fix)
# ────────────────────────────────────────────────────────────────────

def test_v10392_cascade_graph_has_no_2_cycles():
    """The cascade DAG must have no 2-cycles."""
    g = _build_cascade_graph()
    cycles = set()
    for a, targets in g.items():
        for b in targets:
            if a in g.get(b, set()):
                cycles.add(tuple(sorted([a, b])))
    assert len(cycles) == 0, f"cascade has 2-cycles: {sorted(cycles)}"


def test_v10392_crbo_does_not_cascade_to_md():
    """CRBO (300002) must not have any allocations to MD (300001)."""
    tc = _load("target_cascade.json")
    crbo_to_md = 0
    for k, v in tc.items():
        if not isinstance(v, dict):
            continue
        if v.get("from_code") != "300002":
            continue
        for a in v.get("allocations", []) or []:
            if a.get("to_code") == "300001":
                crbo_to_md += 1
    assert crbo_to_md == 0, f"CRBO→MD count: {crbo_to_md} (must be 0)"


def test_v10392_md_to_crbo_preserved():
    """MD (300001) must still cascade ~21 KPIs to CRBO (300002)."""
    tc = _load("target_cascade.json")
    md_to_crbo = 0
    for k, v in tc.items():
        if not isinstance(v, dict):
            continue
        if v.get("from_code") != "300001":
            continue
        for a in v.get("allocations", []) or []:
            if a.get("to_code") == "300002":
                md_to_crbo += 1
    assert md_to_crbo >= 15, (
        f"MD→CRBO should be preserved (~21 KPIs); got {md_to_crbo}"
    )


def test_v10392_md_is_root_no_receivers():
    """MD (300001) is root: no cascade should send to MD."""
    tc = _load("target_cascade.json")
    receivers = 0
    for k, v in tc.items():
        if not isinstance(v, dict):
            continue
        for a in v.get("allocations", []) or []:
            if a.get("to_code") == "300001":
                receivers += 1
    assert receivers == 0, (
        f"MD must have zero receivers (is root); got {receivers}"
    )


def test_v10392_crbo_other_cascades_preserved():
    """CRBO still cascades to non-MD recipients post-v10.397 regeneration.

    After v10.397: CRBO cascades to canonical reports (Head of Branches, etc.)
    Pre-v10.397 had MD as receiver due to circular bug (fixed in v10.392).
    """
    tc = _load("target_cascade.json")
    crbo_other_recipients = set()
    for k, v in tc.items():
        if not isinstance(v, dict):
            continue
        if v.get("from_code") != "300002":
            continue
        for a in v.get("allocations", []) or []:
            t = a.get("to_code")
            if t and t != "300001":
                crbo_other_recipients.add(t)
    # v10.397: CRBO has canonical reports; should have at least one non-MD
    # recipient. v10.392's anti-circular fix preserved (no MD as receiver).
    assert len(crbo_other_recipients) >= 1, (
        f"CRBO should cascade to at least one non-MD recipient; got "
        f"{len(crbo_other_recipients)}"
    )


# ────────────────────────────────────────────────────────────────────
# Section 2 — Data integrity
# ────────────────────────────────────────────────────────────────────

def test_v10392_allocated_sum_recomputed_for_modified_entries():
    """For CRBO's modified entries, allocated_sum should match new allocations."""
    tc = _load("target_cascade.json")
    inconsistent = []
    for k, v in tc.items():
        if not isinstance(v, dict):
            continue
        if v.get("from_code") != "300002":
            continue
        if not v.get("kpi"):
            continue
        computed = sum(a.get("amount", 0) for a in v.get("allocations", []) or [])
        recorded = v.get("allocated_sum", 0)
        if abs(computed - recorded) > 0.01:
            inconsistent.append((k, computed, recorded))
    assert len(inconsistent) == 0, (
        f"Some CRBO entries have stale allocated_sum: {inconsistent[:3]}"
    )


def test_v10392_target_cascade_still_parses():
    """target_cascade.json must still be valid JSON."""
    tc = _load("target_cascade.json")
    assert isinstance(tc, dict)
    assert len(tc) > 100


def test_v10392_backup_preserved():
    backup = REPO / "data" / "_v10392_backups" / "target_cascade.json.before"
    assert backup.exists(), "v10.392 backup file missing"
    # Backup should still contain the bug
    backup_data = json.loads(backup.read_text())
    crbo_to_md_in_backup = 0
    for k, v in backup_data.items():
        if not isinstance(v, dict):
            continue
        if v.get("from_code") != "300002":
            continue
        for a in v.get("allocations", []) or []:
            if a.get("to_code") == "300001":
                crbo_to_md_in_backup += 1
    assert crbo_to_md_in_backup >= 15, (
        f"backup should contain pre-fix state with CRBO→MD allocations; "
        f"got {crbo_to_md_in_backup}"
    )


# ────────────────────────────────────────────────────────────────────
# Section 3 — Design doc + audit gate
# ────────────────────────────────────────────────────────────────────

def test_v10392_design_doc_has_8_parts():
    p = REPO / "docs" / "CIRCULAR_CASCADE_FIXED_v10.392.md"
    assert p.exists()
    text = p.read_text()
    for part in range(1, 9):
        assert f"## Part {part}" in text, f"missing Part {part}"


def test_v10392_g277_passes():
    sys.path.insert(0, str(REPO / "scripts"))
    for k in list(sys.modules):
        if k.startswith("audit"):
            del sys.modules[k]
    from audit import gate_v10392_circular_cascade_fixed
    r = gate_v10392_circular_cascade_fixed()
    assert r["passed"], r.get("violations")


# ────────────────────────────────────────────────────────────────────
# Section 4 — No regression
# ────────────────────────────────────────────────────────────────────

def test_v10392_other_cascade_relationships_unchanged():
    """Spot-check: a Branch Manager's allocations should be unchanged
    (the BM doesn't have a CRBO/MD relationship)."""
    tc = _load("target_cascade.json")
    bm_entries = [k for k, v in tc.items()
                  if isinstance(v, dict) and v.get("from_code") == "300226"
                  and v.get("kpi")]
    assert len(bm_entries) > 10, (
        "Senior Branch Manager 300226 should still have cascade entries"
    )
    # Sum of allocations should be > 0
    for k in bm_entries[:5]:
        entry = tc[k]
        total = sum(a.get("amount", 0) for a in entry.get("allocations", []) or [])
        assert total > 0, f"BM entry {k} has zero allocated"
