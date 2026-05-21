"""Integration tests for v10.399 — Joshua's 7-point HQ canonical corrections.

Per Joshua 2026-05-13:
1. Delete synthetic Managing Director (keep only Chief Executive & MD)
2. Head of DFS → CCO (was CIO)
3. Manager Card Operations remains under DFS (now via CCO)
4. Corporate Sales Dealer confirmed under Treasury (CFO)
5. Trade Finance Back Office Manager confirmed under Head of Operations
6. Trade Finance split (relationships → CCO, operations → COO) confirmed
7. Admin role under MD (developer/login, not CHRO)

10 tests across 3 sections.
"""

import json
import sys
from pathlib import Path

REPO = Path("/tmp/a2z_fix")
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


def _load(name):
    return json.loads((REPO / "data" / name).read_text())


# ────────────────────────────────────────────────────────────────────
# Section 1 — Synthetic Managing Director deleted (C1 resolved)
# ────────────────────────────────────────────────────────────────────

def test_v10399_synthetic_md_deleted():
    """Only one MD record should remain: William Mwanake."""
    users = _load("users.json")
    synthetic = [un for un, u in users.items()
                if isinstance(u, dict) and u.get("role") == "Managing Director"]
    assert not synthetic, f"Synthetic Managing Director records remain: {synthetic}"


def test_v10399_william_mwanake_is_canonical_md():
    """Chief Executive & Managing Director remains as William Mwanake."""
    users = _load("users.json")
    mds = [(un, u) for un, u in users.items()
           if isinstance(u, dict) and u.get("role") == "Chief Executive & Managing Director"]
    assert len(mds) == 1, f"Should have exactly 1 CE&MD; got {len(mds)}"
    un, u = mds[0]
    assert un == "william001"
    assert str(u.get("staff_code")) == "300001"


def test_v10399_managing_director_tier_removed():
    """role_tiers should no longer have 'Managing Director' key."""
    cfg = _load("org_hierarchy_config.json")
    assert "Managing Director" not in cfg.get("role_tiers", {})


# ────────────────────────────────────────────────────────────────────
# Section 2 — Joshua's canonical updates
# ────────────────────────────────────────────────────────────────────

def test_v10399_head_of_dfs_under_cco():
    """Per Joshua: DFS is commercially-led, not technology-led."""
    cfg = _load("org_hierarchy_config.json")
    dfs = cfg["role_manager_whitelist"].get("Head of Digital Financial Services", [])
    assert "Chief Commercial Officer" in dfs, (
        f"Head of DFS should report to CCO per Joshua; got {dfs}"
    )
    assert "Chief Information Officer" not in dfs, (
        f"Head of DFS should NOT still report to CIO; got {dfs}"
    )


def test_v10399_admin_role_under_md():
    """Admin is Joshua's developer/login account, not CHRO."""
    cfg = _load("org_hierarchy_config.json")
    admin = cfg["role_manager_whitelist"].get("Admin", [])
    assert "Chief Executive & Managing Director" in admin
    assert "Chief Human Resource Officer" not in admin


def test_v10399_card_operations_chain_via_cco():
    """Manager Card Operations → Head of DFS → CCO (chain preserved)."""
    cfg = _load("org_hierarchy_config.json")
    rmw = cfg["role_manager_whitelist"]
    assert "Head of Digital Financial Services" in rmw.get("Manager Card Operations", [])
    assert "Chief Commercial Officer" in rmw.get("Head of Digital Financial Services", [])


def test_v10399_corporate_sales_dealer_under_treasury():
    cfg = _load("org_hierarchy_config.json")
    csd = cfg["role_manager_whitelist"].get("Corporate Sales Dealer", [])
    assert "Head of Treasury" in csd or "Senior Manager Treasury" in csd


def test_v10399_trade_finance_back_office_under_operations():
    cfg = _load("org_hierarchy_config.json")
    tfbo = cfg["role_manager_whitelist"].get("Trade Finance Back Office Manager", [])
    assert "Head of Operations" in tfbo, (
        f"Trade Finance Back Office Manager should report to Head of Operations; got {tfbo}"
    )


def test_v10399_trade_finance_split_correct():
    """Relationships → CCO via Head Of Corporates & TF; ops → COO via Head of Ops."""
    cfg = _load("org_hierarchy_config.json")
    rmw = cfg["role_manager_whitelist"]
    # Relationship side
    rm_tf = rmw.get("Relationship Manager- Trade Finance", [])
    assert "Head Of Corporates & Trade Finance" in rm_tf or \
           "Senior Relationship Manager-Trade Finance Specialist" in rm_tf
    # Operations side
    tf_officer = rmw.get("Trade Finance Officer", [])
    assert "Head of Operations" in tf_officer or "Senior Trade Finance Officer" in tf_officer


# ────────────────────────────────────────────────────────────────────
# Section 3 — Engine + bookkeeping
# ────────────────────────────────────────────────────────────────────

def test_v10399_g285_passes():
    sys.path.insert(0, str(REPO / "scripts"))
    for k in list(sys.modules):
        if k.startswith("audit"):
            del sys.modules[k]
    from audit import gate_v10399_joshua_corrections
    r = gate_v10399_joshua_corrections()
    assert r["passed"], r.get("violations")


def test_v10399_engine_metrics_still_zero():
    """v10.399 corrections preserve the zero-state from v10.398."""
    for k in list(sys.modules):
        if "cascade" in k:
            del sys.modules[k]
    from utils.cascade_structure_engine import full_audit
    s = full_audit().summary
    assert s["cycles_count"] == 0
    assert s["cross_branch_count"] == 0
    assert s["multi_sender_count"] == 0
    assert s["rep_critical_count"] == 0
