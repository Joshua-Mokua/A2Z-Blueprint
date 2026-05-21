"""
================================================================================
A2Z MIS 360 — Volume Seventeen Batch Tests (Standards #85-#88 Reporting Auto)
================================================================================

Tests Standards #85 Management Reporting Pack, #86 Board Reporting Pack,
#87 Submission Workflow, #88 Pillar 3 Disclosure.

Total: 74 unit tests covering MIS pack assembly + completeness validation,
       CMA Code 14-day board distribution rule, CBK BSD submission state machine
       + deadline tracking, and Basel Pillar 3 (BCBS 309/356) 12-table generator.

Run via:
    pytest tests/test_volume_seventeen_batch.py -v
================================================================================
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

try:
    import pytest  # type: ignore
except ImportError:
    pytest = None  # type: ignore

from utils.management_reporting import (
    ManagementReportingEngine, MisSection,
    MONTHLY_MIS_SECTIONS, WEEKLY_FLASH_SECTIONS,
    PACK_FREQUENCIES, DISTRIBUTION_TIERS,
    EXCO_MIN_COMPLETE_PCT, MANCO_MIN_COMPLETE_PCT, DEPT_MIN_COMPLETE_PCT,
    MONTHLY_PACK_LEAD_DAYS, WEEKLY_FLASH_LEAD_DAYS,
)
from utils.board_reporting import (
    BoardReportingEngine, BoardSection,
    BOARD_PACK_SECTIONS, BOARD_COMMITTEES, BOARD_FREQUENCIES,
    BOARD_PACK_LEAD_DAYS, BOARD_COMMITTEE_LEAD_DAYS,
    BOARD_MIN_COMPLETE_PCT, COMMITTEE_PRIMARY_SECTIONS,
)
from utils.submission_workflow import (
    SubmissionWorkflowEngine, Submission, WorkflowEvent,
    SUBMISSION_STATES, ALLOWED_TRANSITIONS, SUBMISSION_TYPES,
    FILING_DEADLINE_DAYS, WORKFLOW_EVENT_TYPES, DEADLINE_STATUS_BANDS_DAYS,
)
from utils.pillar3_disclosure import (
    Pillar3Engine, Pillar3Inputs,
    PILLAR_3_TABLES, DISCLOSURE_FREQUENCIES,
    TABLE_FREQUENCIES_LARGE_BANK, TABLE_FREQUENCIES_OTHER_BANK,
    LARGE_BANK_ASSET_THRESHOLD_KES, KM1_MANDATORY_METRICS,
)


# ============================================================================
# #85 Management Reporting (17)
# ============================================================================

class TestManagementReporting:

    def _full_monthly(self):
        return [MisSection(section_id=s, title=s, populated=True)
                for s in MONTHLY_MIS_SECTIONS]

    def _full_weekly(self):
        return [MisSection(section_id=s, title=s, populated=True)
                for s in WEEKLY_FLASH_SECTIONS]

    def test_monthly_sections_byte_for_byte(self):
        for s in ("EXECUTIVE_SUMMARY", "FINANCIAL_HIGHLIGHTS", "BALANCE_SHEET",
                  "INCOME_STATEMENT", "KPI_DASHBOARD", "BRANCH_PERFORMANCE",
                  "RISK_INDICATORS", "COMPLIANCE_STATUS", "HR_METRICS",
                  "IT_OPERATIONS"):
            assert s in MONTHLY_MIS_SECTIONS
        assert len(MONTHLY_MIS_SECTIONS) == 10

    def test_weekly_sections_byte_for_byte(self):
        for s in ("EXECUTIVE_SUMMARY", "KEY_KPIS", "RISK_ALERTS", "ACTION_ITEMS"):
            assert s in WEEKLY_FLASH_SECTIONS
        assert len(WEEKLY_FLASH_SECTIONS) == 4

    def test_frequencies_byte_for_byte(self):
        for f in ("MONTHLY", "WEEKLY", "AD_HOC"):
            assert f in PACK_FREQUENCIES

    def test_tiers_byte_for_byte(self):
        for t in ("EXCO", "MANCO", "DEPARTMENT_HEADS"):
            assert t in DISTRIBUTION_TIERS

    def test_thresholds_byte_for_byte(self):
        assert EXCO_MIN_COMPLETE_PCT == Decimal("100")
        assert MANCO_MIN_COMPLETE_PCT == Decimal("90")
        assert DEPT_MIN_COMPLETE_PCT == Decimal("80")

    def test_lead_times_byte_for_byte(self):
        assert MONTHLY_PACK_LEAD_DAYS == 5
        assert WEEKLY_FLASH_LEAD_DAYS == 1

    def test_monthly_full_complete(self):
        r = ManagementReportingEngine.generate_monthly_mis_pack(
            date(2026, 4, 30), self._full_monthly(), target_tier="EXCO")
        assert r["completeness_pct"] == "100.00"
        assert r["eligible_for_distribution"] is True

    def test_monthly_below_exco_threshold(self):
        sections = self._full_monthly()
        sections[0].populated = False
        r = ManagementReportingEngine.generate_monthly_mis_pack(
            date(2026, 4, 30), sections, target_tier="EXCO")
        assert r["eligible_for_distribution"] is False

    def test_monthly_meets_manco_threshold(self):
        sections = self._full_monthly()
        sections[0].populated = False
        r = ManagementReportingEngine.generate_monthly_mis_pack(
            date(2026, 4, 30), sections, target_tier="MANCO")
        assert r["eligible_for_distribution"] is True

    def test_monthly_meets_dept_threshold(self):
        sections = self._full_monthly()
        sections[0].populated = False
        sections[1].populated = False
        r = ManagementReportingEngine.generate_monthly_mis_pack(
            date(2026, 4, 30), sections, target_tier="DEPARTMENT_HEADS")
        assert Decimal(r["completeness_pct"]) == Decimal("80.00")
        assert r["eligible_for_distribution"] is True

    def test_monthly_missing_sections_surfaced(self):
        sections = self._full_monthly()[:5]
        r = ManagementReportingEngine.generate_monthly_mis_pack(
            date(2026, 4, 30), sections, target_tier="EXCO")
        assert len(r["missing_sections"]) == 5

    def test_monthly_missing_period_rule6(self):
        r = ManagementReportingEngine.generate_monthly_mis_pack(
            None, self._full_monthly(), target_tier="EXCO")
        assert r["generated"] is False

    def test_unknown_tier_rejected(self):
        r = ManagementReportingEngine.generate_monthly_mis_pack(
            date(2026, 4, 30), self._full_monthly(), target_tier="WEIRD")
        assert r["generated"] is False

    def test_weekly_full_complete(self):
        r = ManagementReportingEngine.generate_weekly_executive_flash(
            date(2026, 4, 24), self._full_weekly())
        assert r["eligible_for_distribution"] is True

    def test_weekly_missing_blocks_distribution(self):
        sections = self._full_weekly()
        sections[0].populated = False
        r = ManagementReportingEngine.generate_weekly_executive_flash(
            date(2026, 4, 24), sections)
        assert r["eligible_for_distribution"] is False

    def test_distribution_list_exco(self):
        r = ManagementReportingEngine.distribution_list("EXCO")
        assert "MD" in r["recipients"]

    def test_distribution_list_unknown(self):
        r = ManagementReportingEngine.distribution_list("WEIRD")
        assert "error" in r


# ============================================================================
# #86 Board Reporting (17)
# ============================================================================

class TestBoardReporting:

    def _full_board(self):
        return [BoardSection(section_id=s, title=s, populated=True,
                             approved_by="Sec", approved_date=date(2026, 4, 1))
                for s in BOARD_PACK_SECTIONS]

    def test_board_sections_byte_for_byte(self):
        for s in ("COVER_LETTER", "STRATEGIC_UPDATE", "FINANCIAL_PERFORMANCE",
                  "RISK_REPORT", "COMPLIANCE_REPORT", "AUDIT_REPORT",
                  "HR_REPORT", "IT_CYBER_REPORT", "CUSTOMER_EXPERIENCE",
                  "SUSTAINABILITY_ESG", "BOARD_RESOLUTIONS", "APPENDICES"):
            assert s in BOARD_PACK_SECTIONS
        assert len(BOARD_PACK_SECTIONS) == 12

    def test_committees_byte_for_byte(self):
        for c in ("BOARD_AUDIT_COMMITTEE", "BOARD_RISK_COMMITTEE",
                  "BOARD_CREDIT_COMMITTEE", "BOARD_NOMINATIONS_COMMITTEE",
                  "BOARD_STRATEGY_COMMITTEE"):
            assert c in BOARD_COMMITTEES
        assert len(BOARD_COMMITTEES) == 5

    def test_lead_times_byte_for_byte(self):
        assert BOARD_PACK_LEAD_DAYS == 14
        assert BOARD_COMMITTEE_LEAD_DAYS == 7

    def test_min_complete_byte_for_byte(self):
        assert BOARD_MIN_COMPLETE_PCT == Decimal("100")

    def test_frequencies_byte_for_byte(self):
        for f in ("QUARTERLY", "MONTHLY", "EXTRAORDINARY"):
            assert f in BOARD_FREQUENCIES

    def test_committee_section_mapping_byte_for_byte(self):
        bac = COMMITTEE_PRIMARY_SECTIONS["BOARD_AUDIT_COMMITTEE"]
        assert "AUDIT_REPORT" in bac
        assert "FINANCIAL_PERFORMANCE" in bac
        assert "COMPLIANCE_REPORT" in bac
        assert "RISK_REPORT" in bac

    def test_board_pack_full_compliant(self):
        r = BoardReportingEngine.generate_board_pack(
            date(2026, 5, 15), date(2026, 4, 30), self._full_board())
        assert r["lead_time_compliant"] is True
        assert r["completeness_compliant"] is True
        assert r["eligible_for_distribution"] is True

    def test_board_lead_time_violation(self):
        """7 days lead time < 14 day rule."""
        r = BoardReportingEngine.generate_board_pack(
            date(2026, 5, 15), date(2026, 5, 8), self._full_board())
        assert r["lead_time_compliant"] is False
        assert r["eligible_for_distribution"] is False

    def test_board_missing_section(self):
        sections = self._full_board()
        sections[0].populated = False
        r = BoardReportingEngine.generate_board_pack(
            date(2026, 5, 15), date(2026, 4, 30), sections)
        assert r["completeness_compliant"] is False

    def test_board_unapproved_section(self):
        sections = self._full_board()
        sections[0].approved_by = None
        r = BoardReportingEngine.generate_board_pack(
            date(2026, 5, 15), date(2026, 4, 30), sections)
        assert r["all_approved"] is False

    def test_board_missing_dates_rule6(self):
        r = BoardReportingEngine.generate_board_pack(
            None, date(2026, 4, 30), self._full_board())
        assert r["generated"] is False

    def test_board_unknown_frequency(self):
        r = BoardReportingEngine.generate_board_pack(
            date(2026, 5, 15), date(2026, 4, 30), self._full_board(),
            frequency="WEIRD")
        assert r["generated"] is False

    def test_committee_pack_audit_complete(self):
        sections = [BoardSection(section_id=s, title=s, populated=True)
                    for s in COMMITTEE_PRIMARY_SECTIONS["BOARD_AUDIT_COMMITTEE"]]
        r = BoardReportingEngine.generate_committee_pack(
            "BOARD_AUDIT_COMMITTEE", date(2026, 5, 15), date(2026, 5, 7), sections)
        assert r["eligible_for_distribution"] is True

    def test_committee_pack_lead_time_violation(self):
        sections = [BoardSection(section_id=s, title=s, populated=True)
                    for s in COMMITTEE_PRIMARY_SECTIONS["BOARD_RISK_COMMITTEE"]]
        r = BoardReportingEngine.generate_committee_pack(
            "BOARD_RISK_COMMITTEE", date(2026, 5, 15), date(2026, 5, 13), sections)
        assert r["lead_time_compliant"] is False

    def test_committee_pack_unknown(self):
        r = BoardReportingEngine.generate_committee_pack(
            "WEIRD", date(2026, 5, 15), date(2026, 5, 7), [])
        assert r["generated"] is False

    def test_validate_lead_time_compliant(self):
        r = BoardReportingEngine.validate_lead_time(
            date(2026, 5, 15), date(2026, 4, 30), "BOARD")
        assert r["compliant"] is True

    def test_validate_lead_time_rule1(self):
        r = BoardReportingEngine.validate_lead_time(None, date(2026, 4, 30))
        assert r["lead_days"] is None


# ============================================================================
# #87 Submission Workflow (21)
# ============================================================================

class TestSubmissionWorkflow:

    def test_states_byte_for_byte(self):
        for s in ("DRAFT", "REVIEW", "APPROVED", "SUBMITTED",
                  "ACKNOWLEDGED", "REJECTED"):
            assert s in SUBMISSION_STATES
        assert len(SUBMISSION_STATES) == 6

    def test_transitions_byte_for_byte(self):
        assert ALLOWED_TRANSITIONS["DRAFT"] == ("REVIEW",)
        assert "APPROVED" in ALLOWED_TRANSITIONS["REVIEW"]
        assert "DRAFT" in ALLOWED_TRANSITIONS["REVIEW"]
        assert "SUBMITTED" in ALLOWED_TRANSITIONS["APPROVED"]
        assert "ACKNOWLEDGED" in ALLOWED_TRANSITIONS["SUBMITTED"]
        assert ALLOWED_TRANSITIONS["ACKNOWLEDGED"] == ()

    def test_submission_types_byte_for_byte(self):
        for s in ("BSD_1", "BSD_2", "BSD_3", "BSD_17", "BSD_19",
                  "LCR", "NSFR", "LARGE_EXPOSURES", "PILLAR_3", "ANNUAL_RETURN"):
            assert s in SUBMISSION_TYPES
        assert len(SUBMISSION_TYPES) == 10

    def test_filing_deadlines_byte_for_byte(self):
        assert FILING_DEADLINE_DAYS["BSD_1"] == 1
        assert FILING_DEADLINE_DAYS["BSD_2"] == 5
        assert FILING_DEADLINE_DAYS["BSD_3"] == 15
        assert FILING_DEADLINE_DAYS["BSD_17"] == 15
        assert FILING_DEADLINE_DAYS["BSD_19"] == 30
        assert FILING_DEADLINE_DAYS["NSFR"] == 30
        assert FILING_DEADLINE_DAYS["PILLAR_3"] == 90
        assert FILING_DEADLINE_DAYS["ANNUAL_RETURN"] == 90

    def test_event_types_byte_for_byte(self):
        for e in ("STATE_CHANGE", "REVIEWER_ASSIGNED", "COMMENT_ADDED"):
            assert e in WORKFLOW_EVENT_TYPES

    def test_status_bands_byte_for_byte(self):
        assert DEADLINE_STATUS_BANDS_DAYS["DUE_TODAY"] == (0, 0)
        assert DEADLINE_STATUS_BANDS_DAYS["URGENT"] == (1, 2)
        assert DEADLINE_STATUS_BANDS_DAYS["UPCOMING"] == (3, 7)

    def test_valid_transition(self):
        r = SubmissionWorkflowEngine.validate_state_transition("DRAFT", "REVIEW")
        assert r["allowed"] is True

    def test_invalid_transition(self):
        r = SubmissionWorkflowEngine.validate_state_transition("DRAFT", "SUBMITTED")
        assert r["allowed"] is False

    def test_terminal_state_no_exit(self):
        r = SubmissionWorkflowEngine.validate_state_transition("ACKNOWLEDGED", "DRAFT")
        assert r["allowed"] is False

    def test_unknown_state_rejected(self):
        r = SubmissionWorkflowEngine.validate_state_transition("WEIRD", "DRAFT")
        assert r["allowed"] is False

    def test_deadline_on_track(self):
        r = SubmissionWorkflowEngine.days_until_deadline(
            "BSD_3", date(2026, 4, 30), as_of=date(2026, 5, 1))
        assert r["days_until_deadline"] == 14
        assert r["status"] == "ON_TRACK"

    def test_deadline_due_today(self):
        r = SubmissionWorkflowEngine.days_until_deadline(
            "BSD_3", date(2026, 4, 30), as_of=date(2026, 5, 15))
        assert r["status"] == "DUE_TODAY"

    def test_deadline_overdue(self):
        r = SubmissionWorkflowEngine.days_until_deadline(
            "BSD_3", date(2026, 4, 30), as_of=date(2026, 5, 18))
        assert r["is_overdue"] is True

    def test_deadline_urgent(self):
        r = SubmissionWorkflowEngine.days_until_deadline(
            "BSD_3", date(2026, 4, 30), as_of=date(2026, 5, 14))
        assert r["status"] == "URGENT"

    def test_deadline_unknown_type(self):
        r = SubmissionWorkflowEngine.days_until_deadline("WEIRD", date(2026, 4, 30))
        assert r["days_until_deadline"] is None

    def test_deadline_missing_period_rule1(self):
        r = SubmissionWorkflowEngine.days_until_deadline("BSD_3", None)
        assert r["days_until_deadline"] is None

    def test_log_state_change_valid(self):
        sub = Submission(submission_id="S1", submission_type="BSD_3",
                        period_end=date(2026, 4, 30))
        r = SubmissionWorkflowEngine.log_workflow_event(
            sub, actor="alice", event_type="STATE_CHANGE", new_state="REVIEW")
        assert r["logged"] is True
        assert sub.current_state == "REVIEW"

    def test_log_invalid_state_change_rejected(self):
        sub = Submission(submission_id="S1", submission_type="BSD_3",
                        period_end=date(2026, 4, 30))
        r = SubmissionWorkflowEngine.log_workflow_event(
            sub, actor="alice", event_type="STATE_CHANGE", new_state="SUBMITTED")
        assert r["logged"] is False
        assert sub.current_state == "DRAFT"

    def test_log_comment_no_state_change(self):
        sub = Submission(submission_id="S1", submission_type="BSD_3",
                        period_end=date(2026, 4, 30), current_state="REVIEW")
        r = SubmissionWorkflowEngine.log_workflow_event(
            sub, actor="bob", event_type="COMMENT_ADDED", comment="LGTM")
        assert r["logged"] is True
        assert sub.current_state == "REVIEW"

    def test_full_lifecycle_traversal(self):
        sub = Submission(submission_id="S1", submission_type="BSD_3",
                        period_end=date(2026, 4, 30))
        for state in ["REVIEW", "APPROVED", "SUBMITTED", "ACKNOWLEDGED"]:
            r = SubmissionWorkflowEngine.log_workflow_event(
                sub, actor="user", event_type="STATE_CHANGE", new_state=state)
            assert r["logged"] is True
        assert sub.current_state == "ACKNOWLEDGED"

    def test_status_summary_overdue(self):
        subs = [
            Submission(submission_id="S1", submission_type="BSD_3",
                      period_end=date(2026, 1, 1), current_state="DRAFT"),
        ]
        r = SubmissionWorkflowEngine.submission_status_summary(
            subs, as_of=date(2026, 4, 30))
        assert r["overdue_count"] >= 1


# ============================================================================
# #88 Pillar 3 Disclosure (19)
# ============================================================================

def _p3_inputs(**kw):
    defaults = dict(
        reporting_period_end=date(2026, 4, 30),
        total_assets_kes=Decimal("150000000000"),
        cet1_capital_kes=Decimal("12000000000"),
        tier1_capital_kes=Decimal("13000000000"),
        total_capital_kes=Decimal("15000000000"),
        rwa_kes=Decimal("90000000000"),
        leverage_exposures_kes=Decimal("250000000000"),
        lcr_hqla_kes=Decimal("20000000000"),
        lcr_net_outflows_kes=Decimal("15000000000"),
        nsfr_asf_kes=Decimal("100000000000"),
        nsfr_rsf_kes=Decimal("90000000000"),
    )
    defaults.update(kw)
    return Pillar3Inputs(**defaults)


class TestPillar3Disclosure:

    def test_tables_byte_for_byte(self):
        for t in ("KM1", "OV1", "CR1", "CR3", "CR4", "CR5",
                  "LIQ1", "LIQ2", "LR1", "MR1", "OR1", "REM1"):
            assert t in PILLAR_3_TABLES
        assert len(PILLAR_3_TABLES) == 12

    def test_frequencies_byte_for_byte(self):
        for f in ("ANNUAL", "SEMI_ANNUAL", "QUARTERLY"):
            assert f in DISCLOSURE_FREQUENCIES

    def test_large_bank_freq_map_byte_for_byte(self):
        assert TABLE_FREQUENCIES_LARGE_BANK["KM1"] == "QUARTERLY"
        assert TABLE_FREQUENCIES_LARGE_BANK["LIQ1"] == "QUARTERLY"
        assert TABLE_FREQUENCIES_LARGE_BANK["REM1"] == "ANNUAL"
        assert TABLE_FREQUENCIES_LARGE_BANK["CR1"] == "SEMI_ANNUAL"

    def test_other_bank_freq_map_byte_for_byte(self):
        assert TABLE_FREQUENCIES_OTHER_BANK["KM1"] == "SEMI_ANNUAL"
        assert TABLE_FREQUENCIES_OTHER_BANK["LIQ1"] == "SEMI_ANNUAL"

    def test_large_bank_threshold_byte_for_byte(self):
        assert LARGE_BANK_ASSET_THRESHOLD_KES == Decimal("100000000000")

    def test_km1_mandatory_metrics_byte_for_byte(self):
        for m in ("cet1_capital_kes", "tier1_capital_kes", "total_capital_kes",
                  "rwa_kes", "cet1_ratio_pct", "tier1_ratio_pct", "total_car_pct",
                  "leverage_ratio_pct", "lcr_pct", "nsfr_pct"):
            assert m in KM1_MANDATORY_METRICS
        assert len(KM1_MANDATORY_METRICS) == 10

    def test_is_large_bank(self):
        assert Pillar3Engine.is_large_bank(Decimal("150000000000")) is True
        assert Pillar3Engine.is_large_bank(Decimal("50000000000")) is False
        assert Pillar3Engine.is_large_bank(None) is None

    def test_km1_full_complete(self):
        r = Pillar3Engine.generate_km1_key_metrics(_p3_inputs())
        assert r["complete"] is True
        assert r["metrics"]["cet1_ratio_pct"] == "13.33"
        assert r["metrics"]["total_car_pct"] == "16.67"
        assert r["metrics"]["leverage_ratio_pct"] == "5.20"
        assert r["metrics"]["lcr_pct"] == "133.33"
        assert r["metrics"]["nsfr_pct"] == "111.11"

    def test_km1_zero_rwa_rule1(self):
        r = Pillar3Engine.generate_km1_key_metrics(
            _p3_inputs(rwa_kes=Decimal("0")))
        assert r["metrics"]["total_car_pct"] is None

    def test_km1_missing_period_rule6(self):
        r = Pillar3Engine.generate_km1_key_metrics(
            _p3_inputs(reporting_period_end=None))
        assert r["generated"] is False

    def test_km1_missing_metric_surfaced(self):
        r = Pillar3Engine.generate_km1_key_metrics(
            _p3_inputs(nsfr_asf_kes=None))
        assert "nsfr_pct" in r["missing_mandatory_metrics"]

    def test_ov1_full_complete(self):
        r = Pillar3Engine.generate_ov1_overview_rwa(
            _p3_inputs(),
            credit_rwa_kes=Decimal("70000000000"),
            market_rwa_kes=Decimal("5000000000"),
            operational_rwa_kes=Decimal("15000000000"),
        )
        assert r["complete"] is True

    def test_ov1_missing_components_rule6(self):
        r = Pillar3Engine.generate_ov1_overview_rwa(
            _p3_inputs(),
            credit_rwa_kes=Decimal("70000000000"),
        )
        assert "market_rwa_kes" in r["missing_components"]
        assert r["complete"] is False

    def test_lr1_basic(self):
        r = Pillar3Engine.generate_lr1_leverage(_p3_inputs())
        assert r["leverage_ratio_pct"] == "5.20"

    def test_lr1_zero_exposures_rule1(self):
        r = Pillar3Engine.generate_lr1_leverage(
            _p3_inputs(leverage_exposures_kes=Decimal("0")))
        assert r["leverage_ratio_pct"] is None

    def test_pack_complete(self):
        r = Pillar3Engine.generate_pillar3_pack(
            _p3_inputs(), provided_table_ids=list(PILLAR_3_TABLES))
        assert r["complete"] is True
        assert r["bank_class"] == "LARGE_BANK"

    def test_pack_missing_tables_rule6(self):
        r = Pillar3Engine.generate_pillar3_pack(
            _p3_inputs(), provided_table_ids=["KM1", "OV1"])
        assert r["complete"] is False
        assert len(r["missing_tables"]) == 10

    def test_pack_other_bank(self):
        r = Pillar3Engine.generate_pillar3_pack(
            _p3_inputs(total_assets_kes=Decimal("50000000000")),
            provided_table_ids=list(PILLAR_3_TABLES))
        assert r["bank_class"] == "OTHER_BANK"

    def test_pack_unknown_class(self):
        r = Pillar3Engine.generate_pillar3_pack(
            _p3_inputs(total_assets_kes=None),
            provided_table_ids=list(PILLAR_3_TABLES))
        assert r["bank_class"] == "UNKNOWN"
