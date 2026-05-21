"""
================================================================================
A2Z MIS 360 — Standard #397: Campaign ROI Attribution
================================================================================

Risk classification: Cat C (deterministic multi-touch attribution model;
                              production ML attribution deferred)

Multi-touch attribution of campaign impact: incremental conversions,
revenue lift, customer-lifetime impact.

Public API:
    record_touchpoint(customer_id, campaign_id, touchpoint_data, actor)
    record_conversion(customer_id, conversion_data, actor)
    attribute_conversion(customer_id, conversion_id) -> attribution map
    campaign_attribution_summary(campaign_id, period_start, period_end)
        -> Dict
    incremental_lift(campaign_id, baseline_conversion_rate) -> Dict

ATTRIBUTION_MODELS byte-for-byte (5):
    LAST_TOUCH       -- 100% credit to last campaign touched before conversion
    FIRST_TOUCH      -- 100% credit to first campaign in funnel
    LINEAR           -- equal credit across all touchpoints
    TIME_DECAY       -- credit weighted by recency (recent > older)
    POSITION_BASED   -- 40/20/40 first/middle/last

Honesty rules:
    Rule 1: empty touchpoints → 0% attribution with reason
    Rule 6: invalid model rejected
    Rule 7: SPEC_DEVIATION_NOTE for ML attribution deferral

================================================================================
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


SPEC_DEVIATION_NOTE: str = (
    "Continuation.docx #397 specifies multi-touch attribution including "
    "customer-lifetime impact. v10.279 ships 5 deterministic attribution "
    "models. Production CLV-aware attribution requires customer LTV "
    "model + ML uplift modeling — deferred to deployment phase."
)


ATTRIBUTION_MODELS: Tuple[str, ...] = (
    "LAST_TOUCH", "FIRST_TOUCH", "LINEAR", "TIME_DECAY", "POSITION_BASED",
)


class CampaignsAttributionEngine:
    """Multi-touch attribution + incremental lift."""

    def __init__(
        self,
        touchpoints_path: Optional[Path] = None,
        conversions_path: Optional[Path] = None,
    ):
        base = Path(__file__).parent.parent / "data"
        self.touchpoints_path = touchpoints_path or base / "campaign_touchpoints.json"
        self.conversions_path = conversions_path or base / "campaign_conversions.json"

    def _load(self, path: Path, table: str, idx: Tuple[str, ...]) -> List[Dict[str, Any]]:
        try:
            from utils.db import db as _db
            data = _db.dual_load(path, table=table, index_cols=idx)
            return data if isinstance(data, list) else []
        except Exception:
            return []

    def _save(self, path: Path, records: List[Dict[str, Any]],
                table: str, pk: str) -> bool:
        try:
            from utils.db import db as _db
            path.parent.mkdir(parents=True, exist_ok=True)
            _db.dual_save(path, data=records, table=table, pk_col=pk)
            return True
        except Exception:
            return False

    def record_touchpoint(
        self, customer_id: str, campaign_id: str,
        touchpoint_data: Dict[str, Any], actor: str,
    ) -> Dict[str, Any]:
        if not actor:
            return {"recorded": False, "error": "actor_required"}
        records = self._load(self.touchpoints_path,
                                 "campaign_touchpoints",
                                 ("touchpoint_id",))
        tp_id = (f"TP-{customer_id}-{campaign_id}-"
                       f"{int(datetime.utcnow().timestamp() * 1000)}")
        records.append({
            "touchpoint_id": tp_id,
            "customer_id": customer_id,
            "campaign_id": campaign_id,
            "touchpoint_type": touchpoint_data.get("touchpoint_type", "EXPOSURE"),
            "channel": touchpoint_data.get("channel"),
            "occurred_at": touchpoint_data.get(
                "occurred_at", datetime.utcnow().isoformat()),
            "actor": actor,
            "recorded_at": datetime.utcnow().isoformat(),
        })
        ok = self._save(self.touchpoints_path, records,
                          "campaign_touchpoints", "touchpoint_id")
        return {"recorded": ok, "touchpoint_id": tp_id}

    def record_conversion(
        self, customer_id: str, conversion_data: Dict[str, Any], actor: str,
    ) -> Dict[str, Any]:
        if not actor:
            return {"recorded": False, "error": "actor_required"}
        for f in ("conversion_id", "amount_kes"):
            if f not in conversion_data:
                return {"recorded": False, "error": f"missing_field:{f}"}
        try:
            amt = Decimal(str(conversion_data["amount_kes"]))
        except Exception:
            return {"recorded": False, "error": "invalid_amount"}
        if amt < 0:
            return {"recorded": False, "error": "negative_amount_rejected"}

        records = self._load(self.conversions_path,
                                 "campaign_conversions",
                                 ("conversion_id",))
        records.append({
            "conversion_id": conversion_data["conversion_id"],
            "customer_id": customer_id,
            "amount_kes": str(amt),
            "occurred_at": conversion_data.get(
                "occurred_at", datetime.utcnow().isoformat()),
            "actor": actor,
        })
        ok = self._save(self.conversions_path, records,
                          "campaign_conversions", "conversion_id")
        return {"recorded": ok}

    def attribute_conversion(
        self, customer_id: str, conversion_id: str,
        model: str = "LAST_TOUCH",
        attribution_window_days: int = 30,
    ) -> Dict[str, Any]:
        if model not in ATTRIBUTION_MODELS:
            return {"error": f"invalid_model:{model}",
                       "valid_models": list(ATTRIBUTION_MODELS)}

        # Find conversion
        conversions = self._load(self.conversions_path,
                                       "campaign_conversions",
                                       ("conversion_id",))
        conv = next((c for c in conversions
                        if c.get("conversion_id") == conversion_id
                        and c.get("customer_id") == customer_id), None)
        if conv is None:
            return {"error": "conversion_not_found"}

        # Find touchpoints in window
        try:
            conv_time = datetime.fromisoformat(
                conv["occurred_at"].replace("Z", ""))
        except (ValueError, KeyError):
            return {"error": "invalid_conversion_timestamp"}

        window_start = conv_time - timedelta(days=attribution_window_days)
        all_tps = self._load(self.touchpoints_path,
                                 "campaign_touchpoints",
                                 ("touchpoint_id",))
        relevant = []
        for tp in all_tps:
            if tp.get("customer_id") != customer_id:
                continue
            try:
                tp_time = datetime.fromisoformat(
                    tp["occurred_at"].replace("Z", ""))
                if window_start <= tp_time <= conv_time:
                    relevant.append((tp, tp_time))
            except (ValueError, KeyError):
                continue

        if not relevant:
            return {
                "customer_id": customer_id,
                "conversion_id": conversion_id,
                "model": model,
                "attribution": {},
                "reason": "no_touchpoints_in_window",
            }

        relevant.sort(key=lambda x: x[1])  # oldest first
        amount = Decimal(conv["amount_kes"])
        attribution: Dict[str, Decimal] = defaultdict(lambda: Decimal("0"))

        if model == "LAST_TOUCH":
            attribution[relevant[-1][0]["campaign_id"]] += amount
        elif model == "FIRST_TOUCH":
            attribution[relevant[0][0]["campaign_id"]] += amount
        elif model == "LINEAR":
            credit = amount / Decimal(len(relevant))
            for tp, _ in relevant:
                attribution[tp["campaign_id"]] += credit
        elif model == "TIME_DECAY":
            # Half-life of 7 days; weight = 0.5 ^ (days_since / 7)
            weights = []
            for _, tp_time in relevant:
                days_since = (conv_time - tp_time).total_seconds() / 86400.0
                w = Decimal(str(0.5 ** (days_since / 7.0)))
                weights.append(w)
            total_w = sum(weights, Decimal("0"))
            if total_w == 0:
                total_w = Decimal("1")
            for (tp, _), w in zip(relevant, weights):
                attribution[tp["campaign_id"]] += amount * w / total_w
        elif model == "POSITION_BASED":
            # 40% first, 40% last, 20% middle (split evenly)
            n = len(relevant)
            if n == 1:
                attribution[relevant[0][0]["campaign_id"]] += amount
            elif n == 2:
                attribution[relevant[0][0]["campaign_id"]] += amount * Decimal("0.5")
                attribution[relevant[1][0]["campaign_id"]] += amount * Decimal("0.5")
            else:
                attribution[relevant[0][0]["campaign_id"]] += amount * Decimal("0.4")
                attribution[relevant[-1][0]["campaign_id"]] += amount * Decimal("0.4")
                middle_credit = amount * Decimal("0.2") / Decimal(n - 2)
                for tp, _ in relevant[1:-1]:
                    attribution[tp["campaign_id"]] += middle_credit

        return {
            "customer_id": customer_id,
            "conversion_id": conversion_id,
            "model": model,
            "amount_kes": str(amount),
            "touchpoint_count": len(relevant),
            "attribution": {k: str(v.quantize(Decimal("0.01")))
                                  for k, v in attribution.items()},
        }

    def campaign_attribution_summary(
        self, campaign_id: str, model: str = "LAST_TOUCH",
        period_start: Optional[str] = None,
        period_end: Optional[str] = None,
    ) -> Dict[str, Any]:
        if model not in ATTRIBUTION_MODELS:
            return {"error": f"invalid_model:{model}"}
        conversions = self._load(self.conversions_path,
                                       "campaign_conversions",
                                       ("conversion_id",))
        if period_start:
            conversions = [c for c in conversions
                                if c.get("occurred_at", "") >= period_start]
        if period_end:
            conversions = [c for c in conversions
                                if c.get("occurred_at", "") <= period_end]

        total_attributed = Decimal("0")
        attributed_count = 0
        for c in conversions:
            attr = self.attribute_conversion(
                c["customer_id"], c["conversion_id"], model=model,
            )
            if "attribution" in attr and campaign_id in attr["attribution"]:
                total_attributed += Decimal(attr["attribution"][campaign_id])
                attributed_count += 1

        return {
            "campaign_id": campaign_id,
            "model": model,
            "period_start": period_start, "period_end": period_end,
            "attributed_revenue_kes": str(
                total_attributed.quantize(Decimal("0.01"))),
            "attributed_conversion_count": attributed_count,
        }

    def incremental_lift(
        self, campaign_id: str, baseline_conversion_rate_pct: str,
        actual_conversion_rate_pct: str, exposed_count: int,
    ) -> Dict[str, Any]:
        try:
            baseline = Decimal(baseline_conversion_rate_pct)
            actual = Decimal(actual_conversion_rate_pct)
        except Exception:
            return {"error": "invalid_rates"}
        if exposed_count <= 0:
            return {"error": "exposed_count_must_be_positive"}

        lift_pct = actual - baseline
        incremental_conversions = (Decimal(exposed_count)
                                          * lift_pct / Decimal("100"))
        return {
            "campaign_id": campaign_id,
            "baseline_rate_pct": str(baseline),
            "actual_rate_pct": str(actual),
            "lift_pp": str(lift_pct.quantize(Decimal("0.01"))),
            "exposed_count": exposed_count,
            "incremental_conversions": str(
                incremental_conversions.quantize(Decimal("0.01"))),
        }


def _self_test() -> None:
    import tempfile
    import time

    assert "LINEAR" in ATTRIBUTION_MODELS
    assert "v10.279" in SPEC_DEVIATION_NOTE

    with tempfile.TemporaryDirectory() as tmpdir:
        engine = CampaignsAttributionEngine(
            touchpoints_path=Path(tmpdir) / "tp.json",
            conversions_path=Path(tmpdir) / "cv.json",
        )

        # Setup: customer C1 touched by 3 campaigns over 14 days, then converts
        base = datetime.utcnow() - timedelta(days=14)
        engine.record_touchpoint(
            "C1", "CAMP-A",
            {"touchpoint_type": "EXPOSURE", "channel": "EMAIL",
             "occurred_at": base.isoformat()},
            actor="adapter",
        )
        time.sleep(0.01)
        engine.record_touchpoint(
            "C1", "CAMP-B",
            {"touchpoint_type": "CLICK", "channel": "PUSH",
             "occurred_at": (base + timedelta(days=7)).isoformat()},
            actor="adapter",
        )
        time.sleep(0.01)
        engine.record_touchpoint(
            "C1", "CAMP-C",
            {"touchpoint_type": "OPEN", "channel": "EMAIL",
             "occurred_at": (base + timedelta(days=13)).isoformat()},
            actor="adapter",
        )
        engine.record_conversion(
            "C1",
            {"conversion_id": "CONV-001", "amount_kes": "10000",
             "occurred_at": datetime.utcnow().isoformat()},
            actor="adapter",
        )

        # Test 1: invalid amount
        r = engine.record_conversion(
            "X", {"conversion_id": "Y", "amount_kes": "abc"}, actor="a",
        )
        assert not r["recorded"]
        r = engine.record_conversion(
            "X", {"conversion_id": "Y", "amount_kes": "-100"}, actor="a",
        )
        assert not r["recorded"]

        # Test 2: LAST_TOUCH attributes 100% to CAMP-C
        attr = engine.attribute_conversion(
            "C1", "CONV-001", model="LAST_TOUCH",
        )
        assert "CAMP-C" in attr["attribution"]
        assert Decimal(attr["attribution"]["CAMP-C"]) == Decimal("10000.00")

        # Test 3: FIRST_TOUCH attributes 100% to CAMP-A
        attr = engine.attribute_conversion(
            "C1", "CONV-001", model="FIRST_TOUCH",
        )
        assert "CAMP-A" in attr["attribution"]
        assert Decimal(attr["attribution"]["CAMP-A"]) == Decimal("10000.00")

        # Test 4: LINEAR splits equally
        attr = engine.attribute_conversion(
            "C1", "CONV-001", model="LINEAR",
        )
        # 10000/3 = 3333.33 each (with rounding)
        for camp_id in ["CAMP-A", "CAMP-B", "CAMP-C"]:
            assert camp_id in attr["attribution"]

        # Test 5: POSITION_BASED 40/20/40
        attr = engine.attribute_conversion(
            "C1", "CONV-001", model="POSITION_BASED",
        )
        assert Decimal(attr["attribution"]["CAMP-A"]) == Decimal("4000.00")
        assert Decimal(attr["attribution"]["CAMP-C"]) == Decimal("4000.00")
        assert Decimal(attr["attribution"]["CAMP-B"]) == Decimal("2000.00")

        # Test 6: TIME_DECAY weights toward recent
        attr = engine.attribute_conversion(
            "C1", "CONV-001", model="TIME_DECAY",
        )
        # CAMP-C (most recent, 1-day-ago) should get largest share
        camp_c_amt = Decimal(attr["attribution"]["CAMP-C"])
        camp_a_amt = Decimal(attr["attribution"]["CAMP-A"])
        assert camp_c_amt > camp_a_amt

        # Test 7: invalid model
        attr = engine.attribute_conversion(
            "C1", "CONV-001", model="INVALID",
        )
        assert "error" in attr

        # Test 8: conversion not found
        attr = engine.attribute_conversion("X", "Y")
        assert "error" in attr

        # Test 9: campaign_attribution_summary
        s = engine.campaign_attribution_summary(
            "CAMP-C", model="LAST_TOUCH",
        )
        assert s["attributed_conversion_count"] == 1
        assert Decimal(s["attributed_revenue_kes"]) == Decimal("10000.00")

        # Test 10: incremental_lift
        l = engine.incremental_lift(
            "CAMP-A", "5.0", "8.5", exposed_count=1000,
        )
        assert Decimal(l["lift_pp"]) == Decimal("3.50")
        assert Decimal(l["incremental_conversions"]) == Decimal("35.00")

        # Test 11: invalid lift inputs
        l = engine.incremental_lift("X", "abc", "1.0", 100)
        assert "error" in l

    print("  ✅ campaigns_attribution self-test PASS")


if __name__ == "__main__":
    _self_test()
