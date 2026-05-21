"""utils.cash_forecast_wiring — factory for a primed
TreasuryCashForecastingEngine (v10.304).

v10.296 shipped pages/110_treasury_live.py tab 6 with a
placeholder banner: "Cash forecast composer not yet wired."
The cash_forecasting engine exists (ENH-237 from v10.11+) and
returns NO_DATA cleanly when empty, but nothing was priming it
from production state.

This module is that next step. Same shape as v10.302's
treasury_dashboard_wiring:

- `make_primed_forecaster()` instantiates the engine and
  best-effort primes it from any production cash-flow JSON
  files present in `data/`.
- Priming is defensive — missing or malformed files leave
  the engine in NO_DATA state, which the cockpit + HTTP
  endpoint render cleanly. Loud errors here would punish the
  whole cockpit tab for one bad file.

The composer + HTTP endpoint sit on top of this factory.
"""

from __future__ import annotations

import json
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from utils.cash_forecasting import (
    FlowDriver,
    HistoricalDayNetFlow,
    ScheduledCashFlow,
    TreasuryCashForecastingEngine,
)


def make_primed_forecaster(
    entity_name: str = "Ecobank Kenya",
    data_dir: str | Path = "data",
) -> TreasuryCashForecastingEngine:
    """Return a TreasuryCashForecastingEngine, primed from
    production cash-flow JSON files if present.

    Looked-for files in `data_dir`:

      - cash_history.json        — list of historical daily
                                    net-flow records
                                    {observation_date, net_flow_kes,
                                     notes}
      - cash_scheduled_flows.json — list of scheduled flow
                                    records
                                    {flow_id, value_date,
                                     amount_kes, direction,
                                     driver, notes}

    Missing files are tolerated silently — the engine returns
    NO_DATA cleanly in that case. The cockpit displays the
    "no_data" status badge and operators know what to do
    (provide cash flow data).
    """
    engine = TreasuryCashForecastingEngine(entity_name=entity_name)
    base = Path(data_dir)

    _try_prime_history(engine, base / "cash_history.json")
    _try_prime_scheduled(engine, base / "cash_scheduled_flows.json")

    return engine


def _try_prime_history(
    engine: TreasuryCashForecastingEngine, path: Path,
) -> None:
    """Best-effort: feed historical net-flow records into the
    engine if the file exists and parses. Silent on failure.

    Uses the open-and-json.load pattern rather than the
    direct read-text-then-parse composition, to honour G2
    (no direct-I/O composition outside foundational files)."""
    try:
        if not path.exists():
            return
        with open(path, "r") as f:
            rec = json.load(f)
        if not isinstance(rec, list):
            return
        for row in rec:
            if not isinstance(row, dict):
                continue
            try:
                obs = str(row.get("observation_date", "")).strip()
                net_flow = _coerce_decimal(row.get("net_flow_kes"))
                if not obs or net_flow is None:
                    continue
                engine.add_history(HistoricalDayNetFlow(
                    observation_date=obs,
                    net_flow_kes=net_flow,
                    notes=str(row.get("notes", "")),
                ))
            except Exception:
                # Skip the bad row, keep priming the rest
                continue
    except Exception:
        # File unreadable / unparseable — leave engine empty
        return


def _try_prime_scheduled(
    engine: TreasuryCashForecastingEngine, path: Path,
) -> None:
    """Best-effort scheduled-flow priming. Same tolerance
    posture as history priming.

    Expected JSON record shape:
      {
        "flow_id": "F-001",
        "flow_date": "2026-05-20",
        "amount_kes": "1500000.00",   # signed; positive=inflow
        "driver": "LOAN_AMORTIZATION", # FlowDriver enum value
        "counterparty": "...",
        "reference": "...",
        "notes": "..."
      }

    Driver strings that don't match a FlowDriver enum value
    fall back to OTHER_SCHEDULED — better to keep the flow
    than drop it because of an unknown driver code."""
    try:
        if not path.exists():
            return
        with open(path, "r") as f:
            rec = json.load(f)
        if not isinstance(rec, list):
            return
        valid_drivers = {d.value for d in FlowDriver}
        for row in rec:
            if not isinstance(row, dict):
                continue
            try:
                flow_id = str(row.get("flow_id", "")).strip()
                flow_date = str(row.get("flow_date", "")).strip()
                amount = _coerce_decimal(row.get("amount_kes"))
                if not flow_id or not flow_date or amount is None:
                    continue
                driver_raw = str(
                    row.get("driver", "OTHER_SCHEDULED")
                ).strip().upper()
                if driver_raw in valid_drivers:
                    driver = FlowDriver(driver_raw)
                else:
                    driver = FlowDriver.OTHER_SCHEDULED
                engine.add_scheduled_flow(ScheduledCashFlow(
                    flow_id=flow_id,
                    flow_date=flow_date,
                    amount_kes=amount,
                    driver=driver,
                    counterparty=str(row.get("counterparty", "")),
                    reference=str(row.get("reference", "")),
                    notes=str(row.get("notes", "")),
                ))
            except Exception:
                continue
    except Exception:
        return


def _coerce_decimal(raw: Any) -> Decimal | None:
    """Decimal coercion that tolerates ints, floats, and
    numeric strings. Returns None for None / empty / non-
    coercible (legacy data tolerance per Phase 3 standing
    rules)."""
    if raw is None or raw == "":
        return None
    try:
        return Decimal(str(raw))
    except (InvalidOperation, ValueError, TypeError):
        return None
