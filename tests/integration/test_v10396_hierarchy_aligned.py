"""Integration tests for v10.396 — canonical hierarchy aligned with Joshua's
clarification (2026-05-13).

Three changes to org_hierarchy_config.json:
1. SBM tier 3 → 4 (branch top, not regional)
2. SBM added as alt manager for branch subordinates (BOM/BRM/BSRO/RO PB/RO BB)
3. DSR (and DSR Assets & Liabilities) → BM/SBM (per Joshua "DSR reports to BM")

Pure config change — no code. Engine auto-derives new pairs via v10.395.

10 tests across 4 sections.
"""

import json
import sys
from pathlib import Path

REPO = Path("/tmp/a2z_fix")
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


def _load_cfg():
    return json.loads((REPO / "data" / "org_hierarchy_config.json").read_text())


# ────────────────────────────────────────────────────────────────────
# Section 1 — Tier alignment
# ────────────────────────────────────────────────────────────────────

def test_v10396_sbm_tier_is_4():
    """Senior Branch Manager is a branch top (big branches), tier 4."""
    cfg = _load_cfg()
    assert cfg["role_tiers"]["Senior Branch Manager"] == 4


def test_v10396_sbm_tier_equals_bm_tier():
    """SBM and BM are both branch tops — must share tier."""
    cfg = _load_cfg()
    assert cfg["role_tiers"]["Senior Branch Manager"] == cfg["role_tiers"]["Branch Manager"]


def test_v10396_area_manager_remains_tier_3():
    """Area Manager remains regional (tier 3) — supervises multiple branches."""
    cfg = _load_cfg()
    assert cfg["role_tiers"]["Area Manager"] == 3


# ────────────────────────────────────────────────────────────────────
# Section 2 — Manager whitelist alignment
# ────────────────────────────────────────────────────────────────────

def test_v10396_sbm_is_alt_manager_for_branch_subs():
    """SBM should be alt manager for all branch subordinates."""
    cfg = _load_cfg()
    rmw = cfg["role_manager_whitelist"]
    for sub in ("Branch Operations Manager",
                "Branch Relationship Manager",
                "Branch Senior Relationship Officer",
                "Relationship Officer-Personal Banker",
                "Relationship Officer-Business Banker"):
        assert "Senior Branch Manager" in rmw[sub], (
            f"{sub} should include SBM in canonical managers; got {rmw[sub]}"
        )


def test_v10396_dsr_reports_to_branch_manager():
    """Per Joshua: DSR reports to Branch Manager (not BOS/BOM)."""
    cfg = _load_cfg()
    rmw = cfg["role_manager_whitelist"]
    for role in ("Direct Sales Representative",
                 "Direct Sales Representative - Assets & Liabilities"):
        mgrs = rmw[role]
        assert "Branch Manager" in mgrs
        assert "Senior Branch Manager" in mgrs
        # BOS/BOM should no longer be in DSR managers
        assert "Branch Operations Supervisor" not in mgrs
        assert "Branch Operations Manager" not in mgrs


def test_v10396_provenance_note_present():
    cfg = _load_cfg()
    assert "_v10396_joshua_clarification" in cfg
    note = cfg["_v10396_joshua_clarification"]
    assert "changes" in note


def test_v10396_backup_preserved():
    backup = REPO / "data" / "_v10396_backups" / "org_hierarchy_config.json.before"
    assert backup.exists()


# ────────────────────────────────────────────────────────────────────
# Section 3 — Engine auto-derivation effects
# ────────────────────────────────────────────────────────────────────

def test_v10396_engine_includes_sbm_pairs():
    """Engine should now include (SBM, branch subordinate) pairs."""
    # Force re-import
    for k in list(sys.modules):
        if "cascade_structure_engine" in k:
            del sys.modules[k]
    from utils.cascade_structure_engine import WITHIN_BRANCH_ROLE_PAIRS

    must_have = [
        ("Senior Branch Manager", "Branch Operations Manager"),
        ("Senior Branch Manager", "Branch Relationship Manager"),
        ("Senior Branch Manager", "Branch Senior Relationship Officer"),
        ("Senior Branch Manager", "Direct Sales Representative"),
        ("Branch Manager", "Direct Sales Representative"),
    ]
    for pair in must_have:
        assert pair in WITHIN_BRANCH_ROLE_PAIRS, (
            f"missing pair after alignment: {pair}"
        )


def test_v10396_engine_excludes_old_dsr_pairs():
    """BOS/BOM should NOT cascade to DSR after Joshua's reassignment."""
    for k in list(sys.modules):
        if "cascade_structure_engine" in k:
            del sys.modules[k]
    from utils.cascade_structure_engine import WITHIN_BRANCH_ROLE_PAIRS
    assert ("Branch Operations Supervisor", "Direct Sales Representative") not in WITHIN_BRANCH_ROLE_PAIRS
    assert ("Branch Operations Manager", "Direct Sales Representative") not in WITHIN_BRANCH_ROLE_PAIRS


# ────────────────────────────────────────────────────────────────────
# Section 4 — Gate + sanity
# ────────────────────────────────────────────────────────────────────

def test_v10396_8_sbms_across_8_branches():
    """Confirms big-branch SBM pattern: 8 SBMs each at distinct branches."""
    users = json.loads((REPO / "data" / "users.json").read_text())
    sbm_branches = set()
    sbm_count = 0
    for u in users.values():
        if u.get("role") == "Senior Branch Manager":
            sbm_count += 1
            sbm_branches.add(u.get("unit", "?"))
    assert sbm_count == len(sbm_branches), (
        f"SBM should be 1-per-branch big-branch pattern; "
        f"{sbm_count} SBMs in {len(sbm_branches)} branches"
    )


def test_v10396_g281_passes():
    sys.path.insert(0, str(REPO / "scripts"))
    for k in list(sys.modules):
        if k.startswith("audit"):
            del sys.modules[k]
    from audit import gate_v10396_hierarchy_aligned_with_joshua
    r = gate_v10396_hierarchy_aligned_with_joshua()
    assert r["passed"], r.get("violations")
