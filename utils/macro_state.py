"""utils/macro_state.py — Phase O4-B macro economic state.

Single source of truth for Kenya 2026 macro economic indicators. Held
as an immutable dataclass; evolution and shocks return a new state
rather than mutating in place. Singleton accessor mirrors the sim clock
pattern.

Baseline values: realistic Kenya 2026 figures based on:
  - CBK Monetary Policy Committee decisions through 2024-2025
  - 13-month T-bill auction averages
  - USD/KES central bank reference rate trends
  - World Bank Kenya GDP projections
  - Kenya Banking sector NPL ratio (CBK supervision reports)
  - Inflation Y-on-Y (Kenya National Bureau of Statistics)

This module is the data definition only. Drift/shock logic lives in
utils/macro_evolution.py and event scheduling in utils/macro_calendar.py.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, replace, field
from datetime import datetime, timezone
from typing import Optional


@dataclass(frozen=True)
class MacroState:
    """Snapshot of Kenya macro economic state at a moment in sim time.

    Rates are decimals (0.10 == 10%). FX rates are KES per unit of
    foreign currency (so usd_kes=130 means 1 USD = 130 KES).
    """
    as_of: datetime

    # ── Interest rates (decimals) ──────────────────────────────
    cbk_central_bank_rate: float = 0.10     # CBR
    treasury_91d: float = 0.13              # 91-day T-bill yield
    treasury_182d: float = 0.135            # 182-day T-bill yield
    treasury_364d: float = 0.14             # 364-day T-bill yield
    interbank_rate: float = 0.10            # interbank weighted average

    # ── FX rates (KES per foreign currency unit) ───────────────
    usd_kes: float = 130.0                  # CBK reference rate
    eur_kes: float = 141.0
    gbp_kes: float = 163.0
    usd_kes_bid_ask_spread: float = 0.005   # 50bps typical retail spread

    # ── Macro indicators ───────────────────────────────────────
    inflation_yoy: float = 0.055            # CBK target 5±2.5%
    gdp_growth_yoy: float = 0.055
    npl_ratio: float = 0.15                 # banking sector NPL/gross loans
    cash_reserve_ratio: float = 0.0425      # CRR (CBK statutory)
    liquidity_ratio: float = 0.50           # statutory min 20%
    private_sector_credit_growth: float = 0.08  # YoY

    # ── Provenance ─────────────────────────────────────────────
    last_drift_at: Optional[datetime] = None
    last_shock_name: str = ""
    last_shock_at: Optional[datetime] = None

    @classmethod
    def kenya_2026_baseline(cls, as_of: datetime) -> "MacroState":
        """The standard Kenya 2026 baseline at the requested sim moment."""
        if as_of.tzinfo is None:
            raise ValueError("as_of must be timezone-aware")
        return cls(as_of=as_of.astimezone(timezone.utc))

    def with_change(self, **kw) -> "MacroState":
        """Return a new MacroState with specified fields changed."""
        return replace(self, **kw)

    def to_dict(self) -> dict:
        """Serialise to dict (for emit / telemetry)."""
        return {
            "as_of": self.as_of.isoformat(),
            "cbk_central_bank_rate": round(self.cbk_central_bank_rate, 5),
            "treasury_91d": round(self.treasury_91d, 5),
            "treasury_182d": round(self.treasury_182d, 5),
            "treasury_364d": round(self.treasury_364d, 5),
            "interbank_rate": round(self.interbank_rate, 5),
            "usd_kes": round(self.usd_kes, 3),
            "eur_kes": round(self.eur_kes, 3),
            "gbp_kes": round(self.gbp_kes, 3),
            "usd_kes_bid_ask_spread": round(self.usd_kes_bid_ask_spread, 5),
            "inflation_yoy": round(self.inflation_yoy, 5),
            "gdp_growth_yoy": round(self.gdp_growth_yoy, 5),
            "npl_ratio": round(self.npl_ratio, 5),
            "cash_reserve_ratio": round(self.cash_reserve_ratio, 5),
            "liquidity_ratio": round(self.liquidity_ratio, 5),
            "private_sector_credit_growth":
                round(self.private_sector_credit_growth, 5),
            "last_drift_at": self.last_drift_at.isoformat()
                             if self.last_drift_at else None,
            "last_shock_name": self.last_shock_name,
            "last_shock_at": self.last_shock_at.isoformat()
                              if self.last_shock_at else None,
        }


# ── Module singleton accessor ───────────────────────────────────────

_GLOBAL_MACRO: Optional[MacroState] = None
_MACRO_LOCK = threading.Lock()


def get_macro_state() -> MacroState:
    """Return current global macro state (lazy-initialised at sim_now)."""
    global _GLOBAL_MACRO
    with _MACRO_LOCK:
        if _GLOBAL_MACRO is None:
            # Lazy import to avoid circular dep
            from utils.simulation_clock import sim_now
            _GLOBAL_MACRO = MacroState.kenya_2026_baseline(as_of=sim_now())
        return _GLOBAL_MACRO


def set_macro_state(state: MacroState) -> None:
    """Replace the global macro state. Used by evolution + shock logic."""
    global _GLOBAL_MACRO
    with _MACRO_LOCK:
        _GLOBAL_MACRO = state


def reset_macro_state() -> None:
    """Clear global state. Useful for test isolation."""
    global _GLOBAL_MACRO
    with _MACRO_LOCK:
        _GLOBAL_MACRO = None


__all__ = [
    "MacroState", "get_macro_state", "set_macro_state",
    "reset_macro_state",
]
