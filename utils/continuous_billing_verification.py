"""utils/continuous_billing_verification.py — v10.55: Pre-Issuance Billing Verification.

╔════════════════════════════════════════════════════════════════════════╗
║  ENH-246 — Continuous Billing Verification                              ║
║  Cat B — revenue_assurance arc continuation                             ║
╠════════════════════════════════════════════════════════════════════════╣
║  Pre-issuance verification engine. Critical scope distinction from      ║
║  ENH-242: ENH-242 screens POSTED records for anomalies; ENH-246         ║
║  screens PENDING records before they post — catches mistakes before     ║
║  the invoice goes out, not after.                                       ║
║                                                                          ║
║  Five verification checks per BillingDraft:                             ║
║    1. CONTRACT_LIFECYCLE   — contract exists, covers draft_date         ║
║    2. RATE_BAND            — applied_rate ∈ [floor, ceiling]            ║
║    3. TAX_COMPUTATION      — computed_tax ≈ amount × tax_rate           ║
║    4. DISCOUNT_AUTH        — discount > 0 needs authorization_id        ║
║    5. DISCOUNT_BAND        — discount ≤ contract.max_discount_pct       ║
║                                                                          ║
║  Verdicts:                                                               ║
║    PASS                       — all checks green                        ║
║    HOLD_PENDING_REVIEW        — non-blocking finding(s)                 ║
║    REJECT_RECOMMENDED         — blocking finding(s)                     ║
║                                                                          ║
║  Per Rule 7, engine recommends — never blocks billing itself. The       ║
║  caller's billing pipeline reads the verdict and decides; engine        ║
║  never holds, releases, or modifies a draft.                            ║
║                                                                          ║
║  Per Rule 1, every CheckResult surfaces check_name + status +           ║
║  description + expected + observed + framework refs. The aggregate      ║
║  VerificationResult surfaces all 5 results plus the verdict.            ║
║                                                                          ║
║  Pure stdlib (Decimal + frozen dataclasses + enums).                    ║
║                                                                          ║
║  Composes with:                                                          ║
║    - revenue_anomaly_patterns (ENH-242 — reuses ContractRate)          ║
║    - revenue_validation (ENH-241 — reuses ValidationSeverity)          ║
║    - revenue_orchestrator (ENH-243 — verdicts feed orchestrator         ║
║      via VerificationFinding shape)                                     ║
╚════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import Enum
from typing import Dict, List, Optional, Sequence, Tuple

from utils.revenue_validation import ValidationSeverity
from utils.revenue_anomaly_patterns import ContractRate

SPEC_DEVIATION_NOTE = (
    "ContinuousBillingVerificationEngine implements ENH-246 as "
    "pre-issuance verification. Pure stdlib (Decimal + "
    "dataclasses). Per Rule 1, every CheckResult and the "
    "aggregate VerificationResult surface full provenance + "
    "framework refs. Per Rule 7, engine RECOMMENDS verdicts — "
    "never blocks billing, never releases held drafts, never "
    "modifies the draft itself. Caller's billing pipeline reads "
    "verdict and decides. ContractRate dataclass reused from "
    "ENH-242 for cross-arc consistency."
)


# ════════════════════════════════════════════════════════════════════════
# Enums
# ════════════════════════════════════════════════════════════════════════

class CheckName(Enum):
    CONTRACT_LIFECYCLE = "CONTRACT_LIFECYCLE"
    RATE_BAND = "RATE_BAND"
    TAX_COMPUTATION = "TAX_COMPUTATION"
    DISCOUNT_AUTH = "DISCOUNT_AUTH"
    DISCOUNT_BAND = "DISCOUNT_BAND"


class CheckStatus(Enum):
    PASS = "PASS"
    WARN = "WARN"        # non-blocking
    FAIL = "FAIL"        # blocking
    SKIPPED = "SKIPPED"  # required input absent


class Verdict(Enum):
    PASS = "PASS"
    HOLD_PENDING_REVIEW = "HOLD_PENDING_REVIEW"
    REJECT_RECOMMENDED = "REJECT_RECOMMENDED"


# ════════════════════════════════════════════════════════════════════════
# Dataclasses
# ════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class ExtendedContractRate:
    """Extends ENH-242's ContractRate with optional max_discount_pct
    for the discount-band check. Keep ENH-242's ContractRate
    pristine; this is an optional sidecar."""
    contract_id: str
    max_discount_pct: Optional[Decimal] = None  # 0..1

    def __post_init__(self) -> None:
        if not self.contract_id:
            raise ValueError("contract_id must be non-empty")
        if (self.max_discount_pct is not None and
                not (Decimal("0") <= self.max_discount_pct
                     <= Decimal("1"))):
            raise ValueError(
                "max_discount_pct must be in [0, 1]")


@dataclass(frozen=True)
class BillingDraft:
    """A pending invoice line not yet issued."""
    draft_id: str
    customer_id: str
    product_code: str
    contract_id: Optional[str]
    proposed_amount_kes: Decimal
    draft_date: date
    applied_rate_pct: Optional[Decimal] = None
    discount_pct: Decimal = Decimal("0")
    discount_authorization_id: Optional[str] = None
    tax_rate_pct: Optional[Decimal] = None       # e.g. 0.16 for 16% VAT
    computed_tax_kes: Optional[Decimal] = None

    def __post_init__(self) -> None:
        if not self.draft_id:
            raise ValueError("draft_id must be non-empty")
        if self.proposed_amount_kes < 0:
            raise ValueError("proposed_amount_kes must be ≥ 0")
        if not (Decimal("0") <= self.discount_pct <= Decimal("1")):
            raise ValueError("discount_pct must be in [0, 1]")


@dataclass(frozen=True)
class CheckResult:
    check_name: CheckName
    status: CheckStatus
    severity: ValidationSeverity
    description: str
    expected: str
    observed: str
    framework_refs: Tuple[str, ...] = ()


@dataclass(frozen=True)
class VerificationResult:
    draft_id: str
    verdict: Verdict
    check_results: Tuple[CheckResult, ...]
    fail_count: int
    warn_count: int
    skipped_count: int
    framework_refs: Tuple[str, ...]
    notes: str = ""


# ════════════════════════════════════════════════════════════════════════
# Engine
# ════════════════════════════════════════════════════════════════════════

class ContinuousBillingVerificationEngine:
    """Pre-issuance billing verification.

    Per Rule 7, the engine never:
      - blocks a draft from being issued
      - releases a held draft
      - modifies the draft
      - posts the draft to GL
      - notifies anyone

    The caller's billing pipeline reads the verdict and decides
    what to do — typically: PASS → release; HOLD → hold for
    operator review; REJECT_RECOMMENDED → reject (caller can
    override after investigation).
    """

    # 1% tolerance on tax computation, with KES 5 floor for very
    # small bills. Matches the broader 1% tolerance discipline
    # across the arc.
    TAX_TOLERANCE_PCT: Decimal = Decimal("0.01")
    TAX_TOLERANCE_FLOOR_KES: Decimal = Decimal("5")

    # ── Check 1: Contract lifecycle ─────────────────────────────────
    def _check_contract_lifecycle(
        self, draft: BillingDraft,
        contracts: Dict[str, ContractRate],
    ) -> CheckResult:
        if draft.contract_id is None:
            return CheckResult(
                check_name=CheckName.CONTRACT_LIFECYCLE,
                status=CheckStatus.SKIPPED,
                severity=ValidationSeverity.INFO,
                description="no contract reference on draft",
                expected="contract_id present (or N/A for ad-hoc)",
                observed="contract_id=None",
                framework_refs=("ENH-246 §contract_lifecycle",))
        contract = contracts.get(draft.contract_id)
        if contract is None:
            return CheckResult(
                check_name=CheckName.CONTRACT_LIFECYCLE,
                status=CheckStatus.FAIL,
                severity=ValidationSeverity.HIGH,
                description=(
                    f"contract {draft.contract_id} not found "
                    "in active master"),
                expected="contract present in master",
                observed="contract not found",
                framework_refs=(
                    "ENH-246 §contract_lifecycle",
                    "Master data discipline"))
        if not (contract.effective_from
                <= draft.draft_date
                <= contract.effective_to):
            return CheckResult(
                check_name=CheckName.CONTRACT_LIFECYCLE,
                status=CheckStatus.FAIL,
                severity=ValidationSeverity.HIGH,
                description=(
                    f"draft date "
                    f"{draft.draft_date.isoformat()} outside "
                    f"contract effective window"),
                expected=(
                    f"{contract.effective_from.isoformat()} "
                    f"to {contract.effective_to.isoformat()}"),
                observed=draft.draft_date.isoformat(),
                framework_refs=(
                    "ENH-246 §contract_lifecycle",
                    "ENH-242 §expired_contract_billing"))
        return CheckResult(
            check_name=CheckName.CONTRACT_LIFECYCLE,
            status=CheckStatus.PASS,
            severity=ValidationSeverity.INFO,
            description="contract active and covers draft date",
            expected="active contract",
            observed=f"contract {contract.contract_id} active",
            framework_refs=("ENH-246 §contract_lifecycle",))

    # ── Check 2: Rate band ──────────────────────────────────────────
    def _check_rate_band(
        self, draft: BillingDraft,
        contracts: Dict[str, ContractRate],
    ) -> CheckResult:
        if draft.contract_id is None or draft.applied_rate_pct is None:
            return CheckResult(
                check_name=CheckName.RATE_BAND,
                status=CheckStatus.SKIPPED,
                severity=ValidationSeverity.INFO,
                description=(
                    "no contract or applied_rate to check"),
                expected=(
                    "contract_id + applied_rate_pct populated"),
                observed=(
                    f"contract_id={draft.contract_id}, "
                    f"applied_rate_pct={draft.applied_rate_pct}"),
                framework_refs=("ENH-246 §rate_band",))
        contract = contracts.get(draft.contract_id)
        if contract is None:
            return CheckResult(
                check_name=CheckName.RATE_BAND,
                status=CheckStatus.SKIPPED,
                severity=ValidationSeverity.INFO,
                description=(
                    "contract missing — handled by lifecycle check"),
                expected="contract present",
                observed="contract not found",
                framework_refs=("ENH-246 §rate_band",))
        if draft.applied_rate_pct < contract.floor_rate_pct:
            return CheckResult(
                check_name=CheckName.RATE_BAND,
                status=CheckStatus.WARN,
                severity=ValidationSeverity.MEDIUM,
                description=(
                    f"applied rate {draft.applied_rate_pct}% "
                    f"below contract floor "
                    f"{contract.floor_rate_pct}% — leakage"),
                expected=(
                    f"≥ {contract.floor_rate_pct}%"),
                observed=f"{draft.applied_rate_pct}%",
                framework_refs=(
                    "ENH-246 §rate_band",
                    "ENH-242 §rate_card_breach"))
        if draft.applied_rate_pct > contract.ceiling_rate_pct:
            return CheckResult(
                check_name=CheckName.RATE_BAND,
                status=CheckStatus.FAIL,
                severity=ValidationSeverity.HIGH,
                description=(
                    f"applied rate {draft.applied_rate_pct}% "
                    f"above contract ceiling "
                    f"{contract.ceiling_rate_pct}% — "
                    f"compliance breach"),
                expected=(
                    f"≤ {contract.ceiling_rate_pct}%"),
                observed=f"{draft.applied_rate_pct}%",
                framework_refs=(
                    "ENH-246 §rate_band",
                    "Consumer protection — fair pricing"))
        return CheckResult(
            check_name=CheckName.RATE_BAND,
            status=CheckStatus.PASS,
            severity=ValidationSeverity.INFO,
            description="applied rate within contract band",
            expected=(
                f"[{contract.floor_rate_pct}, "
                f"{contract.ceiling_rate_pct}]%"),
            observed=f"{draft.applied_rate_pct}%",
            framework_refs=("ENH-246 §rate_band",))

    # ── Check 3: Tax computation ────────────────────────────────────
    def _check_tax_computation(
        self, draft: BillingDraft,
    ) -> CheckResult:
        if (draft.tax_rate_pct is None or
                draft.computed_tax_kes is None):
            return CheckResult(
                check_name=CheckName.TAX_COMPUTATION,
                status=CheckStatus.SKIPPED,
                severity=ValidationSeverity.INFO,
                description=(
                    "no tax rate or computed tax to verify"),
                expected="both tax_rate_pct and computed_tax_kes",
                observed=(
                    f"tax_rate_pct={draft.tax_rate_pct}, "
                    f"computed_tax_kes={draft.computed_tax_kes}"),
                framework_refs=("ENH-246 §tax_computation",))
        # Tax base is amount AFTER discount
        net_amount = (
            draft.proposed_amount_kes
            * (Decimal("1") - draft.discount_pct))
        expected_tax = net_amount * draft.tax_rate_pct
        tolerance = max(
            self.TAX_TOLERANCE_FLOOR_KES,
            expected_tax * self.TAX_TOLERANCE_PCT)
        diff = abs(draft.computed_tax_kes - expected_tax)
        if diff <= tolerance:
            return CheckResult(
                check_name=CheckName.TAX_COMPUTATION,
                status=CheckStatus.PASS,
                severity=ValidationSeverity.INFO,
                description="tax computation matches expected",
                expected=str(expected_tax),
                observed=str(draft.computed_tax_kes),
                framework_refs=("ENH-246 §tax_computation",))
        return CheckResult(
            check_name=CheckName.TAX_COMPUTATION,
            status=CheckStatus.FAIL,
            severity=ValidationSeverity.HIGH,
            description=(
                f"tax computation mismatch: expected "
                f"{expected_tax}, computed "
                f"{draft.computed_tax_kes}"),
            expected=f"≈ {expected_tax} (±{tolerance})",
            observed=str(draft.computed_tax_kes),
            framework_refs=(
                "ENH-246 §tax_computation",
                "KRA tax compliance"))

    # ── Check 4: Discount authorization ─────────────────────────────
    def _check_discount_auth(
        self, draft: BillingDraft,
    ) -> CheckResult:
        if draft.discount_pct == 0:
            return CheckResult(
                check_name=CheckName.DISCOUNT_AUTH,
                status=CheckStatus.SKIPPED,
                severity=ValidationSeverity.INFO,
                description="no discount applied",
                expected="discount_pct > 0 needs authorization",
                observed="discount_pct=0",
                framework_refs=("ENH-246 §discount_auth",))
        if draft.discount_authorization_id:
            return CheckResult(
                check_name=CheckName.DISCOUNT_AUTH,
                status=CheckStatus.PASS,
                severity=ValidationSeverity.INFO,
                description="discount authorized",
                expected="non-empty authorization_id",
                observed=(
                    f"authorization_id="
                    f"{draft.discount_authorization_id}"),
                framework_refs=("ENH-246 §discount_auth",))
        return CheckResult(
            check_name=CheckName.DISCOUNT_AUTH,
            status=CheckStatus.FAIL,
            severity=ValidationSeverity.HIGH,
            description=(
                f"discount {draft.discount_pct} applied without "
                f"authorization_id — leakage"),
            expected="non-empty authorization_id",
            observed="authorization_id=None",
            framework_refs=(
                "ENH-246 §discount_auth",
                "ENH-242 §unauthorized_fee_waiver"))

    # ── Check 5: Discount band ──────────────────────────────────────
    def _check_discount_band(
        self, draft: BillingDraft,
        ext_contracts: Dict[str, ExtendedContractRate],
    ) -> CheckResult:
        if draft.discount_pct == 0 or draft.contract_id is None:
            return CheckResult(
                check_name=CheckName.DISCOUNT_BAND,
                status=CheckStatus.SKIPPED,
                severity=ValidationSeverity.INFO,
                description=(
                    "no discount or contract — band check N/A"),
                expected="discount_pct > 0 + contract_id present",
                observed=(
                    f"discount_pct={draft.discount_pct}, "
                    f"contract_id={draft.contract_id}"),
                framework_refs=("ENH-246 §discount_band",))
        ext = ext_contracts.get(draft.contract_id)
        if ext is None or ext.max_discount_pct is None:
            return CheckResult(
                check_name=CheckName.DISCOUNT_BAND,
                status=CheckStatus.SKIPPED,
                severity=ValidationSeverity.INFO,
                description=(
                    "no max_discount_pct configured for contract"),
                expected="ExtendedContractRate present",
                observed="not found",
                framework_refs=("ENH-246 §discount_band",))
        if draft.discount_pct > ext.max_discount_pct:
            return CheckResult(
                check_name=CheckName.DISCOUNT_BAND,
                status=CheckStatus.FAIL,
                severity=ValidationSeverity.HIGH,
                description=(
                    f"discount {draft.discount_pct} exceeds "
                    f"contract max {ext.max_discount_pct}"),
                expected=f"≤ {ext.max_discount_pct}",
                observed=str(draft.discount_pct),
                framework_refs=("ENH-246 §discount_band",))
        return CheckResult(
            check_name=CheckName.DISCOUNT_BAND,
            status=CheckStatus.PASS,
            severity=ValidationSeverity.INFO,
            description="discount within contract band",
            expected=f"≤ {ext.max_discount_pct}",
            observed=str(draft.discount_pct),
            framework_refs=("ENH-246 §discount_band",))

    # ── Verdict aggregation ─────────────────────────────────────────
    @staticmethod
    def _aggregate_verdict(
        results: Sequence[CheckResult],
    ) -> Verdict:
        if any(r.status == CheckStatus.FAIL for r in results):
            return Verdict.REJECT_RECOMMENDED
        if any(r.status == CheckStatus.WARN for r in results):
            return Verdict.HOLD_PENDING_REVIEW
        return Verdict.PASS

    # ── Public API ──────────────────────────────────────────────────
    def verify(
        self,
        draft: BillingDraft,
        contracts: Sequence[ContractRate] = (),
        extended_contracts: Sequence[ExtendedContractRate] = (),
        notes: str = "",
    ) -> VerificationResult:
        contract_index = {c.contract_id: c for c in contracts}
        ext_index = {
            e.contract_id: e for e in extended_contracts}

        results = (
            self._check_contract_lifecycle(draft, contract_index),
            self._check_rate_band(draft, contract_index),
            self._check_tax_computation(draft),
            self._check_discount_auth(draft),
            self._check_discount_band(draft, ext_index),
        )
        verdict = self._aggregate_verdict(results)
        fail_count = sum(
            1 for r in results if r.status == CheckStatus.FAIL)
        warn_count = sum(
            1 for r in results if r.status == CheckStatus.WARN)
        skipped_count = sum(
            1 for r in results
            if r.status == CheckStatus.SKIPPED)

        return VerificationResult(
            draft_id=draft.draft_id,
            verdict=verdict,
            check_results=results,
            fail_count=fail_count,
            warn_count=warn_count,
            skipped_count=skipped_count,
            framework_refs=(
                "ENH-246 §verify",
                "Composes ENH-241 ValidationSeverity + "
                "ENH-242 ContractRate",
                "Per Rule 7 — recommends verdict, never blocks "
                "billing",
            ),
            notes=notes)

    def verify_batch(
        self,
        drafts: Sequence[BillingDraft],
        contracts: Sequence[ContractRate] = (),
        extended_contracts: Sequence[ExtendedContractRate] = (),
    ) -> Tuple[VerificationResult, ...]:
        return tuple(
            self.verify(d, contracts, extended_contracts)
            for d in drafts)


# ════════════════════════════════════════════════════════════════════════
# Self-tests
# ════════════════════════════════════════════════════════════════════════

def _default_contract():
    return ContractRate(
        contract_id="C1", customer_id="cust-A",
        product_code="LOAN", floor_rate_pct=Decimal("3.0"),
        ceiling_rate_pct=Decimal("8.0"),
        effective_from=date(2026, 1, 1),
        effective_to=date(2026, 12, 31))


def _test_draft_validates_amount_non_negative():
    try:
        BillingDraft(
            draft_id="d1", customer_id="c", product_code="p",
            contract_id=None,
            proposed_amount_kes=Decimal("-1"),
            draft_date=date(2026, 4, 1))
        assert False
    except ValueError:
        pass


def _test_draft_validates_discount_range():
    try:
        BillingDraft(
            draft_id="d1", customer_id="c", product_code="p",
            contract_id=None,
            proposed_amount_kes=Decimal("100"),
            draft_date=date(2026, 4, 1),
            discount_pct=Decimal("1.5"))
        assert False
    except ValueError:
        pass


def _test_extended_contract_validates_max_discount():
    try:
        ExtendedContractRate(
            contract_id="C1",
            max_discount_pct=Decimal("1.5"))
        assert False
    except ValueError:
        pass


def _test_clean_draft_passes():
    eng = ContinuousBillingVerificationEngine()
    draft = BillingDraft(
        draft_id="d1", customer_id="cust-A",
        product_code="LOAN", contract_id="C1",
        proposed_amount_kes=Decimal("100000"),
        draft_date=date(2026, 4, 15),
        applied_rate_pct=Decimal("5.0"))
    result = eng.verify(draft, contracts=(_default_contract(),))
    assert result.verdict == Verdict.PASS
    assert result.fail_count == 0
    assert result.warn_count == 0


def _test_missing_contract_fails():
    eng = ContinuousBillingVerificationEngine()
    draft = BillingDraft(
        draft_id="d1", customer_id="cust-A",
        product_code="LOAN", contract_id="MISSING",
        proposed_amount_kes=Decimal("100000"),
        draft_date=date(2026, 4, 15))
    result = eng.verify(draft, contracts=(_default_contract(),))
    assert result.verdict == Verdict.REJECT_RECOMMENDED
    assert result.fail_count >= 1


def _test_expired_contract_fails():
    eng = ContinuousBillingVerificationEngine()
    draft = BillingDraft(
        draft_id="d1", customer_id="cust-A",
        product_code="LOAN", contract_id="C1",
        proposed_amount_kes=Decimal("100000"),
        draft_date=date(2027, 6, 1))   # after effective_to
    result = eng.verify(draft, contracts=(_default_contract(),))
    assert result.verdict == Verdict.REJECT_RECOMMENDED
    lifecycle = next(
        r for r in result.check_results
        if r.check_name == CheckName.CONTRACT_LIFECYCLE)
    assert lifecycle.status == CheckStatus.FAIL


def _test_rate_below_floor_warns_not_fails():
    """Below-floor rate is leakage but not a compliance breach —
    WARN (HOLD), not FAIL."""
    eng = ContinuousBillingVerificationEngine()
    draft = BillingDraft(
        draft_id="d1", customer_id="cust-A",
        product_code="LOAN", contract_id="C1",
        proposed_amount_kes=Decimal("100000"),
        draft_date=date(2026, 4, 15),
        applied_rate_pct=Decimal("2.0"))
    result = eng.verify(draft, contracts=(_default_contract(),))
    assert result.verdict == Verdict.HOLD_PENDING_REVIEW
    rate = next(
        r for r in result.check_results
        if r.check_name == CheckName.RATE_BAND)
    assert rate.status == CheckStatus.WARN


def _test_rate_above_ceiling_fails():
    eng = ContinuousBillingVerificationEngine()
    draft = BillingDraft(
        draft_id="d1", customer_id="cust-A",
        product_code="LOAN", contract_id="C1",
        proposed_amount_kes=Decimal("100000"),
        draft_date=date(2026, 4, 15),
        applied_rate_pct=Decimal("10.0"))
    result = eng.verify(draft, contracts=(_default_contract(),))
    assert result.verdict == Verdict.REJECT_RECOMMENDED


def _test_tax_computation_correct_passes():
    eng = ContinuousBillingVerificationEngine()
    draft = BillingDraft(
        draft_id="d1", customer_id="c", product_code="p",
        contract_id=None,
        proposed_amount_kes=Decimal("1000"),
        draft_date=date(2026, 4, 15),
        tax_rate_pct=Decimal("0.16"),
        computed_tax_kes=Decimal("160"))
    result = eng.verify(draft)
    tax = next(
        r for r in result.check_results
        if r.check_name == CheckName.TAX_COMPUTATION)
    assert tax.status == CheckStatus.PASS


def _test_tax_computation_with_discount():
    """Tax base = amount × (1 - discount)."""
    eng = ContinuousBillingVerificationEngine()
    draft = BillingDraft(
        draft_id="d1", customer_id="c", product_code="p",
        contract_id="C1",
        proposed_amount_kes=Decimal("1000"),
        draft_date=date(2026, 4, 15),
        discount_pct=Decimal("0.20"),
        discount_authorization_id="AUTH-1",
        tax_rate_pct=Decimal("0.16"),
        # Net = 800; tax = 128
        computed_tax_kes=Decimal("128"))
    result = eng.verify(draft, contracts=(_default_contract(),))
    tax = next(
        r for r in result.check_results
        if r.check_name == CheckName.TAX_COMPUTATION)
    assert tax.status == CheckStatus.PASS


def _test_tax_computation_wrong_fails():
    eng = ContinuousBillingVerificationEngine()
    draft = BillingDraft(
        draft_id="d1", customer_id="c", product_code="p",
        contract_id=None,
        proposed_amount_kes=Decimal("1000"),
        draft_date=date(2026, 4, 15),
        tax_rate_pct=Decimal("0.16"),
        computed_tax_kes=Decimal("100"))   # should be 160
    result = eng.verify(draft)
    assert result.verdict == Verdict.REJECT_RECOMMENDED


def _test_unauthorized_discount_fails():
    eng = ContinuousBillingVerificationEngine()
    draft = BillingDraft(
        draft_id="d1", customer_id="c", product_code="p",
        contract_id=None,
        proposed_amount_kes=Decimal("1000"),
        draft_date=date(2026, 4, 15),
        discount_pct=Decimal("0.10"),
        discount_authorization_id=None)
    result = eng.verify(draft)
    assert result.verdict == Verdict.REJECT_RECOMMENDED
    auth = next(
        r for r in result.check_results
        if r.check_name == CheckName.DISCOUNT_AUTH)
    assert auth.status == CheckStatus.FAIL


def _test_authorized_discount_passes():
    eng = ContinuousBillingVerificationEngine()
    draft = BillingDraft(
        draft_id="d1", customer_id="c", product_code="p",
        contract_id=None,
        proposed_amount_kes=Decimal("1000"),
        draft_date=date(2026, 4, 15),
        discount_pct=Decimal("0.10"),
        discount_authorization_id="AUTH-001")
    result = eng.verify(draft)
    auth = next(
        r for r in result.check_results
        if r.check_name == CheckName.DISCOUNT_AUTH)
    assert auth.status == CheckStatus.PASS


def _test_discount_above_band_fails():
    eng = ContinuousBillingVerificationEngine()
    ext = ExtendedContractRate(
        contract_id="C1",
        max_discount_pct=Decimal("0.15"))
    draft = BillingDraft(
        draft_id="d1", customer_id="cust-A",
        product_code="LOAN", contract_id="C1",
        proposed_amount_kes=Decimal("1000"),
        draft_date=date(2026, 4, 15),
        discount_pct=Decimal("0.25"),
        discount_authorization_id="AUTH-001")
    result = eng.verify(
        draft, contracts=(_default_contract(),),
        extended_contracts=(ext,))
    assert result.verdict == Verdict.REJECT_RECOMMENDED


def _test_skipped_checks_dont_drive_verdict():
    eng = ContinuousBillingVerificationEngine()
    draft = BillingDraft(
        draft_id="d1", customer_id="c", product_code="p",
        contract_id=None,
        proposed_amount_kes=Decimal("1000"),
        draft_date=date(2026, 4, 15))
    result = eng.verify(draft)
    assert result.verdict == Verdict.PASS
    assert result.skipped_count >= 1


def _test_verify_batch_processes_multiple():
    eng = ContinuousBillingVerificationEngine()
    drafts = (
        BillingDraft(
            draft_id="d1", customer_id="c", product_code="p",
            contract_id=None,
            proposed_amount_kes=Decimal("1000"),
            draft_date=date(2026, 4, 15)),
        BillingDraft(
            draft_id="d2", customer_id="c", product_code="p",
            contract_id="MISSING",
            proposed_amount_kes=Decimal("1000"),
            draft_date=date(2026, 4, 15)),
    )
    results = eng.verify_batch(drafts)
    assert len(results) == 2
    assert results[0].verdict == Verdict.PASS
    assert results[1].verdict == Verdict.REJECT_RECOMMENDED


def _test_full_provenance():
    eng = ContinuousBillingVerificationEngine()
    draft = BillingDraft(
        draft_id="prov-test", customer_id="c", product_code="p",
        contract_id=None,
        proposed_amount_kes=Decimal("1000"),
        draft_date=date(2026, 4, 15))
    result = eng.verify(draft, notes="prov")
    assert result.draft_id == "prov-test"
    assert len(result.check_results) == 5
    for r in result.check_results:
        assert r.expected
        assert r.observed
        assert len(r.framework_refs) >= 1


def self_test() -> None:
    tests = [
        _test_draft_validates_amount_non_negative,
        _test_draft_validates_discount_range,
        _test_extended_contract_validates_max_discount,
        _test_clean_draft_passes,
        _test_missing_contract_fails,
        _test_expired_contract_fails,
        _test_rate_below_floor_warns_not_fails,
        _test_rate_above_ceiling_fails,
        _test_tax_computation_correct_passes,
        _test_tax_computation_with_discount,
        _test_tax_computation_wrong_fails,
        _test_unauthorized_discount_fails,
        _test_authorized_discount_passes,
        _test_discount_above_band_fails,
        _test_skipped_checks_dont_drive_verdict,
        _test_verify_batch_processes_multiple,
        _test_full_provenance,
    ]
    failed: List[Tuple[str, str]] = []
    for t in tests:
        try:
            t()
        except AssertionError as e:
            failed.append((t.__name__, str(e)))
        except Exception as e:
            failed.append((t.__name__, f"{type(e).__name__}: {e}"))
    if failed:
        print(
            f"✗ continuous_billing_verification self-test: "
            f"{len(failed)} failures",
            file=sys.stderr)
        for name, msg in failed:
            print(f"  - {name}: {msg}", file=sys.stderr)
        raise SystemExit(1)
    print(
        f"✓ continuous_billing_verification self-test passed "
        f"({len(tests)} tests)")


if __name__ == "__main__":
    self_test()
