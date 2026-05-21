"""utils/reconciliation_workflow.py — v10.19 Phase 2 batch 3 (RMS arc batch 2).

╔════════════════════════════════════════════════════════════════════════╗
║  RECONCILIATION WORKFLOW — EXCEPTION MGMT + MEMORY + TIMING + GUARDS   ║
╠════════════════════════════════════════════════════════════════════════╣
║  Risk class: Cat A (auto-resolution + write-off actions affect books) ║
║  Implements 4 of 17 RMS standards from registry:                        ║
║    ENH-183:     Exception Management & Workflow                         ║
║    ENH-RMS-R2:  Memory-Layer Architecture (pattern recall)             ║
║    ENH-RMS-R4:  Timing-Difference Auto-Handling                         ║
║    ENH-RMS-R5:  Governed Execution Layer (TruePath-style)               ║
╠════════════════════════════════════════════════════════════════════════╣
║  Regulatory provenance:                                                 ║
║    CBK Prudential Guideline CBK/PG/02 — operational risk              ║
║    CBK CRMF April 2021 §6 — internal controls + reconciliation        ║
║    CBK Banking Act §39 — books and records integrity                   ║
║    PCAOB AS 2401 — fraud risk + management override of controls       ║
║    SOX §404 — internal control over financial reporting               ║
║    COSO ERM — three lines of defense + control activities             ║
║    Basel BCBS 239 §5 — accuracy and integrity principles              ║
║    Kenya Data Protection Act 2019 §28 — retention                      ║
╠════════════════════════════════════════════════════════════════════════╣
║  Composes with: utils/reconciliation_matching.py (v10.18) — UNMATCHED  ║
║                  + MEDIUM/LOW confidence matches feed into exceptions   ║
║                                                                         ║
║  Honesty Rule 1: pattern recall surfaces confidence + match count;     ║
║  no silent "this is just like before" — caller sees evidence.          ║
║  Honesty Rule 7: guardrails are explicit; auto-action requires         ║
║  passing all configured guards or it surfaces blocked-with-reason.     ║
╚════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal, getcontext
from enum import Enum
from typing import Callable, Dict, List, Mapping, Optional, Sequence, Tuple

getcontext().prec = 28


# ════════════════════════════════════════════════════════════════════════
# Exception types + lifecycle (ENH-183)
# ════════════════════════════════════════════════════════════════════════

class ExceptionType(Enum):
    """Categories of reconciliation exceptions."""
    UNMATCHED_SOURCE = "UNMATCHED_SOURCE"      # source txn has no target
    UNMATCHED_TARGET = "UNMATCHED_TARGET"      # target txn has no source
    AMOUNT_MISMATCH = "AMOUNT_MISMATCH"        # amounts differ beyond tolerance
    TIMING_DIFFERENCE = "TIMING_DIFFERENCE"    # value dates differ
    ONE_TO_MANY = "ONE_TO_MANY"                # one source, multiple targets
    MANY_TO_ONE = "MANY_TO_ONE"                # multiple sources, one target
    DUPLICATE_SUSPECTED = "DUPLICATE_SUSPECTED"  # potentially booked twice
    REFERENCE_MISSING = "REFERENCE_MISSING"    # cannot match — no reference
    WRONG_ACCOUNT = "WRONG_ACCOUNT"            # booked to wrong account
    REVIEW_QUEUE = "REVIEW_QUEUE"              # MEDIUM confidence match flagged


class ExceptionState(Enum):
    """Lifecycle states for a reconciliation exception."""
    NEW = "NEW"
    ASSIGNED = "ASSIGNED"
    INVESTIGATING = "INVESTIGATING"
    PENDING_APPROVAL = "PENDING_APPROVAL"
    AUTO_RESOLVED = "AUTO_RESOLVED"
    MANUALLY_RESOLVED = "MANUALLY_RESOLVED"
    ESCALATED = "ESCALATED"
    WRITTEN_OFF = "WRITTEN_OFF"
    REJECTED_NEEDS_REVERSAL = "REJECTED_NEEDS_REVERSAL"


# Allowed transitions
ALLOWED_EXC_TRANSITIONS: Mapping[ExceptionState, Tuple[ExceptionState, ...]] = {
    ExceptionState.NEW: (
        ExceptionState.ASSIGNED, ExceptionState.AUTO_RESOLVED),
    ExceptionState.ASSIGNED: (
        ExceptionState.INVESTIGATING, ExceptionState.ESCALATED,
        ExceptionState.AUTO_RESOLVED),
    ExceptionState.INVESTIGATING: (
        ExceptionState.PENDING_APPROVAL,
        ExceptionState.MANUALLY_RESOLVED,
        ExceptionState.ESCALATED,
        ExceptionState.REJECTED_NEEDS_REVERSAL),
    ExceptionState.PENDING_APPROVAL: (
        ExceptionState.MANUALLY_RESOLVED,
        ExceptionState.WRITTEN_OFF,
        ExceptionState.ESCALATED),
    ExceptionState.ESCALATED: (
        ExceptionState.MANUALLY_RESOLVED,
        ExceptionState.WRITTEN_OFF),
    # Terminal states
    ExceptionState.AUTO_RESOLVED: (),
    ExceptionState.MANUALLY_RESOLVED: (),
    ExceptionState.WRITTEN_OFF: (),
    ExceptionState.REJECTED_NEEDS_REVERSAL: (),
}


def is_terminal_exception_state(state: ExceptionState) -> bool:
    return len(ALLOWED_EXC_TRANSITIONS.get(state, ())) == 0


def is_valid_exception_transition(
    from_state: ExceptionState, to_state: ExceptionState) -> bool:
    return to_state in ALLOWED_EXC_TRANSITIONS.get(from_state, ())


class AgingBucket(Enum):
    """Days-since-created buckets for SLA tracking."""
    FRESH_0_3 = "FRESH_0_3"          # 0–3 days
    AGING_4_7 = "AGING_4_7"          # 4–7 days
    OVERDUE_8_30 = "OVERDUE_8_30"    # 8–30 days
    BREACH_30_PLUS = "BREACH_30_PLUS"  # > 30 days — SLA breach


def compute_aging_bucket(days_open: int) -> AgingBucket:
    if days_open < 0:
        raise ValueError(f"days_open {days_open} cannot be negative")
    if days_open <= 3:
        return AgingBucket.FRESH_0_3
    if days_open <= 7:
        return AgingBucket.AGING_4_7
    if days_open <= 30:
        return AgingBucket.OVERDUE_8_30
    return AgingBucket.BREACH_30_PLUS


# Default SLA thresholds (days) by exception type
DEFAULT_SLA_DAYS: Mapping[ExceptionType, int] = {
    ExceptionType.UNMATCHED_SOURCE: 7,
    ExceptionType.UNMATCHED_TARGET: 7,
    ExceptionType.AMOUNT_MISMATCH: 5,
    ExceptionType.TIMING_DIFFERENCE: 3,
    ExceptionType.ONE_TO_MANY: 7,
    ExceptionType.MANY_TO_ONE: 7,
    ExceptionType.DUPLICATE_SUSPECTED: 3,
    ExceptionType.REFERENCE_MISSING: 5,
    ExceptionType.WRONG_ACCOUNT: 3,
    ExceptionType.REVIEW_QUEUE: 5,
}


# ════════════════════════════════════════════════════════════════════════
# Exception assignment rules
# ════════════════════════════════════════════════════════════════════════

class AssignmentQueue(Enum):
    """Operational queues for routing exceptions."""
    OPS_RECON_TIER1 = "OPS_RECON_TIER1"        # routine breaks
    OPS_RECON_TIER2 = "OPS_RECON_TIER2"        # complex breaks
    NOSTRO_DESK = "NOSTRO_DESK"                # Nostro/Vostro specific
    TRADE_OPS = "TRADE_OPS"                    # trade finance
    TREASURY_OPS = "TREASURY_OPS"              # treasury
    CARDS_OPS = "CARDS_OPS"                    # card networks
    MOBILE_MONEY_OPS = "MOBILE_MONEY_OPS"      # M-Pesa, Airtel
    MGMT_REVIEW = "MGMT_REVIEW"                # escalated
    FINANCE_WRITEOFF_PANEL = "FINANCE_WRITEOFF_PANEL"  # write-off committee


# Amount tier thresholds (KES) for queue routing
ASSIGNMENT_AMOUNT_TIER_LOW_KES = Decimal("100000")        # 100K
ASSIGNMENT_AMOUNT_TIER_HIGH_KES = Decimal("10000000")     # 10M


def assign_queue(
    *,
    exception_type: ExceptionType,
    amount_kes: Decimal,
    source_hint: str = "",
) -> AssignmentQueue:
    """Route an exception to the right operational queue.

    Routing rules:
      - Nostro/Vostro hint → NOSTRO_DESK
      - Mobile money hint → MOBILE_MONEY_OPS
      - Card network hint → CARDS_OPS
      - Trade finance hint → TRADE_OPS
      - Treasury hint → TREASURY_OPS
      - Amount > 10M → MGMT_REVIEW (regardless of type)
      - Amount > 100K → OPS_RECON_TIER2
      - Otherwise → OPS_RECON_TIER1
    """
    hint = source_hint.upper() if source_hint else ""

    if amount_kes > ASSIGNMENT_AMOUNT_TIER_HIGH_KES:
        return AssignmentQueue.MGMT_REVIEW

    if "NOSTRO" in hint or "VOSTRO" in hint:
        return AssignmentQueue.NOSTRO_DESK
    if "MPESA" in hint or "M-PESA" in hint or "AIRTEL" in hint:
        return AssignmentQueue.MOBILE_MONEY_OPS
    if "CARD" in hint or "VISA" in hint or "MASTERCARD" in hint:
        return AssignmentQueue.CARDS_OPS
    if "TRADE" in hint or "LC" in hint or "GUARANTEE" in hint:
        return AssignmentQueue.TRADE_OPS
    if "TREASURY" in hint or "MM" in hint or "FX" in hint:
        return AssignmentQueue.TREASURY_OPS

    if amount_kes > ASSIGNMENT_AMOUNT_TIER_LOW_KES:
        return AssignmentQueue.OPS_RECON_TIER2
    return AssignmentQueue.OPS_RECON_TIER1


# ════════════════════════════════════════════════════════════════════════
# Exception record dataclass
# ════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class ExceptionRecord:
    """One reconciliation exception."""
    exception_id: str
    exception_type: ExceptionType
    state: ExceptionState
    created_at: str                       # ISO-8601
    amount_kes: Decimal
    counterparty_name: str = ""
    source_transaction_id: Optional[str] = None
    target_transaction_id: Optional[str] = None
    assigned_queue: Optional[AssignmentQueue] = None
    assigned_to_user_id: Optional[str] = None
    sla_days: int = 7
    resolution_pattern_id: Optional[str] = None
    auto_action_taken: bool = False
    notes: str = ""

    def days_open(self, *, as_of: date) -> int:
        """Days since creation."""
        try:
            created = date.fromisoformat(self.created_at[:10])
        except ValueError:
            return 0
        return max(0, (as_of - created).days)

    def aging(self, *, as_of: date) -> AgingBucket:
        return compute_aging_bucket(self.days_open(as_of=as_of))

    def is_sla_breached(self, *, as_of: date) -> bool:
        return self.days_open(as_of=as_of) > self.sla_days


# ════════════════════════════════════════════════════════════════════════
# Memory layer (ENH-RMS-R2)
# ════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class ResolutionPattern:
    """Pattern of past resolutions, keyed by canonical signature.

    When a new exception arrives, the engine looks up its signature; if a
    pattern exists, the engine surfaces "we've seen N similar exceptions
    before, all resolved by [resolution_action]". Confidence grows with
    occurrence count.
    """
    pattern_id: str
    signature: str                        # canonical key — see compute_signature
    occurrence_count: int                  # how many times this pattern has occurred
    last_seen: str                         # ISO-8601 timestamp
    typical_resolution: str                # e.g. "WRITE_OFF_TO_FX_REVAL"
    typical_account: str = ""              # GL account used
    confidence: Decimal = Decimal("0.5")    # 0–1
    notes: str = ""


def compute_signature(
    *,
    exception_type: ExceptionType,
    amount_kes: Decimal,
    counterparty_name: str,
    amount_buckets: Tuple[Decimal, ...] = (
        Decimal("1000"), Decimal("10000"), Decimal("100000"),
        Decimal("1000000"), Decimal("10000000")),
) -> str:
    """Canonical signature for memory lookup.

    Bucket amount + normalize counterparty so similar exceptions match.
    """
    # Find amount bucket
    amount_bucket = "MICRO"
    for b in amount_buckets:
        if amount_kes <= b:
            amount_bucket = f"<={b}"
            break
    else:
        amount_bucket = "MEGA"
    # Normalize counterparty (use first 3 tokens, uppercased)
    cp = counterparty_name.upper().strip()
    cp_tokens = cp.split()[:3]
    cp_canonical = "_".join(cp_tokens)
    return f"{exception_type.value}|{amount_bucket}|{cp_canonical}"


# Confidence growth thresholds for memory recall
MEMORY_CONFIDENCE_LOW = Decimal("0.5")        # 1 occurrence
MEMORY_CONFIDENCE_MEDIUM = Decimal("0.75")    # 3+ occurrences
MEMORY_CONFIDENCE_HIGH = Decimal("0.90")      # 10+ occurrences


def confidence_from_occurrences(count: int) -> Decimal:
    """Map occurrence count to memory recall confidence."""
    if count >= 10:
        return MEMORY_CONFIDENCE_HIGH
    if count >= 3:
        return MEMORY_CONFIDENCE_MEDIUM
    if count >= 1:
        return MEMORY_CONFIDENCE_LOW
    return Decimal("0")


class MemoryLayer:
    """Pattern memory for recurring exceptions.

    Per ENH-RMS-R2: when the same exception signature recurs, surface what
    was done last time — with confidence based on occurrence count.

    Per Rule 1: caller always sees:
      - whether a pattern was found
      - the occurrence count
      - the historical resolution
      - confidence
    No silent "this is just like before" — evidence is surfaced.
    """

    def __init__(self):
        self._patterns: Dict[str, ResolutionPattern] = {}

    def record_resolution(
        self,
        *,
        exception_record: ExceptionRecord,
        resolution_action: str,
        gl_account: str = "",
        timestamp: str = "",
    ) -> ResolutionPattern:
        """Record a resolution; create or update the pattern."""
        sig = compute_signature(
            exception_type=exception_record.exception_type,
            amount_kes=exception_record.amount_kes,
            counterparty_name=exception_record.counterparty_name)

        existing = self._patterns.get(sig)
        if existing is None:
            new_pattern = ResolutionPattern(
                pattern_id=f"PAT-{len(self._patterns) + 1:06d}",
                signature=sig, occurrence_count=1,
                last_seen=timestamp,
                typical_resolution=resolution_action,
                typical_account=gl_account,
                confidence=confidence_from_occurrences(1))
            self._patterns[sig] = new_pattern
            return new_pattern

        new_count = existing.occurrence_count + 1
        # Update typical_resolution to most recent (could be enhanced to
        # mode/majority — but Rule 1 says don't fabricate; recent is honest)
        updated = ResolutionPattern(
            pattern_id=existing.pattern_id,
            signature=sig, occurrence_count=new_count,
            last_seen=timestamp,
            typical_resolution=resolution_action,
            typical_account=gl_account,
            confidence=confidence_from_occurrences(new_count),
            notes=existing.notes)
        self._patterns[sig] = updated
        return updated

    def recall(
        self,
        *,
        exception_type: ExceptionType,
        amount_kes: Decimal,
        counterparty_name: str,
    ) -> Optional[ResolutionPattern]:
        """Look up a pattern matching this exception's signature."""
        sig = compute_signature(
            exception_type=exception_type,
            amount_kes=amount_kes,
            counterparty_name=counterparty_name)
        return self._patterns.get(sig)


# ════════════════════════════════════════════════════════════════════════
# Timing-difference auto-handling (ENH-RMS-R4)
# ════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class TimingDifferenceConfig:
    """Configuration for timing-difference auto-resolution."""
    max_lag_days: int = 3                # T+3 settlement default
    auto_resolve_max_lag_days: int = 1    # T+1 auto, > T+1 needs review
    require_same_amount: bool = True
    require_same_counterparty: bool = True


@dataclass(frozen=True)
class TimingDifferenceCandidate:
    """A potential timing-difference pairing."""
    source_exception_id: str
    target_transaction_id: str
    lag_days: int
    amount_kes: Decimal
    counterparty_name: str
    can_auto_resolve: bool
    reason: str


def detect_timing_difference(
    *,
    exception: ExceptionRecord,
    candidate_target_value_date: str,
    candidate_target_amount_kes: Decimal,
    candidate_target_counterparty: str,
    candidate_target_id: str,
    config: Optional[TimingDifferenceConfig] = None,
) -> Optional[TimingDifferenceCandidate]:
    """Check if a candidate target represents a timing-difference resolution.

    Returns None if the candidate doesn't meet timing-diff criteria.
    Returns a TimingDifferenceCandidate (with can_auto_resolve flag) if
    it qualifies.
    """
    cfg = config or TimingDifferenceConfig()

    if cfg.require_same_amount and (
            exception.amount_kes != candidate_target_amount_kes):
        return None

    if cfg.require_same_counterparty:
        # Use simple normalization here — full normalization is in v10.18
        a_name = exception.counterparty_name.upper().strip()
        b_name = candidate_target_counterparty.upper().strip()
        if a_name and b_name and a_name != b_name:
            # Allow partial match if one starts with other (handles "ACME LTD" vs "ACME")
            if not (a_name.startswith(b_name) or b_name.startswith(a_name)):
                return None

    try:
        exc_date = date.fromisoformat(exception.created_at[:10])
        cand_date = date.fromisoformat(candidate_target_value_date)
    except ValueError:
        return None
    lag_days = abs((cand_date - exc_date).days)

    if lag_days > cfg.max_lag_days:
        return None

    can_auto = lag_days <= cfg.auto_resolve_max_lag_days
    reason = (
        f"T+{lag_days} timing match"
        + (" — auto-resolvable" if can_auto else
              " — exceeds auto threshold; manual review"))

    return TimingDifferenceCandidate(
        source_exception_id=exception.exception_id,
        target_transaction_id=candidate_target_id,
        lag_days=lag_days,
        amount_kes=exception.amount_kes,
        counterparty_name=exception.counterparty_name,
        can_auto_resolve=can_auto,
        reason=reason)


# ════════════════════════════════════════════════════════════════════════
# Governed execution layer (ENH-RMS-R5)
# ════════════════════════════════════════════════════════════════════════

class GuardRailType(Enum):
    """Types of guards on auto-actions."""
    AMOUNT_LIMIT = "AMOUNT_LIMIT"
    ALLOWED_ACCOUNT_TYPES = "ALLOWED_ACCOUNT_TYPES"
    BUSINESS_HOURS_ONLY = "BUSINESS_HOURS_ONLY"
    REQUIRES_DUAL_APPROVAL = "REQUIRES_DUAL_APPROVAL"
    RATE_LIMIT_PER_HOUR = "RATE_LIMIT_PER_HOUR"
    BLOCKED_COUNTERPARTIES = "BLOCKED_COUNTERPARTIES"
    PATTERN_CONFIDENCE_FLOOR = "PATTERN_CONFIDENCE_FLOOR"


@dataclass(frozen=True)
class GuardRail:
    """A single guardrail definition."""
    guard_id: str
    guard_type: GuardRailType
    config: Mapping[str, object]      # e.g. {"max_amount_kes": Decimal("50000")}
    notes: str = ""


@dataclass(frozen=True)
class GuardCheckResult:
    """Result of evaluating a single guard."""
    guard_id: str
    guard_type: GuardRailType
    passed: bool
    reason: str = ""


@dataclass(frozen=True)
class GovernedExecutionDecision:
    """Output of evaluating all guards on a proposed auto-action."""
    action_proposed: str                     # e.g. "AUTO_RESOLVE_TIMING_DIFF"
    guards_evaluated: Tuple[GuardCheckResult, ...]
    is_permitted: bool                        # all guards passed
    blocked_by_guard_ids: Tuple[str, ...]
    requires_dual_approval: bool
    notes: str = ""


# Default global guards — TruePath-style defaults
DEFAULT_AUTO_RESOLUTION_AMOUNT_LIMIT_KES = Decimal("50000")     # auto only ≤ 50K
DEFAULT_PATTERN_CONFIDENCE_FLOOR = Decimal("0.75")              # MEMORY_CONFIDENCE_MEDIUM


def evaluate_guards(
    *,
    action: str,
    proposed_amount_kes: Decimal,
    counterparty: str = "",
    pattern_confidence: Optional[Decimal] = None,
    rate_limit_count_in_hour: int = 0,
    is_business_hours: bool = True,
    account_type: str = "",
    guards: Sequence[GuardRail] = (),
) -> GovernedExecutionDecision:
    """Evaluate all configured guards on a proposed action.

    Returns the full decision with per-guard outcomes — caller sees exactly
    why something was blocked (or permitted).
    """
    results: List[GuardCheckResult] = []
    blocked_by: List[str] = []
    requires_dual: bool = False

    for g in guards:
        if g.guard_type == GuardRailType.AMOUNT_LIMIT:
            limit = g.config.get("max_amount_kes",
                                    DEFAULT_AUTO_RESOLUTION_AMOUNT_LIMIT_KES)
            if not isinstance(limit, Decimal):
                limit = Decimal(str(limit))
            passed = proposed_amount_kes <= limit
            results.append(GuardCheckResult(
                guard_id=g.guard_id, guard_type=g.guard_type,
                passed=passed,
                reason=(
                    f"amount {proposed_amount_kes} ≤ limit {limit}"
                    if passed
                    else f"amount {proposed_amount_kes} > limit {limit}")))
            if not passed:
                blocked_by.append(g.guard_id)

        elif g.guard_type == GuardRailType.ALLOWED_ACCOUNT_TYPES:
            allowed = g.config.get("allowed_types", ())
            passed = account_type in allowed
            results.append(GuardCheckResult(
                guard_id=g.guard_id, guard_type=g.guard_type,
                passed=passed,
                reason=(
                    f"account_type '{account_type}' allowed"
                    if passed
                    else f"account_type '{account_type}' not in {allowed}")))
            if not passed:
                blocked_by.append(g.guard_id)

        elif g.guard_type == GuardRailType.BUSINESS_HOURS_ONLY:
            results.append(GuardCheckResult(
                guard_id=g.guard_id, guard_type=g.guard_type,
                passed=is_business_hours,
                reason=(
                    "within business hours" if is_business_hours
                    else "outside business hours")))
            if not is_business_hours:
                blocked_by.append(g.guard_id)

        elif g.guard_type == GuardRailType.REQUIRES_DUAL_APPROVAL:
            threshold = g.config.get("amount_threshold_kes", Decimal("0"))
            if not isinstance(threshold, Decimal):
                threshold = Decimal(str(threshold))
            if proposed_amount_kes >= threshold:
                requires_dual = True
                results.append(GuardCheckResult(
                    guard_id=g.guard_id, guard_type=g.guard_type,
                    passed=False,    # action permitted but flagged for dual
                    reason=(
                        f"amount {proposed_amount_kes} ≥ threshold "
                        f"{threshold} requires dual approval")))
                blocked_by.append(g.guard_id)
            else:
                results.append(GuardCheckResult(
                    guard_id=g.guard_id, guard_type=g.guard_type,
                    passed=True,
                    reason="below dual-approval threshold"))

        elif g.guard_type == GuardRailType.RATE_LIMIT_PER_HOUR:
            limit = int(g.config.get("max_actions_per_hour", 100))
            passed = rate_limit_count_in_hour < limit
            results.append(GuardCheckResult(
                guard_id=g.guard_id, guard_type=g.guard_type,
                passed=passed,
                reason=(
                    f"{rate_limit_count_in_hour}/{limit} actions in hour")))
            if not passed:
                blocked_by.append(g.guard_id)

        elif g.guard_type == GuardRailType.BLOCKED_COUNTERPARTIES:
            blocked_list = g.config.get("blocked", ())
            cp_upper = counterparty.upper()
            is_blocked = any(b.upper() in cp_upper for b in blocked_list)
            results.append(GuardCheckResult(
                guard_id=g.guard_id, guard_type=g.guard_type,
                passed=not is_blocked,
                reason=(
                    f"counterparty '{counterparty}' allowed"
                    if not is_blocked
                    else f"counterparty '{counterparty}' on blocklist")))
            if is_blocked:
                blocked_by.append(g.guard_id)

        elif g.guard_type == GuardRailType.PATTERN_CONFIDENCE_FLOOR:
            floor_raw = g.config.get(
                "min_confidence", DEFAULT_PATTERN_CONFIDENCE_FLOOR)
            floor = (
                floor_raw if isinstance(floor_raw, Decimal)
                else Decimal(str(floor_raw)))
            if pattern_confidence is None:
                # No pattern → cannot pass this guard
                results.append(GuardCheckResult(
                    guard_id=g.guard_id, guard_type=g.guard_type,
                    passed=False,
                    reason="no pattern confidence available"))
                blocked_by.append(g.guard_id)
            else:
                passed = pattern_confidence >= floor
                results.append(GuardCheckResult(
                    guard_id=g.guard_id, guard_type=g.guard_type,
                    passed=passed,
                    reason=(
                        f"pattern confidence {pattern_confidence} "
                        f"vs floor {floor}")))
                if not passed:
                    blocked_by.append(g.guard_id)

    # Final permitted = all guards passed AND no dual-approval blocking
    is_permitted = (not blocked_by) and (not requires_dual)

    return GovernedExecutionDecision(
        action_proposed=action,
        guards_evaluated=tuple(results),
        is_permitted=is_permitted,
        blocked_by_guard_ids=tuple(blocked_by),
        requires_dual_approval=requires_dual,
        notes=(
            "all guards passed" if is_permitted
            else f"blocked by {len(blocked_by)} guard(s)"
            + (" + dual approval required" if requires_dual else "")))


# ════════════════════════════════════════════════════════════════════════
# Engine — workflow orchestrator
# ════════════════════════════════════════════════════════════════════════

class ReconciliationWorkflowEngine:
    """End-to-end orchestrator: exception lifecycle + memory + timing + guards."""

    def __init__(
        self, *,
        entity_name: str = "Ecobank Kenya",
        memory: Optional[MemoryLayer] = None,
        guards: Sequence[GuardRail] = (),
    ):
        self.entity_name = entity_name
        self.memory = memory or MemoryLayer()
        self.guards = tuple(guards)
        self._exceptions: Dict[str, ExceptionRecord] = {}
        self._transitions: List[Tuple[str, ExceptionState, ExceptionState, str]] = []

    # ── Exception lifecycle ────────────────────────────────────────────
    def register_exception(self, exc: ExceptionRecord) -> None:
        if exc.exception_id in self._exceptions:
            raise ValueError(
                f"exception {exc.exception_id} already registered")
        self._exceptions[exc.exception_id] = exc

    def get(self, exception_id: str) -> ExceptionRecord:
        if exception_id not in self._exceptions:
            raise KeyError(f"exception {exception_id} not found")
        return self._exceptions[exception_id]

    def transition(
        self,
        *,
        exception_id: str,
        to_state: ExceptionState,
        actor: str,
        timestamp: str,
        notes: str = "",
    ) -> ExceptionRecord:
        exc = self.get(exception_id)
        if not is_valid_exception_transition(exc.state, to_state):
            allowed = ALLOWED_EXC_TRANSITIONS.get(exc.state, ())
            raise ValueError(
                f"invalid transition {exc.state.value} → "
                f"{to_state.value}; allowed: "
                f"{[s.value for s in allowed]}")
        self._transitions.append(
            (exception_id, exc.state, to_state, actor))
        # Build new immutable record
        updated = ExceptionRecord(
            exception_id=exc.exception_id,
            exception_type=exc.exception_type,
            state=to_state,
            created_at=exc.created_at,
            amount_kes=exc.amount_kes,
            counterparty_name=exc.counterparty_name,
            source_transaction_id=exc.source_transaction_id,
            target_transaction_id=exc.target_transaction_id,
            assigned_queue=exc.assigned_queue,
            assigned_to_user_id=exc.assigned_to_user_id,
            sla_days=exc.sla_days,
            resolution_pattern_id=exc.resolution_pattern_id,
            auto_action_taken=exc.auto_action_taken,
            notes=(exc.notes + "\n" + notes if notes else exc.notes))
        self._exceptions[exception_id] = updated
        return updated

    # ── Memory layer ───────────────────────────────────────────────────
    def recall_pattern(
        self, exc: ExceptionRecord) -> Optional[ResolutionPattern]:
        return self.memory.recall(
            exception_type=exc.exception_type,
            amount_kes=exc.amount_kes,
            counterparty_name=exc.counterparty_name)

    def record_resolution(
        self,
        *,
        exception_id: str,
        resolution_action: str,
        gl_account: str = "",
        timestamp: str = "",
    ) -> ResolutionPattern:
        exc = self.get(exception_id)
        return self.memory.record_resolution(
            exception_record=exc,
            resolution_action=resolution_action,
            gl_account=gl_account,
            timestamp=timestamp)

    # ── Governed auto-resolution ───────────────────────────────────────
    def attempt_auto_resolve(
        self,
        *,
        exception_id: str,
        proposed_action: str,
        is_business_hours: bool = True,
        rate_limit_count_in_hour: int = 0,
        account_type: str = "GL_RECON",
    ) -> GovernedExecutionDecision:
        """Try to auto-resolve via pattern recall + guard evaluation.

        Flow:
          1. Recall pattern for this exception's signature
          2. If no pattern OR confidence below floor, guards will block
          3. Evaluate all guards
          4. Return decision (permitted/blocked + per-guard reasons)

        Caller decides whether to actually transition exception state
        based on returned `is_permitted`.
        """
        exc = self.get(exception_id)
        pattern = self.recall_pattern(exc)
        pattern_conf = pattern.confidence if pattern else None

        return evaluate_guards(
            action=proposed_action,
            proposed_amount_kes=exc.amount_kes,
            counterparty=exc.counterparty_name,
            pattern_confidence=pattern_conf,
            rate_limit_count_in_hour=rate_limit_count_in_hour,
            is_business_hours=is_business_hours,
            account_type=account_type,
            guards=self.guards)

    # ── Reporting ──────────────────────────────────────────────────────
    def board_summary(
        self, *, as_of: Optional[date] = None) -> Dict[str, object]:
        if as_of is None:
            as_of = date.today()
        if not self._exceptions:
            return {
                "entity": self.entity_name,
                "n_exceptions": 0,
                "by_state": {},
                "by_aging": {},
                "n_sla_breached": 0,
                "n_auto_resolved": 0,
                "n_patterns_known": 0,
            }

        by_state: Dict[str, int] = {}
        by_aging: Dict[str, int] = {}
        sla_breaches = 0
        auto_count = 0
        for exc in self._exceptions.values():
            by_state[exc.state.value] = by_state.get(exc.state.value, 0) + 1
            ag = exc.aging(as_of=as_of)
            by_aging[ag.value] = by_aging.get(ag.value, 0) + 1
            if exc.is_sla_breached(as_of=as_of) and not is_terminal_exception_state(exc.state):
                sla_breaches += 1
            if exc.auto_action_taken:
                auto_count += 1

        return {
            "entity": self.entity_name,
            "n_exceptions": len(self._exceptions),
            "by_state": by_state,
            "by_aging": by_aging,
            "n_sla_breached": sla_breaches,
            "n_auto_resolved": auto_count,
            "n_patterns_known": len(self.memory._patterns),
        }


# ════════════════════════════════════════════════════════════════════════
# Self-test
# ════════════════════════════════════════════════════════════════════════

def _make_exc(
    eid="E1", typ=ExceptionType.UNMATCHED_SOURCE, state=ExceptionState.NEW,
    created="2026-01-01T10:00:00Z", amount="50000", cp="ACME LTD",
    sla=7, auto=False,
):
    return ExceptionRecord(
        exception_id=eid, exception_type=typ, state=state,
        created_at=created, amount_kes=Decimal(amount),
        counterparty_name=cp, sla_days=sla, auto_action_taken=auto)


def _test_exception_state_terminal_states():
    terminals = [s for s in ExceptionState if is_terminal_exception_state(s)]
    expected = {
        ExceptionState.AUTO_RESOLVED,
        ExceptionState.MANUALLY_RESOLVED,
        ExceptionState.WRITTEN_OFF,
        ExceptionState.REJECTED_NEEDS_REVERSAL,
    }
    assert set(terminals) == expected


def _test_valid_transitions():
    assert is_valid_exception_transition(
        ExceptionState.NEW, ExceptionState.ASSIGNED)
    assert is_valid_exception_transition(
        ExceptionState.NEW, ExceptionState.AUTO_RESOLVED)
    assert not is_valid_exception_transition(
        ExceptionState.NEW, ExceptionState.MANUALLY_RESOLVED)


def _test_aging_buckets():
    assert compute_aging_bucket(0) == AgingBucket.FRESH_0_3
    assert compute_aging_bucket(3) == AgingBucket.FRESH_0_3
    assert compute_aging_bucket(5) == AgingBucket.AGING_4_7
    assert compute_aging_bucket(15) == AgingBucket.OVERDUE_8_30
    assert compute_aging_bucket(45) == AgingBucket.BREACH_30_PLUS


def _test_aging_negative_raises():
    try:
        compute_aging_bucket(-1)
        assert False
    except ValueError:
        pass


def _test_assignment_high_amount_to_mgmt():
    q = assign_queue(
        exception_type=ExceptionType.UNMATCHED_SOURCE,
        amount_kes=Decimal("50000000"),
        source_hint="GL")
    assert q == AssignmentQueue.MGMT_REVIEW


def _test_assignment_nostro_hint():
    q = assign_queue(
        exception_type=ExceptionType.AMOUNT_MISMATCH,
        amount_kes=Decimal("100000"),
        source_hint="NOSTRO_USD")
    assert q == AssignmentQueue.NOSTRO_DESK


def _test_assignment_mobile_money():
    q = assign_queue(
        exception_type=ExceptionType.UNMATCHED_SOURCE,
        amount_kes=Decimal("5000"),
        source_hint="M-PESA collection")
    assert q == AssignmentQueue.MOBILE_MONEY_OPS


def _test_assignment_default_tier1():
    q = assign_queue(
        exception_type=ExceptionType.UNMATCHED_SOURCE,
        amount_kes=Decimal("5000"))
    assert q == AssignmentQueue.OPS_RECON_TIER1


def _test_assignment_default_tier2():
    q = assign_queue(
        exception_type=ExceptionType.UNMATCHED_SOURCE,
        amount_kes=Decimal("500000"))
    assert q == AssignmentQueue.OPS_RECON_TIER2


def _test_exception_record_days_open():
    exc = _make_exc(created="2026-01-01T10:00:00Z")
    days = exc.days_open(as_of=date(2026, 1, 8))
    assert days == 7


def _test_exception_sla_breach():
    exc = _make_exc(created="2026-01-01T10:00:00Z", sla=5)
    assert exc.is_sla_breached(as_of=date(2026, 1, 10))
    assert not exc.is_sla_breached(as_of=date(2026, 1, 5))


def _test_signature_buckets_amount():
    sig_500 = compute_signature(
        exception_type=ExceptionType.UNMATCHED_SOURCE,
        amount_kes=Decimal("500"),
        counterparty_name="ACME LTD")
    sig_900 = compute_signature(
        exception_type=ExceptionType.UNMATCHED_SOURCE,
        amount_kes=Decimal("900"),
        counterparty_name="ACME LTD")
    # Both fall into <=1000 bucket → same signature
    assert sig_500 == sig_900


def _test_signature_different_amounts_differ():
    sig_small = compute_signature(
        exception_type=ExceptionType.UNMATCHED_SOURCE,
        amount_kes=Decimal("500"),
        counterparty_name="ACME LTD")
    sig_large = compute_signature(
        exception_type=ExceptionType.UNMATCHED_SOURCE,
        amount_kes=Decimal("5000000"),
        counterparty_name="ACME LTD")
    assert sig_small != sig_large


def _test_confidence_growth():
    assert confidence_from_occurrences(0) == Decimal("0")
    assert confidence_from_occurrences(1) == MEMORY_CONFIDENCE_LOW
    assert confidence_from_occurrences(3) == MEMORY_CONFIDENCE_MEDIUM
    assert confidence_from_occurrences(15) == MEMORY_CONFIDENCE_HIGH


def _test_memory_layer_records_and_recalls():
    mem = MemoryLayer()
    exc = _make_exc()
    mem.record_resolution(
        exception_record=exc,
        resolution_action="WRITE_OFF_TO_FX_REVAL",
        gl_account="9991",
        timestamp="2026-01-01T11:00:00Z")
    pattern = mem.recall(
        exception_type=exc.exception_type,
        amount_kes=exc.amount_kes,
        counterparty_name=exc.counterparty_name)
    assert pattern is not None
    assert pattern.typical_resolution == "WRITE_OFF_TO_FX_REVAL"
    assert pattern.occurrence_count == 1
    assert pattern.confidence == MEMORY_CONFIDENCE_LOW


def _test_memory_layer_count_grows_with_repeat():
    mem = MemoryLayer()
    for i in range(5):
        exc = _make_exc(eid=f"E{i}")
        mem.record_resolution(
            exception_record=exc, resolution_action="X")
    pattern = mem.recall(
        exception_type=ExceptionType.UNMATCHED_SOURCE,
        amount_kes=Decimal("50000"),
        counterparty_name="ACME LTD")
    assert pattern.occurrence_count == 5
    assert pattern.confidence == MEMORY_CONFIDENCE_MEDIUM


def _test_memory_layer_recall_miss_returns_none():
    mem = MemoryLayer()
    pattern = mem.recall(
        exception_type=ExceptionType.UNMATCHED_SOURCE,
        amount_kes=Decimal("50000"),
        counterparty_name="UNKNOWN")
    assert pattern is None


def _test_timing_diff_t_plus_1_auto_resolvable():
    exc = _make_exc(created="2026-01-15T00:00:00Z", amount="1000",
                      cp="ACME LTD")
    cand = detect_timing_difference(
        exception=exc,
        candidate_target_value_date="2026-01-16",  # T+1
        candidate_target_amount_kes=Decimal("1000"),
        candidate_target_counterparty="ACME LTD",
        candidate_target_id="T1")
    assert cand is not None
    assert cand.lag_days == 1
    assert cand.can_auto_resolve


def _test_timing_diff_t_plus_2_needs_review():
    exc = _make_exc(created="2026-01-15T00:00:00Z", amount="1000")
    cand = detect_timing_difference(
        exception=exc,
        candidate_target_value_date="2026-01-17",   # T+2
        candidate_target_amount_kes=Decimal("1000"),
        candidate_target_counterparty="ACME LTD",
        candidate_target_id="T1")
    assert cand is not None
    assert cand.lag_days == 2
    assert not cand.can_auto_resolve


def _test_timing_diff_amount_mismatch_returns_none():
    exc = _make_exc(amount="1000")
    cand = detect_timing_difference(
        exception=exc,
        candidate_target_value_date="2026-01-15",
        candidate_target_amount_kes=Decimal("999"),    # different
        candidate_target_counterparty="ACME LTD",
        candidate_target_id="T1")
    assert cand is None


def _test_timing_diff_beyond_max_lag_returns_none():
    exc = _make_exc(created="2026-01-01T00:00:00Z", amount="1000")
    cand = detect_timing_difference(
        exception=exc,
        candidate_target_value_date="2026-01-15",  # T+14
        candidate_target_amount_kes=Decimal("1000"),
        candidate_target_counterparty="ACME LTD",
        candidate_target_id="T1")
    assert cand is None


def _test_guards_amount_limit_blocks_large():
    guard = GuardRail(
        guard_id="G1", guard_type=GuardRailType.AMOUNT_LIMIT,
        config={"max_amount_kes": Decimal("50000")})
    decision = evaluate_guards(
        action="AUTO_RESOLVE",
        proposed_amount_kes=Decimal("100000"),    # > 50K limit
        guards=[guard])
    assert not decision.is_permitted
    assert "G1" in decision.blocked_by_guard_ids


def _test_guards_amount_limit_allows_small():
    guard = GuardRail(
        guard_id="G1", guard_type=GuardRailType.AMOUNT_LIMIT,
        config={"max_amount_kes": Decimal("50000")})
    decision = evaluate_guards(
        action="AUTO_RESOLVE",
        proposed_amount_kes=Decimal("10000"),
        guards=[guard])
    assert decision.is_permitted


def _test_guards_business_hours():
    guard = GuardRail(
        guard_id="G2", guard_type=GuardRailType.BUSINESS_HOURS_ONLY,
        config={})
    out = evaluate_guards(
        action="X", proposed_amount_kes=Decimal("100"),
        is_business_hours=False, guards=[guard])
    assert not out.is_permitted


def _test_guards_dual_approval_flag():
    """Above threshold sets requires_dual_approval=True."""
    guard = GuardRail(
        guard_id="G3", guard_type=GuardRailType.REQUIRES_DUAL_APPROVAL,
        config={"amount_threshold_kes": Decimal("100000")})
    out = evaluate_guards(
        action="X", proposed_amount_kes=Decimal("500000"),
        guards=[guard])
    assert out.requires_dual_approval
    assert not out.is_permitted    # blocked pending approval


def _test_guards_blocked_counterparty():
    guard = GuardRail(
        guard_id="G4", guard_type=GuardRailType.BLOCKED_COUNTERPARTIES,
        config={"blocked": ("OFAC_SANCTIONED",)})
    out = evaluate_guards(
        action="X", proposed_amount_kes=Decimal("100"),
        counterparty="OFAC_SANCTIONED ENTITY",
        guards=[guard])
    assert not out.is_permitted


def _test_guards_pattern_confidence_floor():
    """Pattern confidence must meet floor for guard to pass."""
    guard = GuardRail(
        guard_id="G5", guard_type=GuardRailType.PATTERN_CONFIDENCE_FLOOR,
        config={"min_confidence": Decimal("0.75")})
    # No pattern → blocked
    out = evaluate_guards(
        action="X", proposed_amount_kes=Decimal("100"),
        pattern_confidence=None, guards=[guard])
    assert not out.is_permitted
    # Below floor → blocked
    out2 = evaluate_guards(
        action="X", proposed_amount_kes=Decimal("100"),
        pattern_confidence=Decimal("0.50"), guards=[guard])
    assert not out2.is_permitted
    # Above floor → permitted
    out3 = evaluate_guards(
        action="X", proposed_amount_kes=Decimal("100"),
        pattern_confidence=Decimal("0.90"), guards=[guard])
    assert out3.is_permitted


def _test_guards_rate_limit():
    guard = GuardRail(
        guard_id="G6", guard_type=GuardRailType.RATE_LIMIT_PER_HOUR,
        config={"max_actions_per_hour": 10})
    out = evaluate_guards(
        action="X", proposed_amount_kes=Decimal("100"),
        rate_limit_count_in_hour=15, guards=[guard])
    assert not out.is_permitted


def _test_guards_no_guards_permits():
    """Empty guard list → action permitted."""
    out = evaluate_guards(
        action="X", proposed_amount_kes=Decimal("100"))
    assert out.is_permitted


def _test_engine_register_and_transition():
    eng = ReconciliationWorkflowEngine()
    exc = _make_exc()
    eng.register_exception(exc)
    eng.transition(
        exception_id="E1",
        to_state=ExceptionState.ASSIGNED,
        actor="ops_user", timestamp="t")
    assert eng.get("E1").state == ExceptionState.ASSIGNED


def _test_engine_invalid_transition_raises():
    eng = ReconciliationWorkflowEngine()
    eng.register_exception(_make_exc())
    try:
        eng.transition(
            exception_id="E1",
            to_state=ExceptionState.MANUALLY_RESOLVED,    # NEW → MANUALLY not allowed
            actor="x", timestamp="t")
        assert False
    except ValueError as e:
        assert "invalid transition" in str(e)


def _test_engine_attempt_auto_resolve_no_pattern_blocked():
    """Auto-resolve fails when no pattern + pattern-confidence guard configured."""
    guards = [
        GuardRail(
            guard_id="G1",
            guard_type=GuardRailType.PATTERN_CONFIDENCE_FLOOR,
            config={"min_confidence": Decimal("0.75")}),
    ]
    eng = ReconciliationWorkflowEngine(guards=guards)
    eng.register_exception(_make_exc())
    decision = eng.attempt_auto_resolve(
        exception_id="E1",
        proposed_action="WRITE_OFF")
    assert not decision.is_permitted


def _test_engine_attempt_auto_resolve_with_known_pattern():
    """After multiple recordings, pattern confidence high → auto permitted."""
    guards = [
        GuardRail(
            guard_id="G1",
            guard_type=GuardRailType.PATTERN_CONFIDENCE_FLOOR,
            config={"min_confidence": Decimal("0.75")}),
        GuardRail(
            guard_id="G2",
            guard_type=GuardRailType.AMOUNT_LIMIT,
            config={"max_amount_kes": Decimal("100000")}),
    ]
    eng = ReconciliationWorkflowEngine(guards=guards)
    # Build pattern history (5 occurrences)
    for i in range(5):
        exc = _make_exc(eid=f"E{i}", amount="50000", cp="ACME LTD")
        eng.register_exception(exc)
        eng.record_resolution(
            exception_id=f"E{i}",
            resolution_action="WRITE_OFF_TO_FX_REVAL",
            gl_account="9991")
    # New exception with same signature
    eng.register_exception(_make_exc(eid="NEW", amount="50000", cp="ACME LTD"))
    decision = eng.attempt_auto_resolve(
        exception_id="NEW",
        proposed_action="WRITE_OFF_TO_FX_REVAL")
    assert decision.is_permitted


def _test_engine_board_summary_empty():
    eng = ReconciliationWorkflowEngine()
    s = eng.board_summary()
    assert s["n_exceptions"] == 0


def _test_engine_board_summary_aggregates():
    eng = ReconciliationWorkflowEngine()
    eng.register_exception(_make_exc(eid="E1", auto=True))
    eng.register_exception(_make_exc(eid="E2", auto=False))
    s = eng.board_summary(as_of=date(2026, 1, 5))
    assert s["n_exceptions"] == 2
    assert s["n_auto_resolved"] == 1


def _test_decimal_purity():
    pattern = ResolutionPattern(
        pattern_id="P", signature="sig", occurrence_count=1,
        last_seen="t", typical_resolution="X")
    assert isinstance(pattern.confidence, Decimal)


def self_test() -> None:
    tests = [
        _test_exception_state_terminal_states,
        _test_valid_transitions,
        _test_aging_buckets,
        _test_aging_negative_raises,
        _test_assignment_high_amount_to_mgmt,
        _test_assignment_nostro_hint,
        _test_assignment_mobile_money,
        _test_assignment_default_tier1,
        _test_assignment_default_tier2,
        _test_exception_record_days_open,
        _test_exception_sla_breach,
        _test_signature_buckets_amount,
        _test_signature_different_amounts_differ,
        _test_confidence_growth,
        _test_memory_layer_records_and_recalls,
        _test_memory_layer_count_grows_with_repeat,
        _test_memory_layer_recall_miss_returns_none,
        _test_timing_diff_t_plus_1_auto_resolvable,
        _test_timing_diff_t_plus_2_needs_review,
        _test_timing_diff_amount_mismatch_returns_none,
        _test_timing_diff_beyond_max_lag_returns_none,
        _test_guards_amount_limit_blocks_large,
        _test_guards_amount_limit_allows_small,
        _test_guards_business_hours,
        _test_guards_dual_approval_flag,
        _test_guards_blocked_counterparty,
        _test_guards_pattern_confidence_floor,
        _test_guards_rate_limit,
        _test_guards_no_guards_permits,
        _test_engine_register_and_transition,
        _test_engine_invalid_transition_raises,
        _test_engine_attempt_auto_resolve_no_pattern_blocked,
        _test_engine_attempt_auto_resolve_with_known_pattern,
        _test_engine_board_summary_empty,
        _test_engine_board_summary_aggregates,
        _test_decimal_purity,
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
        print(f"✗ reconciliation_workflow self-test: {len(failed)} failures",
              file=sys.stderr)
        for name, msg in failed:
            print(f"  - {name}: {msg}", file=sys.stderr)
        raise SystemExit(1)
    print(f"✓ reconciliation_workflow self-test passed ({len(tests)} tests)")


if __name__ == "__main__":
    self_test()
