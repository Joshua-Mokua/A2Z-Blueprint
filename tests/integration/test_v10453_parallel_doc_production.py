"""Integration tests for v10.453 — Parallel Doc Production.

88 docs generated (22 × 4 modules). Avg health 43.6% → 61.9% (+18.3pp).
"""

import sys
from pathlib import Path

import pytest

REPO = Path("/tmp/a2z_fix")
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


@pytest.fixture(scope="module")
def all_modules():
    for k in list(sys.modules):
        if "module_doctrine_audit" in k or "cascade_bsc_360" in k:
            del sys.modules[k]
    from utils.module_doctrine_audit import all_modules_audit
    return all_modules_audit()


def test_v10453_generator_exists():
    assert (REPO / "utils" / "module_doc_generator.py").exists()


def test_v10453_22_generators_present():
    text = (REPO / "utils" / "module_doc_generator.py").read_text()
    for gen in ("operational_dependencies", "architecture", "performance",
                "security_review", "redundancy_scan", "orphaned_scan",
                "scalability", "data_duplication", "data_relationships",
                "sync_gaps", "data_lineage", "usage_audit", "pain_points",
                "approval_bottlenecks", "adoption_report", "hidden_deps",
                "dependencies", "stale_scan", "dead_workflows",
                "data_consistency", "security_drift", "qa_gap_analysis"):
        assert f"def gen_{gen}" in text, f"Missing generator: gen_{gen}"


def test_v10453_doc_generators_registry():
    text = (REPO / "utils" / "module_doc_generator.py").read_text()
    assert "DOC_GENERATORS = {" in text


def test_v10453_all_4_modules_have_docs():
    docs_dir = REPO / "docs"
    for module in ("admin", "hr", "bsc_cascade", "credit"):
        produced = list(docs_dir.glob(f"{module}_*.md"))
        assert len(produced) >= 20, f"{module} only has {len(produced)} docs"


def test_v10453_88_total_docs():
    docs_dir = REPO / "docs"
    total = 0
    for module in ("admin", "hr", "bsc_cascade", "credit"):
        total += len(list(docs_dir.glob(f"{module}_*.md")))
    assert total >= 80, f"Only {total} total module docs"


def test_v10453_key_docs_have_content():
    """Critical docs aren't stubs - check they have non-trivial content."""
    for module in ("admin", "hr", "bsc_cascade", "credit"):
        for doc in ("architecture", "security_review", "qa_gap_analysis"):
            path = REPO / "docs" / f"{module}_{doc}.md"
            assert path.exists()
            content = path.read_text()
            assert len(content) > 500, f"{module}_{doc}.md too short ({len(content)} chars)"


# ── Health uplift (slow — fixture) ──────────────────────────────────

def test_v10453_admin_health_above_60(all_modules):
    assert all_modules.modules["admin"].doctrine_health_pct >= 60.0


def test_v10453_hr_health_above_55(all_modules):
    assert all_modules.modules["hr"].doctrine_health_pct >= 55.0


def test_v10453_bsc_cascade_above_60(all_modules):
    assert all_modules.modules["bsc_cascade"].doctrine_health_pct >= 60.0


def test_v10453_credit_above_40(all_modules):
    """Credit was 30.4%, should rise to >40% with docs."""
    assert all_modules.modules["credit"].doctrine_health_pct >= 40.0


def test_v10453_avg_health_lifted(all_modules):
    """Avg honest health should be >=55% after doc production."""
    assert all_modules.avg_doctrine_health_pct >= 55.0


def test_v10453_crisis_count_reduced(all_modules):
    """Crisis modules (<50%) should drop to <=1."""
    assert len(all_modules.crisis_modules) <= 1


def test_v10453_phase_1_strong_after_docs(all_modules):
    """Phase 1 should be 80%+ for all modules now that docs exist."""
    for key, m in all_modules.modules.items():
        assert m.phase_1.score_pct >= 80.0, (
            f"{key} Phase 1 = {m.phase_1.score_pct}%"
        )


def test_v10453_phase_8_strong_after_scan_docs(all_modules):
    """Phase 8 should be 80%+ for all modules with scan docs added."""
    for key, m in all_modules.modules.items():
        assert m.phase_8.score_pct >= 80.0, (
            f"{key} Phase 8 = {m.phase_8.score_pct}%"
        )


def test_v10453_no_module_certified_yet(all_modules):
    """Documents alone don't certify - need command centres, Flexcube, etc."""
    assert all_modules.certified_count == 0


# ── Upstream ────────────────────────────────────────────────────────

def test_v10453_360_harmony_preserved():
    for k in list(sys.modules):
        if "cascade_bsc_360_engine" in k:
            del sys.modules[k]
    from utils.cascade_bsc_360_engine import cascade_bsc_360_audit
    assert cascade_bsc_360_audit().overall_harmony_pct == 100.0


def test_v10453_bsc_rescue_preserved():
    for k in list(sys.modules):
        if "bsc_audit_engine" in k:
            del sys.modules[k]
    from utils.bsc_audit_engine import bsc_full_audit
    assert bsc_full_audit().overall_health_pct == 100.0


def test_v10453_g339_passes():
    sys.path.insert(0, str(REPO / "scripts"))
    for k in list(sys.modules):
        if k.startswith("audit"):
            del sys.modules[k]
    from audit import gate_v10453_parallel_doc_production
    r = gate_v10453_parallel_doc_production()
    assert r["passed"], r.get("violations")
