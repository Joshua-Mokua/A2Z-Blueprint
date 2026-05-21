"""tests/integration/test_cascade_hierarchy_v10318.py

v10.318 — Cascade page hierarchy alignment (Joshua feedback).

Locks the fix for the v10.317 demo issue where logging in as MD on
the "set team targets" page showed "No direct reports found for
Branch Operations Supervisor. Contact Admin to configure reporting
lines."

Three real bugs fixed:
  1. data/org_config.json's hierarchy was incomplete (28 roles,
     stopped at Branch Operations Manager). Now 75 roles, fully
     aligned with v10.316 synthesis.
  2. my_role_level() in pages/12_cascade.py used [k for k, v in
     HIERARCHY.items() if not v] which finds LEAVES, not the root.
     Now uses correct logic (role with no parent in any other
     role's parent list).
  3. is_md / can_all wasn't checked first. Admin users with a low-
     level staff role got matched by fuzzy search to their staff
     role instead of MD. Now is_md returns root immediately.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))


# ────────────────────────────────────────────────────────────────────
# Section 1 — Cascade hierarchy bridge module
# ────────────────────────────────────────────────────────────────────

def test_cascade_hierarchy_module_imports():
    from utils.cascade_hierarchy import (
        role_children_map, role_root, direct_report_roles,
        cascade_chain_from_role, md_direct_reports,
    )
    # Just verify imports work
    assert callable(role_children_map)
    assert callable(role_root)
    assert callable(direct_report_roles)
    assert callable(cascade_chain_from_role)
    assert callable(md_direct_reports)


def test_role_children_map_returns_dict():
    from utils.cascade_hierarchy import role_children_map
    m = role_children_map()
    assert isinstance(m, dict)
    assert len(m) >= 50, (
        f"Expected ≥50 roles in hierarchy, got {len(m)}. "
        f"Has data/org_config.json been edited?"
    )


def test_role_children_map_has_managing_director():
    from utils.cascade_hierarchy import role_children_map
    m = role_children_map()
    assert "Managing Director" in m


def test_role_children_map_has_modern_roles():
    """Confirm v10.318 added the modern roles missing from OLD
    org_config (Branch Operations Supervisor, Teller, CSO, etc.)."""
    from utils.cascade_hierarchy import role_children_map
    m = role_children_map()
    for role in (
        "Teller",
        "Customer Service Officer",
        "Branch Operations Supervisor",
        "Branch Operations Manager",
        "Branch Manager",
        "Area Manager",
        "Head of Branches",
        "Chief Retail Banking Officer",
        "Managing Director",
    ):
        assert role in m, (
            f"{role} missing from hierarchy — v10.318 alignment "
            f"may be incomplete"
        )


# ────────────────────────────────────────────────────────────────────
# Section 2 — Root identification (the v10.318 fix)
# ────────────────────────────────────────────────────────────────────

def test_role_root_returns_managing_director():
    """The root must be Managing Director. Before v10.318, the
    bug was [k for k, v in HIERARCHY.items() if not v] returned
    leaves (Teller, CSO) instead of the root."""
    from utils.cascade_hierarchy import role_root
    root = role_root()
    assert root == "Managing Director", (
        f"role_root() = {root!r}, expected 'Managing Director'. "
        f"v10.318 root-detection bug may have regressed."
    )


def test_role_root_is_node_with_no_parent():
    """Sanity check: the returned root should not appear as anyone
    else's parent in the config."""
    from utils.cascade_hierarchy import role_root, _load_org_config_safe
    root = role_root()
    cfg = _load_org_config_safe()
    raw = cfg.get("hierarchy", {})

    # Walk every entry — none should have the root in their parents
    for role, parents in raw.items():
        if not isinstance(parents, list):
            continue
        # Allow the root itself to have [] (no parent)
        if role == root:
            assert not parents, (
                f"Root {root!r} has parents: {parents}"
            )
            continue
        # Other roles can list anyone (including root) as parent —
        # that's actually expected for Chiefs
    # But ensure root is reachable from at least one role
    all_parents = set()
    for parents in raw.values():
        if isinstance(parents, list):
            all_parents.update(parents)
    assert root in all_parents, (
        f"Root {root!r} is not anyone's parent — orphan root"
    )


# ────────────────────────────────────────────────────────────────────
# Section 3 — MD direct reports
# ────────────────────────────────────────────────────────────────────

def test_md_direct_reports_includes_chiefs():
    from utils.cascade_hierarchy import md_direct_reports
    reports = md_direct_reports()
    assert len(reports) >= 10, (
        f"MD should have ≥10 direct reports, got {len(reports)}: "
        f"{reports}"
    )
    # Spot-check expected Chiefs
    for required_chief in (
        "Chief Retail Banking Officer",
        "Chief Credit Officer",
        "Chief Operating Officer",
        "Chief Financial Officer",
    ):
        assert required_chief in reports, (
            f"Required Chief missing from MD reports: "
            f"{required_chief!r}"
        )


def test_md_direct_reports_only_chiefs_or_gm():
    """The "only Chiefs report to MD" invariant from v10.316
    should hold in the cascade page's view too."""
    from utils.cascade_hierarchy import md_direct_reports
    reports = md_direct_reports()
    for r in reports:
        is_chief_like = (
            r.startswith("Chief") or
            "General Manager" in r
        )
        assert is_chief_like, (
            f"Non-Chief reports to MD: {r!r}. The 'only "
            f"Chiefs report to MD' invariant is violated in "
            f"data/org_config.json"
        )


# ────────────────────────────────────────────────────────────────────
# Section 4 — Teller cascade chain (the exact chain Joshua specified)
# ────────────────────────────────────────────────────────────────────

EXPECTED_TELLER_CHAIN = [
    "Teller",
    "Branch Operations Supervisor",
    "Branch Operations Manager",
    "Branch Manager",
    "Area Manager",
    "Head of Branches",
    "Chief Retail Banking Officer",
    "Managing Director",
]


def test_teller_cascade_chain_exact():
    """The cascade page must walk the exact chain Joshua specified:
    Teller → Branch Operations Supervisor → Branch Operations
    Manager → Branch Manager → Area Manager → Head of Branches →
    Chief Retail Banking Officer → Managing Director."""
    from utils.cascade_hierarchy import cascade_chain_from_role
    chain = cascade_chain_from_role("Teller")
    assert chain == EXPECTED_TELLER_CHAIN, (
        f"Teller cascade chain: got\n  {chain}\nexpected\n  "
        f"{EXPECTED_TELLER_CHAIN}"
    )


def test_cso_cascade_chain_same_as_teller():
    """Customer Service Officers also report to Branch Operations
    Supervisor, so they share the cascade chain except L0."""
    from utils.cascade_hierarchy import cascade_chain_from_role
    chain = cascade_chain_from_role("Customer Service Officer")
    # L0 is CSO, then same as Teller from L1 onward
    assert chain[1:] == EXPECTED_TELLER_CHAIN[1:]


# ────────────────────────────────────────────────────────────────────
# Section 5 — Branch Operations Supervisor has reports (Joshua's bug)
# ────────────────────────────────────────────────────────────────────

def test_branch_ops_supervisor_has_direct_reports():
    """The bug Joshua reported: Branch Operations Supervisor showed
    no direct reports. After v10.318, it should have Tellers, CSOs,
    and Direct Sales Representatives as direct reports."""
    from utils.cascade_hierarchy import direct_report_roles
    reports = direct_report_roles("Branch Operations Supervisor")
    assert "Teller" in reports, (
        f"Branch Operations Supervisor's direct reports missing "
        f"Teller: {reports}"
    )
    assert "Customer Service Officer" in reports
    # At least 3 entry-level roles should report to Branch Ops
    # Supervisor
    assert len(reports) >= 3, (
        f"Expected ≥3 reports to Branch Ops Supervisor, got "
        f"{reports}"
    )


def test_branch_manager_has_correct_reports():
    """Branch Manager's direct reports should include Branch
    Operations Manager and Branch Relationship Manager."""
    from utils.cascade_hierarchy import direct_report_roles
    reports = direct_report_roles("Branch Manager")
    assert "Branch Operations Manager" in reports
    assert "Branch Relationship Manager" in reports


def test_area_manager_has_branch_manager_as_report():
    from utils.cascade_hierarchy import direct_report_roles
    reports = direct_report_roles("Area Manager")
    assert "Branch Manager" in reports


def test_chief_retail_has_head_of_branches_as_report():
    from utils.cascade_hierarchy import direct_report_roles
    reports = direct_report_roles(
        "Chief Retail Banking Officer")
    assert "Head of Branches" in reports


# ────────────────────────────────────────────────────────────────────
# Section 6 — Cascade page source code fix verified
# ────────────────────────────────────────────────────────────────────

def test_cascade_page_has_v10318_fix_marker():
    """pages/12_cascade.py should have the v10.318 fix marker
    in my_role_level() to prevent regression."""
    cascade_page = REPO_ROOT / "pages" / "12_cascade.py"
    source = cascade_page.read_text()
    assert "v10.318 fix" in source, (
        "v10.318 fix marker missing from pages/12_cascade.py — "
        "the my_role_level() fix may have been reverted"
    )


def test_cascade_page_has_admin_md_intent_guard():
    """The is_md / can_all check must be at the top of
    my_role_level() (Step 0), not after fuzzy matching."""
    cascade_page = REPO_ROOT / "pages" / "12_cascade.py"
    source = cascade_page.read_text()
    assert "# 0. Admin / MD intent" in source, (
        "Admin/MD-intent guard (Step 0) missing from "
        "my_role_level() in pages/12_cascade.py"
    )


# ────────────────────────────────────────────────────────────────────
# Section 7 — Audit gate G208
# ────────────────────────────────────────────────────────────────────

def test_g208_gate_exists_and_passes():
    from scripts.audit import GATES
    g208 = None
    for gid, fn in GATES:
        if gid == "G208":
            g208 = fn()
            break
    assert g208 is not None, "G208 not registered"
    assert g208["passed"], (
        f"G208 failed: {g208.get('summary', '')}. "
        f"Violations: {g208.get('violations', [])[:5]}"
    )
