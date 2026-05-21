"""utils/intercompany_matching.py — v10.60: Intercompany Matching.

╔════════════════════════════════════════════════════════════════════════╗
║  ENH-250 — Intercompany Matching & Elimination                          ║
║  Cat B — finance arc 2/10                                               ║
╠════════════════════════════════════════════════════════════════════════╣
║  Pairs intercompany entries across legal entities and recommends        ║
║  elimination journals for consolidation. Where ENH-249 only flags       ║
║  unbalanced IC entries within a single period (engine doesn't know      ║
║  the counter-entity's books), ENH-250 takes a multi-entity view —       ║
║  GLEntries from parent + all subs flow in, the engine pairs by          ║
║  reference + counterparty and surfaces matches/mismatches.              ║
║                                                                          ║
║  Three matching modes:                                                   ║
║    EXACT        — same reference + opposite signs + amount within       ║
║                   tolerance (default KES 100 absolute)                  ║
║    AMOUNT_MISMATCH — same reference + opposite sides, but amount        ║
║                      differs beyond tolerance                           ║
║    UNMATCHED   — no offsetting entry found at all                       ║
║                                                                          ║
║  Multi-leg chain detection (P → S1 → S2) is supported when entries      ║
║  share a chain_id. Engine reports the chain as a unit and computes      ║
║  the net elimination required at the consolidation level.               ║
║                                                                          ║
║  Per Rule 7, engine is DIAGNOSTIC ONLY. It NEVER:                      ║
║    - posts elimination journals (recommends them)                       ║
║    - modifies entity-level GL (frozen contract)                         ║
║    - resolves matches without operator review                           ║
║    - decides which side is "correct" in a mismatch                      ║
║                                                                          ║
║  Per Rule 1, every IcMatch surfaces match_id + status + parties +       ║
║  references + amounts + recommended elimination + framework refs.       ║
║                                                                          ║
║  Pure stdlib (Decimal + frozen dataclasses + enums).                    ║
║                                                                          ║
║  Composes with:                                                          ║
║    - finance_close_orchestrator (ENH-249) — reuses IC concept;         ║
║      ENH-249 detects "pending" within one entity's books, ENH-250       ║
║      pairs across entities                                              ║
║    - group_consolidation (ENH-251) — consumes IcMatch output to        ║
║      apply eliminations during consolidation                            ║
╚════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Dict, List, Optional, Sequence, Tuple

SPEC_DEVIATION_NOTE = (
    "IntercompanyMatchingEngine implements ENH-250. Pure stdlib "
    "(Decimal + dataclasses + enums). Per Rule 1, every IcMatch "
    "surfaces match_id + status + entity_a + entity_b + "
    "reference + amount_a + amount_b + variance + recommended "
    "elimination + framework refs. Per Rule 7, engine DIAGNOSTIC "
    "ONLY — pairs entries, never posts eliminations; flags "
    "mismatches, never decides which side is correct; never "
    "resolves without operator review. Composes with ENH-249 "
    "(in-entity IC pending) and ENH-251 (consolidation, "
    "to-be-built)."
)


# ════════════════════════════════════════════════════════════════════════
# Enums
# ════════════════════════════════════════════════════════════════════════

class MatchStatus(Enum):
    EXACT = "EXACT"                       # within tolerance
    AMOUNT_MISMATCH = "AMOUNT_MISMATCH"   # same ref, diff amount
    UNMATCHED = "UNMATCHED"               # no counter-entry
    MULTI_LEG_CHAIN = "MULTI_LEG_CHAIN"   # part of a chain


class IcSeverity(Enum):
    CRITICAL = "CRITICAL"   # blocks consolidation
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class EliminationType(Enum):
    """The journal entry that eliminates this IC pair at consolidation."""
    REVENUE_EXPENSE = "REVENUE_EXPENSE"   # IC sales/cost
    RECEIVABLE_PAYABLE = "RECEIVABLE_PAYABLE"
    DIVIDEND = "DIVIDEND"
    LOAN = "LOAN"
    OTHER = "OTHER"


# ════════════════════════════════════════════════════════════════════════
# Input dataclasses
# ════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class IcEntry:
    """One intercompany entry from one entity's GL."""
    entry_id: str
    entity_id: str           # entity owning the GL
    counterparty_entity_id: str
    account_code: str
    debit_kes: Decimal
    credit_kes: Decimal
    period: str
    reference: str
    elimination_type: EliminationType
    chain_id: str = ""        # populated for multi-leg chains
    description: str = ""

    def __post_init__(self) -> None:
        if not self.entry_id:
            raise ValueError("entry_id must be non-empty")
        if not self.entity_id:
            raise ValueError("entity_id must be non-empty")
        if not self.counterparty_entity_id:
            raise ValueError(
                "counterparty_entity_id must be non-empty")
        if self.entity_id == self.counterparty_entity_id:
            raise ValueError(
                "counterparty must differ from entity")
        if not self.reference:
            raise ValueError("reference must be non-empty")
        if self.debit_kes < 0 or self.credit_kes < 0:
            raise ValueError("D/C amounts must be ≥ 0")
        if self.debit_kes > 0 and self.credit_kes > 0:
            raise ValueError(
                "IcEntry must be debit XOR credit, not both")
        if self.debit_kes == 0 and self.credit_kes == 0:
            raise ValueError(
                "IcEntry must have non-zero amount")


# ════════════════════════════════════════════════════════════════════════
# Output dataclasses
# ════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class EliminationRecommendation:
    """One recommended elimination journal at consolidation level."""
    rec_id: str
    elimination_type: EliminationType
    entity_a: str
    entity_b: str
    reference: str
    period: str
    debit_account: str        # account to debit at consolidation
    credit_account: str
    amount_kes: Decimal
    description: str


@dataclass(frozen=True)
class IcMatch:
    """One IC pairing result."""
    match_id: str
    status: MatchStatus
    severity: IcSeverity
    period: str
    reference: str
    entity_a: str
    entity_b: str
    entity_a_amount: Decimal
    entity_b_amount: Decimal
    variance_kes: Decimal     # a - b
    related_entry_ids: Tuple[str, ...]
    recommended_elimination: Optional[EliminationRecommendation]
    description: str
    framework_refs: Tuple[str, ...] = ()


@dataclass(frozen=True)
class IcMatchReport:
    period: str
    matches: Tuple[IcMatch, ...]
    by_status: Dict[str, int]
    by_severity: Dict[str, int]
    entries_scanned: int
    entities_scanned: int
    total_eliminations_recommended: int
    framework_refs: Tuple[str, ...]


# ════════════════════════════════════════════════════════════════════════
# Engine
# ════════════════════════════════════════════════════════════════════════

class IntercompanyMatchingEngine:
    """Diagnostic IC matching engine."""

    DEFAULT_AMOUNT_TOLERANCE_KES: Decimal = Decimal("100")

    def __init__(
        self,
        amount_tolerance_kes: Optional[Decimal] = None,
    ) -> None:
        self.tolerance = (
            amount_tolerance_kes
            or self.DEFAULT_AMOUNT_TOLERANCE_KES)

    @staticmethod
    def _signed(e: IcEntry) -> Decimal:
        """Net signed amount (positive = Dr, negative = Cr)."""
        return e.debit_kes - e.credit_kes

    @staticmethod
    def _account_for_elimination(
        e_type: EliminationType, side: str,
    ) -> str:
        """Stub for elimination account routing. Real systems map
        this from CoA + entity policy; engine surfaces a
        placeholder so operators see the recommended structure."""
        defaults = {
            EliminationType.REVENUE_EXPENSE: (
                "IC-REV", "IC-EXP"),
            EliminationType.RECEIVABLE_PAYABLE: (
                "IC-PAY", "IC-REC"),
            EliminationType.DIVIDEND: (
                "IC-DIV-RCVD", "IC-DIV-PAID"),
            EliminationType.LOAN: (
                "IC-LOAN-PAY", "IC-LOAN-REC"),
            EliminationType.OTHER: ("IC-OTHER-D", "IC-OTHER-C"),
        }
        dr, cr = defaults.get(
            e_type, ("IC-OTHER-D", "IC-OTHER-C"))
        return dr if side == "Dr" else cr

    def match_pairs(
        self,
        entries: Sequence[IcEntry],
        period: str,
    ) -> Tuple[IcMatch, ...]:
        """Pair entries by (reference, period) where one side has
        entity_a posting against counterparty entity_b and the
        other has entity_b posting against entity_a. Surface the
        match status."""
        # Group by reference within the period
        by_ref: Dict[str, List[IcEntry]] = {}
        for e in entries:
            if e.period != period:
                continue
            if e.chain_id:
                continue   # handled separately
            by_ref.setdefault(e.reference, []).append(e)

        matches: List[IcMatch] = []
        unmatched_solo: List[IcEntry] = []
        for ref, group in by_ref.items():
            if len(group) == 1:
                unmatched_solo.append(group[0])
                continue
            # Try to form pairs: for each entity ordered pair
            # find symmetric counter
            paired_indices: set = set()
            for i, e_a in enumerate(group):
                if i in paired_indices:
                    continue
                for j, e_b in enumerate(group):
                    if j <= i or j in paired_indices:
                        continue
                    if not self._is_pair(e_a, e_b):
                        continue
                    paired_indices.add(i)
                    paired_indices.add(j)
                    matches.append(self._build_match(
                        e_a, e_b, period))
                    break
            # Anything in this group not paired:
            for k, e in enumerate(group):
                if k not in paired_indices:
                    unmatched_solo.append(e)

        # Solo unmatched entries
        for e in unmatched_solo:
            matches.append(self._unmatched(e, period))

        return tuple(matches)

    @staticmethod
    def _is_pair(a: IcEntry, b: IcEntry) -> bool:
        """Two entries are an IC pair candidate if their entity/
        counterparty are mirror images and they're on opposite
        sides (Dr vs Cr)."""
        if not (a.entity_id == b.counterparty_entity_id
                and b.entity_id == a.counterparty_entity_id):
            return False
        a_is_dr = a.debit_kes > 0
        b_is_dr = b.debit_kes > 0
        return a_is_dr != b_is_dr

    def _build_match(
        self, a: IcEntry, b: IcEntry, period: str,
    ) -> IcMatch:
        # Normalise so entity_a is the Dr-side
        if a.debit_kes > 0:
            dr, cr = a, b
        else:
            dr, cr = b, a
        amount_dr = dr.debit_kes
        amount_cr = cr.credit_kes
        variance = amount_dr - amount_cr
        within_tol = abs(variance) <= self.tolerance
        status = (
            MatchStatus.EXACT if within_tol
            else MatchStatus.AMOUNT_MISMATCH)
        severity = (
            IcSeverity.LOW if within_tol
            else IcSeverity.HIGH)
        rec_elim = (
            self._recommend_elimination(dr, cr, period)
            if within_tol else None)
        if within_tol:
            description = (
                f"IC ref {dr.reference} matched: "
                f"{dr.entity_id} Dr {amount_dr} ↔ "
                f"{cr.entity_id} Cr {amount_cr} "
                f"(variance {variance})")
        else:
            description = (
                f"IC ref {dr.reference} amount mismatch: "
                f"{dr.entity_id} Dr {amount_dr} vs "
                f"{cr.entity_id} Cr {amount_cr} "
                f"(variance {variance}) — exceeds tolerance "
                f"{self.tolerance}")
        return IcMatch(
            match_id=f"ICM-{dr.reference}-{period}",
            status=status,
            severity=severity,
            period=period,
            reference=dr.reference,
            entity_a=dr.entity_id,
            entity_b=cr.entity_id,
            entity_a_amount=amount_dr,
            entity_b_amount=amount_cr,
            variance_kes=variance,
            related_entry_ids=(dr.entry_id, cr.entry_id),
            recommended_elimination=rec_elim,
            description=description,
            framework_refs=(
                "ENH-250 §match_pairs",
                "IFRS 10 — intra-group balances eliminate at "
                "consolidation"))

    def _recommend_elimination(
        self, dr: IcEntry, cr: IcEntry, period: str,
    ) -> EliminationRecommendation:
        e_type = dr.elimination_type
        return EliminationRecommendation(
            rec_id=f"ICM-ELIM-{dr.reference}-{period}",
            elimination_type=e_type,
            entity_a=dr.entity_id,
            entity_b=cr.entity_id,
            reference=dr.reference,
            period=period,
            debit_account=self._account_for_elimination(
                e_type, "Dr"),
            credit_account=self._account_for_elimination(
                e_type, "Cr"),
            amount_kes=dr.debit_kes,
            description=(
                f"recommended elimination: Dr "
                f"{self._account_for_elimination(e_type, 'Dr')} "
                f"/ Cr "
                f"{self._account_for_elimination(e_type, 'Cr')} "
                f"for {dr.debit_kes} (eliminates {e_type.value} "
                f"between {dr.entity_id} and {cr.entity_id})"))

    def _unmatched(
        self, e: IcEntry, period: str,
    ) -> IcMatch:
        amt = self._signed(e)
        return IcMatch(
            match_id=f"ICM-UNMATCHED-{e.entry_id}",
            status=MatchStatus.UNMATCHED,
            severity=IcSeverity.HIGH,
            period=period,
            reference=e.reference,
            entity_a=e.entity_id,
            entity_b=e.counterparty_entity_id,
            entity_a_amount=abs(amt),
            entity_b_amount=Decimal("0"),
            variance_kes=amt,
            related_entry_ids=(e.entry_id,),
            recommended_elimination=None,
            description=(
                f"IC ref {e.reference}: entry {e.entry_id} "
                f"posted by {e.entity_id} against "
                f"{e.counterparty_entity_id} but no offsetting "
                f"entry found — counter-entity hasn't booked"),
            framework_refs=(
                "ENH-250 §match_pairs",
                "IFRS 10 — both sides must exist before "
                "elimination"))

    def detect_chains(
        self,
        entries: Sequence[IcEntry],
        period: str,
    ) -> Tuple[IcMatch, ...]:
        """Multi-leg chain detection: entries sharing a chain_id
        are reported as a chain; engine computes net by chain."""
        by_chain: Dict[str, List[IcEntry]] = {}
        for e in entries:
            if e.period != period:
                continue
            if not e.chain_id:
                continue
            by_chain.setdefault(e.chain_id, []).append(e)

        matches: List[IcMatch] = []
        for chain_id, leg_entries in by_chain.items():
            net = sum(
                (self._signed(e) for e in leg_entries),
                Decimal("0"))
            entities = sorted({
                e.entity_id for e in leg_entries})
            within_tol = abs(net) <= self.tolerance
            severity = (
                IcSeverity.LOW if within_tol
                else IcSeverity.HIGH)
            description = (
                f"IC chain {chain_id} with {len(leg_entries)} "
                f"legs across entities {entities}: net Dr-Cr "
                f"= {net} "
                f"({'balanced' if within_tol else 'unbalanced'})")
            matches.append(IcMatch(
                match_id=f"ICM-CHAIN-{chain_id}-{period}",
                status=MatchStatus.MULTI_LEG_CHAIN,
                severity=severity,
                period=period,
                reference=chain_id,
                entity_a=entities[0] if entities else "",
                entity_b=(
                    entities[-1] if len(entities) > 1 else ""),
                entity_a_amount=net,
                entity_b_amount=Decimal("0"),
                variance_kes=net,
                related_entry_ids=tuple(
                    e.entry_id for e in leg_entries),
                recommended_elimination=None,
                description=description,
                framework_refs=(
                    "ENH-250 §detect_chains",
                    "IFRS 10 — multi-leg IC chains net to zero "
                    "after full elimination cascade")))
        return tuple(matches)

    def match_all(
        self,
        entries: Sequence[IcEntry],
        period: str,
    ) -> IcMatchReport:
        pair_matches = self.match_pairs(entries, period)
        chain_matches = self.detect_chains(entries, period)
        all_matches = pair_matches + chain_matches

        by_status: Dict[str, int] = {
            s.value: 0 for s in MatchStatus}
        for m in all_matches:
            by_status[m.status.value] += 1
        by_sev: Dict[str, int] = {
            s.value: 0 for s in IcSeverity}
        for m in all_matches:
            by_sev[m.severity.value] += 1

        rec_count = sum(
            1 for m in all_matches
            if m.recommended_elimination is not None)

        entities = {e.entity_id for e in entries} | {
            e.counterparty_entity_id for e in entries}

        return IcMatchReport(
            period=period,
            matches=all_matches,
            by_status=by_status,
            by_severity=by_sev,
            entries_scanned=len(entries),
            entities_scanned=len(entities),
            total_eliminations_recommended=rec_count,
            framework_refs=(
                "ENH-250 §match_all",
                "Per Rule 7 — recommends eliminations only; "
                "never posts at entity or consolidation level",
            ))


# ════════════════════════════════════════════════════════════════════════
# Self-tests
# ════════════════════════════════════════════════════════════════════════

def _e(eid, ent, ce, dr=0, cr=0, ref="REF1",
       et=EliminationType.RECEIVABLE_PAYABLE,
       chain="", period="2026-04"):
    return IcEntry(
        entry_id=eid, entity_id=ent, counterparty_entity_id=ce,
        account_code="IC-1500",
        debit_kes=Decimal(str(dr)), credit_kes=Decimal(str(cr)),
        period=period, reference=ref,
        elimination_type=et, chain_id=chain)


def _test_entry_validates_self_counterparty():
    try:
        _e("e1", "PARENT", "PARENT", dr=100)
        assert False
    except ValueError:
        pass


def _test_entry_validates_dr_xor_cr():
    try:
        _e("e1", "P", "S", dr=100, cr=100)
        assert False
    except ValueError:
        pass


def _test_entry_validates_nonzero():
    try:
        _e("e1", "P", "S", dr=0, cr=0)
        assert False
    except ValueError:
        pass


def _test_entry_validates_reference():
    try:
        _e("e1", "P", "S", dr=100, ref="")
        assert False
    except ValueError:
        pass


def _test_exact_match():
    eng = IntercompanyMatchingEngine()
    a = _e("a", "PARENT", "SUBA", dr=100000)
    b = _e("b", "SUBA", "PARENT", cr=100000)
    matches = eng.match_pairs((a, b), "2026-04")
    assert len(matches) == 1
    assert matches[0].status == MatchStatus.EXACT
    assert matches[0].severity == IcSeverity.LOW
    assert matches[0].recommended_elimination is not None


def _test_amount_mismatch():
    eng = IntercompanyMatchingEngine()
    a = _e("a", "PARENT", "SUBA", dr=100000)
    b = _e("b", "SUBA", "PARENT", cr=99000)
    matches = eng.match_pairs((a, b), "2026-04")
    assert len(matches) == 1
    assert matches[0].status == MatchStatus.AMOUNT_MISMATCH
    assert matches[0].severity == IcSeverity.HIGH
    assert matches[0].variance_kes == Decimal("1000")
    assert matches[0].recommended_elimination is None


def _test_within_tolerance_still_exact():
    eng = IntercompanyMatchingEngine()
    a = _e("a", "PARENT", "SUBA", dr=100000)
    b = _e("b", "SUBA", "PARENT", cr=99950)
    # variance 50 ≤ default 100 tolerance
    matches = eng.match_pairs((a, b), "2026-04")
    assert len(matches) == 1
    assert matches[0].status == MatchStatus.EXACT


def _test_unmatched_solo():
    eng = IntercompanyMatchingEngine()
    a = _e("a", "PARENT", "SUBA", dr=100000)
    matches = eng.match_pairs((a,), "2026-04")
    assert len(matches) == 1
    assert matches[0].status == MatchStatus.UNMATCHED
    assert matches[0].severity == IcSeverity.HIGH


def _test_only_offsetting_sides_match():
    """Same reference but both Dr = not a pair."""
    eng = IntercompanyMatchingEngine()
    a = _e("a", "PARENT", "SUBA", dr=100000)
    b = _e("b", "SUBA", "PARENT", dr=100000)  # both Dr
    matches = eng.match_pairs((a, b), "2026-04")
    # neither pairs, both unmatched
    assert len(matches) == 2
    assert all(
        m.status == MatchStatus.UNMATCHED for m in matches)


def _test_mirror_entities_required():
    """A→B and A→C with same reference don't pair."""
    eng = IntercompanyMatchingEngine()
    a = _e("a", "PARENT", "SUBA", dr=100000)
    c = _e("c", "PARENT", "SUBC", cr=100000)
    matches = eng.match_pairs((a, c), "2026-04")
    assert len(matches) == 2
    assert all(
        m.status == MatchStatus.UNMATCHED for m in matches)


def _test_period_scoping():
    """Entries from other periods ignored."""
    eng = IntercompanyMatchingEngine()
    a = _e("a", "PARENT", "SUBA", dr=100000)
    b = _e("b", "SUBA", "PARENT", cr=100000, period="2026-03")
    matches = eng.match_pairs((a, b), "2026-04")
    assert len(matches) == 1
    assert matches[0].status == MatchStatus.UNMATCHED


def _test_chain_detection_balanced():
    eng = IntercompanyMatchingEngine()
    # 3-leg chain: P→S1 100k, S1→S2 100k, S2 receives → S2 books Cr 100k
    e1 = _e("e1", "PARENT", "S1", dr=100000, ref="X1",
            chain="CH-001")
    e2 = _e("e2", "S1", "PARENT", cr=100000, ref="X1",
            chain="CH-001")
    # net should balance (sum signed = 0)
    matches = eng.detect_chains((e1, e2), "2026-04")
    assert len(matches) == 1
    assert matches[0].status == MatchStatus.MULTI_LEG_CHAIN
    assert matches[0].variance_kes == Decimal("0")
    assert matches[0].severity == IcSeverity.LOW


def _test_chain_detection_unbalanced():
    eng = IntercompanyMatchingEngine()
    e1 = _e("e1", "P", "S1", dr=100000, ref="X", chain="CH")
    e2 = _e("e2", "S1", "S2", dr=50000, ref="Y", chain="CH")
    matches = eng.detect_chains((e1, e2), "2026-04")
    assert len(matches) == 1
    assert matches[0].status == MatchStatus.MULTI_LEG_CHAIN
    assert matches[0].variance_kes == Decimal("150000")
    assert matches[0].severity == IcSeverity.HIGH


def _test_match_all_orchestrates():
    eng = IntercompanyMatchingEngine()
    # 1 exact + 1 unmatched + 1 chain
    a = _e("a", "PARENT", "SUBA", dr=100000, ref="R1")
    b = _e("b", "SUBA", "PARENT", cr=100000, ref="R1")
    solo = _e("c", "PARENT", "SUBC", dr=50000, ref="R2")
    chain1 = _e("ch1", "P", "S1", dr=200000, ref="X",
                chain="CH-001")
    chain2 = _e("ch2", "S1", "P", cr=200000, ref="X",
                chain="CH-001")
    report = eng.match_all(
        (a, b, solo, chain1, chain2), "2026-04")
    assert isinstance(report, IcMatchReport)
    assert report.entries_scanned == 5
    assert report.entities_scanned >= 4   # PARENT,SUBA,SUBC,S1
    assert report.total_eliminations_recommended == 1


def _test_match_provenance_full():
    eng = IntercompanyMatchingEngine()
    a = _e("a", "PARENT", "SUBA", dr=100000)
    b = _e("b", "SUBA", "PARENT", cr=100000)
    matches = eng.match_pairs((a, b), "2026-04")
    m = matches[0]
    assert m.match_id
    assert m.entity_a == "PARENT"
    assert m.entity_b == "SUBA"
    assert "a" in m.related_entry_ids
    assert "b" in m.related_entry_ids
    assert any("ENH-250" in r for r in m.framework_refs)
    assert m.recommended_elimination is not None
    rec = m.recommended_elimination
    assert rec.entity_a == "PARENT"
    assert rec.entity_b == "SUBA"
    assert rec.amount_kes == Decimal("100000")


def _test_elimination_account_routing_per_type():
    eng = IntercompanyMatchingEngine()
    div_a = _e("a", "PARENT", "SUBA", cr=50000,
               et=EliminationType.DIVIDEND)
    div_b = _e("b", "SUBA", "PARENT", dr=50000,
               et=EliminationType.DIVIDEND)
    matches = eng.match_pairs((div_a, div_b), "2026-04")
    assert len(matches) == 1
    rec = matches[0].recommended_elimination
    assert rec is not None
    assert "DIV" in rec.debit_account
    assert "DIV" in rec.credit_account


def _test_engine_does_not_mutate_inputs():
    eng = IntercompanyMatchingEngine()
    a = _e("a", "PARENT", "SUBA", dr=100000)
    b = _e("b", "SUBA", "PARENT", cr=100000)
    eng.match_pairs((a, b), "2026-04")
    assert a.debit_kes == Decimal("100000")
    assert b.credit_kes == Decimal("100000")


def _test_custom_tolerance():
    eng = IntercompanyMatchingEngine(
        amount_tolerance_kes=Decimal("5000"))
    a = _e("a", "PARENT", "SUBA", dr=100000)
    b = _e("b", "SUBA", "PARENT", cr=97000)
    # variance 3000 ≤ tolerance 5000 → EXACT
    matches = eng.match_pairs((a, b), "2026-04")
    assert matches[0].status == MatchStatus.EXACT


def self_test() -> None:
    tests = [
        _test_entry_validates_self_counterparty,
        _test_entry_validates_dr_xor_cr,
        _test_entry_validates_nonzero,
        _test_entry_validates_reference,
        _test_exact_match,
        _test_amount_mismatch,
        _test_within_tolerance_still_exact,
        _test_unmatched_solo,
        _test_only_offsetting_sides_match,
        _test_mirror_entities_required,
        _test_period_scoping,
        _test_chain_detection_balanced,
        _test_chain_detection_unbalanced,
        _test_match_all_orchestrates,
        _test_match_provenance_full,
        _test_elimination_account_routing_per_type,
        _test_engine_does_not_mutate_inputs,
        _test_custom_tolerance,
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
            f"✗ intercompany_matching self-test: "
            f"{len(failed)} failures",
            file=sys.stderr)
        for name, msg in failed:
            print(f"  - {name}: {msg}", file=sys.stderr)
        raise SystemExit(1)
    print(
        f"✓ intercompany_matching self-test passed "
        f"({len(tests)} tests)")


if __name__ == "__main__":
    self_test()
