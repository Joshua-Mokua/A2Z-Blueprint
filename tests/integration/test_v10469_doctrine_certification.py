"""Integration tests for v10.469 — Doctrine Certification (deep-honest audit).

Joshua's challenge: 'ensure the body does not slide back into a coma...
the health status we are reporting must be true, reflective, does not
contradict and cannot be questioned again or challenged.'

v10.469 closes 5 structural lies v10.468 architecture hid:
  1. 20 chiefs reporting to MD (true: 9)
  2. Flat hierarchy with 785-direct-report spans (now layered)
  3. 10,602 cascade direction violations (now 0)
  4. role_kpis short codes unresolved (now 0)
  5. MD with 102%+ PBT rated 'Below' (now 'Exceeds')
"""

import json
import sys
from collections import Counter
from pathlib import Path

import pytest

REPO = Path("/tmp/a2z_fix")
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


@pytest.fixture(scope="module")
def users_list():
    data = json.loads((REPO/"data"/"users.json").read_text(encoding="utf-8"))
    lst = data if isinstance(data, list) else list(data.values())
    return [u for u in lst if isinstance(u, dict) and u.get("active", True)]


@pytest.fixture(scope="module")
def code_to_user(users_list):
    return {str(u.get("staff_code","")): u for u in users_list}


@pytest.fixture(scope="module")
def cascade():
    return json.loads((REPO/"data"/"target_cascade.json").read_text(encoding="utf-8"))


# ── 1. EXACTLY 9 TRUE CHIEFS REPORT TO MD ───────────────────────────

def test_v10469_exactly_9_true_chiefs_report_to_md(users_list):
    chiefs_to_md = [u for u in users_list
                   if str(u.get("reports_to","")) == "300001"]
    true_chiefs = [u for u in chiefs_to_md
                  if u.get("role","").startswith("Chief ")
                  or u.get("role","") == "Company Secretary and Chief Legal Officer"]
    assert len(true_chiefs) == 9, \
        f"Expected 9 true chiefs, got {len(true_chiefs)}: {[c['full_name'] for c in true_chiefs]}"


def test_v10469_zero_heads_report_to_md(users_list):
    heads_to_md = [u for u in users_list
                  if str(u.get("reports_to","")) == "300001"
                  and (u.get("role","").startswith("Head of")
                       or u.get("role","").startswith("Head Of"))]
    assert not heads_to_md, \
        f"Heads incorrectly reporting to MD: {[h['full_name'] for h in heads_to_md]}"


def test_v10469_all_chief_x_report_to_md(users_list):
    """Each Chief X Officer must report to MD."""
    for u in users_list:
        role = u.get("role","")
        if role.startswith("Chief ") and "Managing Director" not in role:
            assert str(u.get("reports_to","")) == "300001", \
                f"{u['full_name']} ({role}) reports_to={u.get('reports_to')}"


# ── 2. SPAN OF CONTROL CAPS ─────────────────────────────────────────

def test_v10469_max_span_under_50(users_list):
    mgr_counts = Counter(str(u.get("reports_to","")) for u in users_list
                        if u.get("reports_to"))
    max_span = max(mgr_counts.values())
    assert max_span <= 50, f"Insane span detected: {max_span}"


def test_v10469_zero_managers_over_100_reports(users_list):
    mgr_counts = Counter(str(u.get("reports_to","")) for u in users_list
                        if u.get("reports_to"))
    over_100 = [(code, n) for code, n in mgr_counts.items() if n > 100]
    assert not over_100, f"Managers with >100 reports: {over_100}"


def test_v10469_branch_managers_under_area_managers(users_list, code_to_user):
    bms = [u for u in users_list if u.get("role","") == "Branch Manager"]
    for bm in bms:
        rt = str(bm.get("reports_to",""))
        mgr_role = code_to_user.get(rt, {}).get("role", "")
        assert mgr_role in ("Area Manager", "Head of Branches"), \
            f"BM {bm['full_name']} reports to {rt} ({mgr_role}) — should be Area Manager"


# ── 3. reports_to INTEGRITY ─────────────────────────────────────────

def test_v10469_reports_to_coverage(users_list):
    with_rt = sum(1 for u in users_list if u.get("reports_to"))
    assert with_rt / len(users_list) >= 0.99


def test_v10469_zero_orphan_reports_to(users_list):
    all_codes = {str(u.get("staff_code","")) for u in users_list
                if u.get("staff_code")}
    orphans = [u for u in users_list
              if u.get("reports_to") and str(u["reports_to"]) not in all_codes]
    assert not orphans, f"Orphan reports_to: {[(o['full_name'], o['reports_to']) for o in orphans[:5]]}"


def test_v10469_md_at_top_of_pyramid(users_list):
    md = next((u for u in users_list if str(u.get("staff_code","")) == "300001"), None)
    assert md and md.get("reports_to") is None


# ── 4. CASCADE DIRECTION ALIGNMENT ──────────────────────────────────

def test_v10469_zero_cascade_direction_violations(cascade, code_to_user):
    def ancestors_of(sc, max_depth=8):
        chain = []
        current = code_to_user.get(sc, {})
        for _ in range(max_depth):
            rt = current.get("reports_to")
            if not rt: break
            rt = str(rt)
            if rt in chain: break
            chain.append(rt)
            current = code_to_user.get(rt, {})
        return chain
    violations = []
    for k, e in cascade.items():
        if k.startswith("_") or not isinstance(e, dict): continue
        fc = str(e.get("from_code",""))
        for a in e.get("allocations", []):
            if isinstance(a, dict):
                tc = str(a.get("to_code",""))
                if tc in code_to_user:
                    anc = ancestors_of(tc)
                    if fc not in anc and fc != tc:
                        violations.append((fc, tc))
    assert not violations, f"{len(violations)} cascade direction violations"


# ── 5. role_kpis RESOLUTION ─────────────────────────────────────────

def test_v10469_role_kpis_all_resolved():
    lib = json.loads((REPO/"data"/"kpi_library.json").read_text(encoding="utf-8"))
    kpi_ids = {k.get("id","") for k in lib.get("kpis",[]) if isinstance(k,dict)}
    unresolved = [(role, kid) for role, kl in lib.get("role_kpis",{}).items()
                 if isinstance(kl, list) for kid in kl if kid not in kpi_ids]
    assert not unresolved, f"{len(unresolved)} role_kpis unresolved"


# ── 6. BSC ACHIEVEMENT-ALIGNED ──────────────────────────────────────

def test_v10469_no_chief_rated_below():
    bsc = json.loads((REPO/"data"/"bsc_scores.json").read_text(encoding="utf-8"))
    chief_codes = {"300001","300002","300003","300004","300005","300006",
                   "300007","300008","300009","300010"}
    chief_below = [r for r in bsc if isinstance(r,dict)
                  and str(r.get("staff_code","")) in chief_codes
                  and r.get("rating") == "Below"
                  and r.get("quarter","") >= "2026-Q1"]
    assert not chief_below, f"Chiefs rated 'Below': {chief_below}"


def test_v10469_md_scores_exceeds_or_higher():
    bsc = json.loads((REPO/"data"/"bsc_scores.json").read_text(encoding="utf-8"))
    md_q1 = [r for r in bsc if isinstance(r,dict)
            and str(r.get("staff_code","")) == "300001"
            and r.get("quarter") == "2026-Q1"]
    assert md_q1
    md = md_q1[0]
    assert md["rating"] in ("Exceeds", "Outstanding"), \
        f"MD rated {md['rating']} despite 102%+ achievement"


# ── 7. DATA INTEGRITY ───────────────────────────────────────────────

def test_v10469_zero_phantoms():
    data = json.loads((REPO/"data"/"users.json").read_text(encoding="utf-8"))
    lst = data if isinstance(data, list) else list(data.values())
    phantoms = [u for u in lst if isinstance(u, dict)
               and u.get("active", True) and not u.get("staff_code")]
    assert not phantoms


def test_v10469_zero_duplicate_codes():
    data = json.loads((REPO/"data"/"users.json").read_text(encoding="utf-8"))
    lst = data if isinstance(data, list) else list(data.values())
    codes = [str(u.get("staff_code","")) for u in lst
            if isinstance(u, dict) and u.get("staff_code")]
    dupes = [c for c, n in Counter(codes).items() if n > 1]
    assert not dupes, f"Duplicate codes: {dupes}"


# ── 8. UPSTREAM HEALTH PRESERVED ────────────────────────────────────

def test_v10469_360_harmony_100():
    for k in list(sys.modules):
        if 'cascade_bsc_360' in k: del sys.modules[k]
    from utils.cascade_bsc_360_engine import cascade_bsc_360_audit
    assert cascade_bsc_360_audit().overall_harmony_pct == 100.0


def test_v10469_bsc_rescue_100():
    for k in list(sys.modules):
        if 'bsc_audit_engine' in k: del sys.modules[k]
    from utils.bsc_audit_engine import bsc_full_audit
    assert bsc_full_audit().overall_health_pct == 100.0


def test_v10469_zero_unwired_standards():
    for k in list(sys.modules):
        if 'standards' in k: del sys.modules[k]
    from utils.standards_wiring_per_module import audit_all_module_standards
    a = audit_all_module_standards()
    assert sum(r.unwired_count for r in a.by_module.values()) == 0


def test_v10469_g355_passes():
    sys.path.insert(0, str(REPO / "scripts"))
    for k in list(sys.modules):
        if k.startswith("audit"):
            del sys.modules[k]
    from audit import gate_v10469_doctrine_certification
    r = gate_v10469_doctrine_certification()
    assert r["passed"], r.get("violations")


def test_v10469_no_inactive_in_bsc_or_cascade():
    data = json.loads((REPO/"data"/"users.json").read_text(encoding="utf-8"))
    lst = data if isinstance(data, list) else list(data.values())
    inactive_codes = {str(u.get("staff_code","")) for u in lst
                     if isinstance(u, dict) and not u.get("active",True)
                     and u.get("staff_code")}
    bsc = json.loads((REPO/"data"/"bsc_scores.json").read_text(encoding="utf-8"))
    assert not any(str(r.get("staff_code","")) in inactive_codes
                  for r in bsc if isinstance(r,dict))


def test_v10469_manifest_disk_consistency():
    manifest = json.loads((REPO/"pages"/"_manifest.json").read_text(encoding="utf-8"))
    disk = {p.name for p in (REPO/"pages").glob("*.py") if not p.name.startswith("_")}
    mp = set(manifest.get("pages", {}).keys())
    assert mp == disk
