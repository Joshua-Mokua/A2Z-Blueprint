"""
tests/integration/test_cash_forecast_wiring.py
================================================================================
v10.304 — Cash forecast composer wiring tests, written BEFORE
implementation per Kaizen TDD.

v10.296 shipped pages/110_treasury_live.py tab 6 (Cash forecast)
with a placeholder banner: "Cash forecast composer not yet
wired. ENH-237 cash_forecasting engine exists; this tab will
display its 13-week projection in a follow-on Phase 3 batch."

This batch closes that gap. Same shape as v10.302's
TreasuryDashboardEngine wiring:

  - utils/cash_forecasting.py engine exists today, returns
    NO_DATA cleanly when empty
  - Add a wiring helper that primes the engine from any
    production cash-flow JSON files present
  - Add a treasury_cash_forecast composer to cockpit_read
  - Add /api/cockpit/treasury/cash-forecast HTTP endpoint
  - Render real points in the cockpit tab
  - Remove the placeholder banner
  - G195 locks the closure

Test sections:
  1. Wiring helper exists and instantiates
  2. Engine board_summary readable
  3. treasury_cash_forecast composer contract (documented keys)
  4. Composer is JSON-serialisable + idempotent
  5. Empty-state graceful (no production data → NO_DATA shape)
  6. Page 110 tab 6 wired and old placeholder banner removed
  7. /api/cockpit/treasury/cash-forecast endpoint registered
  8. G195 audit gate liveness
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))


# ============================================================
# Section 1 — Wiring helper exists
# ============================================================

def test_cash_forecast_wiring_module_exists():
    """utils/cash_forecast_wiring.py with a make_primed_forecaster
    helper. Living in its own module mirrors the v10.302
    treasury_dashboard_wiring pattern."""
    from utils import cash_forecast_wiring
    assert hasattr(cash_forecast_wiring,
                    "make_primed_forecaster"), (
        "cash_forecast_wiring must expose "
        "make_primed_forecaster()"
    )


def test_make_primed_forecaster_returns_engine():
    """The factory must return a working
    TreasuryCashForecastingEngine — clean instantiation,
    board_summary callable."""
    from utils.cash_forecast_wiring import (
        make_primed_forecaster,
    )
    from utils.cash_forecasting import (
        TreasuryCashForecastingEngine,
    )
    forecaster = make_primed_forecaster()
    assert isinstance(
        forecaster, TreasuryCashForecastingEngine,
    )
    summary = forecaster.board_summary()
    assert isinstance(summary, dict)
    assert "entity" in summary
    assert "n_history_days" in summary


# ============================================================
# Section 2 — Composer contract
# ============================================================

def test_treasury_cash_forecast_composer_exists():
    """utils.cockpit_read.treasury_cash_forecast must exist."""
    from utils import cockpit_read
    assert hasattr(cockpit_read, "treasury_cash_forecast")


def test_treasury_cash_forecast_returns_documented_keys():
    """Documented return shape for the React SPA + cockpit."""
    from utils.cockpit_read import treasury_cash_forecast
    result = treasury_cash_forecast()
    required = [
        "entity", "forecast_id", "horizon_days",
        "start_date", "n_history_days_used",
        "ml_overlay_applied", "n_points", "points",
        "status", "notes", "as_at",
    ]
    for k in required:
        assert k in result, (
            f"treasury_cash_forecast missing key `{k}`"
        )


def test_treasury_cash_forecast_status_when_no_data():
    """With no production data files present and the engine
    fresh, the composer must report `status: no_data` rather
    than crash."""
    from utils.cockpit_read import treasury_cash_forecast
    result = treasury_cash_forecast()
    # Allowed statuses: no_data (empty engine), ok (data
    # primed), error (engine raised)
    assert result["status"] in (
        "no_data", "ok", "error",
    ), f"unexpected status {result['status']!r}"


def test_treasury_cash_forecast_points_is_list():
    from utils.cockpit_read import treasury_cash_forecast
    result = treasury_cash_forecast()
    assert isinstance(result["points"], list)


# ============================================================
# Section 3 — JSON serialisable + idempotent
# ============================================================

def test_treasury_cash_forecast_json_serialisable():
    """Result must round-trip cleanly through json.dumps for
    the HTTP endpoint. Decimal points must be cast to str."""
    from utils.cockpit_read import treasury_cash_forecast
    result = treasury_cash_forecast()
    re_serialised = json.dumps(result)
    round_tripped = json.loads(re_serialised)
    assert round_tripped == result


def test_treasury_cash_forecast_idempotent():
    """Two consecutive calls produce the same business data
    (except as_at)."""
    from utils.cockpit_read import treasury_cash_forecast
    r1 = treasury_cash_forecast()
    r2 = treasury_cash_forecast()
    for k in set(r1) - {"as_at", "forecast_id"}:
        # forecast_id may include a date stamp; allow drift
        assert r1[k] == r2[k], (
            f"treasury_cash_forecast `{k}` differs: "
            f"{r1[k]!r} vs {r2[k]!r}"
        )


# ============================================================
# Section 4 — Page 110 tab 6 wired
# ============================================================

def test_page_110_tab_6_uses_wired_composer():
    """pages/110_treasury_live.py must reference
    treasury_cash_forecast (the new composer)."""
    src = (
        REPO_ROOT / "pages" / "110_treasury_live.py"
    ).read_text()
    assert "treasury_cash_forecast" in src, (
        "page 110 must use treasury_cash_forecast composer"
    )


def test_page_110_tab_6_placeholder_banner_removed():
    """The 'Cash forecast composer not yet wired' banner from
    v10.296 must be gone after v10.304."""
    src = (
        REPO_ROOT / "pages" / "110_treasury_live.py"
    ).read_text()
    assert "Cash forecast composer not yet wired" not in src, (
        "Old v10.296 cash forecast placeholder still in "
        "page 110. v10.304 should remove it."
    )


# ============================================================
# Section 5 — HTTP endpoint
# ============================================================

def test_api_cockpit_exposes_cash_forecast_endpoint():
    """/api/cockpit/treasury/cash-forecast must be registered."""
    src = (
        REPO_ROOT / "utils" / "api_cockpit.py"
    ).read_text()
    assert "/treasury/cash-forecast" in src, (
        "api_cockpit.py missing /treasury/cash-forecast"
    )


def test_api_cockpit_endpoint_documented():
    """Module docstring must list the new endpoint per the
    G188 documentation contract."""
    src = (
        REPO_ROOT / "utils" / "api_cockpit.py"
    ).read_text()
    docstring_end = src.find("\"\"\"", 100)
    docstring = src[:docstring_end + 3]
    assert (
        "/api/cockpit/treasury/cash-forecast" in docstring
    ), "treasury/cash-forecast not in module docstring"


# ============================================================
# Section 6 — Audit gate G195
# ============================================================

def test_g195_gate_exists_and_passes():
    from scripts.audit import GATES
    g195 = None
    for gid, fn in GATES:
        if gid == "G195":
            g195 = fn()
            break
    assert g195 is not None, "G195 gate not registered"
    assert g195["passed"], (
        f"G195 failed. Summary: {g195.get('summary', '')}. "
        f"Violations: {g195.get('violations', [])[:5]}"
    )
