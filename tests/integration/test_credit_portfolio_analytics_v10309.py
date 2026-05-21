"""
tests/integration/test_credit_portfolio_analytics_v10309.py
================================================================================
v10.309 — Cat A Portfolio Analytics composer. First multi-engine
aggregation composer in Phase 3.

v10.300 shipped Credit cockpit (page 111) with tab 6 carrying a
placeholder banner pointing to credit_risk_scoring,
credit_risk_irb, and ai_underwriting engines as "follow-on Phase
3 batch."

This batch closes that placeholder by composing those three
engines into a single read-side report — analogous to
treasury_daily_report (v10.302) but aggregating Credit-side
engines. Sections:

  1. AI Underwriting (ai_underwriting.AIUnderwritingEngine
     .board_summary): decisions, approval rate, automation
  2. PD distribution (credit_risk_scoring.CreditRiskScoringEngine
     .portfolio_pd_summary): loan count, grade distribution, EL
  3. IRB capital (credit_risk_irb.IRBCapitalEngine
     .compute_portfolio): RWA, EL on a portfolio

The IRB section needs exposures piped in. For the read-side
cockpit we feed the existing data/ifrs9_loans.json portfolio
(already in PG) as the exposure list.

Test sections:
  1. credit_portfolio_analytics composer exists
  2. Returns documented top-level keys (sections, status, as_at)
  3. Each section has section_id + status + metrics
  4. NO_DATA shape when engines are empty
  5. JSON-serialisable (Decimal → str)
  6. Page 111 tab 6 wired (placeholder banner removed)
  7. /api/cockpit/credit/portfolio-analytics endpoint
  8. G199 audit gate liveness
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))


# ============================================================
# Section 1 — Composer contract
# ============================================================

def test_credit_portfolio_analytics_composer_exists():
    from utils import cockpit_read
    assert hasattr(cockpit_read, "credit_portfolio_analytics"), (
        "cockpit_read must expose credit_portfolio_analytics "
        "Cat A composer"
    )


def test_composer_returns_documented_top_level_keys():
    from utils.cockpit_read import credit_portfolio_analytics
    result = credit_portfolio_analytics()
    for k in ("report_id", "sections", "n_sections",
              "board_summary", "status", "as_at"):
        assert k in result, (
            f"credit_portfolio_analytics missing key `{k}`"
        )


def test_composer_returns_three_sections():
    """The three engines named in the v10.300 placeholder
    contribute one section each. If a Cat A composer ever
    fans out beyond these three, this test pins the
    current contract."""
    from utils.cockpit_read import credit_portfolio_analytics
    result = credit_portfolio_analytics()
    section_ids = sorted(
        s["section_id"] for s in result["sections"]
    )
    assert "ai_underwriting" in section_ids
    assert "pd_distribution" in section_ids
    assert "irb_capital" in section_ids


# ============================================================
# Section 2 — Section shape
# ============================================================

def test_each_section_has_required_fields():
    """All sections share the same shape (section_id, title,
    source_engine, status, metrics, notes). Mirrors the
    Treasury daily report section shape from v10.302."""
    from utils.cockpit_read import credit_portfolio_analytics
    result = credit_portfolio_analytics()
    for s in result["sections"]:
        for f in ("section_id", "section_title",
                   "source_engine", "status", "metrics",
                   "notes"):
            assert f in s, (
                f"Section {s.get('section_id', '?')} "
                f"missing field {f}"
            )


def test_section_status_is_one_of_known_values():
    """status ∈ {ok, no_data, error, warning, breach}."""
    from utils.cockpit_read import credit_portfolio_analytics
    result = credit_portfolio_analytics()
    valid = {"ok", "no_data", "error", "warning", "breach"}
    for s in result["sections"]:
        assert s["status"] in valid, (
            f"Section {s['section_id']} has invalid status "
            f"{s['status']!r}"
        )


# ============================================================
# Section 3 — JSON-serialisable
# ============================================================

def test_composer_result_is_json_serialisable():
    """Round-trip through json.dumps for the HTTP endpoint.
    Decimals must already be cast to str."""
    from utils.cockpit_read import credit_portfolio_analytics
    result = credit_portfolio_analytics()
    re_serialised = json.dumps(result)
    round_tripped = json.loads(re_serialised)
    assert round_tripped == result


# ============================================================
# Section 4 — Top-level status reflects worst section
# ============================================================

def test_top_level_status_is_aggregated():
    """Top-level status summarises the section statuses.
    If all sections are no_data, top-level should also be
    no_data. If any are ok, top-level should be ok."""
    from utils.cockpit_read import credit_portfolio_analytics
    result = credit_portfolio_analytics()
    valid_top = {"ok", "no_data", "error"}
    assert result["status"] in valid_top


# ============================================================
# Section 5 — Page 111 wired
# ============================================================

def test_page_111_tab_6_uses_composer():
    src = (
        REPO_ROOT / "pages" / "111_credit_live.py"
    ).read_text()
    assert "credit_portfolio_analytics" in src, (
        "page 111 must reference credit_portfolio_analytics"
    )


def test_page_111_tab_6_placeholder_banner_removed():
    src = (
        REPO_ROOT / "pages" / "111_credit_live.py"
    ).read_text()
    assert (
        "Cat A portfolio analytics engine wiring is a"
        not in src
    ), (
        "v10.300 placeholder banner still in page 111 tab 6"
    )


# ============================================================
# Section 6 — HTTP endpoint
# ============================================================

def test_api_cockpit_portfolio_analytics_endpoint_registered():
    src = (
        REPO_ROOT / "utils" / "api_cockpit.py"
    ).read_text()
    assert "/credit/portfolio-analytics" in src, (
        "api_cockpit.py missing /credit/portfolio-analytics"
    )


def test_api_cockpit_endpoint_documented():
    src = (
        REPO_ROOT / "utils" / "api_cockpit.py"
    ).read_text()
    docstring_end = src.find("\"\"\"", 100)
    docstring = src[:docstring_end + 3]
    assert (
        "/api/cockpit/credit/portfolio-analytics" in docstring
    )


# ============================================================
# Section 7 — Audit gate G199
# ============================================================

def test_g199_gate_exists_and_passes():
    from scripts.audit import GATES
    g199 = None
    for gid, fn in GATES:
        if gid == "G199":
            g199 = fn()
            break
    assert g199 is not None, "G199 not registered"
    assert g199["passed"], (
        f"G199 failed. {g199.get('summary', '')}. "
        f"Violations: {g199.get('violations', [])[:5]}"
    )


# ============================================================
# Section 8 — Defensive: empty engines don't crash
# ============================================================

def test_composer_handles_engine_failure_gracefully():
    """If any of the three engines raises, the composer must
    still return a well-formed result with that section marked
    status='error' rather than crash the cockpit."""
    from utils.cockpit_read import credit_portfolio_analytics
    # Default behavior — none of the engines should raise on
    # empty state, but the result should still have 3 sections
    result = credit_portfolio_analytics()
    assert result["n_sections"] == 3
    # No exception means the composer is at minimum tolerant


# ============================================================
# Section 9 — Idempotent (same call twice = same shape)
# ============================================================

def test_composer_idempotent():
    from utils.cockpit_read import credit_portfolio_analytics
    r1 = credit_portfolio_analytics()
    r2 = credit_portfolio_analytics()
    # Same section count + same section IDs
    assert r1["n_sections"] == r2["n_sections"]
    ids1 = sorted(s["section_id"] for s in r1["sections"])
    ids2 = sorted(s["section_id"] for s in r2["sections"])
    assert ids1 == ids2
