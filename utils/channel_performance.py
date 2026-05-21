"""
================================================================================
A2Z MIS 360 — Standard #91: Channel Performance Analytics Engine
================================================================================

Risk classification: Cat B (deterministic channel economics)

Channel mix, cost-to-serve, and self-service ratio analytics:
    - cost_per_transaction(...)             -- channel unit economics
    - channel_mix_pct(...)                  -- transaction distribution by channel
    - self_service_ratio(...)               -- digital share of total volume
    - channel_availability_compliance(...)  -- uptime vs target
    - blended_cost_per_transaction(...)     -- weighted by mix

10 CHANNELS byte-for-byte:
    BRANCH, ATM, AGENT, MOBILE, INTERNET, USSD, CALL_CENTER, POS, RTGS, SWIFT

CHANNEL_COST_PER_TXN_KES byte-for-byte (illustrative bank average):
    BRANCH        : 200    (highest — staff + premises)
    ATM           : 50
    AGENT         : 30     (agent banking)
    MOBILE        : 2      (lowest — pure digital)
    INTERNET      : 5
    USSD          : 2
    CALL_CENTER   : 80
    POS           : 15
    RTGS          : 1500   (high-value interbank)
    SWIFT         : 2500   (cross-border)

3 SELF_SERVICE_CHANNELS byte-for-byte: MOBILE, INTERNET, USSD

CHANNEL_AVAILABILITY_TARGET_PCT byte-for-byte: 99.5 (industry standard)

3 CHANNEL_TIERS byte-for-byte: PHYSICAL, DIGITAL, INTERBANK

Honesty rules applied:
    Rule 1: cost_per_txn=None when txn_count <= 0
    Rule 6: unknown channel rejected with explanation

================================================================================
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, getcontext
from typing import Any, Dict, List, Optional, Tuple

getcontext().prec = 28

# 10 CHANNELS byte-for-byte
CHANNELS: Tuple[str, ...] = (
    "BRANCH", "ATM", "AGENT", "MOBILE", "INTERNET",
    "USSD", "CALL_CENTER", "POS", "RTGS", "SWIFT",
)

# Cost per transaction byte-for-byte (KES, illustrative)
CHANNEL_COST_PER_TXN_KES: Dict[str, Decimal] = {
    "BRANCH": Decimal("200"),
    "ATM": Decimal("50"),
    "AGENT": Decimal("30"),
    "MOBILE": Decimal("2"),
    "INTERNET": Decimal("5"),
    "USSD": Decimal("2"),
    "CALL_CENTER": Decimal("80"),
    "POS": Decimal("15"),
    "RTGS": Decimal("1500"),
    "SWIFT": Decimal("2500"),
}

# 3 SELF SERVICE CHANNELS byte-for-byte
SELF_SERVICE_CHANNELS: Tuple[str, ...] = ("MOBILE", "INTERNET", "USSD")

# Channel availability target byte-for-byte
CHANNEL_AVAILABILITY_TARGET_PCT = Decimal("99.5")

# 3 CHANNEL TIERS byte-for-byte
CHANNEL_TIERS: Tuple[str, ...] = ("PHYSICAL", "DIGITAL", "INTERBANK")

CHANNEL_TIER_MAP: Dict[str, str] = {
    "BRANCH": "PHYSICAL",
    "ATM": "PHYSICAL",
    "AGENT": "PHYSICAL",
    "POS": "PHYSICAL",
    "CALL_CENTER": "PHYSICAL",  # human-assisted
    "MOBILE": "DIGITAL",
    "INTERNET": "DIGITAL",
    "USSD": "DIGITAL",
    "RTGS": "INTERBANK",
    "SWIFT": "INTERBANK",
}


@dataclass
class ChannelMetrics:
    channel: str
    txn_count: Optional[int] = None
    txn_value_kes: Optional[Decimal] = None
    uptime_pct: Optional[Decimal] = None
    operating_cost_kes: Optional[Decimal] = None


class ChannelPerformanceEngine:
    """Deterministic channel economics analytics."""

    @staticmethod
    def cost_per_transaction(
        operating_cost_kes: Optional[Decimal],
        txn_count: Optional[int],
    ) -> Dict[str, Any]:
        """Rule 1: None when txn_count <= 0 or cost missing."""
        if operating_cost_kes is None:
            return {"cost_per_txn_kes": None, "reason": "missing_operating_cost"}
        if txn_count is None or txn_count <= 0:
            return {"cost_per_txn_kes": None, "reason": "zero_or_missing_txn_count"}
        cpt = operating_cost_kes / Decimal(txn_count)
        return {
            "cost_per_txn_kes": str(cpt.quantize(Decimal("0.01"))),
            "operating_cost_kes": str(operating_cost_kes),
            "txn_count": txn_count,
        }

    @staticmethod
    def channel_mix_pct(
        channel_txn_counts: Dict[str, int],
    ) -> Dict[str, Any]:
        """
        Compute % of transactions in each channel.
        Rule 1: None when total volume = 0; Rule 6: unknown channels surfaced.
        """
        if not channel_txn_counts:
            return {"mix_pct": None, "reason": "empty_channels"}
        total = sum(channel_txn_counts.values())
        if total <= 0:
            return {"mix_pct": None, "reason": "zero_total_volume"}
        unknown = [c for c in channel_txn_counts if c not in CHANNELS]
        mix = {
            c: str((Decimal(n) / Decimal(total) * Decimal("100"))
                   .quantize(Decimal("0.01")))
            for c, n in channel_txn_counts.items()
            if c in CHANNELS
        }
        return {
            "mix_pct": mix,
            "total_txn_count": total,
            "unknown_channels": unknown,
        }

    @staticmethod
    def self_service_ratio(
        channel_txn_counts: Dict[str, int],
    ) -> Dict[str, Any]:
        """
        % of total transactions on self-service channels (MOBILE/INTERNET/USSD).
        Rule 1: None when total = 0.
        """
        if not channel_txn_counts:
            return {"self_service_ratio_pct": None, "reason": "empty"}
        total = sum(n for c, n in channel_txn_counts.items() if c in CHANNELS)
        if total <= 0:
            return {"self_service_ratio_pct": None, "reason": "zero_total"}
        ss = sum(n for c, n in channel_txn_counts.items()
                 if c in SELF_SERVICE_CHANNELS)
        ratio = Decimal(ss) / Decimal(total) * Decimal("100")
        return {
            "self_service_ratio_pct": str(ratio.quantize(Decimal("0.01"))),
            "self_service_count": ss,
            "total_count": total,
            "self_service_channels": list(SELF_SERVICE_CHANNELS),
        }

    @staticmethod
    def channel_availability_compliance(
        channel: str,
        uptime_pct: Optional[Decimal],
    ) -> Dict[str, Any]:
        """Rule 1: None when uptime missing; Rule 6: unknown channel rejected."""
        if channel not in CHANNELS:
            return {"compliant": None, "reason": f"unknown_channel:{channel}",
                    "valid_channels": list(CHANNELS)}
        if uptime_pct is None:
            return {"compliant": None, "reason": "missing_uptime"}
        compliant = uptime_pct >= CHANNEL_AVAILABILITY_TARGET_PCT
        return {
            "channel": channel,
            "uptime_pct": str(uptime_pct.quantize(Decimal("0.01"))),
            "target_pct": str(CHANNEL_AVAILABILITY_TARGET_PCT),
            "compliant": compliant,
            "shortfall_pct": (str((CHANNEL_AVAILABILITY_TARGET_PCT - uptime_pct)
                                  .quantize(Decimal("0.01")))
                              if not compliant else "0.00"),
        }

    @staticmethod
    def blended_cost_per_transaction(
        channel_txn_counts: Dict[str, int],
    ) -> Dict[str, Any]:
        """
        Mix-weighted cost using CHANNEL_COST_PER_TXN_KES standard rates.
        Rule 1: None when total = 0.
        """
        if not channel_txn_counts:
            return {"blended_cost_per_txn_kes": None, "reason": "empty"}
        total = sum(n for c, n in channel_txn_counts.items() if c in CHANNELS)
        if total <= 0:
            return {"blended_cost_per_txn_kes": None, "reason": "zero_total"}
        weighted_cost = Decimal("0")
        for c, n in channel_txn_counts.items():
            if c in CHANNELS:
                weighted_cost += Decimal(n) * CHANNEL_COST_PER_TXN_KES[c]
        blended = weighted_cost / Decimal(total)
        return {
            "blended_cost_per_txn_kes": str(blended.quantize(Decimal("0.01"))),
            "total_txn_count": total,
            "total_weighted_cost_kes": str(weighted_cost),
        }


# ============================================================================
# Self-tests
# ============================================================================

def _test_channels_byte_for_byte():
    expected = ("BRANCH", "ATM", "AGENT", "MOBILE", "INTERNET",
                "USSD", "CALL_CENTER", "POS", "RTGS", "SWIFT")
    for c in expected:
        assert c in CHANNELS
    assert len(CHANNELS) == 10


def _test_channel_costs_byte_for_byte():
    assert CHANNEL_COST_PER_TXN_KES["BRANCH"] == Decimal("200")
    assert CHANNEL_COST_PER_TXN_KES["MOBILE"] == Decimal("2")
    assert CHANNEL_COST_PER_TXN_KES["ATM"] == Decimal("50")
    assert CHANNEL_COST_PER_TXN_KES["AGENT"] == Decimal("30")
    assert CHANNEL_COST_PER_TXN_KES["RTGS"] == Decimal("1500")
    assert CHANNEL_COST_PER_TXN_KES["SWIFT"] == Decimal("2500")


def _test_self_service_byte_for_byte():
    assert "MOBILE" in SELF_SERVICE_CHANNELS
    assert "INTERNET" in SELF_SERVICE_CHANNELS
    assert "USSD" in SELF_SERVICE_CHANNELS
    assert len(SELF_SERVICE_CHANNELS) == 3


def _test_availability_target_byte_for_byte():
    assert CHANNEL_AVAILABILITY_TARGET_PCT == Decimal("99.5")


def _test_channel_tiers_byte_for_byte():
    for t in ("PHYSICAL", "DIGITAL", "INTERBANK"):
        assert t in CHANNEL_TIERS


def _test_tier_map():
    assert CHANNEL_TIER_MAP["BRANCH"] == "PHYSICAL"
    assert CHANNEL_TIER_MAP["MOBILE"] == "DIGITAL"
    assert CHANNEL_TIER_MAP["RTGS"] == "INTERBANK"


def _test_cost_per_txn_basic():
    """1M cost / 100K txns = 10/txn."""
    r = ChannelPerformanceEngine.cost_per_transaction(
        Decimal("1000000"), 100000)
    assert r["cost_per_txn_kes"] == "10.00"


def _test_cost_per_txn_zero_count_rule1():
    r = ChannelPerformanceEngine.cost_per_transaction(Decimal("1000000"), 0)
    assert r["cost_per_txn_kes"] is None


def _test_cost_per_txn_missing_cost_rule1():
    r = ChannelPerformanceEngine.cost_per_transaction(None, 100)
    assert r["cost_per_txn_kes"] is None


def _test_channel_mix_basic():
    r = ChannelPerformanceEngine.channel_mix_pct({
        "BRANCH": 100, "MOBILE": 900,
    })
    assert r["mix_pct"]["BRANCH"] == "10.00"
    assert r["mix_pct"]["MOBILE"] == "90.00"


def _test_channel_mix_unknown_surfaced_rule6():
    r = ChannelPerformanceEngine.channel_mix_pct({
        "BRANCH": 100, "WEIRD": 50,
    })
    assert "WEIRD" in r["unknown_channels"]


def _test_channel_mix_zero_rule1():
    r = ChannelPerformanceEngine.channel_mix_pct({})
    assert r["mix_pct"] is None


def _test_self_service_ratio_basic():
    """800 self-service / 1000 total = 80%."""
    r = ChannelPerformanceEngine.self_service_ratio({
        "MOBILE": 600, "INTERNET": 200, "BRANCH": 200,
    })
    assert r["self_service_ratio_pct"] == "80.00"


def _test_self_service_zero_rule1():
    r = ChannelPerformanceEngine.self_service_ratio({})
    assert r["self_service_ratio_pct"] is None


def _test_availability_compliant():
    """99.7% > 99.5% target → compliant."""
    r = ChannelPerformanceEngine.channel_availability_compliance(
        "MOBILE", Decimal("99.7"))
    assert r["compliant"] is True


def _test_availability_non_compliant():
    """98% < 99.5% → not compliant; shortfall 1.5pp."""
    r = ChannelPerformanceEngine.channel_availability_compliance(
        "ATM", Decimal("98.0"))
    assert r["compliant"] is False
    assert r["shortfall_pct"] == "1.50"


def _test_availability_unknown_channel_rule6():
    r = ChannelPerformanceEngine.channel_availability_compliance(
        "WEIRD", Decimal("99.7"))
    assert r["compliant"] is None


def _test_availability_missing_rule1():
    r = ChannelPerformanceEngine.channel_availability_compliance("MOBILE", None)
    assert r["compliant"] is None


def _test_blended_cost_per_txn():
    """500 BRANCH (200) + 500 MOBILE (2) = 100,000 + 1,000 = 101,000 / 1000 = 101."""
    r = ChannelPerformanceEngine.blended_cost_per_transaction({
        "BRANCH": 500, "MOBILE": 500,
    })
    assert r["blended_cost_per_txn_kes"] == "101.00"


def _test_blended_cost_zero_rule1():
    r = ChannelPerformanceEngine.blended_cost_per_transaction({})
    assert r["blended_cost_per_txn_kes"] is None


def self_test() -> bool:
    tests = [
        _test_channels_byte_for_byte,
        _test_channel_costs_byte_for_byte,
        _test_self_service_byte_for_byte,
        _test_availability_target_byte_for_byte,
        _test_channel_tiers_byte_for_byte,
        _test_tier_map,
        _test_cost_per_txn_basic,
        _test_cost_per_txn_zero_count_rule1,
        _test_cost_per_txn_missing_cost_rule1,
        _test_channel_mix_basic,
        _test_channel_mix_unknown_surfaced_rule6,
        _test_channel_mix_zero_rule1,
        _test_self_service_ratio_basic,
        _test_self_service_zero_rule1,
        _test_availability_compliant,
        _test_availability_non_compliant,
        _test_availability_unknown_channel_rule6,
        _test_availability_missing_rule1,
        _test_blended_cost_per_txn,
        _test_blended_cost_zero_rule1,
    ]
    print("=" * 60)
    print("Channel Performance Engine — Self-Tests (#91)")
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
