"""
================================================================================
A2Z MIS 360 — Volume Twenty Batch Tests (Standards #97-#100 — CENTENNIAL)
================================================================================

Tests Standards #97 Tax/VAT, #98 Procurement, #99 Financial Close,
#100 Group Consolidation (centennial milestone).

Total: 131 unit tests covering KRA tax types + WHT rates + filing deadlines +
       state machines for procurement (7 states) + financial close (6 states) +
       3-way match tolerance + materiality (0.1%) + suspense zero tolerance +
       3-tier signoff + IFRS 10/IAS 28/IFRS 11 consolidation methods +
       NCI computation + IAS 21 currency translation.

Run via:
    pytest tests/test_volume_twenty_batch.py -v
================================================================================
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from utils.tax_compliance import (
    TaxComplianceEngine,
    TAX_TYPES, VAT_RATE_CATEGORIES, VAT_STANDARD_RATE_PCT, VAT_ZERO_RATE_PCT,
    WITHHOLDING_TAX_RATES_PCT, CORPORATE_TAX_RATES_PCT,
    FILING_DEADLINE_DAYS, FILING_STATUSES,
    LATE_FILING_PENALTY_PCT_PER_MONTH, LATE_FILING_PENALTY_MIN_KES,
    LATE_PAYMENT_INTEREST_PCT_MONTHLY,
)
from utils.procurement_workflow import (
    ProcurementWorkflowEngine,
    PROCUREMENT_STATES, ALLOWED_PROCUREMENT_TRANSITIONS,
    APPROVAL_TIERS, BUYER_LIMIT_KES, MANAGER_LIMIT_KES,
    DIRECTOR_LIMIT_KES, MD_LIMIT_KES,
    PROCUREMENT_METHODS, DIRECT_PURCHASE_MAX_KES, RFQ_MAX_KES,
    OPEN_TENDER_MAX_KES, RESTRICTED_TENDER_MIN_KES,
    QUOTATIONS_REQUIRED, VENDOR_SELECTION_CRITERIA,
    THREE_WAY_MATCH_TOLERANCE_PCT,
)
from utils.financial_close import (
    FinancialCloseEngine,
    CLOSE_STATES, ALLOWED_CLOSE_TRANSITIONS,
    CLOSE_CALENDAR_MILESTONES, RECONCILIATION_TYPES,
    ADJUSTMENT_TYPES, SIGNOFF_LEVELS,
    MATERIALITY_THRESHOLD_PCT, SUSPENSE_ZERO_TOLERANCE_KES,
)
from utils.group_consolidation import (
    GroupConsolidationEngine,
    SUBSIDIARY_TYPES, CONSOLIDATION_METHODS,
    CONTROL_THRESHOLD_PCT, SIGNIFICANT_INFLUENCE_THRESHOLD_PCT,
    WHOLLY_OWNED_THRESHOLD_PCT,
    ELIMINATION_TYPES, CURRENCY_TRANSLATION_METHODS,
    CONSOLIDATION_FREQUENCIES,
)


# ============================================================================
# #97 Tax/VAT Compliance (35)
# ============================================================================

class TestTaxCompliance:

    def test_tax_types_byte_for_byte(self):
        for t in ("VAT", "CORPORATE_TAX", "WITHHOLDING_TAX",
                  "EXCISE_DUTY", "PAYE"):
            assert t in TAX_TYPES
        assert len(TAX_TYPES) == 5

    def test_vat_rates_byte_for_byte(self):
        assert VAT_STANDARD_RATE_PCT == Decimal("16")
        assert VAT_ZERO_RATE_PCT == Decimal("0")

    def test_wht_rates_byte_for_byte(self):
        assert WITHHOLDING_TAX_RATES_PCT["PROFESSIONAL_FEES_RESIDENT"] == Decimal("5")
        assert WITHHOLDING_TAX_RATES_PCT["PROFESSIONAL_FEES_NON_RESIDENT"] == Decimal("20")
        assert WITHHOLDING_TAX_RATES_PCT["RENT_RESIDENT"] == Decimal("10")
        assert WITHHOLDING_TAX_RATES_PCT["DIVIDENDS_RESIDENT"] == Decimal("5")
        assert WITHHOLDING_TAX_RATES_PCT["DIVIDENDS_NON_RESIDENT"] == Decimal("15")
        assert WITHHOLDING_TAX_RATES_PCT["INTEREST_RESIDENT"] == Decimal("15")

    def test_corporate_rates_byte_for_byte(self):
        assert CORPORATE_TAX_RATES_PCT["RESIDENT_COMPANY"] == Decimal("30")
        assert CORPORATE_TAX_RATES_PCT["BRANCH_NON_RESIDENT"] == Decimal("37.5")

    def test_filing_deadlines_byte_for_byte(self):
        assert FILING_DEADLINE_DAYS["VAT"] == 20
        assert FILING_DEADLINE_DAYS["PAYE"] == 9
        assert FILING_DEADLINE_DAYS["CORPORATE_TAX"] == 180

    def test_filing_statuses_byte_for_byte(self):
        for s in ("NOT_DUE", "DUE", "FILED", "PAID", "OVERDUE"):
            assert s in FILING_STATUSES

    def test_penalty_constants_byte_for_byte(self):
        assert LATE_FILING_PENALTY_PCT_PER_MONTH == Decimal("5")
        assert LATE_FILING_PENALTY_MIN_KES == Decimal("10000")

    def test_vat_standard_runtime(self):
        r = TaxComplianceEngine.vat_output(Decimal("100000"), "STANDARD")
        assert r["vat"] == "16000.00"
        assert r["input_credit_claimable"] is True

    def test_vat_zero_rated_runtime(self):
        r = TaxComplianceEngine.vat_output(Decimal("100000"), "ZERO_RATED")
        assert r["vat"] == "0.00"
        assert r["input_credit_claimable"] is True

    def test_vat_exempt_runtime(self):
        r = TaxComplianceEngine.vat_output(Decimal("100000"), "EXEMPT")
        assert r["input_credit_claimable"] is False

    def test_vat_unknown_category_rule6(self):
        r = TaxComplianceEngine.vat_output(Decimal("100000"), "WEIRD")
        assert r["computed"] is False

    def test_vat_payable_basic(self):
        r = TaxComplianceEngine.vat_payable(Decimal("16000"), Decimal("5000"))
        assert r == Decimal("11000")

    def test_vat_payable_refund(self):
        r = TaxComplianceEngine.vat_payable(Decimal("5000"), Decimal("16000"))
        assert r == Decimal("-11000")

    def test_vat_payable_missing_rule1(self):
        assert TaxComplianceEngine.vat_payable(None, Decimal("5000")) is None

    def test_corporate_tax_resident(self):
        r = TaxComplianceEngine.corporate_tax(Decimal("1000000"), "RESIDENT_COMPANY")
        assert r["tax"] == "300000.00"

    def test_corporate_tax_branch(self):
        r = TaxComplianceEngine.corporate_tax(Decimal("1000000"), "BRANCH_NON_RESIDENT")
        assert r["tax"] == "375000.00"

    def test_corporate_tax_unknown_rule6(self):
        r = TaxComplianceEngine.corporate_tax(Decimal("1000000"), "WEIRD")
        assert r["computed"] is False

    def test_wht_professional_resident(self):
        r = TaxComplianceEngine.withholding_tax(Decimal("100000"),
                                                 "PROFESSIONAL_FEES_RESIDENT")
        assert r["wht"] == "5000.00"
        assert r["net_payment"] == "95000.00"

    def test_wht_professional_non_resident(self):
        r = TaxComplianceEngine.withholding_tax(Decimal("100000"),
                                                 "PROFESSIONAL_FEES_NON_RESIDENT")
        assert r["wht"] == "20000.00"

    def test_wht_dividends_resident(self):
        r = TaxComplianceEngine.withholding_tax(Decimal("100000"),
                                                 "DIVIDENDS_RESIDENT")
        assert r["wht"] == "5000.00"

    def test_wht_dividends_non_resident(self):
        r = TaxComplianceEngine.withholding_tax(Decimal("100000"),
                                                 "DIVIDENDS_NON_RESIDENT")
        assert r["wht"] == "15000.00"

    def test_wht_unknown_rule6(self):
        r = TaxComplianceEngine.withholding_tax(Decimal("100000"), "WEIRD")
        assert r["computed"] is False

    def test_filing_deadline_vat(self):
        r = TaxComplianceEngine.filing_deadline("VAT", date(2026, 3, 31))
        assert r["deadline_date"] == "2026-04-20"

    def test_filing_deadline_paye(self):
        r = TaxComplianceEngine.filing_deadline("PAYE", date(2026, 3, 31))
        assert r["deadline_date"] == "2026-04-09"

    def test_filing_deadline_corporate(self):
        r = TaxComplianceEngine.filing_deadline("CORPORATE_TAX", date(2025, 12, 31))
        assert r["deadline_date"] == "2026-06-29"

    def test_filing_status_not_due(self):
        r = TaxComplianceEngine.filing_status(
            "VAT", date(2026, 5, 31), as_of=date(2026, 4, 15))
        assert r["status"] == "NOT_DUE"

    def test_filing_status_due(self):
        r = TaxComplianceEngine.filing_status(
            "VAT", date(2026, 3, 31), as_of=date(2026, 4, 15))
        assert r["status"] == "DUE"

    def test_filing_status_overdue(self):
        r = TaxComplianceEngine.filing_status(
            "VAT", date(2026, 3, 31), as_of=date(2026, 4, 30))
        assert r["status"] == "OVERDUE"

    def test_filing_status_filed(self):
        r = TaxComplianceEngine.filing_status(
            "VAT", date(2026, 3, 31), as_of=date(2026, 4, 30),
            filed=True, paid=False)
        assert r["status"] == "FILED"

    def test_filing_status_paid(self):
        r = TaxComplianceEngine.filing_status(
            "VAT", date(2026, 3, 31), as_of=date(2026, 4, 30),
            filed=True, paid=True)
        assert r["status"] == "PAID"

    def test_late_penalty_basic(self):
        p = TaxComplianceEngine.late_filing_penalty(Decimal("100000"), 2)
        assert p == Decimal("10000")

    def test_late_penalty_high(self):
        p = TaxComplianceEngine.late_filing_penalty(Decimal("1000000"), 3)
        assert p == Decimal("150000")

    def test_late_penalty_min_floor(self):
        p = TaxComplianceEngine.late_filing_penalty(Decimal("100000"), 1)
        assert p == Decimal("10000")

    def test_late_penalty_zero_months(self):
        p = TaxComplianceEngine.late_filing_penalty(Decimal("100000"), 0)
        assert p == Decimal("0")

    def test_late_penalty_missing_rule1(self):
        assert TaxComplianceEngine.late_filing_penalty(None, 2) is None


# ============================================================================
# #98 Procurement Workflow (34)
# ============================================================================

class TestProcurementWorkflow:

    def test_states_byte_for_byte(self):
        for s in ("REQUESTED", "APPROVED", "PO_ISSUED", "RECEIVED",
                  "INVOICED", "PAID", "CANCELLED"):
            assert s in PROCUREMENT_STATES
        assert len(PROCUREMENT_STATES) == 7

    def test_transitions_byte_for_byte(self):
        assert ALLOWED_PROCUREMENT_TRANSITIONS["REQUESTED"] == ("APPROVED", "CANCELLED")
        assert ALLOWED_PROCUREMENT_TRANSITIONS["RECEIVED"] == ("INVOICED",)
        assert ALLOWED_PROCUREMENT_TRANSITIONS["PAID"] == ()

    def test_approval_tiers_byte_for_byte(self):
        for t in ("BUYER", "MANAGER", "DIRECTOR", "MD", "BOARD"):
            assert t in APPROVAL_TIERS

    def test_thresholds_byte_for_byte(self):
        assert BUYER_LIMIT_KES == Decimal("100000")
        assert MANAGER_LIMIT_KES == Decimal("1000000")
        assert DIRECTOR_LIMIT_KES == Decimal("10000000")
        assert MD_LIMIT_KES == Decimal("50000000")

    def test_methods_byte_for_byte(self):
        for m in ("DIRECT_PURCHASE", "REQUEST_FOR_QUOTATION", "OPEN_TENDER",
                  "RESTRICTED_TENDER", "FRAMEWORK_AGREEMENT"):
            assert m in PROCUREMENT_METHODS

    def test_method_thresholds_byte_for_byte(self):
        assert DIRECT_PURCHASE_MAX_KES == Decimal("50000")
        assert RFQ_MAX_KES == Decimal("1000000")
        assert OPEN_TENDER_MAX_KES == Decimal("10000000")
        assert RESTRICTED_TENDER_MIN_KES == Decimal("10000001")

    def test_quotations_required_byte_for_byte(self):
        assert QUOTATIONS_REQUIRED["DIRECT_PURCHASE"] == 1
        assert QUOTATIONS_REQUIRED["REQUEST_FOR_QUOTATION"] == 3
        assert QUOTATIONS_REQUIRED["RESTRICTED_TENDER"] == 5

    def test_selection_criteria_byte_for_byte(self):
        for c in ("PRICE", "QUALITY", "DELIVERY", "COMPLIANCE"):
            assert c in VENDOR_SELECTION_CRITERIA

    def test_three_way_tolerance_byte_for_byte(self):
        assert THREE_WAY_MATCH_TOLERANCE_PCT == Decimal("2")

    def test_approval_buyer(self):
        r = ProcurementWorkflowEngine.approval_authority(Decimal("50000"))
        assert r["tier"] == "BUYER"

    def test_approval_buyer_boundary(self):
        r = ProcurementWorkflowEngine.approval_authority(Decimal("100000"))
        assert r["tier"] == "BUYER"

    def test_approval_manager(self):
        r = ProcurementWorkflowEngine.approval_authority(Decimal("500000"))
        assert r["tier"] == "MANAGER"

    def test_approval_director(self):
        r = ProcurementWorkflowEngine.approval_authority(Decimal("5000000"))
        assert r["tier"] == "DIRECTOR"

    def test_approval_md(self):
        r = ProcurementWorkflowEngine.approval_authority(Decimal("30000000"))
        assert r["tier"] == "MD"

    def test_approval_board(self):
        r = ProcurementWorkflowEngine.approval_authority(Decimal("100000000"))
        assert r["tier"] == "BOARD"

    def test_approval_board_boundary(self):
        r = ProcurementWorkflowEngine.approval_authority(Decimal("50000001"))
        assert r["tier"] == "BOARD"

    def test_approval_missing_rule1(self):
        r = ProcurementWorkflowEngine.approval_authority(None)
        assert r["tier"] is None

    def test_method_direct(self):
        r = ProcurementWorkflowEngine.procurement_method(Decimal("30000"))
        assert r["method"] == "DIRECT_PURCHASE"
        assert r["quotations_required"] == 1

    def test_method_rfq(self):
        r = ProcurementWorkflowEngine.procurement_method(Decimal("500000"))
        assert r["method"] == "REQUEST_FOR_QUOTATION"
        assert r["quotations_required"] == 3

    def test_method_open_tender(self):
        r = ProcurementWorkflowEngine.procurement_method(Decimal("5000000"))
        assert r["method"] == "OPEN_TENDER"

    def test_method_restricted_tender(self):
        r = ProcurementWorkflowEngine.procurement_method(Decimal("50000000"))
        assert r["method"] == "RESTRICTED_TENDER"
        assert r["quotations_required"] == 5

    def test_state_valid_transition(self):
        r = ProcurementWorkflowEngine.validate_state_transition("REQUESTED", "APPROVED")
        assert r["allowed"] is True

    def test_state_invalid_skip_rule6(self):
        r = ProcurementWorkflowEngine.validate_state_transition("REQUESTED", "PAID")
        assert r["allowed"] is False

    def test_state_terminal_paid(self):
        r = ProcurementWorkflowEngine.validate_state_transition("PAID", "REQUESTED")
        assert r["allowed"] is False

    def test_state_terminal_cancelled(self):
        r = ProcurementWorkflowEngine.validate_state_transition("CANCELLED", "APPROVED")
        assert r["allowed"] is False

    def test_state_invoiced_to_paid(self):
        r = ProcurementWorkflowEngine.validate_state_transition("INVOICED", "PAID")
        assert r["allowed"] is True

    def test_state_unknown_rule6(self):
        r = ProcurementWorkflowEngine.validate_state_transition("WEIRD", "APPROVED")
        assert r["allowed"] is False

    def test_three_way_exact_match(self):
        r = ProcurementWorkflowEngine.three_way_match(
            Decimal("100000"), Decimal("100000"), Decimal("100000"))
        assert r["matched"] is True

    def test_three_way_within_tolerance(self):
        r = ProcurementWorkflowEngine.three_way_match(
            Decimal("100000"), Decimal("101000"), Decimal("99000"))
        assert r["matched"] is True

    def test_three_way_boundary(self):
        r = ProcurementWorkflowEngine.three_way_match(
            Decimal("100000"), Decimal("102000"), Decimal("100000"))
        assert r["matched"] is True

    def test_three_way_exceeds_tolerance(self):
        r = ProcurementWorkflowEngine.three_way_match(
            Decimal("100000"), Decimal("103000"), Decimal("100000"))
        assert r["matched"] is False
        assert r["eligible_for_payment"] is False

    def test_three_way_missing_grn_rule1(self):
        r = ProcurementWorkflowEngine.three_way_match(
            Decimal("100000"), None, Decimal("100000"))
        assert r["matched"] is None

    def test_bid_count_lookup(self):
        assert ProcurementWorkflowEngine.bid_count_required("REQUEST_FOR_QUOTATION") == 3

    def test_bid_count_unknown(self):
        assert ProcurementWorkflowEngine.bid_count_required("WEIRD") is None


# ============================================================================
# #99 Financial Close (28)
# ============================================================================

class TestFinancialClose:

    def test_states_byte_for_byte(self):
        for s in ("OPEN", "IN_CLOSE", "RECONCILING", "REVIEWED",
                  "CLOSED", "REOPENED"):
            assert s in CLOSE_STATES
        assert len(CLOSE_STATES) == 6

    def test_transitions_byte_for_byte(self):
        assert ALLOWED_CLOSE_TRANSITIONS["OPEN"] == ("IN_CLOSE",)
        assert ALLOWED_CLOSE_TRANSITIONS["CLOSED"] == ("REOPENED",)

    def test_milestones_byte_for_byte(self):
        assert CLOSE_CALENDAR_MILESTONES["TXN_CUTOFF"] == 1
        assert CLOSE_CALENDAR_MILESTONES["GL_CLOSE"] == 5
        assert CLOSE_CALENDAR_MILESTONES["RECON_COMPLETE"] == 10
        assert CLOSE_CALENDAR_MILESTONES["REVIEW_COMPLETE"] == 12
        assert CLOSE_CALENDAR_MILESTONES["MGMT_REPORT"] == 15

    def test_recon_types_byte_for_byte(self):
        for t in ("GL_TO_SUBLEDGER", "BANK_RECON", "INTERCOMPANY",
                  "SUSPENSE_ACCOUNT", "NOSTRO_VOSTRO"):
            assert t in RECONCILIATION_TYPES
        assert len(RECONCILIATION_TYPES) == 5

    def test_adjustment_types_byte_for_byte(self):
        for t in ("ACCRUALS", "PROVISIONS", "REVALUATION",
                  "AMORTIZATION", "DEPRECIATION"):
            assert t in ADJUSTMENT_TYPES
        assert len(ADJUSTMENT_TYPES) == 5

    def test_signoff_levels_byte_for_byte(self):
        for l in ("PREPARER", "REVIEWER", "APPROVER"):
            assert l in SIGNOFF_LEVELS

    def test_materiality_threshold_byte_for_byte(self):
        assert MATERIALITY_THRESHOLD_PCT == Decimal("0.1")

    def test_close_state_open_to_in_close(self):
        r = FinancialCloseEngine.close_state_transition("OPEN", "IN_CLOSE")
        assert r["allowed"] is True

    def test_close_state_invalid_skip_rule6(self):
        r = FinancialCloseEngine.close_state_transition("OPEN", "CLOSED")
        assert r["allowed"] is False

    def test_close_state_reopen_path(self):
        r1 = FinancialCloseEngine.close_state_transition("CLOSED", "REOPENED")
        assert r1["allowed"] is True
        r2 = FinancialCloseEngine.close_state_transition("REOPENED", "IN_CLOSE")
        assert r2["allowed"] is True

    def test_close_state_unknown_rule6(self):
        r = FinancialCloseEngine.close_state_transition("WEIRD", "OPEN")
        assert r["allowed"] is False

    def test_milestone_txn_cutoff(self):
        r = FinancialCloseEngine.close_calendar_milestone(
            date(2026, 4, 30), "TXN_CUTOFF")
        assert r["deadline_date"] == "2026-05-01"

    def test_milestone_gl_close(self):
        r = FinancialCloseEngine.close_calendar_milestone(
            date(2026, 4, 30), "GL_CLOSE")
        assert r["deadline_date"] == "2026-05-05"

    def test_milestone_mgmt_report(self):
        r = FinancialCloseEngine.close_calendar_milestone(
            date(2026, 4, 30), "MGMT_REPORT")
        assert r["deadline_date"] == "2026-05-15"

    def test_milestone_unknown_rule6(self):
        r = FinancialCloseEngine.close_calendar_milestone(
            date(2026, 4, 30), "WEIRD")
        assert r["computed"] is False

    def test_variance_basic(self):
        r = FinancialCloseEngine.reconciliation_variance(
            Decimal("1000000"), Decimal("1001000"))
        assert r["variance"] == "1000"
        assert r["variance_pct"] == "0.1000"

    def test_variance_zero_gl_rule1(self):
        r = FinancialCloseEngine.reconciliation_variance(
            Decimal("0"), Decimal("1000"))
        assert r["variance_pct"] is None

    def test_variance_missing_rule1(self):
        r = FinancialCloseEngine.reconciliation_variance(None, Decimal("1000"))
        assert r["computed"] is False

    def test_materiality_immaterial(self):
        r = FinancialCloseEngine.materiality_check(Decimal("0.05"), "GL_TO_SUBLEDGER")
        assert r["material"] is False

    def test_materiality_material(self):
        r = FinancialCloseEngine.materiality_check(Decimal("0.5"), "GL_TO_SUBLEDGER")
        assert r["material"] is True

    def test_materiality_boundary(self):
        r = FinancialCloseEngine.materiality_check(Decimal("0.1"), "GL_TO_SUBLEDGER")
        assert r["material"] is False

    def test_materiality_suspense_zero_tolerance(self):
        r = FinancialCloseEngine.materiality_check(Decimal("0.01"), "SUSPENSE_ACCOUNT")
        assert r["material"] is True

    def test_materiality_suspense_zero_pass(self):
        r = FinancialCloseEngine.materiality_check(Decimal("0"), "SUSPENSE_ACCOUNT")
        assert r["material"] is False

    def test_materiality_unknown_recon_rule6(self):
        r = FinancialCloseEngine.materiality_check(Decimal("0.5"), "WEIRD")
        assert r["computed"] is False

    def test_materiality_missing_variance_rule1(self):
        r = FinancialCloseEngine.materiality_check(None, "GL_TO_SUBLEDGER")
        assert r["material"] is None

    def test_signoff_complete_all_three(self):
        r = FinancialCloseEngine.signoff_complete(
            {"PREPARER": True, "REVIEWER": True, "APPROVER": True})
        assert r["complete"] is True

    def test_signoff_missing_approver_rule6(self):
        r = FinancialCloseEngine.signoff_complete(
            {"PREPARER": True, "REVIEWER": True, "APPROVER": False})
        assert r["complete"] is False
        assert r["eligible_for_close"] is False

    def test_signoff_all_missing(self):
        r = FinancialCloseEngine.signoff_complete({})
        assert r["complete"] is False


# ============================================================================
# #100 Group Consolidation — CENTENNIAL (34)
# ============================================================================

class TestGroupConsolidation:

    def test_subsidiary_types_byte_for_byte(self):
        for t in ("WHOLLY_OWNED", "MAJORITY_OWNED", "ASSOCIATE",
                  "JOINT_VENTURE", "BRANCH"):
            assert t in SUBSIDIARY_TYPES
        assert len(SUBSIDIARY_TYPES) == 5

    def test_consolidation_methods_byte_for_byte(self):
        for m in ("FULL_CONSOLIDATION", "EQUITY_METHOD",
                  "PROPORTIONATE", "COST_METHOD"):
            assert m in CONSOLIDATION_METHODS
        assert len(CONSOLIDATION_METHODS) == 4

    def test_thresholds_byte_for_byte(self):
        assert CONTROL_THRESHOLD_PCT == Decimal("50")
        assert SIGNIFICANT_INFLUENCE_THRESHOLD_PCT == Decimal("20")
        assert WHOLLY_OWNED_THRESHOLD_PCT == Decimal("100")

    def test_elimination_types_byte_for_byte(self):
        for t in ("INTRA_GROUP_TRADING", "INTRA_GROUP_LOANS",
                  "INTRA_GROUP_DIVIDENDS", "UNREALIZED_PROFITS"):
            assert t in ELIMINATION_TYPES
        assert len(ELIMINATION_TYPES) == 4

    def test_translation_methods_byte_for_byte(self):
        for m in ("TEMPORAL_METHOD", "CURRENT_RATE_METHOD"):
            assert m in CURRENCY_TRANSLATION_METHODS

    def test_frequencies_byte_for_byte(self):
        for f in ("MONTHLY", "QUARTERLY", "ANNUAL"):
            assert f in CONSOLIDATION_FREQUENCIES

    def test_method_full_consolidation_majority(self):
        r = GroupConsolidationEngine.consolidation_method(Decimal("75"))
        assert r["method"] == "FULL_CONSOLIDATION"

    def test_method_full_consolidation_wholly(self):
        r = GroupConsolidationEngine.consolidation_method(Decimal("100"))
        assert r["method"] == "FULL_CONSOLIDATION"

    def test_method_equity(self):
        r = GroupConsolidationEngine.consolidation_method(Decimal("30"))
        assert r["method"] == "EQUITY_METHOD"

    def test_method_equity_boundary_20(self):
        r = GroupConsolidationEngine.consolidation_method(Decimal("20"))
        assert r["method"] == "EQUITY_METHOD"

    def test_method_equity_boundary_50(self):
        r = GroupConsolidationEngine.consolidation_method(Decimal("50"))
        assert r["method"] == "EQUITY_METHOD"

    def test_method_cost(self):
        r = GroupConsolidationEngine.consolidation_method(Decimal("10"))
        assert r["method"] == "COST_METHOD"

    def test_method_cost_boundary_19(self):
        r = GroupConsolidationEngine.consolidation_method(Decimal("19.99"))
        assert r["method"] == "COST_METHOD"

    def test_method_proportionate_jv(self):
        r = GroupConsolidationEngine.consolidation_method(
            Decimal("50"), is_joint_venture=True)
        assert r["method"] == "PROPORTIONATE"

    def test_method_missing_rule1(self):
        r = GroupConsolidationEngine.consolidation_method(None)
        assert r["method"] is None

    def test_method_invalid_over_100_rule6(self):
        r = GroupConsolidationEngine.consolidation_method(Decimal("150"))
        assert r["method"] is None

    def test_classification_wholly_owned(self):
        assert GroupConsolidationEngine.subsidiary_classification(
            Decimal("100")) == "WHOLLY_OWNED"

    def test_classification_majority(self):
        assert GroupConsolidationEngine.subsidiary_classification(
            Decimal("75")) == "MAJORITY_OWNED"

    def test_classification_associate(self):
        assert GroupConsolidationEngine.subsidiary_classification(
            Decimal("30")) == "ASSOCIATE"

    def test_classification_jv(self):
        assert GroupConsolidationEngine.subsidiary_classification(
            Decimal("50"), is_joint_venture=True) == "JOINT_VENTURE"

    def test_classification_branch(self):
        assert GroupConsolidationEngine.subsidiary_classification(
            Decimal("100"), is_branch=True) == "BRANCH"

    def test_classification_below_threshold_returns_none(self):
        assert GroupConsolidationEngine.subsidiary_classification(
            Decimal("10")) is None

    def test_elimination_intra_group_trading(self):
        r = GroupConsolidationEngine.elimination_amount(
            "INTRA_GROUP_TRADING", Decimal("5000000"))
        assert r["elimination"] == "-5000000"

    def test_elimination_unknown_rule6(self):
        r = GroupConsolidationEngine.elimination_amount("WEIRD", Decimal("1000000"))
        assert r["computed"] is False

    def test_elimination_missing_rule1(self):
        r = GroupConsolidationEngine.elimination_amount("INTRA_GROUP_LOANS", None)
        assert r["computed"] is False

    def test_nci_basic(self):
        r = GroupConsolidationEngine.non_controlling_interest(
            Decimal("1000000"), Decimal("75"))
        assert r["nci"] == "250000.00"

    def test_nci_wholly_owned_zero(self):
        r = GroupConsolidationEngine.non_controlling_interest(
            Decimal("1000000"), Decimal("100"))
        assert r["nci"] == "0.00"

    def test_nci_missing_rule1(self):
        r = GroupConsolidationEngine.non_controlling_interest(None, Decimal("75"))
        assert r["computed"] is False

    def test_nci_over_100_rule6(self):
        r = GroupConsolidationEngine.non_controlling_interest(
            Decimal("1000000"), Decimal("150"))
        assert r["computed"] is False

    def test_translation_current_rate(self):
        r = GroupConsolidationEngine.currency_translation(
            Decimal("1000000"), "CURRENT_RATE_METHOD",
            closing_rate=Decimal("130"))
        assert r["translated"] == "130000000.00"

    def test_translation_temporal_monetary(self):
        r = GroupConsolidationEngine.currency_translation(
            Decimal("1000000"), "TEMPORAL_METHOD",
            closing_rate=Decimal("130"), historical_rate=Decimal("100"),
            is_monetary=True)
        assert r["translated"] == "130000000.00"

    def test_translation_temporal_non_monetary(self):
        r = GroupConsolidationEngine.currency_translation(
            Decimal("1000000"), "TEMPORAL_METHOD",
            closing_rate=Decimal("130"), historical_rate=Decimal("100"),
            is_monetary=False)
        assert r["translated"] == "100000000.00"

    def test_translation_unknown_rule6(self):
        r = GroupConsolidationEngine.currency_translation(
            Decimal("1000000"), "WEIRD", closing_rate=Decimal("130"))
        assert r["computed"] is False

    def test_translation_missing_rate_rule1(self):
        r = GroupConsolidationEngine.currency_translation(
            Decimal("1000000"), "CURRENT_RATE_METHOD", closing_rate=None)
        assert r["computed"] is False
