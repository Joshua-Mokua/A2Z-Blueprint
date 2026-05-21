"""Integration tests for v10.468 — Revival Data Population.

Joshua's honest audit questions closed:
  Q1: All standards wired? → 0 unwired (was 21)
  Q2: Every staff has BSC + actuals? → 100% / 100% (was 2.8% / 79.8%)
  Q3: Chiefs have BSCs MD can review? → 21/21 (was 1/20)
  Q4: Cascade down? → 100% (was 84.4%)
  Q5: reports_to chain? → 99.9% (was 0%)
"""

import json
import sys
from pathlib import Path

import pytest

REPO = Path("/tmp/a2z_fix")
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


@pytest.fixture(scope="module")
def users_list():
    data = json.loads((REPO/"data"/"users.json").read_text(encoding="utf-8"))
    lst = data if isinstance(data, list) else data.get("users", list(data.values()))
    return [u for u in lst if isinstance(u, dict) and u.get("active", True)]


@pytest.fixture(scope="module")
def all_staff_codes(users_list):
    return {str(u.get("staff_code","")) for u in users_list if u.get("staff_code")}


@pytest.fixture(scope="module")
def staff_with_bsc():
    bsc = json.loads((REPO/"data"/"bsc_scores.json").read_text(encoding="utf-8"))
    return {str(r.get("staff_code","")) for r in bsc if isinstance(r,dict)}


@pytest.fixture(scope="module")
def staff_with_actuals():
    result = set()
    for f in (REPO/"data").glob("bsc_actuals_*.json"):
        if f.stat().st_size < 1000: continue
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
            if isinstance(d, list):
                for r in d:
                    if isinstance(r, dict):
                        sc = str(r.get("staff_code",""))
                        if sc: result.add(sc)
        except Exception: pass
    return result


@pytest.fixture(scope="module")
def cascade():
    return json.loads((REPO/"data"/"target_cascade.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def staff_in_cascade(cascade):
    result = set()
    for k, e in cascade.items():
        if k.startswith("_"): continue
        if isinstance(e, dict):
            if "from_code" in e: result.add(str(e["from_code"]))
            for alloc in e.get("allocations", []):
                if isinstance(alloc, dict): result.add(str(alloc.get("to_code","")))
    return result


# ── Q1: ZERO UNWIRED STANDARDS ──────────────────────────────────────

def test_v10468_zero_unwired_standards():
    for k in list(sys.modules):
        if 'standards' in k: del sys.modules[k]
    from utils.standards_wiring_per_module import audit_all_module_standards
    a = audit_all_module_standards()
    total_unwired = sum(r.unwired_count for r in a.by_module.values())
    assert total_unwired == 0


def test_v10468_standards_coverage_above_90pct():
    for k in list(sys.modules):
        if 'standards' in k: del sys.modules[k]
    from utils.standards_wiring_per_module import audit_all_module_standards
    a = audit_all_module_standards()
    assert a.avg_coverage_pct >= 90.0


def test_v10468_standards_regex_supports_digits():
    """ifrs9_classification was failing because regex didn't include digits."""
    text = (REPO/"utils"/"standards_wiring_audit_engine.py").read_text()
    assert "[a-z0-9_]" in text


# ── Q2: EVERY STAFF HAS BSC + ACTUALS ───────────────────────────────

def test_v10468_every_staff_has_bsc(all_staff_codes, staff_with_bsc):
    pct = len(staff_with_bsc & all_staff_codes) / len(all_staff_codes)
    assert pct >= 0.99, f"BSC coverage only {pct:.1%}"


def test_v10468_every_staff_has_actuals(all_staff_codes, staff_with_actuals):
    pct = len(staff_with_actuals & all_staff_codes) / len(all_staff_codes)
    assert pct >= 0.99, f"Actuals coverage only {pct:.1%}"


def test_v10468_bsc_count_above_2800():
    bsc = json.loads((REPO/"data"/"bsc_scores.json").read_text(encoding="utf-8"))
    assert len(bsc) >= 2800


# ── Q3: ALL CHIEFS HAVE BSC + ACTUALS ──────────────────────────────

@pytest.fixture(scope="module")
def chief_codes(users_list):
    return {str(u["staff_code"]) for u in users_list
           if (u.get("role","").startswith("Chief ")
               or u.get("role","").startswith("Director ")
               or "Managing Director" in u.get("role","")
               or u.get("role","") == "Company Secretary and Chief Legal Officer"
               or u.get("role","").startswith("Head of")
               or u.get("role","").startswith("Head Of"))}


def test_v10468_all_chiefs_have_bsc(chief_codes, staff_with_bsc):
    missing = chief_codes - staff_with_bsc
    assert not missing, f"Chiefs without BSC: {missing}"


def test_v10468_all_chiefs_have_actuals(chief_codes, staff_with_actuals):
    missing = chief_codes - staff_with_actuals
    assert not missing, f"Chiefs without actuals: {missing}"


def test_v10468_md_has_bsc(staff_with_bsc):
    assert "300001" in staff_with_bsc


# ── Q4: CASCADE COVERAGE ───────────────────────────────────────────

def test_v10468_full_cascade_coverage(all_staff_codes, staff_in_cascade):
    covered = staff_in_cascade & all_staff_codes
    pct = len(covered) / len(all_staff_codes)
    assert pct >= 0.99, f"Cascade coverage only {pct:.1%}"


def test_v10468_cascade_has_v10468_additions(cascade):
    assert "_v10468_cascade_additions" in cascade


# ── Q5: reports_to HIERARCHY ────────────────────────────────────────

def test_v10468_reports_to_coverage(users_list):
    with_rt = sum(1 for u in users_list if u.get("reports_to"))
    pct = with_rt / len(users_list)
    assert pct >= 0.99


def test_v10468_md_is_top_of_pyramid(users_list):
    md = next((u for u in users_list if str(u.get("staff_code","")) == "300001"), None)
    assert md is not None
    assert md.get("reports_to") is None


def test_v10468_all_chiefs_report_to_md(users_list):
    for u in users_list:
        role = u.get("role", "")
        if (role.startswith("Chief ") and "Managing Director" not in role) \
           or role.startswith("Director ") \
           or role == "Company Secretary and Chief Legal Officer":
            assert u.get("reports_to") == "300001", \
                f"{u.get('full_name','?')} ({role}) reports_to={u.get('reports_to')}"


# ── MD DRILL-DOWN SURFACE ──────────────────────────────────────────

def test_v10468_md_cockpit_has_chief_review():
    text = (REPO/"pages"/"100_md_cockpit.py").read_text()
    assert "MD Chief Review" in text


def test_v10468_md_cockpit_has_drill_picker():
    text = (REPO/"pages"/"100_md_cockpit.py").read_text()
    assert "v468_md_drill_picker" in text


def test_v10468_md_cockpit_uses_reports_to():
    text = (REPO/"pages"/"100_md_cockpit.py").read_text()
    assert 'reports_to' in text


# ── NO REGRESSION ───────────────────────────────────────────────────

def test_v10468_bsc_rescue_100():
    for k in list(sys.modules):
        if 'bsc_audit_engine' in k: del sys.modules[k]
    from utils.bsc_audit_engine import bsc_full_audit
    assert bsc_full_audit().overall_health_pct == 100.0


def test_v10468_360_harmony_100():
    for k in list(sys.modules):
        if 'cascade_bsc_360' in k: del sys.modules[k]
    from utils.cascade_bsc_360_engine import cascade_bsc_360_audit
    assert cascade_bsc_360_audit().overall_harmony_pct == 100.0


def test_v10468_g354_passes():
    sys.path.insert(0, str(REPO / "scripts"))
    for k in list(sys.modules):
        if k.startswith("audit"):
            del sys.modules[k]
    from audit import gate_v10468_revival_data_population
    r = gate_v10468_revival_data_population()
    assert r["passed"], r.get("violations")


def test_v10468_zero_orphan_pages():
    for k in list(sys.modules):
        if "module_doctrine_audit" in k:
            del sys.modules[k]
    from utils.module_doctrine_audit import MODULE_REGISTRY
    all_pgs = sorted([p.name for p in (REPO/"pages").glob("*.py")
                     if not p.name.startswith("_")])
    claimed = set()
    for cfg in MODULE_REGISTRY.values():
        claimed.update(cfg.pages)
    assert [p for p in all_pgs if p not in claimed] == []
