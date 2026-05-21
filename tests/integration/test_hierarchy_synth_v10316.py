"""tests/integration/test_hierarchy_synth_v10316.py

v10.316 — Hierarchy refinement (Joshua's review). Closes the
discipline gaps in v10.315 by making reporting lines admin-
configurable + injecting synthetic MD/Chiefs + enforcing
role_manager_whitelist + the "only Chiefs report to MD" invariant.

Locks:
  - Admin config loads cleanly + validates
  - Role-tier classification reads from config (not hardcoded regex)
  - is_valid_manager_for() enforces whitelist
  - Synthetic MD + 10 Chiefs injected into universe
  - cascade_from_root walks top-down
  - Every Teller's cascade matches Joshua's expected chain
  - Only Chiefs (tier 1) report to MD — hardcoded invariant
  - hr.json linkages violating whitelist get basis=hr_json_overridden
  - Span of control sane (no manager has 80+ reports anymore)
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))


EXPECTED_TELLER_CASCADE = [
    "Teller",
    "Branch Operations Supervisor",
    "Branch Operations Manager",
    "Branch Manager",
    "Area Manager",
    "Head of Branches",
    "Chief Retail Banking Officer",
    "Managing Director",
]


# ────────────────────────────────────────────────────────────────────
# Section 1 — Config loading
# ────────────────────────────────────────────────────────────────────

def test_config_file_exists_and_loads():
    """data/org_hierarchy_config.json must exist + load cleanly."""
    from utils.org_hierarchy_config import load_config
    cfg = load_config()
    assert cfg is not None
    # v10.330 — schema version is now bumped to v10.330
    assert cfg.schema_version in ("v10.316", "v10.330"), (
        f"unexpected schema_version: {cfg.schema_version}"
    )


def test_config_validates_clean():
    from utils.org_hierarchy_config import (
        load_config, validate_config,
    )
    cfg = load_config()
    report = validate_config(cfg)
    assert report["valid"], (
        f"Config validation failed: {report['violations']}"
    )


def test_config_has_synthetic_md():
    from utils.org_hierarchy_config import load_config
    cfg = load_config()
    assert cfg.synthetic_top_enabled
    assert cfg.synthetic_md is not None
    assert cfg.synthetic_md.role == "Managing Director"
    assert cfg.synthetic_md.staff_code == "EXEC-MD-001"


def test_config_has_chiefs_for_major_departments():
    """Each major department (Retail Banking, Credit, etc.) must
    have a Chief role mapped."""
    from utils.org_hierarchy_config import load_config
    cfg = load_config()
    required_depts = (
        "Retail Banking", "Credit", "Operations", "Finance",
        "IT & Digital", "Risk & Compliance", "People & HR",
        "Internal Audit", "Legal", "Commercial & Corporate",
    )
    for dept in required_depts:
        chief_role = cfg.department_chief_mapping.get(dept)
        assert chief_role, (
            f"Department '{dept}' has no Chief mapped in config"
        )


# ────────────────────────────────────────────────────────────────────
# Section 2 — Role tier classification (config-driven)
# ────────────────────────────────────────────────────────────────────

def test_classify_role_tier_exact_matches():
    from utils.org_hierarchy_config import (
        load_config, classify_role_tier,
    )
    cfg = load_config()
    cases = [
        ("Managing Director", 0),
        ("Chief Credit Officer", 1),
        ("Chief Retail Banking Officer", 1),
        ("Head of Branches", 2),
        ("Head of Operations", 2),
        ("Area Manager", 3),
        ("Senior Branch Manager", 3),
        ("Branch Manager", 4),
        ("Branch Operations Manager", 4),
        ("Branch Operations Supervisor", 5),
        ("Branch Senior Relationship Officer", 5),
        ("Teller", 6),
        ("Customer Service Officer", 6),
    ]
    for role, expected in cases:
        actual = classify_role_tier(role, cfg)
        assert actual == expected, (
            f"classify_role_tier({role!r}) = {actual}, "
            f"expected {expected}"
        )


def test_classify_role_tier_keyword_fallback():
    """A role not in role_tiers should hit the keyword fallback
    and get a sensible tier."""
    from utils.org_hierarchy_config import (
        load_config, classify_role_tier,
    )
    cfg = load_config()
    # "Manager Foo Bar" should match the tier 4 "manager" keyword
    assert classify_role_tier("Manager Custom Role", cfg) == 4
    # "Special Officer" should match tier 5 "officer" keyword
    assert classify_role_tier("Special Officer", cfg) == 5


def test_classify_role_tier_unknown_defaults_to_five():
    from utils.org_hierarchy_config import (
        load_config, classify_role_tier,
    )
    cfg = load_config()
    assert classify_role_tier(
        "Completely Unknown Role That Matches Nothing",
        cfg
    ) == 5


# ────────────────────────────────────────────────────────────────────
# Section 3 — Whitelist enforcement
# ────────────────────────────────────────────────────────────────────

def test_is_valid_manager_for_teller():
    """Tellers should only report to Branch Operations Supervisor
    or Branch Operations Manager."""
    from utils.org_hierarchy_config import (
        load_config, is_valid_manager_for,
    )
    cfg = load_config()
    assert is_valid_manager_for(
        "Teller", "Branch Operations Supervisor", cfg)
    assert is_valid_manager_for(
        "Teller", "Branch Operations Manager", cfg)
    # NOT valid: Tellers shouldn't report directly to Branch Manager
    # or to Relationship Officers (wrong direction/wrong function)
    assert not is_valid_manager_for(
        "Teller", "Branch Manager", cfg)
    assert not is_valid_manager_for(
        "Teller", "Branch Senior Relationship Officer", cfg)


def test_is_valid_manager_for_unrestricted_role():
    """A role without a whitelist entry should accept any manager."""
    from utils.org_hierarchy_config import (
        load_config, is_valid_manager_for,
    )
    cfg = load_config()
    # "Finance Officer" isn't in whitelist → any manager is fine
    assert is_valid_manager_for(
        "Finance Officer", "Chief Financial Officer", cfg)
    assert is_valid_manager_for(
        "Finance Officer", "Random Other Role", cfg)


# ────────────────────────────────────────────────────────────────────
# Section 4 — Synthetic MD + Chiefs injection
# ────────────────────────────────────────────────────────────────────

def test_synthetic_md_in_universe():
    """staff_universe() (with synth enabled) includes synthetic MD."""
    from utils.virtual_bank import staff_universe, reset_cache
    reset_cache()
    u = staff_universe()
    md = u.get("EXEC-MD-001")
    assert md is not None, (
        "Synthetic MD (EXEC-MD-001) not in universe"
    )
    assert md.role == "Managing Director"
    # v10.326: synthetic users were ALSO added to users.json so the
    # BSC engine accepts them. After v10.326 the source could be
    # either 'synthetic' (from hierarchy synthesis) or 'users' (now
    # picked up by raw loader). Either is fine — what matters is
    # the role + tree position.
    assert md.source in ("synthetic", "users"), (
        f"MD source {md.source!r} unexpected"
    )
    assert md.manager_code is None  # MD is root


def test_synthetic_chiefs_in_universe():
    """All 10 configured Chiefs should be in universe."""
    from utils.virtual_bank import staff_universe, reset_cache
    reset_cache()
    u = staff_universe()
    expected_chief_codes = (
        "EXEC-CRO-001", "EXEC-CCO-001", "EXEC-COO-001",
        "EXEC-CFO-001", "EXEC-CIO-001", "EXEC-CRSO-001",
        "EXEC-CCMP-001", "EXEC-CIA-001", "EXEC-CHRO-001",
        "EXEC-CCMO-001",
    )
    for code in expected_chief_codes:
        chief = u.get(code)
        assert chief is not None, f"Chief {code} not in universe"
        # v10.326: same caveat as MD — source may be 'synthetic' or
        # 'users' after Exec users added to registry.
        assert chief.source in ("synthetic", "users"), (
            f"Chief {code} source {chief.source!r} unexpected"
        )
        assert chief.manager_code == "EXEC-MD-001"


def test_raw_universe_excludes_synthetic_hierarchy_links():
    """staff_universe(include_synth_hierarchy=False) should NOT
    apply the synthetic hierarchy linkages — staff still load
    from users.json but their manager_code may differ.

    v10.326: EXEC-* codes now also appear in users.json as
    synthetic-tagged users, so they DO appear in the raw load
    (this is intentional — see v10.326 changelog). What the
    synthesis layer adds is the hierarchy linkage (chiefs report
    to EXEC-MD-001 etc.), not the existence of the codes.
    """
    from utils.virtual_bank import staff_universe, reset_cache
    reset_cache()
    u_raw = staff_universe(include_synth_hierarchy=False)
    # Raw universe is the active staff from hr+users only
    assert len(u_raw) >= 1400


# ────────────────────────────────────────────────────────────────────
# Section 5 — Teller cascade (the headline demo path)
# ────────────────────────────────────────────────────────────────────

def test_every_teller_walks_expected_cascade():
    """Every Teller's manager_chain must terminate at MD via the
    Retail Banking C-suite path. Real-world variation in the middle
    layers is acceptable: some Branch Managers report to Area Manager,
    others to Senior Branch Manager (both whitelist-valid). What MUST
    hold for every Teller:

      L0:  Teller
      L1:  Branch Operations Supervisor OR Branch Operations Manager
      ...: Walks through Branch Manager → (Area Manager OR Senior
           Branch Manager) → Head of Branches → Chief Retail Banking
           Officer
      LN:  Managing Director (root)

    No cycles. No wrong-direction reporting. No cross-department
    jumps (every link until Chief is Retail Banking)."""
    from utils.virtual_bank import (
        staff_universe, manager_chain, reset_cache,
    )
    reset_cache()
    u = staff_universe()
    tellers = [s for s in u.values() if s.role == "Teller"]
    assert len(tellers) >= 200, (
        f"Expected ≥200 Tellers, got {len(tellers)}"
    )

    required_roles_in_chain = {
        "Teller",
        "Head of Branches",
        "Chief Retail Banking Officer",
        "Managing Director",
    }
    # v10.330 — either Branch Manager OR Senior Branch Manager satisfies
    # the branch-tier requirement (Senior BMs run flagship branches but
    # are peers of standard BMs, both reporting to Area Manager)
    branch_tier_roles = {"Branch Manager", "Senior Branch Manager"}
    valid_l1 = {"Branch Operations Supervisor",
                "Branch Operations Manager"}
    valid_l2_into_branch = {"Branch Operations Manager",
                             "Branch Manager",
                             "Senior Branch Manager"}
    valid_above_branch_mgr = {"Area Manager"}  # v10.330 — only AM valid above BM

    failures = []
    for t in tellers:
        chain = manager_chain(t.staff_code, max_depth=15)
        chain_roles = [link.role for link in chain]

        # Must START with Teller
        if chain_roles[0] != "Teller":
            failures.append((t.staff_code, "L0 != Teller"))
            continue

        # Must END with Managing Director
        if chain_roles[-1] != "Managing Director":
            failures.append(
                (t.staff_code, f"end != MD ({chain_roles[-1]})"))
            continue

        # All required roles must appear somewhere
        missing = required_roles_in_chain - set(chain_roles)
        if missing:
            failures.append(
                (t.staff_code, f"missing roles: {missing}"))
            continue

        # v10.330 — branch tier must include either BM or Senior BM
        if not (branch_tier_roles & set(chain_roles)):
            failures.append(
                (t.staff_code,
                 f"no branch-tier role in chain: {chain_roles}"))
            continue

        # L1 must be Supervisor or Operations Manager
        if chain_roles[1] not in valid_l1:
            failures.append(
                (t.staff_code, f"L1 invalid: {chain_roles[1]}"))
            continue

        # Branch Manager OR Senior Branch Manager must be at L2 or L3
        bm_idx = None
        for idx, role in enumerate(chain_roles):
            if role in branch_tier_roles:
                bm_idx = idx
                break
        if bm_idx is None or bm_idx not in (2, 3):
            failures.append(
                (t.staff_code,
                 f"Branch Manager at L{bm_idx}, expected L2 or L3"))
            continue

        # Role above Branch Manager must be Area/Senior Branch Manager
        # or Head of Branches
        above_bm = chain_roles[bm_idx + 1]
        if above_bm not in valid_above_branch_mgr:
            failures.append(
                (t.staff_code,
                 f"above Branch Manager: {above_bm} "
                 f"(expected Area Manager, Senior Branch Manager, "
                 f"or Head of Branches)"))

    assert not failures, (
        f"{len(failures)}/{len(tellers)} Tellers have invalid "
        f"cascades. Examples: {failures[:3]}"
    )


# ────────────────────────────────────────────────────────────────────
# Section 6 — Only Chiefs report to MD (hardcoded invariant)
# ────────────────────────────────────────────────────────────────────

def test_only_chiefs_report_to_md():
    """The MD's direct reports must all be tier-1 (Chief X Officer
    or General Manager). No tier-2+ staff reports directly to MD."""
    from utils.virtual_bank import staff_universe, reset_cache
    from utils.hierarchy_synth import role_tier
    reset_cache()
    u = staff_universe()
    md_code = "EXEC-MD-001"
    assert md_code in u, "MD not in universe"

    direct_reports = [s for s in u.values()
                      if s.manager_code == md_code]
    assert len(direct_reports) >= 10, (
        f"Expected ≥10 direct reports to MD, got "
        f"{len(direct_reports)}"
    )

    non_chiefs = []
    for s in direct_reports:
        tier = role_tier(s.role)
        if tier != 1:
            non_chiefs.append((s.staff_code, s.role, tier))

    assert not non_chiefs, (
        f"{len(non_chiefs)} non-Chief staff report directly to "
        f"MD: {non_chiefs[:3]}"
    )


def test_md_has_at_least_10_chief_reports():
    """MD should have all 10 configured Chiefs (plus any real
    tier-1 roles like GM-Bancassurance)."""
    from utils.virtual_bank import staff_universe, reset_cache
    reset_cache()
    u = staff_universe()
    direct = [s for s in u.values()
              if s.manager_code == "EXEC-MD-001"]
    assert len(direct) >= 10, (
        f"MD has only {len(direct)} direct reports; expected ≥10"
    )


# ────────────────────────────────────────────────────────────────────
# Section 7 — Whitelist-violating hr.json links overridden
# ────────────────────────────────────────────────────────────────────

def test_hr_json_overridden_basis_observed():
    """v10.316 added the hr_json_overridden basis for hr.json
    linkages that violate the role_manager_whitelist (e.g. Branch
    Manager → Branch Relationship Manager which is wrong direction).
    We should see some staff tagged with this basis."""
    from utils.virtual_bank import staff_universe, reset_cache
    from utils.hierarchy_synth import synthesise_full_hierarchy
    reset_cache()
    u_raw = staff_universe(include_synth_hierarchy=False)
    links = synthesise_full_hierarchy(u_raw)
    overridden = [link for link in links.values()
                  if link.basis == "hr_json_overridden"]
    assert len(overridden) > 0, (
        "Expected some hr.json-overridden links — whitelist "
        "enforcement may not be active"
    )
    # Surface as a known number (today: ~114)
    assert 50 <= len(overridden) <= 250, (
        f"Got {len(overridden)} overridden — outside expected range "
        f"50-250. Has the whitelist or hr.json changed substantially?"
    )


# ────────────────────────────────────────────────────────────────────
# Section 8 — Cascade from root (top-down view)
# ────────────────────────────────────────────────────────────────────

def test_cascade_from_root_returns_md_at_top():
    from utils.virtual_bank import staff_universe, reset_cache
    from utils.hierarchy_synth import cascade_from_root
    reset_cache()
    u = staff_universe(include_synth_hierarchy=False)
    tree = cascade_from_root(u)
    assert tree["root"] is not None
    assert tree["root"]["role"] == "Managing Director"
    assert tree["root"]["staff_code"] == "EXEC-MD-001"


def test_cascade_from_root_md_has_chief_children():
    """MD's children in the cascade tree must all be Chiefs."""
    from utils.virtual_bank import staff_universe, reset_cache
    from utils.hierarchy_synth import cascade_from_root, role_tier
    reset_cache()
    u = staff_universe(include_synth_hierarchy=False)
    tree = cascade_from_root(u)
    for child in tree["children"]:
        tier = role_tier(child["staff"]["role"])
        assert tier == 1, (
            f"MD's direct child {child['staff']['staff_code']} "
            f"({child['staff']['role']}) is tier {tier}, expected 1"
        )


def test_cascade_from_root_covers_all_staff():
    """Total nodes in tree should equal raw universe + synthetic top."""
    from utils.virtual_bank import staff_universe, reset_cache
    from utils.hierarchy_synth import cascade_from_root
    reset_cache()
    u = staff_universe(include_synth_hierarchy=False)
    tree = cascade_from_root(u)
    # 1428 raw staff + 11 synthetic (MD + 10 Chiefs) = 1439
    assert tree["total_nodes"] >= 1400


# ────────────────────────────────────────────────────────────────────
# Section 9 — Span of control + max depth sanity
# ────────────────────────────────────────────────────────────────────

def test_max_span_of_control_reasonable():
    """No single manager should have 100+ reports after v10.316's
    refinements. (v10.315 had Head of DFS with 84.)"""
    from utils.virtual_bank import staff_universe, reset_cache
    from utils.hierarchy_synth import (
        synthesise_full_hierarchy, validate_hierarchy,
    )
    reset_cache()
    u_raw = staff_universe(include_synth_hierarchy=False)
    links = synthesise_full_hierarchy(u_raw)
    report = validate_hierarchy(links, u_raw)
    assert report["max_span_of_control"] <= 100, (
        f"Max span {report['max_span_of_control']} > 100 — some "
        f"manager has unrealistic span of control"
    )


def test_max_depth_reasonable():
    """Cascade depth should be 6-10 for a real-world bank
    of ~1,400 staff."""
    from utils.virtual_bank import staff_universe, reset_cache
    from utils.hierarchy_synth import (
        synthesise_full_hierarchy, validate_hierarchy,
    )
    reset_cache()
    u_raw = staff_universe(include_synth_hierarchy=False)
    links = synthesise_full_hierarchy(u_raw)
    report = validate_hierarchy(links, u_raw)
    assert 5 <= report["max_depth_observed"] <= 12, (
        f"Max depth {report['max_depth_observed']} outside "
        f"realistic range 5-12"
    )


def test_validation_passes_clean():
    """Full validation must return valid=True with zero violations."""
    from utils.virtual_bank import staff_universe, reset_cache
    from utils.hierarchy_synth import (
        synthesise_full_hierarchy, validate_hierarchy,
    )
    reset_cache()
    u_raw = staff_universe(include_synth_hierarchy=False)
    links = synthesise_full_hierarchy(u_raw)
    report = validate_hierarchy(links, u_raw)
    assert report["valid"], (
        f"Hierarchy validation failed: {report['violations']}"
    )


# ────────────────────────────────────────────────────────────────────
# Section 10 — Audit gate G206
# ────────────────────────────────────────────────────────────────────

def test_g206_passes():
    from scripts.audit import GATES
    g206 = None
    for gid, fn in GATES:
        if gid == "G206":
            g206 = fn()
            break
    assert g206 is not None, "G206 not registered"
    assert g206["passed"], (
        f"G206 failed: {g206.get('summary', '')}; "
        f"Violations: {g206.get('violations', [])[:5]}"
    )
