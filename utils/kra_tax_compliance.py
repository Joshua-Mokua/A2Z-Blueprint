"""utils/kra_tax_compliance.py — v10.66: KRA tax compliance.

ENH-256 — Tax Compliance & Reporting. Cat B — finance arc 8/10.

Diagnostic Kenyan tax computation engine with deferred tax + return
package orchestration. Distinct from Standard #97
(utils/tax_compliance.py — base policy layer for VAT/CT/WHT/PAYE/
Excise rules). ENH-256 layers IAS 12 deferred tax + multi-tax
return package on top.

Five tax types covered:
  CORPORATION_TAX  — 30% standard / 25% preferential resident bank
                      / 37% permanent establishment branch
  VAT              — 16% standard / 0% zero-rated / EXEMPT
  WITHHOLDING_TAX  — varies by income type + customer residency
  EXCISE_DUTY      — 20% on banking-fee transactions
  DEFERRED_TAX     — IAS 12 — DTA/DTL on temporary differences

Per Rule 7, engine NEVER:
  - files returns with KRA (iTax)
  - submits VAT returns
  - withholds funds (computes only)
  - reverses prior-period assessments
  - mutates inputs

Per Rule 1, every TaxComputation surfaces taxable_basis +
rate_applied + computed_tax + applicable_rule + inputs_used +
framework_refs.

Pure stdlib (Decimal + frozen dataclasses + enums).
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Dict, List, Optional, Sequence, Tuple

SPEC_DEVIATION_NOTE = (
    "KRATaxComplianceEngine implements ENH-256. Distinct from "
    "Standard #97 (utils/tax_compliance.py — policy layer); "
    "ENH-256 adds IAS 12 deferred tax + multi-tax return "
    "package orchestration. Pure stdlib. Per Rule 1, every "
    "TaxComputation surfaces full provenance. Per Rule 7, "
    "engine DIAGNOSTIC ONLY — never files iTax, never submits "
    "VAT, never withholds funds, never reverses prior "
    "assessments, never mutates inputs."
)


class TaxType(Enum):
    CORPORATION_TAX = "CORPORATION_TAX"
    VAT = "VAT"
    WITHHOLDING_TAX = "WITHHOLDING_TAX"
    EXCISE_DUTY = "EXCISE_DUTY"
    DEFERRED_TAX = "DEFERRED_TAX"


class CorpTaxRegime(Enum):
    STANDARD_RESIDENT = "STANDARD_RESIDENT"
    PREFERENTIAL_BANK = "PREFERENTIAL_BANK"
    PERMANENT_ESTABLISHMENT = "PERMANENT_ESTABLISHMENT"


class VatStatus(Enum):
    STANDARD = "STANDARD"
    ZERO_RATED = "ZERO_RATED"
    EXEMPT = "EXEMPT"


class WhtIncomeType(Enum):
    DIVIDEND = "DIVIDEND"
    INTEREST = "INTEREST"
    ROYALTY = "ROYALTY"
    MGMT_FEE = "MGMT_FEE"
    PROFESSIONAL_FEE = "PROFESSIONAL_FEE"
    RENT = "RENT"


class ResidencyStatus(Enum):
    RESIDENT = "RESIDENT"
    NON_RESIDENT = "NON_RESIDENT"


class TemporaryDifferenceType(Enum):
    TAXABLE = "TAXABLE"
    DEDUCTIBLE = "DEDUCTIBLE"


@dataclass(frozen=True)
class CorpTaxInput:
    period: str
    accounting_profit_kes: Decimal
    permanent_addbacks_kes: Decimal
    permanent_deductions_kes: Decimal
    timing_differences_net_kes: Decimal
    regime: CorpTaxRegime

    def __post_init__(self) -> None:
        if not self.period:
            raise ValueError("period must be non-empty")
        if self.permanent_addbacks_kes < 0:
            raise ValueError("addbacks must be ≥ 0")
        if self.permanent_deductions_kes < 0:
            raise ValueError("deductions must be ≥ 0")


@dataclass(frozen=True)
class VatTransaction:
    transaction_id: str
    period: str
    base_amount_kes: Decimal
    status: VatStatus

    def __post_init__(self) -> None:
        if not self.transaction_id:
            raise ValueError(
                "transaction_id must be non-empty")
        if self.base_amount_kes < 0:
            raise ValueError("base_amount_kes must be ≥ 0")


@dataclass(frozen=True)
class WhtPayment:
    payment_id: str
    period: str
    income_type: WhtIncomeType
    gross_amount_kes: Decimal
    payee_residency: ResidencyStatus

    def __post_init__(self) -> None:
        if not self.payment_id:
            raise ValueError("payment_id must be non-empty")
        if self.gross_amount_kes < 0:
            raise ValueError(
                "gross_amount_kes must be ≥ 0")


@dataclass(frozen=True)
class ExciseTransaction:
    transaction_id: str
    period: str
    fee_amount_kes: Decimal

    def __post_init__(self) -> None:
        if not self.transaction_id:
            raise ValueError(
                "transaction_id must be non-empty")
        if self.fee_amount_kes < 0:
            raise ValueError("fee_amount_kes must be ≥ 0")


@dataclass(frozen=True)
class TemporaryDifference:
    description: str
    period: str
    amount_kes: Decimal
    diff_type: TemporaryDifferenceType

    def __post_init__(self) -> None:
        if not self.description:
            raise ValueError("description must be non-empty")
        if self.amount_kes < 0:
            raise ValueError("amount_kes must be ≥ 0")


@dataclass(frozen=True)
class TaxComputation:
    computation_id: str
    tax_type: TaxType
    period: str
    taxable_basis_kes: Decimal
    rate_applied: Decimal
    computed_tax_kes: Decimal
    applicable_rule: str
    inputs_used: Dict[str, str]
    framework_refs: Tuple[str, ...] = ()


@dataclass(frozen=True)
class DeferredTaxResult:
    period: str
    dtl_kes: Decimal
    dta_kes: Decimal
    net_dt_kes: Decimal
    rate_used: Decimal
    contributions: Tuple[
        Tuple[str, TemporaryDifferenceType, Decimal], ...]
    framework_refs: Tuple[str, ...] = ()


@dataclass(frozen=True)
class TaxReturnPackage:
    period: str
    computations: Tuple[TaxComputation, ...]
    deferred_tax: Optional[DeferredTaxResult]
    by_tax_type: Dict[str, Decimal]
    framework_refs: Tuple[str, ...]


class KRATaxComplianceEngine:
    CORP_TAX_RATES: Dict[CorpTaxRegime, Decimal] = {
        CorpTaxRegime.STANDARD_RESIDENT: Decimal("0.30"),
        CorpTaxRegime.PREFERENTIAL_BANK: Decimal("0.25"),
        CorpTaxRegime.PERMANENT_ESTABLISHMENT: Decimal("0.37"),
    }

    VAT_STANDARD_RATE: Decimal = Decimal("0.16")
    EXCISE_BANKING_RATE: Decimal = Decimal("0.20")

    WHT_RATES: Dict[
        Tuple[WhtIncomeType, ResidencyStatus], Decimal] = {
        (WhtIncomeType.DIVIDEND, ResidencyStatus.RESIDENT): Decimal("0.05"),
        (WhtIncomeType.DIVIDEND, ResidencyStatus.NON_RESIDENT): Decimal("0.15"),
        (WhtIncomeType.INTEREST, ResidencyStatus.RESIDENT): Decimal("0.15"),
        (WhtIncomeType.INTEREST, ResidencyStatus.NON_RESIDENT): Decimal("0.15"),
        (WhtIncomeType.ROYALTY, ResidencyStatus.RESIDENT): Decimal("0.05"),
        (WhtIncomeType.ROYALTY, ResidencyStatus.NON_RESIDENT): Decimal("0.20"),
        (WhtIncomeType.MGMT_FEE, ResidencyStatus.RESIDENT): Decimal("0.05"),
        (WhtIncomeType.MGMT_FEE, ResidencyStatus.NON_RESIDENT): Decimal("0.20"),
        (WhtIncomeType.PROFESSIONAL_FEE, ResidencyStatus.RESIDENT): Decimal("0.05"),
        (WhtIncomeType.PROFESSIONAL_FEE, ResidencyStatus.NON_RESIDENT): Decimal("0.20"),
        (WhtIncomeType.RENT, ResidencyStatus.RESIDENT): Decimal("0.10"),
        (WhtIncomeType.RENT, ResidencyStatus.NON_RESIDENT): Decimal("0.30"),
    }

    DEFAULT_DEFERRED_TAX_RATE: Decimal = Decimal("0.30")

    def compute_corp_tax(
        self, ci: CorpTaxInput,
    ) -> TaxComputation:
        taxable_income = (
            ci.accounting_profit_kes
            + ci.permanent_addbacks_kes
            - ci.permanent_deductions_kes
            - ci.timing_differences_net_kes)
        taxable_capped = (
            taxable_income if taxable_income >= 0
            else Decimal("0"))
        rate = self.CORP_TAX_RATES[ci.regime]
        tax = (taxable_capped * rate).quantize(
            Decimal("0.01"))
        return TaxComputation(
            computation_id=f"TAX-CORP-{ci.period}",
            tax_type=TaxType.CORPORATION_TAX,
            period=ci.period,
            taxable_basis_kes=taxable_capped,
            rate_applied=rate,
            computed_tax_kes=tax,
            applicable_rule=(
                f"Corporation Tax — KRA Income Tax Act / "
                f"{ci.regime.value}"),
            inputs_used={
                "accounting_profit": str(
                    ci.accounting_profit_kes),
                "permanent_addbacks": str(
                    ci.permanent_addbacks_kes),
                "permanent_deductions": str(
                    ci.permanent_deductions_kes),
                "timing_diff_net": str(
                    ci.timing_differences_net_kes),
                "computed_taxable_pre_cap": str(
                    taxable_income),
                "regime": ci.regime.value},
            framework_refs=(
                "ENH-256 §corporation_tax",
                "KRA Income Tax Act Section 3 + Section 35",
                f"Regime: {ci.regime.value}"))

    def compute_vat(
        self, transactions: Sequence[VatTransaction],
    ) -> Tuple[TaxComputation, ...]:
        by_key: Dict[
            Tuple[str, VatStatus],
            List[VatTransaction]] = {}
        for t in transactions:
            by_key.setdefault((t.period, t.status), []).append(t)
        comps: List[TaxComputation] = []
        for (period, status), txns in by_key.items():
            base = sum(
                (t.base_amount_kes for t in txns),
                Decimal("0"))
            if status == VatStatus.STANDARD:
                rate = self.VAT_STANDARD_RATE
                rule = "VAT Act — standard 16%"
            else:
                rate = Decimal("0")
                rule = (
                    "VAT Act — zero-rated"
                    if status == VatStatus.ZERO_RATED
                    else "VAT Act — exempt")
            tax = (base * rate).quantize(Decimal("0.01"))
            comps.append(TaxComputation(
                computation_id=(
                    f"TAX-VAT-{period}-{status.value}"),
                tax_type=TaxType.VAT, period=period,
                taxable_basis_kes=base, rate_applied=rate,
                computed_tax_kes=tax, applicable_rule=rule,
                inputs_used={
                    "txn_count": str(len(txns)),
                    "status": status.value},
                framework_refs=(
                    "ENH-256 §vat",
                    "KRA VAT Act 2013",
                    f"Status: {status.value}")))
        return tuple(comps)

    def compute_wht(
        self, payments: Sequence[WhtPayment],
    ) -> Tuple[TaxComputation, ...]:
        comps: List[TaxComputation] = []
        for p in payments:
            rate = self.WHT_RATES.get(
                (p.income_type, p.payee_residency))
            if rate is None:
                rate = Decimal("0")
                rule = (
                    f"Unsupported {p.income_type.value}/"
                    f"{p.payee_residency.value} — manual "
                    f"review required")
            else:
                rule = (
                    f"WHT — KRA ITA Schedule 5 / "
                    f"{p.income_type.value} / "
                    f"{p.payee_residency.value}")
            tax = (p.gross_amount_kes * rate).quantize(
                Decimal("0.01"))
            comps.append(TaxComputation(
                computation_id=f"TAX-WHT-{p.payment_id}",
                tax_type=TaxType.WITHHOLDING_TAX,
                period=p.period,
                taxable_basis_kes=p.gross_amount_kes,
                rate_applied=rate, computed_tax_kes=tax,
                applicable_rule=rule,
                inputs_used={
                    "income_type": p.income_type.value,
                    "residency": p.payee_residency.value,
                    "gross": str(p.gross_amount_kes)},
                framework_refs=(
                    "ENH-256 §wht",
                    "KRA Income Tax Act Schedule 5",
                    f"Income type: {p.income_type.value}",
                    f"Residency: {p.payee_residency.value}")))
        return tuple(comps)

    def compute_excise(
        self, transactions: Sequence[ExciseTransaction],
    ) -> Tuple[TaxComputation, ...]:
        by_period: Dict[str, Decimal] = {}
        counts: Dict[str, int] = {}
        for t in transactions:
            by_period[t.period] = (
                by_period.get(t.period, Decimal("0"))
                + t.fee_amount_kes)
            counts[t.period] = counts.get(t.period, 0) + 1
        comps: List[TaxComputation] = []
        for period, base in by_period.items():
            tax = (base * self.EXCISE_BANKING_RATE).quantize(
                Decimal("0.01"))
            comps.append(TaxComputation(
                computation_id=f"TAX-EXC-{period}",
                tax_type=TaxType.EXCISE_DUTY, period=period,
                taxable_basis_kes=base,
                rate_applied=self.EXCISE_BANKING_RATE,
                computed_tax_kes=tax,
                applicable_rule=(
                    "Excise Duty Act — banking fees 20%"),
                inputs_used={
                    "fee_total": str(base),
                    "txn_count": str(counts[period])},
                framework_refs=(
                    "ENH-256 §excise",
                    "Excise Duty Act 2015 — banking services",
                    f"Aggregated {counts[period]} fee txns")))
        return tuple(comps)

    def compute_deferred_tax(
        self, period: str,
        diffs: Sequence[TemporaryDifference],
        rate: Optional[Decimal] = None,
    ) -> DeferredTaxResult:
        rate_applied = (
            rate if rate is not None
            else self.DEFAULT_DEFERRED_TAX_RATE)
        dtl_total = Decimal("0")
        dta_total = Decimal("0")
        contribs: List[
            Tuple[str, TemporaryDifferenceType, Decimal]] = []
        for d in diffs:
            tax_effect = (d.amount_kes * rate_applied).quantize(
                Decimal("0.01"))
            if d.diff_type == TemporaryDifferenceType.TAXABLE:
                dtl_total += tax_effect
            else:
                dta_total += tax_effect
            contribs.append(
                (d.description, d.diff_type, tax_effect))
        return DeferredTaxResult(
            period=period, dtl_kes=dtl_total,
            dta_kes=dta_total,
            net_dt_kes=dtl_total - dta_total,
            rate_used=rate_applied,
            contributions=tuple(contribs),
            framework_refs=(
                "ENH-256 §deferred_tax",
                "IAS 12 — Income Taxes",
                "Per Rule 1 — all temporary differences "
                "surfaced individually"))

    def build_return_package(
        self, period: str,
        corp_tax_input: Optional[CorpTaxInput] = None,
        vat_transactions: Sequence[VatTransaction] = (),
        wht_payments: Sequence[WhtPayment] = (),
        excise_transactions: Sequence[ExciseTransaction] = (),
        temp_differences: Sequence[
            TemporaryDifference] = (),
        deferred_tax_rate: Optional[Decimal] = None,
    ) -> TaxReturnPackage:
        comps: List[TaxComputation] = []
        if corp_tax_input is not None:
            comps.append(self.compute_corp_tax(corp_tax_input))
        comps.extend(self.compute_vat(vat_transactions))
        comps.extend(self.compute_wht(wht_payments))
        comps.extend(self.compute_excise(excise_transactions))
        deferred = None
        if temp_differences:
            deferred = self.compute_deferred_tax(
                period, temp_differences,
                rate=deferred_tax_rate)
        by_type: Dict[str, Decimal] = {
            t.value: Decimal("0") for t in TaxType}
        for c in comps:
            by_type[c.tax_type.value] += c.computed_tax_kes
        if deferred is not None:
            by_type[TaxType.DEFERRED_TAX.value] = (
                deferred.net_dt_kes)
        return TaxReturnPackage(
            period=period, computations=tuple(comps),
            deferred_tax=deferred, by_tax_type=by_type,
            framework_refs=(
                "ENH-256 §build_return_package",
                "KRA + IAS 12 — Kenyan tax framework",
                "Per Rule 7 — diagnostic only; never files; "
                "never submits VAT returns; never withholds; "
                "never reverses prior assessments"))


# ════════════════════════════════════════════════════════════════════════
# Self-tests
# ════════════════════════════════════════════════════════════════════════

def _test_corp_tax_input_validates_period():
    try:
        CorpTaxInput(
            period="", accounting_profit_kes=Decimal("100"),
            permanent_addbacks_kes=Decimal("0"),
            permanent_deductions_kes=Decimal("0"),
            timing_differences_net_kes=Decimal("0"),
            regime=CorpTaxRegime.STANDARD_RESIDENT)
        assert False
    except ValueError:
        pass


def _test_vat_transaction_validates_id():
    try:
        VatTransaction(
            transaction_id="", period="2026-04",
            base_amount_kes=Decimal("100"),
            status=VatStatus.STANDARD)
        assert False
    except ValueError:
        pass


def _test_corp_tax_standard_resident():
    eng = KRATaxComplianceEngine()
    ci = CorpTaxInput(
        period="2026", accounting_profit_kes=Decimal("10000000"),
        permanent_addbacks_kes=Decimal("500000"),
        permanent_deductions_kes=Decimal("200000"),
        timing_differences_net_kes=Decimal("0"),
        regime=CorpTaxRegime.STANDARD_RESIDENT)
    c = eng.compute_corp_tax(ci)
    assert c.taxable_basis_kes == Decimal("10300000")
    assert c.rate_applied == Decimal("0.30")
    assert c.computed_tax_kes == Decimal("3090000.00")


def _test_corp_tax_loss_floor():
    eng = KRATaxComplianceEngine()
    ci = CorpTaxInput(
        period="2026",
        accounting_profit_kes=Decimal("-5000000"),
        permanent_addbacks_kes=Decimal("0"),
        permanent_deductions_kes=Decimal("0"),
        timing_differences_net_kes=Decimal("0"),
        regime=CorpTaxRegime.STANDARD_RESIDENT)
    c = eng.compute_corp_tax(ci)
    assert c.computed_tax_kes == Decimal("0.00")
    assert c.taxable_basis_kes == Decimal("0")
    assert "computed_taxable_pre_cap" in c.inputs_used


def _test_corp_tax_pe_branch_37pct():
    eng = KRATaxComplianceEngine()
    ci = CorpTaxInput(
        period="2026",
        accounting_profit_kes=Decimal("1000000"),
        permanent_addbacks_kes=Decimal("0"),
        permanent_deductions_kes=Decimal("0"),
        timing_differences_net_kes=Decimal("0"),
        regime=CorpTaxRegime.PERMANENT_ESTABLISHMENT)
    c = eng.compute_corp_tax(ci)
    assert c.rate_applied == Decimal("0.37")
    assert c.computed_tax_kes == Decimal("370000.00")


def _test_vat_standard_buckets():
    eng = KRATaxComplianceEngine()
    txns = (
        VatTransaction(
            transaction_id="t1", period="2026-04",
            base_amount_kes=Decimal("1000000"),
            status=VatStatus.STANDARD),
        VatTransaction(
            transaction_id="t2", period="2026-04",
            base_amount_kes=Decimal("500000"),
            status=VatStatus.STANDARD),
        VatTransaction(
            transaction_id="t3", period="2026-04",
            base_amount_kes=Decimal("200000"),
            status=VatStatus.ZERO_RATED),
    )
    comps = eng.compute_vat(txns)
    assert len(comps) == 2
    std = next(
        c for c in comps
        if c.applicable_rule.endswith("16%"))
    assert std.computed_tax_kes == Decimal("240000.00")
    zero = next(
        c for c in comps
        if "zero-rated" in c.applicable_rule)
    assert zero.computed_tax_kes == Decimal("0.00")


def _test_vat_exempt_no_tax():
    eng = KRATaxComplianceEngine()
    txns = (
        VatTransaction(
            transaction_id="t1", period="2026-04",
            base_amount_kes=Decimal("1000000"),
            status=VatStatus.EXEMPT),
    )
    comps = eng.compute_vat(txns)
    assert comps[0].computed_tax_kes == Decimal("0.00")
    assert "exempt" in comps[0].applicable_rule


def _test_wht_dividend_resident_5pct():
    eng = KRATaxComplianceEngine()
    p = WhtPayment(
        payment_id="p1", period="2026-04",
        income_type=WhtIncomeType.DIVIDEND,
        gross_amount_kes=Decimal("100000"),
        payee_residency=ResidencyStatus.RESIDENT)
    c = eng.compute_wht((p,))[0]
    assert c.rate_applied == Decimal("0.05")
    assert c.computed_tax_kes == Decimal("5000.00")


def _test_wht_royalty_non_resident_20pct():
    eng = KRATaxComplianceEngine()
    p = WhtPayment(
        payment_id="p1", period="2026-04",
        income_type=WhtIncomeType.ROYALTY,
        gross_amount_kes=Decimal("100000"),
        payee_residency=ResidencyStatus.NON_RESIDENT)
    c = eng.compute_wht((p,))[0]
    assert c.rate_applied == Decimal("0.20")
    assert c.computed_tax_kes == Decimal("20000.00")


def _test_wht_rent_non_resident_30pct():
    eng = KRATaxComplianceEngine()
    p = WhtPayment(
        payment_id="p1", period="2026-04",
        income_type=WhtIncomeType.RENT,
        gross_amount_kes=Decimal("100000"),
        payee_residency=ResidencyStatus.NON_RESIDENT)
    c = eng.compute_wht((p,))[0]
    assert c.rate_applied == Decimal("0.30")
    assert c.computed_tax_kes == Decimal("30000.00")


def _test_excise_banking_20pct():
    eng = KRATaxComplianceEngine()
    txns = (
        ExciseTransaction(
            transaction_id="t1", period="2026-04",
            fee_amount_kes=Decimal("10000")),
        ExciseTransaction(
            transaction_id="t2", period="2026-04",
            fee_amount_kes=Decimal("5000")),
    )
    comps = eng.compute_excise(txns)
    assert len(comps) == 1
    assert comps[0].computed_tax_kes == Decimal("3000.00")
    assert comps[0].rate_applied == Decimal("0.20")


def _test_deferred_tax_dtl():
    eng = KRATaxComplianceEngine()
    diffs = (
        TemporaryDifference(
            description="Accelerated tax depreciation",
            period="2026-04",
            amount_kes=Decimal("1000000"),
            diff_type=TemporaryDifferenceType.TAXABLE),
    )
    r = eng.compute_deferred_tax("2026-04", diffs)
    assert r.dtl_kes == Decimal("300000.00")
    assert r.dta_kes == Decimal("0")
    assert r.net_dt_kes == Decimal("300000.00")


def _test_deferred_tax_dta_offsets_dtl():
    eng = KRATaxComplianceEngine()
    diffs = (
        TemporaryDifference(
            description="Accel dep",
            period="2026-04",
            amount_kes=Decimal("1000000"),
            diff_type=TemporaryDifferenceType.TAXABLE),
        TemporaryDifference(
            description="Provisions",
            period="2026-04",
            amount_kes=Decimal("400000"),
            diff_type=TemporaryDifferenceType.DEDUCTIBLE),
    )
    r = eng.compute_deferred_tax("2026-04", diffs)
    assert r.dtl_kes == Decimal("300000.00")
    assert r.dta_kes == Decimal("120000.00")
    assert r.net_dt_kes == Decimal("180000.00")


def _test_build_return_package_orchestrates():
    eng = KRATaxComplianceEngine()
    ci = CorpTaxInput(
        period="2026", accounting_profit_kes=Decimal("1000000"),
        permanent_addbacks_kes=Decimal("0"),
        permanent_deductions_kes=Decimal("0"),
        timing_differences_net_kes=Decimal("0"),
        regime=CorpTaxRegime.STANDARD_RESIDENT)
    vat = (
        VatTransaction(
            transaction_id="v1", period="2026-04",
            base_amount_kes=Decimal("100000"),
            status=VatStatus.STANDARD),
    )
    wht = (
        WhtPayment(
            payment_id="w1", period="2026-04",
            income_type=WhtIncomeType.INTEREST,
            gross_amount_kes=Decimal("50000"),
            payee_residency=ResidencyStatus.RESIDENT),
    )
    pkg = eng.build_return_package(
        "2026-04", corp_tax_input=ci,
        vat_transactions=vat, wht_payments=wht)
    assert pkg.by_tax_type[TaxType.CORPORATION_TAX.value] == (
        Decimal("300000.00"))
    assert pkg.by_tax_type[TaxType.VAT.value] == Decimal("16000.00")
    assert pkg.by_tax_type[TaxType.WITHHOLDING_TAX.value] == (
        Decimal("7500.00"))


def _test_full_provenance():
    eng = KRATaxComplianceEngine()
    ci = CorpTaxInput(
        period="2026", accounting_profit_kes=Decimal("100"),
        permanent_addbacks_kes=Decimal("0"),
        permanent_deductions_kes=Decimal("0"),
        timing_differences_net_kes=Decimal("0"),
        regime=CorpTaxRegime.STANDARD_RESIDENT)
    c = eng.compute_corp_tax(ci)
    assert c.applicable_rule
    assert "regime" in c.inputs_used
    assert any("ENH-256" in r for r in c.framework_refs)
    assert any("KRA" in r for r in c.framework_refs)


def _test_engine_does_not_mutate_inputs():
    eng = KRATaxComplianceEngine()
    ci = CorpTaxInput(
        period="2026", accounting_profit_kes=Decimal("100000"),
        permanent_addbacks_kes=Decimal("0"),
        permanent_deductions_kes=Decimal("0"),
        timing_differences_net_kes=Decimal("0"),
        regime=CorpTaxRegime.STANDARD_RESIDENT)
    eng.compute_corp_tax(ci)
    assert ci.accounting_profit_kes == Decimal("100000")


def self_test() -> None:
    tests = [
        _test_corp_tax_input_validates_period,
        _test_vat_transaction_validates_id,
        _test_corp_tax_standard_resident,
        _test_corp_tax_loss_floor,
        _test_corp_tax_pe_branch_37pct,
        _test_vat_standard_buckets,
        _test_vat_exempt_no_tax,
        _test_wht_dividend_resident_5pct,
        _test_wht_royalty_non_resident_20pct,
        _test_wht_rent_non_resident_30pct,
        _test_excise_banking_20pct,
        _test_deferred_tax_dtl,
        _test_deferred_tax_dta_offsets_dtl,
        _test_build_return_package_orchestrates,
        _test_full_provenance,
        _test_engine_does_not_mutate_inputs,
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
            f"✗ kra_tax_compliance self-test: "
            f"{len(failed)} failures",
            file=sys.stderr)
        for name, msg in failed:
            print(f"  - {name}: {msg}", file=sys.stderr)
        raise SystemExit(1)
    print(
        f"✓ kra_tax_compliance self-test passed "
        f"({len(tests)} tests)")


if __name__ == "__main__":
    self_test()
