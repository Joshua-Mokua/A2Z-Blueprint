"""Integration tests for v10.371 — Multi-Level bank_targets Schema.

Fourth concrete unification step from v10.367 architecture arc. Extends
bank_targets.json from <metric>|<year> (2-segment) to
<metric>|<level>|<entity>|<year> (4-segment) where level ∈
{bank, sbu, branch, staff, customer}.

Closes the top-down half of the reconciliation: actuals atomic since
v10.370 (G256, G257); targets atomic since v10.371 (G258).

15 tests across 5 sections.
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
# Section 1 — Module surface
# ────────────────────────────────────────────────────────────────────

def test_v10371_module_present():
    p = REPO / "utils" / "bank_targets_schema.py"
    assert p.exists()
    text = p.read_text()
    for sym in ("def parse_target_key",
                "def compose_target_key",
                "def migrate_legacy_targets",
                "def get_target",
                "def set_target",
                "def list_targets_at_level",
                "def sum_children_at_level",
                "def validate_target_hierarchy",
                "def load_bank_targets",
                "def save_bank_targets",
                "def self_test",
                "class TargetKey"):
        assert sym in text, f"bank_targets_schema missing {sym}"


def test_v10371_self_test_passes():
    _reimport("utils.bank_targets_schema")
    from utils.bank_targets_schema import self_test
    import io
    import contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        self_test()
    assert "self-test passed" in buf.getvalue()


def test_v10371_levels_defined():
    _reimport("utils.bank_targets_schema")
    from utils.bank_targets_schema import (
        LEVEL_BANK, LEVEL_SBU, LEVEL_BRANCH, LEVEL_STAFF,
        LEVEL_CUSTOMER, ALL_LEVELS, BANK_ENTITY_ALL,
    )
    assert ALL_LEVELS == (LEVEL_BANK, LEVEL_SBU, LEVEL_BRANCH,
                           LEVEL_STAFF, LEVEL_CUSTOMER)
    assert BANK_ENTITY_ALL == "all"


# ────────────────────────────────────────────────────────────────────
# Section 2 — Parsing / composing / migration
# ────────────────────────────────────────────────────────────────────

def test_v10371_legacy_key_parses_as_bank_all():
    _reimport("utils.bank_targets_schema")
    from utils.bank_targets_schema import parse_target_key, LEVEL_BANK, BANK_ENTITY_ALL
    k = parse_target_key("PBT|2026")
    assert k.metric == "PBT"
    assert k.level == LEVEL_BANK
    assert k.entity == BANK_ENTITY_ALL
    assert k.year == "2026"


def test_v10371_new_4segment_key_parses():
    _reimport("utils.bank_targets_schema")
    from utils.bank_targets_schema import parse_target_key
    k = parse_target_key("PBT|branch|BR001|2026")
    assert k.metric == "PBT"
    assert k.level == "branch"
    assert k.entity == "BR001"
    assert k.year == "2026"


def test_v10371_invalid_keys_return_none():
    _reimport("utils.bank_targets_schema")
    from utils.bank_targets_schema import parse_target_key
    assert parse_target_key("") is None
    assert parse_target_key("_schema_version") is None
    assert parse_target_key("only_one_segment") is None
    # 3-segment is also rejected — must be 2 (legacy) or 4 (new)
    assert parse_target_key("a|b|c") is None


def test_v10371_migrate_creates_aliases():
    _reimport("utils.bank_targets_schema")
    from utils.bank_targets_schema import migrate_legacy_targets
    raw = {
        "PBT|2026": {"target": 1000, "buffer_pct": 0},
        "Total NFI|2026": {"target": 500, "buffer_pct": 0},
        "_schema_version": "v1",
    }
    mig = migrate_legacy_targets(raw)
    # Originals preserved
    assert "PBT|2026" in mig
    assert "Total NFI|2026" in mig
    # Aliases added
    assert "PBT|bank|all|2026" in mig
    assert "Total NFI|bank|all|2026" in mig
    # Metadata preserved
    assert mig["_schema_version"] == "v1"
    # Original raw unmodified
    assert "PBT|bank|all|2026" not in raw


# ────────────────────────────────────────────────────────────────────
# Section 3 — THE HIERARCHY IDENTITY
# ────────────────────────────────────────────────────────────────────

def test_v10371_balanced_hierarchy_passes():
    _reimport("utils.bank_targets_schema")
    from utils.bank_targets_schema import (
        set_target, validate_target_hierarchy,
        LEVEL_SBU, LEVEL_BRANCH,
    )
    t = {"PBT|2026": {"target": 1000}}
    set_target(t, "PBT", LEVEL_SBU, "Retail", "2026", {"target": 600})
    set_target(t, "PBT", LEVEL_SBU, "Commercial", "2026", {"target": 400})
    set_target(t, "PBT", LEVEL_BRANCH, "BR01", "2026", {"target": 500})
    set_target(t, "PBT", LEVEL_BRANCH, "BR02", "2026", {"target": 500})
    violations = validate_target_hierarchy(t, "PBT", "2026")
    assert violations == [], f"expected empty, got {violations}"


def test_v10371_unbalanced_hierarchy_surfaces_violation():
    _reimport("utils.bank_targets_schema")
    from utils.bank_targets_schema import (
        set_target, validate_target_hierarchy, LEVEL_SBU,
    )
    t = {"PBT|2026": {"target": 1000}}
    set_target(t, "PBT", LEVEL_SBU, "Retail", "2026", {"target": 600})
    set_target(t, "PBT", LEVEL_SBU, "Commercial", "2026", {"target": 200})  # 200 short
    violations = validate_target_hierarchy(t, "PBT", "2026")
    assert len(violations) == 1
    assert "Σ(sbu" in violations[0]


def test_v10371_tolerance_configurable():
    _reimport("utils.bank_targets_schema")
    from utils.bank_targets_schema import (
        set_target, validate_target_hierarchy, LEVEL_BRANCH,
    )
    t = {"PBT|2026": {"target": 100000}}
    set_target(t, "PBT", LEVEL_BRANCH, "BR01", "2026", {"target": 100100})  # 0.1% over
    # At default 0.1% tolerance — passes (exactly at the line)
    violations = validate_target_hierarchy(t, "PBT", "2026")
    assert violations == []
    # At tighter 0.05% — fails
    violations = validate_target_hierarchy(
        t, "PBT", "2026", tolerance_pct=Decimal("0.05")
    )
    assert len(violations) == 1


def test_v10371_sparse_levels_allowed():
    """Only some levels populated — should pass (sparse is OK)."""
    _reimport("utils.bank_targets_schema")
    from utils.bank_targets_schema import (
        set_target, validate_target_hierarchy, LEVEL_SBU,
    )
    t = {"PBT|2026": {"target": 1000}}
    set_target(t, "PBT", LEVEL_SBU, "Retail", "2026", {"target": 1000})
    # No branch/staff/customer — should not fail
    violations = validate_target_hierarchy(t, "PBT", "2026")
    assert violations == []


def test_v10371_override_flag_short_circuits():
    _reimport("utils.bank_targets_schema")
    from utils.bank_targets_schema import (
        set_target, validate_target_hierarchy,
        LEVEL_SBU, OVERRIDE_FLAG_KEY,
    )
    t = {"PBT|2026": {"target": 1000},
         OVERRIDE_FLAG_KEY: True}
    set_target(t, "PBT", LEVEL_SBU, "Retail", "2026", {"target": 1})  # way off
    violations = validate_target_hierarchy(t, "PBT", "2026")
    # Override returns informational note, not a true violation
    assert len(violations) == 1
    assert "OVERRIDE" in violations[0]


# ────────────────────────────────────────────────────────────────────
# Section 4 — Live bank_targets.json behavior
# ────────────────────────────────────────────────────────────────────

def test_v10371_load_real_bank_targets_validates_clean():
    """Production bank_targets.json (no child targets yet) must validate clean."""
    _reimport("utils.bank_targets_schema")
    from utils.bank_targets_schema import (
        load_bank_targets, validate_target_hierarchy,
    )
    targets = load_bank_targets()
    # Sparse children — should be clean
    violations = validate_target_hierarchy(targets, "PBT", "2026")
    assert violations == []


def test_v10371_legacy_get_target_works():
    """Reading bank|all target works via legacy fallback."""
    _reimport("utils.bank_targets_schema")
    from utils.bank_targets_schema import (
        load_bank_targets, get_target,
        LEVEL_BANK, BANK_ENTITY_ALL,
    )
    targets = load_bank_targets()
    rec = get_target(targets, "PBT", LEVEL_BANK, BANK_ENTITY_ALL, "2026")
    assert rec is not None
    assert "target" in rec


def test_v10371_save_strips_alias():
    """save_bank_targets shouldn't double-write bank|all alongside legacy."""
    _reimport("utils.bank_targets_schema")
    from utils.bank_targets_schema import (
        load_bank_targets, save_bank_targets,
    )
    with tempfile.TemporaryDirectory() as td:
        # Write a roundtrip: load production → save to temp → reload
        tp = Path(td) / "bt.json"
        targets = load_bank_targets()
        save_bank_targets(targets, path=tp)
        # Re-read raw
        on_disk = json.loads(tp.read_text())
        # Should NOT contain "PBT|bank|all|2026" if "PBT|2026" exists
        if "PBT|2026" in on_disk:
            assert "PBT|bank|all|2026" not in on_disk


# ────────────────────────────────────────────────────────────────────
# Section 5 — G258 + regression
# ────────────────────────────────────────────────────────────────────

def test_v10371_g258_passes():
    sys.path.insert(0, str(REPO / "scripts"))
    _reimport("audit")
    from audit import gate_target_hierarchy
    result = gate_target_hierarchy()
    assert result["passed"], result.get("violations")
    assert result["id"] == "G258"


def test_v10371_charter_section_2_still_passes():
    _reimport("utils.virtual_bank_seed")
    _reimport("utils.virtual_bank_cbs_writer")
    _reimport("utils.teller_actions")
    from utils.virtual_bank_seed import seed_virtual_bank, SeedConfig
    from utils.virtual_bank_cbs_writer import persist_bank_to_cbs
    from utils.actuals_engine import compute_bank_aggregates
    from utils.teller_actions import fire_teller_deposit, find_first_deposit_account

    DEPOSIT = Decimal("100000000")
    bank, _ = seed_virtual_bank(config=SeedConfig.small())
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        persist_bank_to_cbs(bank, output_dir=td_path)
        before = compute_bank_aggregates(td_path).get("Deposit Growth", 0)
        account = find_first_deposit_account(bank)
        fire_teller_deposit(bank, account_no=account, amount=DEPOSIT)
        persist_bank_to_cbs(bank, output_dir=td_path)
        after = compute_bank_aggregates(td_path).get("Deposit Growth", 0)
    delta = Decimal(str(after - before))
    assert delta == DEPOSIT


def test_v10371_all_four_actuals_rollups_still_reconcile():
    """v10.370 identities must still hold after v10.371 changes."""
    _reimport("utils.virtual_bank_seed")
    _reimport("utils.virtual_bank_cbs_writer")
    _reimport("utils.customer_pbt_allocator")
    _reimport("utils.branch_pbt_allocator")
    _reimport("utils.pbt_computation")
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
    bank, _ = seed_virtual_bank(config=SeedConfig.small())
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        persist_bank_to_cbs(bank, output_dir=td_path)
        bp = compute_pbt_from_cbs(td_path)
        for rollup_sum in (
            sum_sbu_pbts(compute_pbt_by_sbu(td_path)),
            sum_branch_pbts(compute_pbt_by_branch(td_path)),
            sum_customer_pbts(compute_pbt_by_customer(td_path)),
            sum_staff_pbts(compute_pbt_by_staff(td_path)),
        ):
            delta = abs(bp.pbt - rollup_sum.pbt)
            assert delta <= Decimal("100"), f"delta {float(delta):,.0f}"
