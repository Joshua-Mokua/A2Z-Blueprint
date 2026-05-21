"""Integration tests for v10.465 — Complete the Body (13 Organs).

Per Joshua mantra doc. Brings body from 10 organs to 13:
  operations          - Muscular & Movement System (COO)
  crm                 - Sensory & Interaction Systems (CRBO + CCO shared)
  reporting_analytics - Vital Signs Monitoring & Diagnostic Systems

Plus extends existing organs with 30+ re-homed pages. Zero orphan pages.
Avg health: 84.6% (10) → 82.7% (13) — only -1.9pp despite 3 new organs.
"""

import ast
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


# ── 13-ORGAN REGISTRY ─────────────────────────────────────────────────

def test_v10465_module_registry_has_13_organs():
    for k in list(sys.modules):
        if "module_doctrine_audit" in k:
            del sys.modules[k]
    from utils.module_doctrine_audit import MODULE_REGISTRY
    assert len(MODULE_REGISTRY) == 13


@pytest.mark.parametrize("organ", [
    "operations", "crm", "reporting_analytics"
])
def test_v10465_new_organ_in_registry(organ):
    for k in list(sys.modules):
        if "module_doctrine_audit" in k:
            del sys.modules[k]
    from utils.module_doctrine_audit import MODULE_REGISTRY
    assert organ in MODULE_REGISTRY


def test_v10465_operations_has_22_pages():
    for k in list(sys.modules):
        if "module_doctrine_audit" in k:
            del sys.modules[k]
    from utils.module_doctrine_audit import MODULE_REGISTRY
    assert len(MODULE_REGISTRY["operations"].pages) >= 20


def test_v10465_crm_has_20plus_pages():
    for k in list(sys.modules):
        if "module_doctrine_audit" in k:
            del sys.modules[k]
    from utils.module_doctrine_audit import MODULE_REGISTRY
    assert len(MODULE_REGISTRY["crm"].pages) >= 20


def test_v10465_reporting_analytics_has_pages():
    for k in list(sys.modules):
        if "module_doctrine_audit" in k:
            del sys.modules[k]
    from utils.module_doctrine_audit import MODULE_REGISTRY
    assert len(MODULE_REGISTRY["reporting_analytics"].pages) >= 8


# ── MANTRA-DOC ORGAN ROLES ────────────────────────────────────────────

def test_v10465_operations_organ_role():
    for k in list(sys.modules):
        if "module_doctrine_audit" in k:
            del sys.modules[k]
    from utils.module_doctrine_audit import MODULE_REGISTRY
    assert "Muscular" in MODULE_REGISTRY["operations"].organ_role


def test_v10465_crm_organ_role():
    for k in list(sys.modules):
        if "module_doctrine_audit" in k:
            del sys.modules[k]
    from utils.module_doctrine_audit import MODULE_REGISTRY
    assert "Sensory" in MODULE_REGISTRY["crm"].organ_role


def test_v10465_reporting_organ_role():
    for k in list(sys.modules):
        if "module_doctrine_audit" in k:
            del sys.modules[k]
    from utils.module_doctrine_audit import MODULE_REGISTRY
    assert "Vital Signs" in MODULE_REGISTRY["reporting_analytics"].organ_role


# ── CHIEFS IN SUPER_USER_MAP ─────────────────────────────────────────

def test_v10465_coo_is_operations_chief():
    for k in list(sys.modules):
        if "super_user_registry" in k:
            del sys.modules[k]
    from utils.super_user_registry import SUPER_USER_MAP
    assert SUPER_USER_MAP["operations"]["primary_role"] == "Chief Operating Officer"


def test_v10465_crbo_is_crm_primary():
    for k in list(sys.modules):
        if "super_user_registry" in k:
            del sys.modules[k]
    from utils.super_user_registry import SUPER_USER_MAP
    assert SUPER_USER_MAP["crm"]["primary_role"] == "Chief Retail Banking Officer"


def test_v10465_cco_is_crm_secondary():
    """Per Joshua: CRM SHARED between CRBO and CCO."""
    for k in list(sys.modules):
        if "super_user_registry" in k:
            del sys.modules[k]
    from utils.super_user_registry import SUPER_USER_MAP
    assert SUPER_USER_MAP["crm"]["secondary_role"] == "Chief Commercial Officer"


@pytest.mark.parametrize("organ", [
    "operations", "crm", "reporting_analytics"
])
def test_v10465_new_organ_escalates_through_ict(organ):
    for k in list(sys.modules):
        if "super_user_registry" in k:
            del sys.modules[k]
    from utils.super_user_registry import SUPER_USER_MAP
    assert "ICT Super User" in SUPER_USER_MAP[organ]["escalation_path"]


# ── SHARED MODULES — Joshua's special attention ─────────────────────

def test_v10465_pipeline_in_crm():
    """Pipeline allows every staff to create leads per Joshua."""
    for k in list(sys.modules):
        if "module_doctrine_audit" in k:
            del sys.modules[k]
    from utils.module_doctrine_audit import MODULE_REGISTRY
    assert "3_pipeline.py" in MODULE_REGISTRY["crm"].pages


def test_v10465_edms_in_operations():
    """EDMS in Operations per Joshua 'cut across' note."""
    for k in list(sys.modules):
        if "module_doctrine_audit" in k:
            del sys.modules[k]
    from utils.module_doctrine_audit import MODULE_REGISTRY
    assert "31_edms.py" in MODULE_REGISTRY["operations"].pages


def test_v10465_cims_in_operations():
    """CIMS in Operations per Joshua special attention."""
    for k in list(sys.modules):
        if "module_doctrine_audit" in k:
            del sys.modules[k]
    from utils.module_doctrine_audit import MODULE_REGISTRY
    cfg = MODULE_REGISTRY["operations"]
    assert "18_cims.py" in cfg.pages
    assert any("cims" in p.lower() for p in cfg.pages)


def test_v10465_sla_in_operations():
    """SLA in Operations per Joshua 'very crucial' note."""
    for k in list(sys.modules):
        if "module_doctrine_audit" in k:
            del sys.modules[k]
    from utils.module_doctrine_audit import MODULE_REGISTRY
    assert "13_sla.py" in MODULE_REGISTRY["operations"].pages


def test_v10465_customer360_in_crm():
    for k in list(sys.modules):
        if "module_doctrine_audit" in k:
            del sys.modules[k]
    from utils.module_doctrine_audit import MODULE_REGISTRY
    assert "34_customer360.py" in MODULE_REGISTRY["crm"].pages


# ── EVENT BUS EXTENDED ────────────────────────────────────────────────

@pytest.mark.parametrize("prefix", ["operations.", "crm.", "analytics."])
def test_v10465_event_bus_has_new_organ_events(prefix):
    for k in list(sys.modules):
        if "cross_organ_event_bus" in k:
            del sys.modules[k]
    from utils.cross_organ_event_bus import EVENT_TYPES
    organ_events = [e for e in EVENT_TYPES if e.startswith(prefix)]
    assert len(organ_events) >= 4


# ── ZERO ORPHAN PAGES ────────────────────────────────────────────────

def test_v10465_zero_orphan_pages():
    """Every page on disk must be claimed by an organ."""
    for k in list(sys.modules):
        if "module_doctrine_audit" in k:
            del sys.modules[k]
    from utils.module_doctrine_audit import MODULE_REGISTRY
    all_pages = sorted([p.name for p in (REPO / "pages").glob("*.py")
                       if not p.name.startswith("_")])
    claimed = set()
    for cfg in MODULE_REGISTRY.values():
        claimed.update(cfg.pages)
    orphans = [p for p in all_pages if p not in claimed]
    assert orphans == [], f"Orphan pages: {orphans}"


# ── HEALTH BASELINE ──────────────────────────────────────────────────

def test_v10465_audit_returns_13_modules(all_modules):
    assert len(all_modules.modules) == 13


def test_v10465_avg_health_above_80(all_modules):
    """Body avg should stay >=80% even with 3 new organs."""
    assert all_modules.avg_doctrine_health_pct >= 80.0


def test_v10465_no_crisis(all_modules):
    assert len(all_modules.crisis_modules) == 0


@pytest.mark.parametrize("organ", [
    "operations", "crm", "reporting_analytics"
])
def test_v10465_new_organ_above_65(all_modules, organ):
    """New organs out of crisis, above 65%."""
    assert all_modules.modules[organ].doctrine_health_pct >= 65.0


def test_v10465_at_least_9_organs_at_10_cert(all_modules):
    high = sum(1 for m in all_modules.modules.values()
              if m.criteria_fully_met >= 10)
    assert high >= 9


# ── DEEP REVIEW DOC ──────────────────────────────────────────────────

def test_v10465_deep_review_doc_exists():
    path = REPO / "docs" / "v10465_DEEP_REVIEW_AND_ASSIGNMENT.md"
    assert path.exists()
    text = path.read_text(encoding="utf-8")
    assert "Chief Retail Banking Officer" in text
    assert "Chief Commercial Officer" in text
    assert "Chief Operating Officer" in text


# ── DOCTRINE DOCS FOR 3 NEW ORGANS ───────────────────────────────────

@pytest.mark.parametrize("organ", [
    "operations", "crm", "reporting_analytics"
])
def test_v10465_new_organ_has_doctrine_docs(organ):
    docs = list((REPO / "docs").glob(f"{organ}_*.md"))
    assert len(docs) >= 20


# ── NO REGRESSION ────────────────────────────────────────────────────

def test_v10465_360_harmony_preserved():
    for k in list(sys.modules):
        if "cascade_bsc_360_engine" in k:
            del sys.modules[k]
    from utils.cascade_bsc_360_engine import cascade_bsc_360_audit
    assert cascade_bsc_360_audit().overall_harmony_pct == 100.0


def test_v10465_bsc_rescue_preserved():
    for k in list(sys.modules):
        if "bsc_audit_engine" in k:
            del sys.modules[k]
    from utils.bsc_audit_engine import bsc_full_audit
    assert bsc_full_audit().overall_health_pct == 100.0


def test_v10465_phase_4_preserved_for_v10464_organs(all_modules):
    """v10.464 fixes shouldn't regress."""
    for organ in ("admin","hr","credit","ict","finance","compliance"):
        assert all_modules.modules[organ].phase_4.score_pct >= 100.0


def test_v10465_phase_2_preserved_all_organs(all_modules):
    """v10.463 Phase 2 closeout shouldn't regress (for the 10 original)."""
    for organ in ("admin","hr","bsc_cascade","credit","ict","finance",
                  "treasury","legal","risk","compliance"):
        assert all_modules.modules[organ].phase_2.score_pct >= 100.0


def test_v10465_manifest_invariant_holds():
    for k in list(sys.modules):
        if "page_manifest_loader" in k:
            del sys.modules[k]
    from utils.page_manifest_loader import list_ghost_entries
    assert list_ghost_entries() == []


def test_v10465_g351_passes():
    sys.path.insert(0, str(REPO / "scripts"))
    for k in list(sys.modules):
        if k.startswith("audit"):
            del sys.modules[k]
    from audit import gate_v10465_complete_body
    r = gate_v10465_complete_body()
    assert r["passed"], r.get("violations")
