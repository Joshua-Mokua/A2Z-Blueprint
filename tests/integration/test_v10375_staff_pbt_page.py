"""Integration tests for v10.375 — Role-aware Staff PBT page (Phase A second).

First UI surface of v10.370 atomic per-staff engine + v10.374 profitability
axis. Resolves the teller-vs-RM framing from v10.370 by surfacing role
filtering in UI while keeping the engine role-neutral.

10 tests across 3 sections.
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
# Section 1 — Page file structure
# ────────────────────────────────────────────────────────────────────

def test_v10375_page_present():
    p = REPO / "pages" / "120_staff_pbt.py"
    assert p.exists()
    assert p.stat().st_size > 5000, "page seems too small"


def test_v10375_page_imports_canonical_engines():
    """Page must consume v10.370 atom + v10.374 taxonomy."""
    p = REPO / "pages" / "120_staff_pbt.py"
    text = p.read_text()
    assert "compute_pbt_by_staff" in text, "must use v10.370 canonical"
    assert "classify_role" in text, "must use v10.374 taxonomy"
    assert "compute_pbt_from_cbs" in text or "compute_pbt_by_customer" in text, (
        "must compute bank total for reconciliation strip"
    )


def test_v10375_page_has_three_role_aware_filters():
    """Tier / SBU / Branch scope — the three v10.374 dimensions."""
    p = REPO / "pages" / "120_staff_pbt.py"
    text = p.read_text()
    for filt in ("tier_filter", "sbu_filter", "scope_filter"):
        assert filt in text, f"missing filter: {filt}"
    # Must default to portfolio_owner for the tier filter (the primary tier)
    assert "portfolio_owner" in text


def test_v10375_page_has_reconciliation_strip():
    """Top-of-page strip must make G257 identity visible."""
    p = REPO / "pages" / "120_staff_pbt.py"
    text = p.read_text()
    assert "Bank PBT" in text
    assert "\u03a3 Staff PBT" in text or "Σ Staff PBT" in text
    assert "Reconciliation" in text


def test_v10375_page_documents_data_lineage():
    """Body-system framing: footer must document the engine chain."""
    p = REPO / "pages" / "120_staff_pbt.py"
    text = p.read_text()
    assert "Data lineage" in text or "data lineage" in text
    # The full chain from seed to UI
    for step in ("seeded VirtualBankCore", "persist_bank_to_cbs",
                 "compute_pbt_by_customer", "compute_pbt_by_staff",
                 "classify_role"):
        assert step in text, f"data lineage missing step: {step}"


# ────────────────────────────────────────────────────────────────────
# Section 2 — Manifest + Gate registration
# ────────────────────────────────────────────────────────────────────

def test_v10375_manifest_entry_correct():
    p = REPO / "pages" / "_manifest.json"
    m = json.loads(p.read_text())
    entry = m["pages"].get("120_staff_pbt.py")
    assert entry is not None, "manifest missing 120_staff_pbt.py"
    assert entry["module_path"] == "sales_customer.staff_pbt"
    assert entry["department_primary"] == "sales_customer"
    assert "tier" in entry["description"].lower() or "role" in entry["description"].lower()


def test_v10375_g261_passes():
    sys.path.insert(0, str(REPO / "scripts"))
    _reimport("audit")
    from audit import gate_staff_pbt_page
    r = gate_staff_pbt_page()
    assert r["passed"], r.get("violations")
    assert r["id"] == "G261"


def test_v10375_g261_is_registered_in_gates_list():
    sys.path.insert(0, str(REPO / "scripts"))
    _reimport("audit")
    import audit as A
    gates = dict(A.GATES)
    assert "G261" in gates
    # Order check: G261 comes after G260
    keys = list(gates.keys())
    assert keys.index("G261") == keys.index("G260") + 1


# ────────────────────────────────────────────────────────────────────
# Section 3 — No regression to prior unification + taxonomy
# ────────────────────────────────────────────────────────────────────

def test_v10375_all_prior_unification_identities_still_hold():
    """v10.375 is a UI batch — engines must still reconcile."""
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


def test_v10375_role_taxonomy_still_at_100_pct_coverage():
    _reimport("utils.role_taxonomy")
    from utils.role_taxonomy import validate_role_coverage
    cov = validate_role_coverage()
    assert cov["default"] == 0
    assert cov["explicit"] + cov["keyword"] == cov["total_used"]


def test_v10375_taggability_invariant_still_holds():
    """The v10.374 invariant must remain: only portfolio_owner + service tag."""
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
