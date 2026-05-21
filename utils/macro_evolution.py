"""utils/macro_evolution.py — Phase O4-B macro state drift + shocks.

Models how macro indicators drift over sim time using a combination of:
  - Brownian motion (small daily volatility around the current level)
  - Mean reversion (rates pull back toward long-run means)
  - Discrete shocks (CBK MPC rate decisions, FX devaluations, MoF actions)

Drift is deterministic for a given seed — same seed + same time
trajectory produces identical state evolution.

References:
  - CBK MPC has moved CBR in 25-50bps steps historically
  - USD/KES daily realised vol ~50bps in stable periods, 100-300bps
    in crisis periods (2022 Q4, Kenya election years)
  - T-bill yields follow CBR with ~300-400bps spread
  - NPL ratio drifts slowly; jumps on credit shocks
"""

from __future__ import annotations

import math
import random
from datetime import datetime, timedelta, timezone
from typing import Optional

from utils.macro_state import MacroState


class MacroEvolution:
    """Drift macro state under brownian + mean-reversion dynamics."""

    def __init__(self, *, seed: int = 0):
        self.rng = random.Random(seed)

        # Long-run means for mean-reversion targets
        self.long_run_cbr = 0.10
        self.long_run_inflation = 0.055
        self.long_run_usd_kes = 130.0
        self.long_run_npl = 0.13
        self.long_run_gdp = 0.055

        # Mean-reversion half-lives in days
        self.cbr_half_life_days = 180        # 6 months
        self.inflation_half_life_days = 90   # 3 months
        self.fx_half_life_days = 90
        self.npl_half_life_days = 365        # slow

        # Daily volatilities
        self.sigma_cbr_daily = 0.0005        # 5bps
        self.sigma_inflation_daily = 0.0008  # 8bps
        self.sigma_fx_daily = 0.005          # 50bps
        self.sigma_npl_daily = 0.0002        # 2bps
        self.sigma_gdp_daily = 0.0003        # 3bps

        # Bounds (won't drift outside these without a shock)
        self.cbr_floor = 0.005
        self.cbr_ceiling = 0.30
        self.usd_kes_floor = 80.0
        self.usd_kes_ceiling = 250.0
        self.npl_floor = 0.02
        self.npl_ceiling = 0.45

    # ── Drift ────────────────────────────────────────────────────

    def evolve(self, state: MacroState, *,
                days_elapsed: float) -> MacroState:
        """Drift the state by ``days_elapsed`` sim days.

        Uses Euler discretisation of a mean-reverting OU process:
            dX = -k*(X - X_lr)*dt + sigma*sqrt(dt)*Z
        where k = ln(2)/half_life and Z ~ N(0,1).
        """
        if days_elapsed <= 0:
            return state

        # CBR
        new_cbr = self._mean_reverting_step(
            state.cbk_central_bank_rate, self.long_run_cbr,
            self.cbr_half_life_days, self.sigma_cbr_daily, days_elapsed,
            floor=self.cbr_floor, ceiling=self.cbr_ceiling,
        )
        # T-bills track CBR with realistic spreads
        spread_91 = state.treasury_91d - state.cbk_central_bank_rate
        spread_182 = state.treasury_182d - state.cbk_central_bank_rate
        spread_364 = state.treasury_364d - state.cbk_central_bank_rate
        new_t91 = max(0.005, new_cbr + spread_91 +
                       self._jitter(self.sigma_cbr_daily / 2, days_elapsed))
        new_t182 = max(0.005, new_cbr + spread_182 +
                        self._jitter(self.sigma_cbr_daily / 2, days_elapsed))
        new_t364 = max(0.005, new_cbr + spread_364 +
                        self._jitter(self.sigma_cbr_daily / 2, days_elapsed))
        new_interbank = max(0.005, new_cbr +
                            self._jitter(self.sigma_cbr_daily, days_elapsed))

        # FX
        new_usd = self._mean_reverting_step(
            state.usd_kes, self.long_run_usd_kes,
            self.fx_half_life_days, state.usd_kes * self.sigma_fx_daily,
            days_elapsed,
            floor=self.usd_kes_floor, ceiling=self.usd_kes_ceiling,
        )
        # EUR/GBP move proportionally with USD plus independent jitter
        usd_change_pct = new_usd / state.usd_kes - 1
        new_eur = state.eur_kes * (1 + usd_change_pct +
                                     self._jitter(self.sigma_fx_daily * 0.5,
                                                   days_elapsed))
        new_gbp = state.gbp_kes * (1 + usd_change_pct +
                                     self._jitter(self.sigma_fx_daily * 0.5,
                                                   days_elapsed))

        # Inflation
        new_inflation = self._mean_reverting_step(
            state.inflation_yoy, self.long_run_inflation,
            self.inflation_half_life_days, self.sigma_inflation_daily,
            days_elapsed, floor=0.0, ceiling=0.30,
        )

        # GDP growth (slower drift, tighter bounds)
        new_gdp = self._mean_reverting_step(
            state.gdp_growth_yoy, self.long_run_gdp,
            365 * 2, self.sigma_gdp_daily, days_elapsed,
            floor=-0.05, ceiling=0.15,
        )

        # NPL — slow mean reversion, asymmetric (jumps up easier than down)
        new_npl = self._mean_reverting_step(
            state.npl_ratio, self.long_run_npl,
            self.npl_half_life_days, self.sigma_npl_daily, days_elapsed,
            floor=self.npl_floor, ceiling=self.npl_ceiling,
        )

        # Credit growth — mild drift
        new_credit_growth = state.private_sector_credit_growth + \
            self._jitter(0.0003, days_elapsed)
        new_credit_growth = max(-0.10, min(0.30, new_credit_growth))

        return state.with_change(
            as_of=state.as_of + timedelta(days=days_elapsed),
            cbk_central_bank_rate=new_cbr,
            treasury_91d=new_t91,
            treasury_182d=new_t182,
            treasury_364d=new_t364,
            interbank_rate=new_interbank,
            usd_kes=new_usd,
            eur_kes=new_eur,
            gbp_kes=new_gbp,
            inflation_yoy=new_inflation,
            gdp_growth_yoy=new_gdp,
            npl_ratio=new_npl,
            private_sector_credit_growth=new_credit_growth,
            last_drift_at=state.as_of + timedelta(days=days_elapsed),
        )

    # ── Discrete shocks ──────────────────────────────────────────

    def apply_shock(self, state: MacroState, *, shock: str,
                     **kwargs) -> MacroState:
        """Apply a discrete shock to the state.

        Recognised ``shock`` values:
          - ``cbr_change``    : kwargs[new_rate] sets CBK Central Bank Rate
          - ``fx_devaluation``: kwargs[pct] applies % change to USD/KES
          - ``credit_shock``  : kwargs[delta] adds to NPL ratio
          - ``inflation_spike``: kwargs[delta] adds to inflation
          - ``mof_budget``    : kwargs[gdp_revision] revises GDP growth
        """
        shock_at = kwargs.get("at") or state.as_of
        if shock == "cbr_change":
            new_rate = kwargs.get("new_rate")
            if new_rate is None:
                raise ValueError("cbr_change requires new_rate kwarg")
            # T-bill spreads typically widen on rate cuts, narrow on hikes
            d_cbr = new_rate - state.cbk_central_bank_rate
            return state.with_change(
                cbk_central_bank_rate=new_rate,
                treasury_91d=state.treasury_91d + d_cbr,
                treasury_182d=state.treasury_182d + d_cbr,
                treasury_364d=state.treasury_364d + d_cbr,
                interbank_rate=new_rate,
                last_shock_name="cbr_change",
                last_shock_at=shock_at,
            )
        if shock == "fx_devaluation":
            pct = kwargs.get("pct")
            if pct is None:
                raise ValueError("fx_devaluation requires pct kwarg")
            return state.with_change(
                usd_kes=state.usd_kes * (1 + pct),
                eur_kes=state.eur_kes * (1 + pct),
                gbp_kes=state.gbp_kes * (1 + pct),
                last_shock_name="fx_devaluation",
                last_shock_at=shock_at,
            )
        if shock == "credit_shock":
            delta = kwargs.get("delta", 0.0)
            new_npl = max(0.0, min(self.npl_ceiling,
                                     state.npl_ratio + delta))
            return state.with_change(
                npl_ratio=new_npl,
                last_shock_name="credit_shock",
                last_shock_at=shock_at,
            )
        if shock == "inflation_spike":
            delta = kwargs.get("delta", 0.0)
            new_infl = max(0.0, min(0.50, state.inflation_yoy + delta))
            return state.with_change(
                inflation_yoy=new_infl,
                last_shock_name="inflation_spike",
                last_shock_at=shock_at,
            )
        if shock == "mof_budget":
            gdp_rev = kwargs.get("gdp_revision", 0.0)
            new_gdp = max(-0.10, min(0.15, state.gdp_growth_yoy + gdp_rev))
            return state.with_change(
                gdp_growth_yoy=new_gdp,
                last_shock_name="mof_budget",
                last_shock_at=shock_at,
            )
        raise ValueError(f"unknown shock type: {shock}")

    # ── Internals ────────────────────────────────────────────────

    def _mean_reverting_step(self, current: float, long_run: float,
                                half_life_days: float, sigma_daily: float,
                                days_elapsed: float, *,
                                floor: float, ceiling: float) -> float:
        """One step of an OU mean-reverting process.

        Uses the analytical OU solution rather than Euler so that the
        step is stable for arbitrary days_elapsed:
            X(t+dt) = X_lr + (X(t) - X_lr) * exp(-k*dt)
                      + sigma_eq * Z

        Variance of the noise term is sigma_daily^2 * (1 - exp(-2*k*dt)) / (2*k).
        For small k*dt this reduces to sigma_daily * sqrt(dt) (Euler).
        For large k*dt the variance saturates to sigma_daily^2 / (2*k).
        """
        if days_elapsed <= 0 or half_life_days <= 0:
            return current
        k = math.log(2) / half_life_days
        decay = math.exp(-k * days_elapsed)
        # Equilibrium-variance noise (analytical OU)
        if k > 0:
            var = (sigma_daily ** 2) * (1.0 - math.exp(-2 * k * days_elapsed)) / (2 * k)
        else:
            var = sigma_daily ** 2 * days_elapsed
        sigma_eq = math.sqrt(max(var, 0.0))
        z = self.rng.gauss(0, 1)
        new_val = long_run + (current - long_run) * decay + sigma_eq * z
        return max(floor, min(ceiling, new_val))

    def _jitter(self, sigma_daily: float, days_elapsed: float) -> float:
        """Pure brownian noise without drift."""
        z = self.rng.gauss(0, 1)
        return sigma_daily * math.sqrt(max(days_elapsed, 1e-9)) * z


__all__ = ["MacroEvolution"]
