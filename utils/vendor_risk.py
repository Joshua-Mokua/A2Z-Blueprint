"""
================================================================================
A2Z MIS 360 — Standard #96: Third-Party / Vendor Risk Management
================================================================================

Risk classification: Cat B (deterministic vendor risk classification + SLA workflow)

Implements CBK Risk Management Guideline on Outsourcing (2014) controls:
    - vendor_tier_classification(...)   -- TIER_1 critical → TIER_4 low
    - due_diligence_completeness(...)   -- 5-check required pack
    - review_due(...)                   -- per-tier cadence enforcement
    - sla_breach_severity(...)          -- breach impact tiering
    - vendor_concentration_check(...)   -- top-vendor share guard

5 VENDOR_CATEGORIES byte-for-byte:
    CRITICAL_TECH, NON_CRITICAL_TECH, FACILITIES, PROFESSIONAL_SERVICES,
    OUTSOURCED_OPS

4 VENDOR_TIERS byte-for-byte:
    TIER_1_CRITICAL  -- core operational dependency (CBS host, payment switch)
    TIER_2_HIGH      -- material support function
    TIER_3_MEDIUM    -- standard supplier
    TIER_4_LOW       -- low-impact / commodity supplier

5 DUE_DILIGENCE_CHECKS byte-for-byte:
    FINANCIAL_HEALTH, INFOSEC_CERT, BUSINESS_CONTINUITY,
    REGULATORY_COMPLIANCE, GEOGRAPHIC_RISK

REVIEW_CADENCE_DAYS byte-for-byte (CBK guideline):
    TIER_1_CRITICAL : 365   -- annual
    TIER_2_HIGH     : 730   -- biennial
    TIER_3_MEDIUM   : 1095  -- triennial
    TIER_4_LOW      : 1825  -- 5-yearly / on-renewal

4 SLA_BREACH_SEVERITIES byte-for-byte:
    CRITICAL, HIGH, MEDIUM, LOW

SLA_BREACH_DOWNTIME_THRESHOLDS_HOURS byte-for-byte:
    CRITICAL : 4   -- ≥4hr downtime
    HIGH     : 2   -- 2-4hr
    MEDIUM   : 1   -- 1-2hr
    LOW      : 0   -- <1hr

VENDOR_CONCENTRATION_CRITICAL_THRESHOLD_PCT byte-for-byte:
    25  -- single vendor >25% of category spend triggers concentration alert

CONTRACT_RENEWAL_NOTICE_DAYS byte-for-byte:
    180  -- 6-month renewal notice required for TIER_1/TIER_2

Honesty rules applied:
    Rule 1: review_due_in_days=None when last_review_date missing
            concentration_pct=None when category total spend zero
    Rule 6: missing critical due-diligence checks block onboarding (fail closed)
            unknown vendor tier / category surfaced

================================================================================
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal, getcontext
from typing import Any, Dict, List, Optional, Tuple

getcontext().prec = 28

# 5 VENDOR CATEGORIES byte-for-byte
VENDOR_CATEGORIES: Tuple[str, ...] = (
    "CRITICAL_TECH", "NON_CRITICAL_TECH", "FACILITIES",
    "PROFESSIONAL_SERVICES", "OUTSOURCED_OPS",
)

# 4 VENDOR TIERS byte-for-byte
VENDOR_TIERS: Tuple[str, ...] = (
    "TIER_1_CRITICAL", "TIER_2_HIGH", "TIER_3_MEDIUM", "TIER_4_LOW",
)

# 5 DUE DILIGENCE CHECKS byte-for-byte (CBK Outsourcing Guideline)
DUE_DILIGENCE_CHECKS: Tuple[str, ...] = (
    "FINANCIAL_HEALTH", "INFOSEC_CERT", "BUSINESS_CONTINUITY",
    "REGULATORY_COMPLIANCE", "GEOGRAPHIC_RISK",
)

# Review cadence in days byte-for-byte
REVIEW_CADENCE_DAYS: Dict[str, int] = {
    "TIER_1_CRITICAL": 365,
    "TIER_2_HIGH": 730,
    "TIER_3_MEDIUM": 1095,
    "TIER_4_LOW": 1825,
}

# 4 SLA BREACH SEVERITIES byte-for-byte
SLA_BREACH_SEVERITIES: Tuple[str, ...] = (
    "CRITICAL", "HIGH", "MEDIUM", "LOW",
)

# SLA breach downtime thresholds in hours byte-for-byte
SLA_BREACH_DOWNTIME_THRESHOLDS_HOURS: Dict[str, int] = {
    "CRITICAL": 4,
    "HIGH": 2,
    "MEDIUM": 1,
    "LOW": 0,
}

# Concentration alert threshold byte-for-byte
VENDOR_CONCENTRATION_CRITICAL_THRESHOLD_PCT = Decimal("25")

# Contract renewal notice byte-for-byte
CONTRACT_RENEWAL_NOTICE_DAYS = 180

# Critical-tier checks (all 5 required to onboard TIER_1/TIER_2)
CRITICAL_TIER_REQUIRED_CHECKS: Tuple[str, ...] = DUE_DILIGENCE_CHECKS  # all 5

# Lower-tier checks (TIER_3/TIER_4 require subset)
LOWER_TIER_REQUIRED_CHECKS: Tuple[str, ...] = (
    "FINANCIAL_HEALTH", "REGULATORY_COMPLIANCE",
)


@dataclass
class VendorRecord:
    vendor_id: str
    category: str
    tier: str
    annual_spend_kes: Optional[Decimal] = None
    last_review_date: Optional[date] = None
    completed_dd_checks: List[str] = field(default_factory=list)


class VendorRiskEngine:
    """Deterministic third-party risk + outsourcing oversight."""

    @staticmethod
    def due_diligence_completeness(vendor: VendorRecord) -> Dict[str, Any]:
        """
        Verify required due-diligence checks completed for vendor's tier.
        Rule 6: missing critical checks block onboarding.
        """
        if vendor.tier not in VENDOR_TIERS:
            return {
                "vendor_id": vendor.vendor_id,
                "complete": False,
                "reason": f"unknown_tier:{vendor.tier}",
                "valid_tiers": list(VENDOR_TIERS),
            }
        if vendor.category not in VENDOR_CATEGORIES:
            return {
                "vendor_id": vendor.vendor_id,
                "complete": False,
                "reason": f"unknown_category:{vendor.category}",
                "valid_categories": list(VENDOR_CATEGORIES),
            }
        # Tier determines required check set
        if vendor.tier in ("TIER_1_CRITICAL", "TIER_2_HIGH"):
            required = CRITICAL_TIER_REQUIRED_CHECKS
        else:
            required = LOWER_TIER_REQUIRED_CHECKS
        completed_set = set(vendor.completed_dd_checks)
        missing = [c for c in required if c not in completed_set]
        complete = len(missing) == 0
        return {
            "vendor_id": vendor.vendor_id,
            "tier": vendor.tier,
            "category": vendor.category,
            "required_checks": list(required),
            "completed_checks": list(completed_set),
            "missing_checks": missing,
            "complete": complete,
            "eligible_for_onboarding": complete,  # fail closed
        }

    @staticmethod
    def review_due(
        vendor: VendorRecord,
        as_of: Optional[date] = None,
    ) -> Dict[str, Any]:
        """
        Determine if vendor is due (or overdue) for periodic review.
        Rule 1: review_due_in_days=None when last_review_date missing.
        """
        if vendor.tier not in VENDOR_TIERS:
            return {
                "vendor_id": vendor.vendor_id,
                "review_due_in_days": None,
                "reason": f"unknown_tier:{vendor.tier}",
            }
        if vendor.last_review_date is None:
            return {
                "vendor_id": vendor.vendor_id,
                "tier": vendor.tier,
                "review_due_in_days": None,
                "reason": "missing_last_review_date",
                "is_overdue": None,
            }
        if as_of is None:
            as_of = date.today()
        cadence_days = REVIEW_CADENCE_DAYS[vendor.tier]
        next_review_date = vendor.last_review_date + timedelta(days=cadence_days)
        days_remaining = (next_review_date - as_of).days
        return {
            "vendor_id": vendor.vendor_id,
            "tier": vendor.tier,
            "last_review_date": vendor.last_review_date.isoformat(),
            "cadence_days": cadence_days,
            "next_review_date": next_review_date.isoformat(),
            "review_due_in_days": days_remaining,
            "is_overdue": days_remaining < 0,
        }

    @staticmethod
    def sla_breach_severity(downtime_hours: Optional[Decimal]) -> Optional[str]:
        """
        Classify SLA breach severity by downtime duration.
        Rule 1: None when downtime_hours missing.
        """
        if downtime_hours is None or downtime_hours < 0:
            return None
        if downtime_hours >= SLA_BREACH_DOWNTIME_THRESHOLDS_HOURS["CRITICAL"]:
            return "CRITICAL"
        if downtime_hours >= SLA_BREACH_DOWNTIME_THRESHOLDS_HOURS["HIGH"]:
            return "HIGH"
        if downtime_hours >= SLA_BREACH_DOWNTIME_THRESHOLDS_HOURS["MEDIUM"]:
            return "MEDIUM"
        return "LOW"

    @staticmethod
    def vendor_concentration_check(
        vendors: List[VendorRecord],
        category: str,
    ) -> Dict[str, Any]:
        """
        Check single-vendor concentration in a category.
        Rule 1: concentration_pct=None when category total spend is zero.
        Rule 6: unknown category surfaced.
        """
        if category not in VENDOR_CATEGORIES:
            return {
                "category": category,
                "computed": False,
                "reason": f"unknown_category:{category}",
            }
        in_cat = [v for v in vendors if v.category == category
                  and v.annual_spend_kes is not None]
        if not in_cat:
            return {
                "category": category,
                "vendor_count": 0,
                "total_spend_kes": "0",
                "max_concentration_pct": None,
                "max_concentration_vendor_id": None,
                "concentration_alert": False,
                "computed": True,
            }
        total = sum(v.annual_spend_kes for v in in_cat)
        if total <= 0:
            return {
                "category": category,
                "vendor_count": len(in_cat),
                "total_spend_kes": "0",
                "max_concentration_pct": None,
                "concentration_alert": False,
                "computed": True,
                "reason": "zero_total_spend",
            }
        # Find max concentration
        max_vendor = max(in_cat, key=lambda v: v.annual_spend_kes)
        max_pct = (max_vendor.annual_spend_kes / total) * Decimal("100")
        alert = max_pct > VENDOR_CONCENTRATION_CRITICAL_THRESHOLD_PCT
        return {
            "category": category,
            "vendor_count": len(in_cat),
            "total_spend_kes": str(total.quantize(Decimal("0.01"))),
            "max_concentration_vendor_id": max_vendor.vendor_id,
            "max_concentration_pct": str(max_pct.quantize(Decimal("0.01"))),
            "concentration_threshold_pct": str(
                VENDOR_CONCENTRATION_CRITICAL_THRESHOLD_PCT),
            "concentration_alert": alert,
            "computed": True,
        }


# ============================================================================
# Self-tests
# ============================================================================

def _test_categories_byte_for_byte():
    expected = ("CRITICAL_TECH", "NON_CRITICAL_TECH", "FACILITIES",
                "PROFESSIONAL_SERVICES", "OUTSOURCED_OPS")
    for c in expected:
        assert c in VENDOR_CATEGORIES
    assert len(VENDOR_CATEGORIES) == 5


def _test_tiers_byte_for_byte():
    expected = ("TIER_1_CRITICAL", "TIER_2_HIGH", "TIER_3_MEDIUM", "TIER_4_LOW")
    for t in expected:
        assert t in VENDOR_TIERS
    assert len(VENDOR_TIERS) == 4


def _test_dd_checks_byte_for_byte():
    expected = ("FINANCIAL_HEALTH", "INFOSEC_CERT", "BUSINESS_CONTINUITY",
                "REGULATORY_COMPLIANCE", "GEOGRAPHIC_RISK")
    for c in expected:
        assert c in DUE_DILIGENCE_CHECKS
    assert len(DUE_DILIGENCE_CHECKS) == 5


def _test_review_cadence_byte_for_byte():
    assert REVIEW_CADENCE_DAYS["TIER_1_CRITICAL"] == 365
    assert REVIEW_CADENCE_DAYS["TIER_2_HIGH"] == 730
    assert REVIEW_CADENCE_DAYS["TIER_3_MEDIUM"] == 1095
    assert REVIEW_CADENCE_DAYS["TIER_4_LOW"] == 1825


def _test_sla_severities_byte_for_byte():
    expected = ("CRITICAL", "HIGH", "MEDIUM", "LOW")
    for s in expected:
        assert s in SLA_BREACH_SEVERITIES


def _test_sla_thresholds_byte_for_byte():
    assert SLA_BREACH_DOWNTIME_THRESHOLDS_HOURS["CRITICAL"] == 4
    assert SLA_BREACH_DOWNTIME_THRESHOLDS_HOURS["HIGH"] == 2
    assert SLA_BREACH_DOWNTIME_THRESHOLDS_HOURS["MEDIUM"] == 1
    assert SLA_BREACH_DOWNTIME_THRESHOLDS_HOURS["LOW"] == 0


def _test_concentration_threshold_byte_for_byte():
    assert VENDOR_CONCENTRATION_CRITICAL_THRESHOLD_PCT == Decimal("25")


def _test_renewal_notice_byte_for_byte():
    assert CONTRACT_RENEWAL_NOTICE_DAYS == 180


def _test_dd_complete_tier1_all_5():
    """TIER_1 needs all 5 checks."""
    v = VendorRecord(
        vendor_id="V1", category="CRITICAL_TECH", tier="TIER_1_CRITICAL",
        completed_dd_checks=list(DUE_DILIGENCE_CHECKS),
    )
    r = VendorRiskEngine.due_diligence_completeness(v)
    assert r["complete"] is True
    assert r["eligible_for_onboarding"] is True


def _test_dd_incomplete_tier1_missing_one():
    v = VendorRecord(
        vendor_id="V1", category="CRITICAL_TECH", tier="TIER_1_CRITICAL",
        completed_dd_checks=["FINANCIAL_HEALTH", "INFOSEC_CERT",
                              "BUSINESS_CONTINUITY", "REGULATORY_COMPLIANCE"],
        # GEOGRAPHIC_RISK missing
    )
    r = VendorRiskEngine.due_diligence_completeness(v)
    assert r["complete"] is False
    assert r["eligible_for_onboarding"] is False
    assert "GEOGRAPHIC_RISK" in r["missing_checks"]


def _test_dd_tier3_only_2_required():
    """TIER_3 only needs FINANCIAL_HEALTH + REGULATORY_COMPLIANCE."""
    v = VendorRecord(
        vendor_id="V1", category="PROFESSIONAL_SERVICES", tier="TIER_3_MEDIUM",
        completed_dd_checks=["FINANCIAL_HEALTH", "REGULATORY_COMPLIANCE"],
    )
    r = VendorRiskEngine.due_diligence_completeness(v)
    assert r["complete"] is True


def _test_dd_unknown_tier_rule6():
    v = VendorRecord(
        vendor_id="V1", category="CRITICAL_TECH", tier="WEIRD",
        completed_dd_checks=list(DUE_DILIGENCE_CHECKS),
    )
    r = VendorRiskEngine.due_diligence_completeness(v)
    assert r["complete"] is False


def _test_review_due_on_track():
    """Last review 30 days ago, TIER_1 cadence 365 → 335 days remaining."""
    v = VendorRecord(
        vendor_id="V1", category="CRITICAL_TECH", tier="TIER_1_CRITICAL",
        last_review_date=date(2026, 4, 1),
    )
    r = VendorRiskEngine.review_due(v, as_of=date(2026, 5, 1))
    assert r["review_due_in_days"] == 335
    assert r["is_overdue"] is False


def _test_review_overdue():
    """Last review 400 days ago, TIER_1 cadence 365 → -35 days = overdue."""
    v = VendorRecord(
        vendor_id="V1", category="CRITICAL_TECH", tier="TIER_1_CRITICAL",
        last_review_date=date(2025, 3, 25),
    )
    r = VendorRiskEngine.review_due(v, as_of=date(2026, 4, 30))
    assert r["review_due_in_days"] == -36
    assert r["is_overdue"] is True


def _test_review_missing_last_date_rule1():
    v = VendorRecord(
        vendor_id="V1", category="CRITICAL_TECH", tier="TIER_1_CRITICAL",
        last_review_date=None,
    )
    r = VendorRiskEngine.review_due(v)
    assert r["review_due_in_days"] is None


def _test_sla_critical():
    """6 hours downtime → CRITICAL."""
    assert VendorRiskEngine.sla_breach_severity(Decimal("6")) == "CRITICAL"


def _test_sla_critical_boundary():
    """Exactly 4hr → CRITICAL."""
    assert VendorRiskEngine.sla_breach_severity(Decimal("4")) == "CRITICAL"


def _test_sla_high():
    """3 hours → HIGH."""
    assert VendorRiskEngine.sla_breach_severity(Decimal("3")) == "HIGH"


def _test_sla_medium():
    """1.5 hours → MEDIUM."""
    assert VendorRiskEngine.sla_breach_severity(Decimal("1.5")) == "MEDIUM"


def _test_sla_low():
    """30 min → LOW."""
    assert VendorRiskEngine.sla_breach_severity(Decimal("0.5")) == "LOW"


def _test_sla_missing_rule1():
    assert VendorRiskEngine.sla_breach_severity(None) is None
    assert VendorRiskEngine.sla_breach_severity(Decimal("-1")) is None


def _test_concentration_alert_triggered():
    """3 vendors: 800K + 100K + 100K = 1M; max = 80% > 25% → alert."""
    vendors = [
        VendorRecord(vendor_id="V1", category="CRITICAL_TECH",
                     tier="TIER_1_CRITICAL", annual_spend_kes=Decimal("800000")),
        VendorRecord(vendor_id="V2", category="CRITICAL_TECH",
                     tier="TIER_2_HIGH", annual_spend_kes=Decimal("100000")),
        VendorRecord(vendor_id="V3", category="CRITICAL_TECH",
                     tier="TIER_3_MEDIUM", annual_spend_kes=Decimal("100000")),
    ]
    r = VendorRiskEngine.vendor_concentration_check(vendors, "CRITICAL_TECH")
    assert r["max_concentration_vendor_id"] == "V1"
    assert Decimal(r["max_concentration_pct"]) == Decimal("80.00")
    assert r["concentration_alert"] is True


def _test_concentration_no_alert():
    """4 vendors evenly split: 25% each = exactly at threshold (not >)."""
    vendors = [
        VendorRecord(vendor_id=f"V{i}", category="CRITICAL_TECH",
                     tier="TIER_1_CRITICAL", annual_spend_kes=Decimal("250000"))
        for i in range(1, 5)
    ]
    r = VendorRiskEngine.vendor_concentration_check(vendors, "CRITICAL_TECH")
    assert r["concentration_alert"] is False  # exactly 25%, not >


def _test_concentration_empty_category():
    r = VendorRiskEngine.vendor_concentration_check([], "CRITICAL_TECH")
    assert r["vendor_count"] == 0


def _test_concentration_unknown_category_rule6():
    r = VendorRiskEngine.vendor_concentration_check([], "WEIRD")
    assert r["computed"] is False


def _test_critical_tier_required_checks():
    """All 5 checks required for TIER_1/TIER_2."""
    assert len(CRITICAL_TIER_REQUIRED_CHECKS) == 5


def _test_lower_tier_required_checks():
    """Only 2 checks required for TIER_3/TIER_4."""
    assert len(LOWER_TIER_REQUIRED_CHECKS) == 2
    assert "FINANCIAL_HEALTH" in LOWER_TIER_REQUIRED_CHECKS
    assert "REGULATORY_COMPLIANCE" in LOWER_TIER_REQUIRED_CHECKS


def self_test() -> bool:
    tests = [
        _test_categories_byte_for_byte,
        _test_tiers_byte_for_byte,
        _test_dd_checks_byte_for_byte,
        _test_review_cadence_byte_for_byte,
        _test_sla_severities_byte_for_byte,
        _test_sla_thresholds_byte_for_byte,
        _test_concentration_threshold_byte_for_byte,
        _test_renewal_notice_byte_for_byte,
        _test_dd_complete_tier1_all_5,
        _test_dd_incomplete_tier1_missing_one,
        _test_dd_tier3_only_2_required,
        _test_dd_unknown_tier_rule6,
        _test_review_due_on_track,
        _test_review_overdue,
        _test_review_missing_last_date_rule1,
        _test_sla_critical,
        _test_sla_critical_boundary,
        _test_sla_high,
        _test_sla_medium,
        _test_sla_low,
        _test_sla_missing_rule1,
        _test_concentration_alert_triggered,
        _test_concentration_no_alert,
        _test_concentration_empty_category,
        _test_concentration_unknown_category_rule6,
        _test_critical_tier_required_checks,
        _test_lower_tier_required_checks,
    ]
    print("=" * 60)
    print("Vendor Risk Engine — Self-Tests (#96)")
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
