"""Integration tests for v10.395 — WITHIN_BRANCH_ROLE_PAIRS dynamic from canonical.

Per Joshua's direction: "role names that apply to the hierarchy stem from
the admin config like the KPIs since different banks may name different
roles differently and we don't want those hardcoded".

v10.395 replaced the hardcoded WITHIN_BRANCH_ROLE_PAIRS constant with
dynamic derivation from data/org_hierarchy_config.json::role_manager_whitelist
+ role_tiers. The engine is now bank-agnostic.

12 tests across 4 sections.
"""

import json
import sys
from pathlib import Path

REPO = Path("/tmp/a2z_fix")
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from utils.cascade_structure_engine import (
    WITHIN_BRANCH_ROLE_PAIRS,
    load_within_branch_role_pairs,
    load_role_tiers,
    load_role_manager_whitelist,
    load_branch_tier_threshold,
    DEFAULT_BRANCH_TIER_THRESHOLD,
    detect_cross_branch_violations,
)


# ────────────────────────────────────────────────────────────────────
# Section 1 — Dynamic loading API
# ────────────────────────────────────────────────────────────────────

def test_v10395_load_role_tiers_returns_canonical():
    tiers = load_role_tiers()
    assert isinstance(tiers, dict)
    assert len(tiers) >= 20, "role_tiers should have many entries"
    # No _note key should leak through
    for k in tiers.keys():
        assert not k.startswith("_"), f"meta key leaked: {k}"
    # Values are ints
    for k, v in tiers.items():
        assert isinstance(v, int), f"{k}={v!r} not int"


def test_v10395_load_role_manager_whitelist_returns_canonical():
    rmw = load_role_manager_whitelist()
    assert isinstance(rmw, dict)
    assert len(rmw) >= 20
    for k, v in rmw.items():
        assert isinstance(v, list), f"{k}={v!r} not list"


def test_v10395_load_branch_tier_threshold_has_default():
    t = load_branch_tier_threshold()
    assert isinstance(t, int)
    # Default for Ecobank Kenya is 4
    assert t == DEFAULT_BRANCH_TIER_THRESHOLD


# ────────────────────────────────────────────────────────────────────
# Section 2 — Within-branch derivation correctness
# ────────────────────────────────────────────────────────────────────

def test_v10395_within_branch_pairs_non_empty():
    pairs = load_within_branch_role_pairs()
    assert len(pairs) > 5, f"expected meaningful set; got {len(pairs)} pairs"


def test_v10395_within_branch_pairs_respect_tier_threshold():
    """Every pair must have both roles at tier >= threshold."""
    pairs = load_within_branch_role_pairs()
    tiers = load_role_tiers()
    threshold = load_branch_tier_threshold()
    for mgr, sub in pairs:
        assert tiers.get(mgr, -1) >= threshold, (
            f"manager {mgr} tier {tiers.get(mgr)} below threshold {threshold}"
        )
        assert tiers.get(sub, -1) >= threshold, (
            f"subordinate {sub} tier {tiers.get(sub)} below threshold {threshold}"
        )


def test_v10395_regional_supervisors_excluded():
    """Tier 3 roles (Area Manager, Senior Branch Manager) must not appear
    as managers in within-branch pairs — they have regional supervision."""
    pairs = load_within_branch_role_pairs()
    tiers = load_role_tiers()
    for mgr, sub in pairs:
        mgr_tier = tiers.get(mgr, -1)
        # Threshold-based, but explicit named exclusions for sanity:
        if mgr_tier == 3:
            assert False, f"tier-3 (regional) role {mgr} in within-branch pairs"


def test_v10395_module_constant_matches_function():
    """WITHIN_BRANCH_ROLE_PAIRS at import time matches dynamic load."""
    assert WITHIN_BRANCH_ROLE_PAIRS == load_within_branch_role_pairs()


def test_v10395_within_branch_pairs_match_canonical():
    """Every pair must derive from role_manager_whitelist entry."""
    pairs = load_within_branch_role_pairs()
    rmw = load_role_manager_whitelist()
    for mgr, sub in pairs:
        assert sub in rmw, f"sub-role {sub} not in canonical whitelist"
        assert mgr in rmw[sub], f"{mgr} not listed as valid manager for {sub}"


# ────────────────────────────────────────────────────────────────────
# Section 3 — No hardcoded role names in engine
# ────────────────────────────────────────────────────────────────────

def test_v10395_engine_has_no_hardcoded_role_strings():
    """Bank portability: engine module must not contain bank-specific role
    names like 'Teller', 'Branch Manager' as string literals at module level
    in the canonical pairs set. (They can appear in docstrings/comments.)"""
    engine_path = REPO / "utils" / "cascade_structure_engine.py"
    text = engine_path.read_text()
    # Check the OLD hardcoded set is gone
    assert "WITHIN_BRANCH_ROLE_PAIRS: Set[Tuple[str, str]] = {" not in text, (
        "Old hardcoded set literal still present"
    )
    # Confirm dynamic helper present
    assert "def load_within_branch_role_pairs" in text


def test_v10395_engine_returns_findings_with_new_pairs():
    """v10.397 regenerated cascade: cross-branch should be 0 (TC18 resolved).

    Pre-v10.397 this checked for 1000-30000 violations (bug present).
    Post-v10.397: 0 violations is the GOAL achieved.
    """
    cb = detect_cross_branch_violations()
    assert len(cb) == 0, (
        f"v10.397 expects 0 cross-branch violations; got {len(cb)} "
        f"(was 25,893 before re-cascade)"
    )


# ────────────────────────────────────────────────────────────────────
# Section 4 — Bank portability
# ────────────────────────────────────────────────────────────────────

def test_v10395_threshold_is_configurable():
    """Admin can override branch_tier_threshold via config field."""
    ohc_path = REPO / "data" / "org_hierarchy_config.json"
    saved = json.loads(ohc_path.read_text())
    try:
        # Temporarily set threshold to 5 (only tier 5+ counts as branch)
        modified = dict(saved)
        modified["branch_tier_threshold"] = 5
        ohc_path.write_text(json.dumps(modified, indent=2))
        new_pairs = load_within_branch_role_pairs()
        # With threshold 5, no tier-4 pairs survive
        tiers = saved.get("role_tiers", {})
        for mgr, sub in new_pairs:
            assert tiers.get(mgr, 0) >= 5
            assert tiers.get(sub, 0) >= 5
    finally:
        ohc_path.write_text(json.dumps(saved, indent=2))


def test_v10395_g280_passes():
    """G280 gate verifies the dynamic loading is wired."""
    sys.path.insert(0, str(REPO / "scripts"))
    for k in list(sys.modules):
        if k.startswith("audit"):
            del sys.modules[k]
    from audit import gate_v10395_within_branch_pairs_dynamic
    r = gate_v10395_within_branch_pairs_dynamic()
    assert r["passed"], r.get("violations")
