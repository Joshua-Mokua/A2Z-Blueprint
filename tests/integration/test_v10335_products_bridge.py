"""Integration tests for v10.335 — Products → BSC bridge.

12 tests across 5 sections:
  Section 1 — Module surface (3 tests)
  Section 2 — Category aggregation correctness (3 tests)
  Section 3 — Owner resolution (2 tests)
  Section 4 — End-to-end cascade (3 tests)
  Section 5 — Audit gate G224 (1 test)
"""

import json
import sys
from pathlib import Path


REPO = Path("/tmp/a2z_fix")
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


# ────────────────────────────────────────────────────────────────────
# Section 1 — Module surface
# ────────────────────────────────────────────────────────────────────

def test_v10335_module_imports_and_surface():
    """Bridge exposes the required public surface."""
    for k in list(sys.modules):
        if k.startswith("utils.products_to_bsc"):
            del sys.modules[k]
    from utils import products_to_bsc as pb
    for sym in (
        "sync_products_to_bsc",
        "find_owner_codes",
        "aggregate_for_owner",
        "aggregate_category",
        "get_product_kpi_summary",
        "get_categories_covered",
        "CATEGORY_OWNER_ROLE",
    ):
        assert hasattr(pb, sym), f"Missing {sym}"


def test_v10335_seven_categories_mapped():
    """All 7 product categories have owner role assignments."""
    for k in list(sys.modules):
        if k.startswith("utils.products_to_bsc"):
            del sys.modules[k]
    from utils.products_to_bsc import CATEGORY_OWNER_ROLE
    expected = {
        "Retail Lending", "Deposits", "Digital", "SME Lending",
        "Corporate", "Trade Finance", "Fee Income",
    }
    assert set(CATEGORY_OWNER_ROLE) == expected


def test_v10335_canonical_product_kpis_in_library():
    """4 PRODUCT_ canonical KPIs registered."""
    lib = json.loads((REPO / "data" / "kpi_library.json").read_text())
    ids = {k.get("id") for k in lib.get("kpis", [])}
    for k in (
        "PRODUCT_BOOK_ACHIEVEMENT",
        "PRODUCT_REVENUE_ACHIEVEMENT",
        "PRODUCT_NPL_RATE",
        "PRODUCT_GROWTH_RATE",
    ):
        assert k in ids, f"Canonical {k} missing"


# ────────────────────────────────────────────────────────────────────
# Section 2 — Category aggregation
# ────────────────────────────────────────────────────────────────────

def test_v10335_book_achievement_correct_formula():
    """PRODUCT_BOOK_ACHIEVEMENT = 100 × Σ actual_book / Σ target_book
    for Q2 baseline (factor=1.0)."""
    for k in list(sys.modules):
        if k.startswith("utils.products_to_bsc"):
            del sys.modules[k]
    from utils.products_to_bsc import load_products, aggregate_for_owner
    prods = load_products()
    retail = [p for p in prods if p.get("category") == "Retail Lending"]
    sum_actual = sum(p.get("actual_book", 0) for p in retail)
    sum_target = sum(p.get("target_book", 0) for p in retail)
    expected = round(100.0 * sum_actual / sum_target, 2)

    agg = aggregate_for_owner(prods, ["Retail Lending"], "2026-Q2")
    assert "PRODUCT_BOOK_ACHIEVEMENT" in agg
    # Allow 0.01 tolerance for Decimal rounding
    actual_v = float(agg["PRODUCT_BOOK_ACHIEVEMENT"])
    assert abs(actual_v - expected) < 0.01, (
        f"Book achievement mismatch: got {actual_v}, expected {expected}"
    )


def test_v10335_fee_only_skips_book_kpis():
    """For Digital category (target_book=0), only PRODUCT_REVENUE_ACHIEVEMENT
    is in the aggregate output."""
    for k in list(sys.modules):
        if k.startswith("utils.products_to_bsc"):
            del sys.modules[k]
    from utils.products_to_bsc import load_products, aggregate_for_owner
    prods = load_products()
    digital_agg = aggregate_for_owner(prods, ["Digital"], "2026-Q2")
    assert "PRODUCT_REVENUE_ACHIEVEMENT" in digital_agg
    assert "PRODUCT_BOOK_ACHIEVEMENT" not in digital_agg
    assert "PRODUCT_NPL_RATE" not in digital_agg
    assert "PRODUCT_GROWTH_RATE" not in digital_agg


def test_v10335_multi_category_owner_aggregates_combined():
    """CRO owns both Retail Lending + Deposits — aggregate must combine
    both categories' books/revenues."""
    for k in list(sys.modules):
        if k.startswith("utils.products_to_bsc"):
            del sys.modules[k]
    from utils.products_to_bsc import load_products, aggregate_for_owner
    prods = load_products()
    cro = aggregate_for_owner(
        prods, ["Retail Lending", "Deposits"], "2026-Q2"
    )
    retail_only = aggregate_for_owner(prods, ["Retail Lending"], "2026-Q2")
    deposits_only = aggregate_for_owner(prods, ["Deposits"], "2026-Q2")
    # CRO combined aggregate must differ from any single category
    assert (
        cro["PRODUCT_BOOK_ACHIEVEMENT"]
        != retail_only["PRODUCT_BOOK_ACHIEVEMENT"]
    )
    assert (
        cro["PRODUCT_BOOK_ACHIEVEMENT"]
        != deposits_only["PRODUCT_BOOK_ACHIEVEMENT"]
    )


# ────────────────────────────────────────────────────────────────────
# Section 3 — Owner resolution
# ────────────────────────────────────────────────────────────────────

def test_v10335_all_owners_resolve_to_active_staff():
    """All 7 category owner roles resolve to an active staff_code."""
    for k in list(sys.modules):
        if k.startswith("utils.products_to_bsc"):
            del sys.modules[k]
    from utils.products_to_bsc import find_owner_codes, CATEGORY_OWNER_ROLE
    owners = find_owner_codes()
    unresolved = [c for c in CATEGORY_OWNER_ROLE if c not in owners]
    assert not unresolved, f"Unresolved categories: {unresolved}"


def test_v10335_cro_owns_two_categories():
    """Chief Retail Banking Officer should own both Retail Lending +
    Deposits (combined retail book)."""
    for k in list(sys.modules):
        if k.startswith("utils.products_to_bsc"):
            del sys.modules[k]
    from utils.products_to_bsc import CATEGORY_OWNER_ROLE
    cro_cats = [
        cat for cat, role in CATEGORY_OWNER_ROLE.items()
        if role == "Chief Retail Banking Officer"
    ]
    assert "Retail Lending" in cro_cats
    assert "Deposits" in cro_cats


# ────────────────────────────────────────────────────────────────────
# Section 4 — End-to-end cascade
# ────────────────────────────────────────────────────────────────────

def test_v10335_bridge_submits_to_q2_actuals():
    """≥15 actuals from products_to_bsc in 2026-Q2."""
    actuals = json.loads(
        (REPO / "data" / "bsc_actuals_2026-Q2.json").read_text()
    )
    from_bridge = sum(
        1 for r in actuals
        if isinstance(r, dict)
        and r.get("source_module") == "products_to_bsc"
    )
    assert from_bridge >= 15, (
        f"Only {from_bridge} bridge actuals in Q2"
    )


def test_v10335_product_targets_resolve_for_owner_role():
    """get_target_for_staff returns role_default target for CRO on
    PRODUCT_BOOK_ACHIEVEMENT."""
    for k in list(sys.modules):
        if k.startswith("utils.bsc_score_computation"):
            del sys.modules[k]
    from utils.bsc_score_computation import get_target_for_staff
    target = get_target_for_staff(
        "EXEC-CRO-001", "PRODUCT_BOOK_ACHIEVEMENT", "2026-Q2"
    )
    assert target is not None, (
        "CRO PRODUCT_BOOK_ACHIEVEMENT target should resolve"
    )
    val, source = target
    assert val == 100.0
    assert source == "role_default"


def test_v10335_cro_scorecard_includes_product_kpis_with_scores():
    """CRO own scorecard now has PRODUCT_ KPIs with actual + target +
    score populated (was unscored before v10.335)."""
    for k in list(sys.modules):
        if k.startswith("utils."):
            del sys.modules[k]
    from utils.bsc_score_computation import compute_staff_scorecard
    card = compute_staff_scorecard(
        "EXEC-CRO-001", "Chief Retail Banking Officer", "2026-Q2"
    )
    prod_kpis_scored = 0
    for k in card.kpi_scores:
        kid = k.get("kpi_id") if isinstance(k, dict) else k.kpi_id
        actual = k.get("actual") if isinstance(k, dict) else k.actual
        target = k.get("target") if isinstance(k, dict) else k.target
        score = k.get("score") if isinstance(k, dict) else k.score
        if kid.startswith("PRODUCT_"):
            if actual is not None and target is not None and score is not None:
                prod_kpis_scored += 1
    assert prod_kpis_scored >= 3, (
        f"Only {prod_kpis_scored} PRODUCT_ KPIs scored on CRO"
    )
    assert card.final_score is not None, (
        "CRO final_score should not be None after v10.335"
    )


# ────────────────────────────────────────────────────────────────────
# Section 5 — Audit gate G224
# ────────────────────────────────────────────────────────────────────

def test_v10335_g224_gate_registered_and_passes():
    """G224 is registered and passes."""
    for k in list(sys.modules):
        if k.startswith("scripts.audit"):
            del sys.modules[k]
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "audit_module", str(REPO / "scripts" / "audit.py")
    )
    audit_mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(audit_mod)
    gate_ids = [gid for gid, _ in audit_mod.GATES]
    assert "G224" in gate_ids
    result = audit_mod.gate_products_bridge_integration()
    assert result["passed"], f"G224 failed: {result['violations']}"
