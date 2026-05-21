"""utils/consolidated_tb_engine.py — v10.61: TB consolidation.

╔════════════════════════════════════════════════════════════════════════╗
║  ENH-251 — Group Consolidation Engine (operational TB layer)            ║
║  Cat B — finance arc 3/10                                               ║
╠════════════════════════════════════════════════════════════════════════╣
║  Operational TB consolidation per IFRS 10 + IAS 21. Note: Standard      ║
║  #100 (utils/group_consolidation.py) is the policy-side engine          ║
║  (method selection by ownership %, classification, NCI calculation     ║
║  rules); ENH-251 is the operational-side engine (taking individual      ║
║  entity trial balances, applying ENH-250 eliminations, FX-translating,  ║
║  producing consolidated TB ready for ENH-255 statement generator).      ║
║                                                                          ║
║  Four-step pipeline:                                                    ║
║                                                                          ║
║    1. AGGREGATION   — line-by-line sum of TB amounts across entities   ║
║                       (after FX translation to presentation currency)   ║
║                                                                          ║
║    2. ELIMINATIONS  — applies operator-approved eliminations from       ║
║                       ENH-250 IcMatchReport.                            ║
║                                                                          ║
║    3. NCI ALLOCATION — for each non-100%-owned subsidiary, allocates    ║
║                        post-elimination contribution between parent     ║
║                        share and non-controlling interest               ║
║                                                                          ║
║    4. FX TRANSLATION — IAS 21: closing rate for B/S items, average      ║
║                        rate for P&L items. Translation differential     ║
║                        accumulates as cumulative_translation_adj for    ║
║                        OCI booking by ENH-255                           ║
║                                                                          ║
║  Per Rule 7, engine DIAGNOSTIC ONLY:                                   ║
║    - never posts consolidation journals to source entity GLs           ║
║    - never goes to FX market (caller supplies rates)                    ║
║    - never auto-selects eliminations (caller passes approved subset)   ║
║                                                                          ║
║  Per Rule 1, every ConsolidatedLine surfaces account_code + per-entity ║
║  contributions + pre/post elimination + NCI share + parent share +      ║
║  FX rate used + framework refs.                                         ║
║                                                                          ║
║  Pure stdlib (Decimal + frozen dataclasses + enums).                    ║
║                                                                          ║
║  Composes with:                                                          ║
║    - finance_close_orchestrator (ENH-249) — uses AccountType            ║
║    - intercompany_matching (ENH-250) — consumes                         ║
║      EliminationRecommendation list                                     ║
║    - financial_statement_generator (ENH-255, to-be-built)              ║
║    - group_consolidation (Standard #100) — that engine determines      ║
║      method/NCI policy; this engine applies the operational mechanics   ║
╚════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Dict, List, Optional, Sequence, Tuple

from utils.finance_close_orchestrator import AccountType
from utils.intercompany_matching import EliminationRecommendation

SPEC_DEVIATION_NOTE = (
    "ConsolidatedTrialBalanceEngine implements ENH-251 per "
    "IFRS 10 + IAS 21. Operational TB consolidation — distinct "
    "from Standard #100 (policy-side method selection in "
    "utils/group_consolidation.py). Pure stdlib (Decimal + "
    "dataclasses). Per Rule 1, every ConsolidatedLine surfaces "
    "full per-entity contributions + eliminations applied + "
    "NCI share + parent share + FX rate used + framework refs. "
    "Per Rule 7, engine DIAGNOSTIC ONLY — produces consolidated "
    "TB but never posts to source entity GLs, never forces FX "
    "rates (caller supplies per IAS 21 closing/average "
    "discipline), never auto-selects eliminations (caller "
    "passes operator-approved subset)."
)


# ════════════════════════════════════════════════════════════════════════
# Enums
# ════════════════════════════════════════════════════════════════════════

class FxRateType(Enum):
    """IAS 21 — different rate per account type."""
    CLOSING = "CLOSING"        # B/S items
    AVERAGE = "AVERAGE"        # P&L items
    HISTORICAL = "HISTORICAL"  # equity (not used by default)


class ConsolidationSeverity(Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


# ════════════════════════════════════════════════════════════════════════
# Input dataclasses
# ════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class EntityProfile:
    entity_id: str
    entity_name: str
    parent_ownership_pct: Decimal
    functional_currency: str
    is_parent: bool = False

    def __post_init__(self) -> None:
        if not self.entity_id:
            raise ValueError("entity_id must be non-empty")
        if not (Decimal("0") <= self.parent_ownership_pct
                <= Decimal("1")):
            raise ValueError(
                "parent_ownership_pct must be in [0, 1]")
        if self.is_parent and (
                self.parent_ownership_pct != Decimal("1")):
            raise ValueError(
                "parent must have ownership_pct = 1")


@dataclass(frozen=True)
class TrialBalanceLine:
    entity_id: str
    account_code: str
    account_type: AccountType
    debit_kes: Decimal
    credit_kes: Decimal
    period: str

    def __post_init__(self) -> None:
        if self.debit_kes < 0 or self.credit_kes < 0:
            raise ValueError("D/C amounts must be ≥ 0")


@dataclass(frozen=True)
class FxRate:
    currency: str
    rate_type: FxRateType
    rate_to_kes: Decimal
    period: str

    def __post_init__(self) -> None:
        if self.rate_to_kes <= 0:
            raise ValueError("rate_to_kes must be > 0")


# ════════════════════════════════════════════════════════════════════════
# Output dataclasses
# ════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class EntityContribution:
    entity_id: str
    debit_kes_functional: Decimal
    credit_kes_functional: Decimal
    fx_rate_used: Decimal
    debit_kes_presentation: Decimal
    credit_kes_presentation: Decimal
    fx_rate_type: FxRateType


@dataclass(frozen=True)
class ConsolidatedLine:
    account_code: str
    account_type: AccountType
    entity_contributions: Tuple[EntityContribution, ...]
    pre_elimination_dr: Decimal
    pre_elimination_cr: Decimal
    eliminations_applied_dr: Decimal
    eliminations_applied_cr: Decimal
    post_elimination_dr: Decimal
    post_elimination_cr: Decimal
    nci_share_dr: Decimal
    nci_share_cr: Decimal
    parent_share_dr: Decimal
    parent_share_cr: Decimal
    framework_refs: Tuple[str, ...] = ()


@dataclass(frozen=True)
class ConsolidationFinding:
    finding_id: str
    severity: ConsolidationSeverity
    description: str
    affected_entities: Tuple[str, ...]
    framework_refs: Tuple[str, ...] = ()


@dataclass(frozen=True)
class ConsolidatedTrialBalance:
    period: str
    presentation_currency: str
    lines: Tuple[ConsolidatedLine, ...]
    findings: Tuple[ConsolidationFinding, ...]
    entities_consolidated: int
    eliminations_applied_count: int
    total_dr: Decimal
    total_cr: Decimal
    cumulative_translation_adjustment_kes: Decimal
    framework_refs: Tuple[str, ...]


# ════════════════════════════════════════════════════════════════════════
# Engine
# ════════════════════════════════════════════════════════════════════════

class ConsolidatedTrialBalanceEngine:
    """Operational TB consolidation per IFRS 10 + IAS 21."""

    DEFAULT_PRESENTATION_CURRENCY: str = "KES"

    @staticmethod
    def _rate_type_for_account(at: AccountType) -> FxRateType:
        if at in (AccountType.REVENUE, AccountType.EXPENSE):
            return FxRateType.AVERAGE
        return FxRateType.CLOSING

    @staticmethod
    def _resolve_fx_rate(
        entity_currency: str,
        rate_type: FxRateType,
        period: str,
        fx_rates: Sequence[FxRate],
        presentation_currency: str,
    ) -> Decimal:
        if entity_currency == presentation_currency:
            return Decimal("1")
        for r in fx_rates:
            if (r.currency == entity_currency
                    and r.rate_type == rate_type
                    and r.period == period):
                return r.rate_to_kes
        raise ValueError(
            f"no FX rate found for {entity_currency} "
            f"({rate_type.value}) in period {period}")

    def consolidate(
        self,
        period: str,
        entities: Sequence[EntityProfile],
        tb_lines: Sequence[TrialBalanceLine],
        fx_rates: Sequence[FxRate] = (),
        eliminations: Sequence[
            EliminationRecommendation] = (),
        presentation_currency: str = (
            DEFAULT_PRESENTATION_CURRENCY),
    ) -> ConsolidatedTrialBalance:
        findings: List[ConsolidationFinding] = []
        entity_index: Dict[str, EntityProfile] = {
            e.entity_id: e for e in entities}

        missing_profiles = {
            tl.entity_id for tl in tb_lines
        } - set(entity_index)
        if missing_profiles:
            findings.append(ConsolidationFinding(
                finding_id="CON-MISSING-PROFILE",
                severity=ConsolidationSeverity.CRITICAL,
                description=(
                    f"trial balance lines reference entities "
                    f"with no EntityProfile: "
                    f"{sorted(missing_profiles)}"),
                affected_entities=tuple(sorted(missing_profiles)),
                framework_refs=(
                    "ENH-251 §validation",
                    "IFRS 10 — every consolidated entity needs "
                    "ownership profile")))

        in_period = tuple(
            tl for tl in tb_lines if tl.period == period)

        by_account: Dict[
            str,
            List[
                Tuple[str, AccountType, Decimal, Decimal]]] = {}
        for tl in in_period:
            by_account.setdefault(tl.account_code, []).append((
                tl.entity_id, tl.account_type,
                tl.debit_kes, tl.credit_kes))

        elim_by_dr: Dict[str, Decimal] = {}
        elim_by_cr: Dict[str, Decimal] = {}
        for el in eliminations:
            elim_by_dr[el.debit_account] = (
                elim_by_dr.get(el.debit_account, Decimal("0"))
                + el.amount_kes)
            elim_by_cr[el.credit_account] = (
                elim_by_cr.get(el.credit_account, Decimal("0"))
                + el.amount_kes)

        consolidated_lines: List[ConsolidatedLine] = []
        cumulative_translation_adj = Decimal("0")

        for account_code, ent_lines in by_account.items():
            account_type = ent_lines[0][1]
            rate_type = self._rate_type_for_account(account_type)

            contributions: List[EntityContribution] = []
            pre_dr = Decimal("0")
            pre_cr = Decimal("0")
            for (entity_id, _, dr_func, cr_func) in ent_lines:
                profile = entity_index.get(entity_id)
                if profile is None:
                    continue
                try:
                    rate = self._resolve_fx_rate(
                        profile.functional_currency,
                        rate_type, period, fx_rates,
                        presentation_currency)
                except ValueError as exc:
                    findings.append(ConsolidationFinding(
                        finding_id=(
                            f"CON-FX-{entity_id}-"
                            f"{account_code}"),
                        severity=ConsolidationSeverity.HIGH,
                        description=str(exc),
                        affected_entities=(entity_id,),
                        framework_refs=(
                            "ENH-251 §fx_translation",
                            "IAS 21 — closing/average rates "
                            "required for translation")))
                    rate = Decimal("1")    # fallback
                dr_pres = (dr_func * rate).quantize(
                    Decimal("0.01"))
                cr_pres = (cr_func * rate).quantize(
                    Decimal("0.01"))
                contributions.append(EntityContribution(
                    entity_id=entity_id,
                    debit_kes_functional=dr_func,
                    credit_kes_functional=cr_func,
                    fx_rate_used=rate,
                    debit_kes_presentation=dr_pres,
                    credit_kes_presentation=cr_pres,
                    fx_rate_type=rate_type))
                pre_dr += dr_pres
                pre_cr += cr_pres
                if rate != Decimal("1"):
                    diff = (
                        (dr_pres - cr_pres)
                        - (dr_func - cr_func))
                    cumulative_translation_adj += diff

            elim_dr = elim_by_dr.get(account_code, Decimal("0"))
            elim_cr = elim_by_cr.get(account_code, Decimal("0"))
            post_dr = pre_dr - elim_dr
            post_cr = pre_cr - elim_cr

            nci_share_dr = Decimal("0")
            nci_share_cr = Decimal("0")
            for (entity_id, _, _, _) in ent_lines:
                profile = entity_index.get(entity_id)
                if profile is None:
                    continue
                if profile.is_parent:
                    continue
                nci_pct = (
                    Decimal("1") - profile.parent_ownership_pct)
                if nci_pct <= 0:
                    continue
                contrib = next(
                    (c for c in contributions
                     if c.entity_id == entity_id), None)
                if contrib is None:
                    continue
                nci_share_dr += (
                    contrib.debit_kes_presentation
                    * nci_pct).quantize(Decimal("0.01"))
                nci_share_cr += (
                    contrib.credit_kes_presentation
                    * nci_pct).quantize(Decimal("0.01"))

            parent_share_dr = post_dr - nci_share_dr
            parent_share_cr = post_cr - nci_share_cr

            consolidated_lines.append(ConsolidatedLine(
                account_code=account_code,
                account_type=account_type,
                entity_contributions=tuple(contributions),
                pre_elimination_dr=pre_dr,
                pre_elimination_cr=pre_cr,
                eliminations_applied_dr=elim_dr,
                eliminations_applied_cr=elim_cr,
                post_elimination_dr=post_dr,
                post_elimination_cr=post_cr,
                nci_share_dr=nci_share_dr,
                nci_share_cr=nci_share_cr,
                parent_share_dr=parent_share_dr,
                parent_share_cr=parent_share_cr,
                framework_refs=(
                    "ENH-251 §aggregate + §eliminate + §nci",)))

        total_dr = sum(
            (l.post_elimination_dr for l in consolidated_lines),
            Decimal("0"))
        total_cr = sum(
            (l.post_elimination_cr for l in consolidated_lines),
            Decimal("0"))

        diff = total_dr - total_cr
        if abs(diff) > Decimal("1"):
            findings.append(ConsolidationFinding(
                finding_id="CON-TB-IMBALANCE",
                severity=(
                    ConsolidationSeverity.HIGH
                    if abs(diff) > Decimal("100")
                    else ConsolidationSeverity.LOW),
                description=(
                    f"consolidated TB Dr {total_dr} ≠ Cr "
                    f"{total_cr} (variance {diff}) — review "
                    f"FX rounding + elimination completeness"),
                affected_entities=tuple(
                    sorted(entity_index.keys())),
                framework_refs=(
                    "ENH-251 §balance_check",
                    "IAS 21 — translation differences flow to "
                    "OCI/cumulative translation reserve")))

        return ConsolidatedTrialBalance(
            period=period,
            presentation_currency=presentation_currency,
            lines=tuple(consolidated_lines),
            findings=tuple(findings),
            entities_consolidated=len(entity_index),
            eliminations_applied_count=len(eliminations),
            total_dr=total_dr,
            total_cr=total_cr,
            cumulative_translation_adjustment_kes=(
                cumulative_translation_adj),
            framework_refs=(
                "ENH-251 §consolidate",
                "IFRS 10 — control-based consolidation",
                "IAS 21 — closing rate B/S, average rate P&L",
                "Per Rule 7 — diagnostic only; never posts to "
                "source entity GLs",
            ))


# ════════════════════════════════════════════════════════════════════════
# Self-tests
# ════════════════════════════════════════════════════════════════════════

def _entity(eid, owner=Decimal("1"), curr="KES",
            is_parent=False):
    return EntityProfile(
        entity_id=eid, entity_name=eid,
        parent_ownership_pct=owner,
        functional_currency=curr, is_parent=is_parent)


def _tb(eid, code, atype, dr=0, cr=0, period="2026-04"):
    return TrialBalanceLine(
        entity_id=eid, account_code=code, account_type=atype,
        debit_kes=Decimal(str(dr)),
        credit_kes=Decimal(str(cr)), period=period)


def _test_entity_validates_ownership():
    try:
        _entity("X", owner=Decimal("1.5"))
        assert False
    except ValueError:
        pass


def _test_parent_must_be_100pct():
    try:
        EntityProfile(
            entity_id="P", entity_name="P",
            parent_ownership_pct=Decimal("0.8"),
            functional_currency="KES", is_parent=True)
        assert False
    except ValueError:
        pass


def _test_tb_validates_negative():
    try:
        _tb("E", "1000", AccountType.ASSET, dr=-100)
        assert False
    except ValueError:
        pass


def _test_simple_aggregation_kes_only():
    eng = ConsolidatedTrialBalanceEngine()
    p = _entity("P", is_parent=True)
    s = _entity("S")
    tb = (
        _tb("P", "1000", AccountType.ASSET, dr=500),
        _tb("S", "1000", AccountType.ASSET, dr=200),
    )
    r = eng.consolidate("2026-04", (p, s), tb)
    assert len(r.lines) == 1
    assert r.lines[0].pre_elimination_dr == Decimal("700")


def _test_aggregation_with_elimination():
    eng = ConsolidatedTrialBalanceEngine()
    p = _entity("P", is_parent=True)
    s = _entity("S")
    tb = (
        _tb("P", "IC-REC", AccountType.ASSET, dr=100000),
        _tb("S", "IC-PAY", AccountType.LIABILITY, cr=100000),
    )
    elim = EliminationRecommendation(
        rec_id="ELIM-1",
        elimination_type=None,
        entity_a="P", entity_b="S",
        reference="R1", period="2026-04",
        debit_account="IC-PAY", credit_account="IC-REC",
        amount_kes=Decimal("100000"),
        description="elim IC AR/AP")
    r = eng.consolidate(
        "2026-04", (p, s), tb, eliminations=(elim,))
    rec = next(l for l in r.lines if l.account_code == "IC-REC")
    pay = next(l for l in r.lines if l.account_code == "IC-PAY")
    assert rec.eliminations_applied_cr == Decimal("100000")
    assert pay.eliminations_applied_dr == Decimal("100000")


def _test_fx_translation_closing_for_assets():
    eng = ConsolidatedTrialBalanceEngine()
    p = _entity("P", curr="KES", is_parent=True)
    f = _entity("F", curr="USD")
    tb = (
        _tb("P", "1000", AccountType.ASSET, dr=1000),
        _tb("F", "1000", AccountType.ASSET, dr=100),
    )
    rates = (
        FxRate(currency="USD", rate_type=FxRateType.CLOSING,
               rate_to_kes=Decimal("130"), period="2026-04"),
    )
    r = eng.consolidate("2026-04", (p, f), tb, fx_rates=rates)
    # 1000 + 100×130 = 14,000
    assert r.lines[0].pre_elimination_dr == Decimal("14000.00")


def _test_fx_translation_average_for_revenue():
    eng = ConsolidatedTrialBalanceEngine()
    p = _entity("P", curr="KES", is_parent=True)
    f = _entity("F", curr="USD")
    tb = (_tb("F", "4000", AccountType.REVENUE, cr=1000),)
    rates = (
        FxRate(currency="USD", rate_type=FxRateType.AVERAGE,
               rate_to_kes=Decimal("128"), period="2026-04"),
    )
    r = eng.consolidate("2026-04", (p, f), tb, fx_rates=rates)
    assert r.lines[0].pre_elimination_cr == Decimal("128000.00")
    assert r.lines[0].entity_contributions[0].fx_rate_type == (
        FxRateType.AVERAGE)


def _test_missing_fx_rate_surfaces_finding():
    eng = ConsolidatedTrialBalanceEngine()
    p = _entity("P", curr="KES", is_parent=True)
    f = _entity("F", curr="USD")
    tb = (_tb("F", "1000", AccountType.ASSET, dr=100),)
    r = eng.consolidate("2026-04", (p, f), tb, fx_rates=())
    fx_findings = [
        x for x in r.findings if "FX" in x.finding_id]
    assert len(fx_findings) >= 1


def _test_nci_allocation_80pct_owned():
    eng = ConsolidatedTrialBalanceEngine()
    p = _entity("P", is_parent=True)
    s = _entity("S", owner=Decimal("0.8"))
    tb = (_tb("S", "3000", AccountType.EQUITY, cr=1000000),)
    r = eng.consolidate("2026-04", (p, s), tb)
    line = r.lines[0]
    assert line.nci_share_cr == Decimal("200000.00")
    assert line.parent_share_cr == Decimal("800000.00")


def _test_parent_no_nci_allocation():
    eng = ConsolidatedTrialBalanceEngine()
    p = _entity("P", is_parent=True)
    tb = (_tb("P", "3000", AccountType.EQUITY, cr=500000),)
    r = eng.consolidate("2026-04", (p,), tb)
    assert r.lines[0].nci_share_cr == Decimal("0")
    assert r.lines[0].parent_share_cr == Decimal("500000.00")


def _test_missing_profile_critical():
    eng = ConsolidatedTrialBalanceEngine()
    p = _entity("P", is_parent=True)
    tb = (
        _tb("P", "1000", AccountType.ASSET, dr=100),
        _tb("UNKNOWN", "1000", AccountType.ASSET, dr=50),
    )
    r = eng.consolidate("2026-04", (p,), tb)
    crit = [
        x for x in r.findings
        if x.severity == ConsolidationSeverity.CRITICAL]
    assert len(crit) >= 1


def _test_period_filtering():
    eng = ConsolidatedTrialBalanceEngine()
    p = _entity("P", is_parent=True)
    tb = (
        _tb("P", "1000", AccountType.ASSET, dr=100,
            period="2026-04"),
        _tb("P", "1000", AccountType.ASSET, dr=999,
            period="2026-03"),
    )
    r = eng.consolidate("2026-04", (p,), tb)
    assert r.lines[0].pre_elimination_dr == Decimal("100")


def _test_full_provenance_per_line():
    eng = ConsolidatedTrialBalanceEngine()
    p = _entity("P", is_parent=True)
    s = _entity("S", owner=Decimal("0.75"))
    tb = (
        _tb("P", "1000", AccountType.ASSET, dr=1000),
        _tb("S", "1000", AccountType.ASSET, dr=400),
    )
    r = eng.consolidate("2026-04", (p, s), tb)
    line = r.lines[0]
    assert len(line.entity_contributions) == 2
    contribs = {
        c.entity_id: c for c in line.entity_contributions}
    assert "P" in contribs
    assert "S" in contribs
    assert contribs["P"].fx_rate_used == Decimal("1")
    assert any("ENH-251" in r for r in line.framework_refs)


def _test_engine_does_not_mutate_inputs():
    eng = ConsolidatedTrialBalanceEngine()
    p = _entity("P", is_parent=True)
    tb = (_tb("P", "1000", AccountType.ASSET, dr=500),)
    eng.consolidate("2026-04", (p,), tb)
    assert tb[0].debit_kes == Decimal("500")


def _test_top_level_aggregates():
    eng = ConsolidatedTrialBalanceEngine()
    p = _entity("P", is_parent=True)
    s = _entity("S")
    tb = (
        _tb("P", "1000", AccountType.ASSET, dr=500),
        _tb("S", "2000", AccountType.LIABILITY, cr=200),
    )
    r = eng.consolidate("2026-04", (p, s), tb)
    assert r.entities_consolidated == 2
    assert r.presentation_currency == "KES"
    assert r.total_dr == Decimal("500")
    assert r.total_cr == Decimal("200")
    assert any("IFRS 10" in x for x in r.framework_refs)
    assert any("Rule 7" in x for x in r.framework_refs)


def _test_unbalanced_tb_finding():
    eng = ConsolidatedTrialBalanceEngine()
    p = _entity("P", is_parent=True)
    tb = (_tb("P", "1000", AccountType.ASSET, dr=1000),)
    r = eng.consolidate("2026-04", (p,), tb)
    imb = [
        x for x in r.findings
        if x.finding_id == "CON-TB-IMBALANCE"]
    assert len(imb) == 1


def self_test() -> None:
    tests = [
        _test_entity_validates_ownership,
        _test_parent_must_be_100pct,
        _test_tb_validates_negative,
        _test_simple_aggregation_kes_only,
        _test_aggregation_with_elimination,
        _test_fx_translation_closing_for_assets,
        _test_fx_translation_average_for_revenue,
        _test_missing_fx_rate_surfaces_finding,
        _test_nci_allocation_80pct_owned,
        _test_parent_no_nci_allocation,
        _test_missing_profile_critical,
        _test_period_filtering,
        _test_full_provenance_per_line,
        _test_engine_does_not_mutate_inputs,
        _test_top_level_aggregates,
        _test_unbalanced_tb_finding,
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
            f"✗ consolidated_tb_engine self-test: "
            f"{len(failed)} failures",
            file=sys.stderr)
        for name, msg in failed:
            print(f"  - {name}: {msg}", file=sys.stderr)
        raise SystemExit(1)
    print(
        f"✓ consolidated_tb_engine self-test passed "
        f"({len(tests)} tests)")


if __name__ == "__main__":
    self_test()
