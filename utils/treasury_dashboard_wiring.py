"""utils.treasury_dashboard_wiring — factory for a fully-wired
TreasuryDashboardEngine (v10.302).

v10.296 shipped pages/110_treasury_live.py tab 7 (Dashboard
Report) backed by a bare `TreasuryDashboardEngine()` —
constructor defaults left all 5 upstream engine slots as None,
so `generate_daily_treasury()` returned a report with zero
sections. The cockpit displayed a banner saying this was the
next Phase 3 step.

This module is that next step. It wires the dashboard to all
five upstream engines:

  - utils.treasury_alm.TreasuryALMEngine        (ALM ratios)
  - utils.treasury_products.TreasuryProductsEngine (FX exposure)
  - utils.rwa_optimization.RWAOptimizationEngine (capital ratios)
  - utils.fund_transfer_pricing.FTPEngine        (NIM, FTP curves)
  - utils.cash_forecasting.TreasuryCashForecastingEngine
                                                  (cash forecast)

Wiring is safe even when upstream engines have no data: the
section builders return NO_DATA sections rather than crashing,
so the dashboard composes a real report shape regardless of
data freshness.

A `make_wired_dashboard()` factory is exposed for use by:
  - pages/110_treasury_live.py (tab 7 rendering)
  - utils/cockpit_read.treasury_daily_report (composer)
  - utils/api_cockpit (HTTP endpoint, via the composer)

Each call instantiates fresh engines — they are stateless
holders of configuration + ephemeral compute. The dashboard
itself is the only stateful part (it caches generated reports
by report_id), but the cockpit page wraps it in @st.cache_data
so multiple calls within the TTL share one report.
"""

from __future__ import annotations

from typing import Any

from utils.treasury_dashboard import TreasuryDashboardEngine


def make_wired_dashboard(
    entity_name: str = "Ecobank Kenya",
) -> TreasuryDashboardEngine:
    """Return a TreasuryDashboardEngine with all 5 upstream
    engines wired. Use this instead of `TreasuryDashboardEngine()`
    anywhere you need a non-empty daily/board/regulatory pack.

    Wiring is best-effort: each upstream engine is wrapped in
    a small try/except so a single import failure doesn't break
    the whole dashboard. Engines that fail to instantiate are
    left as None — board_summary will show them as `*_wired:
    False` and their sections will render NO_DATA, but the rest
    of the dashboard still composes."""
    alm_engine = _try_instantiate(
        "utils.treasury_alm", "TreasuryALMEngine")
    products_engine = _try_instantiate(
        "utils.treasury_products", "TreasuryProductsEngine")
    rwa_engine = _try_instantiate(
        "utils.rwa_optimization", "RWAOptimizationEngine")
    ftp_engine = _try_instantiate(
        "utils.fund_transfer_pricing", "FTPEngine")
    forecast_engine = _try_instantiate(
        "utils.cash_forecasting",
        "TreasuryCashForecastingEngine")

    return TreasuryDashboardEngine(
        entity_name=entity_name,
        alm_engine=alm_engine,
        products_engine=products_engine,
        rwa_engine=rwa_engine,
        ftp_engine=ftp_engine,
        forecast_engine=forecast_engine,
    )


def _try_instantiate(module_path: str, class_name: str) -> Any:
    """Best-effort engine instantiation. Returns the engine or
    None if import/instantiation fails. Failures are silent
    here because the dashboard renders NO_DATA cleanly for
    unwired engines; loud errors would break the whole cockpit
    tab when one engine has a transient issue.
    """
    try:
        import importlib
        mod = importlib.import_module(module_path)
        cls = getattr(mod, class_name)
        return cls()
    except Exception:
        return None
