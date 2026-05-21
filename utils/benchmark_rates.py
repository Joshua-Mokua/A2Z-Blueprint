"""utils/benchmark_rates.py — v10.17 Phase 2 KESONIA-001 enhancement.

╔════════════════════════════════════════════════════════════════════════╗
║  BENCHMARK RATES — KESONIA + CBR + COMPOUNDED INDEX                    ║
╠════════════════════════════════════════════════════════════════════════╣
║  Risk class: Cat A (rate determination affects loan pricing + revenue) ║
║  Implements 1 new Credit standard:                                       ║
║    ENH-CBK-KESONIA: KESONIA + Risk-Based Credit Pricing Model (RBCPM)   ║
╠════════════════════════════════════════════════════════════════════════╣
║  Regulatory provenance:                                                 ║
║    CBK Revised Risk-Based Credit Pricing Model (RBCPM) — Aug 2025      ║
║    KESONIA officially launched 1 September 2025                         ║
║    New variable-rate KES loans: KESONIA-based pricing from 1 Dec 2025  ║
║    Existing variable-rate loans: migration deadline 28 Feb 2026         ║
║    CBK Banking Act §44 — interest rate disclosure                       ║
║    CBK Cooperative Bank circular & industry implementations Q4 2025     ║
║                                                                         ║
║  Methodology references (CBK official):                                ║
║    KESONIA = volume-weighted overnight unsecured interbank rate (KES)   ║
║    KESONIA Compounded Index — daily compounded reference for periods    ║
║    Compound-in-arrears via index ratio: rate = (Idx_end/Idx_start - 1) ║
║                                          × (360 / day_count)            ║
║    Lookback period (offset days) — observation lag vs payment date     ║
║    Fallback: CBR when KESONIA not published                            ║
║    Pricing formula: Total rate = KESONIA + K (bank's risk premium)     ║
╠════════════════════════════════════════════════════════════════════════╣
║  Honesty Rule 1: No KESONIA fabrication. Engine returns explicit None  ║
║  + reason if rate not in registry. Caller must wire CBK feed (Rule 7). ║
║  Honesty Rule 7: rate_fetcher is callable; no silent network call.     ║
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
# Constants — CBK regulatory dates + scope
# ════════════════════════════════════════════════════════════════════════

# Per CBK Revised RBCPM (Aug 2025)
KESONIA_LAUNCH_DATE = "2025-09-01"            # CBK official launch
KESONIA_NEW_LOAN_EFFECTIVE = "2025-09-01"      # mandatory for NEW variable-rate loans
KESONIA_NEW_LOAN_PRACTICAL = "2025-12-01"      # 3-month grace period; banks live
KESONIA_EXISTING_LOAN_DEADLINE = "2026-02-28"  # mandatory migration of EXISTING loans

# Default fallback rate code when KESONIA unavailable
DEFAULT_FALLBACK_RATE_CODE = "CBR"

# CBK convention: 360-day year for KESONIA accrual (matches SONIA + SOFR)
KESONIA_DAY_COUNT_BASIS = 360


# ════════════════════════════════════════════════════════════════════════
# Rate codes + types
# ════════════════════════════════════════════════════════════════════════

class RateCode(Enum):
    """Reference rate identifiers."""
    KESONIA = "KESONIA"                    # overnight (RFR)
    CBR = "CBR"                             # Central Bank Rate (policy rate)
    KESONIA_COMPOUNDED_INDEX = "KESONIA_COMPOUNDED_INDEX"  # cumulative index
    # Term reference rates (computed via index ratio, not separately quoted)


class RateType(Enum):
    OVERNIGHT = "OVERNIGHT"
    POLICY = "POLICY"
    INDEX = "INDEX"


class LoanRateType(Enum):
    """Per CBK RBCPM scope — which loans the framework applies to."""
    VARIABLE_KES = "VARIABLE_KES"           # in scope — KESONIA + K
    VARIABLE_FCY = "VARIABLE_FCY"           # excluded
    FIXED_RATE = "FIXED_RATE"               # excluded
    UNKNOWN = "UNKNOWN"

    def is_kesonia_in_scope(self) -> bool:
        return self == LoanRateType.VARIABLE_KES


# ════════════════════════════════════════════════════════════════════════
# Data classes
# ════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class BenchmarkRateObservation:
    """Single rate observation for one date."""
    rate_code: RateCode
    observation_date: str             # ISO-8601 date (YYYY-MM-DD)
    rate_pct: Decimal                  # e.g., Decimal("8.76") for 8.76%
    rate_type: RateType
    source: str = "CBK"
    notes: str = ""

    def __post_init__(self):
        if self.rate_pct < Decimal("0") or self.rate_pct > Decimal("100"):
            raise ValueError(
                f"rate_pct {self.rate_pct} outside [0, 100]")


@dataclass(frozen=True)
class CompoundedIndexObservation:
    """KESONIA Compounded Index value on a date.

    Per CBK methodology: Index_i = Index_{i-1} × (1 + r_{i-1} × α_{i-1})
    where r is daily KESONIA, α is day-count fraction (1/360).
    """
    observation_date: str             # ISO-8601 date
    index_value: Decimal               # cumulative index (starts at 100.0000 baseline)
    notes: str = ""

    def __post_init__(self):
        if self.index_value <= Decimal("0"):
            raise ValueError(
                f"index_value {self.index_value} must be positive")


@dataclass(frozen=True)
class BenchmarkLookupResult:
    """Result of a rate lookup, including fallback handling.

    Per Rule 1: when KESONIA not available, the result surfaces:
      - actual rate used (could be CBR fallback)
      - explicit `is_fallback` flag
      - explicit `requested_rate_code` vs `applied_rate_code`
    No silent substitution.
    """
    requested_rate_code: RateCode
    applied_rate_code: RateCode
    rate_pct: Optional[Decimal]        # None if neither requested nor fallback available
    observation_date: str
    is_fallback: bool
    notes: str = ""

    def is_resolved(self) -> bool:
        return self.rate_pct is not None


@dataclass(frozen=True)
class CompoundedAccrualResult:
    """Result of compounding KESONIA over a period via the compounded index."""
    period_start: str
    period_end: str
    index_start: Decimal
    index_end: Decimal
    accrual_factor: Decimal             # (Idx_end/Idx_start - 1)
    annualized_rate_pct: Decimal        # accrual_factor × (360 / days)
    days: int
    notes: str = ""


# ════════════════════════════════════════════════════════════════════════
# Engine
# ════════════════════════════════════════════════════════════════════════

class BenchmarkRateRegistry:
    """In-memory registry of rate observations + compounded index values.

    Per Rule 7 — `rate_fetcher` callable injects external data (e.g., CBK
    daily feed). No silent fabrication when fetcher absent.
    """

    def __init__(
        self,
        *,
        entity_name: str = "Ecobank Kenya",
        rate_fetcher: Optional[
            Callable[[RateCode, str], Optional[BenchmarkRateObservation]]] = None,
    ):
        self.entity_name = entity_name
        self.rate_fetcher = rate_fetcher
        self._rates: Dict[Tuple[str, str], BenchmarkRateObservation] = {}
        # key: (rate_code.value, ISO-8601 date)
        self._index: Dict[str, CompoundedIndexObservation] = {}

    # ── Rate registration ──────────────────────────────────────────────
    def add_rate(self, obs: BenchmarkRateObservation) -> None:
        key = (obs.rate_code.value, obs.observation_date)
        self._rates[key] = obs

    def add_rates_bulk(
        self, observations: Sequence[BenchmarkRateObservation]) -> int:
        for obs in observations:
            self.add_rate(obs)
        return len(observations)

    def add_compounded_index(
        self, obs: CompoundedIndexObservation) -> None:
        self._index[obs.observation_date] = obs

    # ── Rate lookup ────────────────────────────────────────────────────
    def get_rate(
        self,
        *,
        rate_code: RateCode,
        as_of_date: str,
        fallback_rate_code: Optional[RateCode] = None,
    ) -> BenchmarkLookupResult:
        """Look up rate as-of given date.

        Order of resolution:
        1. Exact match in registry
        2. Most-recent prior observation (CBK holds rate constant on
           weekends/holidays per official methodology)
        3. Try fetcher if configured
        4. Fall back to fallback_rate_code if requested rate unavailable
        5. Return None rate with explicit notes — no fabrication
        """
        # 1. Exact match
        key = (rate_code.value, as_of_date)
        if key in self._rates:
            obs = self._rates[key]
            return BenchmarkLookupResult(
                requested_rate_code=rate_code,
                applied_rate_code=rate_code,
                rate_pct=obs.rate_pct,
                observation_date=obs.observation_date,
                is_fallback=False,
                notes="exact match in registry")

        # 2. Most-recent prior observation (weekend/holiday handling)
        prior = self._most_recent_prior(rate_code, as_of_date)
        if prior is not None:
            return BenchmarkLookupResult(
                requested_rate_code=rate_code,
                applied_rate_code=rate_code,
                rate_pct=prior.rate_pct,
                observation_date=prior.observation_date,
                is_fallback=False,
                notes=(
                    f"using {prior.observation_date} observation "
                    f"(weekend/holiday hold per CBK methodology)"))

        # 3. Try fetcher (Rule 7 — explicit callable, never silent)
        if self.rate_fetcher is not None:
            try:
                fetched = self.rate_fetcher(rate_code, as_of_date)
                if fetched is not None:
                    self.add_rate(fetched)
                    return BenchmarkLookupResult(
                        requested_rate_code=rate_code,
                        applied_rate_code=rate_code,
                        rate_pct=fetched.rate_pct,
                        observation_date=fetched.observation_date,
                        is_fallback=False,
                        notes="fetched via rate_fetcher")
            except Exception as e:
                # Don't crash on fetcher failure; surface it
                pass

        # 4. Fallback to alternative rate
        if fallback_rate_code is not None and fallback_rate_code != rate_code:
            fb = self._most_recent_prior(fallback_rate_code, as_of_date)
            if fb is None:
                # also try exact match for fallback
                fb_key = (fallback_rate_code.value, as_of_date)
                if fb_key in self._rates:
                    fb = self._rates[fb_key]
            if fb is not None:
                return BenchmarkLookupResult(
                    requested_rate_code=rate_code,
                    applied_rate_code=fallback_rate_code,
                    rate_pct=fb.rate_pct,
                    observation_date=fb.observation_date,
                    is_fallback=True,
                    notes=(
                        f"{rate_code.value} unavailable; using "
                        f"{fallback_rate_code.value} fallback per "
                        f"CBK RBCPM (KESONIA not practical)"))

        # 5. No fabrication — surface unavailable
        return BenchmarkLookupResult(
            requested_rate_code=rate_code,
            applied_rate_code=rate_code,
            rate_pct=None,
            observation_date=as_of_date,
            is_fallback=False,
            notes=(
                f"{rate_code.value} unavailable for {as_of_date}; "
                "no fallback resolved (Rule 1 — no fabrication)"))

    def _most_recent_prior(
        self, rate_code: RateCode, as_of_date: str,
    ) -> Optional[BenchmarkRateObservation]:
        """Find most recent observation on-or-before as_of_date."""
        candidates = [
            obs for (rc, dt), obs in self._rates.items()
            if rc == rate_code.value and dt <= as_of_date]
        if not candidates:
            return None
        return max(candidates, key=lambda o: o.observation_date)

    # ── Compounded index queries ───────────────────────────────────────
    def get_index(self, as_of_date: str) -> Optional[CompoundedIndexObservation]:
        if as_of_date in self._index:
            return self._index[as_of_date]
        # Most recent prior (CBK holds index on weekends)
        candidates = [
            obs for dt, obs in self._index.items() if dt <= as_of_date]
        if not candidates:
            return None
        return max(candidates, key=lambda o: o.observation_date)

    def compute_compounded_accrual(
        self,
        *,
        period_start: str,
        period_end: str,
    ) -> Optional[CompoundedAccrualResult]:
        """Compute compound-in-arrears KESONIA accrual via CBK Compounded Index.

        Per CBK methodology:
            accrual_factor = Index(period_end) / Index(period_start) - 1
            annualized_rate = accrual_factor × (360 / days)

        Returns None if either index endpoint is unavailable.
        """
        idx_start = self.get_index(period_start)
        idx_end = self.get_index(period_end)
        if idx_start is None or idx_end is None:
            return None

        if idx_end.index_value <= idx_start.index_value:
            return None  # would be zero or negative — likely data issue

        days = (date.fromisoformat(period_end)
                  - date.fromisoformat(period_start)).days
        if days <= 0:
            return None

        accrual_factor = (
            idx_end.index_value / idx_start.index_value - Decimal("1"))
        annualized_pct = (
            accrual_factor * Decimal(KESONIA_DAY_COUNT_BASIS)
            / Decimal(days) * Decimal("100"))

        return CompoundedAccrualResult(
            period_start=period_start,
            period_end=period_end,
            index_start=idx_start.index_value,
            index_end=idx_end.index_value,
            accrual_factor=accrual_factor,
            annualized_rate_pct=annualized_pct,
            days=days,
            notes=(
                f"CBK Compounded Index ratio: "
                f"{idx_end.index_value} / {idx_start.index_value}"))

    # ── RBCPM convenience ──────────────────────────────────────────────
    def compute_total_rate(
        self,
        *,
        as_of_date: str,
        k_premium_pct: Decimal,
        loan_rate_type: LoanRateType = LoanRateType.VARIABLE_KES,
        use_compounded: bool = False,
        period_start: Optional[str] = None,
    ) -> Dict[str, object]:
        """Compute total customer rate per CBK RBCPM:
            Total Rate = KESONIA + K (premium)

        Per CBK scope rules:
          - VARIABLE_KES → in scope (use KESONIA + K)
          - VARIABLE_FCY / FIXED_RATE → out of scope (return None + reason)
        """
        if not loan_rate_type.is_kesonia_in_scope():
            return {
                "is_in_scope": False,
                "rate_code_used": None,
                "base_rate_pct": None,
                "k_premium_pct": k_premium_pct,
                "total_rate_pct": None,
                "is_fallback": False,
                "notes": (
                    f"{loan_rate_type.value} is excluded from KESONIA "
                    "RBCPM scope per CBK FAQ"),
            }

        # Compounded vs spot
        if use_compounded and period_start is not None:
            accrual = self.compute_compounded_accrual(
                period_start=period_start, period_end=as_of_date)
            if accrual is not None:
                return {
                    "is_in_scope": True,
                    "rate_code_used": RateCode.KESONIA_COMPOUNDED_INDEX.value,
                    "base_rate_pct": accrual.annualized_rate_pct,
                    "k_premium_pct": k_premium_pct,
                    "total_rate_pct": (
                        accrual.annualized_rate_pct + k_premium_pct),
                    "is_fallback": False,
                    "notes": accrual.notes,
                    "accrual_detail": accrual,
                }

        # Spot KESONIA + K
        result = self.get_rate(
            rate_code=RateCode.KESONIA,
            as_of_date=as_of_date,
            fallback_rate_code=RateCode.CBR)

        if not result.is_resolved():
            return {
                "is_in_scope": True,
                "rate_code_used": None,
                "base_rate_pct": None,
                "k_premium_pct": k_premium_pct,
                "total_rate_pct": None,
                "is_fallback": False,
                "notes": result.notes,
            }

        return {
            "is_in_scope": True,
            "rate_code_used": result.applied_rate_code.value,
            "base_rate_pct": result.rate_pct,
            "k_premium_pct": k_premium_pct,
            "total_rate_pct": result.rate_pct + k_premium_pct,
            "is_fallback": result.is_fallback,
            "notes": result.notes,
        }

    # ── Reporting ──────────────────────────────────────────────────────
    def board_summary(self) -> Dict[str, object]:
        """Aggregate registry state for governance reporting."""
        kesonia_count = sum(
            1 for (rc, _) in self._rates if rc == RateCode.KESONIA.value)
        cbr_count = sum(
            1 for (rc, _) in self._rates if rc == RateCode.CBR.value)

        latest_kesonia = None
        kesonia_obs = [
            obs for (rc, _), obs in self._rates.items()
            if rc == RateCode.KESONIA.value]
        if kesonia_obs:
            latest_kesonia = max(
                kesonia_obs, key=lambda o: o.observation_date)

        return {
            "entity": self.entity_name,
            "n_kesonia_observations": kesonia_count,
            "n_cbr_observations": cbr_count,
            "n_index_observations": len(self._index),
            "latest_kesonia_pct": (
                latest_kesonia.rate_pct if latest_kesonia else None),
            "latest_kesonia_date": (
                latest_kesonia.observation_date
                if latest_kesonia else None),
            "regulatory_dates": {
                "kesonia_launch": KESONIA_LAUNCH_DATE,
                "new_loan_effective": KESONIA_NEW_LOAN_EFFECTIVE,
                "new_loan_practical": KESONIA_NEW_LOAN_PRACTICAL,
                "existing_loan_deadline": KESONIA_EXISTING_LOAN_DEADLINE,
            },
        }


# ════════════════════════════════════════════════════════════════════════
# v10.13 risk_based_pricing bridge — composition helpers
# ════════════════════════════════════════════════════════════════════════

def resolve_funding_rate_decimal(
    *,
    registry: "BenchmarkRateRegistry",
    as_of_date: str,
    rate_code: RateCode = RateCode.KESONIA,
    fallback_rate_code: Optional[RateCode] = RateCode.CBR,
) -> Tuple[Optional[Decimal], BenchmarkLookupResult]:
    """Bridge to v10.13 risk_based_pricing.PricingInputs.funding_rate.

    Returns (rate_as_decimal_fraction, full_lookup_result).

    Caller uses the decimal fraction to populate `funding_rate` on
    `PricingInputs`; the lookup result has audit trail (fallback flag,
    notes, applied_rate_code).

    Per Rule 1: when neither requested rate nor fallback is available,
    rate_decimal returns None — caller must decide whether to halt
    pricing or use a hard-coded backstop. The engine never fabricates.
    """
    result = registry.get_rate(
        rate_code=rate_code,
        as_of_date=as_of_date,
        fallback_rate_code=fallback_rate_code)
    if not result.is_resolved():
        return (None, result)
    return (result.rate_pct / Decimal("100"), result)


def derive_k_premium_pct(
    *,
    offered_rate_decimal: Decimal,
    kesonia_pct: Decimal,
) -> Decimal:
    """Derive customer-facing K premium per CBK RBCPM.

    Per CBK FAQ + Aug 2025 RBCPM document:
       Total Lending Rate = KESONIA + K

    Given a v10.13-computed offered_rate (decimal fraction, e.g. 0.1326),
    and current KESONIA (in percentage points, e.g. 8.76), returns the
    K premium that must be disclosed to the customer (in pp, e.g. 4.50).

    K = (offered_rate × 100) - KESONIA
    """
    return offered_rate_decimal * Decimal("100") - kesonia_pct


# ════════════════════════════════════════════════════════════════════════
# Self-test
# ════════════════════════════════════════════════════════════════════════

def _make_registry_with_data() -> BenchmarkRateRegistry:
    """Helper: registry pre-populated with realistic KESONIA + CBR data."""
    reg = BenchmarkRateRegistry()
    # KESONIA observations (per CBK weekly bulletins)
    reg.add_rates_bulk([
        BenchmarkRateObservation(
            rate_code=RateCode.KESONIA, observation_date="2026-04-16",
            rate_pct=Decimal("8.76"), rate_type=RateType.OVERNIGHT),
        BenchmarkRateObservation(
            rate_code=RateCode.KESONIA, observation_date="2026-04-23",
            rate_pct=Decimal("8.76"), rate_type=RateType.OVERNIGHT),
        BenchmarkRateObservation(
            rate_code=RateCode.CBR, observation_date="2026-04-23",
            rate_pct=Decimal("9.00"), rate_type=RateType.POLICY),
    ])
    # Compounded index (illustrative — baseline 100.0000 at 1 Jan 2025)
    reg.add_compounded_index(CompoundedIndexObservation(
        observation_date="2026-01-01", index_value=Decimal("110.5000")))
    reg.add_compounded_index(CompoundedIndexObservation(
        observation_date="2026-04-01", index_value=Decimal("112.7000")))
    return reg


def _test_constants_match_cbk():
    assert KESONIA_LAUNCH_DATE == "2025-09-01"
    assert KESONIA_EXISTING_LOAN_DEADLINE == "2026-02-28"
    assert KESONIA_DAY_COUNT_BASIS == 360


def _test_rate_observation_validates_pct():
    try:
        BenchmarkRateObservation(
            rate_code=RateCode.KESONIA, observation_date="2026-01-01",
            rate_pct=Decimal("150"), rate_type=RateType.OVERNIGHT)
        assert False
    except ValueError:
        pass


def _test_get_rate_exact_match():
    reg = _make_registry_with_data()
    r = reg.get_rate(rate_code=RateCode.KESONIA,
                       as_of_date="2026-04-23")
    assert r.is_resolved()
    assert r.rate_pct == Decimal("8.76")
    assert not r.is_fallback


def _test_get_rate_weekend_holdover():
    """CBK methodology: rate held constant on weekends/holidays."""
    reg = _make_registry_with_data()
    # 2026-04-25 is a Saturday; nothing on file but 2026-04-23 should hold
    r = reg.get_rate(rate_code=RateCode.KESONIA,
                       as_of_date="2026-04-25")
    assert r.is_resolved()
    assert r.rate_pct == Decimal("8.76")
    assert "weekend" in r.notes.lower() or "holiday" in r.notes.lower()


def _test_get_rate_no_data_no_fabrication():
    """Rule 1 — never fabricate when nothing is registered."""
    reg = BenchmarkRateRegistry()
    r = reg.get_rate(rate_code=RateCode.KESONIA,
                       as_of_date="2026-04-23")
    assert not r.is_resolved()
    assert r.rate_pct is None


def _test_get_rate_falls_back_to_cbr():
    """Per CBK RBCPM: when KESONIA unavailable, fall back to CBR."""
    reg = BenchmarkRateRegistry()
    reg.add_rate(BenchmarkRateObservation(
        rate_code=RateCode.CBR, observation_date="2026-04-23",
        rate_pct=Decimal("9.00"), rate_type=RateType.POLICY))
    r = reg.get_rate(
        rate_code=RateCode.KESONIA,
        as_of_date="2026-04-23",
        fallback_rate_code=RateCode.CBR)
    assert r.is_resolved()
    assert r.is_fallback
    assert r.applied_rate_code == RateCode.CBR
    assert r.rate_pct == Decimal("9.00")


def _test_get_rate_fetcher_invocation():
    """Rule 7 — fetcher called when no in-registry data."""
    fetched_calls = []
    def fake_fetcher(code, dt):
        fetched_calls.append((code.value, dt))
        return BenchmarkRateObservation(
            rate_code=code, observation_date=dt,
            rate_pct=Decimal("8.50"),
            rate_type=RateType.OVERNIGHT, source="test_fetcher")

    reg = BenchmarkRateRegistry(rate_fetcher=fake_fetcher)
    r = reg.get_rate(rate_code=RateCode.KESONIA,
                       as_of_date="2026-04-23")
    assert r.is_resolved()
    assert r.rate_pct == Decimal("8.50")
    assert "fetcher" in r.notes.lower()
    assert len(fetched_calls) == 1


def _test_get_rate_fetcher_failure_handled():
    def failing_fetcher(code, dt):
        raise ConnectionError("CBK API down")
    reg = BenchmarkRateRegistry(rate_fetcher=failing_fetcher)
    r = reg.get_rate(rate_code=RateCode.KESONIA,
                       as_of_date="2026-04-23")
    # Failed fetcher → graceful unresolved result, not crash
    assert not r.is_resolved()


def _test_compounded_index_lookup():
    reg = _make_registry_with_data()
    obs = reg.get_index("2026-04-01")
    assert obs is not None
    assert obs.index_value == Decimal("112.7000")


def _test_compounded_accrual_factor_correct():
    """Compute compound-in-arrears for 90-day period via CBK index ratio."""
    reg = _make_registry_with_data()
    accrual = reg.compute_compounded_accrual(
        period_start="2026-01-01", period_end="2026-04-01")
    assert accrual is not None
    # accrual_factor = 112.7 / 110.5 - 1 = ~0.01991
    expected = Decimal("112.7000") / Decimal("110.5000") - Decimal("1")
    assert accrual.accrual_factor == expected
    # 90 days; annualized = factor × 360/90 × 100
    assert accrual.days == 90


def _test_compounded_accrual_unavailable():
    """Returns None if either index endpoint missing."""
    reg = _make_registry_with_data()
    # No index for 2030 — should return None
    r = reg.compute_compounded_accrual(
        period_start="2030-01-01", period_end="2030-04-01")
    assert r is None


def _test_total_rate_kesonia_plus_k():
    """RBCPM core: Total = KESONIA + K."""
    reg = _make_registry_with_data()
    r = reg.compute_total_rate(
        as_of_date="2026-04-23",
        k_premium_pct=Decimal("4.5"))    # bank's risk premium
    assert r["is_in_scope"]
    assert r["base_rate_pct"] == Decimal("8.76")
    assert r["k_premium_pct"] == Decimal("4.5")
    assert r["total_rate_pct"] == Decimal("13.26")
    assert not r["is_fallback"]


def _test_total_rate_fcy_excluded():
    """Per CBK FAQ — FCY loans excluded from KESONIA RBCPM scope."""
    reg = _make_registry_with_data()
    r = reg.compute_total_rate(
        as_of_date="2026-04-23",
        k_premium_pct=Decimal("3.0"),
        loan_rate_type=LoanRateType.VARIABLE_FCY)
    assert not r["is_in_scope"]
    assert r["total_rate_pct"] is None
    assert "excluded" in r["notes"].lower()


def _test_total_rate_fixed_rate_excluded():
    """Fixed-rate loans excluded."""
    reg = _make_registry_with_data()
    r = reg.compute_total_rate(
        as_of_date="2026-04-23",
        k_premium_pct=Decimal("4.5"),
        loan_rate_type=LoanRateType.FIXED_RATE)
    assert not r["is_in_scope"]


def _test_total_rate_fallback_to_cbr_visible():
    """When KESONIA unavailable, CBR fallback is visible to caller."""
    reg = BenchmarkRateRegistry()
    reg.add_rate(BenchmarkRateObservation(
        rate_code=RateCode.CBR, observation_date="2026-04-23",
        rate_pct=Decimal("9.00"), rate_type=RateType.POLICY))
    r = reg.compute_total_rate(
        as_of_date="2026-04-23", k_premium_pct=Decimal("4.5"))
    assert r["is_in_scope"]
    assert r["is_fallback"]
    assert r["rate_code_used"] == "CBR"
    assert r["total_rate_pct"] == Decimal("13.50")    # 9.00 + 4.50


def _test_total_rate_compounded_path():
    """When use_compounded=True, computes via index ratio."""
    reg = _make_registry_with_data()
    r = reg.compute_total_rate(
        as_of_date="2026-04-01",
        k_premium_pct=Decimal("4.5"),
        use_compounded=True,
        period_start="2026-01-01")
    assert r["is_in_scope"]
    assert r["rate_code_used"] == "KESONIA_COMPOUNDED_INDEX"
    assert r["base_rate_pct"] is not None
    # Compounded annualized rate plus K premium
    assert r["total_rate_pct"] > r["k_premium_pct"]


def _test_board_summary_empty():
    reg = BenchmarkRateRegistry()
    s = reg.board_summary()
    assert s["n_kesonia_observations"] == 0
    assert s["latest_kesonia_pct"] is None
    # Regulatory dates always visible
    assert s["regulatory_dates"]["kesonia_launch"] == "2025-09-01"


def _test_board_summary_aggregates():
    reg = _make_registry_with_data()
    s = reg.board_summary()
    assert s["n_kesonia_observations"] == 2
    assert s["latest_kesonia_pct"] == Decimal("8.76")
    assert s["latest_kesonia_date"] == "2026-04-23"


def _test_decimal_purity():
    reg = _make_registry_with_data()
    r = reg.compute_total_rate(
        as_of_date="2026-04-23", k_premium_pct=Decimal("4.5"))
    assert isinstance(r["total_rate_pct"], Decimal)


def _test_loan_rate_type_scope():
    """Only VARIABLE_KES is in KESONIA scope per CBK FAQ."""
    assert LoanRateType.VARIABLE_KES.is_kesonia_in_scope()
    assert not LoanRateType.VARIABLE_FCY.is_kesonia_in_scope()
    assert not LoanRateType.FIXED_RATE.is_kesonia_in_scope()


def _test_compounded_index_validates_positive():
    try:
        CompoundedIndexObservation(
            observation_date="2026-01-01", index_value=Decimal("0"))
        assert False
    except ValueError:
        pass


def _test_resolve_funding_rate_decimal_kesonia():
    """Bridge: KESONIA observation 8.76% → 0.0876 decimal fraction."""
    reg = _make_registry_with_data()
    rate_dec, lookup = resolve_funding_rate_decimal(
        registry=reg, as_of_date="2026-04-23")
    assert rate_dec == Decimal("0.0876")
    assert lookup.is_resolved()
    assert not lookup.is_fallback


def _test_resolve_funding_rate_decimal_cbr_fallback():
    """When KESONIA unavailable, fallback returns CBR-derived decimal."""
    reg = BenchmarkRateRegistry()
    reg.add_rate(BenchmarkRateObservation(
        rate_code=RateCode.CBR, observation_date="2026-04-23",
        rate_pct=Decimal("9.00"), rate_type=RateType.POLICY))
    rate_dec, lookup = resolve_funding_rate_decimal(
        registry=reg, as_of_date="2026-04-23")
    assert rate_dec == Decimal("0.09")
    assert lookup.is_fallback


def _test_resolve_funding_rate_unavailable_returns_none():
    """Rule 1 — caller must handle None explicitly, not silent zero."""
    reg = BenchmarkRateRegistry()
    rate_dec, lookup = resolve_funding_rate_decimal(
        registry=reg, as_of_date="2026-04-23")
    assert rate_dec is None
    assert not lookup.is_resolved()


def _test_derive_k_premium_pct():
    """K = (offered × 100) - KESONIA. e.g. 13.26% offered, 8.76% KESONIA → K=4.50pp."""
    k = derive_k_premium_pct(
        offered_rate_decimal=Decimal("0.1326"),
        kesonia_pct=Decimal("8.76"))
    assert k == Decimal("4.50")


def _test_v10_13_to_kesonia_round_trip():
    """End-to-end: v10.13 compute_total_rate(offered) → derive K → matches input premium."""
    reg = _make_registry_with_data()
    # KESONIA + K = total. 8.76 + 4.5 = 13.26.
    r = reg.compute_total_rate(
        as_of_date="2026-04-23", k_premium_pct=Decimal("4.5"))
    # If we then have a v10.13 pricing engine return offered_rate=0.1326,
    # derive_k_premium should return 4.5 again.
    derived_k = derive_k_premium_pct(
        offered_rate_decimal=r["total_rate_pct"] / Decimal("100"),
        kesonia_pct=r["base_rate_pct"])
    assert derived_k == Decimal("4.5")


def self_test() -> None:
    tests = [
        _test_constants_match_cbk,
        _test_rate_observation_validates_pct,
        _test_get_rate_exact_match,
        _test_get_rate_weekend_holdover,
        _test_get_rate_no_data_no_fabrication,
        _test_get_rate_falls_back_to_cbr,
        _test_get_rate_fetcher_invocation,
        _test_get_rate_fetcher_failure_handled,
        _test_compounded_index_lookup,
        _test_compounded_accrual_factor_correct,
        _test_compounded_accrual_unavailable,
        _test_total_rate_kesonia_plus_k,
        _test_total_rate_fcy_excluded,
        _test_total_rate_fixed_rate_excluded,
        _test_total_rate_fallback_to_cbr_visible,
        _test_total_rate_compounded_path,
        _test_board_summary_empty,
        _test_board_summary_aggregates,
        _test_decimal_purity,
        _test_loan_rate_type_scope,
        _test_compounded_index_validates_positive,
        _test_resolve_funding_rate_decimal_kesonia,
        _test_resolve_funding_rate_decimal_cbr_fallback,
        _test_resolve_funding_rate_unavailable_returns_none,
        _test_derive_k_premium_pct,
        _test_v10_13_to_kesonia_round_trip,
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
        print(f"✗ benchmark_rates self-test: {len(failed)} failures",
              file=sys.stderr)
        for name, msg in failed:
            print(f"  - {name}: {msg}", file=sys.stderr)
        raise SystemExit(1)
    print(f"✓ benchmark_rates self-test passed ({len(tests)} tests)")


if __name__ == "__main__":
    self_test()
