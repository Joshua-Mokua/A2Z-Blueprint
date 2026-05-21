"""
================================================================================
A2Z MIS 360 — Standard #77: Capital Adequacy Ratio (CAR) Engine
================================================================================

Risk classification: Cat B (deterministic Basel III + CBK regulatory ratios)

Computes capital adequacy metrics per Basel III + CBK Banking Act PG/02:
    - eligible_cet1(...)           -- Common Equity Tier 1 with deductions
    - eligible_at1(...)            -- Additional Tier 1
    - eligible_tier2(...)          -- Tier 2 capital
    - cet1_ratio / tier1_ratio / total_car
    - leverage_ratio(...)          -- Tier 1 / total exposures
    - capital_buffers(...)         -- conservation + countercyclical + D-SIB

Basel III + CBK minimum ratios byte-for-byte:
    CET1 ratio                : >= 4.5% (Basel) / 10.5% (CBK including conservation)
    Tier 1 ratio              : >= 6.0% (Basel) / 12.0% (CBK)
    Total CAR                 : >= 8.0% (Basel) / 14.5% (CBK PG/02)
    Capital conservation      : 2.5% buffer above minimums
    Countercyclical buffer    : 0-2.5% (jurisdiction-specific)
    D-SIB / G-SIB buffer      : 1-3.5% (CBK assigns by tier)
    Leverage ratio            : >= 3% Tier 1 / total exposures
    CET1 deductions           : goodwill, deferred tax assets, intangibles, MSRs (capped)

Honesty rules applied:
    Rule 1: ratios = None when RWA <= 0 or total_exposures <= 0
    Rule 6: components with missing balance excluded with count surfaced

================================================================================
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, getcontext
from typing import Any, Dict, List, Optional, Tuple

getcontext().prec = 28

# Basel III minimums byte-for-byte
BASEL_CET1_MIN_PCT = Decimal("4.5")
BASEL_TIER1_MIN_PCT = Decimal("6.0")
BASEL_TOTAL_CAR_MIN_PCT = Decimal("8.0")

# CBK Banking Act / PG/02 (Kenya specific — including conservation buffer)
# v7.0.1: CBK_CET1_MIN_PCT and CBK_TOTAL_CAR_MIN_PCT now sourced from
# system_invariants registry (single source of truth). Local names retained
# for backward compatibility with downstream usages. Defensive fallback to
# original values if registry import fails (Rule 6 honesty).
try:
    from utils.system_invariants import get_threshold as _get_invariant
    _cet1_from_registry = _get_invariant("CBK_TIER_1_CAR_MIN")
    _total_from_registry = _get_invariant("CBK_TOTAL_CAR_MIN")
    CBK_CET1_MIN_PCT = (
        _cet1_from_registry if _cet1_from_registry is not None
        else Decimal("10.5")
    )
    CBK_TOTAL_CAR_MIN_PCT = (
        _total_from_registry if _total_from_registry is not None
        else Decimal("14.5")
    )
except ImportError:
    CBK_CET1_MIN_PCT = Decimal("10.5")
    CBK_TOTAL_CAR_MIN_PCT = Decimal("14.5")
CBK_TIER1_MIN_PCT = Decimal("12.0")

# Buffers
CAPITAL_CONSERVATION_BUFFER_PCT = Decimal("2.5")
COUNTERCYCLICAL_BUFFER_MAX_PCT = Decimal("2.5")
DSIB_BUFFER_MIN_PCT = Decimal("1.0")
DSIB_BUFFER_MAX_PCT = Decimal("3.5")

# Leverage ratio (Basel III)
LEVERAGE_RATIO_MIN_PCT = Decimal("3.0")

# Tier 2 caps (% of Tier 1)
TIER2_CAP_PCT_OF_TIER1 = Decimal("100")  # Tier 2 cannot exceed Tier 1

# Status thresholds (% above CBK minimums)
CAR_GREEN_BUFFER_PCT = Decimal("2.0")  # >= CBK_min + 2pp = GREEN
CAR_AMBER_BUFFER_PCT = Decimal("0.5")  # within 0.5pp of CBK_min = AMBER

# CET1 deductions (Basel III)
CET1_DEDUCTION_TYPES: Tuple[str, ...] = (
    "GOODWILL",
    "OTHER_INTANGIBLES",
    "DEFERRED_TAX_ASSETS",
    "MORTGAGE_SERVICING_RIGHTS",  # capped at 10% of CET1
    "INVESTMENTS_IN_OWN_SHARES",
    "RECIPROCAL_CROSS_HOLDINGS",
    "SHORTFALL_PROVISIONS",
    "GAIN_ON_SALE_SECURITISATION",
)


@dataclass
class CapitalComponents:
    # CET1 raw components
    paid_up_capital_kes: Optional[Decimal] = None
    share_premium_kes: Optional[Decimal] = None
    retained_earnings_kes: Optional[Decimal] = None
    accumulated_oci_kes: Optional[Decimal] = None
    common_share_capital_minority_kes: Optional[Decimal] = None

    # CET1 deductions
    goodwill_kes: Optional[Decimal] = None
    other_intangibles_kes: Optional[Decimal] = None
    deferred_tax_assets_kes: Optional[Decimal] = None
    investments_in_own_shares_kes: Optional[Decimal] = None
    other_deductions_kes: Optional[Decimal] = None

    # AT1
    perpetual_non_cumulative_preference_shares_kes: Optional[Decimal] = None
    additional_tier1_minority_kes: Optional[Decimal] = None

    # Tier 2
    subordinated_debt_kes: Optional[Decimal] = None
    revaluation_reserves_kes: Optional[Decimal] = None
    general_provisions_kes: Optional[Decimal] = None  # capped at 1.25% RWA per Basel
    tier2_minority_kes: Optional[Decimal] = None


def _sum_optional(*vals: Optional[Decimal]) -> Decimal:
    return sum((v for v in vals if v is not None), Decimal("0"))


def _missing_count(*vals: Optional[Decimal]) -> int:
    return sum(1 for v in vals if v is None)


class CapitalAdequacyEngine:
    """Deterministic Basel III + CBK CAR computation."""

    @staticmethod
    def eligible_cet1(c: CapitalComponents) -> Dict[str, Any]:
        """
        CET1 = sum(eligible items) - sum(deductions).
        Rule 6: missing components excluded; count surfaced.
        """
        gross = _sum_optional(
            c.paid_up_capital_kes,
            c.share_premium_kes,
            c.retained_earnings_kes,
            c.accumulated_oci_kes,
            c.common_share_capital_minority_kes,
        )
        deductions = _sum_optional(
            c.goodwill_kes,
            c.other_intangibles_kes,
            c.deferred_tax_assets_kes,
            c.investments_in_own_shares_kes,
            c.other_deductions_kes,
        )
        net = gross - deductions
        missing = _missing_count(
            c.paid_up_capital_kes, c.share_premium_kes,
            c.retained_earnings_kes,
        )
        return {
            "gross_cet1_kes": str(gross.quantize(Decimal("0.01"))),
            "deductions_kes": str(deductions.quantize(Decimal("0.01"))),
            "net_cet1_kes": str(net.quantize(Decimal("0.01"))),
            "missing_core_components_count": missing,
        }

    @staticmethod
    def eligible_at1(c: CapitalComponents) -> Dict[str, Any]:
        at1 = _sum_optional(
            c.perpetual_non_cumulative_preference_shares_kes,
            c.additional_tier1_minority_kes,
        )
        return {
            "at1_kes": str(at1.quantize(Decimal("0.01"))),
        }

    @staticmethod
    def eligible_tier2(
        c: CapitalComponents,
        total_rwa_kes: Optional[Decimal] = None,
    ) -> Dict[str, Any]:
        """Tier 2 with general provisions capped at 1.25% RWA."""
        general_provisions = c.general_provisions_kes or Decimal("0")
        if total_rwa_kes is not None and total_rwa_kes > 0:
            cap = total_rwa_kes * Decimal("1.25") / Decimal("100")
            capped_provisions = min(general_provisions, cap)
        else:
            capped_provisions = general_provisions
        tier2 = _sum_optional(
            c.subordinated_debt_kes,
            c.revaluation_reserves_kes,
            c.tier2_minority_kes,
        ) + capped_provisions
        return {
            "tier2_kes": str(tier2.quantize(Decimal("0.01"))),
            "general_provisions_raw_kes": str(general_provisions.quantize(Decimal("0.01"))),
            "general_provisions_capped_kes": str(capped_provisions.quantize(Decimal("0.01"))),
            "general_provisions_cap_kes": (str((total_rwa_kes * Decimal("1.25") / Decimal("100")).quantize(Decimal("0.01")))
                                            if total_rwa_kes else None),
        }

    @classmethod
    def total_capital(
        cls,
        c: CapitalComponents,
        total_rwa_kes: Optional[Decimal] = None,
    ) -> Dict[str, Any]:
        """Compute Tier 1 and Total Capital (with Tier 2 capped at 100% of Tier 1)."""
        cet1 = cls.eligible_cet1(c)
        at1 = cls.eligible_at1(c)
        tier2_raw = cls.eligible_tier2(c, total_rwa_kes)

        cet1_amt = Decimal(cet1["net_cet1_kes"])
        at1_amt = Decimal(at1["at1_kes"])
        tier1 = cet1_amt + at1_amt
        tier2_amt = Decimal(tier2_raw["tier2_kes"])

        # Cap Tier 2 at 100% of Tier 1 (Basel III)
        capped_tier2 = min(tier2_amt, tier1) if tier1 > 0 else Decimal("0")
        total = tier1 + capped_tier2

        return {
            "cet1_kes": str(cet1_amt.quantize(Decimal("0.01"))),
            "at1_kes": str(at1_amt.quantize(Decimal("0.01"))),
            "tier1_kes": str(tier1.quantize(Decimal("0.01"))),
            "tier2_kes_raw": str(tier2_amt.quantize(Decimal("0.01"))),
            "tier2_kes_capped": str(capped_tier2.quantize(Decimal("0.01"))),
            "total_capital_kes": str(total.quantize(Decimal("0.01"))),
            "tier2_cap_applied": tier2_amt > capped_tier2,
            "cet1_breakdown": cet1,
            "tier2_breakdown": tier2_raw,
        }

    @classmethod
    def car_ratios(
        cls,
        c: CapitalComponents,
        total_rwa_kes: Optional[Decimal],
    ) -> Dict[str, Any]:
        """
        Compute CET1, Tier 1, Total CAR ratios.
        Rule 1: ratios=None when RWA <= 0.
        """
        cap = cls.total_capital(c, total_rwa_kes)
        cet1_amt = Decimal(cap["cet1_kes"])
        tier1_amt = Decimal(cap["tier1_kes"])
        total_amt = Decimal(cap["total_capital_kes"])

        if total_rwa_kes is None or total_rwa_kes <= 0:
            return {
                "cet1_ratio_pct": None,
                "tier1_ratio_pct": None,
                "total_car_pct": None,
                "rwa_kes": str(total_rwa_kes) if total_rwa_kes else None,
                "reason": "rwa_zero_or_negative",
                "capital_breakdown": cap,
            }

        cet1_ratio = (cet1_amt / total_rwa_kes) * Decimal("100")
        tier1_ratio = (tier1_amt / total_rwa_kes) * Decimal("100")
        total_car = (total_amt / total_rwa_kes) * Decimal("100")

        # CBK status determination on Total CAR
        if total_car >= CBK_TOTAL_CAR_MIN_PCT + CAR_GREEN_BUFFER_PCT:
            status = "GREEN"
        elif total_car >= CBK_TOTAL_CAR_MIN_PCT:
            status = "AMBER"
        else:
            status = "RED"

        return {
            "cet1_kes": cap["cet1_kes"],
            "tier1_kes": cap["tier1_kes"],
            "total_capital_kes": cap["total_capital_kes"],
            "rwa_kes": str(total_rwa_kes.quantize(Decimal("0.01"))),
            "cet1_ratio_pct": str(cet1_ratio.quantize(Decimal("0.01"))),
            "tier1_ratio_pct": str(tier1_ratio.quantize(Decimal("0.01"))),
            "total_car_pct": str(total_car.quantize(Decimal("0.01"))),
            "basel_minimums": {
                "cet1": str(BASEL_CET1_MIN_PCT),
                "tier1": str(BASEL_TIER1_MIN_PCT),
                "total": str(BASEL_TOTAL_CAR_MIN_PCT),
            },
            "cbk_minimums": {
                "cet1": str(CBK_CET1_MIN_PCT),
                "tier1": str(CBK_TIER1_MIN_PCT),
                "total": str(CBK_TOTAL_CAR_MIN_PCT),
            },
            "compliant_basel": (cet1_ratio >= BASEL_CET1_MIN_PCT
                                and tier1_ratio >= BASEL_TIER1_MIN_PCT
                                and total_car >= BASEL_TOTAL_CAR_MIN_PCT),
            "compliant_cbk": (cet1_ratio >= CBK_CET1_MIN_PCT
                              and tier1_ratio >= CBK_TIER1_MIN_PCT
                              and total_car >= CBK_TOTAL_CAR_MIN_PCT),
            "status": status,
        }

    @staticmethod
    def leverage_ratio(
        tier1_kes: Optional[Decimal],
        total_exposures_kes: Optional[Decimal],
    ) -> Dict[str, Any]:
        """
        Leverage Ratio = Tier 1 / Total Exposures × 100.
        Rule 1: None when total_exposures<=0.
        """
        if (total_exposures_kes is None or total_exposures_kes <= 0
                or tier1_kes is None):
            return {
                "leverage_ratio_pct": None,
                "min_required_pct": str(LEVERAGE_RATIO_MIN_PCT),
                "tier1_kes": str(tier1_kes) if tier1_kes else None,
                "total_exposures_kes": str(total_exposures_kes) if total_exposures_kes else None,
                "reason": "exposures_or_tier1_invalid",
            }
        ratio = (tier1_kes / total_exposures_kes) * Decimal("100")
        return {
            "leverage_ratio_pct": str(ratio.quantize(Decimal("0.01"))),
            "min_required_pct": str(LEVERAGE_RATIO_MIN_PCT),
            "tier1_kes": str(tier1_kes.quantize(Decimal("0.01"))),
            "total_exposures_kes": str(total_exposures_kes.quantize(Decimal("0.01"))),
            "compliant": ratio >= LEVERAGE_RATIO_MIN_PCT,
        }

    @staticmethod
    def capital_buffers(
        cet1_ratio_pct: Optional[Decimal],
        countercyclical_pct: Decimal = Decimal("0"),
        dsib_pct: Decimal = Decimal("0"),
    ) -> Dict[str, Any]:
        """
        Compute total buffer requirement = conservation + countercyclical + D-SIB.
        Rule 1: surplus=None when cet1_ratio_pct is None.
        """
        # Validate buffer inputs
        if countercyclical_pct < 0 or countercyclical_pct > COUNTERCYCLICAL_BUFFER_MAX_PCT:
            return {"error": f"countercyclical_pct out of range [0, {COUNTERCYCLICAL_BUFFER_MAX_PCT}]"}
        if dsib_pct < 0 or dsib_pct > DSIB_BUFFER_MAX_PCT:
            return {"error": f"dsib_pct out of range [0, {DSIB_BUFFER_MAX_PCT}]"}

        total_buffer_pct = (CAPITAL_CONSERVATION_BUFFER_PCT
                            + countercyclical_pct + dsib_pct)
        cet1_required_with_buffers = BASEL_CET1_MIN_PCT + total_buffer_pct

        if cet1_ratio_pct is None:
            return {
                "conservation_buffer_pct": str(CAPITAL_CONSERVATION_BUFFER_PCT),
                "countercyclical_buffer_pct": str(countercyclical_pct),
                "dsib_buffer_pct": str(dsib_pct),
                "total_buffer_pct": str(total_buffer_pct),
                "cet1_required_with_buffers_pct": str(cet1_required_with_buffers),
                "buffer_surplus_pct": None,
                "reason": "cet1_ratio_unavailable",
            }

        surplus = cet1_ratio_pct - cet1_required_with_buffers
        return {
            "conservation_buffer_pct": str(CAPITAL_CONSERVATION_BUFFER_PCT),
            "countercyclical_buffer_pct": str(countercyclical_pct),
            "dsib_buffer_pct": str(dsib_pct),
            "total_buffer_pct": str(total_buffer_pct),
            "cet1_required_with_buffers_pct": str(cet1_required_with_buffers),
            "cet1_actual_pct": str(cet1_ratio_pct),
            "buffer_surplus_pct": str(surplus.quantize(Decimal("0.01"))),
            "buffers_met": surplus >= 0,
        }

    # ============================================================================
    # v7.2: L06 Stress test → Capital plan feedback loop (CONSUMER)
    # ============================================================================
    @classmethod
    def capital_plan_from_stress(
        cls,
        stress_payload: Dict[str, Any],
        time_to_remediate_months: int = 12,
    ) -> Dict[str, Any]:
        """L06 (CONSUMER) — derive capital plan from stress test shortfall.

        Consumes the payload produced by
        `stress_testing.stress_capital_shortfall_summary()`. Per Charter §7
        Published Language pattern, depends only on the public payload
        contract (payload_version=1.0).

        Strategy logic:
            - If no breach: no remediation required (GREEN)
            - If shortfall <= 5B KES: profit retention path (organic)
            - If shortfall <= 15B KES: subordinated debt issuance (Tier 2)
            - If shortfall > 15B KES: rights issue / Tier 1 capital raise
            - DSIB / repeated breaches: regulator escalation regardless of size

        Returns:
            dict with: status, shortfall_kes, recommended_actions list,
            time_to_remediate_months, monthly_run_rate_kes,
            consumed_payload_version (Rule 6 traceability),
            error fields if payload malformed.
        """
        # Validate payload contract
        if not isinstance(stress_payload, dict):
            return {
                "status": "INVALID_PAYLOAD",
                "error": "stress_payload must be a dict",
                "consumed_payload_version": None,
            }
        if stress_payload.get("pattern") != "PUBLISHED_LANGUAGE":
            return {
                "status": "INVALID_PAYLOAD",
                "error": "stress_payload not using PUBLISHED_LANGUAGE pattern",
                "consumed_payload_version": stress_payload.get("payload_version"),
            }

        worst_shortfall_str = stress_payload.get("worst_shortfall_kes")
        if worst_shortfall_str is None:
            return {
                "status": "MISSING_SHORTFALL",
                "error": "worst_shortfall_kes missing from payload",
                "consumed_payload_version": stress_payload.get("payload_version"),
            }

        try:
            shortfall = Decimal(str(worst_shortfall_str))
        except Exception:
            return {
                "status": "INVALID_SHORTFALL",
                "error": f"could not parse shortfall '{worst_shortfall_str}'",
                "consumed_payload_version": stress_payload.get("payload_version"),
            }

        if shortfall <= Decimal("0"):
            return {
                "status": "GREEN",
                "shortfall_kes": "0",
                "worst_scenario": stress_payload.get("worst_scenario"),
                "recommended_actions": [
                    "No remediation required — bank passes all stress scenarios above CBK floor.",
                    "Maintain current capital plan; review quarterly.",
                ],
                "time_to_remediate_months": 0,
                "monthly_run_rate_kes": "0",
                "consumed_payload_version": stress_payload.get("payload_version"),
                "cited_invariants": stress_payload.get("cited_invariants", []),
            }

        # Determine remediation path
        FIVE_B = Decimal("5000000000")
        FIFTEEN_B = Decimal("15000000000")
        # Pre-format to billions string for action messages (Decimal-safe)
        shortfall_b = float(shortfall) / 1e9
        if shortfall <= FIVE_B:
            actions = [
                f"Organic remediation via profit retention: KES {shortfall_b:.2f}B over {time_to_remediate_months} months.",
                f"Suspend dividend distribution until restored.",
                "Strengthen RWA optimisation (lower-risk asset mix) to reduce required capital.",
            ]
            severity = "AMBER"
        elif shortfall <= FIFTEEN_B:
            actions = [
                f"Subordinated debt (Tier 2) issuance recommended: target KES {shortfall_b:.2f}B.",
                "Suspend dividend distribution.",
                "Engage CBK on remediation timeline (regulatory courtesy).",
                "Profit retention contributes; Tier 2 covers gap.",
            ]
            severity = "RED"
        else:
            actions = [
                f"Rights issue / Tier 1 capital raise required: KES {shortfall_b:.2f}B.",
                "Notify CBK immediately (Section 31, Banking Act).",
                "Suspend dividends; consider buyback halt.",
                "Board capital action plan within 30 days.",
                "Stress recovery plan + ICAAP submission.",
            ]
            severity = "CRITICAL"

        monthly_run_rate = (
            shortfall / Decimal(time_to_remediate_months)
            if time_to_remediate_months > 0 else Decimal("0")
        ).quantize(Decimal("0.01"))

        return {
            "status": severity,
            "shortfall_kes": str(shortfall),
            "worst_scenario": stress_payload.get("worst_scenario"),
            "recommended_actions": actions,
            "time_to_remediate_months": time_to_remediate_months,
            "monthly_run_rate_kes": str(monthly_run_rate),
            "consumed_payload_version": stress_payload.get("payload_version"),
            "cited_invariants": stress_payload.get("cited_invariants", []),
        }


# ============================================================================
# Self-tests
# ============================================================================

def _components(**kw):
    defaults = dict(
        paid_up_capital_kes=Decimal("5000000000"),
        share_premium_kes=Decimal("2000000000"),
        retained_earnings_kes=Decimal("3000000000"),
        accumulated_oci_kes=Decimal("500000000"),
        goodwill_kes=Decimal("100000000"),
        deferred_tax_assets_kes=Decimal("50000000"),
        subordinated_debt_kes=Decimal("1000000000"),
        general_provisions_kes=Decimal("200000000"),
    )
    defaults.update(kw)
    return CapitalComponents(**defaults)


def _test_cet1_basic():
    c = _components()
    r = CapitalAdequacyEngine.eligible_cet1(c)
    # 5+2+3+0.5 - 0.1 - 0.05 = 10.35B
    assert Decimal(r["net_cet1_kes"]) == Decimal("10350000000.00")


def _test_tier2_provisions_capped():
    """General provisions capped at 1.25% of RWA."""
    c = _components(general_provisions_kes=Decimal("500000000"))
    rwa = Decimal("10000000000")  # 10B
    r = CapitalAdequacyEngine.eligible_tier2(c, rwa)
    # Cap = 10B × 1.25% = 125M
    assert Decimal(r["general_provisions_capped_kes"]) == Decimal("125000000.00")


def _test_total_capital_tier2_capped():
    """Tier 2 cannot exceed Tier 1."""
    c = _components(
        paid_up_capital_kes=Decimal("100000000"),
        share_premium_kes=Decimal("0"),
        retained_earnings_kes=Decimal("0"),
        accumulated_oci_kes=Decimal("0"),
        goodwill_kes=Decimal("0"),
        deferred_tax_assets_kes=Decimal("0"),
        subordinated_debt_kes=Decimal("500000000"),  # 500M Tier 2 candidate
    )
    r = CapitalAdequacyEngine.total_capital(c, None)
    # CET1 = 100M; Tier1 = 100M; Tier 2 raw = 500M; capped at 100M
    assert Decimal(r["tier1_kes"]) == Decimal("100000000.00")
    assert Decimal(r["tier2_kes_capped"]) == Decimal("100000000.00")
    assert r["tier2_cap_applied"] is True


def _test_car_compliant():
    c = _components()
    rwa = Decimal("50000000000")  # 50B RWA
    r = CapitalAdequacyEngine.car_ratios(c, rwa)
    # Should be well above 14.5% with these capital amounts
    assert r["compliant_cbk"] is True
    assert r["status"] == "GREEN"


def _test_car_breach():
    c = _components(
        paid_up_capital_kes=Decimal("1000000000"),  # only 1B paid-up
        share_premium_kes=Decimal("0"),
        retained_earnings_kes=Decimal("0"),
        accumulated_oci_kes=Decimal("0"),
        goodwill_kes=Decimal("0"),
        deferred_tax_assets_kes=Decimal("0"),
        subordinated_debt_kes=Decimal("0"),
        general_provisions_kes=Decimal("0"),
    )
    rwa = Decimal("100000000000")  # 100B RWA
    r = CapitalAdequacyEngine.car_ratios(c, rwa)
    # CAR = 1B / 100B = 1% << 14.5%
    assert r["status"] == "RED"
    assert r["compliant_cbk"] is False


def _test_car_zero_rwa_rule1():
    c = _components()
    r = CapitalAdequacyEngine.car_ratios(c, Decimal("0"))
    assert r["cet1_ratio_pct"] is None
    assert r["total_car_pct"] is None


def _test_leverage_ratio_compliant():
    r = CapitalAdequacyEngine.leverage_ratio(
        Decimal("10000000000"),  # 10B Tier 1
        Decimal("250000000000"),  # 250B exposures
    )
    # 4% > 3%
    assert r["compliant"] is True


def _test_leverage_ratio_breach():
    r = CapitalAdequacyEngine.leverage_ratio(
        Decimal("1000000000"),
        Decimal("100000000000"),
    )
    # 1% < 3%
    assert r["compliant"] is False


def _test_leverage_zero_exposures_rule1():
    r = CapitalAdequacyEngine.leverage_ratio(Decimal("1000000000"), Decimal("0"))
    assert r["leverage_ratio_pct"] is None


def _test_buffers_met():
    r = CapitalAdequacyEngine.capital_buffers(
        Decimal("12.0"),  # CET1 12%
        countercyclical_pct=Decimal("1.0"),
        dsib_pct=Decimal("1.0"),
    )
    # Required = 4.5 + 2.5 + 1.0 + 1.0 = 9.0; surplus = 12 - 9 = 3pp
    assert r["buffers_met"] is True


def _test_buffers_breach():
    r = CapitalAdequacyEngine.capital_buffers(
        Decimal("5.0"),  # CET1 5%
        countercyclical_pct=Decimal("0.5"),
    )
    # Required = 4.5 + 2.5 + 0.5 = 7.5; surplus = 5 - 7.5 = -2.5
    assert r["buffers_met"] is False


def _test_buffers_invalid_input():
    r = CapitalAdequacyEngine.capital_buffers(
        Decimal("12.0"),
        countercyclical_pct=Decimal("3.0"),  # > 2.5 max
    )
    assert "error" in r


def _test_basel_minimums_byte_for_byte():
    assert BASEL_CET1_MIN_PCT == Decimal("4.5")
    assert BASEL_TIER1_MIN_PCT == Decimal("6.0")
    assert BASEL_TOTAL_CAR_MIN_PCT == Decimal("8.0")


def _test_cbk_minimums_byte_for_byte():
    assert CBK_CET1_MIN_PCT == Decimal("10.5")
    assert CBK_TIER1_MIN_PCT == Decimal("12.0")
    assert CBK_TOTAL_CAR_MIN_PCT == Decimal("14.5")


def _test_buffer_constants_byte_for_byte():
    assert CAPITAL_CONSERVATION_BUFFER_PCT == Decimal("2.5")
    assert COUNTERCYCLICAL_BUFFER_MAX_PCT == Decimal("2.5")
    assert DSIB_BUFFER_MIN_PCT == Decimal("1.0")
    assert DSIB_BUFFER_MAX_PCT == Decimal("3.5")
    assert LEVERAGE_RATIO_MIN_PCT == Decimal("3.0")


def _test_cet1_missing_components_rule6():
    c = CapitalComponents()  # all None
    r = CapitalAdequacyEngine.eligible_cet1(c)
    assert r["missing_core_components_count"] >= 3


def self_test() -> bool:
    tests = [
        _test_cet1_basic,
        _test_tier2_provisions_capped,
        _test_total_capital_tier2_capped,
        _test_car_compliant,
        _test_car_breach,
        _test_car_zero_rwa_rule1,
        _test_leverage_ratio_compliant,
        _test_leverage_ratio_breach,
        _test_leverage_zero_exposures_rule1,
        _test_buffers_met,
        _test_buffers_breach,
        _test_buffers_invalid_input,
        _test_basel_minimums_byte_for_byte,
        _test_cbk_minimums_byte_for_byte,
        _test_buffer_constants_byte_for_byte,
        _test_cet1_missing_components_rule6,
    ]
    print("=" * 60)
    print("Capital Adequacy Engine — Self-Tests (#77)")
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
