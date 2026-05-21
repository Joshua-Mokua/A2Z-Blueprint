"""
================================================================================
A2Z MIS 360 — Standard #328: Competitive Rate Intelligence
================================================================================

Risk classification: Cat C (deterministic trend + statistical anomaly
                              detection over competitor rate data points)

Daily competitor rate tracking: deposit rates, lending rates, FX rates,
fees. Trend detection, anomaly alerts. Composes #327 data store and
filters to RATE_TYPES.

Public API:
    rate_history(competitor_id, rate_type, days=90) -> List
    rate_trend(competitor_id, rate_type, period_days=30)
        -> {direction, change_pp, baseline}
    detect_anomalies(rate_type, threshold_pp=2.0, days=30)
        -> List of competitors with rate anomalies
    rate_comparison_table(rate_type, as_of_date) -> Dict per-competitor

RATE_TYPES byte-for-byte (subset of #327 DATA_TYPES filtered):
    DEPOSIT_RATE   LENDING_RATE   FEE

TREND_DIRECTIONS byte-for-byte:
    RISING        -- rate increased > epsilon over period
    FALLING       -- rate decreased > epsilon over period
    STABLE        -- absolute change within epsilon
    INSUFFICIENT  -- not enough data points to compute trend

DEFAULT_TREND_EPSILON_PP = 0.10  -- 10 basis points threshold for STABLE
DEFAULT_ANOMALY_THRESHOLD_PP = 2.0  -- 200 bps absolute change → anomaly

Honesty rules:
    Rule 1: insufficient history → INSUFFICIENT direction (not STABLE)
    Rule 6: invalid rate_type rejected
    Rule 7: deterministic trend + anomaly heuristics; production ML
            anomaly detection (e.g. seasonal-adjusted) deferred

================================================================================
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, date, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from utils.competitor_data_collection import (
    CompetitorDataCollectionEngine, DATA_TYPES,
)


RATE_TYPES: Tuple[str, ...] = ("DEPOSIT_RATE", "LENDING_RATE", "FEE")

TREND_DIRECTIONS: Tuple[str, ...] = (
    "RISING", "FALLING", "STABLE", "INSUFFICIENT",
)

DEFAULT_TREND_EPSILON_PP: Decimal = Decimal("0.10")
DEFAULT_ANOMALY_THRESHOLD_PP: Decimal = Decimal("2.0")


class CompetitorRatesEngine:
    """Rate trend + anomaly detection composed over #327 data store."""

    def __init__(
        self,
        data_collection: Optional[CompetitorDataCollectionEngine] = None,
    ):
        self.data_collection = data_collection or CompetitorDataCollectionEngine()

    def rate_history(
        self,
        competitor_id: str,
        rate_type: str,
        days: int = 90,
    ) -> Dict[str, Any]:
        if rate_type not in RATE_TYPES:
            return {
                "competitor_id": competitor_id,
                "rate_type": rate_type,
                "error": f"invalid_rate_type:{rate_type}",
                "valid_types": list(RATE_TYPES),
            }
        from_date = (date.today() - timedelta(days=days)).isoformat()
        records = self.data_collection.list_data_points(
            competitor_id=competitor_id,
            data_type=rate_type,
            from_date=from_date,
        )
        # Sort chronologically by as_of
        records.sort(key=lambda r: r.get("as_of", ""))
        return {
            "competitor_id": competitor_id,
            "rate_type": rate_type,
            "days": days,
            "data_point_count": len(records),
            "history": [
                {"as_of": r["as_of"], "value": r["value"],
                 "unit": r.get("unit", "")}
                for r in records
            ],
        }

    def rate_trend(
        self,
        competitor_id: str,
        rate_type: str,
        period_days: int = 30,
        epsilon_pp: Optional[Decimal] = None,
    ) -> Dict[str, Any]:
        if rate_type not in RATE_TYPES:
            return {"error": f"invalid_rate_type:{rate_type}"}
        eps = epsilon_pp if epsilon_pp is not None else DEFAULT_TREND_EPSILON_PP

        history = self.rate_history(
            competitor_id, rate_type, days=period_days,
        )
        points = history.get("history", [])
        if len(points) < 2:
            return {
                "competitor_id": competitor_id,
                "rate_type": rate_type,
                "direction": "INSUFFICIENT",
                "data_point_count": len(points),
                "reason": "fewer_than_2_observations",
            }

        try:
            first_val = Decimal(points[0]["value"])
            last_val = Decimal(points[-1]["value"])
        except (ValueError, TypeError, KeyError):
            return {
                "competitor_id": competitor_id,
                "rate_type": rate_type,
                "direction": "INSUFFICIENT",
                "reason": "invalid_value_format",
            }

        change = last_val - first_val
        if abs(change) <= eps:
            direction = "STABLE"
        elif change > 0:
            direction = "RISING"
        else:
            direction = "FALLING"

        return {
            "competitor_id": competitor_id,
            "rate_type": rate_type,
            "direction": direction,
            "data_point_count": len(points),
            "first_value": str(first_val),
            "last_value": str(last_val),
            "change_pp": str(change.quantize(Decimal("0.01"))),
            "first_as_of": points[0]["as_of"],
            "last_as_of": points[-1]["as_of"],
            "epsilon_pp": str(eps),
        }

    def detect_anomalies(
        self,
        rate_type: str,
        threshold_pp: Optional[Decimal] = None,
        days: int = 30,
    ) -> Dict[str, Any]:
        if rate_type not in RATE_TYPES:
            return {"error": f"invalid_rate_type:{rate_type}"}
        threshold = (threshold_pp if threshold_pp is not None
                       else DEFAULT_ANOMALY_THRESHOLD_PP)
        competitors = self.data_collection.list_competitors()
        anomalies = []
        for c in competitors:
            cid = c["competitor_id"]
            trend = self.rate_trend(cid, rate_type, period_days=days)
            if trend.get("direction") in ("RISING", "FALLING"):
                try:
                    change = abs(Decimal(trend["change_pp"]))
                    if change >= threshold:
                        anomalies.append({
                            "competitor_id": cid,
                            "competitor_name": c.get("name"),
                            "direction": trend["direction"],
                            "change_pp": trend["change_pp"],
                            "first_value": trend["first_value"],
                            "last_value": trend["last_value"],
                            "first_as_of": trend["first_as_of"],
                            "last_as_of": trend["last_as_of"],
                        })
                except (ValueError, TypeError, KeyError):
                    continue

        return {
            "rate_type": rate_type,
            "days": days,
            "threshold_pp": str(threshold),
            "anomaly_count": len(anomalies),
            "anomalies": anomalies,
            "competitor_count_evaluated": len(competitors),
        }

    def rate_comparison_table(
        self,
        rate_type: str,
        as_of_date: Optional[str] = None,
    ) -> Dict[str, Any]:
        if rate_type not in RATE_TYPES:
            return {"error": f"invalid_rate_type:{rate_type}"}
        as_of = as_of_date or date.today().isoformat()
        competitors = self.data_collection.list_competitors()
        rows = []
        for c in competitors:
            cid = c["competitor_id"]
            # Get latest data point at or before as_of
            records = self.data_collection.list_data_points(
                competitor_id=cid, data_type=rate_type,
                to_date=as_of,
            )
            records.sort(key=lambda r: r.get("as_of", ""), reverse=True)
            latest = records[0] if records else None
            rows.append({
                "competitor_id": cid,
                "competitor_name": c.get("name"),
                "tier": c.get("tier"),
                "value": latest["value"] if latest else None,
                "unit": latest.get("unit", "") if latest else None,
                "as_of": latest["as_of"] if latest else None,
                "has_data": latest is not None,
            })

        # Sort rows by value descending (None last)
        def _sort_key(r):
            try:
                return Decimal(r["value"]) if r["value"] is not None else Decimal("-99999")
            except (ValueError, TypeError):
                return Decimal("-99999")
        rows.sort(key=_sort_key, reverse=True)

        return {
            "rate_type": rate_type,
            "as_of": as_of,
            "competitor_count": len(rows),
            "rows": rows,
        }


def _self_test() -> None:
    import tempfile

    assert "DEPOSIT_RATE" in RATE_TYPES
    assert "INSUFFICIENT" in TREND_DIRECTIONS

    with tempfile.TemporaryDirectory() as tmpdir:
        dc = CompetitorDataCollectionEngine(
            competitors_path=Path(tmpdir) / "c.json",
            data_points_path=Path(tmpdir) / "d.json",
        )
        engine = CompetitorRatesEngine(data_collection=dc)

        # Setup: 2 competitors with rate history
        dc.register_competitor(
            {"competitor_id": "KCB", "name": "KCB", "tier": "TIER_1"},
            actor="a",
        )
        dc.register_competitor(
            {"competitor_id": "EQUITY", "name": "Equity", "tier": "TIER_1"},
            actor="a",
        )

        # KCB: rates rising 5.0 → 5.5 → 6.5 over 30 days
        for i, (val, days_ago) in enumerate([("5.0", 30), ("5.5", 20), ("6.5", 1)]):
            day = (date.today() - timedelta(days=days_ago)).isoformat()
            dc.record_data_point(
                "KCB",
                {"data_type": "DEPOSIT_RATE", "value": val,
                 "data_source": "WEBSITE_SCRAPE",
                 "as_of": day, "unit": "pct"},
                actor="a",
            )
        # EQUITY: stable around 5.5
        for val, days_ago in [("5.5", 30), ("5.55", 20), ("5.5", 1)]:
            day = (date.today() - timedelta(days=days_ago)).isoformat()
            dc.record_data_point(
                "EQUITY",
                {"data_type": "DEPOSIT_RATE", "value": val,
                 "data_source": "WEBSITE_SCRAPE",
                 "as_of": day, "unit": "pct"},
                actor="a",
            )

        # Test 1: rate_history
        h = engine.rate_history("KCB", "DEPOSIT_RATE", days=60)
        assert h["data_point_count"] == 3

        # Test 2: invalid rate_type
        h = engine.rate_history("KCB", "INVALID", days=60)
        assert "error" in h

        # Test 3: rate_trend KCB → RISING
        t = engine.rate_trend("KCB", "DEPOSIT_RATE", period_days=60)
        assert t["direction"] == "RISING"
        assert Decimal(t["change_pp"]) == Decimal("1.50")

        # Test 4: rate_trend EQUITY → STABLE (within epsilon 0.10)
        t = engine.rate_trend("EQUITY", "DEPOSIT_RATE", period_days=60)
        assert t["direction"] == "STABLE"

        # Test 5: insufficient data
        dc.register_competitor(
            {"competitor_id": "NEW", "name": "New", "tier": "TIER_3"},
            actor="a",
        )
        t = engine.rate_trend("NEW", "DEPOSIT_RATE", period_days=60)
        assert t["direction"] == "INSUFFICIENT"

        # Test 6: detect_anomalies — KCB has +1.5pp which is below 2.0 threshold
        a = engine.detect_anomalies("DEPOSIT_RATE",
                                          threshold_pp=Decimal("2.0"), days=60)
        assert a["anomaly_count"] == 0

        # Test 7: detect_anomalies with lower threshold finds KCB
        a = engine.detect_anomalies("DEPOSIT_RATE",
                                          threshold_pp=Decimal("1.0"), days=60)
        assert a["anomaly_count"] == 1
        assert a["anomalies"][0]["competitor_id"] == "KCB"
        assert a["anomalies"][0]["direction"] == "RISING"

        # Test 8: rate_comparison_table
        ct = engine.rate_comparison_table("DEPOSIT_RATE")
        assert ct["competitor_count"] == 3
        # KCB should be at top (highest 6.5)
        assert ct["rows"][0]["competitor_id"] == "KCB"

    print("  ✅ competitor_rates self-test PASS")


if __name__ == "__main__":
    _self_test()
