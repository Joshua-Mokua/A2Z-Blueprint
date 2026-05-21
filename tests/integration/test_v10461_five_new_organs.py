"""Integration tests for v10.461 — 5 new organs joining the revival.

Per Joshua mantra doc + Module Revival Framework. Brings the body from
5 organs to 10:
  finance     - Circulatory & Energy Distribution
  treasury    - Cash Flow Reservoir & Arterial Blood Pressure
  legal       - Bony Skeleton & Constitutional Framework
  risk        - Immune System Primary
  compliance  - Immune System Antibodies

Avg health: 60.8% (10-organ baseline) → 75.2% (+14.4pp). Zero crisis.
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


# ── 5 NEW CENTRES EXIST + PARSE ───────────────────────────────────────

@pytest.mark.parametrize("page_name", [
    "122_chief_finance_centre.py",
    "123_head_treasury_centre.py",
    "124_company_secretary_centre.py",
    "125_chief_risk_centre.py",
    "126_compliance_centre.py",
])
def test_v10461_centre_exists_and_parses(page_name):
    path = REPO / "pages" / page_name
    assert path.exists(), f"Missing: {page_name}"
    ast.parse(path.read_text(encoding="utf-8"))


@pytest.mark.parametrize("page_name", [
    "122_chief_finance_centre.py",
    "123_head_treasury_centre.py",
    "124_company_secretary_centre.py",
    "125_chief_risk_centre.py",
    "126_compliance_centre.py",
])
def test_v10461_centre_six_doctrine_tabs(page_name):
    text = (REPO / "pages" / page_name).read_text()
    for tab in ("Executive Visibility", "Strategic Intelligence",
                "Organ Health", "My Staff Performance",
                "Risk", "Real-Time"):
        assert tab in text, f"{page_name} missing tab: {tab}"


@pytest.mark.parametrize("page_name", [
    "122_chief_finance_centre.py",
    "123_head_treasury_centre.py",
    "124_company_secretary_centre.py",
    "125_chief_risk_centre.py",
    "126_compliance_centre.py",
])
def test_v10461_centre_has_cascade_view(page_name):
    text = (REPO / "pages" / page_name).read_text().lower()
    assert "cascade" in text, f"{page_name} missing cascade view"


# ── CHIEF ROLES IN RBAC ───────────────────────────────────────────────

def test_v10461_cfo_in_finance_centre():
    text = (REPO / "pages" / "122_chief_finance_centre.py").read_text()
    assert "Chief Finance Officer" in text


def test_v10461_head_treasury_centre():
    text = (REPO / "pages" / "123_head_treasury_centre.py").read_text()
    assert "Head of Treasury" in text


def test_v10461_company_secretary_in_legal():
    text = (REPO / "pages" / "124_company_secretary_centre.py").read_text()
    assert "Company Secretary" in text


def test_v10461_cro_in_risk_centre():
    text = (REPO / "pages" / "125_chief_risk_centre.py").read_text()
    assert "Chief Risk Officer" in text


def test_v10461_head_compliance_centre():
    text = (REPO / "pages" / "126_compliance_centre.py").read_text()
    assert "Head of Compliance" in text


# ── MANIFEST REGISTRATION ─────────────────────────────────────────────

@pytest.mark.parametrize("page_name", [
    "122_chief_finance_centre.py",
    "123_head_treasury_centre.py",
    "124_company_secretary_centre.py",
    "125_chief_risk_centre.py",
    "126_compliance_centre.py",
])
def test_v10461_centre_in_manifest(manifest, page_name):
    entry = manifest["pages"].get(page_name)
    assert entry is not None, f"{page_name} not registered"
    assert entry.get("current_module_key") == "chief_centre"


def test_v10461_manifest_invariant_still_holds(manifest):
    missing = []
    for fname, entry in manifest["pages"].items():
        for req in ("title", "icon", "current_module_key", "department_primary"):
            if req not in entry:
                missing.append(f"{fname}: {req}")
    assert missing == [], f"Manifest invariant broken: {missing[:3]}"


# ── MODULE_REGISTRY EXPANDED ─────────────────────────────────────────

def test_v10461_module_registry_has_10_organs():
    for k in list(sys.modules):
        if "module_doctrine_audit" in k:
            del sys.modules[k]
    from utils.module_doctrine_audit import MODULE_REGISTRY
    assert len(MODULE_REGISTRY) == 10


@pytest.mark.parametrize("module_key", [
    "finance", "treasury", "legal", "risk", "compliance"
])
def test_v10461_new_organ_in_registry(module_key):
    for k in list(sys.modules):
        if "module_doctrine_audit" in k:
            del sys.modules[k]
    from utils.module_doctrine_audit import MODULE_REGISTRY
    assert module_key in MODULE_REGISTRY


# ── SUPER_USER_MAP EXTENDED ──────────────────────────────────────────

def test_v10461_super_user_map_has_10_organs():
    for k in list(sys.modules):
        if "super_user_registry" in k:
            del sys.modules[k]
    from utils.super_user_registry import SUPER_USER_MAP
    assert len(SUPER_USER_MAP) == 10


@pytest.mark.parametrize("module_key", [
    "finance", "treasury", "legal", "risk", "compliance"
])
def test_v10461_new_organ_escalates_through_ict(module_key):
    """All new organs escalate through ICT Super User per Joshua."""
    for k in list(sys.modules):
        if "super_user_registry" in k:
            del sys.modules[k]
    from utils.super_user_registry import SUPER_USER_MAP
    info = SUPER_USER_MAP[module_key]
    assert "ICT Super User" in info["escalation_path"]


# ── EVENT_BUS EXTENDED ───────────────────────────────────────────────

def test_v10461_event_bus_has_finance_events():
    for k in list(sys.modules):
        if "cross_organ_event_bus" in k:
            del sys.modules[k]
    from utils.cross_organ_event_bus import EVENT_TYPES
    finance_events = [e for e in EVENT_TYPES if e.startswith("finance.")]
    assert len(finance_events) >= 4


def test_v10461_event_bus_has_treasury_events():
    for k in list(sys.modules):
        if "cross_organ_event_bus" in k:
            del sys.modules[k]
    from utils.cross_organ_event_bus import EVENT_TYPES
    events = [e for e in EVENT_TYPES if e.startswith("treasury.")]
    assert len(events) >= 4


def test_v10461_event_bus_has_legal_events():
    for k in list(sys.modules):
        if "cross_organ_event_bus" in k:
            del sys.modules[k]
    from utils.cross_organ_event_bus import EVENT_TYPES
    events = [e for e in EVENT_TYPES if e.startswith("legal.")]
    assert len(events) >= 4


def test_v10461_event_bus_has_risk_events():
    for k in list(sys.modules):
        if "cross_organ_event_bus" in k:
            del sys.modules[k]
    from utils.cross_organ_event_bus import EVENT_TYPES
    events = [e for e in EVENT_TYPES if e.startswith("risk.")]
    assert len(events) >= 4


def test_v10461_event_bus_has_compliance_events():
    for k in list(sys.modules):
        if "cross_organ_event_bus" in k:
            del sys.modules[k]
    from utils.cross_organ_event_bus import EVENT_TYPES
    events = [e for e in EVENT_TYPES if e.startswith("compliance.")]
    assert len(events) >= 4


# ── HEALTH OUTCOMES ──────────────────────────────────────────────────

def test_v10461_audit_returns_10_modules(all_modules):
    assert len(all_modules.modules) == 10


def test_v10461_avg_health_above_73(all_modules):
    """Across 10 organs."""
    assert all_modules.avg_doctrine_health_pct >= 73.0


def test_v10461_no_crisis(all_modules):
    """All 5 new organs revived from crisis."""
    assert len(all_modules.crisis_modules) == 0


@pytest.mark.parametrize("module_key", [
    "finance", "treasury", "legal", "risk", "compliance"
])
def test_v10461_new_organ_above_65(all_modules, module_key):
    """Every new organ above 65% (out of crisis)."""
    assert all_modules.modules[module_key].doctrine_health_pct >= 65.0


@pytest.mark.parametrize("module_key", [
    "finance", "treasury", "legal", "risk", "compliance"
])
def test_v10461_new_organ_phase_6_100(all_modules, module_key):
    """New chief centres bring Phase 6 to 100%."""
    assert all_modules.modules[module_key].phase_6.score_pct >= 100.0


# ── DOCS GENERATED FOR 5 NEW ORGANS ──────────────────────────────────

@pytest.mark.parametrize("module_key", [
    "finance", "treasury", "legal", "risk", "compliance"
])
def test_v10461_doctrine_docs_for_new_organ(module_key):
    docs = list((REPO / "docs").glob(f"{module_key}_*.md"))
    assert len(docs) >= 20, \
        f"{module_key} has {len(docs)} docs; expected >=20"


# ── UPSTREAM PRESERVED ───────────────────────────────────────────────

def test_v10461_360_harmony_preserved():
    for k in list(sys.modules):
        if "cascade_bsc_360_engine" in k:
            del sys.modules[k]
    from utils.cascade_bsc_360_engine import cascade_bsc_360_audit
    assert cascade_bsc_360_audit().overall_harmony_pct == 100.0


def test_v10461_bsc_rescue_preserved():
    for k in list(sys.modules):
        if "bsc_audit_engine" in k:
            del sys.modules[k]
    from utils.bsc_audit_engine import bsc_full_audit
    assert bsc_full_audit().overall_health_pct == 100.0


def test_v10461_g347_passes():
    sys.path.insert(0, str(REPO / "scripts"))
    for k in list(sys.modules):
        if k.startswith("audit"):
            del sys.modules[k]
    from audit import gate_v10461_five_new_organs
    r = gate_v10461_five_new_organs()
    assert r["passed"], r.get("violations")
