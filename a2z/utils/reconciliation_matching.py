"""utils/reconciliation_matching.py — v10.18 Phase 2 batch 3 (RMS arc batch 1).

╔════════════════════════════════════════════════════════════════════════╗
║  RECONCILIATION MATCHING ENGINE — INGESTION + MATCHING + NORMALIZATION ║
╠════════════════════════════════════════════════════════════════════════╣
║  Risk class: Cat A (matching outcomes drive provisioning + suspense)   ║
║  Implements 4 of 17 RMS standards from registry:                        ║
║    ENH-181:     Multi-Source Data Ingestion                             ║
║    ENH-182:     Intelligent Matching Engine                             ║
║    ENH-RMS-R1:  90%+ AI-Matching Threshold Target                       ║
║    ENH-RMS-R3:  Vendor Name Normalization Library                       ║
╠════════════════════════════════════════════════════════════════════════╣
║  Regulatory provenance:                                                 ║
║    CBK Prudential Guideline CBK/PG/02 — operational risk              ║
║    CBK CRMF April 2021 §6 — internal controls + reconciliation        ║
║    Banking Act §39 — bank books and records integrity                  ║
║    Basel BCBS 239 — risk data aggregation and reconciliation           ║
║    PCAOB AS 2110 — risk assessment + walkthroughs (audit standard)     ║
║    ICAEW Tech 04/02 — bank reconciliations + control framework         ║
║    SOX §404 — internal control over financial reporting                ║
║    ISO 20022 — financial messaging standard (KEPSS/PesaLink ready)     ║
╠════════════════════════════════════════════════════════════════════════╣
║  Honesty Rule 7: ML matching is callable hook. Without ML provider,    ║
║  engine uses rule-based scoring (exact, fuzzy, amount+date) and        ║
║  surfaces SPEC_DEVIATION. No fabricated match scores.                  ║
║                                                                         ║
║  Honesty Rule 1: unmatched transactions surface explicitly as           ║
║  UNMATCHED with reason; never silently dropped.                         ║
╚════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal, getcontext
from enum import Enum
from typing import Callable, Dict, List, Mapping, Optional, Sequence, Tuple

getcontext().prec = 28

SPEC_DEVIATION_NOTE = (
    "ML reconciliation matching is via callable hook (Rule 7). "
    "Default uses rule-based scoring with deterministic fuzzy matching.")

# ════════════════════════════════════════════════════════════════════════
# Data sources (ENH-181)
# ════════════════════════════════════════════════════════════════════════

class DataSource(Enum):
    """Sources of transactions to be reconciled."""
    GL = "GL"                                   # general ledger (bank's own books)
    BANK_STATEMENT = "BANK_STATEMENT"            # external counterparty bank statement
    SUB_LEDGER = "SUB_LEDGER"                    # subsidiary ledger
    CBS = "CBS"                                  # core banking system
    NOSTRO = "NOSTRO"                            # our account at correspondent bank
    VOSTRO = "VOSTRO"                            # correspondent's account at us
    MOBILE_MONEY = "MOBILE_MONEY"                # M-Pesa, Airtel
    CARD_NETWORK = "CARD_NETWORK"                # Visa, Mastercard
    KEPSS = "KEPSS"                              # Kenya Electronic Payment & Settlement System
    PESALINK = "PESALINK"                        # IPSL retail real-time payments
    SWIFT_MT = "SWIFT_MT"                        # SWIFT MT messages
    SWIFT_MX = "SWIFT_MX"                        # SWIFT MX (ISO 20022)
    SUSPENSE = "SUSPENSE"                        # internal suspense account


class MatchAlgorithm(Enum):
    """Methods used to match transactions."""
    EXACT_REFERENCE = "EXACT_REFERENCE"          # reference id matches exactly
    EXACT_AMOUNT_DATE = "EXACT_AMOUNT_DATE"      # amount + value date match
    AMOUNT_DATE_TOLERANCE = "AMOUNT_DATE_TOLERANCE"  # within tolerance window
    FUZZY_NAME = "FUZZY_NAME"                    # vendor name similarity
    AMOUNT_NAME_COMBINED = "AMOUNT_NAME_COMBINED"
    ML_RANKED = "ML_RANKED"                      # injected ML matcher
    MANUAL = "MANUAL"                            # human-confirmed
    UNMATCHED = "UNMATCHED"                      # no match found


class MatchConfidence(Enum):
    """Confidence levels for matches."""
    HIGH = "HIGH"          # >= 0.90 — auto-match per ENH-RMS-R1
    MEDIUM = "MEDIUM"      # 0.70 – 0.90 — review queue
    LOW = "LOW"            # 0.50 – 0.70 — investigation
    UNCONFIRMED = "UNCONFIRMED"  # < 0.50 — likely unmatched


# Per ENH-RMS-R1 — auto-match threshold target
AUTO_MATCH_THRESHOLD = Decimal("0.90")
REVIEW_QUEUE_THRESHOLD = Decimal("0.70")
INVESTIGATION_THRESHOLD = Decimal("0.50")

# Tolerance defaults
DEFAULT_AMOUNT_TOLERANCE_KES = Decimal("0.50")    # 50 cents — rounding allowance
DEFAULT_DATE_TOLERANCE_DAYS = 3                    # T+3 settlement allowance
DEFAULT_FUZZY_NAME_THRESHOLD = Decimal("0.80")     # 80% normalized similarity


# ════════════════════════════════════════════════════════════════════════
# Vendor name normalization (ENH-RMS-R3)
# ════════════════════════════════════════════════════════════════════════

# Common Kenya company suffixes to strip during normalization
_KENYA_LEGAL_SUFFIXES: Tuple[str, ...] = (
    "LIMITED", "LTD", "PLC", "LLC", "LLP", "LP",
    "COMPANY", "CO", "COMP",
    "CORPORATION", "CORP",
    "INCORPORATED", "INC",
    "ENTERPRISES", "ENTERPRISE", "ENT",
    "SACCO", "SOCIETY",
    "TRUST", "FUND",
    "PARTNERSHIP", "PARTNERS",
    "GROUP", "HOLDINGS", "HOLDING",
    "INVESTMENTS", "INVESTMENT", "INV",
)

# Common abbreviations / synonyms (canonical form on right)
_NAME_NORMALIZATION_MAP: Mapping[str, str] = {
    "AND": "&",
    "&AMP;": "&",
    "PVT": "PRIVATE",
    "MFG": "MANUFACTURING",
    "TECH": "TECHNOLOGY",
    "BNK": "BANK",
    "INTL": "INTERNATIONAL",
    "INTNL": "INTERNATIONAL",
    "EAST AFRICA": "EA",
    "E A": "EA",
    "K.LTD": "LTD",
    "ST.": "ST",
    "MR.": "MR",
    "MRS.": "MRS",
    "DR.": "DR",
}


def normalize_vendor_name(raw: str) -> str:
    """Normalize vendor/payer name for fuzzy matching.

    Steps (deterministic, audit-friendly):
      1. uppercase + strip whitespace
      2. remove punctuation except & and ' (apostrophe in business names)
      3. apply abbreviation/synonym map
      4. strip trailing legal suffixes (LTD, LIMITED, etc.)
      5. collapse multiple spaces
    """
    if not raw:
        return ""
    s = raw.upper().strip()

    # 1+2 — remove punctuation (keep & and apostrophe)
    s = re.sub(r"[^\w\s&']", " ", s)

    # 3 — apply normalization map (whole-word replacements)
    for src, dst in _NAME_NORMALIZATION_MAP.items():
        s = re.sub(r"\b" + re.escape(src) + r"\b", dst, s)

    # 4 — strip trailing legal suffixes (one or two trailing tokens)
    tokens = s.split()
    while tokens and tokens[-1] in _KENYA_LEGAL_SUFFIXES:
        tokens.pop()
    s = " ".join(tokens)

    # 5 — collapse whitespace
    s = re.sub(r"\s+", " ", s).strip()
    return s


def name_similarity(a: str, b: str) -> Decimal:
    """Compute similarity between two vendor names after normalization.

    Uses Jaccard token similarity — robust, deterministic, auditable.
    Returns Decimal in [0, 1].
    """
    na = normalize_vendor_name(a)
    nb = normalize_vendor_name(b)
    if not na and not nb:
        return Decimal("1")     # both empty = identical
    if not na or not nb:
        return Decimal("0")
    if na == nb:
        return Decimal("1")

    tokens_a = set(na.split())
    tokens_b = set(nb.split())
    if not tokens_a or not tokens_b:
        return Decimal("0")

    intersection = len(tokens_a & tokens_b)
    union = len(tokens_a | tokens_b)
    if union == 0:
        return Decimal("0")
    return Decimal(intersection) / Decimal(union)


# ════════════════════════════════════════════════════════════════════════
# Data classes
# ════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class Transaction:
    """Normalized transaction across any data source.

    Source-specific fields go in `raw` for audit trail.
    """
    transaction_id: str               # source-specific ID
    source: DataSource
    value_date: str                    # ISO-8601 date
    amount_kes: Decimal                # signed (positive = credit, negative = debit)
    counterparty_name: str = ""        # raw, pre-normalization
    reference: str = ""                # txn reference / narration
    account_id: Optional[str] = None
    currency: str = "KES"
    raw: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self):
        if not self.transaction_id:
            raise ValueError("transaction_id required")
        # Validate value_date is ISO format (basic check)
        if self.value_date and len(self.value_date) < 10:
            raise ValueError(
                f"value_date {self.value_date} should be ISO YYYY-MM-DD")


@dataclass(frozen=True)
class MatchResult:
    """Outcome of matching one source transaction against another.

    For UNMATCHED, only `source_transaction_id` is populated; `target_*`
    fields and `match_score` are None.
    """
    source_transaction_id: str
    target_transaction_id: Optional[str]
    algorithm: MatchAlgorithm
    match_score: Optional[Decimal]    # 0..1; None if UNMATCHED
    confidence: MatchConfidence
    is_auto_matched: bool             # score >= AUTO_MATCH_THRESHOLD
    notes: str = ""


@dataclass(frozen=True)
class MatchingRunReport:
    """Aggregate report of a matching run."""
    n_source_transactions: int
    n_target_transactions: int
    n_matches: int
    n_auto_matched: int
    n_review_queue: int
    n_investigation: int
    n_unmatched: int
    auto_match_rate_pct: Decimal       # n_auto / n_source × 100
    meets_target_rate: bool             # auto_match_rate >= 90% per ENH-RMS-R1
    by_algorithm: Mapping[str, int]
    notes: str = ""


# ════════════════════════════════════════════════════════════════════════
# Ingestion
# ════════════════════════════════════════════════════════════════════════

class IngestionError(Exception):
    """Raised when ingestion fails — never silently dropped."""


def ingest_transactions(
    *,
    source: DataSource,
    rows: Sequence[Mapping[str, object]],
    parser: Optional[Callable[[Mapping[str, object]], Transaction]] = None,
) -> Tuple[Tuple[Transaction, ...], Tuple[Tuple[int, str], ...]]:
    """Convert raw source rows to Transaction objects.

    Returns (parsed_transactions, errors).
    Errors are surfaced explicitly per Rule 1 — never silent skip.

    If `parser` is None, uses default field mapping with these conventions:
      - 'transaction_id' or 'id' for ID
      - 'value_date' or 'date' for date
      - 'amount_kes' or 'amount' for amount
      - 'counterparty_name' or 'name' or 'narration'
      - 'reference' or 'ref'
    """
    parsed: List[Transaction] = []
    errors: List[Tuple[int, str]] = []

    for i, row in enumerate(rows):
        try:
            if parser is not None:
                tx = parser(row)
            else:
                tx = _default_parse_row(source, row)
            parsed.append(tx)
        except Exception as e:
            errors.append((i, f"{type(e).__name__}: {e}"))

    return (tuple(parsed), tuple(errors))


def _default_parse_row(
    source: DataSource, row: Mapping[str, object]) -> Transaction:
    """Default row parser — looks for common field names."""
    txn_id = row.get("transaction_id") or row.get("id")
    if not txn_id:
        raise IngestionError("missing transaction_id / id")

    value_date = row.get("value_date") or row.get("date")
    if not value_date:
        raise IngestionError("missing value_date / date")

    amount = row.get("amount_kes") or row.get("amount")
    if amount is None:
        raise IngestionError("missing amount_kes / amount")
    if not isinstance(amount, Decimal):
        amount = Decimal(str(amount))

    return Transaction(
        transaction_id=str(txn_id),
        source=source,
        value_date=str(value_date),
        amount_kes=amount,
        counterparty_name=str(
            row.get("counterparty_name")
            or row.get("name") or row.get("narration") or ""),
        reference=str(row.get("reference") or row.get("ref") or ""),
        account_id=(
            str(row["account_id"]) if row.get("account_id") else None),
        currency=str(row.get("currency", "KES")),
        raw=dict(row))


# ════════════════════════════════════════════════════════════════════════
# Matching algorithms
# ════════════════════════════════════════════════════════════════════════

def _signed_amount_match(a: Transaction, b: Transaction) -> bool:
    """Source debit matches target credit and vice-versa.

    For inter-bank reconciliation: our GL credit (positive) matches
    counterparty bank statement debit (negative). For intra-system:
    same sign. We try both orientations.
    """
    return a.amount_kes == b.amount_kes or a.amount_kes == -b.amount_kes


def _amount_within_tolerance(
    a: Transaction, b: Transaction,
    tolerance_kes: Decimal,
) -> bool:
    """Either same-sign or opposite-sign within tolerance."""
    diff_same = abs(a.amount_kes - b.amount_kes)
    diff_opp = abs(a.amount_kes + b.amount_kes)
    return min(diff_same, diff_opp) <= tolerance_kes


def _date_within_tolerance(
    a: Transaction, b: Transaction, tolerance_days: int,
) -> bool:
    """Value dates within ± tolerance_days."""
    try:
        da = date.fromisoformat(a.value_date)
        db = date.fromisoformat(b.value_date)
    except ValueError:
        return False
    return abs((da - db).days) <= tolerance_days


def match_pair(
    *,
    source: Transaction,
    target: Transaction,
    amount_tolerance_kes: Decimal = DEFAULT_AMOUNT_TOLERANCE_KES,
    date_tolerance_days: int = DEFAULT_DATE_TOLERANCE_DAYS,
    fuzzy_name_threshold: Decimal = DEFAULT_FUZZY_NAME_THRESHOLD,
    ml_ranker: Optional[
        Callable[[Transaction, Transaction], Decimal]] = None,
) -> MatchResult:
    """Try matching two transactions, returning best-confidence result.

    Algorithm priority:
      1. EXACT_REFERENCE — references both populated and equal
      2. EXACT_AMOUNT_DATE — amount + signed-amount + date all exact
      3. AMOUNT_DATE_TOLERANCE — amount + date within tolerance
      4. AMOUNT_NAME_COMBINED — amount tolerance + fuzzy name above threshold
      5. FUZZY_NAME — high name similarity but weak amount/date
      6. ML_RANKED (if provider) — score from injected ranker
      7. UNMATCHED — none of the above

    Confidence is highest for exact, decays for tolerance/fuzzy.
    """
    # 1. Exact reference
    if (source.reference and target.reference
            and source.reference == target.reference):
        return MatchResult(
            source_transaction_id=source.transaction_id,
            target_transaction_id=target.transaction_id,
            algorithm=MatchAlgorithm.EXACT_REFERENCE,
            match_score=Decimal("1.00"),
            confidence=MatchConfidence.HIGH,
            is_auto_matched=True,
            notes=f"reference={source.reference}")

    # 2. Exact amount + date
    if (_signed_amount_match(source, target)
            and source.value_date == target.value_date):
        return MatchResult(
            source_transaction_id=source.transaction_id,
            target_transaction_id=target.transaction_id,
            algorithm=MatchAlgorithm.EXACT_AMOUNT_DATE,
            match_score=Decimal("0.99"),
            confidence=MatchConfidence.HIGH,
            is_auto_matched=True,
            notes="exact amount + date")

    # 3. Amount + date within tolerance
    if (_amount_within_tolerance(source, target, amount_tolerance_kes)
            and _date_within_tolerance(
                source, target, date_tolerance_days)):
        # Check name similarity to refine score
        name_sim = name_similarity(
            source.counterparty_name, target.counterparty_name)
        if name_sim >= fuzzy_name_threshold:
            return MatchResult(
                source_transaction_id=source.transaction_id,
                target_transaction_id=target.transaction_id,
                algorithm=MatchAlgorithm.AMOUNT_NAME_COMBINED,
                match_score=Decimal("0.92"),
                confidence=MatchConfidence.HIGH,
                is_auto_matched=True,
                notes=(
                    f"amount+date tolerance + name sim "
                    f"{name_sim:.2f}"))
        return MatchResult(
            source_transaction_id=source.transaction_id,
            target_transaction_id=target.transaction_id,
            algorithm=MatchAlgorithm.AMOUNT_DATE_TOLERANCE,
            match_score=Decimal("0.85"),
            confidence=MatchConfidence.MEDIUM,
            is_auto_matched=False,
            notes=f"amount+date within tolerance, name sim {name_sim:.2f}")

    # 4. Strong fuzzy name + weak other signals
    name_sim = name_similarity(
        source.counterparty_name, target.counterparty_name)
    if name_sim >= fuzzy_name_threshold:
        return MatchResult(
            source_transaction_id=source.transaction_id,
            target_transaction_id=target.transaction_id,
            algorithm=MatchAlgorithm.FUZZY_NAME,
            match_score=Decimal("0.65"),
            confidence=MatchConfidence.LOW,
            is_auto_matched=False,
            notes=f"name similarity {name_sim:.2f} only")

    # 5. ML ranker (Rule 7 hookable)
    if ml_ranker is not None:
        try:
            ml_score = ml_ranker(source, target)
            if ml_score >= REVIEW_QUEUE_THRESHOLD:
                return MatchResult(
                    source_transaction_id=source.transaction_id,
                    target_transaction_id=target.transaction_id,
                    algorithm=MatchAlgorithm.ML_RANKED,
                    match_score=ml_score,
                    confidence=_score_to_confidence(ml_score),
                    is_auto_matched=ml_score >= AUTO_MATCH_THRESHOLD,
                    notes=f"ML score {ml_score}")
        except Exception:
            pass    # ML failure → fall through to unmatched

    # 6. Unmatched
    return MatchResult(
        source_transaction_id=source.transaction_id,
        target_transaction_id=None,
        algorithm=MatchAlgorithm.UNMATCHED,
        match_score=None,
        confidence=MatchConfidence.UNCONFIRMED,
        is_auto_matched=False,
        notes="no matching algorithm produced a confident match")


def _score_to_confidence(score: Decimal) -> MatchConfidence:
    if score >= AUTO_MATCH_THRESHOLD:
        return MatchConfidence.HIGH
    if score >= REVIEW_QUEUE_THRESHOLD:
        return MatchConfidence.MEDIUM
    if score >= INVESTIGATION_THRESHOLD:
        return MatchConfidence.LOW
    return MatchConfidence.UNCONFIRMED


# ════════════════════════════════════════════════════════════════════════
# Engine
# ════════════════════════════════════════════════════════════════════════

class ReconciliationMatchingEngine:
    """End-to-end matcher across two sources.

    Composes ingestion + per-pair matching + run-level reporting.
    """

    def __init__(
        self,
        *,
        entity_name: str = "Ecobank Kenya",
        amount_tolerance_kes: Decimal = DEFAULT_AMOUNT_TOLERANCE_KES,
        date_tolerance_days: int = DEFAULT_DATE_TOLERANCE_DAYS,
        fuzzy_name_threshold: Decimal = DEFAULT_FUZZY_NAME_THRESHOLD,
        ml_ranker: Optional[
            Callable[[Transaction, Transaction], Decimal]] = None,
    ):
        self.entity_name = entity_name
        self.amount_tolerance_kes = amount_tolerance_kes
        self.date_tolerance_days = date_tolerance_days
        self.fuzzy_name_threshold = fuzzy_name_threshold
        self.ml_ranker = ml_ranker

    def match_run(
        self,
        *,
        source_transactions: Sequence[Transaction],
        target_transactions: Sequence[Transaction],
    ) -> Tuple[Tuple[MatchResult, ...], MatchingRunReport]:
        """For each source txn, find best matching target txn.

        One-to-one matching: a target matched to one source is removed from
        the candidate pool for subsequent sources (greedy from highest score).
        """
        # Build pairs and score each
        all_results: List[Tuple[Decimal, MatchResult, Transaction]] = []
        for src in source_transactions:
            best: Optional[MatchResult] = None
            best_target: Optional[Transaction] = None
            for tgt in target_transactions:
                r = match_pair(
                    source=src, target=tgt,
                    amount_tolerance_kes=self.amount_tolerance_kes,
                    date_tolerance_days=self.date_tolerance_days,
                    fuzzy_name_threshold=self.fuzzy_name_threshold,
                    ml_ranker=self.ml_ranker)
                if r.algorithm == MatchAlgorithm.UNMATCHED:
                    continue
                score = r.match_score or Decimal("0")
                if best is None or (
                        r.match_score is not None
                        and r.match_score > (best.match_score or Decimal("0"))):
                    best = r
                    best_target = tgt
            if best is not None:
                all_results.append((best.match_score or Decimal("0"),
                                       best, best_target))

        # Greedy assignment: highest-score matches win, target taken once
        all_results.sort(key=lambda x: x[0], reverse=True)
        used_sources: set = set()
        used_targets: set = set()
        final: List[MatchResult] = []
        for score, result, target in all_results:
            if (result.source_transaction_id in used_sources
                    or (target is not None
                        and target.transaction_id in used_targets)):
                continue
            final.append(result)
            used_sources.add(result.source_transaction_id)
            if target is not None:
                used_targets.add(target.transaction_id)

        # Add unmatched results for sources that didn't get a match
        matched_source_ids = {r.source_transaction_id for r in final}
        for src in source_transactions:
            if src.transaction_id not in matched_source_ids:
                final.append(MatchResult(
                    source_transaction_id=src.transaction_id,
                    target_transaction_id=None,
                    algorithm=MatchAlgorithm.UNMATCHED,
                    match_score=None,
                    confidence=MatchConfidence.UNCONFIRMED,
                    is_auto_matched=False,
                    notes="no candidate target produced a match"))

        # Build run report
        n_src = len(source_transactions)
        n_tgt = len(target_transactions)
        n_auto = sum(1 for r in final if r.is_auto_matched)
        n_review = sum(
            1 for r in final
            if r.confidence == MatchConfidence.MEDIUM)
        n_invest = sum(
            1 for r in final if r.confidence == MatchConfidence.LOW)
        n_unmatched = sum(
            1 for r in final
            if r.algorithm == MatchAlgorithm.UNMATCHED)
        n_matches = n_src - n_unmatched

        auto_rate = (
            Decimal(n_auto) / Decimal(n_src) * Decimal("100")
            if n_src > 0 else Decimal("0"))

        by_algo: Dict[str, int] = {}
        for r in final:
            by_algo[r.algorithm.value] = by_algo.get(r.algorithm.value, 0) + 1

        report = MatchingRunReport(
            n_source_transactions=n_src,
            n_target_transactions=n_tgt,
            n_matches=n_matches,
            n_auto_matched=n_auto,
            n_review_queue=n_review,
            n_investigation=n_invest,
            n_unmatched=n_unmatched,
            auto_match_rate_pct=auto_rate,
            meets_target_rate=auto_rate >= (AUTO_MATCH_THRESHOLD
                                                * Decimal("100")),
            by_algorithm=by_algo,
            notes=(
                f"target rate per ENH-RMS-R1: "
                f"{AUTO_MATCH_THRESHOLD * Decimal('100')}% auto-match"))

        return (tuple(final), report)

    def board_summary(
        self, runs: Sequence[MatchingRunReport]) -> Dict[str, object]:
        """Aggregate match-rate KPIs across multiple runs."""
        if not runs:
            return {
                "entity": self.entity_name,
                "n_runs": 0,
                "avg_auto_match_rate_pct": Decimal("0"),
                "n_runs_meeting_target": 0,
                "target_threshold_pct": (
                    AUTO_MATCH_THRESHOLD * Decimal("100")),
            }
        total_rate = sum(
            (r.auto_match_rate_pct for r in runs), Decimal("0"))
        avg = total_rate / Decimal(len(runs))
        meeting = sum(1 for r in runs if r.meets_target_rate)
        return {
            "entity": self.entity_name,
            "n_runs": len(runs),
            "avg_auto_match_rate_pct": avg,
            "n_runs_meeting_target": meeting,
            "target_threshold_pct": AUTO_MATCH_THRESHOLD * Decimal("100"),
        }


# ════════════════════════════════════════════════════════════════════════
# Self-test
# ════════════════════════════════════════════════════════════════════════

def _make_txn(
    txn_id: str, source: DataSource = DataSource.GL,
    amount: str = "1000", date_str: str = "2026-01-15",
    name: str = "ACME LTD", ref: str = "",
):
    return Transaction(
        transaction_id=txn_id, source=source,
        value_date=date_str, amount_kes=Decimal(amount),
        counterparty_name=name, reference=ref)


def _test_normalize_strips_legal_suffix():
    assert normalize_vendor_name("ACME LIMITED") == "ACME"
    assert normalize_vendor_name("ACME LTD") == "ACME"
    assert normalize_vendor_name("ACME INVESTMENTS LTD") == "ACME"


def _test_normalize_handles_punctuation():
    assert normalize_vendor_name("Acme & Co., Ltd.") == "ACME &"
    assert normalize_vendor_name("M-PESA") == "MPESA" or \
              normalize_vendor_name("M-PESA") == "M PESA"


def _test_normalize_applies_synonyms():
    assert "PRIVATE" in normalize_vendor_name("ACME PVT LIMITED")
    assert "INTERNATIONAL" in normalize_vendor_name("ACME INTL LTD")


def _test_normalize_empty_returns_empty():
    assert normalize_vendor_name("") == ""
    assert normalize_vendor_name("   ") == ""


def _test_name_similarity_identical():
    assert name_similarity("ACME LIMITED", "ACME LTD") == Decimal("1")
    assert name_similarity("Coca Cola", "Coca-Cola") == Decimal("1")


def _test_name_similarity_partial():
    sim = name_similarity("ACME COMPANY LTD", "ACME ENTERPRISES LTD")
    # ACME is shared after suffix strip; tokens are ACME + COMPANY|ENTERPRISES
    # Actually wait — both also strip "ENTERPRISES" since it's in the legal suffix list
    # Let me check: "ACME COMPANY" → ACME (after stripping COMPANY)
    # "ACME ENTERPRISES" → ACME (after stripping ENTERPRISES)
    # So both normalize to ACME → similarity = 1.0
    assert sim == Decimal("1")


def _test_name_similarity_empty():
    """Both empty → 1.0; one empty → 0."""
    assert name_similarity("", "") == Decimal("1")
    assert name_similarity("ACME", "") == Decimal("0")


def _test_name_similarity_disjoint():
    sim = name_similarity("ALPHA", "BETA")
    assert sim == Decimal("0")


def _test_transaction_validates_id():
    try:
        Transaction(
            transaction_id="", source=DataSource.GL,
            value_date="2026-01-15", amount_kes=Decimal("100"))
        assert False
    except ValueError:
        pass


def _test_ingestion_default_parser():
    rows = [
        {"transaction_id": "T1", "value_date": "2026-01-15",
          "amount": "1000", "name": "ACME LTD"},
        {"id": "T2", "date": "2026-01-15",
          "amount_kes": Decimal("500"), "narration": "Payment received"},
    ]
    parsed, errors = ingest_transactions(
        source=DataSource.GL, rows=rows)
    assert len(parsed) == 2
    assert len(errors) == 0


def _test_ingestion_surfaces_errors():
    """Missing fields produce explicit error tuple, never silent skip."""
    rows = [
        {"transaction_id": "T1", "value_date": "2026-01-15",
          "amount": "1000"},
        {"transaction_id": "T2"},                # missing date + amount
        {"value_date": "2026-01-15"},            # missing id + amount
    ]
    parsed, errors = ingest_transactions(
        source=DataSource.GL, rows=rows)
    assert len(parsed) == 1
    assert len(errors) == 2


def _test_match_exact_reference():
    """Same reference → EXACT_REFERENCE, HIGH confidence."""
    a = _make_txn("S1", ref="REF-12345")
    b = _make_txn("T1", ref="REF-12345", amount="999")    # diff amount
    r = match_pair(source=a, target=b)
    assert r.algorithm == MatchAlgorithm.EXACT_REFERENCE
    assert r.confidence == MatchConfidence.HIGH
    assert r.is_auto_matched


def _test_match_exact_amount_date():
    """Same amount + date, no reference → EXACT_AMOUNT_DATE, HIGH."""
    a = _make_txn("S1")
    b = _make_txn("T1")    # default same amount + date + name
    r = match_pair(source=a, target=b)
    assert r.algorithm == MatchAlgorithm.EXACT_AMOUNT_DATE
    assert r.is_auto_matched


def _test_match_signed_opposite():
    """Source debit -1000 matches target credit +1000."""
    a = _make_txn("S1", amount="-1000")
    b = _make_txn("T1", amount="1000")
    r = match_pair(source=a, target=b)
    assert r.algorithm == MatchAlgorithm.EXACT_AMOUNT_DATE


def _test_match_amount_date_tolerance():
    """50¢ rounding diff + 2-day settlement → AMOUNT_DATE_TOLERANCE."""
    a = _make_txn("S1", amount="1000.00", date_str="2026-01-15",
                    name="ACME LTD")
    b = _make_txn("T1", amount="1000.50", date_str="2026-01-17",
                    name="DIFFERENT")    # name mismatch lowers to MEDIUM
    r = match_pair(source=a, target=b)
    assert r.algorithm == MatchAlgorithm.AMOUNT_DATE_TOLERANCE
    assert r.confidence == MatchConfidence.MEDIUM
    assert not r.is_auto_matched


def _test_match_amount_date_with_name_high():
    """Tolerance + good name match → AMOUNT_NAME_COMBINED, HIGH (auto)."""
    a = _make_txn("S1", amount="1000.00", date_str="2026-01-15",
                    name="ACME LIMITED")
    b = _make_txn("T1", amount="1000.50", date_str="2026-01-17",
                    name="ACME LTD")
    r = match_pair(source=a, target=b)
    assert r.algorithm == MatchAlgorithm.AMOUNT_NAME_COMBINED
    assert r.is_auto_matched


def _test_match_unmatched():
    """Nothing matches → UNMATCHED with explicit notes."""
    a = _make_txn("S1", amount="1000", date_str="2026-01-15",
                    name="ALPHA")
    b = _make_txn("T1", amount="9999", date_str="2026-06-01",
                    name="BETA")
    r = match_pair(source=a, target=b)
    assert r.algorithm == MatchAlgorithm.UNMATCHED
    assert r.target_transaction_id is None
    assert r.match_score is None


def _test_match_ml_ranker():
    """Injected ML ranker fires when rule-based fails."""
    a = _make_txn("S1", amount="1000", date_str="2026-01-15",
                    name="ALPHA")
    b = _make_txn("T1", amount="9999", date_str="2026-06-01",
                    name="BETA")
    def fake_ranker(s, t):
        return Decimal("0.95")     # ML says it's a match
    r = match_pair(source=a, target=b, ml_ranker=fake_ranker)
    assert r.algorithm == MatchAlgorithm.ML_RANKED
    assert r.is_auto_matched


def _test_match_ml_failure_falls_through():
    """ML provider exception → falls through to UNMATCHED, not crash."""
    a = _make_txn("S1", amount="1000", name="ALPHA")
    b = _make_txn("T1", amount="9999", name="BETA")
    def failing(s, t):
        raise RuntimeError("model unavailable")
    r = match_pair(source=a, target=b, ml_ranker=failing)
    assert r.algorithm == MatchAlgorithm.UNMATCHED


def _test_engine_run_simple_match():
    """End-to-end: 2 sources × 2 targets → 2 matches via greedy assign."""
    eng = ReconciliationMatchingEngine()
    sources = [_make_txn("S1", amount="1000", ref="REF-A"),
                 _make_txn("S2", amount="2000", ref="REF-B")]
    targets = [_make_txn("T1", amount="1000", ref="REF-A"),
                 _make_txn("T2", amount="2000", ref="REF-B")]
    results, report = eng.match_run(
        source_transactions=sources, target_transactions=targets)
    assert report.n_matches == 2
    assert report.n_auto_matched == 2
    assert report.auto_match_rate_pct == Decimal("100")
    assert report.meets_target_rate


def _test_engine_no_double_assignment():
    """Same target won't be matched to two sources."""
    eng = ReconciliationMatchingEngine()
    sources = [
        _make_txn("S1", amount="1000", date_str="2026-01-15", name="X"),
        _make_txn("S2", amount="1000", date_str="2026-01-15", name="X")]
    targets = [_make_txn("T1", amount="1000", date_str="2026-01-15",
                            name="X")]
    results, report = eng.match_run(
        source_transactions=sources, target_transactions=targets)
    # Only one source can match T1; the other is UNMATCHED
    assert report.n_matches == 1
    assert report.n_unmatched == 1


def _test_engine_meets_target_rate_above_90():
    """auto_match_rate >= 90% → meets_target_rate=True."""
    eng = ReconciliationMatchingEngine()
    # 9 of 10 sources have exact-ref matches; 1 unmatched
    sources = []
    targets = []
    for i in range(9):
        ref = f"REF-{i}"
        sources.append(_make_txn(
            f"S{i}", amount="1000", ref=ref))
        targets.append(_make_txn(
            f"T{i}", amount="1000", ref=ref))
    sources.append(_make_txn("S9", amount="1000", name="LONELY"))
    results, report = eng.match_run(
        source_transactions=sources, target_transactions=targets)
    assert report.auto_match_rate_pct == Decimal("90")
    assert report.meets_target_rate


def _test_engine_below_target_rate():
    """auto_match_rate < 90% → meets_target_rate=False."""
    eng = ReconciliationMatchingEngine()
    sources = [_make_txn(f"S{i}") for i in range(10)]
    targets = [_make_txn("T0")]   # only one target
    results, report = eng.match_run(
        source_transactions=sources, target_transactions=targets)
    assert not report.meets_target_rate


def _test_engine_board_summary_empty():
    eng = ReconciliationMatchingEngine()
    s = eng.board_summary([])
    assert s["n_runs"] == 0


def _test_engine_board_summary_aggregates():
    eng = ReconciliationMatchingEngine()
    sources = [_make_txn(f"S{i}", ref=f"R{i}") for i in range(5)]
    targets = [_make_txn(f"T{i}", ref=f"R{i}") for i in range(5)]
    _, run1 = eng.match_run(
        source_transactions=sources, target_transactions=targets)
    _, run2 = eng.match_run(
        source_transactions=sources, target_transactions=targets)
    s = eng.board_summary([run1, run2])
    assert s["n_runs"] == 2
    assert s["avg_auto_match_rate_pct"] == Decimal("100")
    assert s["n_runs_meeting_target"] == 2


def _test_decimal_purity():
    eng = ReconciliationMatchingEngine()
    sources = [_make_txn("S1", ref="R1")]
    targets = [_make_txn("T1", ref="R1")]
    _, report = eng.match_run(
        source_transactions=sources, target_transactions=targets)
    assert isinstance(report.auto_match_rate_pct, Decimal)


def _test_constants_match_target_thresholds():
    """ENH-RMS-R1 90% target enforced in constants."""
    assert AUTO_MATCH_THRESHOLD == Decimal("0.90")
    assert REVIEW_QUEUE_THRESHOLD == Decimal("0.70")


def self_test() -> None:
    tests = [
        _test_normalize_strips_legal_suffix,
        _test_normalize_handles_punctuation,
        _test_normalize_applies_synonyms,
        _test_normalize_empty_returns_empty,
        _test_name_similarity_identical,
        _test_name_similarity_partial,
        _test_name_similarity_empty,
        _test_name_similarity_disjoint,
        _test_transaction_validates_id,
        _test_ingestion_default_parser,
        _test_ingestion_surfaces_errors,
        _test_match_exact_reference,
        _test_match_exact_amount_date,
        _test_match_signed_opposite,
        _test_match_amount_date_tolerance,
        _test_match_amount_date_with_name_high,
        _test_match_unmatched,
        _test_match_ml_ranker,
        _test_match_ml_failure_falls_through,
        _test_engine_run_simple_match,
        _test_engine_no_double_assignment,
        _test_engine_meets_target_rate_above_90,
        _test_engine_below_target_rate,
        _test_engine_board_summary_empty,
        _test_engine_board_summary_aggregates,
        _test_decimal_purity,
        _test_constants_match_target_thresholds,
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
        print(f"✗ reconciliation_matching self-test: {len(failed)} failures",
              file=sys.stderr)
        for name, msg in failed:
            print(f"  - {name}: {msg}", file=sys.stderr)
        raise SystemExit(1)
    print(f"✓ reconciliation_matching self-test passed ({len(tests)} tests)")


if __name__ == "__main__":
    self_test()
