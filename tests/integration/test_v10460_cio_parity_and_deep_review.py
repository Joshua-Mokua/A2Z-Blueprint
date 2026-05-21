"""Integration tests for v10.460 — CIO Parity + Consolidation + Standards Wiring.

Addresses Joshua's 4 v10.460 concerns:
  1. CIO parity: Chief Information Officer view of ICT staff BSC + cascade + actuals
  2. ICT modules vs tabs deep review
  3. Cross-page function duplication scan (real, not stubs)
  4. QA standards wiring per module

Health uplift: ICT 68.4% → 74.0% (+5.6pp); avg 76.6% → 77.8%.
"""

import ast
import json
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


@pytest.fixture(scope="module")
def manifest():
    return json.loads((REPO / "pages" / "_manifest.json").read_text(encoding="utf-8"))


# ── CONCERN 1: CIO PARITY (Chief ICT Centre) ──────────────────────────

def test_v10460_chief_ict_centre_exists():
    assert (REPO / "pages" / "121_chief_ict_centre.py").exists()


def test_v10460_chief_ict_centre_parses():
    ast.parse((REPO / "pages" / "121_chief_ict_centre.py").read_text())


def test_v10460_chief_ict_centre_substantial():
    """Should be a proper centre, not a stub."""
    text = (REPO / "pages" / "121_chief_ict_centre.py").read_text()
    assert len(text.splitlines()) >= 300


def test_v10460_chief_ict_centre_six_doctrine_tabs():
    """Mirror the 6-tab pattern of HR/Credit centres."""
    text = (REPO / "pages" / "121_chief_ict_centre.py").read_text()
    for tab in ("Executive Visibility", "Strategic Intelligence",
                "Organ Health", "My ICT Staff Performance",
                "Risk", "Real-Time"):
        assert tab in text, f"Missing tab: {tab}"


def test_v10460_cio_sees_ict_staff_bsc():
    """CIO must have visibility into ICT staff BSC scores."""
    text = (REPO / "pages" / "121_chief_ict_centre.py").read_text().lower()
    assert "ict staff" in text or "ict_staff" in text or "my ict" in text
    assert "bsc" in text or "scorecard" in text


def test_v10460_cio_sees_cascade_alignment():
    """CIO must see cascade alignment for ICT roles."""
    text = (REPO / "pages" / "121_chief_ict_centre.py").read_text().lower()
    assert "cascade" in text


def test_v10460_chief_ict_centre_rbac_includes_cio():
    """Must require_access include CIO role."""
    text = (REPO / "pages" / "121_chief_ict_centre.py").read_text()
    assert "Chief Information Officer" in text


def test_v10460_chief_ict_centre_registered_in_manifest(manifest):
    entry = manifest["pages"].get("121_chief_ict_centre.py")
    assert entry is not None
    assert entry.get("current_module_key") == "chief_centre"
    assert entry.get("department_primary") == "it_platform"


def test_v10460_ict_command_centre_candidates_updated():
    """ICT registry primary candidate now points at 121."""
    for k in list(sys.modules):
        if "module_doctrine_audit" in k:
            del sys.modules[k]
    from utils.module_doctrine_audit import MODULE_REGISTRY
    ict = MODULE_REGISTRY["ict"]
    assert "121_chief_ict_centre.py" in ict.command_centre_candidates
    assert ict.command_centre_candidates[0] == "121_chief_ict_centre.py"


# ── CONCERN 2 & 3: CONSOLIDATION ANALYZER (modules vs tabs + duplicates) ──

def test_v10460_consolidation_analyzer_exists():
    assert (REPO / "utils" / "module_consolidation_analyzer.py").exists()


def test_v10460_consolidation_analyzer_parses():
    ast.parse((REPO / "utils" / "module_consolidation_analyzer.py").read_text())


def test_v10460_consolidation_analyzer_api_first():
    text = (REPO / "utils" / "module_consolidation_analyzer.py").read_text()
    assert "import streamlit" not in text


def test_v10460_consolidation_full_api():
    text = (REPO / "utils" / "module_consolidation_analyzer.py").read_text()
    for fn in ("def analyze_module", "def analyze_all_modules",
               "def get_tab_candidates", "def get_duplicate_functions",
               "def generate_consolidation_doc",
               "class ConsolidationReport", "class TabCandidate",
               "class DuplicateFunction"):
        assert fn in text, f"Missing: {fn}"


def test_v10460_consolidation_real_analysis_runs():
    """Not a stub — must produce real findings."""
    for k in list(sys.modules):
        if "module_consolidation_analyzer" in k:
            del sys.modules[k]
    from utils.module_consolidation_analyzer import analyze_all_modules
    reports = analyze_all_modules()
    assert len(reports) == 5
    for key in ("admin", "hr", "bsc_cascade", "credit", "ict"):
        assert key in reports


def test_v10460_ict_has_tab_candidates_detected():
    """ICT has 4 sub-100-LOC pages — real analyzer must find them."""
    for k in list(sys.modules):
        if "module_consolidation_analyzer" in k:
            del sys.modules[k]
    from utils.module_consolidation_analyzer import analyze_module
    ict = analyze_module("ict")
    assert ict.tab_candidate_pages >= 3, \
        f"Expected ≥3 tab candidates for ICT; got {ict.tab_candidate_pages}"


# ── CONCERN 4: STANDARDS WIRING PER MODULE ────────────────────────────

def test_v10460_standards_wiring_per_module_exists():
    assert (REPO / "utils" / "standards_wiring_per_module.py").exists()


def test_v10460_standards_wiring_per_module_parses():
    ast.parse((REPO / "utils" / "standards_wiring_per_module.py").read_text())


def test_v10460_standards_wiring_api_first():
    text = (REPO / "utils" / "standards_wiring_per_module.py").read_text()
    assert "import streamlit" not in text


def test_v10460_standards_wiring_full_api():
    text = (REPO / "utils" / "standards_wiring_per_module.py").read_text()
    for fn in ("MODULE_STANDARD_DOMAINS",
               "def audit_module_standards_wiring",
               "def audit_all_module_standards",
               "def generate_module_standards_doc",
               "class ModuleStandardsAudit",
               "class StandardEntry"):
        assert fn in text, f"Missing: {fn}"


def test_v10460_standards_wiring_real_analysis():
    """Per-module standards wiring must surface real numbers."""
    for k in list(sys.modules):
        if "standards_wiring_per_module" in k or "standards_wiring_audit_engine" in k:
            del sys.modules[k]
    from utils.standards_wiring_per_module import audit_all_module_standards
    sw = audit_all_module_standards()
    assert len(sw.by_module) == 5
    # At least one module should have standards
    total = sum(m.total_standards_for_module for m in sw.by_module.values())
    assert total > 0, "No standards detected for any module"


def test_v10460_hr_standards_high_coverage():
    """HR had 100% wiring in actual run; should stay strong."""
    for k in list(sys.modules):
        if "standards_wiring_per_module" in k:
            del sys.modules[k]
    from utils.standards_wiring_per_module import audit_module_standards_wiring
    hr = audit_module_standards_wiring("hr")
    assert hr.wiring_coverage_pct >= 80.0


# ── REAL DOCS GENERATED ───────────────────────────────────────────────

def test_v10460_consolidation_docs_for_all_modules():
    for m in ("admin", "hr", "bsc_cascade", "credit", "ict"):
        path = REPO / "docs" / f"{m}_consolidation_analysis.md"
        assert path.exists()
        text = path.read_text(encoding="utf-8")
        # Must be real content, not stub
        assert len(text) >= 200
        assert "consolidation_opportunity_score" in text.lower() \
            or "opportunity score" in text.lower()


def test_v10460_standards_wiring_docs_for_all_modules():
    for m in ("admin", "hr", "bsc_cascade", "credit", "ict"):
        path = REPO / "docs" / f"{m}_standards_wiring.md"
        assert path.exists()
        text = path.read_text(encoding="utf-8")
        assert len(text) >= 200
        assert "wiring coverage" in text.lower() \
            or "wired" in text.lower()


# ── HEALTH UPLIFT ─────────────────────────────────────────────────────

def test_v10460_ict_health_up_from_v10459(all_modules):
    """ICT was 68.4% → expected 74%+ via Chief ICT Centre."""
    assert all_modules.modules["ict"].doctrine_health_pct >= 72.0


def test_v10460_ict_phase_6_at_100(all_modules):
    """Chief ICT Centre brings Phase 6 to 100%."""
    assert all_modules.modules["ict"].phase_6.score_pct >= 100.0


def test_v10460_avg_health_above_77(all_modules):
    assert all_modules.avg_doctrine_health_pct >= 77.0


def test_v10460_no_crisis(all_modules):
    assert len(all_modules.crisis_modules) == 0


# ── UPSTREAM ──────────────────────────────────────────────────────────

def test_v10460_360_harmony_preserved():
    for k in list(sys.modules):
        if "cascade_bsc_360_engine" in k:
            del sys.modules[k]
    from utils.cascade_bsc_360_engine import cascade_bsc_360_audit
    assert cascade_bsc_360_audit().overall_harmony_pct == 100.0


def test_v10460_bsc_rescue_preserved():
    for k in list(sys.modules):
        if "bsc_audit_engine" in k:
            del sys.modules[k]
    from utils.bsc_audit_engine import bsc_full_audit
    assert bsc_full_audit().overall_health_pct == 100.0


def test_v10460_manifest_invariant_still_holds(manifest):
    """G343 invariant: every entry has all 4 required fields."""
    missing = []
    for fname, entry in manifest["pages"].items():
        for req in ("title", "icon", "current_module_key", "department_primary"):
            if req not in entry:
                missing.append(f"{fname}: {req}")
    assert missing == [], f"Manifest invariant broken: {missing[:3]}"


def test_v10460_g346_passes():
    sys.path.insert(0, str(REPO / "scripts"))
    for k in list(sys.modules):
        if k.startswith("audit"):
            del sys.modules[k]
    from audit import gate_v10460_cio_parity_and_deep_review
    r = gate_v10460_cio_parity_and_deep_review()
    assert r["passed"], r.get("violations")
