"""Integration tests for v10.364 — PBT computation from CBS.

Closes the highest-priority MD BSC gap: bank_targets.json has
PBT|2026 = 650B but pre-v10.364 there was no proper CBS-computable
actual. v10.364 wires utils.pbt_computation.compute_pbt_from_cbs into
compute_bank_aggregates with proper Operating Income - OpEx - Impairment
formula, configurable factors, and full P&L drill-down.

13 tests across 5 sections.
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
# Section 1 — Module + data shape
# ────────────────────────────────────────────────────────────────────

def test_v10364_pbt_module_exists():
    """utils/pbt_computation.py present with the canonical exports."""
    p = REPO / "utils" / "pbt_computation.py"
    assert p.exists()
    text = p.read_text()
    for sym in ("class PBTComponents", "def compute_pbt_from_cbs",
                "def _load_pbt_assumptions", "def _load_opex_estimate",
                "def format_pbt_summary", "def self_test"):
        assert sym in text, f"pbt_computation missing {sym}"


def test_v10364_pbt_assumptions_json_present():
    """data/pbt_assumptions.json present and well-formed."""
    p = REPO / "data" / "pbt_assumptions.json"
    assert p.exists()
    d = json.loads(p.read_text())
    for k in ("cost_of_funds_pct", "lgd_pct", "non_interest_other_pct"):
        assert k in d, f"pbt_assumptions.json missing {k}"
        assert isinstance(d[k], (int, float)), f"{k} not numeric"


def test_v10364_opex_data_json_present():
    """data/opex_data.json present with bank-level financials."""
    p = REPO / "data" / "opex_data.json"
    assert p.exists()
    d = json.loads(p.read_text())
    bank = d.get("bank", {})
    for k in ("staff_costs_kes_b", "it_costs_kes_b", "premises_kes_b",
              "other_opex_kes_b", "total_opex_kes_b"):
        assert k in bank, f"opex_data.json bank section missing {k}"


# ────────────────────────────────────────────────────────────────────
# Section 2 — compute_pbt_from_cbs correctness
# ────────────────────────────────────────────────────────────────────

def test_v10364_compute_pbt_returns_components():
    """compute_pbt_from_cbs returns a fully-populated PBTComponents."""
    _reimport("utils.pbt_computation")
    from utils.pbt_computation import compute_pbt_from_cbs, PBTComponents
    from utils.virtual_bank_seed import seed_virtual_bank, SeedConfig
    from utils.virtual_bank_cbs_writer import persist_bank_to_cbs

    bank, _ = seed_virtual_bank(config=SeedConfig.small())
    with tempfile.TemporaryDirectory() as td:
        persist_bank_to_cbs(bank, output_dir=Path(td))
        c = compute_pbt_from_cbs(Path(td))

    assert isinstance(c, PBTComponents)
    assert isinstance(c.pbt, Decimal)
    assert isinstance(c.operating_income, Decimal)
    assert isinstance(c.total_opex, Decimal)
    # OpEx must come from opex_data.json (the file exists in this repo)
    assert c.opex_source == "opex_data.json", (
        f"OpEx source: {c.opex_source}"
    )


def test_v10364_pbt_formula_consistency():
    """PBT = Operating Income - Total OpEx - Impairment, exactly."""
    _reimport("utils.pbt_computation")
    from utils.pbt_computation import compute_pbt_from_cbs
    from utils.virtual_bank_seed import seed_virtual_bank, SeedConfig
    from utils.virtual_bank_cbs_writer import persist_bank_to_cbs

    bank, _ = seed_virtual_bank(config=SeedConfig.small())
    with tempfile.TemporaryDirectory() as td:
        persist_bank_to_cbs(bank, output_dir=Path(td))
        c = compute_pbt_from_cbs(Path(td))

    # PBT identity
    expected = c.operating_income - c.total_opex - c.impairment_charge
    assert c.pbt == expected, (
        f"PBT formula broken: {c.pbt} != {expected}"
    )
    # NII identity
    assert c.nii == c.interest_income - c.interest_expense
    # Operating income identity
    assert c.operating_income == c.nii + c.non_interest_income
    # Non-interest income identity
    assert c.non_interest_income == c.fee_income + c.non_interest_other


def test_v10364_assumptions_apply():
    """Assumptions from pbt_assumptions.json flow through to components."""
    _reimport("utils.pbt_computation")
    from utils.pbt_computation import compute_pbt_from_cbs
    from utils.virtual_bank_seed import seed_virtual_bank, SeedConfig
    from utils.virtual_bank_cbs_writer import persist_bank_to_cbs

    bank, _ = seed_virtual_bank(config=SeedConfig.small())
    with tempfile.TemporaryDirectory() as td:
        persist_bank_to_cbs(bank, output_dir=Path(td))
        c = compute_pbt_from_cbs(Path(td))

    # Assumptions match what's in pbt_assumptions.json
    d = json.loads((REPO / "data" / "pbt_assumptions.json").read_text())
    assert c.cost_of_funds_pct == Decimal(str(d["cost_of_funds_pct"]))
    assert c.lgd_pct == Decimal(str(d["lgd_pct"]))
    assert c.non_interest_other_pct == Decimal(str(d["non_interest_other_pct"]))


def test_v10364_opex_from_opex_data_json():
    """Total OpEx must match opex_data.json's bank total_opex (converted KES B → KES)."""
    _reimport("utils.pbt_computation")
    from utils.pbt_computation import _load_opex_estimate

    staff, it, premises, other, total, source = _load_opex_estimate()
    assert source == "opex_data.json"

    expected = json.loads((REPO / "data" / "opex_data.json").read_text())
    bank = expected.get("bank", {})
    BILLION = Decimal("1000000000")
    expected_total = Decimal(str(bank["total_opex_kes_b"])) * BILLION
    assert total == expected_total, (
        f"OpEx total mismatch: {total} != {expected_total}"
    )


# ────────────────────────────────────────────────────────────────────
# Section 3 — Wiring into compute_bank_aggregates
# ────────────────────────────────────────────────────────────────────

def test_v10364_aggregates_returns_pbt_nii_cir():
    """compute_bank_aggregates now returns PBT + NII + CIR."""
    _reimport("utils.actuals_engine")
    from utils.actuals_engine import compute_bank_aggregates
    from utils.virtual_bank_seed import seed_virtual_bank, SeedConfig
    from utils.virtual_bank_cbs_writer import persist_bank_to_cbs

    bank, _ = seed_virtual_bank(config=SeedConfig.small())
    with tempfile.TemporaryDirectory() as td:
        persist_bank_to_cbs(bank, output_dir=Path(td))
        agg = compute_bank_aggregates(Path(td))

    for k in ("PBT", "NII", "CIR"):
        assert k in agg, f"compute_bank_aggregates missing key '{k}'"
    # PBT should be a substantial negative for small seed (OpEx >> tiny income)
    assert agg["PBT"] < -1_000_000_000, (
        f"Expected large negative PBT for small seed (OpEx vs tiny income), "
        f"got {agg['PBT']:,.0f}"
    )


def test_v10364_actuals_engine_imports_pbt_module():
    """actuals_engine imports compute_pbt_from_cbs (no longer uses naive
    placeholder for bank-level PBT)."""
    text = (REPO / "utils" / "actuals_engine.py").read_text()
    assert "from utils.pbt_computation import compute_pbt_from_cbs" in text
    # The bank-level PBT line uses _pbt_value
    assert '"PBT":                            _pbt_value' in text


def test_v10364_bank_targets_pbt_target_present():
    """bank_targets.json has PBT|2026 entry that the MD view will read."""
    bt = json.loads((REPO / "data" / "bank_targets.json").read_text())
    assert "PBT|2026" in bt
    pbt_target = bt["PBT|2026"]
    assert isinstance(pbt_target, dict)
    assert "target" in pbt_target
    assert pbt_target["target"] > 0


# ────────────────────────────────────────────────────────────────────
# Section 4 — Format + drill-down
# ────────────────────────────────────────────────────────────────────

def test_v10364_format_summary_includes_components():
    """format_pbt_summary produces a readable drill-down."""
    _reimport("utils.pbt_computation")
    from utils.pbt_computation import compute_pbt_from_cbs, format_pbt_summary
    from utils.virtual_bank_seed import seed_virtual_bank, SeedConfig
    from utils.virtual_bank_cbs_writer import persist_bank_to_cbs

    bank, _ = seed_virtual_bank(config=SeedConfig.small())
    with tempfile.TemporaryDirectory() as td:
        persist_bank_to_cbs(bank, output_dir=Path(td))
        c = compute_pbt_from_cbs(Path(td))

    s = format_pbt_summary(c)
    for keyword in ("PBT", "Operating Income", "Total OpEx", "NII",
                    "Impairment", "OpEx source", "Assumptions"):
        assert keyword in s, f"Summary missing '{keyword}'"


def test_v10364_components_to_dict_serializable():
    """PBTComponents.to_dict() returns JSON-serializable dict."""
    _reimport("utils.pbt_computation")
    from utils.pbt_computation import compute_pbt_from_cbs
    from utils.virtual_bank_seed import seed_virtual_bank, SeedConfig
    from utils.virtual_bank_cbs_writer import persist_bank_to_cbs

    bank, _ = seed_virtual_bank(config=SeedConfig.small())
    with tempfile.TemporaryDirectory() as td:
        persist_bank_to_cbs(bank, output_dir=Path(td))
        c = compute_pbt_from_cbs(Path(td))

    d = c.to_dict()
    # Must be JSON-serializable (no Decimals)
    s = json.dumps(d)
    assert "pbt" in d


# ────────────────────────────────────────────────────────────────────
# Section 5 — G250 audit gate
# ────────────────────────────────────────────────────────────────────

def test_v10364_g250_gate_passes():
    sys.path.insert(0, str(REPO / "scripts"))
    _reimport("audit")
    from audit import gate_pbt_computation
    result = gate_pbt_computation()
    assert result["passed"], result.get("violations")
    assert result["id"] == "G250"


def test_v10364_g250_in_gates_list():
    text = (REPO / "scripts" / "audit.py").read_text()
    assert '("G250", gate_pbt_computation)' in text
