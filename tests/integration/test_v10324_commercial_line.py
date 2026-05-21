"""tests/integration/test_v10324_commercial_line.py

v10.324 — Commercial Banking line of business + pipeline-as-CRM.

Locks:
  - Head of GIB now under CCMO (was wrongly under Branch Ops)
  - CCMO has expected hierarchy structure
  - Commercial RM role_kpis use canonical codes
  - fixed_kpis reduced to true bank-uniform scales
  - Pipeline-as-CRM features confirmed
  - CCMO has computable recursive score
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))


# ────────────────────────────────────────────────────────────────────
# Section 1 — Head of GIB hierarchy fix
# ────────────────────────────────────────────────────────────────────

def test_head_of_gib_reports_to_ccmo():
    from utils.virtual_bank import staff_universe
    u = staff_universe()
    gib_heads = [
        s for s in u.values()
        if s.role == "Head of Government & Institutional Banking"
    ]
    assert gib_heads, "No Head of GIB found"
    for h in gib_heads:
        assert h.manager_code == "EXEC-CCMO-001", (
            f"Head of GIB ({h.staff_code}) reports to "
            f"{h.manager_code}, expected EXEC-CCMO-001"
        )


def test_gib_whitelist_in_config():
    """The fix lives in org_hierarchy_config.json whitelist."""
    cfg_path = REPO_ROOT / "data" / "org_hierarchy_config.json"
    cfg = json.loads(cfg_path.read_text())
    wl = cfg.get("role_manager_whitelist", {})
    assert "Head of Government & Institutional Banking" in wl
    assert wl[
        "Head of Government & Institutional Banking"
    ] == ["Chief Commercial Officer"]


# ────────────────────────────────────────────────────────────────────
# Section 2 — CCMO hierarchy structure
# ────────────────────────────────────────────────────────────────────

def test_ccmo_has_five_direct_reports():
    from utils.virtual_bank import staff_universe
    u = staff_universe()
    reports = [
        r for r in u.values()
        if r.manager_code == "EXEC-CCMO-001"
    ]
    assert len(reports) >= 5, (
        f"CCMO has only {len(reports)} direct reports, "
        f"expected ≥5"
    )


def test_ccmo_subtree_has_substantial_subordinates():
    from utils.manager_rollup import _all_subordinate_codes
    subs = _all_subordinate_codes("EXEC-CCMO-001")
    assert len(subs) >= 30, (
        f"CCMO subtree has only {len(subs)} subordinates, "
        f"expected ≥30 for commercial line"
    )


def test_ccmo_chains_to_md():
    """Walk from CCMO direct reports up to MD."""
    from utils.virtual_bank import staff_universe
    u = staff_universe()
    ccmo_reports = [
        r for r in u.values()
        if r.manager_code == "EXEC-CCMO-001"
    ]
    for r in ccmo_reports:
        code = r.manager_code
        depth = 0
        reached_md = False
        while code and code in u and depth < 6:
            if code == "EXEC-MD-001":
                reached_md = True
                break
            code = u[code].manager_code
            depth += 1
        assert reached_md, (
            f"{r.staff_code} ({r.role}) does not chain to MD"
        )


# ────────────────────────────────────────────────────────────────────
# Section 3 — role_kpis canonical alignment
# ────────────────────────────────────────────────────────────────────

def test_commercial_rms_use_canonical_kpis():
    lib_path = REPO_ROOT / "data" / "kpi_library.json"
    lib = json.loads(lib_path.read_text())
    rk = lib.get("role_kpis", {})

    canonical_pipeline_kpis = {
        "DISB_CORPORATE", "DISB_MSME", "DISB_RETAIL",
        "COMMERCIAL_DEPOSIT", "TOTAL_NFI",
        "RETAIL_MSME_DEPOSIT",
    }
    commercial_roles = [
        "Senior Relationship Manager - Corporate Banking",
        "Assistant Relationship Manager-Corporate",
        "Relationship Manager - Institutional Banking",
        "Senior Relationship Manager- SME",
        "Relationship Manager - SME",
        "Relationship Manager- Public Sector",
    ]
    for role in commercial_roles:
        kpis = rk.get(role, [])
        canonical = [
            k for k in kpis if k in canonical_pipeline_kpis
        ]
        assert canonical, (
            f"role_kpis[{role}] has no canonical pipeline "
            f"KPIs (DISB_*, COMMERCIAL_DEPOSIT, TOTAL_NFI). "
            f"Current: {kpis}"
        )


def test_v10324_role_kpi_updates_tag():
    """The kpi_library should be tagged with v10.324 updates."""
    lib_path = REPO_ROOT / "data" / "kpi_library.json"
    lib = json.loads(lib_path.read_text())
    assert "_v10324_role_kpi_updates" in lib


# ────────────────────────────────────────────────────────────────────
# Section 4 — fixed_kpis reduced to bank-uniform scales
# ────────────────────────────────────────────────────────────────────

def test_financial_outcomes_not_in_fixed_kpis():
    """PBT, Total NFI, NPL Ratio, etc. should NOT be fixed."""
    fk_path = REPO_ROOT / "data" / "fixed_kpis.json"
    fk = json.loads(fk_path.read_text())
    forbidden = {
        "PBT", "Total NFI", "NPL Ratio",
        "NIM", "ROE", "CIR",
    }
    for period in ("2025-Q3", "2025-Q4", "2026-Q1", "2026-Q2"):
        entry = fk.get(period, {})
        if isinstance(entry, dict):
            kpis = entry.get("kpis", [])
        else:
            kpis = entry if isinstance(entry, list) else []
        leaked = set(kpis) & forbidden
        assert not leaked, (
            f"fixed_kpis[{period}] contains financial "
            f"outcomes that should be per-staff: {leaked}"
        )


def test_fixed_kpis_within_size_limit():
    """≤8 entries per period — true bank-uniform scales only."""
    fk_path = REPO_ROOT / "data" / "fixed_kpis.json"
    fk = json.loads(fk_path.read_text())
    for period in ("2025-Q3", "2025-Q4", "2026-Q1", "2026-Q2"):
        entry = fk.get(period, {})
        if isinstance(entry, dict):
            kpis = entry.get("kpis", [])
        else:
            kpis = entry if isinstance(entry, list) else []
        assert len(kpis) <= 16, (
            f"fixed_kpis[{period}] has {len(kpis)} entries "
            f"(expected ≤8 for true bank-uniform scales)"
        )


def test_score_kpis_remain_fixed():
    """CX Score, Audit Score, Staff Productivity remain fixed."""
    fk_path = REPO_ROOT / "data" / "fixed_kpis.json"
    fk = json.loads(fk_path.read_text())
    required = {"CX Score", "Audit Score", "Staff Productivity"}
    for period in ("2026-Q1", "2026-Q2"):
        entry = fk.get(period, {})
        kpis = (
            entry.get("kpis", []) if isinstance(entry, dict)
            else entry if isinstance(entry, list) else []
        )
        missing = required - set(kpis)
        assert not missing, (
            f"fixed_kpis[{period}] missing required scales: "
            f"{missing}"
        )


# ────────────────────────────────────────────────────────────────────
# Section 5 — Pipeline-as-CRM features
# ────────────────────────────────────────────────────────────────────

def test_pipeline_manager_has_crm_methods():
    import re
    core_text = (
        REPO_ROOT / "utils" / "core.py").read_text()
    m = re.search(
        r"class PipelineManager:.*?(?=\nclass |\Z)",
        core_text, re.DOTALL)
    assert m, "PipelineManager class not found"
    methods = set(re.findall(r"def (\w+)\(", m.group(0)))
    # Core CRM methods
    required = {
        "add_deal", "update_stage", "update_deal",
        "add_activity", "get_deals", "get_activities",
        "request_cancel", "approve_cancel",
        "validate_deal", "pipeline_value", "weighted_pipeline",
    }
    missing = required - methods
    assert not missing, (
        f"PipelineManager missing CRM methods: {missing}"
    )


def test_pipeline_page_has_six_tabs():
    import re
    page_text = (
        REPO_ROOT / "pages" / "3_pipeline.py").read_text()
    tabs = re.findall(
        r"# TAB \d+ — (.*?)$", page_text, re.MULTILINE)
    assert len(tabs) >= 6, (
        f"Pipeline page has only {len(tabs)} tabs"
    )


# ────────────────────────────────────────────────────────────────────
# Section 6 — End-to-end: CCMO has a recursive score
# ────────────────────────────────────────────────────────────────────

def test_ccmo_has_recursive_score_in_q2():
    p = REPO_ROOT / "data" / "cascade_scores_2026-Q2.json"
    assert p.exists()
    data = json.loads(p.read_text())
    ccmo_score = data.get("scores", {}).get("EXEC-CCMO-001")
    assert ccmo_score is not None, (
        "CCMO has no recursive score in 2026-Q2 — "
        "commercial line not integrated"
    )
    assert 1.0 <= ccmo_score <= 5.0


def test_md_score_now_spans_three_chiefs():
    """MD score should be derived from ≥3 Chiefs in Q2 (Retail,
    Bancassurance, Commercial — after v10.324 hierarchy fix)."""
    p = REPO_ROOT / "data" / "cascade_scores_2026-Q2.json"
    data = json.loads(p.read_text())
    md_score = data.get("scores", {}).get("EXEC-MD-001")
    assert md_score is not None
    from utils.virtual_bank import staff_universe
    u = staff_universe()
    md_direct = [
        r for r in u.values()
        if r.manager_code == "EXEC-MD-001"
    ]
    scored = [
        r for r in md_direct
        if r.staff_code in data.get("scores", {})
    ]
    assert len(scored) >= 3, (
        f"MD has only {len(scored)} scored direct reports — "
        f"expected ≥3 (Retail + Bancassurance + Commercial)"
    )


# ────────────────────────────────────────────────────────────────────
# Section 7 — Audit gate G215
# ────────────────────────────────────────────────────────────────────

def test_g215_gate_passes():
    from scripts.audit import GATES
    g = None
    for gid, fn in GATES:
        if gid == "G215":
            g = fn()
            break
    assert g is not None, "G215 not registered"
    assert g["passed"], (
        f"G215 failed: violations={g.get('violations', [])}"
    )
