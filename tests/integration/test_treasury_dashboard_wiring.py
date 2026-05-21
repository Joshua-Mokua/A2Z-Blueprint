"""
tests/integration/test_treasury_dashboard_wiring.py
================================================================================
v10.302 — TreasuryDashboardEngine wiring tests, written
BEFORE the wiring per Kaizen TDD.

v10.296 shipped pages/110_treasury_live.py with tab 7
(Dashboard report) using an UNWIRED TreasuryDashboardEngine:
default constructor produced `n_sections = 0` because no
upstream engines were injected. The cockpit displayed an
informational banner saying "next Phase 3 step: connect ALM/
Products/RWA/FTP/Forecast engines."

This batch closes that gap. The dashboard is wired with all
5 upstream engines, so the daily treasury report composes
real sections (or NO_DATA sections that gracefully render
their unpopulated state — both are improvements over zero
sections).

Test sections:
  1. _cached_dashboard_report returns wired engine state
  2. board_summary shows all 5 engines wired
  3. Section count is non-zero for the daily report
  4. Section count matches the count of wired engines × per-
     engine section count documented in the dashboard module
  5. Page 110 references TreasuryDashboardEngine + injects
     the 5 engines (greppable invariant)
  6. The "0 sections — upstream engines not wired" banner is
     gone from page 110
  7. Cockpit_read exposes a new treasury_daily_report composer
     that returns the report dict (React-readiness invariant)
  8. HTTP endpoint /api/cockpit/treasury/daily-report exists
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))


# ============================================================
# Section 1 — Wiring helper exists and instantiates
# ============================================================

def test_treasury_wired_dashboard_helper_exists():
    """A factory helper must exist that instantiates
    TreasuryDashboardEngine with all 5 upstream engines.
    Living in utils/treasury_dashboard_wiring.py so it can
    be imported by page 110 + tests + API."""
    from utils import treasury_dashboard_wiring
    assert hasattr(treasury_dashboard_wiring,
                    "make_wired_dashboard")


def test_make_wired_dashboard_returns_engine_with_all_5_slots():
    """The factory must return a TreasuryDashboardEngine with
    alm_engine, products_engine, rwa_engine, ftp_engine, and
    forecast_engine all non-None."""
    from utils.treasury_dashboard_wiring import (
        make_wired_dashboard,
    )
    dash = make_wired_dashboard()
    for slot in ("alm_engine", "products_engine", "rwa_engine",
                  "ftp_engine", "forecast_engine"):
        assert getattr(dash, slot) is not None, (
            f"make_wired_dashboard returned a dashboard with "
            f"{slot} = None. All 5 slots must be wired."
        )


def test_make_wired_dashboard_board_summary_shows_all_wired():
    """board_summary must report all five `*_wired: True`."""
    from utils.treasury_dashboard_wiring import (
        make_wired_dashboard,
    )
    dash = make_wired_dashboard()
    summary = dash.board_summary()
    for flag in ("alm_wired", "products_wired", "rwa_wired",
                  "ftp_wired", "forecast_wired"):
        assert summary.get(flag) is True, (
            f"board_summary().{flag} should be True; got "
            f"{summary.get(flag)}"
        )


# ============================================================
# Section 2 — Daily report has sections after wiring
# ============================================================

def test_daily_report_has_sections_when_wired():
    """generate_daily_treasury on a wired dashboard must
    return at least one section. The whole point of v10.302."""
    from utils.treasury_dashboard_wiring import (
        make_wired_dashboard,
    )
    dash = make_wired_dashboard()
    report = dash.generate_daily_treasury(
        report_id="TEST-DAILY",
        as_of_date="2026-05-11",
    )
    assert len(report.sections) > 0, (
        f"Wired dashboard produced {len(report.sections)} "
        f"sections — should be ≥1 (LCR + NSFR from ALM, plus "
        f"products + forecast)"
    )


def test_daily_report_includes_lcr_and_nsfr_sections():
    """build_alm_lcr_section + build_alm_nsfr_section must
    fire when alm_engine is wired."""
    from utils.treasury_dashboard_wiring import (
        make_wired_dashboard,
    )
    dash = make_wired_dashboard()
    report = dash.generate_daily_treasury(
        report_id="TEST-DAILY-LCR",
        as_of_date="2026-05-11",
    )
    section_ids = [s.section_id for s in report.sections]
    assert "alm_lcr" in section_ids, (
        f"alm_lcr section missing. Sections: {section_ids}"
    )
    assert "alm_nsfr" in section_ids, (
        f"alm_nsfr section missing. Sections: {section_ids}"
    )


# ============================================================
# Section 3 — Page 110 uses the wired factory
# ============================================================

def test_page_110_uses_wired_factory():
    """pages/110_treasury_live.py must import + call the wired
    factory, not the bare TreasuryDashboardEngine constructor."""
    src = (
        REPO_ROOT / "pages" / "110_treasury_live.py"
    ).read_text()
    assert "make_wired_dashboard" in src, (
        "page 110 must use make_wired_dashboard() from "
        "treasury_dashboard_wiring"
    )


def test_page_110_zero_sections_banner_removed():
    """The 'No sections in report — upstream engines not yet
    wired' banner must be gone from page 110 after this
    batch."""
    src = (
        REPO_ROOT / "pages" / "110_treasury_live.py"
    ).read_text()
    # Old placeholder text — should no longer appear
    assert "next Phase 3 step: connect ALM" not in src, (
        "Old 'next Phase 3 step' placeholder banner still "
        "present in page 110. After v10.302 wiring it should "
        "be removed."
    )


# ============================================================
# Section 4 — cockpit_read composer for React-readiness
# ============================================================

def test_treasury_daily_report_composer_exists():
    """utils.cockpit_read must expose treasury_daily_report
    so the React SPA can fetch the same report the cockpit
    renders."""
    from utils import cockpit_read
    assert hasattr(cockpit_read, "treasury_daily_report"), (
        "cockpit_read missing treasury_daily_report composer"
    )


def test_treasury_daily_report_returns_documented_keys():
    """treasury_daily_report must return a dict with at least:
    report_id, as_of_date, n_sections, sections, board_summary."""
    from utils.cockpit_read import treasury_daily_report
    result = treasury_daily_report(as_of_date="2026-05-11")
    for k in ("report_id", "as_of_date", "n_sections",
              "sections", "board_summary"):
        assert k in result, (
            f"treasury_daily_report missing key `{k}`"
        )


def test_treasury_daily_report_json_serialisable():
    """Result must round-trip cleanly through json.dumps for
    the HTTP endpoint."""
    import json
    from utils.cockpit_read import treasury_daily_report
    result = treasury_daily_report(as_of_date="2026-05-11")
    re_serialised = json.dumps(result)
    round_tripped = json.loads(re_serialised)
    assert round_tripped == result


def test_treasury_daily_report_has_nonzero_sections():
    """The composer's n_sections must be > 0 (matches the
    wired dashboard's section count)."""
    from utils.cockpit_read import treasury_daily_report
    result = treasury_daily_report(as_of_date="2026-05-11")
    assert result["n_sections"] > 0, (
        f"treasury_daily_report produced {result['n_sections']} "
        f"sections — should be ≥1 after wiring"
    )


# ============================================================
# Section 5 — HTTP endpoint
# ============================================================

def test_api_cockpit_exposes_daily_report_endpoint():
    """/api/cockpit/treasury/daily-report must be registered
    in utils/api_cockpit.py. Static check — works without
    FastAPI installed."""
    src = (
        REPO_ROOT / "utils" / "api_cockpit.py"
    ).read_text()
    assert "/treasury/daily-report" in src, (
        "api_cockpit.py missing /treasury/daily-report endpoint"
    )


def test_api_cockpit_endpoint_documented():
    """Module docstring must list the new endpoint per the
    documentation contract."""
    src = (
        REPO_ROOT / "utils" / "api_cockpit.py"
    ).read_text()
    # The endpoint path should appear in the module docstring
    docstring_end = src.find("\"\"\"", 100)  # end of module ds
    docstring = src[:docstring_end + 3]
    assert "/api/cockpit/treasury/daily-report" in docstring, (
        "treasury/daily-report not in module docstring"
    )


# ============================================================
# Section 6 — Audit gate
# ============================================================

def test_g193_gate_exists_and_passes():
    """After wiring, G193 must report PASS."""
    from scripts.audit import GATES
    g193 = None
    for gid, fn in GATES:
        if gid == "G193":
            g193 = fn()
            break
    assert g193 is not None, "G193 gate not registered"
    assert g193["passed"], (
        f"G193 failed. Summary: {g193.get('summary', '')}. "
        f"Violations: {g193.get('violations', [])[:5]}"
    )
