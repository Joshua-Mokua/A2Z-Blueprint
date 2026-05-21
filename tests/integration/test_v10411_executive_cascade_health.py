"""Integration tests for v10.411 — E5 Executive Cascade Health Dashboard.

Per QA standards Enhancement #5: bank-wide cascade health visibility.

13 tests across 4 sections.
"""

import sys
from pathlib import Path

REPO = Path("/tmp/a2z_fix")
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


# ────────────────────────────────────────────────────────────────────
# Section 1 — Engine module
# ────────────────────────────────────────────────────────────────────

def test_v10411_engine_module_exists():
    path = REPO / "utils" / "cascade_health_engine.py"
    assert path.exists()
    text = path.read_text()
    for needed in (
        "def bank_health_summary",
        "def health_by_pillar",
        "def health_by_sbu",
        "def health_by_kpi",
        "def broken_chains",
        "def stale_entries",
        "class BankHealthSummary",
        "class PillarHealth",
        "class SBUHealth",
        "class KPIHealth",
        "class BrokenChain",
        "class StaleEntry",
    ):
        assert needed in text, f"Missing: {needed}"


def test_v10411_engine_has_defensive_iter():
    """_iter_cascade_entries skips meta-keys / deadlines / globals."""
    text = (REPO / "utils" / "cascade_health_engine.py").read_text()
    assert "def _iter_cascade_entries" in text
    assert 'startswith("_")' in text
    assert 'startswith("deadline|")' in text


# ────────────────────────────────────────────────────────────────────
# Section 2 — Engine behavior
# ────────────────────────────────────────────────────────────────────

def test_v10411_bank_summary_works():
    for k in list(sys.modules):
        if "cascade_health" in k:
            del sys.modules[k]
    from utils.cascade_health_engine import bank_health_summary
    s = bank_health_summary("2026")
    assert s.cascade_entries >= 0
    assert 0 <= s.overall_health_score <= 100
    assert s.fully_allocated_count + s.partial_allocated_count + s.under_allocated_count == s.cascade_entries


def test_v10411_pillar_health_returns_canonical_pillars():
    for k in list(sys.modules):
        if "cascade_health" in k:
            del sys.modules[k]
    from utils.cascade_health_engine import health_by_pillar
    p = health_by_pillar("2026")
    assert len(p) > 0
    # Should include at least Financial (highest bank weight)
    pillar_names = {x.pillar for x in p}
    assert "Financial" in pillar_names or "Unmapped" in pillar_names


def test_v10411_sbu_health_returns_chiefs():
    for k in list(sys.modules):
        if "cascade_health" in k or "manager_rollup" in k:
            del sys.modules[k]
    from utils.cascade_health_engine import health_by_sbu
    s = health_by_sbu("2026")
    assert len(s) > 0
    # At least one chief should have direct reports
    has_subs = any(x.total_direct_reports > 0 for x in s)
    assert has_subs, "No chiefs with subordinates — canonical fallback may be broken"


def test_v10411_health_by_kpi_lists_kpis():
    for k in list(sys.modules):
        if "cascade_health" in k:
            del sys.modules[k]
    from utils.cascade_health_engine import health_by_kpi
    kh = health_by_kpi("2026")
    assert len(kh) > 0


def test_v10411_broken_chains_callable():
    for k in list(sys.modules):
        if "cascade_health" in k or "manager_rollup" in k:
            del sys.modules[k]
    from utils.cascade_health_engine import broken_chains
    bc = broken_chains("2026", max_results=5)
    # Could be empty (good!) or have entries — both OK
    assert isinstance(bc, list)


def test_v10411_stale_entries_callable():
    for k in list(sys.modules):
        if "cascade_health" in k:
            del sys.modules[k]
    from utils.cascade_health_engine import stale_entries
    se = stale_entries("2026", days=30)
    assert isinstance(se, list)


# ────────────────────────────────────────────────────────────────────
# Section 3 — Cascade page wiring
# ────────────────────────────────────────────────────────────────────

def test_v10411_cascade_imports_engine():
    text = (REPO / "pages" / "12_cascade.py").read_text()
    assert "from utils.cascade_health_engine import" in text


def test_v10411_subtab_map_has_cascade_health():
    text = (REPO / "pages" / "12_cascade.py").read_text()
    assert '"cascade_health"' in text
    assert "🩺 Executive health" in text


def test_v10411_executive_health_ui_present():
    text = (REPO / "pages" / "12_cascade.py").read_text()
    assert "Executive cascade health" in text
    assert "Broken cascade chains" in text
    assert "Health by strategic pillar" in text or "🎯 Health by" in text


# ────────────────────────────────────────────────────────────────────
# Section 4 — State + Gate
# ────────────────────────────────────────────────────────────────────

def test_v10411_engine_state_preserved():
    for k in list(sys.modules):
        if "cascade" in k:
            del sys.modules[k]
    from utils.cascade_structure_engine import full_audit
    s = full_audit().summary
    assert s["cycles_count"] == 0
    assert s["cross_branch_count"] == 0
    assert s["multi_sender_count"] == 0
    assert s["rep_critical_count"] == 0


def test_v10411_g297_passes():
    sys.path.insert(0, str(REPO / "scripts"))
    for k in list(sys.modules):
        if k.startswith("audit"):
            del sys.modules[k]
    from audit import gate_v10411_executive_cascade_health_dashboard
    r = gate_v10411_executive_cascade_health_dashboard()
    assert r["passed"], r.get("violations")
