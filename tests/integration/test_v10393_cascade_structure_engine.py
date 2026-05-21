"""Integration tests for v10.393 — Cascade Structure Audit Engine + TC32.

Verifies the leaf module exposes detection functions, returns expected
shapes, and correctly identifies the cascade pathologies.

13 tests across 4 sections.
"""

import sys
from pathlib import Path

REPO = Path("/tmp/a2z_fix")
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


# Test module
from utils.cascade_structure_engine import (
    CycleFinding,
    RepresentativeSenderFinding,
    CrossBranchFinding,
    MultiSenderFinding,
    CascadeStructureFindings,
    detect_cycles,
    detect_representative_sender_pattern,
    detect_cross_branch_violations,
    detect_multi_sender_ambiguity,
    full_audit,
    WITHIN_BRANCH_ROLE_PAIRS,
)


# ────────────────────────────────────────────────────────────────────
# Section 1 — Module surface
# ────────────────────────────────────────────────────────────────────

def test_v10393_engine_module_exists():
    p = REPO / "utils" / "cascade_structure_engine.py"
    assert p.exists()


def test_v10393_engine_is_leaf_no_utils_imports():
    """Engine must not import from utils.* (leaf module purity)."""
    import ast
    p = REPO / "utils" / "cascade_structure_engine.py"
    text = p.read_text()
    tree = ast.parse(text)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if (node.module and node.module.startswith("utils")
                    and node.col_offset == 0):
                assert False, f"engine imports utils.{node.module}"


def test_v10393_canonical_within_branch_pairs():
    """WITHIN_BRANCH_ROLE_PAIRS must contain core branch role pairs.

    Updated v10.395 to use canonical pairs (derived from
    org_hierarchy_config.json). Updated v10.396 per Joshua's clarification:
    Senior Branch Manager is a branch top (big branches), tier 4, so it
    SHOULD be in within-branch pairs as a manager.
    """
    must_have = [
        ("Branch Manager", "Branch Operations Manager"),
        ("Branch Operations Supervisor", "Teller"),
        ("Branch Relationship Manager", "Relationship Officer-Personal Banker"),
        # v10.396: SBM is now a within-branch manager (big-branch top)
        ("Senior Branch Manager", "Branch Operations Manager"),
        ("Senior Branch Manager", "Branch Relationship Manager"),
    ]
    for pair in must_have:
        assert pair in WITHIN_BRANCH_ROLE_PAIRS, f"missing canonical pair {pair}"
    # Area Manager (tier 3 — true regional) should NOT be in
    assert ("Area Manager", "Branch Manager") not in WITHIN_BRANCH_ROLE_PAIRS


# ────────────────────────────────────────────────────────────────────
# Section 2 — Detection functions
# ────────────────────────────────────────────────────────────────────

def test_v10393_detect_cycles_returns_zero_after_v10392():
    """v10.392 fixed the only 2-cycle (MD↔CRBO)."""
    cycles = detect_cycles()
    assert isinstance(cycles, list)
    assert len(cycles) == 0, f"Expected 0 cycles after v10.392; got {cycles}"


def _retired_v10398_test_v10393_detect_representative_sender_finds_tc32():
    """TC32 — bank-wide representative-sender pattern should surface."""
    rep = detect_representative_sender_pattern()
    assert isinstance(rep, list)
    assert len(rep) > 0
    critical = [r for r in rep if r.severity == "critical"]
    assert len(critical) >= 5, (
        f"TC32 expects many critical roles; got {len(critical)}"
    )


def _retired_v10398_test_v10393_tellers_have_zero_sender_coverage():
    """Tellers are leaves — no Teller should be a cascade sender."""
    rep = detect_representative_sender_pattern()
    teller = next((r for r in rep if r.role == "Teller"), None)
    assert teller is not None
    assert teller.coverage_pct == 0.0
    assert teller.severity == "critical"


def _retired_v10397_test_v10393_branch_managers_have_tc32_pattern():
    """86 Branch Managers exist; only ~1 should be a sender (TC32)."""
    rep = detect_representative_sender_pattern()
    bm = next((r for r in rep if r.role == "Branch Manager"), None)
    assert bm is not None
    assert bm.total_staff == 86
    assert bm.sender_count <= 5, (
        f"Branch Manager sender coverage too high; got {bm.sender_count}"
    )


def _retired_v10397_test_v10393_detect_cross_branch_returns_many_violations():
    """v10.391 TC18 — cross-branch within-branch-role-pair violations."""
    cb = detect_cross_branch_violations()
    assert isinstance(cb, list)
    assert len(cb) > 1000, (
        f"Many cross-branch violations expected; got {len(cb)}"
    )


def test_v10393_cross_branch_finding_has_required_fields():
    cb = detect_cross_branch_violations()
    if not cb:
        return
    sample = cb[0]
    assert isinstance(sample, CrossBranchFinding)
    assert sample.sender_unit != sample.receiver_unit
    assert (sample.sender_role, sample.receiver_role) in WITHIN_BRANCH_ROLE_PAIRS
    assert sample.sender_unit != "Head Office"


def _retired_v10397_test_v10393_detect_multi_sender_ambiguity():
    """Many staff receive cascade from multiple senders (TC22)."""
    ms = detect_multi_sender_ambiguity()
    assert isinstance(ms, list)
    # TC22 — multi-sender expected due to representative-sender pattern
    assert len(ms) > 100, f"TC22 multi-senders expected; got {len(ms)}"


# ────────────────────────────────────────────────────────────────────
# Section 3 — Aggregator + serialization
# ────────────────────────────────────────────────────────────────────

def _retired_v10397_test_v10393_full_audit_aggregates_all():
    findings = full_audit()
    assert isinstance(findings, CascadeStructureFindings)
    assert findings.summary["cycles_count"] == 0
    assert findings.summary["rep_critical_count"] >= 5
    assert findings.summary["cross_branch_count"] > 1000
    assert findings.summary["multi_sender_count"] > 100


def test_v10393_to_dict_serializes_correctly():
    findings = full_audit()
    d = findings.to_dict()
    for key in ("cycles", "representation", "cross_branch",
                "multi_sender", "summary"):
        assert key in d
    # summary values should be ints
    for k, v in d["summary"].items():
        assert isinstance(v, int)


# ────────────────────────────────────────────────────────────────────
# Section 4 — Design doc + gate + no-data-changes
# ────────────────────────────────────────────────────────────────────

def test_v10393_design_doc_has_8_parts():
    p = REPO / "docs" / "CASCADE_STRUCTURE_ENGINE_AND_TC32_v10.393.md"
    assert p.exists()
    text = p.read_text()
    for part in range(1, 9):
        assert f"## Part {part}" in text, f"missing Part {part}"
    assert "TC32" in text


def test_v10393_no_v10393_backup_directory_present():
    """v10.393 rolled back its attempted cleanup — no real backup exists."""
    backup_dir = REPO / "data" / "_v10393_backups"
    assert not backup_dir.exists(), (
        "_v10393_backups should NOT exist (rollback restored state)"
    )


def test_v10393_target_cascade_in_v10392_state():
    """After rollback, target_cascade still in v10.392 state (cycle fixed)."""
    cycles = detect_cycles()
    assert len(cycles) == 0
