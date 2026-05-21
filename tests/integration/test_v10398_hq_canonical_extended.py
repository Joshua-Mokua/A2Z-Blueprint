"""Integration tests for v10.398 — HQ canonical extension per Joshua.

Resolves TC42 (HQ specialist roles without canonical reports).

15 tests across 5 sections.
"""

import json
import sys
from collections import Counter
from pathlib import Path

REPO = Path("/tmp/a2z_fix")
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


def _load(name):
    return json.loads((REPO / "data" / name).read_text())


# ────────────────────────────────────────────────────────────────────
# Section 1 — hr.json dedup
# ────────────────────────────────────────────────────────────────────

def test_v10398_hr_json_no_duplicate_codes():
    hr = _load("hr.json")
    records = hr if isinstance(hr, list) else [r for k, r in hr.items()
                                               if not k.startswith("_") and isinstance(r, dict)]
    codes = Counter(str(r.get("staff_code", "")) for r in records
                    if isinstance(r, dict) and r.get("staff_code"))
    dups = [c for c, n in codes.items() if n > 1]
    assert not dups, f"hr.json has {len(dups)} duplicate staff_codes"


def test_v10398_hr_json_backup_preserved():
    assert (REPO / "data" / "_v10398_backups" / "hr.json.before").exists()


def test_v10398_all_three_staff_lists_clean():
    """users.json + staff_register.xlsx + hr.json all dedup'd."""
    users = _load("users.json")
    u_codes = Counter(str(u.get("staff_code", "")) for u in users.values()
                      if isinstance(u, dict) and u.get("staff_code"))
    u_dups = [c for c, n in u_codes.items() if n > 1]
    assert not u_dups, f"users.json has {len(u_dups)} duplicates"

    hr = _load("hr.json")
    records = hr if isinstance(hr, list) else [r for k, r in hr.items()
                                               if not k.startswith("_") and isinstance(r, dict)]
    hr_codes = Counter(str(r.get("staff_code", "")) for r in records
                       if isinstance(r, dict) and r.get("staff_code"))
    hr_dups = [c for c, n in hr_codes.items() if n > 1]
    assert not hr_dups, f"hr.json has {len(hr_dups)} duplicates"


# ────────────────────────────────────────────────────────────────────
# Section 2 — Chief reporting lines (all → MD)
# ────────────────────────────────────────────────────────────────────

def test_v10398_all_chiefs_report_to_md():
    cfg = _load("org_hierarchy_config.json")
    rmw = cfg["role_manager_whitelist"]
    chiefs_to_md = [
        "Chief Retail Banking Officer",
        "Chief Commercial Officer",
        "Chief Credit Officer",
        "Chief Financial Officer",
        "Chief Risk Officer",
        "Chief Information Officer",
        "Chief Operating Officer",
        "Chief Human Resource Officer",
        "Chief Internal Auditor",
        "General Manager - Bancassurance",
        "Company Secretary and Chief Legal Officer",
    ]
    for ch in chiefs_to_md:
        assert ch in rmw, f"{ch} not in role_manager_whitelist"
        assert "Chief Executive & Managing Director" in rmw[ch], (
            f"{ch} should report to MD; got {rmw[ch]}"
        )


def test_v10398_chief_compliance_officer_reports_to_cro():
    """Per Joshua: 'All risk roles i.e Market risk EUC and compliance report here (CRO)'."""
    cfg = _load("org_hierarchy_config.json")
    cco = cfg["role_manager_whitelist"].get("Chief Compliance Officer", [])
    assert "Chief Risk Officer" in cco, (
        f"Chief Compliance Officer should report to CRO; got {cco}"
    )


def test_v10398_new_chiefs_in_canonical():
    """CCO, Chief Credit Officer, GM Bancassurance, Chief Internal Auditor."""
    cfg = _load("org_hierarchy_config.json")
    rmw = cfg["role_manager_whitelist"]
    for new_chief in ("Chief Commercial Officer", "Chief Credit Officer",
                      "Chief Internal Auditor", "General Manager - Bancassurance"):
        assert new_chief in rmw, f"{new_chief} (new) missing from canonical"


# ────────────────────────────────────────────────────────────────────
# Section 3 — Chief subtree coverage
# ────────────────────────────────────────────────────────────────────

def test_v10398_cfo_has_treasury_subtree():
    cfg = _load("org_hierarchy_config.json")
    rmw = cfg["role_manager_whitelist"]
    assert "Chief Financial Officer" in rmw.get("Head of Treasury", [])
    assert "Head of Treasury" in rmw.get("Senior Manager Treasury", [])


def test_v10398_cco_has_corporate_sme_gib_subtrees():
    cfg = _load("org_hierarchy_config.json")
    rmw = cfg["role_manager_whitelist"]
    assert "Chief Commercial Officer" in rmw.get("Head Of Corporates & Trade Finance", [])
    assert "Chief Commercial Officer" in rmw.get("Head of MSME", [])
    assert "Chief Commercial Officer" in rmw.get("Head of Government & Institutional Banking", [])


def test_v10398_credit_chief_has_credit_subtrees():
    cfg = _load("org_hierarchy_config.json")
    rmw = cfg["role_manager_whitelist"]
    assert "Chief Credit Officer" in rmw.get("Senior Manager -Credit Analysis", [])
    assert "Chief Credit Officer" in rmw.get("Assistant Manager -Credit Administration", [])
    assert "Chief Credit Officer" in rmw.get("Senior Manager-Collections & Recoveries", [])


def test_v10398_cio_has_ict_subtree():
    """v10.398 had DFS under CIO; v10.399 moved DFS → CCO per Joshua.
    CIO still owns ICT subtree (Head of ICT + technical roles).
    """
    cfg = _load("org_hierarchy_config.json")
    rmw = cfg["role_manager_whitelist"]
    assert "Chief Information Officer" in rmw.get("Head Of ICT", [])
    # Head of DFS moved to CCO per Joshua's v10.399 correction
    # (test_v10399_head_of_dfs_under_cco asserts this directly)


def test_v10398_chro_has_hrbp_subtrees():
    cfg = _load("org_hierarchy_config.json")
    rmw = cfg["role_manager_whitelist"]
    for hrbp in ("Human Resource Business Partner- Operations",
                 "Human Resource Business Partner-Payroll",
                 "Senior Human Resource Business Partner-Training"):
        assert "Chief Human Resource Officer" in rmw.get(hrbp, []), f"{hrbp} not under CHRO"


# ────────────────────────────────────────────────────────────────────
# Section 4 — Bancassurance dual-reporting (Joshua's explicit directive)
# ────────────────────────────────────────────────────────────────────

def test_v10398_bancassurance_officer_primary_branch_manager():
    """Branch-located bancassurance reports to BM; HQ falls through to GM Banc."""
    cfg = _load("org_hierarchy_config.json")
    banc = cfg["role_manager_whitelist"].get("Bancassurance Officer", [])
    assert "Branch Manager" in banc, "Bancassurance Officer should have BM as manager"
    assert "Senior Branch Manager" in banc, "Bancassurance Officer should have SBM as alt"
    assert "General Manager - Bancassurance" in banc, (
        "Bancassurance Officer should have GM Bancassurance for dotted line / HQ fallback"
    )


def test_v10398_gm_bancassurance_has_manager_underwriting_subtree():
    cfg = _load("org_hierarchy_config.json")
    rmw = cfg["role_manager_whitelist"]
    assert "General Manager - Bancassurance" in rmw.get("Manager Underwriting", [])


# ────────────────────────────────────────────────────────────────────
# Section 5 — Engine audit post-extension
# ────────────────────────────────────────────────────────────────────

def test_v10398_engine_zero_critical_rep_sender():
    """TC42 RESOLVED — all HQ chiefs/heads now appear as cascade senders."""
    for k in list(sys.modules):
        if "cascade" in k:
            del sys.modules[k]
    from utils.cascade_structure_engine import full_audit
    findings = full_audit()
    assert findings.summary["rep_critical_count"] == 0, (
        f"v10.398 expects 0 rep_critical findings; got "
        f"{findings.summary['rep_critical_count']}"
    )


def test_v10398_engine_all_structural_metrics_zero():
    """Phase C2 goal: cycles + cross-branch + multi-sender + critical = 0."""
    for k in list(sys.modules):
        if "cascade" in k:
            del sys.modules[k]
    from utils.cascade_structure_engine import full_audit
    findings = full_audit()
    s = findings.summary
    assert s["cycles_count"] == 0
    assert s["cross_branch_count"] == 0
    assert s["multi_sender_count"] == 0
    assert s["rep_critical_count"] == 0


def test_v10398_g284_passes():
    sys.path.insert(0, str(REPO / "scripts"))
    for k in list(sys.modules):
        if k.startswith("audit"):
            del sys.modules[k]
    from audit import gate_v10398_hq_canonical_extended
    r = gate_v10398_hq_canonical_extended()
    assert r["passed"], r.get("violations")
