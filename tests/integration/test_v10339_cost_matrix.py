"""Integration tests for v10.339 — Cost matrix admin UI + runtime.

14 tests across 5 sections:
  Section 1 — Rules data file + schema (3 tests)
  Section 2 — CRUD operations (3 tests)
  Section 3 — Compute engine (4 tests)
  Section 4 — Admin UI integration (2 tests)
  Section 5 — Audit gate G228 (2 tests)
"""

import json
import sys
from pathlib import Path

REPO = Path("/tmp/a2z_fix")
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


def _reimport(modname):
    for k in list(sys.modules):
        if k.startswith(modname):
            del sys.modules[k]


# ────────────────────────────────────────────────────────────────────
# Section 1 — Rules data file
# ────────────────────────────────────────────────────────────────────

def test_v10339_rules_file_exists_with_seed_rules():
    """data/cost_allocation_rules.json exists with ≥8 seed rules."""
    p = REPO / "data" / "cost_allocation_rules.json"
    assert p.exists()
    blob = json.loads(p.read_text())
    assert blob.get("_schema_version") == "v10.339"
    rules = blob.get("rules", [])
    assert len(rules) >= 8, f"only {len(rules)} rules"


def test_v10339_seed_rules_total_matches_bank_opex():
    """Total annual opex from active rules ≈ 7.9B (matches opex_data.json)."""
    blob = json.loads(
        (REPO / "data" / "cost_allocation_rules.json").read_text()
    )
    total = sum(
        r.get("annual_amount_kes_b", 0)
        for r in blob["rules"]
        if r.get("active", True)
    )
    # Tier-2 Kenya bank opex band 7.0–9.0B
    assert 7.0 <= total <= 9.0, f"total opex {total}B outside band"


def test_v10339_rules_have_required_fields():
    """Every rule has rule_id + cost_item + allocation_method + amount."""
    blob = json.loads(
        (REPO / "data" / "cost_allocation_rules.json").read_text()
    )
    for r in blob["rules"]:
        for field in (
            "rule_id", "cost_item", "allocation_method",
            "annual_amount_kes_b",
        ):
            assert field in r, f"rule missing {field}: {r}"


# ────────────────────────────────────────────────────────────────────
# Section 2 — CRUD
# ────────────────────────────────────────────────────────────────────

def test_v10339_load_rules_returns_list():
    _reimport("utils.cost_allocation")
    from utils.cost_allocation import load_rules, load_active_rules
    rules = load_rules()
    assert isinstance(rules, list)
    assert len(rules) >= 8
    active = load_active_rules()
    assert all(r.get("active", True) for r in active)


def test_v10339_upsert_then_delete_roundtrip():
    """Upsert a new rule, verify, delete it, verify it's gone."""
    _reimport("utils.cost_allocation")
    from utils.cost_allocation import (
        upsert_rule, delete_rule, load_rules,
    )
    new_rule = {
        "rule_id":              "RULE_TEST_v10339",
        "cost_item":            "Test cost",
        "annual_amount_kes_b":  0.02,
        "allocation_method":    "driver_based",
        "driver_1":             "staff_count_by_segment",
        "driver_1_weight":      1.0,
        "active":               True,
    }
    res = upsert_rule(new_rule, username="test")
    assert res["saved"], res.get("errors")
    assert res["op"] == "insert"
    assert any(r.get("rule_id") == "RULE_TEST_v10339" for r in load_rules())

    res = delete_rule("RULE_TEST_v10339", username="test")
    assert res.get("deleted"), res
    assert not any(r.get("rule_id") == "RULE_TEST_v10339" for r in load_rules())


def test_v10339_upsert_rejects_invalid_rule():
    """Validation gate stops malformed rules from saving."""
    _reimport("utils.cost_allocation")
    from utils.cost_allocation import upsert_rule
    bad = {
        "rule_id":              "RULE_BAD",
        "cost_item":            "",
        "allocation_method":    "magic_method",
    }
    res = upsert_rule(bad, username="test")
    assert not res["saved"]
    assert res["errors"]


# ────────────────────────────────────────────────────────────────────
# Section 3 — Compute engine
# ────────────────────────────────────────────────────────────────────

def test_v10339_apply_rules_returns_per_segment_allocation():
    """apply_rules → at least one non-direct cost item with segment allocation."""
    _reimport("utils.cost_allocation")
    from utils.cost_allocation import apply_rules
    alloc = apply_rules()
    non_direct = {k: v for k, v in alloc.items() if not k.startswith("_")}
    assert non_direct, "no non-direct allocations produced"
    # Every non-direct entry must have at least one canonical segment
    canonical = {"AFFLUENT", "CORE_MIDDLE", "MASS",
                 "MICRO", "SMALL", "MEDIUM", "CORPORATE"}
    for ci, dist in non_direct.items():
        assert dist, f"empty allocation for {ci}"
        assert set(dist.keys()) & canonical, (
            f"{ci} not allocated to canonical segments: {set(dist.keys())}"
        )


def test_v10339_direct_costs_surfaced_separately():
    """Direct rules surface under '_direct' key, not in segment allocation."""
    _reimport("utils.cost_allocation")
    from utils.cost_allocation import apply_rules
    alloc = apply_rules()
    direct = alloc.get("_direct", {})
    assert direct, "no direct items surfaced"
    # Loan loss provisions + funding interest expense are direct per seed
    expected = {"Loan loss provisions (IFRS 9)", "Funding interest expense"}
    assert set(direct.keys()) & expected, (
        f"expected direct items missing: {set(direct.keys())}"
    )


def test_v10339_equal_split_method_distributes_across_all_segments():
    """Equal-split rule allocates ~equally to all 7 segments."""
    _reimport("utils.cost_allocation")
    from utils.cost_allocation import apply_rules
    alloc = apply_rules()
    # RULE_007 audit fees is equal_split
    audit_alloc = alloc.get("Audit and professional fees")
    assert audit_alloc is not None
    # 7 segments, 0.15B annual / 4 quarters = 37.5M / 7 ≈ 5.36M each
    assert len(audit_alloc) == 7
    values = list(audit_alloc.values())
    # Range should be tight (only rounding differences)
    assert max(values) - min(values) < 1.0  # within KES 1 difference


def test_v10339_reconciliation_report_shape():
    """reconciliation_report returns expected fields."""
    _reimport("utils.cost_allocation")
    from utils.cost_allocation import reconciliation_report
    rep = reconciliation_report()
    for field in (
        "rule_count", "active_count", "total_annual_kes_b",
        "total_quarterly_kes_m", "by_method", "coverage_by_segment",
    ):
        assert field in rep, f"missing {field}"
    assert 7.0 <= rep["total_annual_kes_b"] <= 9.0
    assert rep["active_count"] >= 8
    # by_method covers seeded methods
    methods = set(rep["by_method"].keys())
    assert {"driver_based", "equal_split", "direct"} <= methods


# ────────────────────────────────────────────────────────────────────
# Section 4 — Admin UI
# ────────────────────────────────────────────────────────────────────

def test_v10339_admin_page_has_cost_matrix_tab():
    """7_admin.py has the v10.339 Cost Matrix tab."""
    text = (REPO / "pages" / "7_admin.py").read_text()
    assert "💰 Cost Matrix" in text
    assert "Cost Allocation Matrix" in text
    assert "from utils.cost_allocation import" in text


def test_v10339_performance_section_has_three_tabs():
    """Performance section expanded to 3 tabs (KPI Library / Segment / Cost)."""
    text = (REPO / "pages" / "7_admin.py").read_text()
    # The Performance section tabs block
    idx = text.find("# ── Section 1: Performance & BSC")
    assert idx >= 0
    section_block = text[idx:idx + 600]
    assert "📚 KPI Library" in section_block
    assert "🎯 Segment Configuration" in section_block
    assert "💰 Cost Matrix" in section_block


# ────────────────────────────────────────────────────────────────────
# Section 5 — G228 gate
# ────────────────────────────────────────────────────────────────────

def test_v10339_g228_gate_passes():
    """G228 audit gate registered + passing."""
    _reimport("scripts.audit")
    sys.path.insert(0, str(REPO / "scripts"))
    from audit import gate_cost_matrix_admin
    result = gate_cost_matrix_admin()
    assert result["passed"], result.get("violations")
    assert result["id"] == "G228"
    assert result["name"] == "cost_matrix_admin"


def test_v10339_g228_registered_in_gates_list():
    """G228 is in the GATES list."""
    text = (REPO / "scripts" / "audit.py").read_text()
    assert '("G228", gate_cost_matrix_admin)' in text
