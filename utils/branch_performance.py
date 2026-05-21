"""
================================================================================
A2Z MIS 360 — Standard #94: Branch Performance Management & Peer Benchmarking
================================================================================

Risk classification: Cat B (deterministic branch P&L + percentile benchmarking)

Provides:
    - branch_pnl(...)               -- 6-line branch profit & loss
    - cost_income_ratio(...)        -- C/I ratio with Rule 1
    - return_on_avg_assets(...)     -- ROAA with Rule 1
    - quartile_rank(...)            -- TIER_1 (top) ... TIER_4 (bottom)
    - peer_benchmark_metrics(...)   -- p25/median/p75 across peer group

6 BRANCH_PNL_LINES byte-for-byte:
    NII, NON_INTEREST_INCOME, OPEX_DIRECT, OPEX_ALLOCATED, IMPAIRMENT, NPBT

4 PERFORMANCE_TIERS byte-for-byte:
    TIER_1 (top 25%)
    TIER_2 (50-75%)
    TIER_3 (25-50%)
    TIER_4 (bottom 25%)

Quartile boundaries byte-for-byte:
    TIER_1_THRESHOLD_PCT = 75   -- ≥75th percentile
    TIER_2_THRESHOLD_PCT = 50   -- ≥50th percentile
    TIER_3_THRESHOLD_PCT = 25   -- ≥25th percentile
    -- below 25th = TIER_4

3 BRANCH_LIFECYCLE_STAGES byte-for-byte:
    NEW          (<2yr)
    GROWTH       (2-5yr)
    MATURE       (5+yr)

LIFECYCLE_BANDS_YEARS byte-for-byte:
    NEW    : (0, 2)
    GROWTH : (2, 5)
    MATURE : (5, 999)

3 PEER_GROUP_LOCATIONS byte-for-byte:
    TIER_1_CITIES (Nairobi/Mombasa metros)
    TIER_2_CITIES (other major towns)
    RURAL

3 PEER_GROUP_SIZES byte-for-byte:
    LARGE, MEDIUM, SMALL

3 BENCHMARK_PERCENTILES byte-for-byte:
    PERCENTILE_25, MEDIAN, PERCENTILE_75

Honesty rules applied:
    Rule 1: cost_income_ratio=None when total_income=0 or missing
            ROAA=None when avg_assets=0 or missing
            quartile_rank=None when peer_group empty
    Rule 6: missing branch metrics surfaced

================================================================================
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, getcontext
from typing import Any, Dict, List, Optional, Tuple

getcontext().prec = 28

# 6 BRANCH P&L LINES byte-for-byte
BRANCH_PNL_LINES: Tuple[str, ...] = (
    "NII", "NON_INTEREST_INCOME", "OPEX_DIRECT", "OPEX_ALLOCATED",
    "IMPAIRMENT", "NPBT",
)

# 4 PERFORMANCE TIERS byte-for-byte
PERFORMANCE_TIERS: Tuple[str, ...] = (
    "TIER_1", "TIER_2", "TIER_3", "TIER_4",
)

# Quartile thresholds byte-for-byte
TIER_1_THRESHOLD_PCT = Decimal("75")
TIER_2_THRESHOLD_PCT = Decimal("50")
TIER_3_THRESHOLD_PCT = Decimal("25")

# 3 LIFECYCLE STAGES byte-for-byte
BRANCH_LIFECYCLE_STAGES: Tuple[str, ...] = ("NEW", "GROWTH", "MATURE")

LIFECYCLE_BANDS_YEARS: Dict[str, Tuple[int, int]] = {
    "NEW": (0, 2),
    "GROWTH": (2, 5),
    "MATURE": (5, 999),
}

# 3 PEER GROUP LOCATIONS byte-for-byte
PEER_GROUP_LOCATIONS: Tuple[str, ...] = (
    "TIER_1_CITIES", "TIER_2_CITIES", "RURAL",
)

# 3 PEER GROUP SIZES byte-for-byte
PEER_GROUP_SIZES: Tuple[str, ...] = ("LARGE", "MEDIUM", "SMALL")

# 3 BENCHMARK PERCENTILES byte-for-byte
BENCHMARK_PERCENTILES: Tuple[str, ...] = (
    "PERCENTILE_25", "MEDIAN", "PERCENTILE_75",
)


@dataclass
class BranchPnlInputs:
    branch_id: str
    nii: Optional[Decimal] = None
    non_interest_income: Optional[Decimal] = None
    opex_direct: Optional[Decimal] = None
    opex_allocated: Optional[Decimal] = None
    impairment: Optional[Decimal] = None
    avg_assets: Optional[Decimal] = None


class BranchPerformanceEngine:
    """Deterministic branch P&L + peer benchmarking."""

    @staticmethod
    def branch_pnl(inputs: BranchPnlInputs) -> Dict[str, Any]:
        """
        Compute branch NPBT from 5 input lines.
        Rule 1: NPBT=None when any input missing.
        """
        components = [inputs.nii, inputs.non_interest_income,
                      inputs.opex_direct, inputs.opex_allocated, inputs.impairment]
        missing = [name for name, val in zip(
            ["nii", "non_interest_income", "opex_direct",
             "opex_allocated", "impairment"], components) if val is None]
        if missing:
            return {
                "branch_id": inputs.branch_id,
                "npbt": None,
                "computed": False,
                "missing_inputs": missing,
            }
        # NPBT = NII + Non-Int Income - OpEx Direct - OpEx Allocated - Impairment
        npbt = (inputs.nii + inputs.non_interest_income
                - inputs.opex_direct - inputs.opex_allocated
                - inputs.impairment)
        total_income = inputs.nii + inputs.non_interest_income
        total_opex = inputs.opex_direct + inputs.opex_allocated
        return {
            "branch_id": inputs.branch_id,
            "nii": str(inputs.nii),
            "non_interest_income": str(inputs.non_interest_income),
            "total_income": str(total_income),
            "opex_direct": str(inputs.opex_direct),
            "opex_allocated": str(inputs.opex_allocated),
            "total_opex": str(total_opex),
            "impairment": str(inputs.impairment),
            "npbt": str(npbt),
            "computed": True,
        }

    @staticmethod
    def cost_income_ratio(
        total_opex: Optional[Decimal],
        total_income: Optional[Decimal],
    ) -> Optional[Decimal]:
        """
        Cost/Income ratio = total_opex / total_income × 100.
        Rule 1: None when total_income=0 or missing.
        """
        if total_opex is None or total_income is None or total_income <= 0:
            return None
        return (total_opex / total_income) * Decimal("100")

    @staticmethod
    def return_on_avg_assets(
        npbt: Optional[Decimal],
        avg_assets: Optional[Decimal],
    ) -> Optional[Decimal]:
        """ROAA = NPBT / avg_assets × 100. Rule 1: None when avg_assets=0."""
        if npbt is None or avg_assets is None or avg_assets <= 0:
            return None
        return (npbt / avg_assets) * Decimal("100")

    @staticmethod
    def quartile_rank(
        branch_value: Optional[Decimal],
        peer_values: List[Decimal],
    ) -> Dict[str, Any]:
        """
        Rank a branch into TIER_1..TIER_4 against peer group.
        Rule 1: tier=None when peer_values empty or branch_value missing.
        """
        if branch_value is None:
            return {"tier": None, "percentile": None,
                    "reason": "missing_branch_value"}
        if not peer_values:
            return {"tier": None, "percentile": None,
                    "reason": "empty_peer_group"}
        # Rank: count how many peer values are <= branch_value
        below_or_equal = sum(1 for v in peer_values if v <= branch_value)
        percentile = Decimal(below_or_equal) / Decimal(len(peer_values)) * Decimal("100")
        if percentile >= TIER_1_THRESHOLD_PCT:
            tier = "TIER_1"
        elif percentile >= TIER_2_THRESHOLD_PCT:
            tier = "TIER_2"
        elif percentile >= TIER_3_THRESHOLD_PCT:
            tier = "TIER_3"
        else:
            tier = "TIER_4"
        return {
            "branch_value": str(branch_value),
            "peer_count": len(peer_values),
            "percentile": str(percentile.quantize(Decimal("0.01"))),
            "tier": tier,
        }

    @staticmethod
    def peer_benchmark_metrics(
        peer_values: List[Decimal],
    ) -> Dict[str, Any]:
        """
        Compute p25/median/p75 of a peer group.
        Rule 1: all None when peer_values empty.
        """
        if not peer_values:
            return {
                "percentile_25": None,
                "median": None,
                "percentile_75": None,
                "n": 0,
                "reason": "empty_peer_group",
            }
        sorted_vals = sorted(peer_values)
        n = len(sorted_vals)

        def _pctile(p: Decimal) -> Decimal:
            # Simple position-based percentile (no interpolation)
            idx = int((p / Decimal("100")) * Decimal(n - 1))
            idx = max(0, min(idx, n - 1))
            return sorted_vals[idx]

        return {
            "percentile_25": str(_pctile(Decimal("25"))),
            "median": str(_pctile(Decimal("50"))),
            "percentile_75": str(_pctile(Decimal("75"))),
            "n": n,
        }

    @staticmethod
    def lifecycle_stage(years_open: Optional[int]) -> Optional[str]:
        """Classify branch by age into NEW/GROWTH/MATURE.
        Rule 1: None when years_open missing.
        """
        if years_open is None or years_open < 0:
            return None
        for stage, (lo, hi) in LIFECYCLE_BANDS_YEARS.items():
            if lo <= years_open < hi:
                return stage
        return None


# ============================================================================
# Self-tests
# ============================================================================

def _test_pnl_lines_byte_for_byte():
    expected = ("NII", "NON_INTEREST_INCOME", "OPEX_DIRECT",
                "OPEX_ALLOCATED", "IMPAIRMENT", "NPBT")
    for l in expected:
        assert l in BRANCH_PNL_LINES
    assert len(BRANCH_PNL_LINES) == 6


def _test_tiers_byte_for_byte():
    expected = ("TIER_1", "TIER_2", "TIER_3", "TIER_4")
    for t in expected:
        assert t in PERFORMANCE_TIERS
    assert len(PERFORMANCE_TIERS) == 4


def _test_thresholds_byte_for_byte():
    assert TIER_1_THRESHOLD_PCT == Decimal("75")
    assert TIER_2_THRESHOLD_PCT == Decimal("50")
    assert TIER_3_THRESHOLD_PCT == Decimal("25")


def _test_lifecycle_stages_byte_for_byte():
    expected = ("NEW", "GROWTH", "MATURE")
    for s in expected:
        assert s in BRANCH_LIFECYCLE_STAGES


def _test_lifecycle_bands_byte_for_byte():
    assert LIFECYCLE_BANDS_YEARS["NEW"] == (0, 2)
    assert LIFECYCLE_BANDS_YEARS["GROWTH"] == (2, 5)
    assert LIFECYCLE_BANDS_YEARS["MATURE"] == (5, 999)


def _test_peer_group_locations_byte_for_byte():
    expected = ("TIER_1_CITIES", "TIER_2_CITIES", "RURAL")
    for l in expected:
        assert l in PEER_GROUP_LOCATIONS


def _test_peer_group_sizes_byte_for_byte():
    expected = ("LARGE", "MEDIUM", "SMALL")
    for s in expected:
        assert s in PEER_GROUP_SIZES


def _test_benchmark_percentiles_byte_for_byte():
    expected = ("PERCENTILE_25", "MEDIAN", "PERCENTILE_75")
    for p in expected:
        assert p in BENCHMARK_PERCENTILES


def _test_branch_pnl_full():
    """NII=100, NII_other=20, OpExD=40, OpExA=20, Imp=10 → NPBT=50."""
    r = BranchPerformanceEngine.branch_pnl(BranchPnlInputs(
        branch_id="B1",
        nii=Decimal("100"),
        non_interest_income=Decimal("20"),
        opex_direct=Decimal("40"),
        opex_allocated=Decimal("20"),
        impairment=Decimal("10"),
    ))
    assert r["computed"] is True
    assert r["npbt"] == "50"
    assert r["total_income"] == "120"
    assert r["total_opex"] == "60"


def _test_branch_pnl_missing_input_rule1():
    r = BranchPerformanceEngine.branch_pnl(BranchPnlInputs(
        branch_id="B1",
        nii=Decimal("100"),
        # non_interest_income missing
        opex_direct=Decimal("40"),
        opex_allocated=Decimal("20"),
        impairment=Decimal("10"),
    ))
    assert r["computed"] is False
    assert "non_interest_income" in r["missing_inputs"]


def _test_cost_income_ratio_basic():
    """60/120 × 100 = 50%."""
    r = BranchPerformanceEngine.cost_income_ratio(Decimal("60"), Decimal("120"))
    assert r == Decimal("50")


def _test_cost_income_ratio_zero_income_rule1():
    r = BranchPerformanceEngine.cost_income_ratio(Decimal("60"), Decimal("0"))
    assert r is None


def _test_cost_income_ratio_missing_rule1():
    r = BranchPerformanceEngine.cost_income_ratio(None, Decimal("120"))
    assert r is None


def _test_roaa_basic():
    """50 / 1000 × 100 = 5%."""
    r = BranchPerformanceEngine.return_on_avg_assets(Decimal("50"), Decimal("1000"))
    assert r == Decimal("5")


def _test_roaa_zero_assets_rule1():
    r = BranchPerformanceEngine.return_on_avg_assets(Decimal("50"), Decimal("0"))
    assert r is None


def _test_quartile_top():
    """Branch value 100, peers [10, 20, 30, 40, 50, 60, 70, 80, 90, 95]
    Branch beats all 10 → 100th percentile → TIER_1.
    """
    r = BranchPerformanceEngine.quartile_rank(
        Decimal("100"),
        [Decimal(str(x)) for x in [10, 20, 30, 40, 50, 60, 70, 80, 90, 95]],
    )
    assert r["tier"] == "TIER_1"


def _test_quartile_middle():
    """Branch value 60, peers [10, 20, 30, 40, 50, 60, 70, 80, 90, 95]
    Beats or equals 6 of 10 → 60th percentile → TIER_2 (>=50%).
    """
    r = BranchPerformanceEngine.quartile_rank(
        Decimal("60"),
        [Decimal(str(x)) for x in [10, 20, 30, 40, 50, 60, 70, 80, 90, 95]],
    )
    assert r["tier"] == "TIER_2"


def _test_quartile_bottom():
    """Branch value 5, peers [10..95] → 0% → TIER_4."""
    r = BranchPerformanceEngine.quartile_rank(
        Decimal("5"),
        [Decimal(str(x)) for x in [10, 20, 30, 40, 50, 60, 70, 80, 90, 95]],
    )
    assert r["tier"] == "TIER_4"


def _test_quartile_empty_peer_group_rule1():
    r = BranchPerformanceEngine.quartile_rank(Decimal("50"), [])
    assert r["tier"] is None


def _test_quartile_missing_branch_value():
    r = BranchPerformanceEngine.quartile_rank(None, [Decimal("50")])
    assert r["tier"] is None


def _test_peer_benchmark_metrics():
    """Peers [10, 20, 30, 40, 50, 60, 70, 80, 90, 100]."""
    r = BranchPerformanceEngine.peer_benchmark_metrics(
        [Decimal(str(x)) for x in [10, 20, 30, 40, 50, 60, 70, 80, 90, 100]])
    assert r["n"] == 10
    # All percentiles defined
    assert r["percentile_25"] is not None
    assert r["median"] is not None
    assert r["percentile_75"] is not None


def _test_peer_benchmark_empty_rule1():
    r = BranchPerformanceEngine.peer_benchmark_metrics([])
    assert r["n"] == 0
    assert r["median"] is None


def _test_lifecycle_new():
    assert BranchPerformanceEngine.lifecycle_stage(0) == "NEW"
    assert BranchPerformanceEngine.lifecycle_stage(1) == "NEW"


def _test_lifecycle_growth():
    assert BranchPerformanceEngine.lifecycle_stage(2) == "GROWTH"
    assert BranchPerformanceEngine.lifecycle_stage(4) == "GROWTH"


def _test_lifecycle_mature():
    assert BranchPerformanceEngine.lifecycle_stage(5) == "MATURE"
    assert BranchPerformanceEngine.lifecycle_stage(20) == "MATURE"


def _test_lifecycle_missing_rule1():
    assert BranchPerformanceEngine.lifecycle_stage(None) is None
    assert BranchPerformanceEngine.lifecycle_stage(-1) is None


def self_test() -> bool:
    tests = [
        _test_pnl_lines_byte_for_byte,
        _test_tiers_byte_for_byte,
        _test_thresholds_byte_for_byte,
        _test_lifecycle_stages_byte_for_byte,
        _test_lifecycle_bands_byte_for_byte,
        _test_peer_group_locations_byte_for_byte,
        _test_peer_group_sizes_byte_for_byte,
        _test_benchmark_percentiles_byte_for_byte,
        _test_branch_pnl_full,
        _test_branch_pnl_missing_input_rule1,
        _test_cost_income_ratio_basic,
        _test_cost_income_ratio_zero_income_rule1,
        _test_cost_income_ratio_missing_rule1,
        _test_roaa_basic,
        _test_roaa_zero_assets_rule1,
        _test_quartile_top,
        _test_quartile_middle,
        _test_quartile_bottom,
        _test_quartile_empty_peer_group_rule1,
        _test_quartile_missing_branch_value,
        _test_peer_benchmark_metrics,
        _test_peer_benchmark_empty_rule1,
        _test_lifecycle_new,
        _test_lifecycle_growth,
        _test_lifecycle_mature,
        _test_lifecycle_missing_rule1,
    ]
    print("=" * 60)
    print("Branch Performance Engine — Self-Tests (#94)")
    print("=" * 60)
    failed = 0
    for t in tests:
        try:
            t()
            print(f"  PASS  {t.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"  FAIL  {t.__name__}: {e}")
        except Exception as e:
            failed += 1
            print(f"  ERROR {t.__name__}: {e}")
    print("-" * 60)
    if failed == 0:
        print(f"  ALL {len(tests)} TESTS PASSED")
        return True
    print(f"  {failed}/{len(tests)} FAILED")
    return False


if __name__ == "__main__":
    import sys
    sys.exit(0 if self_test() else 1)
