"""
================================================================================
A2Z MIS 360 — Standard #86: Board Reporting Pack Generator
================================================================================

Risk classification: Cat B (deterministic quarterly/monthly board pack assembly)

Generates board pack per CMA Code of Corporate Governance + Banking Act:
    - generate_board_pack(...)              -- 12-section quarterly board pack
    - generate_committee_pack(...)          -- sub-committee specific pack
    - validate_lead_time(...)               -- 14-day distribution rule
    - committee_section_mapping(...)        -- which sections to which committee

12 BOARD_PACK_SECTIONS byte-for-byte (CMA Code + Banking Act):
    COVER_LETTER, STRATEGIC_UPDATE, FINANCIAL_PERFORMANCE, RISK_REPORT,
    COMPLIANCE_REPORT, AUDIT_REPORT, HR_REPORT, IT_CYBER_REPORT,
    CUSTOMER_EXPERIENCE, SUSTAINABILITY_ESG, BOARD_RESOLUTIONS, APPENDICES

5 BOARD_COMMITTEES byte-for-byte (typical bank governance):
    BOARD_AUDIT_COMMITTEE, BOARD_RISK_COMMITTEE, BOARD_CREDIT_COMMITTEE,
    BOARD_NOMINATIONS_COMMITTEE, BOARD_STRATEGY_COMMITTEE

3 BOARD_FREQUENCIES byte-for-byte: QUARTERLY, MONTHLY, EXTRAORDINARY

CMA Code lead time: distribution required >= 14 days before meeting date.

Required completeness for board distribution: 100% (all 12 sections must be
populated and approved).

Honesty rules applied:
    Rule 1: lead_days_until_meeting=None when meeting_date missing
    Rule 6: missing sections surfaced; pack NOT distributed if completeness<100%
            or lead time violated (fail closed)

================================================================================
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal, getcontext
from typing import Any, Dict, List, Optional, Tuple

getcontext().prec = 28

# 12 BOARD PACK SECTIONS byte-for-byte
BOARD_PACK_SECTIONS: Tuple[str, ...] = (
    "COVER_LETTER",
    "STRATEGIC_UPDATE",
    "FINANCIAL_PERFORMANCE",
    "RISK_REPORT",
    "COMPLIANCE_REPORT",
    "AUDIT_REPORT",
    "HR_REPORT",
    "IT_CYBER_REPORT",
    "CUSTOMER_EXPERIENCE",
    "SUSTAINABILITY_ESG",
    "BOARD_RESOLUTIONS",
    "APPENDICES",
)

# 5 BOARD COMMITTEES byte-for-byte
BOARD_COMMITTEES: Tuple[str, ...] = (
    "BOARD_AUDIT_COMMITTEE",
    "BOARD_RISK_COMMITTEE",
    "BOARD_CREDIT_COMMITTEE",
    "BOARD_NOMINATIONS_COMMITTEE",
    "BOARD_STRATEGY_COMMITTEE",
)

# 3 BOARD FREQUENCIES byte-for-byte
BOARD_FREQUENCIES: Tuple[str, ...] = ("QUARTERLY", "MONTHLY", "EXTRAORDINARY")

# CMA Code of Corporate Governance lead time byte-for-byte
BOARD_PACK_LEAD_DAYS = 14   # CMA Code: 14 days before meeting
BOARD_COMMITTEE_LEAD_DAYS = 7  # 7 days before sub-committee meeting

# Required board pack completeness byte-for-byte
BOARD_MIN_COMPLETE_PCT = Decimal("100")  # zero tolerance for board

# Committee section mapping (which sections each committee primarily focuses on)
COMMITTEE_PRIMARY_SECTIONS: Dict[str, Tuple[str, ...]] = {
    "BOARD_AUDIT_COMMITTEE": ("AUDIT_REPORT", "FINANCIAL_PERFORMANCE",
                              "COMPLIANCE_REPORT", "RISK_REPORT"),
    "BOARD_RISK_COMMITTEE": ("RISK_REPORT", "COMPLIANCE_REPORT",
                              "IT_CYBER_REPORT"),
    "BOARD_CREDIT_COMMITTEE": ("RISK_REPORT", "FINANCIAL_PERFORMANCE"),
    "BOARD_NOMINATIONS_COMMITTEE": ("HR_REPORT", "STRATEGIC_UPDATE"),
    "BOARD_STRATEGY_COMMITTEE": ("STRATEGIC_UPDATE", "FINANCIAL_PERFORMANCE",
                                  "CUSTOMER_EXPERIENCE", "SUSTAINABILITY_ESG"),
}


@dataclass
class BoardSection:
    section_id: str
    title: str
    populated: bool = False
    approved_by: Optional[str] = None
    approved_date: Optional[date] = None


class BoardReportingEngine:
    """Deterministic board pack generation with CMA Code lead-time validation."""

    @staticmethod
    def generate_board_pack(
        meeting_date: Optional[date],
        distribution_date: Optional[date],
        sections: List[BoardSection],
        frequency: str = "QUARTERLY",
    ) -> Dict[str, Any]:
        """
        Build a board pack with completeness + lead-time validation.
        Rule 6: missing sections surfaced; pack not distributed if violations.
        """
        errors = []
        if meeting_date is None:
            errors.append("missing_meeting_date")
        if distribution_date is None:
            errors.append("missing_distribution_date")
        if frequency not in BOARD_FREQUENCIES:
            errors.append(f"unknown_frequency:{frequency}")
        if errors:
            return {
                "pack_type": "BOARD",
                "generated": False,
                "validation_errors": errors,
                "valid_frequencies": list(BOARD_FREQUENCIES),
            }

        # Lead time check (CMA Code: 14 days)
        lead_days = (meeting_date - distribution_date).days
        lead_compliant = lead_days >= BOARD_PACK_LEAD_DAYS

        # Completeness check
        section_ids_provided = {s.section_id for s in sections}
        missing_sections = [
            s for s in BOARD_PACK_SECTIONS if not any(
                x.section_id == s and x.populated for x in sections)
        ]
        unapproved_sections = [s.section_id for s in sections
                               if s.populated and s.approved_by is None]
        total_required = len(BOARD_PACK_SECTIONS)
        populated_count = sum(
            1 for s in BOARD_PACK_SECTIONS
            if any(x.section_id == s and x.populated for x in sections)
        )
        completeness_pct = (
            Decimal(populated_count) / Decimal(total_required) * Decimal("100")
        )
        completeness_compliant = completeness_pct >= BOARD_MIN_COMPLETE_PCT

        # Fail-closed: must satisfy both lead time AND completeness AND all approved
        all_approved = (len(unapproved_sections) == 0
                        and any(s.populated for s in sections))
        eligible_for_distribution = (
            lead_compliant and completeness_compliant and all_approved
        )

        return {
            "pack_type": "BOARD",
            "frequency": frequency,
            "meeting_date": meeting_date.isoformat(),
            "distribution_date": distribution_date.isoformat(),
            "lead_days_until_meeting": lead_days,
            "lead_days_required": BOARD_PACK_LEAD_DAYS,
            "lead_time_compliant": lead_compliant,
            "required_sections_count": total_required,
            "populated_count": populated_count,
            "completeness_pct": str(completeness_pct.quantize(Decimal("0.01"))),
            "min_required_pct": str(BOARD_MIN_COMPLETE_PCT),
            "completeness_compliant": completeness_compliant,
            "missing_sections": missing_sections,
            "unapproved_sections": unapproved_sections,
            "all_approved": all_approved,
            "eligible_for_distribution": eligible_for_distribution,
            "generated": True,
        }

    @staticmethod
    def generate_committee_pack(
        committee: str,
        meeting_date: Optional[date],
        distribution_date: Optional[date],
        sections: List[BoardSection],
    ) -> Dict[str, Any]:
        """
        Sub-committee specific pack — only primary sections required.
        Rule 6: missing required sections surfaced.
        """
        if committee not in BOARD_COMMITTEES:
            return {
                "pack_type": "COMMITTEE",
                "generated": False,
                "validation_errors": [f"unknown_committee:{committee}"],
                "valid_committees": list(BOARD_COMMITTEES),
            }
        if meeting_date is None or distribution_date is None:
            return {
                "pack_type": "COMMITTEE",
                "committee": committee,
                "generated": False,
                "validation_errors": ["missing_dates"],
            }

        primary = COMMITTEE_PRIMARY_SECTIONS[committee]
        lead_days = (meeting_date - distribution_date).days
        lead_compliant = lead_days >= BOARD_COMMITTEE_LEAD_DAYS

        missing = [s for s in primary if not any(
            x.section_id == s and x.populated for x in sections)]
        eligible = lead_compliant and len(missing) == 0

        return {
            "pack_type": "COMMITTEE",
            "committee": committee,
            "meeting_date": meeting_date.isoformat(),
            "distribution_date": distribution_date.isoformat(),
            "lead_days_until_meeting": lead_days,
            "lead_days_required": BOARD_COMMITTEE_LEAD_DAYS,
            "lead_time_compliant": lead_compliant,
            "required_sections": list(primary),
            "missing_sections": missing,
            "eligible_for_distribution": eligible,
            "generated": True,
        }

    @staticmethod
    def validate_lead_time(
        meeting_date: Optional[date],
        distribution_date: Optional[date],
        pack_type: str = "BOARD",
    ) -> Dict[str, Any]:
        """Rule 1: lead_days=None when meeting_date missing."""
        if meeting_date is None or distribution_date is None:
            return {
                "lead_days": None,
                "compliant": None,
                "reason": "missing_dates",
            }
        lead_days = (meeting_date - distribution_date).days
        required = (BOARD_PACK_LEAD_DAYS if pack_type == "BOARD"
                    else BOARD_COMMITTEE_LEAD_DAYS)
        return {
            "lead_days": lead_days,
            "lead_days_required": required,
            "compliant": lead_days >= required,
            "pack_type": pack_type,
        }


# ============================================================================
# Self-tests
# ============================================================================

def _full_board_sections():
    return [BoardSection(section_id=s, title=s.replace("_", " ").title(),
                         populated=True, approved_by="Board_Secretary",
                         approved_date=date(2026, 4, 1))
            for s in BOARD_PACK_SECTIONS]


def _test_board_pack_full_compliant():
    r = BoardReportingEngine.generate_board_pack(
        meeting_date=date(2026, 5, 15),
        distribution_date=date(2026, 4, 30),  # 15 days ahead
        sections=_full_board_sections(),
    )
    assert r["lead_time_compliant"] is True
    assert r["completeness_compliant"] is True
    assert r["eligible_for_distribution"] is True


def _test_board_pack_lead_time_violation():
    """Distribution only 7 days before meeting — violates 14-day rule."""
    r = BoardReportingEngine.generate_board_pack(
        meeting_date=date(2026, 5, 15),
        distribution_date=date(2026, 5, 8),
        sections=_full_board_sections(),
    )
    assert r["lead_time_compliant"] is False
    assert r["eligible_for_distribution"] is False


def _test_board_pack_missing_section():
    """Drop 1 section → 11/12 = 91.67% < 100% min."""
    sections = _full_board_sections()
    sections[0].populated = False
    r = BoardReportingEngine.generate_board_pack(
        meeting_date=date(2026, 5, 15),
        distribution_date=date(2026, 4, 30),
        sections=sections,
    )
    assert r["completeness_compliant"] is False
    assert r["eligible_for_distribution"] is False
    assert "COVER_LETTER" in r["missing_sections"]


def _test_board_pack_unapproved_section():
    sections = _full_board_sections()
    sections[0].approved_by = None
    r = BoardReportingEngine.generate_board_pack(
        meeting_date=date(2026, 5, 15),
        distribution_date=date(2026, 4, 30),
        sections=sections,
    )
    assert r["all_approved"] is False
    assert r["eligible_for_distribution"] is False


def _test_board_pack_missing_dates_rule6():
    r = BoardReportingEngine.generate_board_pack(
        meeting_date=None, distribution_date=date(2026, 4, 30),
        sections=_full_board_sections(),
    )
    assert r["generated"] is False


def _test_board_pack_unknown_frequency():
    r = BoardReportingEngine.generate_board_pack(
        meeting_date=date(2026, 5, 15),
        distribution_date=date(2026, 4, 30),
        sections=_full_board_sections(),
        frequency="WEIRD",
    )
    assert r["generated"] is False


def _test_committee_pack_audit_complete():
    """Audit committee needs AUDIT_REPORT + FINANCIAL_PERFORMANCE + COMPLIANCE_REPORT + RISK_REPORT."""
    sections = [
        BoardSection(section_id="AUDIT_REPORT", title="Audit", populated=True),
        BoardSection(section_id="FINANCIAL_PERFORMANCE", title="Fin", populated=True),
        BoardSection(section_id="COMPLIANCE_REPORT", title="Compliance", populated=True),
        BoardSection(section_id="RISK_REPORT", title="Risk", populated=True),
    ]
    r = BoardReportingEngine.generate_committee_pack(
        committee="BOARD_AUDIT_COMMITTEE",
        meeting_date=date(2026, 5, 15),
        distribution_date=date(2026, 5, 7),  # 8 days ahead, > 7
        sections=sections,
    )
    assert r["eligible_for_distribution"] is True


def _test_committee_pack_lead_time_violation():
    sections = [
        BoardSection(section_id=s, title=s, populated=True)
        for s in COMMITTEE_PRIMARY_SECTIONS["BOARD_RISK_COMMITTEE"]
    ]
    r = BoardReportingEngine.generate_committee_pack(
        committee="BOARD_RISK_COMMITTEE",
        meeting_date=date(2026, 5, 15),
        distribution_date=date(2026, 5, 13),  # 2 days < 7
        sections=sections,
    )
    assert r["lead_time_compliant"] is False


def _test_committee_pack_unknown():
    r = BoardReportingEngine.generate_committee_pack(
        committee="WEIRD",
        meeting_date=date(2026, 5, 15),
        distribution_date=date(2026, 5, 7),
        sections=[],
    )
    assert r["generated"] is False


def _test_validate_lead_time_compliant():
    r = BoardReportingEngine.validate_lead_time(
        date(2026, 5, 15), date(2026, 4, 30), "BOARD")
    assert r["compliant"] is True
    assert r["lead_days"] == 15


def _test_validate_lead_time_rule1_missing():
    r = BoardReportingEngine.validate_lead_time(None, date(2026, 4, 30))
    assert r["lead_days"] is None


def _test_board_pack_sections_byte_for_byte():
    expected = ("COVER_LETTER", "STRATEGIC_UPDATE", "FINANCIAL_PERFORMANCE",
                "RISK_REPORT", "COMPLIANCE_REPORT", "AUDIT_REPORT",
                "HR_REPORT", "IT_CYBER_REPORT", "CUSTOMER_EXPERIENCE",
                "SUSTAINABILITY_ESG", "BOARD_RESOLUTIONS", "APPENDICES")
    for s in expected:
        assert s in BOARD_PACK_SECTIONS
    assert len(BOARD_PACK_SECTIONS) == 12


def _test_committees_byte_for_byte():
    expected = ("BOARD_AUDIT_COMMITTEE", "BOARD_RISK_COMMITTEE",
                "BOARD_CREDIT_COMMITTEE", "BOARD_NOMINATIONS_COMMITTEE",
                "BOARD_STRATEGY_COMMITTEE")
    for c in expected:
        assert c in BOARD_COMMITTEES
    assert len(BOARD_COMMITTEES) == 5


def _test_lead_times_byte_for_byte():
    assert BOARD_PACK_LEAD_DAYS == 14
    assert BOARD_COMMITTEE_LEAD_DAYS == 7


def _test_min_complete_byte_for_byte():
    assert BOARD_MIN_COMPLETE_PCT == Decimal("100")


def _test_frequencies_byte_for_byte():
    expected = ("QUARTERLY", "MONTHLY", "EXTRAORDINARY")
    for f in expected:
        assert f in BOARD_FREQUENCIES


def _test_committee_section_mapping_byte_for_byte():
    """BAC primary sections include AUDIT_REPORT, FINANCIAL_PERFORMANCE."""
    bac = COMMITTEE_PRIMARY_SECTIONS["BOARD_AUDIT_COMMITTEE"]
    assert "AUDIT_REPORT" in bac
    assert "FINANCIAL_PERFORMANCE" in bac
    brc = COMMITTEE_PRIMARY_SECTIONS["BOARD_RISK_COMMITTEE"]
    assert "RISK_REPORT" in brc


def self_test() -> bool:
    tests = [
        _test_board_pack_full_compliant,
        _test_board_pack_lead_time_violation,
        _test_board_pack_missing_section,
        _test_board_pack_unapproved_section,
        _test_board_pack_missing_dates_rule6,
        _test_board_pack_unknown_frequency,
        _test_committee_pack_audit_complete,
        _test_committee_pack_lead_time_violation,
        _test_committee_pack_unknown,
        _test_validate_lead_time_compliant,
        _test_validate_lead_time_rule1_missing,
        _test_board_pack_sections_byte_for_byte,
        _test_committees_byte_for_byte,
        _test_lead_times_byte_for_byte,
        _test_min_complete_byte_for_byte,
        _test_frequencies_byte_for_byte,
        _test_committee_section_mapping_byte_for_byte,
    ]
    print("=" * 60)
    print("Board Reporting Pack Generator — Self-Tests (#86)")
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
