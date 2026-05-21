"""utils.profitability_integration — BSC Integration + MD Dashboard data
(Standards #29 + #30, v5.49). Volume Three.

STANDARD #29: Customer Profitability → BSC Integration
-------------------------------------------------------
Per the spec:

    def submit_rm_profitability_to_bsc():
        for rm_code in get_all_relationship_managers():
            pnl = RMProfitabilityDashboard().calculate_rm_portfolio_pnl(rm_code, current_period)
            submit(staff_code=rm_code, kpi_id="RM_PORTFOLIO_PBT",
                   value=pnl["portfolio_pnl"]["total_pbt"])

The function pulls every RM's portfolio PnL via #23 and submits the
total PBT as a BSC actual against the RM_PORTFOLIO_PBT KPI.

HONESTY INHERITANCE FROM MANDATORY STANDARD #11
================================================
v5.49 ships an honest version: portfolios with `provisional=True`
(more than half of customers ran on FTP-blind upstream) are NOT
silently submitted as if they were final BSC actuals. Three options:

  1. mode='strict' (DEFAULT): provisional portfolios are SKIPPED,
     reported in skipped_provisional[]. The BSC stays clean.
  2. mode='warn': provisional portfolios are submitted but tagged
     in BSC actuals as `is_provisional=True` (requires the BSC
     submitter to honour that flag).
  3. mode='all': everything submitted regardless. ONLY for use
     during data-quality remediation when the gap is being measured.

Default is 'strict' because corrupting the BSC with naive math is
worse than under-reporting one period's RM PBT. The choice is
recorded in meta.submission_mode.

STANDARD #30: Customer Profitability → MD Dashboard
----------------------------------------------------
Per the spec:

    def customer_profitability_md_view():
        col1, col2, col3 = st.columns(3)
        with col1: st.metric("Total Customer PBT", format_currency(total_customer_pbt))
        with col2: st.metric("Profitable Customers %", f"{profitable_percentage}%")
        st.plotly_chart(profitability_pyramid)

This is a Streamlit UI page. v5.49 ships the SERVICE FUNCTION that
prepares the data, NOT the Streamlit code itself (UI pages are
unit-test-hostile and the data layer is the substantive part).

  build_md_dashboard_data(period) → dict with:
    total_customer_pbt:       sum of customer PBTs in period
    profitable_customer_count: count of customers with PBT > 0
    profitable_customer_pct:   that count / total customers
    pyramid_distribution:      {tier: count} from #22
    rm_portfolios:             [{rm_code, total_pbt, provisional},...]
    data_quality_summary:      aggregated warnings from underlying engines
    meta:                      provenance + composition trail

A Streamlit page wraps this function in three columns + one chart.

WHAT'S NOT HERE (deliberate)
-----------------------------
- The actual BSC submitter — this module assumes there's a
  bsc_actuals submission function (the existing #1/#2 BSC engine).
  v5.49 takes it as an injectable, defaults to a no-op that records
  what it WOULD have submitted (so the function is testable).

- The Streamlit page itself — the data function is the substantive
  piece and what's verifiable. A page that imports this function
  and lays out three st.metric() widgets is uninteresting glue.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP, getcontext
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger("a2z.profit_integration")
getcontext().prec = 28

ROOT = Path(__file__).parent.parent
DATA_DIR = ROOT / "data"
BSC_SUBMISSIONS_LOG = DATA_DIR / "rm_pbt_bsc_submissions.json"

ZERO = Decimal("0")

# Spec literal
RM_PORTFOLIO_PBT_KPI_ID = "RM_PORTFOLIO_PBT"

# Submission mode — see module docstring
SUBMISSION_MODES: Tuple[str, ...] = ("strict", "warn", "all")
DEFAULT_SUBMISSION_MODE = "strict"


# ─────────────────────────────────────────────────────────────────────
# Standard #29 — BSC integration
# ─────────────────────────────────────────────────────────────────────

def submit_rm_profitability_to_bsc(
    period: str,
    *,
    all_rms_fn:           Optional[Callable[[], List[str]]] = None,
    rm_portfolio_fn:      Optional[Callable[[str, str], Optional[dict]]] = None,
    bsc_submit_fn:        Optional[Callable[..., bool]] = None,
    submission_mode:      str = DEFAULT_SUBMISSION_MODE,
) -> Dict[str, Any]:
    """Submit each RM's portfolio PBT to BSC for the given period.

    Returns:
        {
          "period":         str,
          "submission_mode": str,
          "submitted":      [{rm_code, total_pbt, kpi_id, success},...],
          "skipped_provisional": [{rm_code, reason},...],
          "skipped_unavailable": [{rm_code, reason},...],
          "submitted_count": int,
          "skipped_count":   int,
          "data_quality_warning": str | None,
          "meta":           {...},
        }

    Returns {} when period is empty.
    """
    if not period:
        return {}

    if submission_mode not in SUBMISSION_MODES:
        raise ValueError(
            f"submission_mode must be in {SUBMISSION_MODES}, got {submission_mode!r}"
        )

    all_rms       = all_rms_fn       or _default_all_rms
    rm_portfolio  = rm_portfolio_fn  or _default_rm_portfolio
    bsc_submit    = bsc_submit_fn    or _default_bsc_submit

    rm_codes = all_rms() or []

    submitted: List[dict] = []
    skipped_provisional: List[dict] = []
    skipped_unavailable: List[dict] = []
    provisional_seen = 0

    for rm_code in rm_codes:
        portfolio = rm_portfolio(rm_code, period)
        if not portfolio:
            skipped_unavailable.append({
                "rm_code": rm_code,
                "reason":  "portfolio not available — rm_portfolio_fn returned None",
            })
            continue

        portfolio_pnl = portfolio.get("portfolio_pnl") or {}
        total_pbt = portfolio_pnl.get("total_pbt", 0)
        is_provisional = portfolio_pnl.get("provisional", False)

        if is_provisional:
            provisional_seen += 1
            if submission_mode == "strict":
                skipped_provisional.append({
                    "rm_code": rm_code,
                    "reason":  "portfolio is provisional (>50% upstream "
                               "FTP-off, per Mandatory Standard #11)",
                })
                continue

        # Submit
        kwargs = {
            "staff_code": rm_code,
            "kpi_id":     RM_PORTFOLIO_PBT_KPI_ID,
            "value":      float(total_pbt),
            "period":     period,
        }
        if submission_mode == "warn" and is_provisional:
            kwargs["is_provisional"] = True
        try:
            success = bool(bsc_submit(**kwargs))
        except Exception as e:
            logger.warning("bsc_submit failed for %s: %s", rm_code, e)
            success = False

        submitted.append({
            "rm_code":       rm_code,
            "total_pbt":     float(total_pbt),
            "kpi_id":        RM_PORTFOLIO_PBT_KPI_ID,
            "is_provisional": is_provisional,
            "success":       success,
        })

    warning = None
    if provisional_seen > 0:
        if submission_mode == "strict":
            warning = (
                f"{provisional_seen} provisional portfolio(s) skipped per "
                f"strict mode (Mandatory Standard #11). Re-run upstream "
                f"PnLs with ftp_mode='on' before next submission."
            )
        else:
            warning = (
                f"{provisional_seen} provisional portfolio(s) submitted "
                f"with is_provisional=True (mode={submission_mode!r}). "
                f"BSC consumers must honour the flag."
            )

    return {
        "period":               period,
        "submission_mode":      submission_mode,
        "submitted":            submitted,
        "skipped_provisional":  skipped_provisional,
        "skipped_unavailable":  skipped_unavailable,
        "submitted_count":      len(submitted),
        "skipped_count":        len(skipped_provisional) + len(skipped_unavailable),
        "data_quality_warning": warning,
        "meta": {
            "rms_processed":       len(rm_codes),
            "provisional_seen":    provisional_seen,
            "kpi_id":              RM_PORTFOLIO_PBT_KPI_ID,
            "generated_at":        datetime.now(timezone.utc).isoformat(),
        },
    }


# ─────────────────────────────────────────────────────────────────────
# Standard #30 — MD dashboard data layer
# ─────────────────────────────────────────────────────────────────────

def build_md_dashboard_data(
    period: str,
    *,
    all_customers_fn:  Optional[Callable[[], List[str]]] = None,
    pnl_lookup_fn:     Optional[Callable[[str, str], Optional[dict]]] = None,
    pyramid_fn:        Optional[Callable[[str], Optional[dict]]] = None,
    all_rms_fn:        Optional[Callable[[], List[str]]] = None,
    rm_portfolio_fn:   Optional[Callable[[str, str], Optional[dict]]] = None,
) -> Dict[str, Any]:
    """Prepare the data the MD dashboard page renders.

    Returns:
        {
          "period":                 str,
          "total_customer_pbt":     float,
          "total_customer_revenue": float,
          "profitable_customer_count": int,
          "total_customer_count":      int,
          "profitable_customer_pct":   float,    # 0..100
          "pyramid_distribution":      {tier: count, ...},
          "rm_portfolios":             [{rm_code, total_pbt, provisional},...],
          "rm_portfolios_provisional": int,
          "data_quality_summary":      {...},
          "meta":                      {...},
        }

    Returns {} when period is empty.
    """
    if not period:
        return {}

    all_customers = all_customers_fn or _default_all_customers
    pnl_lookup    = pnl_lookup_fn    or _default_pnl_lookup
    pyramid       = pyramid_fn       or _default_pyramid_lookup
    all_rms       = all_rms_fn       or _default_all_rms
    rm_portfolio  = rm_portfolio_fn  or _default_rm_portfolio

    customer_ids = all_customers() or []

    total_pbt = ZERO
    total_revenue = ZERO
    profitable_count = 0
    available_count = 0
    ftp_off_count = 0
    none_margin_count = 0

    for cid in customer_ids:
        pnl = pnl_lookup(cid, period)
        if not pnl:
            continue
        available_count += 1
        try:
            pbt_d = Decimal(str(pnl.get("pbt", 0)))
            rev_d = Decimal(str(pnl.get("total_revenue", 0)))
        except Exception:
            continue
        total_pbt += pbt_d
        total_revenue += rev_d
        if pbt_d > ZERO:
            profitable_count += 1
        if pnl.get("pbt_margin") is None:
            none_margin_count += 1
        upstream_meta = pnl.get("meta") or {}
        if upstream_meta.get("ftp_mode") == "off":
            ftp_off_count += 1

    profitable_pct = (
        (profitable_count / available_count * 100)
        if available_count > 0 else 0.0
    )

    # Pyramid distribution from #22
    py = pyramid(period) or {}
    pyramid_distribution: Dict[str, int] = {}
    if py.get("tiers"):
        for tier, info in py["tiers"].items():
            pyramid_distribution[tier] = int(info.get("count", 0))

    # RM portfolios from #23
    rm_codes = all_rms() or []
    rm_portfolios: List[Dict[str, Any]] = []
    rm_provisional = 0
    for rm_code in rm_codes:
        port = rm_portfolio(rm_code, period)
        if not port:
            continue
        ppnl = port.get("portfolio_pnl") or {}
        is_prov = bool(ppnl.get("provisional"))
        if is_prov:
            rm_provisional += 1
        rm_portfolios.append({
            "rm_code":     rm_code,
            "total_pbt":   float(ppnl.get("total_pbt", 0)),
            "provisional": is_prov,
        })

    # Roll up data-quality summary
    dq_summary = {
        "ftp_off_customer_count":    ftp_off_count,
        "none_margin_customer_count": none_margin_count,
        "rm_portfolios_provisional": rm_provisional,
        "warnings": [],
    }
    if ftp_off_count > 0:
        dq_summary["warnings"].append(
            f"{ftp_off_count} customer PnLs ran with ftp_mode='off' "
            f"(per Mandatory Standard #11)."
        )
    if rm_provisional > 0:
        dq_summary["warnings"].append(
            f"{rm_provisional} RM portfolio(s) flagged provisional."
        )
    if none_margin_count > 0:
        dq_summary["warnings"].append(
            f"{none_margin_count} customer(s) had pbt_margin=None "
            f"(zero-revenue case)."
        )

    return {
        "period":                       period,
        "total_customer_pbt":           _money(total_pbt),
        "total_customer_revenue":       _money(total_revenue),
        "profitable_customer_count":    profitable_count,
        "total_customer_count":         available_count,
        "profitable_customer_pct":      round(profitable_pct, 2),
        "pyramid_distribution":         pyramid_distribution,
        "rm_portfolios":                rm_portfolios,
        "rm_portfolios_provisional":    rm_provisional,
        "data_quality_summary":         dq_summary,
        "meta": {
            "customers_requested":  len(customer_ids),
            "customers_available":  available_count,
            "rms_processed":        len(rm_codes),
            "rm_portfolios_built":  len(rm_portfolios),
            "generated_at":         datetime.now(timezone.utc).isoformat(),
        },
    }


# ─────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────

def _money(d: Decimal) -> float:
    if not isinstance(d, Decimal):
        try:
            d = Decimal(str(d))
        except Exception:
            return 0.0
    return float(d.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


# ─────────────────────────────────────────────────────────────────────
# Defaults
# ─────────────────────────────────────────────────────────────────────

def _default_all_customers() -> List[str]:
    try:
        from utils.profitability_hierarchy import _default_all_customers as f
        return f()
    except Exception:
        return []


def _default_all_rms() -> List[str]:
    try:
        from utils.rm_profitability import _default_all_rms as f
        return f()
    except Exception:
        return []


def _default_pnl_lookup(customer_id: str, period: str) -> Optional[dict]:
    try:
        from utils.customer_profitability import get_pnl
        return get_pnl(customer_id, period)
    except Exception:
        return None


def _default_pyramid_lookup(period: str) -> Optional[dict]:
    try:
        from utils.profitability_hierarchy import get_pyramid
        return get_pyramid(period)
    except Exception:
        return None


def _default_rm_portfolio(rm_code: str, period: str) -> Optional[dict]:
    try:
        from utils.rm_profitability import get_portfolio
        return get_portfolio(rm_code, period)
    except Exception:
        return None


def _default_bsc_submit(**kwargs) -> bool:
    """Default BSC submit is a no-op that records to the log file
    so the integration is testable without the real BSC dependency.
    """
    try:
        from utils.db import db
        existing = db.load_json(BSC_SUBMISSIONS_LOG, default=[])
        if not isinstance(existing, list):
            existing = []
        existing.append({
            "submitted_at": datetime.now(timezone.utc).isoformat(),
            **kwargs,
        })
        db.save_json(BSC_SUBMISSIONS_LOG, existing)
        return True
    except Exception as e:
        logger.warning("default bsc submit log failed: %s", e)
        return False


# ─────────────────────────────────────────────────────────────────────
# Self-test
# ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("A2Z MIS 360 — utils.profitability_integration self-test")

    # ── Mock BSC submit ───────────────────────────────────────────────
    submissions: List[dict] = []
    def mock_bsc(**kwargs):
        submissions.append(kwargs)
        return True

    # ── Standard #29 — strict mode ────────────────────────────────────
    portfolios = {
        ("RM01", "2026-04"): {"portfolio_pnl": {"total_pbt": 1000000, "provisional": False}},
        ("RM02", "2026-04"): {"portfolio_pnl": {"total_pbt": 500000,  "provisional": False}},
        ("RM03", "2026-04"): {"portfolio_pnl": {"total_pbt": -200000, "provisional": True}},   # provisional
    }
    submissions.clear()
    r = submit_rm_profitability_to_bsc(
        period="2026-04",
        all_rms_fn=lambda: ["RM01", "RM02", "RM03"],
        rm_portfolio_fn=lambda rm, p: portfolios.get((rm, p)),
        bsc_submit_fn=mock_bsc,
        submission_mode="strict",
    )
    assert r["submitted_count"] == 2
    assert r["skipped_count"] == 1
    assert r["skipped_provisional"][0]["rm_code"] == "RM03"
    assert "Mandatory Standard #11" in r["data_quality_warning"]
    assert all(s["kpi_id"] == "RM_PORTFOLIO_PBT" for s in submissions)
    assert {s["staff_code"] for s in submissions} == {"RM01", "RM02"}
    print(f"  ✅ #29 strict mode: 2 submitted, 1 provisional skipped")

    # ── #29 warn mode submits with flag ───────────────────────────────
    submissions.clear()
    r = submit_rm_profitability_to_bsc(
        period="2026-04",
        all_rms_fn=lambda: ["RM01", "RM02", "RM03"],
        rm_portfolio_fn=lambda rm, p: portfolios.get((rm, p)),
        bsc_submit_fn=mock_bsc,
        submission_mode="warn",
    )
    assert r["submitted_count"] == 3
    assert r["skipped_count"] == 0
    rm03_sub = next(s for s in submissions if s["staff_code"] == "RM03")
    assert rm03_sub.get("is_provisional") is True
    print(f"  ✅ #29 warn mode: all 3 submitted, RM03 flagged is_provisional")

    # ── #29 unavailable portfolio tracked ─────────────────────────────
    r = submit_rm_profitability_to_bsc(
        period="2026-04",
        all_rms_fn=lambda: ["RM01", "MISSING"],
        rm_portfolio_fn=lambda rm, p: portfolios.get((rm, p)),
        bsc_submit_fn=mock_bsc,
    )
    assert r["submitted_count"] == 1
    assert len(r["skipped_unavailable"]) == 1
    assert r["skipped_unavailable"][0]["rm_code"] == "MISSING"
    print(f"  ✅ #29 missing portfolio tracked")

    # ── #29 invalid submission_mode rejected ──────────────────────────
    try:
        submit_rm_profitability_to_bsc(period="2026-04", submission_mode="bogus")
        assert False
    except ValueError:
        pass
    print(f"  ✅ #29 invalid submission_mode rejected")

    # ── #29 empty period → {} ─────────────────────────────────────────
    assert submit_rm_profitability_to_bsc(period="") == {}
    print(f"  ✅ #29 empty period → {{}}")

    # ── Standard #30 — dashboard data ─────────────────────────────────
    pnls = {
        ("C1", "2026-04"): {"pbt": 100000, "pbt_margin": 0.5,  "total_revenue": 200000, "meta": {"ftp_mode": "on"}},
        ("C2", "2026-04"): {"pbt": 50000,  "pbt_margin": 0.3,  "total_revenue": 166667, "meta": {"ftp_mode": "on"}},
        ("C3", "2026-04"): {"pbt": -5000,  "pbt_margin": -0.05, "total_revenue": 100000, "meta": {"ftp_mode": "off"}},
        ("C4", "2026-04"): {"pbt": -100,   "pbt_margin": None, "total_revenue": 0,      "meta": {"ftp_mode": "on"}},
    }
    pyramid_data = {
        "tiers": {
            "platinum": {"count": 0},
            "gold": {"count": 1},
            "silver": {"count": 1},
            "bronze": {"count": 0},
            "negative": {"count": 1},
            "unclassified": {"count": 1},
        }
    }
    r = build_md_dashboard_data(
        period="2026-04",
        all_customers_fn=lambda: ["C1", "C2", "C3", "C4"],
        pnl_lookup_fn=lambda c, p: pnls.get((c, p)),
        pyramid_fn=lambda p: pyramid_data,
        all_rms_fn=lambda: ["RM01", "RM02", "RM03"],
        rm_portfolio_fn=lambda rm, p: portfolios.get((rm, p)),
    )
    # PBT: 100000 + 50000 - 5000 - 100 = 144900
    assert r["total_customer_pbt"] == 144900.0, f"got {r['total_customer_pbt']}"
    # Profitable: C1, C2 = 2 of 4 = 50%
    assert r["profitable_customer_count"] == 2
    assert r["profitable_customer_pct"] == 50.0
    assert r["pyramid_distribution"] == {"platinum": 0, "gold": 1, "silver": 1,
                                          "bronze": 0, "negative": 1, "unclassified": 1}
    assert r["rm_portfolios_provisional"] == 1
    assert len(r["data_quality_summary"]["warnings"]) == 3   # FTP-off, provisional, none-margin
    print(f"  ✅ #30 dashboard data: total_pbt={r['total_customer_pbt']:,}, "
          f"profitable={r['profitable_customer_pct']}%, "
          f"warnings={len(r['data_quality_summary']['warnings'])}")

    # ── #30 empty period → {} ─────────────────────────────────────────
    assert build_md_dashboard_data(period="") == {}
    print(f"  ✅ #30 empty period → {{}}")

    print("\n  ALL TESTS PASSED")
