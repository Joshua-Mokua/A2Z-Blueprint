"""utils/multi_entity_currency.py — v10.67: ME&MC accounting.

ENH-257 — Multi-Entity & Multi-Currency Accounting. Cat B —
finance arc 9/10.

Diagnostic multi-currency journal validation + IAS 21 period-end
FX revaluation + inter-entity transfer journal recommender.
Distinct from ENH-251 (consolidated_tb_engine) which handles
TB-level consolidation FX translation; ENH-257 handles
transaction-level multi-currency accounting before TBs are
extracted.

Three capabilities:
  1. validate_multi_currency_journal — enforces per-entry
     currency consistency + balanced D/C in transaction currency
     + functional-currency conversion at supplied spot rate
  2. revalue_monetary_balances — IAS 21 §23 — period-end
     remeasurement of foreign-currency monetary items at closing
     rate; surfaces FX gain/loss for caller to post (engine
     never posts)
  3. recommend_inter_entity_transfer — produces mirror journal
     pair for caller approval; engine NEVER posts the journals

Per Rule 7, engine NEVER:
  - posts journals (recommends only)
  - auto-revalues without operator review
  - sources FX rates from market (caller supplies)
  - decides which monetary items qualify (caller flags)
  - mutates inputs

Per Rule 1, every output dataclass surfaces full inputs +
framework refs.

Pure stdlib (Decimal + frozen dataclasses + enums).
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Dict, List, Optional, Sequence, Tuple

SPEC_DEVIATION_NOTE = (
    "MultiEntityCurrencyEngine implements ENH-257 — "
    "transaction-level multi-currency accounting per IAS 21. "
    "Distinct from ENH-251 (TB-level consolidation FX). Pure "
    "stdlib. Per Rule 1, every output surfaces full inputs + "
    "framework refs. Per Rule 7, engine DIAGNOSTIC ONLY — "
    "never posts journals, never auto-revalues, never sources "
    "FX rates from market, never decides monetary item "
    "classification, never mutates inputs."
)


class JournalIssue(Enum):
    UNBALANCED = "UNBALANCED"
    MIXED_CURRENCY_LINES = "MIXED_CURRENCY_LINES"
    MISSING_FX_RATE = "MISSING_FX_RATE"
    NEGATIVE_AMOUNT = "NEGATIVE_AMOUNT"
    EMPTY_JOURNAL = "EMPTY_JOURNAL"


class RevalSeverity(Enum):
    NONE = "NONE"           # zero or trivial gain/loss
    LOW = "LOW"             # < 1% of base
    MEDIUM = "MEDIUM"       # 1-5%
    HIGH = "HIGH"           # ≥ 5%


# ════════════════════════════════════════════════════════════════════════
# Input dataclasses
# ════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class JournalLine:
    line_id: str
    entity_id: str
    account_code: str
    debit_txn_currency: Decimal
    credit_txn_currency: Decimal
    transaction_currency: str   # ISO code

    def __post_init__(self) -> None:
        if not self.line_id:
            raise ValueError("line_id must be non-empty")
        if not self.entity_id:
            raise ValueError("entity_id must be non-empty")
        if not self.transaction_currency:
            raise ValueError(
                "transaction_currency must be non-empty")
        if (self.debit_txn_currency < 0
                or self.credit_txn_currency < 0):
            raise ValueError("amounts must be ≥ 0")


@dataclass(frozen=True)
class FxSpotRate:
    """One spot rate from txn currency to functional currency."""
    transaction_currency: str
    functional_currency: str
    rate: Decimal      # 1 unit txn = N functional
    rate_date: str

    def __post_init__(self) -> None:
        if self.rate <= 0:
            raise ValueError("rate must be > 0")


@dataclass(frozen=True)
class MonetaryBalance:
    """A foreign-currency monetary item to revalue at period end."""
    balance_id: str
    entity_id: str
    account_code: str
    currency: str
    txn_currency_balance: Decimal     # signed: + asset/Dr, - liab/Cr
    historical_functional_balance: Decimal   # at original rate

    def __post_init__(self) -> None:
        if not self.balance_id:
            raise ValueError("balance_id must be non-empty")
        if not self.currency:
            raise ValueError("currency must be non-empty")


@dataclass(frozen=True)
class InterEntityTransferRequest:
    request_id: str
    from_entity: str
    to_entity: str
    amount_kes: Decimal
    purpose: str       # "loan", "expense_recharge", etc.

    def __post_init__(self) -> None:
        if not self.request_id:
            raise ValueError("request_id must be non-empty")
        if self.from_entity == self.to_entity:
            raise ValueError(
                "from_entity must differ from to_entity")
        if self.amount_kes <= 0:
            raise ValueError("amount_kes must be > 0")
        if not self.purpose:
            raise ValueError("purpose must be non-empty")


# ════════════════════════════════════════════════════════════════════════
# Output dataclasses
# ════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class JournalValidation:
    journal_id: str
    is_valid: bool
    issues: Tuple[Tuple[JournalIssue, str], ...]
    total_dr_txn: Decimal
    total_cr_txn: Decimal
    transaction_currency: str
    functional_dr: Decimal
    functional_cr: Decimal
    fx_rate_used: Decimal
    framework_refs: Tuple[str, ...] = ()


@dataclass(frozen=True)
class RevaluationFinding:
    finding_id: str
    balance_id: str
    entity_id: str
    currency: str
    txn_balance: Decimal
    historical_functional: Decimal
    closing_rate: Decimal
    revalued_functional: Decimal
    fx_gain_loss_kes: Decimal     # +ve = gain, -ve = loss
    severity: RevalSeverity
    description: str
    framework_refs: Tuple[str, ...] = ()


@dataclass(frozen=True)
class InterEntityTransferRecommendation:
    request_id: str
    debit_leg_entity: str
    debit_leg_account: str
    credit_leg_entity: str
    credit_leg_account: str
    amount_kes: Decimal
    purpose: str
    description: str
    framework_refs: Tuple[str, ...] = ()


# ════════════════════════════════════════════════════════════════════════
# Engine
# ════════════════════════════════════════════════════════════════════════

class MultiEntityCurrencyEngine:
    """Diagnostic ME&MC engine."""

    DEFAULT_FUNCTIONAL_CURRENCY: str = "KES"
    SAME_CURRENCY_RATE: Decimal = Decimal("1")

    # Account-code prefix mapping for inter-entity transfers
    INTER_ENTITY_RECEIVABLE_ACCT: str = "IC-RCV"
    INTER_ENTITY_PAYABLE_ACCT: str = "IC-PAY"

    @staticmethod
    def _resolve_rate(
        txn_currency: str, functional_currency: str,
        rates: Sequence[FxSpotRate], rate_date: str,
    ) -> Optional[Decimal]:
        if txn_currency == functional_currency:
            return Decimal("1")
        for r in rates:
            if (r.transaction_currency == txn_currency
                    and r.functional_currency == functional_currency
                    and r.rate_date == rate_date):
                return r.rate
        return None

    def validate_multi_currency_journal(
        self, journal_id: str,
        lines: Sequence[JournalLine],
        rate_date: str,
        rates: Sequence[FxSpotRate] = (),
        functional_currency: Optional[str] = None,
    ) -> JournalValidation:
        fc = (
            functional_currency
            or self.DEFAULT_FUNCTIONAL_CURRENCY)
        issues: List[Tuple[JournalIssue, str]] = []
        if not lines:
            issues.append(
                (JournalIssue.EMPTY_JOURNAL,
                 "journal has no lines"))
            return JournalValidation(
                journal_id=journal_id, is_valid=False,
                issues=tuple(issues),
                total_dr_txn=Decimal("0"),
                total_cr_txn=Decimal("0"),
                transaction_currency="",
                functional_dr=Decimal("0"),
                functional_cr=Decimal("0"),
                fx_rate_used=Decimal("0"),
                framework_refs=(
                    "ENH-257 §validate_journal",))
        currencies = {l.transaction_currency for l in lines}
        if len(currencies) > 1:
            issues.append(
                (JournalIssue.MIXED_CURRENCY_LINES,
                 f"journal mixes currencies: "
                 f"{sorted(currencies)} — split into "
                 f"per-currency journals"))
            txn_currency = sorted(currencies)[0]
        else:
            txn_currency = next(iter(currencies))
        total_dr_txn = sum(
            (l.debit_txn_currency for l in lines),
            Decimal("0"))
        total_cr_txn = sum(
            (l.credit_txn_currency for l in lines),
            Decimal("0"))
        if total_dr_txn != total_cr_txn:
            issues.append(
                (JournalIssue.UNBALANCED,
                 f"D {total_dr_txn} ≠ C {total_cr_txn} in "
                 f"{txn_currency}; variance "
                 f"{total_dr_txn - total_cr_txn}"))
        rate = self._resolve_rate(
            txn_currency, fc, rates, rate_date)
        if rate is None:
            issues.append(
                (JournalIssue.MISSING_FX_RATE,
                 f"no spot rate {txn_currency}→{fc} for "
                 f"{rate_date}"))
            rate = Decimal("0")
            functional_dr = Decimal("0")
            functional_cr = Decimal("0")
        else:
            functional_dr = (total_dr_txn * rate).quantize(
                Decimal("0.01"))
            functional_cr = (total_cr_txn * rate).quantize(
                Decimal("0.01"))
        return JournalValidation(
            journal_id=journal_id,
            is_valid=len(issues) == 0,
            issues=tuple(issues),
            total_dr_txn=total_dr_txn,
            total_cr_txn=total_cr_txn,
            transaction_currency=txn_currency,
            functional_dr=functional_dr,
            functional_cr=functional_cr,
            fx_rate_used=rate,
            framework_refs=(
                "ENH-257 §validate_journal",
                "IAS 21 — transaction at spot rate; one "
                "journal one currency",
                "Per Rule 7 — flags issues; never auto-corrects"))

    def revalue_monetary_balances(
        self, period_end: str,
        balances: Sequence[MonetaryBalance],
        closing_rates: Sequence[FxSpotRate],
        functional_currency: Optional[str] = None,
    ) -> Tuple[RevaluationFinding, ...]:
        fc = (
            functional_currency
            or self.DEFAULT_FUNCTIONAL_CURRENCY)
        findings: List[RevaluationFinding] = []
        for b in balances:
            rate = self._resolve_rate(
                b.currency, fc, closing_rates, period_end)
            if rate is None:
                findings.append(RevaluationFinding(
                    finding_id=(
                        f"REV-MISSING-RATE-{b.balance_id}"),
                    balance_id=b.balance_id,
                    entity_id=b.entity_id,
                    currency=b.currency,
                    txn_balance=b.txn_currency_balance,
                    historical_functional=(
                        b.historical_functional_balance),
                    closing_rate=Decimal("0"),
                    revalued_functional=Decimal("0"),
                    fx_gain_loss_kes=Decimal("0"),
                    severity=RevalSeverity.HIGH,
                    description=(
                        f"no closing rate {b.currency}→{fc} for "
                        f"{period_end} — cannot revalue "
                        f"{b.balance_id}"),
                    framework_refs=(
                        "ENH-257 §revalue_monetary_balances",
                        "IAS 21 §23 — closing rate required for "
                        "monetary item remeasurement")))
                continue
            revalued = (
                b.txn_currency_balance * rate).quantize(
                Decimal("0.01"))
            gain_loss = (
                revalued - b.historical_functional_balance)
            base = abs(b.historical_functional_balance)
            if base == 0:
                rel = Decimal("0")
            else:
                rel = abs(gain_loss) / base
            if gain_loss == 0:
                severity = RevalSeverity.NONE
            elif rel < Decimal("0.01"):
                severity = RevalSeverity.LOW
            elif rel < Decimal("0.05"):
                severity = RevalSeverity.MEDIUM
            else:
                severity = RevalSeverity.HIGH
            description = (
                f"{b.balance_id} ({b.currency} "
                f"{b.txn_currency_balance}): historical "
                f"{b.historical_functional_balance} → revalued "
                f"{revalued} at closing rate {rate} → FX "
                f"{'gain' if gain_loss > 0 else 'loss'} "
                f"{gain_loss} ({rel} relative)")
            findings.append(RevaluationFinding(
                finding_id=f"REV-{b.balance_id}-{period_end}",
                balance_id=b.balance_id,
                entity_id=b.entity_id,
                currency=b.currency,
                txn_balance=b.txn_currency_balance,
                historical_functional=(
                    b.historical_functional_balance),
                closing_rate=rate,
                revalued_functional=revalued,
                fx_gain_loss_kes=gain_loss,
                severity=severity,
                description=description,
                framework_refs=(
                    "ENH-257 §revalue_monetary_balances",
                    "IAS 21 §23 — period-end remeasurement at "
                    "closing rate",
                    "Per Rule 7 — surfaces gain/loss; caller "
                    "posts the revaluation journal")))
        return tuple(findings)

    def recommend_inter_entity_transfer(
        self, req: InterEntityTransferRequest,
    ) -> InterEntityTransferRecommendation:
        return InterEntityTransferRecommendation(
            request_id=req.request_id,
            debit_leg_entity=req.from_entity,
            debit_leg_account=self.INTER_ENTITY_RECEIVABLE_ACCT,
            credit_leg_entity=req.to_entity,
            credit_leg_account=self.INTER_ENTITY_PAYABLE_ACCT,
            amount_kes=req.amount_kes,
            purpose=req.purpose,
            description=(
                f"Inter-entity transfer {req.from_entity} → "
                f"{req.to_entity} for {req.purpose}: "
                f"{req.from_entity} books Dr "
                f"{self.INTER_ENTITY_RECEIVABLE_ACCT} "
                f"{req.amount_kes}; {req.to_entity} books Cr "
                f"{self.INTER_ENTITY_PAYABLE_ACCT} "
                f"{req.amount_kes}. Operator approval required "
                f"before posting."),
            framework_refs=(
                "ENH-257 §inter_entity_transfer",
                "IFRS 10 — intra-group balances eliminate at "
                "consolidation",
                "Per Rule 7 — recommends mirror pair; never "
                "posts; operator approves first"))


# ════════════════════════════════════════════════════════════════════════
# Self-tests
# ════════════════════════════════════════════════════════════════════════

def _line(lid="l1", ent="P", code="1000",
          dr=Decimal("0"), cr=Decimal("0"), curr="KES"):
    return JournalLine(
        line_id=lid, entity_id=ent, account_code=code,
        debit_txn_currency=dr, credit_txn_currency=cr,
        transaction_currency=curr)


def _test_line_validates_id():
    try:
        _line(lid="")
        assert False
    except ValueError:
        pass


def _test_line_validates_negative_amount():
    try:
        _line(dr=Decimal("-1"))
        assert False
    except ValueError:
        pass


def _test_rate_validates_positive():
    try:
        FxSpotRate(
            transaction_currency="USD",
            functional_currency="KES",
            rate=Decimal("0"), rate_date="2026-04-30")
        assert False
    except ValueError:
        pass


def _test_balanced_kes_journal_passes():
    eng = MultiEntityCurrencyEngine()
    lines = (
        _line(lid="l1", dr=Decimal("1000"), curr="KES"),
        _line(lid="l2", code="2000",
              cr=Decimal("1000"), curr="KES"),
    )
    v = eng.validate_multi_currency_journal(
        "J1", lines, "2026-04-15")
    assert v.is_valid is True
    assert len(v.issues) == 0
    assert v.fx_rate_used == Decimal("1")


def _test_unbalanced_journal_fails():
    eng = MultiEntityCurrencyEngine()
    lines = (
        _line(lid="l1", dr=Decimal("1000"), curr="KES"),
        _line(lid="l2", code="2000",
              cr=Decimal("900"), curr="KES"),
    )
    v = eng.validate_multi_currency_journal(
        "J1", lines, "2026-04-15")
    assert v.is_valid is False
    assert any(
        i[0] == JournalIssue.UNBALANCED for i in v.issues)


def _test_mixed_currency_journal_fails():
    eng = MultiEntityCurrencyEngine()
    lines = (
        _line(lid="l1", dr=Decimal("100"), curr="USD"),
        _line(lid="l2", code="2000",
              cr=Decimal("100"), curr="EUR"),
    )
    rates = (
        FxSpotRate(
            transaction_currency="USD",
            functional_currency="KES",
            rate=Decimal("130"), rate_date="2026-04-15"),
    )
    v = eng.validate_multi_currency_journal(
        "J1", lines, "2026-04-15", rates=rates)
    assert any(
        i[0] == JournalIssue.MIXED_CURRENCY_LINES
        for i in v.issues)


def _test_missing_fx_rate_fails():
    eng = MultiEntityCurrencyEngine()
    lines = (
        _line(lid="l1", dr=Decimal("100"), curr="USD"),
        _line(lid="l2", code="2000",
              cr=Decimal("100"), curr="USD"),
    )
    v = eng.validate_multi_currency_journal(
        "J1", lines, "2026-04-15", rates=())
    assert any(
        i[0] == JournalIssue.MISSING_FX_RATE
        for i in v.issues)


def _test_empty_journal_fails():
    eng = MultiEntityCurrencyEngine()
    v = eng.validate_multi_currency_journal(
        "J1", (), "2026-04-15")
    assert v.is_valid is False
    assert any(
        i[0] == JournalIssue.EMPTY_JOURNAL for i in v.issues)


def _test_usd_journal_translates_to_kes():
    eng = MultiEntityCurrencyEngine()
    lines = (
        _line(lid="l1", dr=Decimal("100"), curr="USD"),
        _line(lid="l2", code="2000",
              cr=Decimal("100"), curr="USD"),
    )
    rates = (
        FxSpotRate(
            transaction_currency="USD",
            functional_currency="KES",
            rate=Decimal("130"), rate_date="2026-04-15"),
    )
    v = eng.validate_multi_currency_journal(
        "J1", lines, "2026-04-15", rates=rates)
    assert v.is_valid is True
    assert v.functional_dr == Decimal("13000.00")
    assert v.functional_cr == Decimal("13000.00")
    assert v.fx_rate_used == Decimal("130")


def _test_revalue_no_change():
    eng = MultiEntityCurrencyEngine()
    bal = MonetaryBalance(
        balance_id="b1", entity_id="P",
        account_code="1500",
        currency="USD",
        txn_currency_balance=Decimal("1000"),
        historical_functional_balance=Decimal("130000"))
    rates = (
        FxSpotRate(
            transaction_currency="USD",
            functional_currency="KES",
            rate=Decimal("130"),
            rate_date="2026-04-30"),
    )
    findings = eng.revalue_monetary_balances(
        "2026-04-30", (bal,), rates)
    assert len(findings) == 1
    assert findings[0].fx_gain_loss_kes == Decimal("0.00")
    assert findings[0].severity == RevalSeverity.NONE


def _test_revalue_high_gain():
    eng = MultiEntityCurrencyEngine()
    # USD asset booked at historical 100; revalued at 130
    bal = MonetaryBalance(
        balance_id="b1", entity_id="P",
        account_code="1500",
        currency="USD",
        txn_currency_balance=Decimal("1000"),
        historical_functional_balance=Decimal("100000"))
    rates = (
        FxSpotRate(
            transaction_currency="USD",
            functional_currency="KES",
            rate=Decimal("130"),
            rate_date="2026-04-30"),
    )
    findings = eng.revalue_monetary_balances(
        "2026-04-30", (bal,), rates)
    # Revalued = 130k; gain = 30k = 30% of 100k
    assert findings[0].fx_gain_loss_kes == Decimal("30000.00")
    assert findings[0].severity == RevalSeverity.HIGH


def _test_revalue_loss():
    eng = MultiEntityCurrencyEngine()
    bal = MonetaryBalance(
        balance_id="b1", entity_id="P",
        account_code="2500",
        currency="USD",
        txn_currency_balance=Decimal("-1000"),  # liability
        historical_functional_balance=Decimal("-130000"))
    rates = (
        FxSpotRate(
            transaction_currency="USD",
            functional_currency="KES",
            rate=Decimal("135"),
            rate_date="2026-04-30"),
    )
    findings = eng.revalue_monetary_balances(
        "2026-04-30", (bal,), rates)
    # Liability worsens: revalued = -135k; gain/loss = -135k - (-130k) = -5k
    assert findings[0].fx_gain_loss_kes == Decimal("-5000.00")


def _test_revalue_missing_rate_high_severity():
    eng = MultiEntityCurrencyEngine()
    bal = MonetaryBalance(
        balance_id="b1", entity_id="P",
        account_code="1500",
        currency="GBP",
        txn_currency_balance=Decimal("1000"),
        historical_functional_balance=Decimal("160000"))
    findings = eng.revalue_monetary_balances(
        "2026-04-30", (bal,), ())
    assert findings[0].severity == RevalSeverity.HIGH
    assert "no closing rate" in findings[0].description


def _test_inter_entity_request_validates_self():
    try:
        InterEntityTransferRequest(
            request_id="r1", from_entity="P", to_entity="P",
            amount_kes=Decimal("1000"), purpose="loan")
        assert False
    except ValueError:
        pass


def _test_inter_entity_recommendation():
    eng = MultiEntityCurrencyEngine()
    req = InterEntityTransferRequest(
        request_id="REQ-001",
        from_entity="PARENT", to_entity="SUBA",
        amount_kes=Decimal("5000000"),
        purpose="working_capital_loan")
    rec = eng.recommend_inter_entity_transfer(req)
    assert rec.debit_leg_entity == "PARENT"
    assert rec.credit_leg_entity == "SUBA"
    assert rec.amount_kes == Decimal("5000000")
    assert "IC-RCV" in rec.debit_leg_account
    assert "IC-PAY" in rec.credit_leg_account
    assert any("Rule 7" in r for r in rec.framework_refs)


def _test_engine_does_not_mutate_inputs():
    eng = MultiEntityCurrencyEngine()
    lines = (
        _line(lid="l1", dr=Decimal("100"), curr="KES"),
        _line(lid="l2", code="2000",
              cr=Decimal("100"), curr="KES"),
    )
    eng.validate_multi_currency_journal(
        "J1", lines, "2026-04-15")
    assert lines[0].debit_txn_currency == Decimal("100")


def _test_full_provenance_revaluation():
    eng = MultiEntityCurrencyEngine()
    bal = MonetaryBalance(
        balance_id="b1", entity_id="P",
        account_code="1500",
        currency="USD",
        txn_currency_balance=Decimal("1000"),
        historical_functional_balance=Decimal("100000"))
    rates = (
        FxSpotRate(
            transaction_currency="USD",
            functional_currency="KES",
            rate=Decimal("130"),
            rate_date="2026-04-30"),
    )
    findings = eng.revalue_monetary_balances(
        "2026-04-30", (bal,), rates)
    f = findings[0]
    assert any("ENH-257" in r for r in f.framework_refs)
    assert any("IAS 21" in r for r in f.framework_refs)
    assert any("Rule 7" in r for r in f.framework_refs)


def self_test() -> None:
    tests = [
        _test_line_validates_id,
        _test_line_validates_negative_amount,
        _test_rate_validates_positive,
        _test_balanced_kes_journal_passes,
        _test_unbalanced_journal_fails,
        _test_mixed_currency_journal_fails,
        _test_missing_fx_rate_fails,
        _test_empty_journal_fails,
        _test_usd_journal_translates_to_kes,
        _test_revalue_no_change,
        _test_revalue_high_gain,
        _test_revalue_loss,
        _test_revalue_missing_rate_high_severity,
        _test_inter_entity_request_validates_self,
        _test_inter_entity_recommendation,
        _test_engine_does_not_mutate_inputs,
        _test_full_provenance_revaluation,
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
            f"✗ multi_entity_currency self-test: "
            f"{len(failed)} failures",
            file=sys.stderr)
        for name, msg in failed:
            print(f"  - {name}: {msg}", file=sys.stderr)
        raise SystemExit(1)
    print(
        f"✓ multi_entity_currency self-test passed "
        f"({len(tests)} tests)")


if __name__ == "__main__":
    self_test()
