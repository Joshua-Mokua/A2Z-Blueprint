"""Integration tests for v10.378 — Customer Master Merge (Phase B continues).

Per Joshua's "merge into 1" approval at v10.374 wrap-up. Establishes the
recognition/sensory layer of the body-system framing.

Three deliverables:
  1. docs/CUSTOMER_MASTER_MERGE_v10.378.md (7 Parts)
  2. utils/customer_master_canonical.py (canonical merge engine, leaf module)
  3. G264 audit gate

12 tests across 4 sections.
"""

import sys
import tempfile
from pathlib import Path

REPO = Path("/tmp/a2z_fix")
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


def _reimport(prefix):
    for k in list(sys.modules):
        if k.startswith(prefix):
            del sys.modules[k]


# ────────────────────────────────────────────────────────────────────
# Section 1 — Design doc + module presence + purity
# ────────────────────────────────────────────────────────────────────

def test_v10378_design_doc_present_with_all_7_parts():
    p = REPO / "docs" / "CUSTOMER_MASTER_MERGE_v10.378.md"
    assert p.exists()
    assert p.stat().st_size > 4000, "design doc seems too small"
    text = p.read_text()
    for part in (
        "## Part 1 — The two customer universes",
        "## Part 2 — The merge strategy",
        "## Part 3 — Module API",
        "## Part 4 — Reconciliation identity",
        "## Part 5 — What v10.378 deliberately does NOT do",
        "## Part 6 — Where customer master fits",
        "## Part 7 — Honest acknowledgement",
    ):
        assert part in text, f"missing section: {part}"


def test_v10378_canonical_module_present_with_required_exports():
    p = REPO / "utils" / "customer_master_canonical.py"
    assert p.exists()
    text = p.read_text()
    for sym in ("class UnifiedCustomerRecord",
                "def compute_unified_customer_master",
                "def reconciliation_summary",
                "def get_customer",
                "STATUS_CBS_ONLY", "STATUS_MARKETING_ONLY", "STATUS_BOTH",
                "SRC_CBS", "SRC_MARKETING", "SRC_DERIVED"):
        assert sym in text, f"missing {sym}"


def test_v10378_canonical_module_is_leaf():
    """v10.364 lesson: leaf module — no top-level upward utils imports."""
    p = REPO / "utils" / "customer_master_canonical.py"
    import ast
    tree = ast.parse(p.read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            # Only check top-level imports (col_offset == 0)
            if (node.module and node.module.startswith("utils") and
                    node.col_offset == 0):
                raise AssertionError(
                    f"top-level upward utils.* import: {node.module}"
                )


# ────────────────────────────────────────────────────────────────────
# Section 2 — Merge mechanics
# ────────────────────────────────────────────────────────────────────

def test_v10378_marketing_only_universe_loads():
    """Without CBS, all customers come from marketing — status='marketing_only'."""
    _reimport("utils.customer_master_canonical")
    from utils.customer_master_canonical import (
        compute_unified_customer_master, STATUS_MARKETING_ONLY,
    )
    unified = compute_unified_customer_master(cbs_dir=None)
    assert len(unified) >= 3000, f"only {len(unified)} marketing customers"
    # All marketing-only
    for r in unified.values():
        assert r.enrichment_status == STATUS_MARKETING_ONLY


def test_v10378_business_customers_classified_correctly():
    """Business CIFs (CIFNNNNNN format) → customer_type='business'."""
    _reimport("utils.customer_master_canonical")
    from utils.customer_master_canonical import (
        compute_unified_customer_master, _load_marketing_businesses,
    )
    unified = compute_unified_customer_master(cbs_dir=None)
    businesses = _load_marketing_businesses()
    for biz_cif in list(businesses.keys())[:5]:
        r = unified.get(biz_cif)
        assert r is not None, f"business CIF {biz_cif} not in unified"
        assert r.customer_type == "business"
        assert biz_cif.startswith("CIF")


def test_v10378_cbs_lineage_tagged_for_transactional_fields():
    """When CBS provides branch_code/rm_code, _field_lineage marks them 'cbs'."""
    _reimport("utils.customer_master_canonical")
    _reimport("utils.virtual_bank_seed")
    _reimport("utils.virtual_bank_cbs_writer")
    from utils.customer_master_canonical import (
        compute_unified_customer_master, STATUS_CBS_ONLY, SRC_CBS,
    )
    from utils.virtual_bank_seed import seed_virtual_bank, SeedConfig
    from utils.virtual_bank_cbs_writer import persist_bank_to_cbs

    bank, _ = seed_virtual_bank(config=SeedConfig.small())
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        persist_bank_to_cbs(bank, output_dir=td_path)
        unified = compute_unified_customer_master(cbs_dir=td_path)

    cbs_only = [r for r in unified.values() if r.enrichment_status == STATUS_CBS_ONLY]
    assert len(cbs_only) > 0, "expected CBS-only records from seed"
    sample = cbs_only[0]
    assert sample.branch_code is not None
    assert sample._field_lineage.get("branch_code") == SRC_CBS
    assert sample._field_lineage.get("rm_code") == SRC_CBS


def test_v10378_marketing_lineage_tagged_for_intelligence_fields():
    """Marketing fields (clv, churn, nba) have lineage='marketing'."""
    _reimport("utils.customer_master_canonical")
    from utils.customer_master_canonical import (
        compute_unified_customer_master, STATUS_MARKETING_ONLY, SRC_MARKETING,
    )
    unified = compute_unified_customer_master(cbs_dir=None)
    mkt_with_clv = [r for r in unified.values()
                    if r.enrichment_status == STATUS_MARKETING_ONLY
                    and r.clv_estimate is not None]
    assert len(mkt_with_clv) > 0, "expected marketing records with CLV"
    sample = mkt_with_clv[0]
    assert sample._field_lineage.get("clv_estimate") == SRC_MARKETING


# ────────────────────────────────────────────────────────────────────
# Section 3 — Reconciliation identity
# ────────────────────────────────────────────────────────────────────

def test_v10378_identity_equation_holds_end_to_end():
    """|A∪B| == |A| + |B| - |A∩B|."""
    _reimport("utils.customer_master_canonical")
    _reimport("utils.virtual_bank_seed")
    _reimport("utils.virtual_bank_cbs_writer")
    from utils.customer_master_canonical import (
        compute_unified_customer_master, reconciliation_summary,
    )
    from utils.virtual_bank_seed import seed_virtual_bank, SeedConfig
    from utils.virtual_bank_cbs_writer import persist_bank_to_cbs

    bank, _ = seed_virtual_bank(config=SeedConfig.small())
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        persist_bank_to_cbs(bank, output_dir=td_path)
        unified = compute_unified_customer_master(cbs_dir=td_path)
        summary = reconciliation_summary(unified, cbs_dir=td_path)

    assert summary["identity_holds"], (
        f"LHS={summary['identity_lhs']} RHS={summary['identity_rhs']}"
    )
    # Math: 100 CBS + 3,206 marketing, 0 overlap = 3,306 unified
    assert summary["cbs_count"] == 100
    assert summary["marketing_count"] >= 3000
    assert summary["overlap_count"] == 0  # disjoint CIF schemes in seed
    assert summary["unified_count"] == summary["cbs_count"] + summary["marketing_count"]


def test_v10378_status_totals_match():
    """cbs_only + marketing_only + both == unified_count."""
    _reimport("utils.customer_master_canonical")
    _reimport("utils.virtual_bank_seed")
    _reimport("utils.virtual_bank_cbs_writer")
    from utils.customer_master_canonical import (
        compute_unified_customer_master, reconciliation_summary,
    )
    from utils.virtual_bank_seed import seed_virtual_bank, SeedConfig
    from utils.virtual_bank_cbs_writer import persist_bank_to_cbs

    bank, _ = seed_virtual_bank(config=SeedConfig.small())
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        persist_bank_to_cbs(bank, output_dir=td_path)
        unified = compute_unified_customer_master(cbs_dir=td_path)
        summary = reconciliation_summary(unified, cbs_dir=td_path)
    assert summary["status_totals_match"]


def test_v10378_get_customer_single_lookup():
    """get_customer(cif) returns the unified record or None."""
    _reimport("utils.customer_master_canonical")
    from utils.customer_master_canonical import (
        compute_unified_customer_master, get_customer,
    )
    unified = compute_unified_customer_master(cbs_dir=None)
    any_cif = next(iter(unified.keys()))
    single = get_customer(any_cif)
    assert single is not None
    assert single.cif == any_cif


# ────────────────────────────────────────────────────────────────────
# Section 4 — G264 + no-regression to prior unification
# ────────────────────────────────────────────────────────────────────

def test_v10378_g264_passes():
    sys.path.insert(0, str(REPO / "scripts"))
    _reimport("audit")
    from audit import gate_customer_master_merge
    r = gate_customer_master_merge()
    assert r["passed"], r.get("violations")
    assert r["id"] == "G264"


def test_v10378_no_regression_to_prior_unification_identities():
    """All 8 prior canonical identities still hold (G250 + G253 + G254 + G255
    + G256 + G257 + G258 + G263).
    """
    _reimport("utils.virtual_bank_seed")
    _reimport("utils.virtual_bank_cbs_writer")
    _reimport("utils.customer_pbt_allocator")
    _reimport("utils.branch_pbt_allocator")
    _reimport("utils.pbt_computation")
    _reimport("utils.sbu_pnl_rollup")
    _reimport("utils.virtual_bank_kpi_unifier")
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
    from utils.virtual_bank_kpi_unifier import unify_all_kpi_flow

    bank, _ = seed_virtual_bank(config=SeedConfig.small())
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        persist_bank_to_cbs(bank, output_dir=td_path)
        bp = float(compute_pbt_from_cbs(td_path).pbt)
        for rollup in (
            float(sum_sbu_pbts(compute_pbt_by_sbu(td_path)).pbt),
            float(sum_branch_pbts(compute_pbt_by_branch(td_path)).pbt),
            float(sum_customer_pbts(compute_pbt_by_customer(td_path)).pbt),
            float(sum_staff_pbts(compute_pbt_by_staff(td_path)).pbt),
        ):
            assert abs(bp - rollup) <= 100
        # G253 engine convergence
        engine_b = bank_total_pnl(cost_source="canonical", cbs_dir=td_path)["pbt"]
        assert abs(bp - engine_b) / max(abs(bp), 1) * 100 < 1.0
        # G263 universal contract still produces conforming records
        result = unify_all_kpi_flow(cbs_dir=td_path, period="2026")
        assert result["validation"]["violations"] == 0
        assert result["reconciliation"]["all_within_kes_100"]


def test_v10378_role_taxonomy_still_100_pct():
    """v10.374 invariant: 100% role coverage."""
    _reimport("utils.role_taxonomy")
    from utils.role_taxonomy import validate_role_coverage
    cov = validate_role_coverage()
    assert cov["default"] == 0
