"""Integration tests for v10.394 — Line Manager Hierarchy & Fixed KPI Review.

Review-only batch. Verifies the design doc claims hold against live data:
1. Fixed KPI mechanism exists and is MD-controlled
2. NPL is NOT in current fixed list (correctly per-branch)
3. NPL_RATIO contradiction exists (TC39)
4. role_manager_whitelist is the canonical hierarchy
5. WITHIN_BRANCH_ROLE_PAIRS diverges from canonical (TC40)

12 tests across 4 sections.
"""

import json
import sys
from pathlib import Path

REPO = Path("/tmp/a2z_fix")
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


def _load(path):
    return json.loads((REPO / "data" / path).read_text())


# ────────────────────────────────────────────────────────────────────
# Section 1 — Fixed KPI mechanism
# ────────────────────────────────────────────────────────────────────

def test_v10394_fixed_kpis_json_exists():
    p = REPO / "data" / "fixed_kpis.json"
    assert p.exists()


def test_v10394_fixed_kpis_has_quarterly_periods():
    """Fixed KPIs use quarterly periods (2025-Q3, 2026-Q1, etc.)."""
    fk = _load("fixed_kpis.json")
    quarterly = [k for k in fk.keys() if "-Q" in k]
    assert len(quarterly) >= 2, f"expected quarterly periods; got {list(fk.keys())[:5]}"


def test_v10394_cx_score_is_currently_fixed():
    """Per Joshua: CX Score 90% bank-wide → fixed in current period."""
    fk = _load("fixed_kpis.json")
    # Check any current period
    for k in fk.keys():
        if k.startswith("2026"):
            kpis = fk[k].get("kpis", []) if isinstance(fk[k], dict) else []
            if "CX Score" in kpis:
                return
    assert False, "CX Score should be in fixed list for 2026 period"


def test_v10394_npl_ratio_human_name_not_fixed():
    """Per Joshua: NPL varies branch-to-branch → 'NPL Ratio' (human name)
    should NOT be in current fixed list."""
    fk = _load("fixed_kpis.json")
    for k in fk.keys():
        if k.startswith("2026"):
            kpis = fk[k].get("kpis", []) if isinstance(fk[k], dict) else []
            assert "NPL Ratio" not in kpis, (
                f"'NPL Ratio' should NOT be fixed (varies per branch); "
                f"found in {k}"
            )


def _retired_v10402_test_v10394_npl_uppercase_naming_contradiction():
    """TC39: NPL_RATIO (uppercase) IS in current fixed list — contradicts
    NPL Ratio (human) being removed. Naming bug."""
    fk = _load("fixed_kpis.json")
    found_uppercase = False
    for k in fk.keys():
        if k.startswith("2026"):
            kpis = fk[k].get("kpis", []) if isinstance(fk[k], dict) else []
            if "NPL_RATIO" in kpis:
                found_uppercase = True
    assert found_uppercase, (
        "TC39: NPL_RATIO uppercase variant in fixed list "
        "(contradicts NPL Ratio being removed)"
    )


def test_v10394_per_branch_kpis_correctly_removed():
    """PBT, Total NFI, NIM, ROE, CIR should be in _v10324_removed_from_fixed."""
    fk = _load("fixed_kpis.json")
    for k in fk.keys():
        if k.startswith("2026"):
            removed = fk[k].get("_v10324_removed_from_fixed", []) if isinstance(fk[k], dict) else []
            for must_be_removed in ["PBT", "Total NFI", "NIM", "ROE", "CIR"]:
                assert must_be_removed in removed, (
                    f"{must_be_removed} should be in removed-from-fixed "
                    f"(varies per unit; found removed: {removed})"
                )
            return  # one period is enough


# ────────────────────────────────────────────────────────────────────
# Section 2 — Canonical hierarchy
# ────────────────────────────────────────────────────────────────────

def test_v10394_role_manager_whitelist_is_canonical():
    """org_hierarchy_config.json::role_manager_whitelist is canonical."""
    ohc = _load("org_hierarchy_config.json")
    rmw = ohc.get("role_manager_whitelist", {})
    assert isinstance(rmw, dict)
    # Filter _note keys
    real = {k: v for k, v in rmw.items() if not k.startswith("_")}
    assert len(real) >= 20, f"expected ~26 subordinate roles; got {len(real)}"


def test_v10394_canonical_uses_actual_data_role_names():
    """Canonical uses 'Chief Retail Banking Officer' not 'Director Retail Banking'."""
    ohc = _load("org_hierarchy_config.json")
    rmw = ohc.get("role_manager_whitelist", {})
    # Collect all manager role names
    all_managers = set()
    for k, v in rmw.items():
        if k.startswith("_"): continue
        if isinstance(v, list):
            all_managers.update(v)
    # Expected canonical names
    assert "Chief Retail Banking Officer" in all_managers
    assert "Area Manager" in all_managers
    # Pre-canonical names that pipeline _HIER uses should NOT appear here
    assert "Director Retail Banking" not in all_managers
    assert "Regional Head" not in all_managers


def test_v10394_branch_credit_manager_not_in_canonical():
    """Confirms v10.391 TC17: BCM role doesn't exist in canonical hierarchy."""
    ohc = _load("org_hierarchy_config.json")
    rmw = ohc.get("role_manager_whitelist", {})
    real = {k: v for k, v in rmw.items() if not k.startswith("_")}
    # BCM should not be a key (no subordinate reports to BCM in canonical)
    assert "Branch Credit Manager" not in real
    # BCM should not appear as a manager either
    for k, mgrs in real.items():
        if isinstance(mgrs, list):
            assert "Branch Credit Manager" not in mgrs


# ────────────────────────────────────────────────────────────────────
# Section 3 — Structure engine divergence (TC40)
# ────────────────────────────────────────────────────────────────────

def test_v10394_engine_within_branch_pairs_diverges_from_canonical_RETIRED_v10395():
    """RETIRED v10.395: TC40 divergence resolved.

    v10.395 aligned WITHIN_BRANCH_ROLE_PAIRS to canonical via dynamic
    derivation from org_hierarchy_config.json. The divergence this test
    expected (9 missing + 6 extra pairs) is now zero. Retired; replaced
    by test_v10395_within_branch_pairs_match_canonical.
    """
    return  # skip — TC40 fixed by v10.395


# ────────────────────────────────────────────────────────────────────
# Section 4 — Design doc + gate
# ────────────────────────────────────────────────────────────────────

def test_v10394_design_doc_has_10_parts():
    p = REPO / "docs" / "LINE_MANAGER_HIERARCHY_AND_FIXED_KPI_REVIEW_v10.394.md"
    assert p.exists()
    text = p.read_text()
    for part in range(1, 11):
        assert f"## Part {part}" in text, f"missing Part {part}"


def test_v10394_g279_passes():
    sys.path.insert(0, str(REPO / "scripts"))
    for k in list(sys.modules):
        if k.startswith("audit"):
            del sys.modules[k]
    from audit import gate_v10394_hierarchy_and_fixed_kpi_review
    r = gate_v10394_hierarchy_and_fixed_kpi_review()
    assert r["passed"], r.get("violations")
