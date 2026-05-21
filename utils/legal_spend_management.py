"""utils/legal_spend_management.py — ENH-225 Legal Spend Management.

Fourth Legal arc engine. Tracks budget allocation per matter, accrual
of approved spend, rate cards by firm × timekeeper role, and variance
from budget.

DESIGN
------
The engine is decoupled from outside_counsel_portal — it accepts spend
records via record_spend() rather than calling that engine directly.
The orchestration layer wires APPROVED billing submissions into spend
records, allowing the engine to be tested independently and to receive
internal_counsel hours from legal_case_management as well.

LIFECYCLE — Budget
    ACTIVE → CLOSED (matter resolved or budget retired)
    Variance state computed dynamically from accrued spend:
        ON_TRACK        — spend ≤ 80% of budget
        WARNING         — 80% < spend ≤ 95%
        AT_LIMIT        — 95% < spend ≤ 100%
        EXCEEDED        — spend > 100%

REGULATORY ALIGNMENT
- Companies Act §145 (Kenya) — director cost-control duty
- CBK Operational Risk Mgmt Guidelines — vendor cost discipline
- Internal procurement controls

HONEST DEFERRALS
- REAL_TIME_AP_RECONCILIATION DEFERRED — engine accumulates approved
  spend; reconciliation against AP/AR books (FLEXCUBE GL) is
  operator-side
- RATE_NEGOTIATION_RECOMMENDATIONS DEFERRED — engine surfaces rate
  observations; recommendation logic for rate negotiation is future
  work
- INTERNAL_COUNSEL_COSTING META_ONLY — engine accepts internal_counsel
  hours but doesn't compute fully-loaded internal cost (HR salary
  load, benefits) — operator-side
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, List, Mapping, Optional, Tuple


class BudgetStatus(str, Enum):
    ACTIVE = "ACTIVE"
    CLOSED = "CLOSED"


class VarianceState(str, Enum):
    ON_TRACK = "ON_TRACK"
    WARNING = "WARNING"
    AT_LIMIT = "AT_LIMIT"
    EXCEEDED = "EXCEEDED"


class SpendOrigin(str, Enum):
    EXTERNAL_BILLING = "EXTERNAL_BILLING"   # from outside_counsel_portal
    INTERNAL_COUNSEL = "INTERNAL_COUNSEL"   # from legal_case_management
    EXPENSE = "EXPENSE"                     # disbursements, court fees
    OTHER = "OTHER"


class TransitionOutcome(str, Enum):
    OK = "OK"
    REJECTED_INVALID_TRANSITION = "REJECTED_INVALID_TRANSITION"
    REJECTED_REASON_REQUIRED = "REJECTED_REASON_REQUIRED"
    REJECTED_NOT_FOUND = "REJECTED_NOT_FOUND"
    REJECTED_CURRENCY_MISMATCH = "REJECTED_CURRENCY_MISMATCH"


@dataclass(frozen=True)
class SpendRecord:
    spend_id: str
    matter_id: str
    origin: SpendOrigin
    amount: Decimal
    currency: str
    description: str
    counterparty: str       # firm name or "INTERNAL"
    recorded_at_utc: str
    source_ref: str = ""    # e.g. submission_id from portal

    def to_dict(self) -> Dict[str, Any]:
        return {"spend_id": self.spend_id,
                "matter_id": self.matter_id,
                "origin": self.origin.value,
                "amount": str(self.amount),
                "currency": self.currency,
                "description": self.description,
                "counterparty": self.counterparty,
                "recorded_at_utc": self.recorded_at_utc,
                "source_ref": self.source_ref}


@dataclass(frozen=True)
class Budget:
    budget_id: str
    matter_id: str
    name: str
    amount: Decimal
    currency: str
    period_start: str       # YYYY-MM-DD
    period_end: str
    owner_role: str
    status: BudgetStatus
    created_at_utc: str
    closed_at_utc: str = ""
    closure_reason: str = ""
    transition_log: Tuple[Mapping[str, Any], ...] = ()

    def to_dict(self) -> Dict[str, Any]:
        return {"budget_id": self.budget_id,
                "matter_id": self.matter_id, "name": self.name,
                "amount": str(self.amount), "currency": self.currency,
                "period_start": self.period_start,
                "period_end": self.period_end,
                "owner_role": self.owner_role,
                "status": self.status.value,
                "created_at_utc": self.created_at_utc,
                "closed_at_utc": self.closed_at_utc,
                "closure_reason": self.closure_reason,
                "transition_log": [dict(t)
                                     for t in self.transition_log]}


@dataclass(frozen=True)
class RateCard:
    rate_card_id: str
    firm_name: str
    timekeeper_role: str    # partner/senior/associate/paralegal
    hourly_rate: Decimal
    currency: str
    effective_from: str     # YYYY-MM-DD
    effective_to: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {"rate_card_id": self.rate_card_id,
                "firm_name": self.firm_name,
                "timekeeper_role": self.timekeeper_role,
                "hourly_rate": str(self.hourly_rate),
                "currency": self.currency,
                "effective_from": self.effective_from,
                "effective_to": self.effective_to}


class LegalSpendManagementEngine:
    """ENH-225 Legal Spend Management Engine."""

    REAL_TIME_AP_RECONCILIATION_STATUS = (
        "DEFERRED — engine accumulates approved spend records; "
        "reconciliation against AP/AR books (FLEXCUBE GL) is "
        "operator-side. v10.173 ships accrual ledger; FLEXCUBE "
        "wiring future increment.")

    RATE_NEGOTIATION_RECOMMENDATIONS_STATUS = (
        "DEFERRED — engine stores rate cards and surfaces firm-by-"
        "firm spend observations; ML-driven recommendations for rate "
        "renegotiation (peer-firm benchmarking, market rate "
        "comparison) are future work.")

    INTERNAL_COUNSEL_COSTING_STATUS = (
        "META_ONLY — engine accepts internal_counsel hours but does "
        "not compute fully-loaded internal cost (HR salary load, "
        "benefits, overhead). For internal hours, the spend amount "
        "is what the operator passes in — typically a notional rate "
        "or zero. True internal costing is operator-side.")

    # Variance thresholds (% of budget)
    THRESHOLD_WARNING = Decimal("0.80")
    THRESHOLD_AT_LIMIT = Decimal("0.95")
    THRESHOLD_EXCEEDED = Decimal("1.00")

    def __init__(self) -> None:
        self._budgets: Dict[str, Budget] = {}
        self._spend_records: Dict[str, SpendRecord] = {}
        self._rate_cards: Dict[str, RateCard] = {}
        self._next_budget = 1
        self._next_spend = 1
        self._next_rate_card = 1

    # ------------------------------------------------------------------
    # Budgets
    # ------------------------------------------------------------------

    def create_budget(
        self, matter_id: str, name: str, amount: Decimal,
        currency: str, period_start: str, period_end: str,
        owner_role: str,
    ) -> Budget:
        if amount <= Decimal("0"):
            raise ValueError("budget amount must be positive")
        if not matter_id.strip():
            raise ValueError("matter_id required")
        if not owner_role.strip():
            raise ValueError(
                "owner_role required — every budget needs a named "
                "accountable owner")
        # Validate dates
        for d in (period_start, period_end):
            try:
                datetime.strptime(d, "%Y-%m-%d")
            except ValueError:
                raise ValueError(
                    f"date must be YYYY-MM-DD: got {d!r}")

        bid = f"BGT-{self._next_budget:06d}"
        self._next_budget += 1
        now_utc = datetime.now(timezone.utc).isoformat()
        budget = Budget(
            budget_id=bid, matter_id=matter_id.strip(),
            name=name.strip(), amount=amount,
            currency=currency.strip(),
            period_start=period_start, period_end=period_end,
            owner_role=owner_role.strip(),
            status=BudgetStatus.ACTIVE,
            created_at_utc=now_utc,
            transition_log=(
                {"to_status": "ACTIVE", "at_utc": now_utc,
                 "user": "system",
                 "reason": "budget created"},))
        self._budgets[bid] = budget
        return budget

    def close_budget(
        self, budget_id: str, user: str, reason: str,
    ) -> Tuple[TransitionOutcome, Optional[Budget]]:
        if budget_id not in self._budgets:
            return (TransitionOutcome.REJECTED_NOT_FOUND, None)
        if not reason.strip():
            return (TransitionOutcome.REJECTED_REASON_REQUIRED,
                    self._budgets[budget_id])
        current = self._budgets[budget_id]
        if current.status == BudgetStatus.CLOSED:
            return (TransitionOutcome.REJECTED_INVALID_TRANSITION,
                    current)
        now_utc = datetime.now(timezone.utc).isoformat()
        kwargs = {f: getattr(current, f) for f in
                    current.__dataclass_fields__}
        kwargs["status"] = BudgetStatus.CLOSED
        kwargs["closed_at_utc"] = now_utc
        kwargs["closure_reason"] = reason.strip()
        kwargs["transition_log"] = (
            current.transition_log +
            ({"to_status": "CLOSED", "at_utc": now_utc,
              "user": user, "reason": reason},))
        updated = Budget(**kwargs)
        self._budgets[budget_id] = updated
        return (TransitionOutcome.OK, updated)

    # ------------------------------------------------------------------
    # Spend records
    # ------------------------------------------------------------------

    def record_spend(
        self, matter_id: str, origin: SpendOrigin,
        amount: Decimal, currency: str,
        description: str, counterparty: str,
        source_ref: str = "",
    ) -> Tuple[TransitionOutcome, Optional[SpendRecord]]:
        if amount <= Decimal("0"):
            raise ValueError("spend amount must be positive")
        # If a budget exists for this matter, currency must match
        budgets = [b for b in self._budgets.values()
                    if b.matter_id == matter_id and
                       b.status == BudgetStatus.ACTIVE]
        for b in budgets:
            if b.currency != currency:
                return (TransitionOutcome.REJECTED_CURRENCY_MISMATCH,
                        None)
        sid = f"SPN-{self._next_spend:06d}"
        self._next_spend += 1
        now_utc = datetime.now(timezone.utc).isoformat()
        record = SpendRecord(
            spend_id=sid, matter_id=matter_id.strip(),
            origin=origin, amount=amount,
            currency=currency.strip(),
            description=description.strip(),
            counterparty=counterparty.strip(),
            recorded_at_utc=now_utc,
            source_ref=source_ref.strip())
        self._spend_records[sid] = record
        return (TransitionOutcome.OK, record)

    # ------------------------------------------------------------------
    # Rate cards
    # ------------------------------------------------------------------

    def add_rate_card(
        self, firm_name: str, timekeeper_role: str,
        hourly_rate: Decimal, currency: str, effective_from: str,
    ) -> RateCard:
        if hourly_rate <= Decimal("0"):
            raise ValueError("hourly_rate must be positive")
        rid = f"RTC-{self._next_rate_card:06d}"
        self._next_rate_card += 1
        card = RateCard(
            rate_card_id=rid, firm_name=firm_name.strip(),
            timekeeper_role=timekeeper_role.strip(),
            hourly_rate=hourly_rate, currency=currency.strip(),
            effective_from=effective_from)
        self._rate_cards[rid] = card
        return card

    # ------------------------------------------------------------------
    # Variance computation
    # ------------------------------------------------------------------

    def accrued_spend_for_matter(
            self, matter_id: str,
            currency: Optional[str] = None) -> Decimal:
        records = [r for r in self._spend_records.values()
                    if r.matter_id == matter_id]
        if currency:
            records = [r for r in records if r.currency == currency]
        return sum((r.amount for r in records), Decimal("0"))

    def variance_for_budget(
            self, budget_id: str) -> Dict[str, Any]:
        if budget_id not in self._budgets:
            raise KeyError(f"not found: {budget_id}")
        budget = self._budgets[budget_id]
        spend = self.accrued_spend_for_matter(
            budget.matter_id, currency=budget.currency)
        ratio = (spend / budget.amount
                  if budget.amount > 0 else Decimal("0"))
        if ratio > self.THRESHOLD_EXCEEDED:
            state = VarianceState.EXCEEDED
        elif ratio > self.THRESHOLD_AT_LIMIT:
            state = VarianceState.AT_LIMIT
        elif ratio > self.THRESHOLD_WARNING:
            state = VarianceState.WARNING
        else:
            state = VarianceState.ON_TRACK
        return {"budget_id": budget_id,
                "matter_id": budget.matter_id,
                "budget_amount": str(budget.amount),
                "accrued_spend": str(spend),
                "currency": budget.currency,
                "remaining": str(budget.amount - spend),
                "ratio": str(ratio.quantize(Decimal("0.0001"))),
                "state": state.value,
                "status": budget.status.value}

    def matters_at_or_over_limit(self) -> Tuple[Dict[str, Any], ...]:
        out = []
        for bid, b in self._budgets.items():
            if b.status != BudgetStatus.ACTIVE:
                continue
            v = self.variance_for_budget(bid)
            if v["state"] in (VarianceState.AT_LIMIT.value,
                                VarianceState.EXCEEDED.value):
                out.append(v)
        return tuple(out)

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def budget_by_id(self, budget_id: str) -> Budget:
        if budget_id not in self._budgets:
            raise KeyError(f"not found: {budget_id}")
        return self._budgets[budget_id]

    def budgets_for_matter(self, matter_id: str) -> Tuple[Budget, ...]:
        return tuple(b for b in self._budgets.values()
                       if b.matter_id == matter_id)

    def spend_for_matter(
            self, matter_id: str) -> Tuple[SpendRecord, ...]:
        return tuple(r for r in self._spend_records.values()
                       if r.matter_id == matter_id)

    def rate_cards_for_firm(
            self, firm_name: str) -> Tuple[RateCard, ...]:
        return tuple(c for c in self._rate_cards.values()
                       if c.firm_name == firm_name)

    def spend_by_firm(self) -> Dict[str, Dict[str, str]]:
        """Spend grouped by firm × currency."""
        out: Dict[str, Dict[str, Decimal]] = {}
        for r in self._spend_records.values():
            firm = r.counterparty
            if firm not in out:
                out[firm] = {}
            out[firm][r.currency] = (
                out[firm].get(r.currency, Decimal("0")) + r.amount)
        return {firm: {ccy: str(amt) for ccy, amt in v.items()}
                for firm, v in out.items()}

    def board_summary(self) -> Dict[str, Any]:
        n_budgets = len(self._budgets)
        n_active = sum(1 for b in self._budgets.values()
                        if b.status == BudgetStatus.ACTIVE)
        n_breached = len(self.matters_at_or_over_limit())
        # Aggregate budget + spend by currency
        budget_by_ccy: Dict[str, Decimal] = {}
        spend_by_ccy: Dict[str, Decimal] = {}
        for b in self._budgets.values():
            if b.status != BudgetStatus.ACTIVE:
                continue
            budget_by_ccy[b.currency] = (
                budget_by_ccy.get(b.currency, Decimal("0"))
                + b.amount)
        for r in self._spend_records.values():
            spend_by_ccy[r.currency] = (
                spend_by_ccy.get(r.currency, Decimal("0"))
                + r.amount)
        return {
            "entity": "Ecobank Kenya",
            "engine": "ENH-225 LegalSpendManagementEngine",
            "n_budgets_total": n_budgets,
            "n_budgets_active": n_active,
            "n_budgets_at_or_over_limit": n_breached,
            "n_spend_records": len(self._spend_records),
            "n_rate_cards": len(self._rate_cards),
            "active_budgets_by_currency": {
                k: str(v) for k, v in budget_by_ccy.items()},
            "total_spend_by_currency": {
                k: str(v) for k, v in spend_by_ccy.items()},
            "real_time_ap_reconciliation_status": (
                self.REAL_TIME_AP_RECONCILIATION_STATUS),
            "rate_negotiation_recommendations_status": (
                self.RATE_NEGOTIATION_RECOMMENDATIONS_STATUS),
            "internal_counsel_costing_status": (
                self.INTERNAL_COUNSEL_COSTING_STATUS),
            "regulatory_basis": (
                "Companies Act §145 (Kenya) director cost-control "
                "duty, CBK Operational Risk Management Guidelines "
                "vendor cost discipline, internal procurement "
                "controls"),
        }
