"""
================================================================================
A2Z MIS 360 — Standard #85: Management Reporting Pack Generator
================================================================================

Risk classification: Cat B (deterministic monthly/weekly MIS pack assembly)

Generates management information packs (MIS) for ExCo / ManCo / Dept Heads:
    - generate_monthly_mis_pack(...)        -- 10-section monthly pack
    - generate_weekly_executive_flash(...)  -- 4-section weekly flash
    - validate_section_completeness(...)    -- pre-distribution validation
    - distribution_list(...)                -- recipients per pack type

10 MONTHLY_MIS_SECTIONS byte-for-byte (Banking sector standard):
    EXECUTIVE_SUMMARY, FINANCIAL_HIGHLIGHTS, BALANCE_SHEET, INCOME_STATEMENT,
    KPI_DASHBOARD, BRANCH_PERFORMANCE, RISK_INDICATORS, COMPLIANCE_STATUS,
    HR_METRICS, IT_OPERATIONS

4 WEEKLY_FLASH_SECTIONS byte-for-byte:
    EXECUTIVE_SUMMARY, KEY_KPIS, RISK_ALERTS, ACTION_ITEMS

3 PACK_FREQUENCIES byte-for-byte: MONTHLY, WEEKLY, AD_HOC

3 DISTRIBUTION_TIERS byte-for-byte: EXCO, MANCO, DEPARTMENT_HEADS

Completeness thresholds:
    EXCO_MIN_COMPLETE_PCT = 100  (executive: zero tolerance)
    MANCO_MIN_COMPLETE_PCT = 90  (90% of sections required)
    DEPT_MIN_COMPLETE_PCT = 80   (80% of sections required)

Honesty rules applied:
    Rule 1: completeness_pct=None when no sections (denominator zero)
    Rule 6: missing required sections surfaced in `missing_sections[]`;
            pack NOT distributed if completeness < tier minimum (fail closed)

================================================================================
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, getcontext
from typing import Any, Dict, List, Optional, Tuple

getcontext().prec = 28

# 10 MONTHLY MIS sections byte-for-byte
MONTHLY_MIS_SECTIONS: Tuple[str, ...] = (
    "EXECUTIVE_SUMMARY",
    "FINANCIAL_HIGHLIGHTS",
    "BALANCE_SHEET",
    "INCOME_STATEMENT",
    "KPI_DASHBOARD",
    "BRANCH_PERFORMANCE",
    "RISK_INDICATORS",
    "COMPLIANCE_STATUS",
    "HR_METRICS",
    "IT_OPERATIONS",
)

# 4 WEEKLY FLASH sections byte-for-byte
WEEKLY_FLASH_SECTIONS: Tuple[str, ...] = (
    "EXECUTIVE_SUMMARY",
    "KEY_KPIS",
    "RISK_ALERTS",
    "ACTION_ITEMS",
)

# 3 PACK FREQUENCIES byte-for-byte
PACK_FREQUENCIES: Tuple[str, ...] = ("MONTHLY", "WEEKLY", "AD_HOC")

# 3 DISTRIBUTION TIERS byte-for-byte
DISTRIBUTION_TIERS: Tuple[str, ...] = ("EXCO", "MANCO", "DEPARTMENT_HEADS")

# Completeness thresholds byte-for-byte
EXCO_MIN_COMPLETE_PCT = Decimal("100")
MANCO_MIN_COMPLETE_PCT = Decimal("90")
DEPT_MIN_COMPLETE_PCT = Decimal("80")

# Lead time SLAs (days before period-end + this many days = distribution)
MONTHLY_PACK_LEAD_DAYS = 5    # within 5 days of month-end
WEEKLY_FLASH_LEAD_DAYS = 1    # within 1 day of Friday close


@dataclass
class MisSection:
    section_id: str
    title: str
    populated: bool = False
    has_data_quality_issues: bool = False
    last_updated: Optional[date] = None


class ManagementReportingEngine:
    """Deterministic MIS pack generation with completeness validation."""

    @staticmethod
    def generate_monthly_mis_pack(
        reporting_period_end: Optional[date],
        sections: List[MisSection],
        target_tier: str = "EXCO",
    ) -> Dict[str, Any]:
        """
        Build a monthly MIS pack with completeness validation.
        Rule 6: missing sections surfaced; pack not distributed if below tier min.
        """
        if reporting_period_end is None:
            return {
                "pack_type": "MONTHLY",
                "generated": False,
                "validation_errors": ["missing_reporting_period_end"],
            }
        if target_tier not in DISTRIBUTION_TIERS:
            return {
                "pack_type": "MONTHLY",
                "generated": False,
                "validation_errors": [f"unknown_tier:{target_tier}"],
                "valid_tiers": list(DISTRIBUTION_TIERS),
            }

        # Compute completeness
        section_ids_provided = {s.section_id for s in sections}
        present_sections = [s for s in sections if s.populated]
        missing_sections = [
            s for s in MONTHLY_MIS_SECTIONS if s not in section_ids_provided
            or not any(x.section_id == s and x.populated for x in sections)
        ]
        unpopulated = [s.section_id for s in sections
                       if s.section_id in MONTHLY_MIS_SECTIONS and not s.populated]
        with_quality_issues = [s.section_id for s in sections if s.has_data_quality_issues]

        total_required = len(MONTHLY_MIS_SECTIONS)
        # Rule 1: shouldn't happen since constant > 0, but defend
        if total_required <= 0:
            return {
                "pack_type": "MONTHLY",
                "generated": False,
                "completeness_pct": None,
                "reason": "no_required_sections_defined",
            }

        populated_required_count = sum(
            1 for s in MONTHLY_MIS_SECTIONS
            if any(x.section_id == s and x.populated for x in sections)
        )
        completeness_pct = (
            Decimal(populated_required_count) / Decimal(total_required) * Decimal("100")
        )

        # Determine min threshold per tier
        min_pct = {
            "EXCO": EXCO_MIN_COMPLETE_PCT,
            "MANCO": MANCO_MIN_COMPLETE_PCT,
            "DEPARTMENT_HEADS": DEPT_MIN_COMPLETE_PCT,
        }[target_tier]

        # Fail-closed for distribution
        eligible_for_distribution = completeness_pct >= min_pct

        return {
            "pack_type": "MONTHLY",
            "frequency": "MONTHLY",
            "reporting_period_end": reporting_period_end.isoformat(),
            "target_tier": target_tier,
            "required_sections_count": total_required,
            "populated_required_count": populated_required_count,
            "completeness_pct": str(completeness_pct.quantize(Decimal("0.01"))),
            "min_required_pct": str(min_pct),
            "missing_sections": missing_sections,
            "unpopulated_sections": unpopulated,
            "sections_with_quality_issues": with_quality_issues,
            "eligible_for_distribution": eligible_for_distribution,
            "generated": True,
        }

    @staticmethod
    def generate_weekly_executive_flash(
        reporting_week_end: Optional[date],
        sections: List[MisSection],
    ) -> Dict[str, Any]:
        """Weekly flash for ExCo. Always EXCO tier. Rule 6 fail-closed."""
        if reporting_week_end is None:
            return {
                "pack_type": "WEEKLY",
                "generated": False,
                "validation_errors": ["missing_reporting_week_end"],
            }

        section_ids_provided = {s.section_id for s in sections}
        missing_sections = [
            s for s in WEEKLY_FLASH_SECTIONS if s not in section_ids_provided
            or not any(x.section_id == s and x.populated for x in sections)
        ]
        total_required = len(WEEKLY_FLASH_SECTIONS)
        populated_required_count = sum(
            1 for s in WEEKLY_FLASH_SECTIONS
            if any(x.section_id == s and x.populated for x in sections)
        )
        completeness_pct = (
            Decimal(populated_required_count) / Decimal(total_required) * Decimal("100")
        )

        # Weekly flash is EXCO-tier — 100% threshold
        eligible_for_distribution = completeness_pct >= EXCO_MIN_COMPLETE_PCT

        return {
            "pack_type": "WEEKLY",
            "frequency": "WEEKLY",
            "reporting_week_end": reporting_week_end.isoformat(),
            "target_tier": "EXCO",
            "required_sections_count": total_required,
            "populated_required_count": populated_required_count,
            "completeness_pct": str(completeness_pct.quantize(Decimal("0.01"))),
            "min_required_pct": str(EXCO_MIN_COMPLETE_PCT),
            "missing_sections": missing_sections,
            "eligible_for_distribution": eligible_for_distribution,
            "generated": True,
        }

    @staticmethod
    def distribution_list(target_tier: str) -> Dict[str, Any]:
        """
        Return distribution recipients for a tier.
        Returns explicit list (illustrative, deterministic).
        """
        if target_tier not in DISTRIBUTION_TIERS:
            return {"error": f"unknown_tier:{target_tier}",
                    "valid_tiers": list(DISTRIBUTION_TIERS)}
        recipients = {
            "EXCO": ["MD", "Director_Retail", "Director_Commercial", "CFO", "CRO", "Company_Secretary"],
            "MANCO": ["MD", "Director_Retail", "Director_Commercial", "CFO", "CRO",
                      "Head_of_Retail", "Head_of_SME", "Head_of_Corporate", "Head_of_Operations",
                      "Head_of_HR", "Head_of_IT", "Head_of_Compliance"],
            "DEPARTMENT_HEADS": ["All_MANCO", "All_Branch_Managers", "All_Department_Heads"],
        }
        return {
            "tier": target_tier,
            "recipients": recipients[target_tier],
            "recipient_count": len(recipients[target_tier]),
        }


# ============================================================================
# Self-tests
# ============================================================================

def _full_monthly_sections():
    return [MisSection(section_id=s, title=s.replace("_", " ").title(),
                       populated=True) for s in MONTHLY_MIS_SECTIONS]


def _full_weekly_sections():
    return [MisSection(section_id=s, title=s.replace("_", " ").title(),
                       populated=True) for s in WEEKLY_FLASH_SECTIONS]


def _test_monthly_full_complete():
    r = ManagementReportingEngine.generate_monthly_mis_pack(
        date(2026, 4, 30), _full_monthly_sections(), target_tier="EXCO")
    assert r["completeness_pct"] == "100.00"
    assert r["eligible_for_distribution"] is True


def _test_monthly_below_exco_threshold():
    """Drop 1 section → 90% < 100% EXCO requirement."""
    sections = _full_monthly_sections()
    sections[0].populated = False
    r = ManagementReportingEngine.generate_monthly_mis_pack(
        date(2026, 4, 30), sections, target_tier="EXCO")
    assert Decimal(r["completeness_pct"]) == Decimal("90.00")
    assert r["eligible_for_distribution"] is False  # 90 < 100 EXCO min


def _test_monthly_meets_manco_threshold():
    """90% meets MANCO 90% min."""
    sections = _full_monthly_sections()
    sections[0].populated = False
    r = ManagementReportingEngine.generate_monthly_mis_pack(
        date(2026, 4, 30), sections, target_tier="MANCO")
    assert r["eligible_for_distribution"] is True


def _test_monthly_meets_dept_threshold():
    """80% meets DEPT 80% min."""
    sections = _full_monthly_sections()
    sections[0].populated = False
    sections[1].populated = False
    r = ManagementReportingEngine.generate_monthly_mis_pack(
        date(2026, 4, 30), sections, target_tier="DEPARTMENT_HEADS")
    assert Decimal(r["completeness_pct"]) == Decimal("80.00")
    assert r["eligible_for_distribution"] is True


def _test_monthly_missing_sections_surfaced():
    """Provide only 5 of 10 sections → missing 5 surfaced."""
    sections = _full_monthly_sections()[:5]
    r = ManagementReportingEngine.generate_monthly_mis_pack(
        date(2026, 4, 30), sections, target_tier="EXCO")
    assert len(r["missing_sections"]) == 5


def _test_monthly_missing_period_rule6():
    r = ManagementReportingEngine.generate_monthly_mis_pack(
        None, _full_monthly_sections(), target_tier="EXCO")
    assert r["generated"] is False


def _test_unknown_tier():
    r = ManagementReportingEngine.generate_monthly_mis_pack(
        date(2026, 4, 30), _full_monthly_sections(), target_tier="WEIRD")
    assert r["generated"] is False
    assert any("unknown_tier" in e for e in r["validation_errors"])


def _test_weekly_full_complete():
    r = ManagementReportingEngine.generate_weekly_executive_flash(
        date(2026, 4, 24), _full_weekly_sections())
    assert r["completeness_pct"] == "100.00"
    assert r["eligible_for_distribution"] is True


def _test_weekly_missing_section_blocks_distribution():
    """3 of 4 sections = 75% < 100% EXCO min."""
    sections = _full_weekly_sections()
    sections[0].populated = False
    r = ManagementReportingEngine.generate_weekly_executive_flash(
        date(2026, 4, 24), sections)
    assert Decimal(r["completeness_pct"]) == Decimal("75.00")
    assert r["eligible_for_distribution"] is False


def _test_distribution_list_exco():
    r = ManagementReportingEngine.distribution_list("EXCO")
    assert "MD" in r["recipients"]
    assert r["recipient_count"] >= 5


def _test_distribution_list_unknown():
    r = ManagementReportingEngine.distribution_list("WEIRD")
    assert "error" in r


def _test_monthly_sections_byte_for_byte():
    expected = (
        "EXECUTIVE_SUMMARY", "FINANCIAL_HIGHLIGHTS", "BALANCE_SHEET",
        "INCOME_STATEMENT", "KPI_DASHBOARD", "BRANCH_PERFORMANCE",
        "RISK_INDICATORS", "COMPLIANCE_STATUS", "HR_METRICS", "IT_OPERATIONS",
    )
    for s in expected:
        assert s in MONTHLY_MIS_SECTIONS
    assert len(MONTHLY_MIS_SECTIONS) == 10


def _test_weekly_sections_byte_for_byte():
    expected = ("EXECUTIVE_SUMMARY", "KEY_KPIS", "RISK_ALERTS", "ACTION_ITEMS")
    for s in expected:
        assert s in WEEKLY_FLASH_SECTIONS
    assert len(WEEKLY_FLASH_SECTIONS) == 4


def _test_frequencies_byte_for_byte():
    expected = ("MONTHLY", "WEEKLY", "AD_HOC")
    for f in expected:
        assert f in PACK_FREQUENCIES


def _test_tiers_byte_for_byte():
    expected = ("EXCO", "MANCO", "DEPARTMENT_HEADS")
    for t in expected:
        assert t in DISTRIBUTION_TIERS


def _test_thresholds_byte_for_byte():
    assert EXCO_MIN_COMPLETE_PCT == Decimal("100")
    assert MANCO_MIN_COMPLETE_PCT == Decimal("90")
    assert DEPT_MIN_COMPLETE_PCT == Decimal("80")


def _test_lead_times_byte_for_byte():
    assert MONTHLY_PACK_LEAD_DAYS == 5
    assert WEEKLY_FLASH_LEAD_DAYS == 1


def self_test() -> bool:
    tests = [
        _test_monthly_full_complete,
        _test_monthly_below_exco_threshold,
        _test_monthly_meets_manco_threshold,
        _test_monthly_meets_dept_threshold,
        _test_monthly_missing_sections_surfaced,
        _test_monthly_missing_period_rule6,
        _test_unknown_tier,
        _test_weekly_full_complete,
        _test_weekly_missing_section_blocks_distribution,
        _test_distribution_list_exco,
        _test_distribution_list_unknown,
        _test_monthly_sections_byte_for_byte,
        _test_weekly_sections_byte_for_byte,
        _test_frequencies_byte_for_byte,
        _test_tiers_byte_for_byte,
        _test_thresholds_byte_for_byte,
        _test_lead_times_byte_for_byte,
    ]
    print("=" * 60)
    print("Management Reporting Pack Generator — Self-Tests (#85)")
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
