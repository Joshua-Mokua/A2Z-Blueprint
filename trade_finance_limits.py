"""utils/trade_finance_limits.py — v10.71: TF limits.

ENH-273 — Trade Finance Limits & Risk Management. Cat B —
trade_finance arc 2/N.

Diagnostic pre-deal limit checking + post-deal allocation engine
for trade finance instruments. Consumes TradeInstrument objects
from ENH-269 and surfaces 4-dimensional limit utilization +
breach analysis. Composes with ENH-252 CBK regulatory single-
borrower limits but operates at the trade-finance product level
(distinct concerns: ENH-252 covers bank-wide aggregate exposure;
ENH-273 covers per-instrument pre-deal allocation).

Four dimensions of limit checking:
  1. Country limit — exposure to a foreign country (sovereign +
     counterparty risk concentration)
  2. Counterparty limit — total exposure to a single corporate
     counterparty (across all products)
  3. Product limit — concentration in a single trade finance
     product type (LC / SBLC / BG / Collection)
  4. Tenor limit — exposure aging concentration (short / medium
     / long buckets) — concentration in long-tenor exposure
     materially worsens liquidity profile

Per Rule 7, engine NEVER:
  - approves or rejects deals (computes utilization only)
  - blocks instrument issuance
  - posts limit allocations to source systems
  - amends operator-set limits
  - sources market data (counterparty FX exposure caller-supplied)
  - mutates inputs

Per Rule 1, every utilization output surfaces dimension +
exposure + limit + utilization% + headroom + breach severity +
contributing instrument IDs + framework refs.

Pure stdlib (Decimal + frozen dataclasses + enums).
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Dict, List, Optional, Sequence, Tuple

from utils.trade_finance_instruments import (
    TradeInstrument, InstrumentType, InstrumentState)

SPEC_DEVIATION_NOTE = (
    "TradeFinanceLimitsEngine implements ENH-273 — pre-deal "
    "+ post-deal limit utilization checking across country, "
    "counterparty, product, tenor dimensions. Composes with "
    "ENH-269 instruments. Distinct from ENH-252 (CBK bank-wide "
    "aggregate). Pure stdlib. Per Rule 1, every utilization "
    "output surfaces full provenance. Per Rule 7, engine "
    "DIAGNOSTIC ONLY — never approves or rejects deals (computes "
    "only); never blocks issuance; never posts to source "
    "systems; never amends operator-set limits; never sources "
    "market data; never mutates inputs."
)


# ════════════════════════════════════════════════════════════════════════
# Enums
# ════════════════════════════════════════════════════════════════════════

class LimitDimension(Enum):
    COUNTRY = "COUNTRY"
    COUNTERPARTY = "COUNTERPARTY"
    PRODUCT = "PRODUCT"
    TENOR = "TENOR"


class TenorBucket(Enum):
    """Tenor bucket by days-to-expiry from today."""
    SHORT = "SHORT"      # ≤ 90d
    MEDIUM = "MEDIUM"    # 91-180d
    LONG = "LONG"        # 181-365d
    EXTRA_LONG = "EXTRA_LONG"   # > 365d (special-approval)


class UtilizationSeverity(Enum):
    """Utilization severity by % of limit consumed."""
    HEALTHY = "HEALTHY"           # ≤ 70%
    ELEVATED = "ELEVATED"         # 70-85%
    HIGH = "HIGH"                 # 85-100%
    BREACH = "BREACH"             # > 100%


class PreDealOutcome(Enum):
    """Pre-deal check outcome — what would happen if proposed
    deal were added to current portfolio."""
    APPROVE_LIKELY = "APPROVE_LIKELY"   # post-deal HEALTHY
    REVIEW_NEEDED = "REVIEW_NEEDED"     # post-deal ELEVATED
    SENIOR_APPROVAL = "SENIOR_APPROVAL"  # post-deal HIGH
    BLOCK_RECOMMENDED = "BLOCK_RECOMMENDED"  # post-deal BREACH


# ════════════════════════════════════════════════════════════════════════
# Input dataclasses
# ════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class CountryLimit:
    country_code: str       # ISO-3166-alpha-2
    limit_kes: Decimal

    def __post_init__(self) -> None:
        if not self.country_code:
            raise ValueError("country_code must be non-empty")
        if self.limit_kes <= 0:
            raise ValueError("limit_kes must be > 0")


@dataclass(frozen=True)
class CounterpartyLimit:
    counterparty_id: str
    counterparty_name: str
    limit_kes: Decimal

    def __post_init__(self) -> None:
        if not self.counterparty_id:
            raise ValueError(
                "counterparty_id must be non-empty")
        if self.limit_kes <= 0:
            raise ValueError("limit_kes must be > 0")


@dataclass(frozen=True)
class ProductLimit:
    instrument_type: InstrumentType
    limit_kes: Decimal

    def __post_init__(self) -> None:
        if self.limit_kes <= 0:
            raise ValueError("limit_kes must be > 0")


@dataclass(frozen=True)
class TenorLimit:
    bucket: TenorBucket
    limit_kes: Decimal

    def __post_init__(self) -> None:
        if self.limit_kes <= 0:
            raise ValueError("limit_kes must be > 0")


@dataclass(frozen=True)
class CountryAttribution:
    """Maps applicant counterparty to country."""
    counterparty_id: str
    country_code: str

    def __post_init__(self) -> None:
        if not self.counterparty_id:
            raise ValueError(
                "counterparty_id must be non-empty")
        if not self.country_code:
            raise ValueError("country_code must be non-empty")


# ════════════════════════════════════════════════════════════════════════
# Output dataclasses
# ════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class LimitUtilization:
    dimension: LimitDimension
    bucket_key: str           # country code / cp id / product / tenor
    bucket_label: str         # human-readable
    exposure_kes: Decimal
    limit_kes: Decimal
    utilization_pct: Decimal
    headroom_kes: Decimal     # limit - exposure (negative if breached)
    severity: UtilizationSeverity
    contributing_instrument_ids: Tuple[str, ...]
    framework_refs: Tuple[str, ...] = ()


@dataclass(frozen=True)
class PreDealCheck:
    proposed_instrument_id: str
    pre_deal_utilization: Tuple[LimitUtilization, ...]
    post_deal_utilization: Tuple[LimitUtilization, ...]
    binding_dimension: Optional[LimitDimension]    # tightest
    outcome: PreDealOutcome
    description: str
    framework_refs: Tuple[str, ...] = ()


@dataclass(frozen=True)
class PortfolioLimitReport:
    as_of_date: str
    utilizations: Tuple[LimitUtilization, ...]
    by_severity: Dict[str, int]
    by_dimension: Dict[str, int]
    breached_count: int
    framework_refs: Tuple[str, ...]


# ════════════════════════════════════════════════════════════════════════
# Engine
# ════════════════════════════════════════════════════════════════════════

class TradeFinanceLimitsEngine:
    """Diagnostic limits + risk engine."""

    SHORT_TENOR_MAX_DAYS: int = 90
    MEDIUM_TENOR_MAX_DAYS: int = 180
    LONG_TENOR_MAX_DAYS: int = 365

    # Severity thresholds (% of limit)
    ELEVATED_THRESHOLD: Decimal = Decimal("0.70")
    HIGH_THRESHOLD: Decimal = Decimal("0.85")
    BREACH_THRESHOLD: Decimal = Decimal("1.00")

    # ── Helpers ───────────────────────────────────────────────────
    @staticmethod
    def _exposure_of(inst: TradeInstrument) -> Decimal:
        """Use undrawn + drawn (i.e., notional) for limit
        purposes. Drawn portion still consumes counterparty limit
        until repaid."""
        # Closed instruments don't consume limits
        if inst.state in (
            InstrumentState.EXPIRED,
            InstrumentState.CANCELLED,
            InstrumentState.REJECTED,
            InstrumentState.DRAWN,
        ):
            return Decimal("0")
        return inst.amount_kes

    @classmethod
    def _classify_tenor(
        cls, inst: TradeInstrument,
        as_of_date_iso: str,
    ) -> TenorBucket:
        from datetime import date
        as_of = date.fromisoformat(as_of_date_iso)
        days_to_expiry = (inst.expiry_date - as_of).days
        if days_to_expiry <= cls.SHORT_TENOR_MAX_DAYS:
            return TenorBucket.SHORT
        if days_to_expiry <= cls.MEDIUM_TENOR_MAX_DAYS:
            return TenorBucket.MEDIUM
        if days_to_expiry <= cls.LONG_TENOR_MAX_DAYS:
            return TenorBucket.LONG
        return TenorBucket.EXTRA_LONG

    @classmethod
    def _severity(
        cls, utilization_pct: Decimal,
    ) -> UtilizationSeverity:
        if utilization_pct > cls.BREACH_THRESHOLD:
            return UtilizationSeverity.BREACH
        if utilization_pct > cls.HIGH_THRESHOLD:
            return UtilizationSeverity.HIGH
        if utilization_pct > cls.ELEVATED_THRESHOLD:
            return UtilizationSeverity.ELEVATED
        return UtilizationSeverity.HEALTHY

    # ── Country dimension ─────────────────────────────────────────
    def compute_country_utilization(
        self,
        instruments: Sequence[TradeInstrument],
        country_limits: Sequence[CountryLimit],
        country_attributions: Sequence[CountryAttribution],
    ) -> Tuple[LimitUtilization, ...]:
        # Dimension opt-out: if no limits configured, return nothing.
        # Caller has chosen not to track this dimension.
        if not country_limits:
            return ()
        attr_by_cp: Dict[str, str] = {
            a.counterparty_id: a.country_code
            for a in country_attributions}
        # Aggregate exposure by country
        exposure_by_country: Dict[str, Decimal] = {}
        contributors_by_country: Dict[
            str, List[str]] = {}
        for inst in instruments:
            country = attr_by_cp.get(inst.beneficiary)
            if country is None:
                # Unattributed counterparty — surface as
                # finding under "UNKNOWN" pseudo-country
                country = "UNKNOWN"
            exp = self._exposure_of(inst)
            if exp > 0:
                exposure_by_country[country] = (
                    exposure_by_country.get(
                        country, Decimal("0")) + exp)
                contributors_by_country.setdefault(
                    country, []).append(inst.instrument_id)
        # Match against limits
        limit_by_country: Dict[str, Decimal] = {
            l.country_code: l.limit_kes for l in country_limits}
        outputs: List[LimitUtilization] = []
        # Include all limit-set countries (even zero exposure)
        # plus any countries with exposure but no limit
        all_countries = set(
            limit_by_country) | set(exposure_by_country)
        for country in sorted(all_countries):
            exposure = exposure_by_country.get(
                country, Decimal("0"))
            limit = limit_by_country.get(country)
            if limit is None:
                # No limit defined for country with exposure
                # — flag as BREACH with policy concern
                outputs.append(LimitUtilization(
                    dimension=LimitDimension.COUNTRY,
                    bucket_key=country,
                    bucket_label=f"country={country}",
                    exposure_kes=exposure,
                    limit_kes=Decimal("0"),
                    utilization_pct=Decimal("0"),
                    headroom_kes=-exposure,
                    severity=UtilizationSeverity.BREACH,
                    contributing_instrument_ids=tuple(
                        contributors_by_country.get(
                            country, [])),
                    framework_refs=(
                        "ENH-273 §country_limit",
                        f"No country limit defined for "
                        f"{country} but exposure exists — "
                        f"policy gap",)))
                continue
            utilization = (
                exposure / limit if limit > 0 else Decimal("0"))
            outputs.append(LimitUtilization(
                dimension=LimitDimension.COUNTRY,
                bucket_key=country,
                bucket_label=f"country={country}",
                exposure_kes=exposure,
                limit_kes=limit,
                utilization_pct=utilization,
                headroom_kes=limit - exposure,
                severity=self._severity(utilization),
                contributing_instrument_ids=tuple(
                    contributors_by_country.get(country, [])),
                framework_refs=(
                    "ENH-273 §country_limit",
                    "Basel — country/transfer risk concentration",
                )))
        return tuple(outputs)

    # ── Counterparty dimension ────────────────────────────────────
    def compute_counterparty_utilization(
        self,
        instruments: Sequence[TradeInstrument],
        counterparty_limits: Sequence[CounterpartyLimit],
    ) -> Tuple[LimitUtilization, ...]:
        if not counterparty_limits:
            return ()
        # Aggregate exposure by counterparty (use beneficiary
        # since that's who the bank is exposed to in trade
        # finance — applicant pays bank, bank pays beneficiary)
        # Distinct: in BG, applicant is the obligor, bank backs
        # beneficiary's claim. Limits should map to APPLICANT
        # (the bank's customer) — that's who'd default. Let's
        # use applicant for limit purposes.
        exposure_by_cp: Dict[str, Decimal] = {}
        contributors_by_cp: Dict[str, List[str]] = {}
        for inst in instruments:
            exp = self._exposure_of(inst)
            if exp <= 0:
                continue
            # Applicant carries the risk to the bank
            cp = inst.applicant
            exposure_by_cp[cp] = (
                exposure_by_cp.get(cp, Decimal("0")) + exp)
            contributors_by_cp.setdefault(
                cp, []).append(inst.instrument_id)
        limit_by_cp: Dict[str, Tuple[Decimal, str]] = {
            l.counterparty_id: (l.limit_kes, l.counterparty_name)
            for l in counterparty_limits}
        outputs: List[LimitUtilization] = []
        all_cps = set(limit_by_cp) | set(exposure_by_cp)
        for cp in sorted(all_cps):
            exposure = exposure_by_cp.get(cp, Decimal("0"))
            limit_tuple = limit_by_cp.get(cp)
            if limit_tuple is None:
                outputs.append(LimitUtilization(
                    dimension=LimitDimension.COUNTERPARTY,
                    bucket_key=cp,
                    bucket_label=f"counterparty={cp}",
                    exposure_kes=exposure,
                    limit_kes=Decimal("0"),
                    utilization_pct=Decimal("0"),
                    headroom_kes=-exposure,
                    severity=UtilizationSeverity.BREACH,
                    contributing_instrument_ids=tuple(
                        contributors_by_cp.get(cp, [])),
                    framework_refs=(
                        "ENH-273 §counterparty_limit",
                        f"No counterparty limit defined for "
                        f"{cp} — policy gap",)))
                continue
            limit, name = limit_tuple
            utilization = (
                exposure / limit if limit > 0 else Decimal("0"))
            outputs.append(LimitUtilization(
                dimension=LimitDimension.COUNTERPARTY,
                bucket_key=cp,
                bucket_label=f"counterparty={cp} ({name})",
                exposure_kes=exposure,
                limit_kes=limit,
                utilization_pct=utilization,
                headroom_kes=limit - exposure,
                severity=self._severity(utilization),
                contributing_instrument_ids=tuple(
                    contributors_by_cp.get(cp, [])),
                framework_refs=(
                    "ENH-273 §counterparty_limit",
                    "Basel — single-name concentration limit "
                    "(per-product, distinct from ENH-252 SBL "
                    "bank-wide aggregate)",
                )))
        return tuple(outputs)

    # ── Product dimension ─────────────────────────────────────────
    def compute_product_utilization(
        self,
        instruments: Sequence[TradeInstrument],
        product_limits: Sequence[ProductLimit],
    ) -> Tuple[LimitUtilization, ...]:
        if not product_limits:
            return ()
        exposure_by_product: Dict[
            InstrumentType, Decimal] = {}
        contributors_by_product: Dict[
            InstrumentType, List[str]] = {}
        for inst in instruments:
            exp = self._exposure_of(inst)
            if exp <= 0:
                continue
            exposure_by_product[inst.instrument_type] = (
                exposure_by_product.get(
                    inst.instrument_type, Decimal("0")) + exp)
            contributors_by_product.setdefault(
                inst.instrument_type, []).append(
                inst.instrument_id)
        limit_by_product: Dict[
            InstrumentType, Decimal] = {
            l.instrument_type: l.limit_kes
            for l in product_limits}
        outputs: List[LimitUtilization] = []
        all_products = (
            set(limit_by_product) | set(exposure_by_product))
        for product in sorted(
            all_products, key=lambda p: p.value
        ):
            exposure = exposure_by_product.get(
                product, Decimal("0"))
            limit = limit_by_product.get(product)
            if limit is None:
                # No limit defined for product with exposure
                outputs.append(LimitUtilization(
                    dimension=LimitDimension.PRODUCT,
                    bucket_key=product.value,
                    bucket_label=f"product={product.value}",
                    exposure_kes=exposure,
                    limit_kes=Decimal("0"),
                    utilization_pct=Decimal("0"),
                    headroom_kes=-exposure,
                    severity=UtilizationSeverity.BREACH,
                    contributing_instrument_ids=tuple(
                        contributors_by_product.get(
                            product, [])),
                    framework_refs=(
                        "ENH-273 §product_limit",
                        f"No product limit defined for "
                        f"{product.value} — policy gap",)))
                continue
            utilization = (
                exposure / limit if limit > 0 else Decimal("0"))
            outputs.append(LimitUtilization(
                dimension=LimitDimension.PRODUCT,
                bucket_key=product.value,
                bucket_label=f"product={product.value}",
                exposure_kes=exposure,
                limit_kes=limit,
                utilization_pct=utilization,
                headroom_kes=limit - exposure,
                severity=self._severity(utilization),
                contributing_instrument_ids=tuple(
                    contributors_by_product.get(product, [])),
                framework_refs=(
                    "ENH-273 §product_limit",
                    "Risk appetite — product concentration",)))
        return tuple(outputs)

    # ── Tenor dimension ───────────────────────────────────────────
    def compute_tenor_utilization(
        self,
        instruments: Sequence[TradeInstrument],
        tenor_limits: Sequence[TenorLimit],
        as_of_date_iso: str,
    ) -> Tuple[LimitUtilization, ...]:
        if not tenor_limits:
            return ()
        exposure_by_bucket: Dict[
            TenorBucket, Decimal] = {}
        contributors_by_bucket: Dict[
            TenorBucket, List[str]] = {}
        for inst in instruments:
            exp = self._exposure_of(inst)
            if exp <= 0:
                continue
            bucket = self._classify_tenor(
                inst, as_of_date_iso)
            exposure_by_bucket[bucket] = (
                exposure_by_bucket.get(
                    bucket, Decimal("0")) + exp)
            contributors_by_bucket.setdefault(
                bucket, []).append(inst.instrument_id)
        limit_by_bucket: Dict[TenorBucket, Decimal] = {
            l.bucket: l.limit_kes for l in tenor_limits}
        outputs: List[LimitUtilization] = []
        for bucket in TenorBucket:
            exposure = exposure_by_bucket.get(
                bucket, Decimal("0"))
            limit = limit_by_bucket.get(bucket)
            if limit is None and exposure == 0:
                continue
            if limit is None:
                outputs.append(LimitUtilization(
                    dimension=LimitDimension.TENOR,
                    bucket_key=bucket.value,
                    bucket_label=f"tenor={bucket.value}",
                    exposure_kes=exposure,
                    limit_kes=Decimal("0"),
                    utilization_pct=Decimal("0"),
                    headroom_kes=-exposure,
                    severity=UtilizationSeverity.BREACH,
                    contributing_instrument_ids=tuple(
                        contributors_by_bucket.get(
                            bucket, [])),
                    framework_refs=(
                        "ENH-273 §tenor_limit",
                        f"No tenor limit defined for "
                        f"{bucket.value} — policy gap",)))
                continue
            utilization = (
                exposure / limit if limit > 0 else Decimal("0"))
            outputs.append(LimitUtilization(
                dimension=LimitDimension.TENOR,
                bucket_key=bucket.value,
                bucket_label=f"tenor={bucket.value}",
                exposure_kes=exposure,
                limit_kes=limit,
                utilization_pct=utilization,
                headroom_kes=limit - exposure,
                severity=self._severity(utilization),
                contributing_instrument_ids=tuple(
                    contributors_by_bucket.get(bucket, [])),
                framework_refs=(
                    "ENH-273 §tenor_limit",
                    "Liquidity profile — tenor concentration; "
                    "long-tenor exposure worsens stress "
                    "metrics",)))
        return tuple(outputs)

    # ── Pre-deal check ────────────────────────────────────────────
    def check_pre_deal(
        self,
        proposed_instrument: TradeInstrument,
        existing_instruments: Sequence[TradeInstrument],
        country_limits: Sequence[CountryLimit] = (),
        counterparty_limits: Sequence[
            CounterpartyLimit] = (),
        product_limits: Sequence[ProductLimit] = (),
        tenor_limits: Sequence[TenorLimit] = (),
        country_attributions: Sequence[
            CountryAttribution] = (),
        as_of_date_iso: str = "2026-04-15",
    ) -> PreDealCheck:
        # Pre-deal utilization (without proposed)
        pre = (
            self.compute_country_utilization(
                existing_instruments,
                country_limits, country_attributions)
            + self.compute_counterparty_utilization(
                existing_instruments, counterparty_limits)
            + self.compute_product_utilization(
                existing_instruments, product_limits)
            + self.compute_tenor_utilization(
                existing_instruments, tenor_limits,
                as_of_date_iso))
        # Post-deal utilization (with proposed added)
        post_portfolio = tuple(
            existing_instruments) + (proposed_instrument,)
        post = (
            self.compute_country_utilization(
                post_portfolio,
                country_limits, country_attributions)
            + self.compute_counterparty_utilization(
                post_portfolio, counterparty_limits)
            + self.compute_product_utilization(
                post_portfolio, product_limits)
            + self.compute_tenor_utilization(
                post_portfolio, tenor_limits,
                as_of_date_iso))
        # Identify binding dimension — worst severity in post
        # that involves the proposed instrument
        affected_post = [
            u for u in post
            if proposed_instrument.instrument_id
            in u.contributing_instrument_ids]
        if not affected_post:
            outcome = PreDealOutcome.APPROVE_LIKELY
            binding = None
            description = (
                f"proposed {proposed_instrument.instrument_id} "
                f"does not appear in any limit dimension — "
                f"likely no limits configured; review")
        else:
            severity_rank = {
                UtilizationSeverity.HEALTHY: 0,
                UtilizationSeverity.ELEVATED: 1,
                UtilizationSeverity.HIGH: 2,
                UtilizationSeverity.BREACH: 3}
            worst = max(
                affected_post, key=lambda u: severity_rank[
                    u.severity])
            binding = worst.dimension
            if worst.severity == UtilizationSeverity.BREACH:
                outcome = PreDealOutcome.BLOCK_RECOMMENDED
            elif worst.severity == UtilizationSeverity.HIGH:
                outcome = PreDealOutcome.SENIOR_APPROVAL
            elif worst.severity == UtilizationSeverity.ELEVATED:
                outcome = PreDealOutcome.REVIEW_NEEDED
            else:
                outcome = PreDealOutcome.APPROVE_LIKELY
            description = (
                f"proposed deal post-allocation: "
                f"{worst.bucket_label} → "
                f"{worst.severity.value} "
                f"(util "
                f"{worst.utilization_pct.quantize(Decimal('0.001'))}, "
                f"headroom {worst.headroom_kes}); binding "
                f"dimension {binding.value}")
        return PreDealCheck(
            proposed_instrument_id=(
                proposed_instrument.instrument_id),
            pre_deal_utilization=pre,
            post_deal_utilization=post,
            binding_dimension=binding,
            outcome=outcome,
            description=description,
            framework_refs=(
                "ENH-273 §check_pre_deal",
                "Per Rule 7 — surfaces outcome recommendation; "
                "operator approves or rejects; engine never "
                "blocks deals automatically",
            ),
        )

    # ── Portfolio report ─────────────────────────────────────────
    def build_portfolio_report(
        self,
        instruments: Sequence[TradeInstrument],
        country_limits: Sequence[CountryLimit] = (),
        counterparty_limits: Sequence[
            CounterpartyLimit] = (),
        product_limits: Sequence[ProductLimit] = (),
        tenor_limits: Sequence[TenorLimit] = (),
        country_attributions: Sequence[
            CountryAttribution] = (),
        as_of_date_iso: str = "2026-04-15",
    ) -> PortfolioLimitReport:
        utils = (
            self.compute_country_utilization(
                instruments, country_limits,
                country_attributions)
            + self.compute_counterparty_utilization(
                instruments, counterparty_limits)
            + self.compute_product_utilization(
                instruments, product_limits)
            + self.compute_tenor_utilization(
                instruments, tenor_limits, as_of_date_iso))
        by_severity: Dict[str, int] = {
            s.value: 0 for s in UtilizationSeverity}
        by_dimension: Dict[str, int] = {
            d.value: 0 for d in LimitDimension}
        breached = 0
        for u in utils:
            by_severity[u.severity.value] += 1
            by_dimension[u.dimension.value] += 1
            if u.severity == UtilizationSeverity.BREACH:
                breached += 1
        return PortfolioLimitReport(
            as_of_date=as_of_date_iso,
            utilizations=tuple(utils),
            by_severity=by_severity,
            by_dimension=by_dimension,
            breached_count=breached,
            framework_refs=(
                "ENH-273 §build_portfolio_report",
                "4-dimensional limit framework: country / "
                "counterparty / product / tenor",
                "Per Rule 7 — never amends operator-set "
                "limits; never auto-rebalances portfolio",
            ),
        )


# ════════════════════════════════════════════════════════════════════════
# Self-tests
# ════════════════════════════════════════════════════════════════════════

def _make_lc_for_limits(
    iid="LC-LIM-1",
    applicant="Acme Imports Ltd",
    beneficiary="Shanghai Steel",
    amount=Decimal("10000000"),
    expiry_iso="2026-08-01",
):
    from datetime import date as _d
    from utils.trade_finance_instruments import (
        TradeInstrument, InstrumentType, InstrumentState,
        LcType)
    return TradeInstrument(
        instrument_id=iid,
        instrument_type=InstrumentType.LC,
        state=InstrumentState.ACTIVE,
        applicant=applicant,
        beneficiary=beneficiary,
        issuing_bank="Ecobank Kenya",
        advising_bank="ABC Bank",
        amount_kes=amount,
        currency="KES",
        issue_date=_d(2026, 4, 1),
        expiry_date=_d.fromisoformat(expiry_iso),
        tenor_days=0, lc_type=LcType.SIGHT,
        incoterms="CIF Mombasa",
        description_of_goods="goods")


def _test_country_limit_validates_inputs():
    try:
        CountryLimit(country_code="", limit_kes=Decimal("1"))
        assert False
    except ValueError:
        pass
    try:
        CountryLimit(country_code="KE", limit_kes=Decimal("0"))
        assert False
    except ValueError:
        pass


def _test_counterparty_limit_validates_inputs():
    try:
        CounterpartyLimit(
            counterparty_id="", counterparty_name="X",
            limit_kes=Decimal("1"))
        assert False
    except ValueError:
        pass


def _test_product_limit_validates_amount():
    try:
        ProductLimit(
            instrument_type=InstrumentType.LC,
            limit_kes=Decimal("0"))
        assert False
    except ValueError:
        pass


def _test_country_utilization_basic():
    eng = TradeFinanceLimitsEngine()
    insts = (
        _make_lc_for_limits(
            iid="L1", beneficiary="ChineseCorp",
            amount=Decimal("3000000")),
        _make_lc_for_limits(
            iid="L2", beneficiary="ChineseCorp",
            amount=Decimal("2000000")),
        _make_lc_for_limits(
            iid="L3", beneficiary="GermanCorp",
            amount=Decimal("8000000")),
    )
    limits = (
        CountryLimit(
            country_code="CN", limit_kes=Decimal("10000000")),
        CountryLimit(
            country_code="DE", limit_kes=Decimal("10000000")),
    )
    attrs = (
        CountryAttribution(
            counterparty_id="ChineseCorp", country_code="CN"),
        CountryAttribution(
            counterparty_id="GermanCorp", country_code="DE"),
    )
    utils = eng.compute_country_utilization(
        insts, limits, attrs)
    by_country = {u.bucket_key: u for u in utils}
    assert by_country["CN"].exposure_kes == Decimal("5000000")
    assert by_country["CN"].utilization_pct == Decimal("0.5")
    assert by_country["DE"].exposure_kes == Decimal("8000000")
    assert by_country["DE"].utilization_pct == Decimal("0.8")
    assert by_country["DE"].severity == (
        UtilizationSeverity.ELEVATED)


def _test_country_no_limit_for_exposure_breach():
    eng = TradeFinanceLimitsEngine()
    insts = (
        _make_lc_for_limits(
            iid="L1", beneficiary="UnknownCorp"),
    )
    # Limits configured for KE only — but exposure is to ZZ
    # → policy gap surfaced as BREACH for ZZ
    limits = (
        CountryLimit(
            country_code="KE", limit_kes=Decimal("100000000")),
    )
    attrs = (
        CountryAttribution(
            counterparty_id="UnknownCorp", country_code="ZZ"),
    )
    utils = eng.compute_country_utilization(
        insts, limits, attrs)
    # Should have ZZ (policy gap = BREACH) and KE (no exposure)
    zz = next(
        (u for u in utils if u.bucket_key == "ZZ"), None)
    assert zz is not None
    assert zz.severity == UtilizationSeverity.BREACH
    assert any(
        "policy gap" in r for r in zz.framework_refs)


def _test_counterparty_aggregation_uses_applicant():
    eng = TradeFinanceLimitsEngine()
    # Same applicant across 2 LCs
    insts = (
        _make_lc_for_limits(
            iid="L1",
            applicant="MegaCorp",
            beneficiary="A Corp",
            amount=Decimal("4000000")),
        _make_lc_for_limits(
            iid="L2",
            applicant="MegaCorp",
            beneficiary="B Corp",
            amount=Decimal("3000000")),
    )
    limits = (
        CounterpartyLimit(
            counterparty_id="MegaCorp",
            counterparty_name="MegaCorp",
            limit_kes=Decimal("10000000")),
    )
    utils = eng.compute_counterparty_utilization(
        insts, limits)
    mega = next(
        u for u in utils
        if u.bucket_key == "MegaCorp")
    assert mega.exposure_kes == Decimal("7000000")
    assert mega.utilization_pct == Decimal("0.7")
    assert mega.severity == UtilizationSeverity.HEALTHY


def _test_severity_thresholds():
    eng = TradeFinanceLimitsEngine()
    assert eng._severity(Decimal("0.5")) == (
        UtilizationSeverity.HEALTHY)
    assert eng._severity(Decimal("0.71")) == (
        UtilizationSeverity.ELEVATED)
    assert eng._severity(Decimal("0.86")) == (
        UtilizationSeverity.HIGH)
    assert eng._severity(Decimal("1.01")) == (
        UtilizationSeverity.BREACH)
    # Boundary values: exactly at threshold = previous severity
    assert eng._severity(Decimal("0.70")) == (
        UtilizationSeverity.HEALTHY)
    assert eng._severity(Decimal("0.85")) == (
        UtilizationSeverity.ELEVATED)
    assert eng._severity(Decimal("1.00")) == (
        UtilizationSeverity.HIGH)


def _test_product_utilization():
    eng = TradeFinanceLimitsEngine()
    insts = (
        _make_lc_for_limits(
            iid="L1", amount=Decimal("5000000")),
        _make_lc_for_limits(
            iid="L2", amount=Decimal("4000000")),
    )
    limits = (
        ProductLimit(
            instrument_type=InstrumentType.LC,
            limit_kes=Decimal("10000000")),
    )
    utils = eng.compute_product_utilization(insts, limits)
    lc_util = next(
        u for u in utils
        if u.bucket_key == InstrumentType.LC.value)
    assert lc_util.exposure_kes == Decimal("9000000")
    assert lc_util.utilization_pct == Decimal("0.9")
    assert lc_util.severity == UtilizationSeverity.HIGH


def _test_tenor_classification():
    eng = TradeFinanceLimitsEngine()
    short = _make_lc_for_limits(
        expiry_iso="2026-05-01")    # 16d after 4/15
    medium = _make_lc_for_limits(
        expiry_iso="2026-08-01")    # 108d
    long_ = _make_lc_for_limits(
        expiry_iso="2026-12-01")    # 230d
    extra = _make_lc_for_limits(
        expiry_iso="2027-08-01")    # 473d
    assert eng._classify_tenor(short, "2026-04-15") == (
        TenorBucket.SHORT)
    assert eng._classify_tenor(medium, "2026-04-15") == (
        TenorBucket.MEDIUM)
    assert eng._classify_tenor(long_, "2026-04-15") == (
        TenorBucket.LONG)
    assert eng._classify_tenor(extra, "2026-04-15") == (
        TenorBucket.EXTRA_LONG)


def _test_closed_instruments_excluded_from_exposure():
    eng = TradeFinanceLimitsEngine()
    from utils.trade_finance_instruments import InstrumentState
    insts = (
        _make_lc_for_limits(
            iid="L_ACTIVE", amount=Decimal("5000000")),
    )
    # Mutate a copy via dataclasses.replace
    from dataclasses import replace
    expired = replace(
        insts[0], instrument_id="L_EXP",
        state=InstrumentState.EXPIRED)
    insts2 = insts + (expired,)
    limits = (
        ProductLimit(
            instrument_type=InstrumentType.LC,
            limit_kes=Decimal("10000000")),
    )
    utils = eng.compute_product_utilization(insts2, limits)
    lc_util = next(
        u for u in utils
        if u.bucket_key == InstrumentType.LC.value)
    # Only ACTIVE counted
    assert lc_util.exposure_kes == Decimal("5000000")
    # Only L_ACTIVE in contributors
    assert lc_util.contributing_instrument_ids == ("L_ACTIVE",)


def _test_pre_deal_block_when_breached():
    eng = TradeFinanceLimitsEngine()
    proposed = _make_lc_for_limits(
        iid="PROPOSED",
        applicant="MegaCorp",
        amount=Decimal("5000000"))
    existing = (
        _make_lc_for_limits(
            iid="EX1",
            applicant="MegaCorp",
            amount=Decimal("8000000")),
    )
    limits = (
        CounterpartyLimit(
            counterparty_id="MegaCorp",
            counterparty_name="MegaCorp",
            limit_kes=Decimal("10000000")),
    )
    check = eng.check_pre_deal(
        proposed, existing,
        counterparty_limits=limits)
    # 8m existing + 5m proposed = 13m vs 10m limit → BREACH
    assert check.outcome == PreDealOutcome.BLOCK_RECOMMENDED
    assert check.binding_dimension == (
        LimitDimension.COUNTERPARTY)


def _test_pre_deal_review_when_elevated():
    eng = TradeFinanceLimitsEngine()
    proposed = _make_lc_for_limits(
        iid="PROPOSED",
        applicant="MegaCorp",
        amount=Decimal("3000000"))
    existing = (
        _make_lc_for_limits(
            iid="EX1",
            applicant="MegaCorp",
            amount=Decimal("5000000")),
    )
    limits = (
        CounterpartyLimit(
            counterparty_id="MegaCorp",
            counterparty_name="MegaCorp",
            limit_kes=Decimal("10000000")),
    )
    check = eng.check_pre_deal(
        proposed, existing,
        counterparty_limits=limits)
    # 5m + 3m = 8m vs 10m = 80% → ELEVATED → REVIEW_NEEDED
    assert check.outcome == PreDealOutcome.REVIEW_NEEDED


def _test_pre_deal_approve_when_healthy():
    eng = TradeFinanceLimitsEngine()
    proposed = _make_lc_for_limits(
        iid="PROPOSED",
        applicant="MegaCorp",
        amount=Decimal("1000000"))
    limits = (
        CounterpartyLimit(
            counterparty_id="MegaCorp",
            counterparty_name="MegaCorp",
            limit_kes=Decimal("10000000")),
    )
    check = eng.check_pre_deal(
        proposed, (), counterparty_limits=limits)
    # 1m / 10m = 10% → HEALTHY → APPROVE_LIKELY
    assert check.outcome == PreDealOutcome.APPROVE_LIKELY


def _test_portfolio_report_aggregates():
    eng = TradeFinanceLimitsEngine()
    insts = (
        _make_lc_for_limits(
            iid="L1", applicant="A", amount=Decimal("5000000")),
        _make_lc_for_limits(
            iid="L2", applicant="A", amount=Decimal("6000000")),
    )
    cp_limits = (
        CounterpartyLimit(
            counterparty_id="A", counterparty_name="A",
            limit_kes=Decimal("10000000")),
    )
    report = eng.build_portfolio_report(
        insts, counterparty_limits=cp_limits)
    # 11m vs 10m → BREACH
    assert report.breached_count >= 1
    assert any(
        "ENH-273" in r for r in report.framework_refs)


def _test_engine_does_not_mutate_inputs():
    eng = TradeFinanceLimitsEngine()
    inst = _make_lc_for_limits(amount=Decimal("1000000"))
    limit = ProductLimit(
        instrument_type=InstrumentType.LC,
        limit_kes=Decimal("10000000"))
    eng.compute_product_utilization((inst,), (limit,))
    assert inst.amount_kes == Decimal("1000000")
    assert limit.limit_kes == Decimal("10000000")


def _test_full_provenance():
    eng = TradeFinanceLimitsEngine()
    inst = _make_lc_for_limits()
    limits = (
        ProductLimit(
            instrument_type=InstrumentType.LC,
            limit_kes=Decimal("100000000")),
    )
    utils = eng.compute_product_utilization((inst,), limits)
    u = utils[0]
    assert u.dimension == LimitDimension.PRODUCT
    assert "LC-LIM-1" in u.contributing_instrument_ids
    assert any("ENH-273" in r for r in u.framework_refs)


def self_test() -> None:
    tests = [
        _test_country_limit_validates_inputs,
        _test_counterparty_limit_validates_inputs,
        _test_product_limit_validates_amount,
        _test_country_utilization_basic,
        _test_country_no_limit_for_exposure_breach,
        _test_counterparty_aggregation_uses_applicant,
        _test_severity_thresholds,
        _test_product_utilization,
        _test_tenor_classification,
        _test_closed_instruments_excluded_from_exposure,
        _test_pre_deal_block_when_breached,
        _test_pre_deal_review_when_elevated,
        _test_pre_deal_approve_when_healthy,
        _test_portfolio_report_aggregates,
        _test_engine_does_not_mutate_inputs,
        _test_full_provenance,
    ]
    failed = []
    for t in tests:
        try:
            t()
        except AssertionError as e:
            failed.append((t.__name__, str(e)))
        except Exception as e:
            failed.append(
                (t.__name__, f"{type(e).__name__}: {e}"))
    if failed:
        print(
            f"✗ trade_finance_limits self-test: "
            f"{len(failed)} failures",
            file=sys.stderr)
        for name, msg in failed:
            print(f"  - {name}: {msg}", file=sys.stderr)
        raise SystemExit(1)
    print(
        f"✓ trade_finance_limits self-test passed "
        f"({len(tests)} tests)")


if __name__ == "__main__":
    self_test()
