"""tests/integration/test_hierarchy_synth_v10315.py

v10.315 — Hierarchy synthesis (B-012 close).

Locks the verified state of the synthesised manager linkages:
  - Root identification (handles no-MD case)
  - Coverage from 13.45% (v10.314) to ≥99% (v10.315)
  - Validation: 1 root, no cycles, max depth ≤15, span ≤200
  - Retail Banking branch sub-hierarchy works
  - hr.json linkages still take precedence over synthesis
  - manager_chain() walks for the full 1,428 staff
  - virtual_bank.staff_universe(include_synth_hierarchy=False)
    still shows the raw state for B-012 audits
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))


# ────────────────────────────────────────────────────────────────────
# Section 1 — role_tier function
# ────────────────────────────────────────────────────────────────────

def test_role_tier_managing_director_is_zero():
    from utils.hierarchy_synth import role_tier
    assert role_tier("Managing Director") == 0


def test_role_tier_chief_x_is_one():
    from utils.hierarchy_synth import role_tier
    assert role_tier("Chief Credit Officer") == 1
    assert role_tier("Chief Financial Officer") == 1


def test_role_tier_head_of_x_is_two():
    from utils.hierarchy_synth import role_tier
    assert role_tier("Head of Branches") == 2
    assert role_tier("Head of Operations") == 2


def test_role_tier_area_manager_is_three():
    from utils.hierarchy_synth import role_tier
    assert role_tier("Area Manager") == 3
    assert role_tier("Senior Branch Manager") == 3


def test_role_tier_branch_manager_is_four():
    from utils.hierarchy_synth import role_tier
    assert role_tier("Branch Manager") == 4


def test_role_tier_teller_is_six():
    """Teller is special-cased to tier 6 (entry-level) even though
    'Teller' doesn't match any officer/supervisor regex."""
    from utils.hierarchy_synth import role_tier
    assert role_tier("Teller") == 6


def test_role_tier_cso_is_six():
    """Customer Service Officer is overridden to tier 6 despite
    matching the \\bofficer\\b regex (entry-level frontline)."""
    from utils.hierarchy_synth import role_tier
    assert role_tier("Customer Service Officer") == 6


def test_role_tier_unknown_defaults_to_five():
    from utils.hierarchy_synth import role_tier
    assert role_tier("Some Random Role That Doesn't Match") == 5


# ────────────────────────────────────────────────────────────────────
# Section 2 — Root finding
# ────────────────────────────────────────────────────────────────────

def test_find_root_md_returns_a_code():
    """Even with no Managing Director in data, find_root_md should
    return the most-senior available staff (not None)."""
    from utils.virtual_bank import staff_universe
    from utils.hierarchy_synth import find_root_md
    u = staff_universe(include_synth_hierarchy=False)
    root = find_root_md(u)
    assert root is not None
    assert root in u


def test_find_root_md_returns_none_for_empty_universe():
    from utils.hierarchy_synth import find_root_md
    assert find_root_md({}) is None


def test_root_is_the_most_senior_staff():
    """The selected root should be the lowest-tier (most senior)
    staff available."""
    from utils.virtual_bank import staff_universe
    from utils.hierarchy_synth import find_root_md, role_tier
    u = staff_universe(include_synth_hierarchy=False)
    root = find_root_md(u)
    root_staff = u[root]
    root_tier = role_tier(root_staff.role)
    # No staff in the universe should be at a lower tier than root
    for s in u.values():
        assert role_tier(s.role) >= root_tier, (
            f"Staff {s.staff_code} ({s.role}) is at tier "
            f"{role_tier(s.role)} but root is at tier {root_tier}"
        )


# ────────────────────────────────────────────────────────────────────
# Section 3 — Full hierarchy synthesis
# ────────────────────────────────────────────────────────────────────

def test_synthesise_covers_all_staff():
    """Every staff in the universe should get a HierarchyLink."""
    from utils.virtual_bank import staff_universe
    from utils.hierarchy_synth import synthesise_full_hierarchy
    u = staff_universe(include_synth_hierarchy=False)
    links = synthesise_full_hierarchy(u)
    assert len(links) == len(u), (
        f"Links produced: {len(links)}, universe: {len(u)}"
    )
    for code in u:
        assert code in links


def test_synthesised_hierarchy_is_valid():
    """The validation function should return valid=True for the
    full org synthesis."""
    from utils.virtual_bank import staff_universe
    from utils.hierarchy_synth import (
        synthesise_full_hierarchy, validate_hierarchy,
    )
    u = staff_universe(include_synth_hierarchy=False)
    links = synthesise_full_hierarchy(u)
    report = validate_hierarchy(links, u)
    assert report["valid"], (
        f"Hierarchy invalid: {report['violations']}"
    )


def test_synthesised_hierarchy_has_exactly_one_root():
    from utils.virtual_bank import staff_universe
    from utils.hierarchy_synth import (
        synthesise_full_hierarchy, validate_hierarchy,
    )
    u = staff_universe(include_synth_hierarchy=False)
    links = synthesise_full_hierarchy(u)
    report = validate_hierarchy(links, u)
    assert len(report["roots"]) == 1, (
        f"Expected 1 root, got {len(report['roots'])}: "
        f"{report['roots'][:5]}"
    )


def test_synthesised_hierarchy_has_no_cycles():
    """Cycles would cause infinite loops in cascade walks."""
    from utils.virtual_bank import staff_universe
    from utils.hierarchy_synth import (
        synthesise_full_hierarchy, validate_hierarchy,
    )
    u = staff_universe(include_synth_hierarchy=False)
    links = synthesise_full_hierarchy(u)
    report = validate_hierarchy(links, u)
    assert report["unreachable"] == 0, (
        f"{report['unreachable']} staff couldn't reach root "
        f"(cycle or chain too deep)"
    )


def test_synthesised_hierarchy_max_depth_is_reasonable():
    """A 1,428-staff org should have depth ≤15 levels."""
    from utils.virtual_bank import staff_universe
    from utils.hierarchy_synth import (
        synthesise_full_hierarchy, validate_hierarchy,
    )
    u = staff_universe(include_synth_hierarchy=False)
    links = synthesise_full_hierarchy(u)
    report = validate_hierarchy(links, u)
    assert report["max_depth_observed"] <= 15, (
        f"Max depth {report['max_depth_observed']} > 15 — "
        f"hierarchy is unrealistically tall"
    )


# ────────────────────────────────────────────────────────────────────
# Section 4 — hr.json linkages take precedence
# ────────────────────────────────────────────────────────────────────

def test_hr_json_linkages_preserved_in_synthesis():
    """If a staff has a manager_code in hr.json, the synthesis must
    keep it (not override with a different manager)."""
    from utils.virtual_bank import staff_universe
    from utils.hierarchy_synth import synthesise_full_hierarchy
    u_raw = staff_universe(include_synth_hierarchy=False)
    links = synthesise_full_hierarchy(u_raw)

    # Find staff with hr.json manager_code
    hr_linked = [s for s in u_raw.values() if s.manager_code]
    assert hr_linked, "Need some hr.json-linked staff for this test"

    for s in hr_linked[:20]:  # check first 20
        link = links[s.staff_code]
        assert link.manager_code == s.manager_code, (
            f"Staff {s.staff_code}: hr.json manager_code is "
            f"{s.manager_code} but synthesis says {link.manager_code}"
        )
        assert link.basis == "hr_json", (
            f"Staff {s.staff_code}: should be marked basis=hr_json"
        )


# ────────────────────────────────────────────────────────────────────
# Section 5 — virtual_bank.staff_universe integration
# ────────────────────────────────────────────────────────────────────

def test_staff_universe_default_includes_synth():
    """Default call to staff_universe() should fill in synth linkages,
    bringing manager-linkage coverage to ≥99%."""
    from utils.virtual_bank import staff_universe
    u = staff_universe()
    with_mgr = sum(1 for s in u.values() if s.manager_code)
    coverage_pct = (with_mgr / len(u) * 100) if u else 0
    assert coverage_pct >= 99.0, (
        f"Default synthesis only gave {coverage_pct:.2f}% coverage"
    )


def test_staff_universe_can_disable_synth():
    """Setting include_synth_hierarchy=False shows the raw state
    (only the ~192 hr.json linkages)."""
    from utils.virtual_bank import staff_universe
    u_raw = staff_universe(include_synth_hierarchy=False)
    u_synth = staff_universe(include_synth_hierarchy=True)

    raw_linkage = sum(1 for s in u_raw.values() if s.manager_code)
    synth_linkage = sum(1 for s in u_synth.values() if s.manager_code)

    assert raw_linkage < synth_linkage, (
        f"Raw linkage ({raw_linkage}) should be < "
        f"synthesised ({synth_linkage})"
    )
    assert raw_linkage <= 250, (
        f"Raw hr.json linkage too high: {raw_linkage} (expected ~192)"
    )


# ────────────────────────────────────────────────────────────────────
# Section 6 — manager_chain works end-to-end
# ────────────────────────────────────────────────────────────────────

def test_manager_chain_works_for_teller():
    """A frontline Teller should now have a walkable cascade chain
    of ≥3 levels to the root."""
    from utils.virtual_bank import staff_universe, manager_chain
    u = staff_universe()
    teller = next(
        (s for s in u.values() if s.role == "Teller"), None)
    assert teller is not None, "No Teller in universe"
    chain = manager_chain(teller.staff_code, max_depth=15)
    assert len(chain) >= 3, (
        f"Teller cascade only {len(chain)} levels deep: "
        f"{[(l.role, l.department) for l in chain]}"
    )


def test_manager_chain_reaches_root_for_random_staff():
    """Pick 5 random staff (deterministic by sorting); each should
    have a chain that terminates at a root (manager_code=None)."""
    from utils.virtual_bank import staff_universe, manager_chain
    u = staff_universe()
    sample_codes = sorted(u.keys())[::300][:5]  # 5 evenly-spaced
    for code in sample_codes:
        chain = manager_chain(code, max_depth=20)
        # Last element should be the root
        last = chain[-1]
        assert last.manager_code is None, (
            f"Staff {code}'s chain doesn't terminate at root "
            f"(last is {last.staff_code} with mgr "
            f"{last.manager_code})"
        )


# ────────────────────────────────────────────────────────────────────
# Section 7 — Retail Banking branch structure
# ────────────────────────────────────────────────────────────────────

def test_retail_branch_managers_route_through_synthesis():
    """Branch Managers without hr.json linkage should be linked
    via the retail_branch basis."""
    from utils.virtual_bank import staff_universe
    from utils.hierarchy_synth import synthesise_full_hierarchy
    u_raw = staff_universe(include_synth_hierarchy=False)
    links = synthesise_full_hierarchy(u_raw)

    branch_mgrs = [
        s for s in u_raw.values()
        if s.role == "Branch Manager" and not s.manager_code
    ]
    assert branch_mgrs, "No Branch Managers without hr.json linkage"
    for bm in branch_mgrs[:10]:
        link = links[bm.staff_code]
        assert link.basis in ("retail_branch", "retail_hq"), (
            f"Branch Manager {bm.staff_code} linked via "
            f"{link.basis}, expected retail_*"
        )


def test_retail_tellers_route_through_synthesis():
    """Tellers should be linked via retail_branch synthesis OR
    hr_json (if they appear in hr.json with manager_code). The
    key invariant: every Teller has a non-None manager."""
    from utils.virtual_bank import staff_universe
    from utils.hierarchy_synth import synthesise_full_hierarchy
    u_raw = staff_universe(include_synth_hierarchy=False)
    links = synthesise_full_hierarchy(u_raw)

    tellers = [s for s in u_raw.values() if s.role == "Teller"]
    for t in tellers[:20]:
        link = links[t.staff_code]
        assert link.manager_code is not None, (
            f"Teller {t.staff_code} has no manager"
        )
        # Acceptable bases: retail_branch (most Tellers) or
        # hr_json (the ~29 Tellers with source-data manager_code)
        assert link.basis in ("retail_branch", "hr_json"), (
            f"Teller {t.staff_code} linked via {link.basis}, "
            f"expected retail_branch or hr_json"
        )


# ────────────────────────────────────────────────────────────────────
# Section 8 — Audit gate G205
# ────────────────────────────────────────────────────────────────────

def test_g205_gate_exists_and_passes():
    from scripts.audit import GATES
    g205 = None
    for gid, fn in GATES:
        if gid == "G205":
            g205 = fn()
            break
    assert g205 is not None, "G205 not registered"
    assert g205["passed"], (
        f"G205 failed: {g205.get('summary', '')}. "
        f"Violations: {g205.get('violations', [])[:5]}"
    )
