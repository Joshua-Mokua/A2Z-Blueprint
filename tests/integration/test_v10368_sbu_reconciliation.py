"""Integration tests for v10.368 — SBU PBT reconciliation.

First concrete unification step from the v10.367 architecture arc:
- compute_pbt_by_sbu returns Dict[str, PBTComponents]
- Σ(SBU PBT) == Bank PBT within KES 100 (the reconciliation identity)
- Six SBU buckets: Retail, Commercial, Corporate, Treasury, Digital/Agency, Unallocated
- Mapping in data/segment_sbu_mapping.json (Rule N1)
- Bridge writes customers.csv as companion to accounts.csv

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

def test_v10368_compute_pbt_by_sbu_present():
    text = (REPO / "utils" / "pbt_computation.py").read_text()
    for sym in ("def compute_pbt_by_sbu",
                "def sum_sbu_pbts",
                "def format_sbu_breakdown",
                "def _load_segment_sbu_mapping",
                "def _load_opex_by_sbu",
                "def _load_customer_segment_lookup"):
        assert sym in text, f"pbt_computation missing {sym}"


def test_v10368_segment_sbu_mapping_config_present():
    p = REPO / "data" / "segment_sbu_mapping.json"
    assert p.exists()
    d = json.loads(p.read_text())
    assert "segment_to_sbu" in d
    assert "operational_sbus" in d
    # All three naming conventions covered
    s2s = d["segment_to_sbu"]
    for code in ("AFFLUENT", "MASS", "RETAIL", "SME", "CORPORATE"):
        assert code in s2s, f"Mapping missing {code}"


def test_v10368_bridge_writes_customers_csv():
    _reimport("utils.virtual_bank_seed")
    _reimport("utils.virtual_bank_cbs_writer")
    from utils.virtual_bank_seed import seed_virtual_bank, SeedConfig
    from utils.virtual_bank_cbs_writer import persist_bank_to_cbs

    bank, _ = seed_virtual_bank(config=SeedConfig.small())
    with tempfile.TemporaryDirectory() as td:
        persist_bank_to_cbs(bank, output_dir=Path(td))
        cust_csv = Path(td) / "customers.csv"
        assert cust_csv.exists(), "Bridge didn't write customers.csv"
        # Schema check
        import csv
        with open(cust_csv) as f:
            r = csv.DictReader(f)
            assert r.fieldnames == ["cif", "full_name", "segment",
                                     "branch_code", "rm_code"]
            rows = list(r)
            assert len(rows) >= 50  # small seed has 100 customers
            for row in rows[:5]:
                assert row["cif"]
                assert row["segment"]


# ────────────────────────────────────────────────────────────────────
# Section 2 — compute_pbt_by_sbu correctness
# ────────────────────────────────────────────────────────────────────

def test_v10368_returns_all_known_sbus():
    _reimport("utils.virtual_bank_seed")
    _reimport("utils.virtual_bank_cbs_writer")
    _reimport("utils.pbt_computation")
    from utils.virtual_bank_seed import seed_virtual_bank, SeedConfig
    from utils.virtual_bank_cbs_writer import persist_bank_to_cbs
    from utils.pbt_computation import compute_pbt_by_sbu

    bank, _ = seed_virtual_bank(config=SeedConfig.small())
    with tempfile.TemporaryDirectory() as td:
        persist_bank_to_cbs(bank, output_dir=Path(td))
        sbu_pbts = compute_pbt_by_sbu(Path(td))

    # All 5 SBUs from opex_data + Unallocated
    expected = {"Retail Banking", "Commercial Banking", "Corporate Banking",
                "Treasury", "Digital / Agency", "Unallocated"}
    actual = set(sbu_pbts.keys())
    assert expected.issubset(actual), (
        f"Missing SBUs: {expected - actual}; got: {actual}"
    )


def test_v10368_customer_facing_sbus_have_income():
    """Retail/Commercial/Corporate SBUs should have non-zero operating
    income from customer-attributed accounts."""
    _reimport("utils.virtual_bank_seed")
    _reimport("utils.virtual_bank_cbs_writer")
    _reimport("utils.pbt_computation")
    from utils.virtual_bank_seed import seed_virtual_bank, SeedConfig
    from utils.virtual_bank_cbs_writer import persist_bank_to_cbs
    from utils.pbt_computation import compute_pbt_by_sbu

    bank, _ = seed_virtual_bank(config=SeedConfig.small())
    with tempfile.TemporaryDirectory() as td:
        persist_bank_to_cbs(bank, output_dir=Path(td))
        sbu_pbts = compute_pbt_by_sbu(Path(td))

    # Retail Banking should have customers + non-zero income
    retail = sbu_pbts.get("Retail Banking")
    assert retail is not None
    # Income may be negative (small seed) but should be non-zero
    assert retail.interest_income > 0 or retail.fee_income > 0, (
        "Retail Banking has no income at all — segment attribution may be broken"
    )


def test_v10368_operational_sbus_have_zero_income():
    """Treasury & Digital/Agency are operational — no customer-attributable
    income in CBS yet, but they have their config OpEx."""
    _reimport("utils.virtual_bank_seed")
    _reimport("utils.virtual_bank_cbs_writer")
    _reimport("utils.pbt_computation")
    from utils.virtual_bank_seed import seed_virtual_bank, SeedConfig
    from utils.virtual_bank_cbs_writer import persist_bank_to_cbs
    from utils.pbt_computation import compute_pbt_by_sbu

    bank, _ = seed_virtual_bank(config=SeedConfig.small())
    with tempfile.TemporaryDirectory() as td:
        persist_bank_to_cbs(bank, output_dir=Path(td))
        sbu_pbts = compute_pbt_by_sbu(Path(td))

    treasury = sbu_pbts.get("Treasury")
    assert treasury is not None
    assert treasury.operating_income == Decimal("0"), (
        f"Treasury has unexpected income: {treasury.operating_income}"
    )
    assert treasury.total_opex > 0, "Treasury has no OpEx allocated"
    # PBT = -OpEx
    assert treasury.pbt == -treasury.total_opex


def test_v10368_unallocated_absorbs_opex_gap():
    """The 0.7B gap between bank.total_opex (7.9B) and Σ(by_sbu.opex) (7.2B)
    must be absorbed by the Unallocated bucket."""
    _reimport("utils.virtual_bank_seed")
    _reimport("utils.virtual_bank_cbs_writer")
    _reimport("utils.pbt_computation")
    from utils.virtual_bank_seed import seed_virtual_bank, SeedConfig
    from utils.virtual_bank_cbs_writer import persist_bank_to_cbs
    from utils.pbt_computation import compute_pbt_by_sbu

    bank, _ = seed_virtual_bank(config=SeedConfig.small())
    with tempfile.TemporaryDirectory() as td:
        persist_bank_to_cbs(bank, output_dir=Path(td))
        sbu_pbts = compute_pbt_by_sbu(Path(td))

    unalloc = sbu_pbts.get("Unallocated")
    assert unalloc is not None
    # Expected gap: 7.9B - (3.1 + 2.0 + 0.9 + 0.4 + 0.8) = 0.7B
    EXPECTED_GAP = Decimal("700000000")
    assert abs(unalloc.total_opex - EXPECTED_GAP) < Decimal("10000"), (
        f"Unallocated OpEx {float(unalloc.total_opex):,.0f} != "
        f"expected gap {float(EXPECTED_GAP):,.0f}"
    )


# ────────────────────────────────────────────────────────────────────
# Section 3 — THE RECONCILIATION IDENTITY
# ────────────────────────────────────────────────────────────────────

def test_v10368_sum_sbu_equals_bank_pbt_exact():
    """THE CORE IDENTITY: Σ(SBU PBT) == Bank PBT exactly (or within
    KES 100 tolerance for rounding)."""
    _reimport("utils.virtual_bank_seed")
    _reimport("utils.virtual_bank_cbs_writer")
    _reimport("utils.pbt_computation")
    from utils.virtual_bank_seed import seed_virtual_bank, SeedConfig
    from utils.virtual_bank_cbs_writer import persist_bank_to_cbs
    from utils.pbt_computation import (
        compute_pbt_from_cbs, compute_pbt_by_sbu, sum_sbu_pbts,
    )

    bank, _ = seed_virtual_bank(config=SeedConfig.small())
    with tempfile.TemporaryDirectory() as td:
        persist_bank_to_cbs(bank, output_dir=Path(td))
        bank_pbt = compute_pbt_from_cbs(Path(td))
        sbu_pbts = compute_pbt_by_sbu(Path(td))
        sbu_total = sum_sbu_pbts(sbu_pbts)

    delta = abs(bank_pbt.pbt - sbu_total.pbt)
    TOLERANCE = Decimal("100")
    assert delta <= TOLERANCE, (
        f"RECONCILIATION BROKEN: Σ(SBU PBT) {float(sbu_total.pbt):,.0f} != "
        f"Bank PBT {float(bank_pbt.pbt):,.0f}; delta {float(delta):,.0f} > {TOLERANCE}"
    )


def test_v10368_sum_sbu_equals_bank_interest_income():
    _reimport("utils.virtual_bank_seed")
    _reimport("utils.virtual_bank_cbs_writer")
    _reimport("utils.pbt_computation")
    from utils.virtual_bank_seed import seed_virtual_bank, SeedConfig
    from utils.virtual_bank_cbs_writer import persist_bank_to_cbs
    from utils.pbt_computation import (
        compute_pbt_from_cbs, compute_pbt_by_sbu, sum_sbu_pbts,
    )

    bank, _ = seed_virtual_bank(config=SeedConfig.small())
    with tempfile.TemporaryDirectory() as td:
        persist_bank_to_cbs(bank, output_dir=Path(td))
        bank_pbt = compute_pbt_from_cbs(Path(td))
        sbu_total = sum_sbu_pbts(compute_pbt_by_sbu(Path(td)))

    # Interest income should be the same regardless of bucketing
    assert sbu_total.interest_income == bank_pbt.interest_income


def test_v10368_sum_sbu_equals_bank_total_opex():
    _reimport("utils.virtual_bank_seed")
    _reimport("utils.virtual_bank_cbs_writer")
    _reimport("utils.pbt_computation")
    from utils.virtual_bank_seed import seed_virtual_bank, SeedConfig
    from utils.virtual_bank_cbs_writer import persist_bank_to_cbs
    from utils.pbt_computation import (
        compute_pbt_from_cbs, compute_pbt_by_sbu, sum_sbu_pbts,
    )

    bank, _ = seed_virtual_bank(config=SeedConfig.small())
    with tempfile.TemporaryDirectory() as td:
        persist_bank_to_cbs(bank, output_dir=Path(td))
        bank_pbt = compute_pbt_from_cbs(Path(td))
        sbu_total = sum_sbu_pbts(compute_pbt_by_sbu(Path(td)))

    # Total OpEx should match bank-level (Unallocated absorbs gap)
    assert sbu_total.total_opex == bank_pbt.total_opex, (
        f"Σ SBU OpEx {sbu_total.total_opex} != bank OpEx {bank_pbt.total_opex}"
    )


# ────────────────────────────────────────────────────────────────────
# Section 4 — Format + serialization
# ────────────────────────────────────────────────────────────────────

def test_v10368_format_sbu_breakdown_readable():
    _reimport("utils.virtual_bank_seed")
    _reimport("utils.virtual_bank_cbs_writer")
    _reimport("utils.pbt_computation")
    from utils.virtual_bank_seed import seed_virtual_bank, SeedConfig
    from utils.virtual_bank_cbs_writer import persist_bank_to_cbs
    from utils.pbt_computation import compute_pbt_by_sbu, format_sbu_breakdown

    bank, _ = seed_virtual_bank(config=SeedConfig.small())
    with tempfile.TemporaryDirectory() as td:
        persist_bank_to_cbs(bank, output_dir=Path(td))
        s = format_sbu_breakdown(compute_pbt_by_sbu(Path(td)))
    for keyword in ("Retail Banking", "Commercial Banking", "Corporate Banking",
                    "Treasury", "Bank Total", "OpIncome", "PBT"):
        assert keyword in s, f"format_sbu_breakdown missing '{keyword}'"


def test_v10368_each_pbt_components_serializes():
    _reimport("utils.virtual_bank_seed")
    _reimport("utils.virtual_bank_cbs_writer")
    _reimport("utils.pbt_computation")
    from utils.virtual_bank_seed import seed_virtual_bank, SeedConfig
    from utils.virtual_bank_cbs_writer import persist_bank_to_cbs
    from utils.pbt_computation import compute_pbt_by_sbu

    bank, _ = seed_virtual_bank(config=SeedConfig.small())
    with tempfile.TemporaryDirectory() as td:
        persist_bank_to_cbs(bank, output_dir=Path(td))
        sbu_pbts = compute_pbt_by_sbu(Path(td))
    # All PBTComponents must serialize
    for sbu, comp in sbu_pbts.items():
        d = comp.to_dict()
        s = json.dumps(d)
        assert isinstance(d["pbt"], float)


# ────────────────────────────────────────────────────────────────────
# Section 5 — G254 audit gate + regression check
# ────────────────────────────────────────────────────────────────────

def test_v10368_g254_passes():
    sys.path.insert(0, str(REPO / "scripts"))
    _reimport("audit")
    from audit import gate_sbu_reconciliation
    result = gate_sbu_reconciliation()
    assert result["passed"], result.get("violations")
    assert result["id"] == "G254"


def test_v10368_g254_in_gates_list():
    text = (REPO / "scripts" / "audit.py").read_text()
    assert '("G254", gate_sbu_reconciliation)' in text


def test_v10368_charter_section_2_still_passes_with_sbu_dimension():
    """Adding SBU dimension shouldn't break Charter §2: teller deposits
    still propagate to bank-wide totals."""
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
    assert delta == DEPOSIT, (
        f"Charter §2 regression: delta {delta} != {DEPOSIT}"
    )
