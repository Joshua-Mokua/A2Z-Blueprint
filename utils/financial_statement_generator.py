"""utils/financial_statement_generator.py — v10.65: FSG.

ENH-255 — Financial Statement Generator. Cat B — finance arc 7/10.

Diagnostic IFRS statement generator. Consumes ConsolidatedLine
output from ENH-251 and produces 5 IFRS statements:
  1. Balance Sheet (IAS 1 §54)
  2. Income Statement / P&L (IAS 1 §82)
  3. Other Comprehensive Income (IAS 1 §82A)
  4. Statement of Changes in Equity (IAS 1 §106)
  5. Cash Flow Statement (IAS 7) — caller supplies CF inputs since
     they're not derivable from a single-period TB

Per Rule 7, engine produces structured statement objects. It NEVER:
  - files statements with regulators (CMA, NSE, KRA)
  - serializes to PDF / XBRL / IFRS taxonomy schema
  - mutates inputs (frozen contract enforces this)
  - asserts auditor sign-off

Per Rule 1, every StatementLine surfaces line_code + description +
amount + parent_share + nci_share + source_account_codes +
framework_refs.

Pure stdlib (Decimal + frozen dataclasses + enums).
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Dict, List, Optional, Sequence, Tuple

from utils.consolidated_tb_engine import (
    ConsolidatedLine, ConsolidatedTrialBalance)
from utils.finance_close_orchestrator import AccountType

SPEC_DEVIATION_NOTE = (
    "FinancialStatementGenerator implements ENH-255 per IAS 1 + "
    "IAS 7. Pure stdlib (Decimal + dataclasses). Per Rule 1, "
    "every StatementLine surfaces full provenance. Per Rule 7, "
    "engine DIAGNOSTIC ONLY — produces structured statements; "
    "never files with regulators; never serializes to PDF/XBRL; "
    "never asserts auditor sign-off; never mutates inputs."
)


# ════════════════════════════════════════════════════════════════════════
# Enums
# ════════════════════════════════════════════════════════════════════════

class BsClassification(Enum):
    CURRENT_ASSET = "CURRENT_ASSET"
    NON_CURRENT_ASSET = "NON_CURRENT_ASSET"
    CURRENT_LIABILITY = "CURRENT_LIABILITY"
    NON_CURRENT_LIABILITY = "NON_CURRENT_LIABILITY"
    EQUITY_PARENT = "EQUITY_PARENT"
    EQUITY_NCI = "EQUITY_NCI"


class CashFlowSection(Enum):
    OPERATING = "OPERATING"
    INVESTING = "INVESTING"
    FINANCING = "FINANCING"


class OciClassification(Enum):
    """IAS 1 §82A — items by recyclability."""
    NEVER_RECYCLED = "NEVER_RECYCLED"   # revaluation, equity FV,
                                          # DB remeasurement
    RECYCLABLE_TO_PNL = "RECYCLABLE_TO_PNL"   # CTA, debt FV, CF hedge


# ════════════════════════════════════════════════════════════════════════
# Input dataclasses
# ════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class AccountClassification:
    """Maps account_code to BS/IS classification."""
    account_code: str
    bs_classification: Optional[BsClassification] = None
    is_revenue: bool = False
    is_expense: bool = False
    is_oci: bool = False
    oci_classification: Optional[OciClassification] = None
    cash_flow_section: Optional[CashFlowSection] = None
    line_label: str = ""

    def __post_init__(self) -> None:
        if not self.account_code:
            raise ValueError("account_code must be non-empty")
        flags = sum([
            self.bs_classification is not None,
            self.is_revenue, self.is_expense, self.is_oci])
        if flags == 0:
            raise ValueError(
                "account must be classified as one of "
                "BS / revenue / expense / OCI")
        if flags > 1:
            raise ValueError(
                "account must have exactly one classification")
        if self.is_oci and self.oci_classification is None:
            raise ValueError(
                "OCI account requires oci_classification")


@dataclass(frozen=True)
class CashFlowInput:
    """Caller-supplied CF item — engine doesn't derive these."""
    section: CashFlowSection
    description: str
    amount_kes: Decimal     # positive = inflow, negative = outflow

    def __post_init__(self) -> None:
        if not self.description:
            raise ValueError("description must be non-empty")


@dataclass(frozen=True)
class EquityMovement:
    """One movement in equity for the period."""
    component: str          # e.g. "Share Capital", "Retained Earnings"
    description: str        # e.g. "Profit for the year", "Dividends paid"
    amount_kes: Decimal     # positive = increase, negative = decrease

    def __post_init__(self) -> None:
        if not self.component:
            raise ValueError("component must be non-empty")


@dataclass(frozen=True)
class OpeningCashBalance:
    period: str
    opening_balance_kes: Decimal


# ════════════════════════════════════════════════════════════════════════
# Output dataclasses
# ════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class StatementLine:
    line_code: str
    description: str
    amount_kes: Decimal
    parent_share_kes: Decimal
    nci_share_kes: Decimal
    source_account_codes: Tuple[str, ...]
    framework_refs: Tuple[str, ...] = ()


@dataclass(frozen=True)
class BalanceSheet:
    period: str
    current_assets: Tuple[StatementLine, ...]
    non_current_assets: Tuple[StatementLine, ...]
    current_liabilities: Tuple[StatementLine, ...]
    non_current_liabilities: Tuple[StatementLine, ...]
    equity_parent: Tuple[StatementLine, ...]
    equity_nci: Tuple[StatementLine, ...]
    total_assets_kes: Decimal
    total_liabilities_kes: Decimal
    total_equity_kes: Decimal
    framework_refs: Tuple[str, ...] = ()


@dataclass(frozen=True)
class IncomeStatement:
    period: str
    revenue_lines: Tuple[StatementLine, ...]
    expense_lines: Tuple[StatementLine, ...]
    total_revenue_kes: Decimal
    total_expenses_kes: Decimal
    profit_before_tax_kes: Decimal
    framework_refs: Tuple[str, ...] = ()


@dataclass(frozen=True)
class OciStatement:
    period: str
    never_recycled_lines: Tuple[StatementLine, ...]
    recyclable_lines: Tuple[StatementLine, ...]
    cumulative_translation_adjustment_kes: Decimal
    total_oci_kes: Decimal
    framework_refs: Tuple[str, ...] = ()


@dataclass(frozen=True)
class EquityChanges:
    period: str
    movements: Tuple[EquityMovement, ...]
    by_component: Dict[str, Decimal]
    total_change_kes: Decimal
    framework_refs: Tuple[str, ...] = ()


@dataclass(frozen=True)
class CashFlowStatement:
    period: str
    operating_lines: Tuple[CashFlowInput, ...]
    investing_lines: Tuple[CashFlowInput, ...]
    financing_lines: Tuple[CashFlowInput, ...]
    net_operating_kes: Decimal
    net_investing_kes: Decimal
    net_financing_kes: Decimal
    net_change_kes: Decimal
    opening_cash_kes: Decimal
    closing_cash_kes: Decimal
    framework_refs: Tuple[str, ...] = ()


@dataclass(frozen=True)
class FinancialStatementPackage:
    period: str
    presentation_currency: str
    balance_sheet: BalanceSheet
    income_statement: IncomeStatement
    oci_statement: OciStatement
    equity_changes: Optional[EquityChanges]
    cash_flow_statement: Optional[CashFlowStatement]
    findings: Tuple[str, ...]
    framework_refs: Tuple[str, ...]


# ════════════════════════════════════════════════════════════════════════
# Engine
# ════════════════════════════════════════════════════════════════════════

class FinancialStatementGenerator:
    """Diagnostic IFRS statement generator."""

    @staticmethod
    def _net_amount(line: ConsolidatedLine) -> Decimal:
        """Net post-elimination Dr-Cr."""
        return (
            line.post_elimination_dr
            - line.post_elimination_cr)

    @staticmethod
    def _net_parent(line: ConsolidatedLine) -> Decimal:
        return line.parent_share_dr - line.parent_share_cr

    @staticmethod
    def _net_nci(line: ConsolidatedLine) -> Decimal:
        return line.nci_share_dr - line.nci_share_cr

    def generate_package(
        self,
        consolidated_tb: ConsolidatedTrialBalance,
        classifications: Sequence[AccountClassification],
        cash_flow_inputs: Sequence[CashFlowInput] = (),
        equity_movements: Sequence[EquityMovement] = (),
        opening_cash_balance_kes: Optional[Decimal] = None,
    ) -> FinancialStatementPackage:
        cls_index: Dict[str, AccountClassification] = {
            c.account_code: c for c in classifications}

        # Bucket consolidated lines by classification
        bs_buckets: Dict[
            BsClassification, List[StatementLine]] = {
            cl: [] for cl in BsClassification}
        revenue_lines: List[StatementLine] = []
        expense_lines: List[StatementLine] = []
        oci_never: List[StatementLine] = []
        oci_recyclable: List[StatementLine] = []
        findings: List[str] = []

        for line in consolidated_tb.lines:
            cls = cls_index.get(line.account_code)
            if cls is None:
                findings.append(
                    f"unclassified account: {line.account_code} "
                    f"— line excluded from statements")
                continue
            net_amount = self._net_amount(line)
            net_parent = self._net_parent(line)
            net_nci = self._net_nci(line)
            sline = StatementLine(
                line_code=line.account_code,
                description=cls.line_label or line.account_code,
                amount_kes=net_amount,
                parent_share_kes=net_parent,
                nci_share_kes=net_nci,
                source_account_codes=(line.account_code,),
                framework_refs=(
                    "ENH-255 §classification",
                    f"source ENH-251 line {line.account_code}"))
            if cls.bs_classification is not None:
                bs_buckets[cls.bs_classification].append(sline)
            elif cls.is_revenue:
                revenue_lines.append(sline)
            elif cls.is_expense:
                expense_lines.append(sline)
            elif cls.is_oci:
                if (cls.oci_classification
                        == OciClassification.NEVER_RECYCLED):
                    oci_never.append(sline)
                else:
                    oci_recyclable.append(sline)

        # ── Balance Sheet ────────────────────────────────────────
        # Assets are Dr-balance: positive net = asset value
        # Liabilities/equity are Cr-balance: negative net = liability/equity
        # We invert sign for liabilities and equity to display positively
        def _flip_for_credit_natured(
            lines: List[StatementLine],
        ) -> Tuple[StatementLine, ...]:
            return tuple(
                StatementLine(
                    line_code=l.line_code,
                    description=l.description,
                    amount_kes=-l.amount_kes,
                    parent_share_kes=-l.parent_share_kes,
                    nci_share_kes=-l.nci_share_kes,
                    source_account_codes=l.source_account_codes,
                    framework_refs=l.framework_refs)
                for l in lines)

        current_a = tuple(bs_buckets[BsClassification.CURRENT_ASSET])
        non_current_a = tuple(
            bs_buckets[BsClassification.NON_CURRENT_ASSET])
        current_l = _flip_for_credit_natured(
            bs_buckets[BsClassification.CURRENT_LIABILITY])
        non_current_l = _flip_for_credit_natured(
            bs_buckets[BsClassification.NON_CURRENT_LIABILITY])
        equity_parent = _flip_for_credit_natured(
            bs_buckets[BsClassification.EQUITY_PARENT])
        equity_nci = _flip_for_credit_natured(
            bs_buckets[BsClassification.EQUITY_NCI])

        total_assets = sum(
            (l.amount_kes for l in current_a + non_current_a),
            Decimal("0"))
        total_liabilities = sum(
            (l.amount_kes for l in current_l + non_current_l),
            Decimal("0"))
        total_equity = sum(
            (l.amount_kes
             for l in equity_parent + equity_nci),
            Decimal("0"))

        bs = BalanceSheet(
            period=consolidated_tb.period,
            current_assets=current_a,
            non_current_assets=non_current_a,
            current_liabilities=current_l,
            non_current_liabilities=non_current_l,
            equity_parent=equity_parent,
            equity_nci=equity_nci,
            total_assets_kes=total_assets,
            total_liabilities_kes=total_liabilities,
            total_equity_kes=total_equity,
            framework_refs=(
                "ENH-255 §balance_sheet",
                "IAS 1 §54 — minimum line items"))

        # Sanity: assets = liab + equity (caller can interrogate;
        # variance is non-fatal because OCI / retained earnings /
        # period P&L flow into equity outside this engine's scope)
        bs_imbalance = (
            total_assets - total_liabilities - total_equity)
        if abs(bs_imbalance) > Decimal("1"):
            findings.append(
                f"balance sheet imbalance: assets {total_assets} "
                f"vs liab+equity "
                f"{total_liabilities + total_equity} "
                f"(variance {bs_imbalance}) — note period P&L "
                f"and OCI flow to equity outside this engine")

        # ── Income Statement ─────────────────────────────────────
        # Revenue is Cr-balance (flip), Expenses are Dr-balance
        rev_flipped = _flip_for_credit_natured(revenue_lines)
        total_rev = sum(
            (l.amount_kes for l in rev_flipped), Decimal("0"))
        total_exp = sum(
            (l.amount_kes for l in expense_lines), Decimal("0"))
        pbt = total_rev - total_exp
        is_stmt = IncomeStatement(
            period=consolidated_tb.period,
            revenue_lines=rev_flipped,
            expense_lines=tuple(expense_lines),
            total_revenue_kes=total_rev,
            total_expenses_kes=total_exp,
            profit_before_tax_kes=pbt,
            framework_refs=(
                "ENH-255 §income_statement",
                "IAS 1 §82 — minimum line items"))

        # ── OCI ──────────────────────────────────────────────────
        oci_total = sum(
            (-l.amount_kes
             for l in oci_never + oci_recyclable),
            Decimal("0"))
        # CTA from ENH-251 is added to recyclable OCI total
        cta = (
            consolidated_tb
            .cumulative_translation_adjustment_kes)
        oci_total += cta
        oci_stmt = OciStatement(
            period=consolidated_tb.period,
            never_recycled_lines=tuple(oci_never),
            recyclable_lines=tuple(oci_recyclable),
            cumulative_translation_adjustment_kes=cta,
            total_oci_kes=oci_total,
            framework_refs=(
                "ENH-255 §oci",
                "IAS 1 §82A — OCI items by recyclability",
                "IAS 21 — CTA flows to OCI cumulative "
                "translation reserve"))

        # ── Equity changes (optional — caller-supplied) ──────────
        equity_changes = None
        if equity_movements:
            by_component: Dict[str, Decimal] = {}
            for m in equity_movements:
                by_component[m.component] = (
                    by_component.get(m.component, Decimal("0"))
                    + m.amount_kes)
            equity_changes = EquityChanges(
                period=consolidated_tb.period,
                movements=tuple(equity_movements),
                by_component=by_component,
                total_change_kes=sum(
                    by_component.values(), Decimal("0")),
                framework_refs=(
                    "ENH-255 §equity",
                    "IAS 1 §106 — statement of changes in equity"))

        # ── Cash flow (optional) ─────────────────────────────────
        cf_stmt = None
        if cash_flow_inputs:
            op = tuple(
                cf for cf in cash_flow_inputs
                if cf.section == CashFlowSection.OPERATING)
            inv = tuple(
                cf for cf in cash_flow_inputs
                if cf.section == CashFlowSection.INVESTING)
            fin = tuple(
                cf for cf in cash_flow_inputs
                if cf.section == CashFlowSection.FINANCING)
            net_op = sum(
                (c.amount_kes for c in op), Decimal("0"))
            net_inv = sum(
                (c.amount_kes for c in inv), Decimal("0"))
            net_fin = sum(
                (c.amount_kes for c in fin), Decimal("0"))
            net_change = net_op + net_inv + net_fin
            opening = (
                opening_cash_balance_kes
                if opening_cash_balance_kes is not None
                else Decimal("0"))
            closing = opening + net_change
            cf_stmt = CashFlowStatement(
                period=consolidated_tb.period,
                operating_lines=op,
                investing_lines=inv,
                financing_lines=fin,
                net_operating_kes=net_op,
                net_investing_kes=net_inv,
                net_financing_kes=net_fin,
                net_change_kes=net_change,
                opening_cash_kes=opening,
                closing_cash_kes=closing,
                framework_refs=(
                    "ENH-255 §cash_flow",
                    "IAS 7 — cash flow statement structure",
                    "Caller supplies CF items — not derivable "
                    "from single-period TB"))

        return FinancialStatementPackage(
            period=consolidated_tb.period,
            presentation_currency=(
                consolidated_tb.presentation_currency),
            balance_sheet=bs,
            income_statement=is_stmt,
            oci_statement=oci_stmt,
            equity_changes=equity_changes,
            cash_flow_statement=cf_stmt,
            findings=tuple(findings),
            framework_refs=(
                "ENH-255 §generate_package",
                "IAS 1 + IAS 7 — IFRS presentation framework",
                "Per Rule 7 — produces structured statements; "
                "never files; never serializes; never asserts "
                "auditor sign-off"))


# ════════════════════════════════════════════════════════════════════════
# Self-tests
# ════════════════════════════════════════════════════════════════════════

def _make_tb_line(
    code, atype, dr=Decimal("0"), cr=Decimal("0"),
    parent_dr=None, parent_cr=None,
    nci_dr=Decimal("0"), nci_cr=Decimal("0"),
):
    if parent_dr is None:
        parent_dr = dr - nci_dr
    if parent_cr is None:
        parent_cr = cr - nci_cr
    return ConsolidatedLine(
        account_code=code, account_type=atype,
        entity_contributions=(),
        pre_elimination_dr=dr, pre_elimination_cr=cr,
        eliminations_applied_dr=Decimal("0"),
        eliminations_applied_cr=Decimal("0"),
        post_elimination_dr=dr, post_elimination_cr=cr,
        nci_share_dr=nci_dr, nci_share_cr=nci_cr,
        parent_share_dr=parent_dr, parent_share_cr=parent_cr,
        framework_refs=("ENH-251",))


def _make_tb(lines, period="2026-04",
             pres_curr="KES", cta=Decimal("0")):
    total_dr = sum(
        (l.post_elimination_dr for l in lines), Decimal("0"))
    total_cr = sum(
        (l.post_elimination_cr for l in lines), Decimal("0"))
    return ConsolidatedTrialBalance(
        period=period,
        presentation_currency=pres_curr,
        lines=tuple(lines),
        findings=(),
        entities_consolidated=1,
        eliminations_applied_count=0,
        total_dr=total_dr,
        total_cr=total_cr,
        cumulative_translation_adjustment_kes=cta,
        framework_refs=("ENH-251",))


def _test_classification_validates_at_least_one_flag():
    try:
        AccountClassification(
            account_code="X", bs_classification=None)
        assert False
    except ValueError:
        pass


def _test_classification_validates_single_flag():
    try:
        AccountClassification(
            account_code="X",
            bs_classification=BsClassification.CURRENT_ASSET,
            is_revenue=True)
        assert False
    except ValueError:
        pass


def _test_oci_requires_oci_classification():
    try:
        AccountClassification(
            account_code="X", is_oci=True,
            oci_classification=None)
        assert False
    except ValueError:
        pass


def _test_simple_balance_sheet():
    eng = FinancialStatementGenerator()
    tb_lines = [
        _make_tb_line(
            "1000", AccountType.ASSET,
            dr=Decimal("100000")),
        _make_tb_line(
            "2000", AccountType.LIABILITY,
            cr=Decimal("60000")),
        _make_tb_line(
            "3000", AccountType.EQUITY,
            cr=Decimal("40000")),
    ]
    tb = _make_tb(tb_lines)
    cls = (
        AccountClassification(
            account_code="1000",
            bs_classification=BsClassification.CURRENT_ASSET,
            line_label="Cash"),
        AccountClassification(
            account_code="2000",
            bs_classification=(
                BsClassification.CURRENT_LIABILITY),
            line_label="Trade Payables"),
        AccountClassification(
            account_code="3000",
            bs_classification=BsClassification.EQUITY_PARENT,
            line_label="Share Capital"),
    )
    pkg = eng.generate_package(tb, cls)
    bs = pkg.balance_sheet
    assert bs.total_assets_kes == Decimal("100000")
    assert bs.total_liabilities_kes == Decimal("60000")
    assert bs.total_equity_kes == Decimal("40000")
    # Balanced
    assert (
        bs.total_assets_kes
        == bs.total_liabilities_kes + bs.total_equity_kes)


def _test_income_statement_pbt():
    eng = FinancialStatementGenerator()
    tb_lines = [
        _make_tb_line(
            "4000", AccountType.REVENUE,
            cr=Decimal("100000")),
        _make_tb_line(
            "5000", AccountType.EXPENSE,
            dr=Decimal("70000")),
    ]
    tb = _make_tb(tb_lines)
    cls = (
        AccountClassification(
            account_code="4000", is_revenue=True,
            line_label="Revenue"),
        AccountClassification(
            account_code="5000", is_expense=True,
            line_label="Operating Expenses"),
    )
    pkg = eng.generate_package(tb, cls)
    is_stmt = pkg.income_statement
    assert is_stmt.total_revenue_kes == Decimal("100000")
    assert is_stmt.total_expenses_kes == Decimal("70000")
    assert is_stmt.profit_before_tax_kes == Decimal("30000")


def _test_oci_with_cta_from_consolidation():
    eng = FinancialStatementGenerator()
    tb = _make_tb(
        [], cta=Decimal("50000"))
    pkg = eng.generate_package(tb, ())
    assert pkg.oci_statement.cumulative_translation_adjustment_kes == (
        Decimal("50000"))
    assert pkg.oci_statement.total_oci_kes == Decimal("50000")


def _test_oci_recyclable_vs_never():
    eng = FinancialStatementGenerator()
    tb_lines = [
        _make_tb_line(
            "OCI-REVAL", AccountType.EQUITY,
            cr=Decimal("20000")),  # revaluation = NEVER_RECYCLED
        _make_tb_line(
            "OCI-CFH", AccountType.EQUITY,
            cr=Decimal("10000")),  # cash flow hedge = RECYCLABLE
    ]
    tb = _make_tb(tb_lines)
    cls = (
        AccountClassification(
            account_code="OCI-REVAL", is_oci=True,
            oci_classification=(
                OciClassification.NEVER_RECYCLED),
            line_label="Revaluation Surplus"),
        AccountClassification(
            account_code="OCI-CFH", is_oci=True,
            oci_classification=(
                OciClassification.RECYCLABLE_TO_PNL),
            line_label="CF Hedge Reserve"),
    )
    pkg = eng.generate_package(tb, cls)
    assert len(pkg.oci_statement.never_recycled_lines) == 1
    assert len(pkg.oci_statement.recyclable_lines) == 1


def _test_unclassified_account_surfaces_finding():
    eng = FinancialStatementGenerator()
    tb_lines = [
        _make_tb_line(
            "MYSTERY-ACCT", AccountType.ASSET,
            dr=Decimal("999")),
    ]
    tb = _make_tb(tb_lines)
    pkg = eng.generate_package(tb, ())
    assert any(
        "unclassified" in f for f in pkg.findings)


def _test_cash_flow_statement_assembly():
    eng = FinancialStatementGenerator()
    tb = _make_tb([])
    cf_inputs = (
        CashFlowInput(
            section=CashFlowSection.OPERATING,
            description="Profit before tax",
            amount_kes=Decimal("100000")),
        CashFlowInput(
            section=CashFlowSection.OPERATING,
            description="Depreciation add-back",
            amount_kes=Decimal("20000")),
        CashFlowInput(
            section=CashFlowSection.INVESTING,
            description="PPE purchases",
            amount_kes=Decimal("-50000")),
        CashFlowInput(
            section=CashFlowSection.FINANCING,
            description="Dividends paid",
            amount_kes=Decimal("-30000")),
    )
    pkg = eng.generate_package(
        tb, (), cash_flow_inputs=cf_inputs,
        opening_cash_balance_kes=Decimal("200000"))
    cf = pkg.cash_flow_statement
    assert cf is not None
    assert cf.net_operating_kes == Decimal("120000")
    assert cf.net_investing_kes == Decimal("-50000")
    assert cf.net_financing_kes == Decimal("-30000")
    assert cf.net_change_kes == Decimal("40000")
    assert cf.opening_cash_kes == Decimal("200000")
    assert cf.closing_cash_kes == Decimal("240000")


def _test_cash_flow_input_validates_description():
    try:
        CashFlowInput(
            section=CashFlowSection.OPERATING,
            description="", amount_kes=Decimal("1"))
        assert False
    except ValueError:
        pass


def _test_no_cash_flow_input_yields_no_cf_statement():
    eng = FinancialStatementGenerator()
    tb = _make_tb([])
    pkg = eng.generate_package(tb, ())
    assert pkg.cash_flow_statement is None


def _test_equity_movements_aggregated_by_component():
    eng = FinancialStatementGenerator()
    tb = _make_tb([])
    movements = (
        EquityMovement(
            component="Retained Earnings",
            description="Profit for the year",
            amount_kes=Decimal("500000")),
        EquityMovement(
            component="Retained Earnings",
            description="Dividends paid",
            amount_kes=Decimal("-200000")),
        EquityMovement(
            component="Share Capital",
            description="Shares issued",
            amount_kes=Decimal("1000000")),
    )
    pkg = eng.generate_package(
        tb, (), equity_movements=movements)
    eq = pkg.equity_changes
    assert eq is not None
    assert eq.by_component["Retained Earnings"] == (
        Decimal("300000"))
    assert eq.by_component["Share Capital"] == (
        Decimal("1000000"))
    assert eq.total_change_kes == Decimal("1300000")


def _test_nci_split_in_balance_sheet():
    eng = FinancialStatementGenerator()
    # 80% owned sub equity 1m → NCI 200k, parent 800k
    tb_lines = [
        _make_tb_line(
            "3000", AccountType.EQUITY,
            cr=Decimal("1000000"),
            parent_cr=Decimal("800000"),
            nci_cr=Decimal("200000")),
    ]
    tb = _make_tb(tb_lines)
    cls = (
        AccountClassification(
            account_code="3000",
            bs_classification=BsClassification.EQUITY_PARENT,
            line_label="Subsidiary Equity"),
    )
    pkg = eng.generate_package(tb, cls)
    eq_line = pkg.balance_sheet.equity_parent[0]
    # Flipped to positive presentation
    assert eq_line.amount_kes == Decimal("1000000")
    assert eq_line.parent_share_kes == Decimal("800000")
    assert eq_line.nci_share_kes == Decimal("200000")


def _test_full_provenance():
    eng = FinancialStatementGenerator()
    tb_lines = [
        _make_tb_line(
            "1000", AccountType.ASSET, dr=Decimal("1000")),
    ]
    tb = _make_tb(tb_lines)
    cls = (
        AccountClassification(
            account_code="1000",
            bs_classification=BsClassification.CURRENT_ASSET,
            line_label="Cash"),
    )
    pkg = eng.generate_package(tb, cls)
    assert any(
        "ENH-255" in r for r in pkg.framework_refs)
    assert any(
        "Rule 7" in r for r in pkg.framework_refs)
    line = pkg.balance_sheet.current_assets[0]
    assert "1000" in line.source_account_codes
    assert any("ENH-255" in r for r in line.framework_refs)


def _test_engine_does_not_mutate_inputs():
    eng = FinancialStatementGenerator()
    tb_lines = [
        _make_tb_line(
            "1000", AccountType.ASSET, dr=Decimal("1000")),
    ]
    tb = _make_tb(tb_lines)
    eng.generate_package(tb, ())
    assert tb.lines[0].post_elimination_dr == Decimal("1000")


def _test_balance_sheet_imbalance_surfaces_finding():
    eng = FinancialStatementGenerator()
    tb_lines = [
        _make_tb_line(
            "1000", AccountType.ASSET, dr=Decimal("100000")),
        _make_tb_line(
            "2000", AccountType.LIABILITY,
            cr=Decimal("30000")),
        # Equity is missing → BS unbalanced
    ]
    tb = _make_tb(tb_lines)
    cls = (
        AccountClassification(
            account_code="1000",
            bs_classification=BsClassification.CURRENT_ASSET,
            line_label="Cash"),
        AccountClassification(
            account_code="2000",
            bs_classification=(
                BsClassification.CURRENT_LIABILITY),
            line_label="Payables"),
    )
    pkg = eng.generate_package(tb, cls)
    assert any(
        "balance sheet imbalance" in f
        for f in pkg.findings)


def _test_presentation_currency_propagated():
    eng = FinancialStatementGenerator()
    tb = _make_tb([], pres_curr="USD")
    pkg = eng.generate_package(tb, ())
    assert pkg.presentation_currency == "USD"


def self_test() -> None:
    tests = [
        _test_classification_validates_at_least_one_flag,
        _test_classification_validates_single_flag,
        _test_oci_requires_oci_classification,
        _test_simple_balance_sheet,
        _test_income_statement_pbt,
        _test_oci_with_cta_from_consolidation,
        _test_oci_recyclable_vs_never,
        _test_unclassified_account_surfaces_finding,
        _test_cash_flow_statement_assembly,
        _test_cash_flow_input_validates_description,
        _test_no_cash_flow_input_yields_no_cf_statement,
        _test_equity_movements_aggregated_by_component,
        _test_nci_split_in_balance_sheet,
        _test_full_provenance,
        _test_engine_does_not_mutate_inputs,
        _test_balance_sheet_imbalance_surfaces_finding,
        _test_presentation_currency_propagated,
    ]
    failed = []
    for t in tests:
        try:
            t()
        except AssertionError as e:
            failed.append((t.__name__, str(e)))
        except Exception as e:
            failed.append((t.__name__, f"{type(e).__name__}: {e}"))
    if failed:
        print(
            f"✗ financial_statement_generator self-test: "
            f"{len(failed)} failures",
            file=sys.stderr)
        for name, msg in failed:
            print(f"  - {name}: {msg}", file=sys.stderr)
        raise SystemExit(1)
    print(
        f"✓ financial_statement_generator self-test passed "
        f"({len(tests)} tests)")


if __name__ == "__main__":
    self_test()
