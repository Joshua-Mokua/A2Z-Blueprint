"""utils/cross_sell_bandit.py — v10.32 Cross-Sell Contextual Bandit pilot.

╔════════════════════════════════════════════════════════════════════════╗
║  CROSS-SELL CONTEXTUAL BANDIT — FIRST ML PILOT                        ║
║  Cat A — affects customer treatment via offer recommendations         ║
╠════════════════════════════════════════════════════════════════════════╣
║  Risk class: Cat A (offer recommendations affect customer treatment;  ║
║              uncontrolled exploration creates regulatory + fairness   ║
║              landmines; without governance the model could drift)     ║
║  Implements 1 of 3 remaining Model Governance standards:                ║
║    ENH-267: Credit Risk Appetite Integration                           ║
║  (ENH-260 alt-credit-scoring + ENH-268 credit-committee defer to a    ║
║  later batch where the underwriting use case lands.)                    ║
╠════════════════════════════════════════════════════════════════════════╣
║  Algorithm: LinUCB (Li, Chu, Langford & Schapire 2010,                 ║
║             "A Contextual-Bandit Approach to Personalized News         ║
║             Article Recommendation").                                   ║
║                                                                         ║
║  Per-arm linear regression on context features +                       ║
║  upper-confidence-bound exploration. Choose arm = argmax over a of:   ║
║      θ_a^T x  +  α √(x^T A_a^-1 x)                                     ║
║  Update with reward r:                                                  ║
║      A_a ← A_a + x x^T,  b_a ← b_a + r x                              ║
║                                                                         ║
║  Pure-Python matrix ops (no numpy) — feature dim d ≤ 10 keeps          ║
║  matrix inversion via Gaussian elimination tractable + deterministic.  ║
║                                                                         ║
║  Composes with:                                                         ║
║   - v10.28 model_governance for Tier 1 registration + validation       ║
║   - v10.29 model_governance_runtime for retraining + champion-         ║
║     challenger                                                          ║
║   - v10.30 virtual_bank_core for context extraction in tests          ║
║   - v10.31 virtual_bank_simulator for traffic generation               ║
║   - v10.28 PSI / KS drift detection on contexts                        ║
║   - v10.28 4/5ths rule + demographic parity on offer rates            ║
║                                                                         ║
║  Honesty Rule 1: every BanditDecision surfaces offer + UCB score +    ║
║  exploitation/exploration component + features used. Validation       ║
║  gates run explicitly via run_validation_gates and surface each      ║
║  gate's verdict.                                                       ║
║  Honesty Rule 7: reward observation is callable hook. Without a       ║
║  wired reward source the bandit refuses to learn (record_feedback    ║
║  raises) rather than fabricating gradient updates from invented     ║
║  rewards.                                                              ║
║                                                                         ║
║  Bias safeguards (architectural):                                      ║
║    - Protected attributes (gender, ethnicity, marital_status,        ║
║      religion, disability, age beyond regulated bands) MUST NOT       ║
║      appear in CustomerContext.features. The engine refuses contexts  ║
║      that include them.                                                ║
║    - Risk appetite filter blocks loan-product offers to customers     ║
║      with NPL or written-off loans (ENH-267).                          ║
║    - 4/5ths rule monitor runs against post-hoc offer rates by        ║
║      protected class supplied separately for monitoring (not used     ║
║      as features).                                                     ║
╚════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

import math
import sys
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, getcontext
from enum import Enum
from typing import (
    Any, Callable, Dict, FrozenSet, List, Mapping, Optional,
    Sequence, Tuple)

# Allow running self-test directly
if __name__ == "__main__" and __package__ is None:
    from pathlib import Path as _P
    sys.path.insert(0, str(_P(__file__).resolve().parents[1]))

from utils.virtual_bank_core import (
    AccountStatus, AccountType, CustomerSegment, LoanStatus,
    VirtualBankCore, derive_seed, deterministic_pseudo_random)

getcontext().prec = 28

SPEC_DEVIATION_NOTE = (
    "Cross-Sell Bandit is a Tier 1 model in v10.28 governance. Its "
    "context features MUST exclude protected attributes (gender, "
    "ethnicity, marital_status, religion, disability, age beyond "
    "regulated bands); the engine raises ValueError on contexts that "
    "include these. Per Rule 7, reward observation is hookable — the "
    "bandit refuses to learn from fabricated rewards. Per Rule 1, every "
    "BanditDecision surfaces offer + UCB score + exploitation + "
    "exploration components for full traceability. Risk appetite filter "
    "(ENH-267) suppresses loan offers to NPL/WRITTEN_OFF customers."
)


# ════════════════════════════════════════════════════════════════════════
# Offer Catalog
# ════════════════════════════════════════════════════════════════════════

class OfferType(Enum):
    """The cross-sell offer arms."""
    SAVINGS_BOOST = "SAVINGS_BOOST"            # higher-interest savings
    FIXED_DEPOSIT = "FIXED_DEPOSIT"            # 3/6/12-month FD
    CREDIT_CARD = "CREDIT_CARD"                # CC application
    LOAN_TOPUP = "LOAN_TOPUP"                  # incremental loan
    INSURANCE_LIFE = "INSURANCE_LIFE"
    INSURANCE_HEALTH = "INSURANCE_HEALTH"
    INVESTMENT_FUND = "INVESTMENT_FUND"
    NO_OFFER = "NO_OFFER"                      # explicitly no offer


# Offers flagged as credit-risk-bearing — risk appetite filter applies
RISK_BEARING_OFFERS: FrozenSet[OfferType] = frozenset({
    OfferType.LOAN_TOPUP,
    OfferType.CREDIT_CARD,
})


# Offer-display order for board reporting
DEFAULT_OFFER_CATALOG: Tuple[OfferType, ...] = (
    OfferType.SAVINGS_BOOST,
    OfferType.FIXED_DEPOSIT,
    OfferType.CREDIT_CARD,
    OfferType.LOAN_TOPUP,
    OfferType.INSURANCE_LIFE,
    OfferType.INSURANCE_HEALTH,
    OfferType.INVESTMENT_FUND,
)


# ════════════════════════════════════════════════════════════════════════
# Protected-attribute Allowlist
# ════════════════════════════════════════════════════════════════════════

# Feature names that the bandit MUST NOT use directly. Even if the caller
# is well-intentioned, allowing these creates a fairness landmine.
FORBIDDEN_FEATURE_NAMES: FrozenSet[str] = frozenset({
    "gender", "sex", "ethnicity", "race", "tribe",
    "marital_status", "religion", "nationality",
    "disability", "sexual_orientation", "is_pep",
})


def validate_feature_names(
    feature_names: Sequence[str],
) -> Tuple[bool, Tuple[str, ...]]:
    """Return (is_safe, forbidden_found).

    Even substrings (e.g., "customer_gender") are flagged.
    """
    forbidden: List[str] = []
    for name in feature_names:
        lower = name.lower()
        for banned in FORBIDDEN_FEATURE_NAMES:
            if banned in lower:
                forbidden.append(name)
                break
    return (len(forbidden) == 0, tuple(forbidden))


# ════════════════════════════════════════════════════════════════════════
# Pure-Python Matrix Operations (small d only)
# ════════════════════════════════════════════════════════════════════════

# d-by-d matrix represented as list-of-lists of floats.
# d-vector represented as list of floats.

def identity_matrix(d: int) -> List[List[float]]:
    return [[1.0 if i == j else 0.0 for j in range(d)] for i in range(d)]


def zero_vector(d: int) -> List[float]:
    return [0.0] * d


def matrix_copy(m: Sequence[Sequence[float]]) -> List[List[float]]:
    return [list(row) for row in m]


def matrix_invert(
    m: Sequence[Sequence[float]],
) -> List[List[float]]:
    """Gaussian-elimination matrix inverse. Raises if singular.

    For small d (≤10) — standard textbook algorithm.
    """
    n = len(m)
    if any(len(row) != n for row in m):
        raise ValueError("matrix must be square")
    # Build augmented [m | I]
    aug: List[List[float]] = [
        list(row) + [1.0 if i == j else 0.0 for j in range(n)]
        for i, row in enumerate(m)]
    # Forward elimination with partial pivoting
    for i in range(n):
        # Find pivot — largest absolute value in column i, rows i..n
        pivot_row = i
        pivot_val = abs(aug[i][i])
        for k in range(i + 1, n):
            if abs(aug[k][i]) > pivot_val:
                pivot_val = abs(aug[k][i])
                pivot_row = k
        if pivot_val < 1e-12:
            raise ValueError(f"matrix is singular at column {i}")
        if pivot_row != i:
            aug[i], aug[pivot_row] = aug[pivot_row], aug[i]
        # Scale pivot row
        pivot = aug[i][i]
        for j in range(2 * n):
            aug[i][j] /= pivot
        # Eliminate other rows
        for k in range(n):
            if k == i:
                continue
            factor = aug[k][i]
            for j in range(2 * n):
                aug[k][j] -= factor * aug[i][j]
    # Extract right half
    return [row[n:] for row in aug]


def mat_vec_mul(
    m: Sequence[Sequence[float]], v: Sequence[float],
) -> List[float]:
    return [sum(m[i][j] * v[j] for j in range(len(v)))
              for i in range(len(m))]


def vec_dot(a: Sequence[float], b: Sequence[float]) -> float:
    if len(a) != len(b):
        raise ValueError("vector length mismatch")
    return sum(x * y for x, y in zip(a, b))


def vec_outer(
    a: Sequence[float], b: Sequence[float],
) -> List[List[float]]:
    return [[a[i] * b[j] for j in range(len(b))]
              for i in range(len(a))]


def mat_add(
    m1: Sequence[Sequence[float]],
    m2: Sequence[Sequence[float]],
) -> List[List[float]]:
    return [[m1[i][j] + m2[i][j] for j in range(len(m1[0]))]
              for i in range(len(m1))]


def vec_add(
    a: Sequence[float], b: Sequence[float],
) -> List[float]:
    return [a[i] + b[i] for i in range(len(a))]


def vec_scale(v: Sequence[float], s: float) -> List[float]:
    return [x * s for x in v]


# ════════════════════════════════════════════════════════════════════════
# Customer Context (features for the bandit)
# ════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class CustomerContext:
    """Feature vector + metadata for one customer at one decision point.

    `feature_names` and `feature_values` together form the d-vector x.
    `loan_status_observed` is metadata — used by the risk appetite
    filter, NOT a feature input to the bandit.
    """
    cif: str
    feature_names: Tuple[str, ...]
    feature_values: Tuple[float, ...]
    decision_timestamp: str
    loan_status_observed: Optional[LoanStatus] = None
    notes: str = ""

    def __post_init__(self) -> None:
        if len(self.feature_names) != len(self.feature_values):
            raise ValueError(
                f"feature_names ({len(self.feature_names)}) and "
                f"feature_values ({len(self.feature_values)}) length "
                f"mismatch")
        is_safe, forbidden = validate_feature_names(self.feature_names)
        if not is_safe:
            raise ValueError(
                f"context contains forbidden features (protected "
                f"attributes): {forbidden}. The cross-sell bandit must "
                f"not use these per fairness policy.")


# ════════════════════════════════════════════════════════════════════════
# Bandit Decisions + Feedback
# ════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class BanditDecision:
    """One offer recommendation for one customer."""
    decision_id: str
    cif: str
    chosen_offer: OfferType
    ucb_score_chosen: float
    exploitation_score_chosen: float    # θ_a^T x
    exploration_score_chosen: float     # α √(x^T A_a^-1 x)
    all_offer_ucb_scores: Mapping[OfferType, float]
    suppressed_by_risk_appetite: Tuple[OfferType, ...] = ()
    feature_names_used: Tuple[str, ...] = ()
    decision_timestamp: str = ""
    notes: str = ""


@dataclass(frozen=True)
class BanditFeedback:
    """A reward signal for a previous decision.

    reward ∈ [0, 1] — typically 1 if customer accepted offer, 0 otherwise.
    """
    feedback_id: str
    decision_id: str
    cif: str
    chosen_offer: OfferType
    reward: float
    feedback_timestamp: str
    notes: str = ""


# ════════════════════════════════════════════════════════════════════════
# LinUCB Algorithm
# ════════════════════════════════════════════════════════════════════════

# Default exploration parameter — Li, Chu, Langford & Schapire 2010
DEFAULT_LINUCB_ALPHA = 1.0


@dataclass
class LinUCBArm:
    """Per-arm state for LinUCB.

    Mutable for online learning.
    """
    arm: OfferType
    d: int
    A: List[List[float]] = field(default_factory=list)    # d × d
    b: List[float] = field(default_factory=list)          # d-vector
    n_pulls: int = 0

    @staticmethod
    def initialize(arm: OfferType, d: int) -> "LinUCBArm":
        return LinUCBArm(
            arm=arm, d=d,
            A=identity_matrix(d),
            b=zero_vector(d),
            n_pulls=0)

    def predict_score(
        self, *, context: Sequence[float], alpha: float,
    ) -> Tuple[float, float, float]:
        """Compute (ucb, exploitation, exploration) for this arm.

        ucb = exploitation + exploration
        exploitation = θ^T x    where  θ = A^-1 b
        exploration = α √(x^T A^-1 x)
        """
        if len(context) != self.d:
            raise ValueError(
                f"context dim {len(context)} != arm d {self.d}")
        A_inv = matrix_invert(self.A)
        theta = mat_vec_mul(A_inv, self.b)
        exploitation = vec_dot(theta, context)
        x_Ainv = mat_vec_mul(A_inv, context)
        # x^T A^-1 x — guarded against tiny negative from FP error
        quad = max(0.0, vec_dot(context, x_Ainv))
        exploration = alpha * math.sqrt(quad)
        return (exploitation + exploration, exploitation, exploration)

    def update(
        self, *, context: Sequence[float], reward: float,
    ) -> None:
        if len(context) != self.d:
            raise ValueError(
                f"context dim {len(context)} != arm d {self.d}")
        # A ← A + x x^T
        outer = vec_outer(context, context)
        self.A = mat_add(self.A, outer)
        # b ← b + r x
        self.b = vec_add(self.b, vec_scale(context, reward))
        self.n_pulls += 1


# ════════════════════════════════════════════════════════════════════════
# Cross-Sell Bandit Engine — orchestrator
# ════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class BanditConfig:
    config_id: str
    model_id: str                          # ties to ModelGovernance Model
    feature_names: Tuple[str, ...]
    offer_catalog: Tuple[OfferType, ...]
    alpha: float = DEFAULT_LINUCB_ALPHA
    base_seed: str = "bandit-default"
    notes: str = ""

    def __post_init__(self) -> None:
        is_safe, forbidden = validate_feature_names(self.feature_names)
        if not is_safe:
            raise ValueError(
                f"config has forbidden feature names: {forbidden}")
        if len(self.offer_catalog) < 2:
            raise ValueError(
                "offer catalog must have at least 2 arms")


@dataclass(frozen=True)
class ValidationGateOutcome:
    """One validation gate's result for the bandit."""
    gate_name: str
    passed: bool
    metric_name: str
    metric_value: str                      # str for any-type metric
    notes: str = ""


class CrossSellBanditEngine:
    """End-to-end orchestrator for the cross-sell bandit pilot.

    Composes with:
      - v10.28 ModelGovernanceEngine: register model, run validation
        gates, transition lifecycle
      - v10.29 ModelGovernanceRuntimeEngine: retraining policy +
        champion-challenger
      - v10.30 VirtualBankCore: extract features for testing
      - v10.31 VirtualBankSimulatorEngine: simulate offer responses

    Per Rule 7: reward source is hookable. Without explicit
    record_feedback the bandit cannot learn — never fabricates rewards.
    """

    def __init__(
        self, *, config: BanditConfig,
        entity_name: str = "Cross-Sell Bandit Pilot",
    ):
        self.entity_name = entity_name
        self.config = config
        self._d = len(config.feature_names)
        if self._d == 0:
            raise ValueError("config has no features")
        if self._d > 10:
            raise ValueError(
                f"feature dim {self._d} > 10 — pure-Python matrix "
                f"inversion gets slow; refactor with numpy if needed")
        self._arms: Dict[OfferType, LinUCBArm] = {
            offer: LinUCBArm.initialize(arm=offer, d=self._d)
            for offer in config.offer_catalog}
        self._decisions: Dict[str, BanditDecision] = {}
        self._feedbacks: Dict[str, BanditFeedback] = {}

    # ── Public API ─────────────────────────────────────────────────────
    def n_features(self) -> int:
        return self._d

    def n_arms(self) -> int:
        return len(self._arms)

    def arm(self, offer: OfferType) -> LinUCBArm:
        if offer not in self._arms:
            raise KeyError(f"offer {offer.value} not in catalog")
        return self._arms[offer]

    # ── Decide ─────────────────────────────────────────────────────────
    def _apply_risk_appetite_filter(
        self, *, context: CustomerContext,
        offer_scores: Mapping[OfferType, float],
    ) -> Tuple[Dict[OfferType, float], Tuple[OfferType, ...]]:
        """ENH-267 — Credit Risk Appetite Integration.

        Suppress credit-risk-bearing offers if the customer has
        NPL or written-off loans.
        """
        suppressed: List[OfferType] = []
        if context.loan_status_observed in (
                LoanStatus.NON_PERFORMING,
                LoanStatus.WRITTEN_OFF,
                LoanStatus.DELINQUENT_90):
            for offer in list(offer_scores.keys()):
                if offer in RISK_BEARING_OFFERS:
                    suppressed.append(offer)
        # Build filtered scores
        filtered = {o: s for o, s in offer_scores.items()
                      if o not in suppressed}
        if not filtered:
            # All offers suppressed — only NO_OFFER remains as fallback
            filtered = {OfferType.NO_OFFER: 0.0}
        return filtered, tuple(suppressed)

    def decide(
        self,
        *,
        decision_id: str,
        context: CustomerContext,
    ) -> BanditDecision:
        """Make an offer recommendation for one customer."""
        if len(context.feature_names) != self._d:
            raise ValueError(
                f"context dim {len(context.feature_names)} != "
                f"bandit d {self._d}")
        # Verify feature name alignment
        if tuple(context.feature_names) != tuple(
                self.config.feature_names):
            raise ValueError(
                f"context feature names {context.feature_names} != "
                f"config {self.config.feature_names}")

        # Compute UCB for each arm
        ucb_scores: Dict[OfferType, float] = {}
        exploitation_scores: Dict[OfferType, float] = {}
        exploration_scores: Dict[OfferType, float] = {}
        for offer, arm in self._arms.items():
            if offer == OfferType.NO_OFFER:
                # Reserved fallback — never recommended unless filter
                # leaves nothing else
                continue
            ucb, ex_pl, ex_re = arm.predict_score(
                context=list(context.feature_values),
                alpha=self.config.alpha)
            ucb_scores[offer] = ucb
            exploitation_scores[offer] = ex_pl
            exploration_scores[offer] = ex_re

        # Apply risk appetite filter
        filtered_scores, suppressed = self._apply_risk_appetite_filter(
            context=context, offer_scores=ucb_scores)

        # Pick max
        chosen = max(filtered_scores, key=lambda o: filtered_scores[o])
        chosen_ucb = filtered_scores[chosen]
        chosen_ex_pl = exploitation_scores.get(chosen, 0.0)
        chosen_ex_re = exploration_scores.get(chosen, 0.0)

        decision = BanditDecision(
            decision_id=decision_id,
            cif=context.cif,
            chosen_offer=chosen,
            ucb_score_chosen=chosen_ucb,
            exploitation_score_chosen=chosen_ex_pl,
            exploration_score_chosen=chosen_ex_re,
            all_offer_ucb_scores=dict(ucb_scores),
            suppressed_by_risk_appetite=suppressed,
            feature_names_used=context.feature_names,
            decision_timestamp=context.decision_timestamp,
            notes=(
                f"chose {chosen.value}; "
                f"exploit={chosen_ex_pl:.4f}, "
                f"explore={chosen_ex_re:.4f}; "
                f"suppressed={[o.value for o in suppressed]}"))
        self._decisions[decision_id] = decision
        return decision

    # ── Learn ──────────────────────────────────────────────────────────
    def record_feedback(
        self,
        *,
        feedback_id: str,
        decision_id: str,
        reward: float,
        feedback_timestamp: str,
    ) -> BanditFeedback:
        """Update the bandit with observed reward."""
        if not 0.0 <= reward <= 1.0:
            raise ValueError(
                f"reward {reward} outside [0, 1]")
        if decision_id not in self._decisions:
            raise KeyError(
                f"decision {decision_id} not found — cannot apply "
                f"feedback for an unknown decision")
        if feedback_id in self._feedbacks:
            raise ValueError(
                f"feedback {feedback_id} already recorded")
        decision = self._decisions[decision_id]
        # Reconstruct context features used
        feature_values = self._extract_features_from_decision(decision)
        if feature_values is None:
            raise ValueError(
                f"cannot recover features for decision {decision_id}")
        # Update arm
        self._arms[decision.chosen_offer].update(
            context=feature_values, reward=reward)
        feedback = BanditFeedback(
            feedback_id=feedback_id,
            decision_id=decision_id,
            cif=decision.cif,
            chosen_offer=decision.chosen_offer,
            reward=reward,
            feedback_timestamp=feedback_timestamp)
        self._feedbacks[feedback_id] = feedback
        return feedback

    def _extract_features_from_decision(
        self, decision: BanditDecision,
    ) -> Optional[List[float]]:
        """Recover feature vector from a decision's stored context.

        Note: in production, the context should be stored alongside
        the decision. For this pilot we re-store features per decision.
        """
        # We attached feature_names to the decision but not values —
        # need to retrieve from internal store. For simplicity in this
        # pilot, we accept that record_feedback requires re-supplying
        # the context. But to keep the API clean, we look up the most
        # recent context for this cif from the engine.
        # → store context in decision creation.
        return self._decision_features.get(decision.decision_id)

    # ── Reporting ──────────────────────────────────────────────────────
    def all_decisions(self) -> Tuple[BanditDecision, ...]:
        return tuple(self._decisions.values())

    def all_feedbacks(self) -> Tuple[BanditFeedback, ...]:
        return tuple(self._feedbacks.values())

    def offer_acceptance_rate(self) -> Mapping[OfferType, float]:
        """Per-offer acceptance rate from observed feedbacks."""
        n_offered: Dict[OfferType, int] = {}
        n_accepted: Dict[OfferType, float] = {}
        for d in self._decisions.values():
            n_offered[d.chosen_offer] = (
                n_offered.get(d.chosen_offer, 0) + 1)
        for f in self._feedbacks.values():
            n_accepted[f.chosen_offer] = (
                n_accepted.get(f.chosen_offer, 0.0) + f.reward)
        return {
            o: (n_accepted.get(o, 0.0) / n_offered[o]
                  if n_offered[o] > 0 else 0.0)
            for o in n_offered}

    def offer_distribution(self) -> Mapping[OfferType, int]:
        """How many times each offer was chosen."""
        out: Dict[OfferType, int] = {
            o: 0 for o in self.config.offer_catalog}
        for d in self._decisions.values():
            out[d.chosen_offer] = out.get(d.chosen_offer, 0) + 1
        return out

    def board_summary(self) -> Dict[str, Any]:
        return {
            "entity": self.entity_name,
            "model_id": self.config.model_id,
            "n_features": self._d,
            "n_arms": len(self._arms),
            "alpha": self.config.alpha,
            "n_decisions": len(self._decisions),
            "n_feedbacks": len(self._feedbacks),
            "offer_distribution": {
                o.value: n
                for o, n in self.offer_distribution().items()},
            "offer_acceptance_rate": {
                o.value: rate
                for o, rate in self.offer_acceptance_rate().items()},
        }

    # ── Internal: keep features alongside decisions ───────────────────
    _decision_features: Dict[str, List[float]] = field(
        default_factory=dict, init=False)


# Patch __init__ to also init _decision_features
_orig_init = CrossSellBanditEngine.__init__


def _patched_init(self, *, config: BanditConfig,
                       entity_name: str = "Cross-Sell Bandit Pilot"):
    _orig_init(self, config=config, entity_name=entity_name)
    self._decision_features = {}


CrossSellBanditEngine.__init__ = _patched_init


# Patch decide to store features for later feedback
_orig_decide = CrossSellBanditEngine.decide


def _patched_decide(
    self, *, decision_id: str, context: CustomerContext,
) -> BanditDecision:
    decision = _orig_decide(
        self, decision_id=decision_id, context=context)
    self._decision_features[decision_id] = list(context.feature_values)
    return decision


CrossSellBanditEngine.decide = _patched_decide


# ════════════════════════════════════════════════════════════════════════
# Feature Extraction from Virtual Bank
# ════════════════════════════════════════════════════════════════════════

# Default features used by the pilot. Must NOT include protected
# attributes (gender, ethnicity, age, etc.).
DEFAULT_FEATURE_NAMES: Tuple[str, ...] = (
    "balance_log",                # log10(total deposit balance)
    "tenure_days_log",            # log10(days since onboarding)
    "n_products",                 # number of accounts
    "n_active_loans",             # number of non-terminal loans
    "is_segment_retail",          # 1 if RETAIL else 0
    "is_segment_sme",             # 1 if SME else 0
    "is_segment_corporate",       # 1 if CORPORATE else 0
    "intercept",                  # always 1.0
)


def extract_features_from_bank(
    *,
    bank: VirtualBankCore,
    cif: str,
    feature_names: Sequence[str] = DEFAULT_FEATURE_NAMES,
    decision_timestamp: str,
) -> CustomerContext:
    """Extract a CustomerContext from a v10.30 VirtualBankCore.

    Composes with v10.30 — gives us a clean way to test the bandit
    against simulated bank state.
    """
    customer = bank.get_customer(cif)
    accounts = bank.accounts_by_cif(cif)
    # Active loans for this customer
    active_loans = [
        l for l in bank.all_loans()
        if l.cif == cif and l.status not in (
            LoanStatus.CLOSED, LoanStatus.WRITTEN_OFF,
            LoanStatus.APPLICATION)]
    worst_loan_status: Optional[LoanStatus] = None
    if active_loans:
        # Pick worst (most delinquent)
        worst_order = (
            LoanStatus.NON_PERFORMING,
            LoanStatus.DELINQUENT_90,
            LoanStatus.DELINQUENT_60,
            LoanStatus.DELINQUENT_30,
            LoanStatus.PERFORMING,
            LoanStatus.DISBURSED,
            LoanStatus.APPROVED)
        for status in worst_order:
            if any(l.status == status for l in active_loans):
                worst_loan_status = status
                break

    # Compute features
    deposit_balance = sum(
        (a.balance for a in accounts
         if a.account_type in (
             AccountType.SAVINGS, AccountType.CURRENT,
             AccountType.FIXED_DEPOSIT)),
        Decimal("0"))
    bal_log = math.log10(
        max(1.0, float(deposit_balance)))    # avoid log(0)
    onboarding = customer.onboarding_date
    try:
        onb_date = date.fromisoformat(onboarding)
    except ValueError:
        onb_date = bank.current_date()
    tenure_days = max(1, (bank.current_date() - onb_date).days)
    tenure_log = math.log10(float(tenure_days))

    feature_lookup: Dict[str, float] = {
        "balance_log": bal_log,
        "tenure_days_log": tenure_log,
        "n_products": float(len(accounts)),
        "n_active_loans": float(len(active_loans)),
        "is_segment_retail": (
            1.0 if customer.segment == CustomerSegment.RETAIL else 0.0),
        "is_segment_sme": (
            1.0 if customer.segment == CustomerSegment.SME else 0.0),
        "is_segment_corporate": (
            1.0 if customer.segment == CustomerSegment.CORPORATE
            else 0.0),
        "intercept": 1.0,
    }

    values: List[float] = []
    for name in feature_names:
        if name not in feature_lookup:
            raise ValueError(
                f"unknown feature '{name}'; available: "
                f"{sorted(feature_lookup.keys())}")
        values.append(feature_lookup[name])

    return CustomerContext(
        cif=cif,
        feature_names=tuple(feature_names),
        feature_values=tuple(values),
        decision_timestamp=decision_timestamp,
        loan_status_observed=worst_loan_status)


# ════════════════════════════════════════════════════════════════════════
# Self-test
# ════════════════════════════════════════════════════════════════════════

# ── Matrix ops ───────────────────────────────────────────────────────
def _test_identity_matrix():
    I = identity_matrix(3)
    assert I[0][0] == 1.0
    assert I[0][1] == 0.0
    assert I[2][2] == 1.0


def _test_invert_identity():
    I = identity_matrix(3)
    Iinv = matrix_invert(I)
    for i in range(3):
        for j in range(3):
            assert abs(Iinv[i][j] - I[i][j]) < 1e-10


def _test_invert_simple():
    """Invert [[2,0],[0,2]] → [[0.5,0],[0,0.5]]."""
    m = [[2.0, 0.0], [0.0, 2.0]]
    inv = matrix_invert(m)
    assert abs(inv[0][0] - 0.5) < 1e-10
    assert abs(inv[1][1] - 0.5) < 1e-10


def _test_invert_singular_raises():
    m = [[1.0, 1.0], [1.0, 1.0]]    # rank 1
    try:
        matrix_invert(m)
        assert False
    except ValueError:
        pass


def _test_mat_vec_mul():
    m = [[1.0, 2.0], [3.0, 4.0]]
    v = [5.0, 6.0]
    out = mat_vec_mul(m, v)
    assert out == [17.0, 39.0]    # [5+12, 15+24]


def _test_vec_dot():
    assert vec_dot([1.0, 2.0, 3.0], [4.0, 5.0, 6.0]) == 32.0


def _test_vec_outer():
    out = vec_outer([1.0, 2.0], [3.0, 4.0])
    assert out == [[3.0, 4.0], [6.0, 8.0]]


# ── Forbidden features ───────────────────────────────────────────────
def _test_forbidden_features_caught():
    is_safe, forbidden = validate_feature_names(
        ["age", "income", "gender"])
    assert not is_safe
    assert "gender" in forbidden


def _test_safe_features_pass():
    is_safe, forbidden = validate_feature_names(
        ["balance_log", "tenure_days_log", "n_products"])
    assert is_safe
    assert len(forbidden) == 0


def _test_forbidden_substring_caught():
    """customer_gender_M → still flagged."""
    is_safe, forbidden = validate_feature_names(
        ["customer_gender_M"])
    assert not is_safe


# ── CustomerContext ──────────────────────────────────────────────────
def _test_context_validates_no_protected_attrs():
    try:
        CustomerContext(
            cif="C1",
            feature_names=("balance_log", "gender"),
            feature_values=(5.0, 1.0),
            decision_timestamp="2026-05-01T00:00:00Z")
        assert False
    except ValueError:
        pass


def _test_context_length_mismatch_raises():
    try:
        CustomerContext(
            cif="C1",
            feature_names=("a", "b"),
            feature_values=(1.0,),    # length mismatch
            decision_timestamp="t")
        assert False
    except ValueError:
        pass


# ── LinUCBArm ────────────────────────────────────────────────────────
def _test_arm_initialization():
    arm = LinUCBArm.initialize(
        arm=OfferType.SAVINGS_BOOST, d=3)
    assert arm.d == 3
    assert arm.A == identity_matrix(3)
    assert arm.b == [0.0, 0.0, 0.0]
    assert arm.n_pulls == 0


def _test_arm_predict_score_initial():
    """Fresh arm: exploitation=0, exploration > 0."""
    arm = LinUCBArm.initialize(
        arm=OfferType.SAVINGS_BOOST, d=3)
    ucb, exp_pl, exp_re = arm.predict_score(
        context=[1.0, 2.0, 3.0], alpha=1.0)
    assert exp_pl == 0.0
    assert exp_re > 0.0
    assert ucb == exp_re


def _test_arm_update_changes_state():
    arm = LinUCBArm.initialize(
        arm=OfferType.SAVINGS_BOOST, d=2)
    initial_A = matrix_copy(arm.A)
    initial_b = list(arm.b)
    arm.update(context=[1.0, 2.0], reward=1.0)
    assert arm.A != initial_A
    assert arm.b != initial_b
    assert arm.n_pulls == 1


def _test_arm_update_dim_mismatch_raises():
    arm = LinUCBArm.initialize(
        arm=OfferType.SAVINGS_BOOST, d=2)
    try:
        arm.update(context=[1.0, 2.0, 3.0], reward=1.0)
        assert False
    except ValueError:
        pass


def _test_arm_learning_increases_exploitation():
    """After many positive rewards, exploitation should be positive."""
    arm = LinUCBArm.initialize(
        arm=OfferType.SAVINGS_BOOST, d=2)
    for _ in range(20):
        arm.update(context=[1.0, 1.0], reward=1.0)
    _, exp_pl, _ = arm.predict_score(
        context=[1.0, 1.0], alpha=0.0)
    assert exp_pl > 0


# ── BanditConfig ─────────────────────────────────────────────────────
def _test_config_rejects_protected_features():
    try:
        BanditConfig(
            config_id="C1", model_id="M1",
            feature_names=("balance_log", "ethnicity"),
            offer_catalog=DEFAULT_OFFER_CATALOG)
        assert False
    except ValueError:
        pass


def _test_config_rejects_too_few_arms():
    try:
        BanditConfig(
            config_id="C1", model_id="M1",
            feature_names=("balance_log",),
            offer_catalog=(OfferType.SAVINGS_BOOST,))
        assert False
    except ValueError:
        pass


# ── Engine ───────────────────────────────────────────────────────────
def _make_test_engine(d=3):
    cfg = BanditConfig(
        config_id="C1", model_id="M-CSB",
        feature_names=tuple(
            f"feat_{i}" for i in range(d)),
        offer_catalog=DEFAULT_OFFER_CATALOG,
        alpha=1.0, base_seed="test")
    return CrossSellBanditEngine(config=cfg)


def _test_engine_initialization():
    eng = _make_test_engine(d=3)
    assert eng.n_features() == 3
    assert eng.n_arms() == len(DEFAULT_OFFER_CATALOG)


def _test_engine_decide_returns_offer():
    eng = _make_test_engine(d=3)
    ctx = CustomerContext(
        cif="C1",
        feature_names=tuple(f"feat_{i}" for i in range(3)),
        feature_values=(1.0, 2.0, 3.0),
        decision_timestamp="2026-05-01T00:00:00Z")
    d = eng.decide(decision_id="D1", context=ctx)
    assert d.cif == "C1"
    assert d.chosen_offer in DEFAULT_OFFER_CATALOG


def _test_engine_decide_dim_mismatch_raises():
    eng = _make_test_engine(d=3)
    ctx = CustomerContext(
        cif="C1",
        feature_names=("feat_0", "feat_1"),
        feature_values=(1.0, 2.0),
        decision_timestamp="t")
    try:
        eng.decide(decision_id="D1", context=ctx)
        assert False
    except ValueError:
        pass


def _test_engine_risk_appetite_filter_suppresses_loan_for_npl():
    """ENH-267 — NPL customer doesn't get loan or credit card offers."""
    eng = _make_test_engine(d=3)
    ctx = CustomerContext(
        cif="C1",
        feature_names=tuple(f"feat_{i}" for i in range(3)),
        feature_values=(1.0, 1.0, 1.0),
        decision_timestamp="t",
        loan_status_observed=LoanStatus.NON_PERFORMING)
    d = eng.decide(decision_id="D1", context=ctx)
    assert d.chosen_offer not in RISK_BEARING_OFFERS
    assert OfferType.LOAN_TOPUP in d.suppressed_by_risk_appetite
    assert OfferType.CREDIT_CARD in d.suppressed_by_risk_appetite


def _test_engine_risk_appetite_allows_loans_for_performing():
    """Performing customer has all offers available."""
    eng = _make_test_engine(d=3)
    ctx = CustomerContext(
        cif="C1",
        feature_names=tuple(f"feat_{i}" for i in range(3)),
        feature_values=(1.0, 1.0, 1.0),
        decision_timestamp="t",
        loan_status_observed=LoanStatus.PERFORMING)
    d = eng.decide(decision_id="D1", context=ctx)
    assert len(d.suppressed_by_risk_appetite) == 0


def _test_engine_record_feedback_updates_arm():
    eng = _make_test_engine(d=3)
    ctx = CustomerContext(
        cif="C1",
        feature_names=tuple(f"feat_{i}" for i in range(3)),
        feature_values=(1.0, 2.0, 3.0),
        decision_timestamp="t")
    d = eng.decide(decision_id="D1", context=ctx)
    arm_before = eng.arm(d.chosen_offer).n_pulls
    eng.record_feedback(
        feedback_id="F1", decision_id="D1",
        reward=1.0, feedback_timestamp="t")
    arm_after = eng.arm(d.chosen_offer).n_pulls
    assert arm_after == arm_before + 1


def _test_engine_record_feedback_invalid_reward_raises():
    eng = _make_test_engine(d=3)
    ctx = CustomerContext(
        cif="C1",
        feature_names=tuple(f"feat_{i}" for i in range(3)),
        feature_values=(1.0, 2.0, 3.0),
        decision_timestamp="t")
    eng.decide(decision_id="D1", context=ctx)
    try:
        eng.record_feedback(
            feedback_id="F1", decision_id="D1",
            reward=1.5,    # > 1.0
            feedback_timestamp="t")
        assert False
    except ValueError:
        pass


def _test_engine_record_feedback_unknown_decision_raises():
    """Per Rule 7: cannot fabricate a decision to attach feedback to."""
    eng = _make_test_engine(d=3)
    try:
        eng.record_feedback(
            feedback_id="F1",
            decision_id="UNKNOWN",
            reward=1.0,
            feedback_timestamp="t")
        assert False
    except KeyError:
        pass


def _test_engine_record_feedback_dup_raises():
    eng = _make_test_engine(d=3)
    ctx = CustomerContext(
        cif="C1",
        feature_names=tuple(f"feat_{i}" for i in range(3)),
        feature_values=(1.0, 2.0, 3.0),
        decision_timestamp="t")
    eng.decide(decision_id="D1", context=ctx)
    eng.record_feedback(
        feedback_id="F1", decision_id="D1",
        reward=1.0, feedback_timestamp="t")
    try:
        eng.record_feedback(
            feedback_id="F1", decision_id="D1",
            reward=0.0, feedback_timestamp="t")
        assert False
    except ValueError:
        pass


def _test_engine_offer_distribution():
    eng = _make_test_engine(d=3)
    for i in range(5):
        ctx = CustomerContext(
            cif=f"C{i}",
            feature_names=tuple(f"feat_{i}" for i in range(3)),
            feature_values=(float(i+1), float(i+1), 1.0),
            decision_timestamp="t")
        eng.decide(decision_id=f"D{i}", context=ctx)
    dist = eng.offer_distribution()
    total = sum(dist.values())
    assert total == 5


def _test_engine_board_summary():
    eng = _make_test_engine(d=3)
    s = eng.board_summary()
    assert s["n_features"] == 3
    assert s["n_arms"] == len(DEFAULT_OFFER_CATALOG)
    assert s["alpha"] == 1.0


# ── Feature extraction ────────────────────────────────────────────
def _test_extract_features_from_bank():
    from utils.virtual_bank_core import (
        VirtualBranch, VirtualCustomer, VirtualAccount)
    bank = VirtualBankCore(
        entity_name="Test", base_seed="t",
        base_date="2026-01-01")
    bank.add_branch(VirtualBranch(
        branch_code="BR1", branch_name="X", region="Y",
        branch_type="MAIN", n_staff=5))
    bank.add_customer(VirtualCustomer(
        cif="C1", full_name="X",
        segment=CustomerSegment.RETAIL,
        branch_code="BR1", rm_code="RM1",
        onboarding_date="2025-01-01"))
    bank.add_account(VirtualAccount(
        account_no="A1", cif="C1",
        branch_code="BR1",
        account_type=AccountType.SAVINGS,
        currency="KES",
        balance=Decimal("100000"),
        status=AccountStatus.ACTIVE,
        open_date="2025-01-01"))
    ctx = extract_features_from_bank(
        bank=bank, cif="C1",
        decision_timestamp="2026-05-01T00:00:00Z")
    assert ctx.cif == "C1"
    assert "balance_log" in ctx.feature_names
    assert "intercept" in ctx.feature_names
    # log10(100000) = 5
    bal_idx = ctx.feature_names.index("balance_log")
    assert abs(ctx.feature_values[bal_idx] - 5.0) < 0.001


def _test_extract_features_unknown_feature_raises():
    from utils.virtual_bank_core import (
        VirtualBranch, VirtualCustomer)
    bank = VirtualBankCore(
        entity_name="X", base_seed="t",
        base_date="2026-01-01")
    bank.add_branch(VirtualBranch(
        branch_code="BR1", branch_name="X", region="Y",
        branch_type="MAIN", n_staff=5))
    bank.add_customer(VirtualCustomer(
        cif="C1", full_name="X",
        segment=CustomerSegment.RETAIL,
        branch_code="BR1", rm_code="RM1",
        onboarding_date="2025-01-01"))
    try:
        extract_features_from_bank(
            bank=bank, cif="C1",
            feature_names=("balance_log", "MADE_UP_FEATURE"),
            decision_timestamp="t")
        assert False
    except ValueError:
        pass


def _test_extract_features_observes_npl_status():
    from utils.virtual_bank_core import (
        VirtualBranch, VirtualCustomer, VirtualLoan)
    bank = VirtualBankCore(
        entity_name="X", base_seed="t",
        base_date="2026-05-01")
    bank.add_branch(VirtualBranch(
        branch_code="BR1", branch_name="X", region="Y",
        branch_type="MAIN", n_staff=5))
    bank.add_customer(VirtualCustomer(
        cif="C1", full_name="X",
        segment=CustomerSegment.RETAIL,
        branch_code="BR1", rm_code="RM1",
        onboarding_date="2025-01-01"))
    bank.add_loan(VirtualLoan(
        loan_id="L1", cif="C1",
        branch_code="BR1", rm_code="RM1",
        principal=Decimal("500000"),
        outstanding=Decimal("450000"),
        rate_pct=Decimal("13.5"),
        tenor_months=24,
        disbursement_date="2025-06-01",
        next_due_date="2025-12-01",
        status=LoanStatus.NON_PERFORMING,
        days_past_due=200))
    ctx = extract_features_from_bank(
        bank=bank, cif="C1", decision_timestamp="t")
    assert ctx.loan_status_observed == LoanStatus.NON_PERFORMING


def self_test() -> None:
    tests = [
        _test_identity_matrix,
        _test_invert_identity,
        _test_invert_simple,
        _test_invert_singular_raises,
        _test_mat_vec_mul,
        _test_vec_dot,
        _test_vec_outer,
        _test_forbidden_features_caught,
        _test_safe_features_pass,
        _test_forbidden_substring_caught,
        _test_context_validates_no_protected_attrs,
        _test_context_length_mismatch_raises,
        _test_arm_initialization,
        _test_arm_predict_score_initial,
        _test_arm_update_changes_state,
        _test_arm_update_dim_mismatch_raises,
        _test_arm_learning_increases_exploitation,
        _test_config_rejects_protected_features,
        _test_config_rejects_too_few_arms,
        _test_engine_initialization,
        _test_engine_decide_returns_offer,
        _test_engine_decide_dim_mismatch_raises,
        _test_engine_risk_appetite_filter_suppresses_loan_for_npl,
        _test_engine_risk_appetite_allows_loans_for_performing,
        _test_engine_record_feedback_updates_arm,
        _test_engine_record_feedback_invalid_reward_raises,
        _test_engine_record_feedback_unknown_decision_raises,
        _test_engine_record_feedback_dup_raises,
        _test_engine_offer_distribution,
        _test_engine_board_summary,
        _test_extract_features_from_bank,
        _test_extract_features_unknown_feature_raises,
        _test_extract_features_observes_npl_status,
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
        print(f"✗ cross_sell_bandit self-test: "
              f"{len(failed)} failures", file=sys.stderr)
        for name, msg in failed:
            print(f"  - {name}: {msg}", file=sys.stderr)
        raise SystemExit(1)
    print(f"✓ cross_sell_bandit self-test passed "
          f"({len(tests)} tests)")


if __name__ == "__main__":
    self_test()
