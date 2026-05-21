"""Integration tests for v10.466 — Four New Chief Centres.

Per Joshua continue v10.465 roadmap. Builds chief centres for the 3
new organs added in v10.465 (Operations, CRM, Reporting & Analytics).

  127_chief_operations_centre.py - COO Grace Makokha (Operations)
  128_chief_retail_centre.py     - CRBO Nicholas Ndegwa (CRM retail)
  129_chief_commercial_centre.py - CCO Emmanuel Kuria (CRM commercial)
  130_head_analytics_centre.py   - Head of Analytics (Reporting)

Per Joshua: CRBO + CCO are PARALLEL centres on same CRM organ
differentiated by reporting hierarchy.

Avg health: 83.0% → 84.0% (+1.0pp). All 3 new organs jumped 3.6-4.6pp.
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


# ── 4 NEW CENTRES EXIST + PARSE ───────────────────────────────────────

@pytest.mark.parametrize("page_name", [
    "127_chief_operations_centre.py",
    "128_chief_retail_centre.py",
    "129_chief_commercial_centre.py",
    "130_head_analytics_centre.py",
])
def test_v10466_centre_exists_and_parses(page_name):
    path = REPO / "pages" / page_name
    assert path.exists(), f"Missing: {page_name}"
    ast.parse(path.read_text(encoding="utf-8"))


@pytest.mark.parametrize("page_name", [
    "127_chief_operations_centre.py",
    "128_chief_retail_centre.py",
    "129_chief_commercial_centre.py",
    "130_head_analytics_centre.py",
])
def test_v10466_centre_six_doctrine_tabs(page_name):
    text = (REPO / "pages" / page_name).read_text()
    for tab in ("Executive Visibility", "Strategic Intelligence",
                "Organ Health", "My Staff Performance",
                "Risk", "Real-Time"):
        assert tab in text, f"{page_name} missing tab: {tab}"


@pytest.mark.parametrize("page_name", [
    "127_chief_operations_centre.py",
    "128_chief_retail_centre.py",
    "129_chief_commercial_centre.py",
    "130_head_analytics_centre.py",
])
def test_v10466_centre_has_cascade_view(page_name):
    text = (REPO / "pages" / page_name).read_text().lower()
    assert "cascade" in text


@pytest.mark.parametrize("page_name", [
    "127_chief_operations_centre.py",
    "128_chief_retail_centre.py",
    "129_chief_commercial_centre.py",
    "130_head_analytics_centre.py",
])
def test_v10466_centre_has_st_button(page_name):
    """Phase 4 WF4 compliance."""
    text = (REPO / "pages" / page_name).read_text()
    assert "st.button" in text


# ── CHIEFS IN RBAC ────────────────────────────────────────────────────

def test_v10466_coo_in_operations_centre():
    text = (REPO / "pages" / "127_chief_operations_centre.py").read_text()
    assert "Chief Operating Officer" in text


def test_v10466_crbo_in_retail_centre():
    text = (REPO / "pages" / "128_chief_retail_centre.py").read_text()
    assert "Chief Retail Banking Officer" in text


def test_v10466_cco_in_commercial_centre():
    text = (REPO / "pages" / "129_chief_commercial_centre.py").read_text()
    assert "Chief Commercial Officer" in text


def test_v10466_head_analytics_centre():
    text = (REPO / "pages" / "130_head_analytics_centre.py").read_text()
    assert "Head of Analytics" in text


# ── REPORTING HIERARCHY DIFFERENTIATION (Joshua doctrine) ────────────

def test_v10466_crbo_filters_retail_hierarchy():
    """CRBO sees retail-side via Branch Managers → Regional Heads."""
    text = (REPO / "pages" / "128_chief_retail_centre.py").read_text()
    assert "Branch Manager" in text or "branch manager" in text.lower()
    assert "Regional Head" in text or "regional head" in text.lower()


def test_v10466_cco_filters_commercial_hierarchy():
    """CCO sees commercial-side via Trade Finance → Head Of Corporates."""
    text = (REPO / "pages" / "129_chief_commercial_centre.py").read_text()
    assert "Trade Finance" in text
    assert "Corporates" in text or "Head Of Corporates" in text


def test_v10466_crm_centres_share_pipeline_doctrine():
    """Per Joshua: every staff can create leads via Pipeline."""
    crbo = (REPO / "pages" / "128_chief_retail_centre.py").read_text()
    cco = (REPO / "pages" / "129_chief_commercial_centre.py").read_text()
    assert "pipeline" in crbo.lower() or "Pipeline" in crbo
    assert "pipeline" in cco.lower() or "Pipeline" in cco


# ── MANIFEST REGISTRATION ────────────────────────────────────────────

@pytest.mark.parametrize("page_name", [
    "127_chief_operations_centre.py",
    "128_chief_retail_centre.py",
    "129_chief_commercial_centre.py",
    "130_head_analytics_centre.py",
])
def test_v10466_centre_in_manifest(manifest, page_name):
    entry = manifest["pages"].get(page_name)
    assert entry is not None, f"{page_name} not registered"
    assert entry.get("current_module_key") == "chief_centre"


def test_v10466_manifest_invariant_holds(manifest):
    missing = []
    for fname, entry in manifest["pages"].items():
        for req in ("title", "icon", "current_module_key", "department_primary"):
            if req not in entry:
                missing.append(f"{fname}: {req}")
    assert missing == [], f"Manifest invariant broken: {missing[:3]}"


# ── MODULE_REGISTRY UPDATED ──────────────────────────────────────────

def test_v10466_operations_primary_centre_is_127():
    for k in list(sys.modules):
        if "module_doctrine_audit" in k:
            del sys.modules[k]
    from utils.module_doctrine_audit import MODULE_REGISTRY
    assert MODULE_REGISTRY["operations"].command_centre_candidates[0] == "127_chief_operations_centre.py"


def test_v10466_crm_has_both_centres():
    for k in list(sys.modules):
        if "module_doctrine_audit" in k:
            del sys.modules[k]
    from utils.module_doctrine_audit import MODULE_REGISTRY
    candidates = MODULE_REGISTRY["crm"].command_centre_candidates[:3]
    assert "128_chief_retail_centre.py" in candidates
    assert "129_chief_commercial_centre.py" in candidates


def test_v10466_reporting_primary_centre_is_130():
    for k in list(sys.modules):
        if "module_doctrine_audit" in k:
            del sys.modules[k]
    from utils.module_doctrine_audit import MODULE_REGISTRY
    assert MODULE_REGISTRY["reporting_analytics"].command_centre_candidates[0] == "130_head_analytics_centre.py"


# ── HEALTH UPLIFT ────────────────────────────────────────────────────

def test_v10466_avg_health_above_83(all_modules):
    assert all_modules.avg_doctrine_health_pct >= 83.0


def test_v10466_operations_above_78(all_modules):
    """Operations should jump 75.8 → 80%+ via Phase 6 centre."""
    assert all_modules.modules["operations"].doctrine_health_pct >= 78.0


def test_v10466_crm_above_78(all_modules):
    assert all_modules.modules["crm"].doctrine_health_pct >= 78.0


def test_v10466_reporting_above_73(all_modules):
    assert all_modules.modules["reporting_analytics"].doctrine_health_pct >= 73.0


def test_v10466_no_crisis(all_modules):
    assert len(all_modules.crisis_modules) == 0


def test_v10466_all_13_organs_at_9_cert(all_modules):
    """All 13 should now hit at least 9/14 cert criteria."""
    low = [k for k, m in all_modules.modules.items()
          if m.criteria_fully_met < 9]
    assert not low, f"Organs below 9 cert: {low}"


def test_v10466_new_organs_phase_6_above_80(all_modules):
    """Chief centres should bring Phase 6 to 85%+."""
    for organ in ("operations", "crm", "reporting_analytics"):
        assert all_modules.modules[organ].phase_6.score_pct >= 80.0


# ── NO REGRESSION ────────────────────────────────────────────────────

def test_v10466_360_harmony_preserved():
    for k in list(sys.modules):
        if "cascade_bsc_360_engine" in k:
            del sys.modules[k]
    from utils.cascade_bsc_360_engine import cascade_bsc_360_audit
    assert cascade_bsc_360_audit().overall_harmony_pct == 100.0


def test_v10466_bsc_rescue_preserved():
    for k in list(sys.modules):
        if "bsc_audit_engine" in k:
            del sys.modules[k]
    from utils.bsc_audit_engine import bsc_full_audit
    assert bsc_full_audit().overall_health_pct == 100.0


def test_v10466_phase_4_preserved_for_mature_organs(all_modules):
    """v10.464 Phase 4 closeout must not regress."""
    for organ in ("admin","hr","credit","ict","finance","compliance"):
        assert all_modules.modules[organ].phase_4.score_pct >= 100.0


def test_v10466_zero_orphan_pages():
    for k in list(sys.modules):
        if "module_doctrine_audit" in k:
            del sys.modules[k]
    from utils.module_doctrine_audit import MODULE_REGISTRY
    all_pgs = sorted([p.name for p in (REPO/"pages").glob("*.py")
                     if not p.name.startswith("_")])
    claimed = set()
    for cfg in MODULE_REGISTRY.values():
        claimed.update(cfg.pages)
    orphans = [p for p in all_pgs if p not in claimed]
    assert orphans == [], f"Orphan pages: {orphans}"


def test_v10466_manifest_invariant_holds_again():
    for k in list(sys.modules):
        if "page_manifest_loader" in k:
            del sys.modules[k]
    from utils.page_manifest_loader import list_ghost_entries
    assert list_ghost_entries() == []


def test_v10466_g352_passes():
    sys.path.insert(0, str(REPO / "scripts"))
    for k in list(sys.modules):
        if k.startswith("audit"):
            del sys.modules[k]
    from audit import gate_v10466_four_new_chief_centres
    r = gate_v10466_four_new_chief_centres()
    assert r["passed"], r.get("violations")
