"""Integration tests for v10.374 — Role Taxonomy Alignment (Phase A first batch).

Establishes the profitability axis orthogonal to the seniority axis.
Five tiers: portfolio_owner / proposition_owner / structural_owner /
service / support. Two complementary attributes: branch_scope, sbu.

Joshua's framing — body system harmony: the seniority axis (role_tiers)
is the skeleton (who reports to whom); the profitability axis is the
circulatory system (where the PBT blood flows).

14 tests across 5 sections.
"""

import json
import sys
import tempfile
from decimal import Decimal
from pathlib import Path

REPO = Path("/tmp/a2z_fix")
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


def _reimport(prefix):
    for k in list(sys.modules):
        if k.startswith(prefix):
            del sys.modules[k]


# ────────────────────────────────────────────────────────────────────
# Section 1 — Module surface + config
# ────────────────────────────────────────────────────────────────────

def test_v10374_module_present():
    p = REPO / "utils" / "role_taxonomy.py"
    assert p.exists()
    text = p.read_text()
    for sym in ("def classify_role", "def get_profitability_tier",
                "def get_branch_scope", "def get_sbu",
                "def can_be_tagged", "def list_roles_by_tier",
                "def list_roles_by_sbu", "def validate_role_coverage",
                "class RoleClassification"):
        assert sym in text, f"missing {sym}"


def test_v10374_org_hierarchy_has_profitability_axis():
    p = REPO / "data" / "org_hierarchy_config.json"
    d = json.loads(p.read_text())
    axis = d.get("profitability_axis")
    assert axis is not None
    assert "role_classification" in axis
    assert "tier_keyword_fallback" in axis
    assert "_validation_rules" in axis
    assert len(axis["role_classification"]) >= 30


def test_v10374_self_test_passes():
    _reimport("utils.role_taxonomy")
    from utils.role_taxonomy import self_test
    import io
    import contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        self_test()
    assert "self-test passed" in buf.getvalue()


# ────────────────────────────────────────────────────────────────────
# Section 2 — Five tier classifications correct
# ────────────────────────────────────────────────────────────────────

def test_v10374_branch_sales_classify_as_portfolio_owner():
    _reimport("utils.role_taxonomy")
    from utils.role_taxonomy import (
        classify_role, TIER_PORTFOLIO_OWNER, SCOPE_BRANCH_BOUND, SBU_RETAIL,
    )
    for role in ("Relationship Officer-Personal Banker",
                 "Relationship Officer-Business Banker",
                 "Branch Relationship Manager"):
        c = classify_role(role)
        assert c.tier == TIER_PORTFOLIO_OWNER, f"{role}: {c.tier}"
        assert c.branch_scope == SCOPE_BRANCH_BOUND
        assert c.sbu == SBU_RETAIL


def test_v10374_ho_rms_classify_as_head_office_portfolio_owners():
    """Joshua: HO RMs span multiple branches but fit one SBU."""
    _reimport("utils.role_taxonomy")
    from utils.role_taxonomy import (
        classify_role, TIER_PORTFOLIO_OWNER, SCOPE_HEAD_OFFICE,
        SBU_COMMERCIAL, SBU_CORPORATE,
    )
    # SME RM → Commercial SBU
    c = classify_role("Relationship Manager - SME")
    assert c.tier == TIER_PORTFOLIO_OWNER
    assert c.branch_scope == SCOPE_HEAD_OFFICE
    assert c.sbu == SBU_COMMERCIAL
    # Corporate RM → Corporate SBU
    c = classify_role("Relationship Manager - Corporate Banking")
    assert c.sbu == SBU_CORPORATE


def test_v10374_proposition_owners_classified_and_not_taggable():
    """Joshua: proposition owners (Women Banking, Diaspora) overlap; NOT tagged."""
    _reimport("utils.role_taxonomy")
    from utils.role_taxonomy import (
        classify_role, can_be_tagged, TIER_PROPOSITION_OWNER,
    )
    c = classify_role("Head Of Women Banking")
    assert c.tier == TIER_PROPOSITION_OWNER
    assert not can_be_tagged("Head Of Women Banking")
    c = classify_role("Senior Manager Diaspora Banking")
    assert c.tier == TIER_PROPOSITION_OWNER
    assert not can_be_tagged("Senior Manager Diaspora Banking")


def test_v10374_branch_mgr_and_above_are_structural_not_tagged():
    """Joshua: Branch managers and upwards are NOT tagged."""
    _reimport("utils.role_taxonomy")
    from utils.role_taxonomy import (
        classify_role, can_be_tagged, TIER_STRUCTURAL_OWNER,
    )
    for role in ("Branch Manager", "Area Manager",
                 "Head of Branches", "Managing Director",
                 "Chief Retail Banking Officer"):
        c = classify_role(role)
        assert c.tier == TIER_STRUCTURAL_OWNER, f"{role} not structural: {c.tier}"
        assert not can_be_tagged(role), f"{role} should NOT be taggable"


def test_v10374_service_can_be_tagged_but_not_primary():
    """Tellers / CSOs occasionally introduce accounts (taggable) but not primary sales."""
    _reimport("utils.role_taxonomy")
    from utils.role_taxonomy import (
        classify_role, can_be_tagged, TIER_SERVICE,
    )
    for role in ("Teller", "Customer Service Officer",
                 "Branch Operations Supervisor"):
        c = classify_role(role)
        assert c.tier == TIER_SERVICE
        assert can_be_tagged(role)  # CAN tag, occasionally


def test_v10374_support_roles_not_taggable():
    _reimport("utils.role_taxonomy")
    from utils.role_taxonomy import can_be_tagged
    for role in ("Compliance Officer", "Internal Auditor",
                 "Finance Officer", "Credit Admin Officer"):
        assert not can_be_tagged(role), f"{role} should NOT be taggable"


# ────────────────────────────────────────────────────────────────────
# Section 3 — 100% coverage on production data
# ────────────────────────────────────────────────────────────────────

def test_v10374_full_coverage_users_and_hr():
    _reimport("utils.role_taxonomy")
    from utils.role_taxonomy import validate_role_coverage
    cov = validate_role_coverage()
    assert cov["default"] == 0, (
        f"{cov['default']} roles fall to no_match_default: "
        f"{cov['unclassified'][:5]}"
    )
    assert cov["total_used"] == cov["explicit"] + cov["keyword"] + cov["default"]
    assert cov["total_used"] >= 100, f"expected ≥100 used roles, got {cov['total_used']}"


def test_v10374_distribution_makes_sense():
    """Sanity: distribution across tiers must reflect a real bank shape."""
    _reimport("utils.role_taxonomy")
    from utils.role_taxonomy import validate_role_coverage
    cov = validate_role_coverage()
    bt = cov["by_tier"]
    # Must have meaningful counts in all five tiers
    assert bt["portfolio_owner"] >= 10
    assert bt["proposition_owner"] >= 1
    assert bt["structural_owner"] >= 10
    assert bt["service"] >= 3
    assert bt["support"] >= 10


# ────────────────────────────────────────────────────────────────────
# Section 4 — G260 + alignment with prior work
# ────────────────────────────────────────────────────────────────────

def test_v10374_g260_passes():
    sys.path.insert(0, str(REPO / "scripts"))
    _reimport("audit")
    from audit import gate_role_taxonomy_alignment
    r = gate_role_taxonomy_alignment()
    assert r["passed"], r.get("violations")
    assert r["id"] == "G260"


def test_v10374_sbu_values_align_with_segment_mapping():
    """SBUs in role_taxonomy must match canonical SBUs from v10.368."""
    _reimport("utils.role_taxonomy")
    from utils.role_taxonomy import (
        SBU_RETAIL, SBU_COMMERCIAL, SBU_CORPORATE,
    )
    p = REPO / "data" / "segment_sbu_mapping.json"
    seg = json.loads(p.read_text())
    known = set(seg.get("segment_to_sbu", {}).values())
    # The customer-facing SBUs used by role_taxonomy must be a subset
    for sbu in (SBU_RETAIL, SBU_COMMERCIAL, SBU_CORPORATE):
        assert sbu in known, f"{sbu} not in segment_sbu_mapping"


def test_v10374_taggability_invariant():
    """Only portfolio_owner + service tiers can be tagged. Others must not."""
    _reimport("utils.role_taxonomy")
    from utils.role_taxonomy import (
        list_all_classified_roles, classify_role, can_be_tagged,
        TIER_PORTFOLIO_OWNER, TIER_SERVICE,
    )
    for role in list_all_classified_roles():
        c = classify_role(role)
        if c.tier in (TIER_PORTFOLIO_OWNER, TIER_SERVICE):
            assert can_be_tagged(role), f"{role} ({c.tier}) should be taggable"
        else:
            assert not can_be_tagged(role), f"{role} ({c.tier}) should NOT be taggable"


# ────────────────────────────────────────────────────────────────────
# Section 5 — Body-system harmony: no regression to prior unification
# ────────────────────────────────────────────────────────────────────

def test_v10374_all_prior_identities_still_hold():
    _reimport("utils.virtual_bank_seed")
    _reimport("utils.virtual_bank_cbs_writer")
    _reimport("utils.customer_pbt_allocator")
    _reimport("utils.branch_pbt_allocator")
    _reimport("utils.pbt_computation")
    _reimport("utils.sbu_pnl_rollup")
    from utils.virtual_bank_seed import seed_virtual_bank, SeedConfig
    from utils.virtual_bank_cbs_writer import persist_bank_to_cbs
    from utils.pbt_computation import (
        compute_pbt_from_cbs, compute_pbt_by_sbu, sum_sbu_pbts,
    )
    from utils.branch_pbt_allocator import (
        compute_pbt_by_branch, sum_branch_pbts,
    )
    from utils.customer_pbt_allocator import (
        compute_pbt_by_customer, sum_customer_pbts,
        compute_pbt_by_staff, sum_staff_pbts,
    )
    from utils.sbu_pnl_rollup import bank_total_pnl

    bank, _ = seed_virtual_bank(config=SeedConfig.small())
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        persist_bank_to_cbs(bank, output_dir=td_path)
        bp = float(compute_pbt_from_cbs(td_path).pbt)
        for rollup_pbt in (
            float(sum_sbu_pbts(compute_pbt_by_sbu(td_path)).pbt),
            float(sum_branch_pbts(compute_pbt_by_branch(td_path)).pbt),
            float(sum_customer_pbts(compute_pbt_by_customer(td_path)).pbt),
            float(sum_staff_pbts(compute_pbt_by_staff(td_path)).pbt),
        ):
            assert abs(bp - rollup_pbt) <= 100
        engine_b = bank_total_pnl(cost_source="canonical", cbs_dir=td_path)["pbt"]
        assert abs(bp - engine_b) / max(abs(bp), 1) * 100 < 1.0
