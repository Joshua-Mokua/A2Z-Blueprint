"""Integration tests for v10.464 — Phase 4 Human Workflow Alignment.

Three work-streams:
  1. WF1 - cascade role recognition via _expected_roles_v10464 metadata
  2. WF3 - removed 6 ghost pages from credit MODULE_REGISTRY
  3. WF4 - explicit st.button + action buttons on chief centres + pages

Avg health: 81.3% → 84.6% (+3.3pp). Phase 4 = 100% all 10 organs.
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
def cascade():
    return json.loads((REPO / "data" / "target_cascade.json").read_text(encoding="utf-8"))


# ── WF1: CASCADE METADATA BLOCK ──────────────────────────────────────

def test_v10464_cascade_has_metadata_block(cascade):
    assert "_expected_roles_v10464" in cascade


def test_v10464_metadata_block_has_organ_hierarchy(cascade):
    meta = cascade["_expected_roles_v10464"]
    assert "organ_role_hierarchy" in meta


@pytest.mark.parametrize("organ", [
    "admin", "hr", "bsc_cascade", "credit", "ict",
    "finance", "treasury", "legal", "risk", "compliance"
])
def test_v10464_organ_documented_in_metadata(cascade, organ):
    meta = cascade["_expected_roles_v10464"]
    assert organ in meta["organ_role_hierarchy"]
    organ_meta = meta["organ_role_hierarchy"][organ]
    assert "expected_roles" in organ_meta
    assert len(organ_meta["expected_roles"]) >= 3


# ── WF3: GHOST PAGES REMOVED FROM CREDIT ─────────────────────────────

@pytest.mark.parametrize("ghost", [
    "24_credit_committee.py", "25_credit_monitoring.py",
    "26_drr.py", "27_ifrs9.py", "38_credit_workbench.py",
    "72_specialized_credit.py"
])
def test_v10464_credit_no_ghost_pages(ghost):
    text = (REPO / "utils" / "module_doctrine_audit.py").read_text()
    assert f'"{ghost}"' not in text, \
        f"Credit MODULE_REGISTRY still references ghost: {ghost}"


def test_v10464_credit_pages_all_exist():
    for k in list(sys.modules):
        if "module_doctrine_audit" in k:
            del sys.modules[k]
    from utils.module_doctrine_audit import MODULE_REGISTRY
    cfg = MODULE_REGISTRY["credit"]
    for p in cfg.pages:
        path = REPO / "pages" / p
        assert path.exists(), f"Credit ghost: {p}"


# ── WF4: OPERATIONAL OUTPUTS (st.button) ─────────────────────────────

@pytest.mark.parametrize("centre", [
    "85_chief_credit_centre.py",
    "122_chief_finance_centre.py",
    "123_head_treasury_centre.py",
    "124_company_secretary_centre.py",
    "125_chief_risk_centre.py",
    "126_compliance_centre.py",
])
def test_v10464_centre_has_st_button(centre):
    text = (REPO / "pages" / centre).read_text()
    assert "st.button" in text, \
        f"{centre} missing st.button literal (Phase 4 WF4)"


# ── PHASE 4 = 100% ALL 10 ORGANS ─────────────────────────────────────

@pytest.mark.parametrize("organ", [
    "admin", "hr", "bsc_cascade", "credit", "ict",
    "finance", "treasury", "legal", "risk", "compliance"
])
def test_v10464_phase_4_100_for_organ(all_modules, organ):
    assert all_modules.modules[organ].phase_4.score_pct >= 100.0


def test_v10464_phase_4_wf1_passes_for_all(all_modules):
    """WF1 expected roles in cascade ≥80%."""
    failures = []
    for key, m in all_modules.modules.items():
        wf1 = next((s for s in m.phase_4.sub_criteria
                   if "WF1" in s["c"]), None)
        if wf1 and not wf1["met"]:
            failures.append(key)
    assert not failures, f"WF1 failing: {failures}"


# ── HEALTH UPLIFT ────────────────────────────────────────────────────

def test_v10464_avg_health_above_84(all_modules):
    assert all_modules.avg_doctrine_health_pct >= 84.0


def test_v10464_no_crisis(all_modules):
    assert len(all_modules.crisis_modules) == 0


def test_v10464_credit_at_11_cert(all_modules):
    """Credit should jump to 11/14 after Phase 4 fixes."""
    assert all_modules.modules["credit"].criteria_fully_met >= 11


def test_v10464_at_least_9_organs_at_10_cert(all_modules):
    high = sum(1 for m in all_modules.modules.values()
              if m.criteria_fully_met >= 10)
    assert high >= 9


# ── NO REGRESSION ────────────────────────────────────────────────────

def test_v10464_360_harmony_preserved():
    for k in list(sys.modules):
        if "cascade_bsc_360_engine" in k:
            del sys.modules[k]
    from utils.cascade_bsc_360_engine import cascade_bsc_360_audit
    assert cascade_bsc_360_audit().overall_harmony_pct == 100.0


def test_v10464_bsc_rescue_preserved():
    for k in list(sys.modules):
        if "bsc_audit_engine" in k:
            del sys.modules[k]
    from utils.bsc_audit_engine import bsc_full_audit
    assert bsc_full_audit().overall_health_pct == 100.0


def test_v10464_phase_2_still_100_for_all(all_modules):
    """v10.463 Phase 2 closeout must not regress."""
    for key, m in all_modules.modules.items():
        assert m.phase_2.score_pct >= 100.0, \
            f"{key} Phase 2 regressed to {m.phase_2.score_pct}%"


def test_v10464_manifest_invariant_holds():
    for k in list(sys.modules):
        if "page_manifest_loader" in k:
            del sys.modules[k]
    from utils.page_manifest_loader import list_ghost_entries
    assert list_ghost_entries() == []


def test_v10464_g350_passes():
    sys.path.insert(0, str(REPO / "scripts"))
    for k in list(sys.modules):
        if k.startswith("audit"):
            del sys.modules[k]
    from audit import gate_v10464_phase_4_aligned
    r = gate_v10464_phase_4_aligned()
    assert r["passed"], r.get("violations")


# ── PAGE PARSE INTEGRITY (button injection didn't break anything) ────

@pytest.mark.parametrize("page", [
    "85_chief_credit_centre.py",
    "122_chief_finance_centre.py",
    "123_head_treasury_centre.py",
    "124_company_secretary_centre.py",
    "125_chief_risk_centre.py",
    "126_compliance_centre.py",
    "91_systems_view.py",
    "96_it_digital_pt1.py",
    "97_it_digital_pt2.py",
    "98_platform_health.py",
    "116_finance_hub.py",
    "110_treasury_live.py",
    "24_compliance.py",
    "112_compliance_live.py",
    "40_collateral.py",
])
def test_v10464_modified_page_parses(page):
    ast.parse((REPO / "pages" / page).read_text(encoding="utf-8"))
