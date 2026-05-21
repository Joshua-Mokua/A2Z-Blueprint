"""utils.profitability_trends — Profitability Trend Analysis
(Standard #28, v5.49). Volume Three.

Per the master spec:

    class ProfitabilityTrends:
        def analyze_customer_trend(self, customer_id, periods=12):
            historical_pnl = [self.calculate_customer_pnl(customer_id, period)
                              for period in periods]
            trend = self.calculate_trend(historical_pnl)
            if trend.direction == "down" and trend.percentage < -0.15:
                self.send_alert(f"Customer profitability declined {abs(trend.percentage)*100:.1f}%")

Verification: not stated. The verifiable structural claim is:
  - Trend direction (up/down/flat) computed correctly
  - Trend percentage matches expected change over the window
  - Alert fires iff direction == "down" AND percentage < -0.15
Audit gate G36.

WHAT THIS ENGINE DOES
----------------------
Given a customer and a number of historical periods, the engine:

  1. Pulls customer PBT for each period (via #21's get_pnl)
  2. Computes a trend: linear regression over time, returning slope
     direction (up/down/flat) and percentage change first→last
  3. If trend is downward more than -15%, fires an alert (which the
     caller can route to e.g. the RM, a relationship manager, or a
     workflow queue)
  4. Returns the trend + the historical points + meta block

TREND COMPUTATION
-----------------
Direction: from least-squares slope sign with a small flat band
  (|slope| < 1% of mean PBT → "flat" not "up" or "down")
Percentage: (last_period_pbt - first_period_pbt) / |first_period_pbt|
  Returned as a fraction (e.g. -0.20 for a 20% decline).
  Returned as None when first_period_pbt == 0 (undefined ratio).

The alert threshold is -0.15 (-15%) per the spec literal.

HONESTY INHERITANCE FROM MANDATORY STANDARD #11
================================================
This engine compares PBT across multiple periods. Each period's PBT
came from #21 with potentially different ftp_mode settings. A
customer whose Q1 PnL ran on naive math (ftp_mode="off") and whose
Q4 PnL ran with FTP=on will show a "trend" that's mostly the model
change, not a real economic shift.

The engine surfaces this in three ways:
  1. meta.upstream_ftp_modes counter (same as #23/#24)
  2. data_quality_warning when periods used different ftp_modes
  3. trend.confidence "low" when modes are mixed; alerts are
     SUPPRESSED when confidence is low (the alert would be misleading)

ALERT SUPPRESSION RULE
----------------------
The spec says "if trend.direction == 'down' and trend.percentage <
-0.15: send_alert". v5.49 ADDS one safety: if the periods used
mixed FTP modes, confidence is low and the alert is NOT sent
(because the apparent decline may be a model artefact).

This is conservative — false negatives (missed real declines)
are preferable to false positives (RM panics about a mode-driven
"decline" that isn't real). The decision is recorded in
meta.alert_suppressed_reason.

DEFENSIVE CONTRACT
------------------
- customer_id empty / None periods → {}
- Any period missing PnL → recorded in meta.unavailable_periods
- < 2 periods of data → trend = "insufficient_data", no alert,
  no provisional flag
- All PBTs zero → "flat", no alert
- First period PBT zero → percentage None, alert suppressed
"""
from __future__ import annotations

import logging
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP, getcontext
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger("a2z.trends")
getcontext().prec = 28

ROOT = Path(__file__).parent.parent
DATA_DIR = ROOT / "data"
TRENDS_FILE = DATA_DIR / "profitability_trends.json"

ZERO = Decimal("0")

# Thresholds — spec literal for alert; flat band is documented below
ALERT_DECLINE_THRESHOLD = Decimal("-0.15")    # spec literal
FLAT_BAND_FRACTION       = Decimal("0.01")     # |slope/mean| < 1% → flat

DIRECTION_UP   = "up"
DIRECTION_DOWN = "down"
DIRECTION_FLAT = "flat"
DIRECTION_INSUFFICIENT = "insufficient_data"


# ─────────────────────────────────────────────────────────────────────
# Engine
# ─────────────────────────────────────────────────────────────────────

class ProfitabilityTrends:
    """Standard #28 — Customer profitability trend analysis."""

    def __init__(
        self,
        pnl_lookup_fn:  Optional[Callable[[str, str], Optional[dict]]] = None,
        alert_sink_fn:  Optional[Callable[[dict], None]] = None,
        period_list_fn: Optional[Callable[[int], List[str]]] = None,
    ):
        """All collaborators injectable.

        pnl_lookup_fn(customer_id, period) → dict | None
            Returns #21 PnL output. Default reads
            data/customer_pnl.json via #21's get_pnl.

        alert_sink_fn(alert_dict) → None
            Where alerts are routed. Default is no-op (alerts only
            recorded in result, not dispatched). Production wires
            this to e.g. the RM notification queue.

        period_list_fn(n) → list[str]
            Returns the n most recent periods, oldest-first. Default
            generates monthly periods ending at the current month.
        """
        self._pnl_lookup  = pnl_lookup_fn  or _default_pnl_lookup
        self._alert_sink  = alert_sink_fn  or (lambda a: None)
        self._period_list = period_list_fn or _default_period_list

    # ──────────────────────────────────────────────────────────────────
    # Spec entry
    # ──────────────────────────────────────────────────────────────────

    def analyze_customer_trend(
        self, customer_id: str, periods: int = 12,
    ) -> Dict[str, Any]:
        """Analyse a customer's profitability trend over the last N periods.

        Returns:
            {
              "customer_id":      str,
              "periods_window":   int,
              "history":          [{period, pbt, margin, ftp_mode}, ...],
              "trend": {
                  "direction":  "up" | "down" | "flat" | "insufficient_data",
                  "percentage": float | None,    # fraction
                  "first_pbt":  float,
                  "last_pbt":   float,
                  "confidence": "high" | "low",
              },
              "alert": {
                  "fired":       bool,
                  "suppressed":  bool,
                  "message":     str | None,
                  "reason":      str,
              },
              "data_quality_warning": str | None,
              "meta": {...}
            }

        Returns {} for empty customer_id.
        """
        if not customer_id or periods <= 0:
            return {}

        period_codes = self._period_list(periods) or []
        history: List[Dict[str, Any]] = []
        unavailable: List[str] = []
        ftp_mode_counter: Counter = Counter()

        for p in period_codes:
            pnl = self._pnl_lookup(customer_id, p)
            if not pnl:
                unavailable.append(p)
                continue
            mode = (pnl.get("meta") or {}).get("ftp_mode", "unknown")
            mode = mode if mode in ("on", "off", "unknown") else "unknown"
            ftp_mode_counter[mode] += 1
            history.append({
                "period":   p,
                "pbt":      float(pnl.get("pbt", 0)),
                "margin":   pnl.get("pbt_margin"),
                "ftp_mode": mode,
            })

        # Trend
        trend = self._compute_trend(history)

        # Honesty: confidence drops to low when modes are mixed
        ftp_modes_used = {m for m, n in ftp_mode_counter.items() if n > 0}
        modes_mixed = len(ftp_modes_used) > 1 or "off" in ftp_modes_used
        confidence = "low" if modes_mixed else "high"
        trend["confidence"] = confidence

        # Alert: spec rule + suppression for low confidence
        alert_fired = False
        alert_suppressed = False
        alert_reason = ""
        alert_message: Optional[str] = None

        if (
            trend["direction"] == DIRECTION_DOWN
            and trend["percentage"] is not None
            and Decimal(str(trend["percentage"])) < ALERT_DECLINE_THRESHOLD
        ):
            if confidence == "low":
                alert_suppressed = True
                alert_reason = (
                    "decline detected but confidence is low — periods used "
                    "mixed ftp_modes (per Mandatory Standard #11). "
                    "Re-run upstream PnLs in consistent mode before alerting."
                )
            else:
                alert_fired = True
                pct = abs(trend["percentage"]) * 100
                alert_message = (
                    f"Customer profitability declined {pct:.1f}%"
                )
                alert_reason = "spec rule fired: direction=down and percentage<-0.15"
                self._alert_sink({
                    "customer_id": customer_id,
                    "message":     alert_message,
                    "trend":       trend,
                })

        # Data-quality warning surfaces if any period had ftp_mode='off'
        warning = None
        if ftp_mode_counter.get("off", 0) > 0 or modes_mixed:
            warning = (
                f"Trend includes periods with mixed or naive ftp_modes "
                f"({dict(ftp_mode_counter)}). Per Mandatory Standard #11, "
                f"compare like-with-like before drawing conclusions."
            )

        return {
            "customer_id":          customer_id,
            "periods_window":       periods,
            "history":              history,
            "trend":                trend,
            "alert": {
                "fired":      alert_fired,
                "suppressed": alert_suppressed,
                "message":    alert_message,
                "reason":     alert_reason,
            },
            "data_quality_warning": warning,
            "meta": {
                "periods_requested":     periods,
                "periods_with_data":     len(history),
                "unavailable_periods":   unavailable,
                "upstream_ftp_modes":    dict(ftp_mode_counter),
                "alert_threshold_pct":   float(ALERT_DECLINE_THRESHOLD * 100),
                "flat_band_pct":         float(FLAT_BAND_FRACTION * 100),
                "generated_at":          datetime.now(timezone.utc).isoformat(),
            },
        }

    # ──────────────────────────────────────────────────────────────────
    # Trend math
    # ──────────────────────────────────────────────────────────────────

    def _compute_trend(self, history: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Compute direction + percentage change.

        history: list of {period, pbt, margin}, oldest-first.

        direction: linear regression slope over time, with a flat band
        (|slope| < FLAT_BAND_FRACTION × |mean_pbt| → flat).

        percentage: (last - first) / |first|, None if first==0.
        """
        n = len(history)
        if n < 2:
            return {
                "direction":  DIRECTION_INSUFFICIENT,
                "percentage": None,
                "first_pbt":  float(history[0]["pbt"]) if n == 1 else 0.0,
                "last_pbt":   float(history[-1]["pbt"]) if n >= 1 else 0.0,
            }

        ys = [Decimal(str(h["pbt"])) for h in history]
        first = ys[0]
        last  = ys[-1]

        # Percentage change (last vs first)
        if first == ZERO:
            percentage = None
        else:
            percentage = float(((last - first) / abs(first)).quantize(
                Decimal("0.0001"), rounding=ROUND_HALF_UP
            ))

        # Slope via simple least-squares with x = 0,1,...,n-1
        # slope = sum((x_i - x_mean)(y_i - y_mean)) / sum((x_i - x_mean)^2)
        x_mean = Decimal(n - 1) / Decimal(2)
        y_mean = sum(ys, start=ZERO) / Decimal(n)
        num = ZERO
        den = ZERO
        for i, y in enumerate(ys):
            xd = Decimal(i) - x_mean
            yd = y - y_mean
            num += xd * yd
            den += xd * xd
        slope = num / den if den != ZERO else ZERO

        # Direction with flat band
        mean_abs = abs(y_mean)
        flat_threshold = FLAT_BAND_FRACTION * mean_abs if mean_abs > ZERO else \
                         FLAT_BAND_FRACTION

        if abs(slope) < flat_threshold:
            direction = DIRECTION_FLAT
        elif slope > ZERO:
            direction = DIRECTION_UP
        else:
            direction = DIRECTION_DOWN

        return {
            "direction":  direction,
            "percentage": percentage,
            "first_pbt":  float(first.quantize(Decimal("0.01"))),
            "last_pbt":   float(last.quantize(Decimal("0.01"))),
        }


# ─────────────────────────────────────────────────────────────────────
# Defaults
# ─────────────────────────────────────────────────────────────────────

def _default_pnl_lookup(customer_id: str, period: str) -> Optional[dict]:
    try:
        from utils.customer_profitability import get_pnl
        return get_pnl(customer_id, period)
    except Exception as e:
        logger.warning("trends: default get_pnl failed: %s", e)
        return None


def _default_period_list(n: int) -> List[str]:
    """Return n monthly period codes ending at current month, oldest-first."""
    today = datetime.now(timezone.utc).date()
    out = []
    y, m = today.year, today.month
    for _ in range(n):
        out.append(f"{y:04d}-{m:02d}")
        m -= 1
        if m == 0:
            m = 12
            y -= 1
    return list(reversed(out))


# ─────────────────────────────────────────────────────────────────────
# Self-test
# ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("A2Z MIS 360 — utils.profitability_trends self-test")

    # ── Helper ────────────────────────────────────────────────────────
    def history_pnls(values, ftp_mode="on"):
        """Build pnl_lookup_fn returning given values for periods 1..N."""
        def fn(c, p):
            i = int(p.split("-")[1]) - 1
            if 0 <= i < len(values):
                return {
                    "pbt": values[i],
                    "pbt_margin": 0.5,
                    "meta": {"ftp_mode": ftp_mode},
                }
            return None
        return fn

    def periods(n):
        # Just generate "2026-01", "2026-02", ...
        return [f"2026-{i+1:02d}" for i in range(n)]

    # ── Case 1: clear upward trend ────────────────────────────────────
    eng = ProfitabilityTrends(
        pnl_lookup_fn=history_pnls([100, 110, 120, 130, 140, 150]),
        period_list_fn=lambda n: periods(min(n, 6)),
    )
    r = eng.analyze_customer_trend("C1", periods=6)
    assert r["trend"]["direction"] == "up"
    assert r["trend"]["first_pbt"] == 100.0
    assert r["trend"]["last_pbt"] == 150.0
    # percentage = (150 - 100) / 100 = 0.50
    assert abs(r["trend"]["percentage"] - 0.5) < 1e-4
    print(f"  ✅ upward trend: {r['trend']['direction']}, "
          f"{r['trend']['percentage']*100:.1f}%")

    # ── Case 2: 20% decline → alert fires ─────────────────────────────
    alerts_caught = []
    eng_dec = ProfitabilityTrends(
        pnl_lookup_fn=history_pnls([100, 95, 90, 85, 80]),
        alert_sink_fn=lambda a: alerts_caught.append(a),
        period_list_fn=lambda n: periods(min(n, 5)),
    )
    r = eng_dec.analyze_customer_trend("C1", periods=5)
    assert r["trend"]["direction"] == "down"
    # percentage = (80 - 100) / 100 = -0.20 < -0.15 → alert
    assert r["alert"]["fired"] is True
    assert "20.0%" in r["alert"]["message"]
    assert len(alerts_caught) == 1
    print(f"  ✅ 20% decline: alert fired, message='{r['alert']['message']}'")

    # ── Case 3: 10% decline → no alert (threshold) ────────────────────
    alerts2 = []
    eng_small = ProfitabilityTrends(
        pnl_lookup_fn=history_pnls([100, 98, 96, 94, 90]),
        alert_sink_fn=lambda a: alerts2.append(a),
        period_list_fn=lambda n: periods(min(n, 5)),
    )
    r = eng_small.analyze_customer_trend("C1", periods=5)
    # percentage = (90 - 100)/100 = -0.10, NOT < -0.15
    assert r["trend"]["direction"] == "down"
    assert r["alert"]["fired"] is False
    assert len(alerts2) == 0
    print(f"  ✅ 10% decline: no alert (threshold -15%)")

    # ── Case 4: flat trend ────────────────────────────────────────────
    eng_flat = ProfitabilityTrends(
        pnl_lookup_fn=history_pnls([100, 100, 100, 100]),
        period_list_fn=lambda n: periods(min(n, 4)),
    )
    r = eng_flat.analyze_customer_trend("C1", periods=4)
    assert r["trend"]["direction"] == "flat"
    assert r["trend"]["percentage"] == 0.0
    print(f"  ✅ flat trend detected")

    # ── Case 5: alert SUPPRESSED when ftp_modes mixed ─────────────────
    def mixed_lookup(c, p):
        i = int(p.split("-")[1]) - 1
        values = [100, 95, 80, 75, 70]
        modes = ["off", "off", "on", "on", "on"]
        if 0 <= i < len(values):
            return {
                "pbt": values[i],
                "pbt_margin": 0.5,
                "meta": {"ftp_mode": modes[i]},
            }
        return None
    alerts3 = []
    eng_mixed = ProfitabilityTrends(
        pnl_lookup_fn=mixed_lookup,
        alert_sink_fn=lambda a: alerts3.append(a),
        period_list_fn=lambda n: periods(min(n, 5)),
    )
    r = eng_mixed.analyze_customer_trend("C1", periods=5)
    # 30% decline — but suppressed
    assert r["trend"]["direction"] == "down"
    assert r["alert"]["fired"] is False, "alert should be suppressed"
    assert r["alert"]["suppressed"] is True
    assert "Mandatory Standard #11" in r["alert"]["reason"]
    assert len(alerts3) == 0
    print(f"  ✅ alert suppressed on mixed-mode periods")

    # ── Case 6: insufficient data ─────────────────────────────────────
    eng_short = ProfitabilityTrends(
        pnl_lookup_fn=history_pnls([100]),
        period_list_fn=lambda n: periods(min(n, 1)),
    )
    r = eng_short.analyze_customer_trend("C1", periods=1)
    assert r["trend"]["direction"] == "insufficient_data"
    assert r["alert"]["fired"] is False
    print(f"  ✅ insufficient data handled gracefully")

    # ── Case 7: empty customer_id → {} ────────────────────────────────
    assert eng.analyze_customer_trend("", periods=6) == {}
    print(f"  ✅ empty customer_id → {{}}")

    # ── Case 8: zero periods → {} ─────────────────────────────────────
    assert eng.analyze_customer_trend("C1", periods=0) == {}
    print(f"  ✅ zero periods → {{}}")

    # ── Case 9: missing periods tracked ───────────────────────────────
    def partial(c, p):
        i = int(p.split("-")[1]) - 1
        if i in (0, 2, 4):    # only odd-indexed periods have data
            return {"pbt": 100 - i*5, "pbt_margin": 0.5,
                    "meta": {"ftp_mode": "on"}}
        return None
    eng_partial = ProfitabilityTrends(
        pnl_lookup_fn=partial,
        period_list_fn=lambda n: periods(min(n, 5)),
    )
    r = eng_partial.analyze_customer_trend("C1", periods=5)
    assert r["meta"]["periods_with_data"] == 3
    assert len(r["meta"]["unavailable_periods"]) == 2
    print(f"  ✅ missing periods tracked: {r['meta']['periods_with_data']}/5 with data")

    # ── Case 10: data quality warning surfaces with FTP-off ───────────
    eng_off = ProfitabilityTrends(
        pnl_lookup_fn=history_pnls([100, 95, 90], ftp_mode="off"),
        period_list_fn=lambda n: periods(min(n, 3)),
    )
    r = eng_off.analyze_customer_trend("C1", periods=3)
    assert r["data_quality_warning"] is not None
    assert "Mandatory Standard #11" in r["data_quality_warning"]
    print(f"  ✅ data quality warning with FTP-off")

    print("\n  ALL TESTS PASSED")
