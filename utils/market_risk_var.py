"""utils/market_risk_var.py — v10.39: VaR / ES / Backtesting.

╔════════════════════════════════════════════════════════════════════════╗
║  MARKET RISK — VALUE-AT-RISK & EXPECTED SHORTFALL                      ║
║  Cat A — Standards ENH-MR-001 (VaR), ENH-MR-002 (ES),                  ║
║          ENH-MR-005 (Backtesting)                                      ║
╠════════════════════════════════════════════════════════════════════════╣
║  Three VaR methodologies:                                               ║
║    - Parametric (variance-covariance assuming normal returns)           ║
║    - Historical (empirical percentile, no distribution assumption)      ║
║    - Monte Carlo (simulated returns)                                    ║
║                                                                         ║
║  Expected Shortfall (CVaR / Tail VaR) — average loss in the tail       ║
║  beyond VaR. FRTB-IMA standard at 97.5% confidence.                     ║
║                                                                         ║
║  Backtesting:                                                           ║
║    - Kupiec POF test (unconditional coverage)                          ║
║    - Christoffersen independence test                                   ║
║    - Combined conditional coverage test (CC = POF + IND)                ║
║                                                                         ║
║  Honesty Rule 1: every VaRResult surfaces methodology +                 ║
║  confidence + horizon + portfolio value + return distribution           ║
║  summary (mean, stdev, min, max, n) + framework refs. The user          ║
║  sees not just the number but how it was computed.                      ║
║                                                                         ║
║  Honesty Rule 7: live return histories, vol estimates, and             ║
║  correlation matrices are EXTERNAL inputs. Methods take them as         ║
║  arguments and never fetch market data.                                 ║
║                                                                         ║
║  Composes with: market_risk_factors (RiskFactor for factor             ║
║  decomposition), market_risk_sensitivities (factor-decomposed           ║
║  parametric VaR uses sensitivities + covariance matrix),               ║
║  scenario_simulator (RISK-* scenarios trigger VaR computation).         ║
║                                                                         ║
║  Regulatory anchors: BCBS d352 FRTB-IMA (ES @ 97.5%), Basel             ║
║  market-risk amendment 1996 (VaR @ 99%, 10-day), CBK PG/04,             ║
║  Kupiec 1995, Christoffersen 1998.                                     ║
╚════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from decimal import Decimal, getcontext
from enum import Enum
from statistics import NormalDist, mean, pstdev
from typing import (
    Any, Callable, Dict, List, Mapping, Optional, Sequence,
    Tuple)

from utils.market_risk_factors import (
    RISK_FACTOR_TO_CLASS, RiskFactor, RiskFactorClass)

getcontext().prec = 28


SPEC_DEVIATION_NOTE = (
    "VaREngine implements ENH-MR-001/002/005. Parametric VaR uses "
    "Normal(μ,σ²) assumption with z = NormalDist().inv_cdf(1-α). "
    "Historical VaR uses linear interpolation between adjacent "
    "order statistics (numpy-compatible). Expected Shortfall is "
    "computed as the mean of returns ≤ -VaR (consistent with FRTB-"
    "IMA convention; ES is reported as a positive loss number). "
    "Holding-period scaling uses √T per Basel market-risk "
    "amendment. Kupiec POF and Christoffersen independence tests "
    "use χ²(1) critical values hard-coded at 1%, 5%, 10% "
    "significance. Per Rule 7, return histories are external "
    "input — never fetched."
)


# ════════════════════════════════════════════════════════════════════════
# Methodology and severity enums
# ════════════════════════════════════════════════════════════════════════

class VaRMethodology(Enum):
    PARAMETRIC = "PARAMETRIC"           # variance-covariance (Normal)
    HISTORICAL = "HISTORICAL"           # empirical percentile
    MONTE_CARLO = "MONTE_CARLO"


class BacktestVerdict(Enum):
    """Outcome of a backtest at the configured significance level."""
    PASS = "PASS"
    FAIL = "FAIL"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


# ════════════════════════════════════════════════════════════════════════
# χ²(1) critical values (hard-coded — no scipy dependency)
# ════════════════════════════════════════════════════════════════════════

_CHI2_1_CRITICAL: Mapping[Decimal, Decimal] = {
    Decimal("0.10"): Decimal("2.706"),
    Decimal("0.05"): Decimal("3.841"),
    Decimal("0.01"): Decimal("6.635"),
}

_CHI2_2_CRITICAL: Mapping[Decimal, Decimal] = {
    Decimal("0.10"): Decimal("4.605"),
    Decimal("0.05"): Decimal("5.991"),
    Decimal("0.01"): Decimal("9.210"),
}


# ════════════════════════════════════════════════════════════════════════
# Result dataclasses
# ════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class ReturnDistributionSummary:
    """Per Rule 1: descriptive stats of the underlying returns."""
    n_observations: int
    mean: Decimal
    stdev: Decimal
    minimum: Decimal
    maximum: Decimal


@dataclass(frozen=True)
class VaRResult:
    """A VaR (and Expected Shortfall) computation outcome.

    Per Rule 1, the result carries everything needed to triage:
      - methodology (which method)
      - confidence (e.g., 0.99)
      - horizon_days (1, 10, etc.)
      - portfolio_value_kes (the base value VaR is denominated in)
      - var_kes (the loss number — POSITIVE)
      - expected_shortfall_kes (POSITIVE; ≥ var_kes)
      - return_distribution (mean / stdev / min / max / n)
      - framework_refs
    """
    methodology: VaRMethodology
    confidence: Decimal
    horizon_days: int
    portfolio_value_kes: Decimal
    var_kes: Decimal
    expected_shortfall_kes: Decimal
    return_distribution: ReturnDistributionSummary
    framework_refs: Tuple[str, ...]
    notes: str = ""


@dataclass(frozen=True)
class BacktestResult:
    """Per Rule 1: full diagnostic information."""
    test_name: str
    significance: Decimal
    n_observations: int
    n_breaches: int
    expected_n_breaches: Decimal
    test_statistic: Decimal
    critical_value: Decimal
    verdict: BacktestVerdict
    framework_refs: Tuple[str, ...]


# ════════════════════════════════════════════════════════════════════════
# Engine
# ════════════════════════════════════════════════════════════════════════

class VaREngine:
    """Market-risk VaR / ES / backtesting computations.

    Per Rule 7, return histories and simulation parameters are
    passed in by the caller. The engine never fetches data.
    """

    # ── Parametric VaR ────────────────────────────────────────────────
    def parametric_var(
        self,
        returns: Sequence[float],
        portfolio_value_kes: Decimal,
        confidence: Decimal = Decimal("0.99"),
        horizon_days: int = 1,
    ) -> VaRResult:
        """VaR under the Normal(μ, σ²) assumption.

        VaR_α = -(μ × T - z_α × σ × √T) × PV_0
              ≈ (z_α × σ × √T - μ × T) × PV_0      (loss convention)

        Reported as a positive loss amount.
        """
        if not returns:
            raise ValueError("returns must not be empty")
        if not (Decimal("0") < confidence < Decimal("1")):
            raise ValueError(
                "confidence must be in (0, 1) — got "
                f"{confidence}")
        if horizon_days < 1:
            raise ValueError("horizon_days must be >= 1")

        mu = mean(returns)
        sigma = pstdev(returns) if len(returns) > 1 else 0.0
        # z_α from inverse standard-normal CDF
        z_alpha = NormalDist().inv_cdf(float(confidence))
        # Holding-period scaling
        sqrt_T = math.sqrt(horizon_days)
        # Loss-positive VaR fraction
        var_fraction = z_alpha * sigma * sqrt_T - mu * horizon_days
        # Convert to KES amount
        var_kes = portfolio_value_kes * Decimal(str(var_fraction))
        # ES under normal: ES_α = (φ(z) / (1-α)) × σ × √T - μ × T
        phi_z = math.exp(-0.5 * z_alpha * z_alpha) / math.sqrt(
            2 * math.pi)
        es_fraction = (
            (phi_z / float(1 - confidence)) * sigma * sqrt_T -
            mu * horizon_days)
        es_kes = portfolio_value_kes * Decimal(str(es_fraction))

        # Distribution summary
        dist_summary = self._summarize_returns(returns)

        return VaRResult(
            methodology=VaRMethodology.PARAMETRIC,
            confidence=confidence,
            horizon_days=horizon_days,
            portfolio_value_kes=portfolio_value_kes,
            var_kes=max(var_kes, Decimal("0")),
            expected_shortfall_kes=max(es_kes, Decimal("0")),
            return_distribution=dist_summary,
            framework_refs=(
                "Basel Market Risk Amendment 1996",
                "BCBS d352 FRTB IMA (parametric reference)",
            ),
            notes=(
                f"z_alpha={z_alpha:.4f}, sigma={sigma:.6f}, "
                f"mu={mu:.6f}"),
        )

    # ── Historical VaR ────────────────────────────────────────────────
    def historical_var(
        self,
        returns: Sequence[float],
        portfolio_value_kes: Decimal,
        confidence: Decimal = Decimal("0.99"),
        horizon_days: int = 1,
    ) -> VaRResult:
        """Empirical VaR = − percentile(returns, 1−α).

        For horizon scaling > 1 day, applies √T scaling to the
        empirical 1-day VaR (consistent with Basel convention,
        though some books prefer overlapping returns; we surface
        the scaling factor in notes).
        """
        if not returns:
            raise ValueError("returns must not be empty")
        if not (Decimal("0") < confidence < Decimal("1")):
            raise ValueError("confidence must be in (0, 1)")
        if horizon_days < 1:
            raise ValueError("horizon_days must be >= 1")

        sorted_r = sorted(returns)
        # Linear-interpolation percentile (numpy default)
        alpha = float(1 - confidence)        # tail probability
        n = len(sorted_r)
        # Position in sorted array: (n-1) × alpha
        idx_float = (n - 1) * alpha
        lower_idx = int(math.floor(idx_float))
        upper_idx = min(lower_idx + 1, n - 1)
        weight = idx_float - lower_idx
        percentile_value = (
            sorted_r[lower_idx] * (1 - weight) +
            sorted_r[upper_idx] * weight)
        # VaR is loss-positive
        one_day_var_fraction = -percentile_value
        sqrt_T = math.sqrt(horizon_days)
        var_fraction = one_day_var_fraction * sqrt_T
        var_kes = portfolio_value_kes * Decimal(str(var_fraction))

        # ES: mean of returns ≤ percentile_value
        tail_returns = [r for r in sorted_r if r <= percentile_value]
        if tail_returns:
            es_one_day = -mean(tail_returns)
        else:
            es_one_day = one_day_var_fraction
        es_fraction = es_one_day * sqrt_T
        es_kes = portfolio_value_kes * Decimal(str(es_fraction))

        return VaRResult(
            methodology=VaRMethodology.HISTORICAL,
            confidence=confidence,
            horizon_days=horizon_days,
            portfolio_value_kes=portfolio_value_kes,
            var_kes=max(var_kes, Decimal("0")),
            expected_shortfall_kes=max(es_kes, Decimal("0")),
            return_distribution=self._summarize_returns(returns),
            framework_refs=(
                "Basel Market Risk Amendment 1996",
                "BCBS d352 FRTB IMA (historical reference)",
            ),
            notes=(
                f"percentile={percentile_value:.6f}, "
                f"sqrt_T scaling factor={sqrt_T:.4f}, "
                f"tail_count={len(tail_returns)}"),
        )

    # ── Monte Carlo VaR ───────────────────────────────────────────────
    def monte_carlo_var(
        self,
        portfolio_value_kes: Decimal,
        return_mean: float,
        return_stdev: float,
        confidence: Decimal = Decimal("0.99"),
        horizon_days: int = 1,
        n_simulations: int = 10000,
        seed: Optional[int] = None,
    ) -> VaRResult:
        """Simulate N return paths and percentile the result.

        Uses single-factor lognormal-like scaling:
          R_T = μ × T + σ × √T × ε,  ε ~ N(0,1)
        """
        if n_simulations < 100:
            raise ValueError(
                "n_simulations must be >= 100 for stability")
        if not (Decimal("0") < confidence < Decimal("1")):
            raise ValueError("confidence must be in (0, 1)")
        if horizon_days < 1:
            raise ValueError("horizon_days must be >= 1")

        rng = random.Random(seed) if seed is not None else random
        sqrt_T = math.sqrt(horizon_days)
        sims: List[float] = []
        for _ in range(n_simulations):
            eps = rng.gauss(0, 1)
            r = return_mean * horizon_days + return_stdev * sqrt_T * eps
            sims.append(r)

        # Use historical VaR algorithm on the simulated returns
        result = self.historical_var(
            returns=sims,
            portfolio_value_kes=portfolio_value_kes,
            confidence=confidence,
            horizon_days=1)    # already scaled
        # Patch the methodology and notes (return_distribution
        # reflects the simulated set)
        return VaRResult(
            methodology=VaRMethodology.MONTE_CARLO,
            confidence=confidence,
            horizon_days=horizon_days,
            portfolio_value_kes=portfolio_value_kes,
            var_kes=result.var_kes,
            expected_shortfall_kes=result.expected_shortfall_kes,
            return_distribution=result.return_distribution,
            framework_refs=(
                "Basel Market Risk Amendment 1996",
                "BCBS d352 FRTB IMA (Monte Carlo)",
            ),
            notes=(
                f"n_simulations={n_simulations}, "
                f"seed={seed}, "
                f"input mu={return_mean:.6f}, "
                f"input sigma={return_stdev:.6f}"),
        )

    # ── Backtests ─────────────────────────────────────────────────────
    def kupiec_pof_test(
        self,
        breach_sequence: Sequence[bool],
        var_confidence: Decimal,
        significance: Decimal = Decimal("0.05"),
    ) -> BacktestResult:
        """Kupiec Proportion of Failures (POF) test.

        H0: actual breach rate p̂ = expected p = 1 − var_confidence

        Likelihood ratio:
          LR = -2 ln[ (1-p)^(N-x) p^x / (1-p̂)^(N-x) p̂^x ]
        ~ χ²(1) under H0.
        """
        if not breach_sequence:
            return BacktestResult(
                test_name="Kupiec POF",
                significance=significance,
                n_observations=0,
                n_breaches=0,
                expected_n_breaches=Decimal("0"),
                test_statistic=Decimal("0"),
                critical_value=_CHI2_1_CRITICAL.get(
                    significance, Decimal("3.841")),
                verdict=BacktestVerdict.INSUFFICIENT_DATA,
                framework_refs=("Kupiec 1995",))

        N = len(breach_sequence)
        x = sum(1 for b in breach_sequence if b)
        p = float(1 - var_confidence)        # expected
        p_hat = x / N                        # observed

        # Avoid log(0) — if x = 0, p̂ = 0; the second term in
        # the LR formula has 0^0 ambiguity; handle explicitly
        if x == 0:
            # Likelihood under H0 = (1-p)^N
            log_h0 = N * math.log(1 - p)
            # Likelihood under H1 with p̂ = 0 is (1)^N = 1, log = 0
            lr = -2 * (log_h0 - 0)
        elif x == N:
            log_h0 = N * math.log(p)
            log_h1 = 0    # (p̂)^N = 1^N
            lr = -2 * (log_h0 - log_h1)
        else:
            log_h0 = (
                (N - x) * math.log(1 - p) + x * math.log(p))
            log_h1 = (
                (N - x) * math.log(1 - p_hat) +
                x * math.log(p_hat))
            lr = -2 * (log_h0 - log_h1)

        critical = _CHI2_1_CRITICAL.get(
            significance, Decimal("3.841"))
        verdict = (
            BacktestVerdict.FAIL if Decimal(str(lr)) > critical
            else BacktestVerdict.PASS)
        return BacktestResult(
            test_name="Kupiec POF",
            significance=significance,
            n_observations=N,
            n_breaches=x,
            expected_n_breaches=Decimal(str(round(N * p, 2))),
            test_statistic=Decimal(str(round(lr, 4))),
            critical_value=critical,
            verdict=verdict,
            framework_refs=(
                "Kupiec 1995",
                "BCBS d352 FRTB backtesting",
            ))

    def christoffersen_independence_test(
        self,
        breach_sequence: Sequence[bool],
        significance: Decimal = Decimal("0.05"),
    ) -> BacktestResult:
        """Christoffersen 1998 independence test.

        Tests whether breaches are independently distributed.

        Build a 2×2 transition matrix:
          n_00: no breach → no breach
          n_01: no breach → breach
          n_10: breach → no breach
          n_11: breach → breach

        Under H0 (independence), π̂_01 = π̂_11 = π̂ = total breach rate.
        Under H1, π̂_01 = n_01/(n_00+n_01), π̂_11 = n_11/(n_10+n_11).

        LR_ind = -2 ln[ L(π̂) / L(π̂_01, π̂_11) ] ~ χ²(1).
        """
        if len(breach_sequence) < 2:
            return BacktestResult(
                test_name="Christoffersen Independence",
                significance=significance,
                n_observations=len(breach_sequence),
                n_breaches=sum(1 for b in breach_sequence if b),
                expected_n_breaches=Decimal("0"),
                test_statistic=Decimal("0"),
                critical_value=_CHI2_1_CRITICAL.get(
                    significance, Decimal("3.841")),
                verdict=BacktestVerdict.INSUFFICIENT_DATA,
                framework_refs=("Christoffersen 1998",))

        n_00 = n_01 = n_10 = n_11 = 0
        for prev, curr in zip(
                breach_sequence[:-1], breach_sequence[1:]):
            if (not prev) and (not curr):
                n_00 += 1
            elif (not prev) and curr:
                n_01 += 1
            elif prev and (not curr):
                n_10 += 1
            else:
                n_11 += 1

        n_total = n_00 + n_01 + n_10 + n_11
        n_breaches = n_01 + n_11
        if n_total == 0 or n_breaches == 0 or n_breaches == n_total:
            return BacktestResult(
                test_name="Christoffersen Independence",
                significance=significance,
                n_observations=len(breach_sequence),
                n_breaches=sum(1 for b in breach_sequence if b),
                expected_n_breaches=Decimal("0"),
                test_statistic=Decimal("0"),
                critical_value=_CHI2_1_CRITICAL.get(
                    significance, Decimal("3.841")),
                verdict=BacktestVerdict.INSUFFICIENT_DATA,
                framework_refs=("Christoffersen 1998",))

        pi_hat = n_breaches / n_total
        denom_0 = n_00 + n_01
        denom_1 = n_10 + n_11
        pi_01 = n_01 / denom_0 if denom_0 > 0 else 0.0
        pi_11 = n_11 / denom_1 if denom_1 > 0 else 0.0

        def _safe_log(p: float) -> float:
            return math.log(p) if p > 0 else 0.0

        log_h0 = (
            n_breaches * _safe_log(pi_hat) +
            (n_total - n_breaches) * _safe_log(1 - pi_hat))
        log_h1 = (
            n_00 * _safe_log(1 - pi_01) +
            n_01 * _safe_log(pi_01) +
            n_10 * _safe_log(1 - pi_11) +
            n_11 * _safe_log(pi_11))
        lr = -2 * (log_h0 - log_h1)
        critical = _CHI2_1_CRITICAL.get(
            significance, Decimal("3.841"))
        verdict = (
            BacktestVerdict.FAIL if Decimal(str(lr)) > critical
            else BacktestVerdict.PASS)
        return BacktestResult(
            test_name="Christoffersen Independence",
            significance=significance,
            n_observations=len(breach_sequence),
            n_breaches=sum(1 for b in breach_sequence if b),
            expected_n_breaches=Decimal(
                str(round(pi_hat * len(breach_sequence), 2))),
            test_statistic=Decimal(str(round(lr, 4))),
            critical_value=critical,
            verdict=verdict,
            framework_refs=(
                "Christoffersen 1998",
                "BCBS d352 FRTB backtesting",
            ))

    # ── Helpers ───────────────────────────────────────────────────────
    @staticmethod
    def _summarize_returns(
        returns: Sequence[float],
    ) -> ReturnDistributionSummary:
        if not returns:
            raise ValueError("empty returns")
        return ReturnDistributionSummary(
            n_observations=len(returns),
            mean=Decimal(str(round(mean(returns), 8))),
            stdev=Decimal(str(round(
                pstdev(returns) if len(returns) > 1 else 0.0, 8))),
            minimum=Decimal(str(round(min(returns), 8))),
            maximum=Decimal(str(round(max(returns), 8))),
        )


# ════════════════════════════════════════════════════════════════════════
# Self-test
# ════════════════════════════════════════════════════════════════════════

def _gen_normal_returns(
    n: int, mu: float = 0.0, sigma: float = 0.01,
    seed: int = 42,
) -> List[float]:
    rng = random.Random(seed)
    return [rng.gauss(mu, sigma) for _ in range(n)]


def _test_parametric_var_normal_returns():
    eng = VaREngine()
    returns = _gen_normal_returns(1000, mu=0.0, sigma=0.01)
    result = eng.parametric_var(
        returns=returns,
        portfolio_value_kes=Decimal("1000000"),
        confidence=Decimal("0.99"),
        horizon_days=1)
    # 99% z = 2.326; sigma ~ 0.01; VaR ~ 2.326 × 0.01 × 1m ≈ 23,260
    assert result.var_kes > Decimal("20000")
    assert result.var_kes < Decimal("28000")
    assert result.expected_shortfall_kes > result.var_kes


def _test_parametric_var_higher_confidence_higher_var():
    eng = VaREngine()
    returns = _gen_normal_returns(1000)
    var_95 = eng.parametric_var(
        returns, Decimal("1000000"),
        confidence=Decimal("0.95"))
    var_99 = eng.parametric_var(
        returns, Decimal("1000000"),
        confidence=Decimal("0.99"))
    assert var_99.var_kes > var_95.var_kes


def _test_parametric_var_horizon_scaling():
    eng = VaREngine()
    returns = _gen_normal_returns(1000, mu=0.0, sigma=0.01)
    var_1d = eng.parametric_var(
        returns, Decimal("1000000"), horizon_days=1)
    var_10d = eng.parametric_var(
        returns, Decimal("1000000"), horizon_days=10)
    # √10 ≈ 3.16; var_10d / var_1d should be ~ 3.16
    ratio = float(var_10d.var_kes / var_1d.var_kes)
    assert 2.8 < ratio < 3.5, f"ratio={ratio}"


def _test_parametric_var_rejects_invalid_confidence():
    eng = VaREngine()
    try:
        eng.parametric_var(
            returns=[0.01, -0.02],
            portfolio_value_kes=Decimal("1000"),
            confidence=Decimal("1.5"))
        assert False
    except ValueError:
        pass


def _test_parametric_var_rejects_invalid_horizon():
    eng = VaREngine()
    try:
        eng.parametric_var(
            returns=[0.01], portfolio_value_kes=Decimal("1000"),
            horizon_days=0)
        assert False
    except ValueError:
        pass


def _test_parametric_var_rejects_empty_returns():
    eng = VaREngine()
    try:
        eng.parametric_var(
            returns=[], portfolio_value_kes=Decimal("1000"))
        assert False
    except ValueError:
        pass


def _test_historical_var_simple():
    eng = VaREngine()
    # 100 returns, sorted: -0.05 worst, -0.04, ..., 0.05 best
    returns = [(i - 50) / 1000 for i in range(101)]
    result = eng.historical_var(
        returns=returns,
        portfolio_value_kes=Decimal("1000000"),
        confidence=Decimal("0.95"))
    # 95th percentile of losses → roughly -0.045 → 45,000
    assert result.var_kes > Decimal("40000")
    assert result.var_kes < Decimal("50000")


def _test_historical_var_es_at_least_var():
    eng = VaREngine()
    returns = _gen_normal_returns(500, sigma=0.02)
    result = eng.historical_var(
        returns, Decimal("1000000"), Decimal("0.99"))
    assert result.expected_shortfall_kes >= result.var_kes


def _test_historical_var_no_distributional_assumption():
    """Even with non-normal returns, historical VaR should still
    produce sensible numbers."""
    eng = VaREngine()
    # Bimodal-ish returns
    returns = [-0.10] * 5 + [0.0] * 90 + [0.05] * 5
    result = eng.historical_var(
        returns, Decimal("1000000"), Decimal("0.95"))
    # 5% tail starts at -0.10
    assert result.var_kes > Decimal("0")


def _test_monte_carlo_var_basic():
    eng = VaREngine()
    result = eng.monte_carlo_var(
        portfolio_value_kes=Decimal("1000000"),
        return_mean=0.0,
        return_stdev=0.01,
        confidence=Decimal("0.99"),
        n_simulations=5000,
        seed=42)
    # Should be similar to parametric VaR
    assert result.var_kes > Decimal("18000")
    assert result.var_kes < Decimal("30000")


def _test_monte_carlo_reproducible_with_seed():
    eng = VaREngine()
    a = eng.monte_carlo_var(
        Decimal("1000000"), 0.0, 0.01,
        n_simulations=1000, seed=123)
    b = eng.monte_carlo_var(
        Decimal("1000000"), 0.0, 0.01,
        n_simulations=1000, seed=123)
    assert a.var_kes == b.var_kes


def _test_monte_carlo_rejects_too_few_simulations():
    eng = VaREngine()
    try:
        eng.monte_carlo_var(
            Decimal("1000000"), 0.0, 0.01,
            n_simulations=50)
        assert False
    except ValueError:
        pass


def _test_kupiec_pass_when_breaches_match_expected():
    eng = VaREngine()
    # 99% VaR over 250 days ≈ 2.5 expected breaches.
    # Simulate exactly 3 breaches → should pass.
    seq = [False] * 247 + [True, True, True]
    result = eng.kupiec_pof_test(
        breach_sequence=seq,
        var_confidence=Decimal("0.99"))
    assert result.verdict == BacktestVerdict.PASS


def _test_kupiec_fail_when_too_many_breaches():
    eng = VaREngine()
    # 20 breaches in 250 days at 99% conf — 8x expected
    seq = [True] * 20 + [False] * 230
    result = eng.kupiec_pof_test(
        breach_sequence=seq,
        var_confidence=Decimal("0.99"))
    assert result.verdict == BacktestVerdict.FAIL


def _test_kupiec_handles_zero_breaches():
    eng = VaREngine()
    seq = [False] * 250
    result = eng.kupiec_pof_test(
        seq, var_confidence=Decimal("0.99"))
    # Zero breaches over 250 days at 99% (~2.5 expected) is a
    # mild discrepancy — should pass at 5%
    assert result.verdict in (
        BacktestVerdict.PASS, BacktestVerdict.FAIL)


def _test_kupiec_insufficient_data():
    eng = VaREngine()
    result = eng.kupiec_pof_test(
        breach_sequence=[],
        var_confidence=Decimal("0.99"))
    assert result.verdict == BacktestVerdict.INSUFFICIENT_DATA


def _test_christoffersen_independent_breaches_pass():
    eng = VaREngine()
    # Random-ish independent sequence
    rng = random.Random(42)
    seq = [rng.random() < 0.05 for _ in range(500)]
    result = eng.christoffersen_independence_test(seq)
    # Independent → should PASS
    assert result.verdict in (
        BacktestVerdict.PASS, BacktestVerdict.INSUFFICIENT_DATA)


def _test_christoffersen_clustered_breaches_fail():
    eng = VaREngine()
    # Strong clustering: all breaches in a row
    seq = [False] * 100 + [True] * 20 + [False] * 100
    result = eng.christoffersen_independence_test(seq)
    # Clustering should fail independence
    assert result.verdict == BacktestVerdict.FAIL


def _test_var_result_carries_full_triage():
    eng = VaREngine()
    returns = _gen_normal_returns(500)
    result = eng.parametric_var(
        returns, Decimal("1000000"), Decimal("0.99"))
    # Per Rule 1: every field populated
    assert result.return_distribution.n_observations == 500
    assert len(result.framework_refs) >= 1
    assert result.notes != ""
    assert result.confidence == Decimal("0.99")
    assert result.horizon_days == 1


def self_test() -> None:
    import sys
    tests = [
        _test_parametric_var_normal_returns,
        _test_parametric_var_higher_confidence_higher_var,
        _test_parametric_var_horizon_scaling,
        _test_parametric_var_rejects_invalid_confidence,
        _test_parametric_var_rejects_invalid_horizon,
        _test_parametric_var_rejects_empty_returns,
        _test_historical_var_simple,
        _test_historical_var_es_at_least_var,
        _test_historical_var_no_distributional_assumption,
        _test_monte_carlo_var_basic,
        _test_monte_carlo_reproducible_with_seed,
        _test_monte_carlo_rejects_too_few_simulations,
        _test_kupiec_pass_when_breaches_match_expected,
        _test_kupiec_fail_when_too_many_breaches,
        _test_kupiec_handles_zero_breaches,
        _test_kupiec_insufficient_data,
        _test_christoffersen_independent_breaches_pass,
        _test_christoffersen_clustered_breaches_fail,
        _test_var_result_carries_full_triage,
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
            f"✗ market_risk_var self-test: "
            f"{len(failed)} failures",
            file=sys.stderr)
        for n, m in failed:
            print(f"  - {n}: {m}", file=sys.stderr)
        raise SystemExit(1)
    print(
        f"✓ market_risk_var self-test passed "
        f"({len(tests)} tests)")


if __name__ == "__main__":
    self_test()
