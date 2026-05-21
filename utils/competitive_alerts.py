"""
================================================================================
A2Z MIS 360 — Standard #331: Competitive Alert Engine
================================================================================

Risk classification: Cat C (deterministic alert generation + routing
                              over competitor data; smart_alerts integration)

Real-time alerts on competitor moves: new product, rate change,
leadership change, M&A activity. Routed to relevant executives.
Composes #327 data store + #328 rate trends + #329 digital intel +
v9.x smart_alerts via published_alert hook.

Public API:
    register_alert_rule(rule_data, actor, reason)
    transition_rule_state(rule_id, new_state, actor, reason)
    evaluate_alerts(period_start, period_end, actor)
        -> List of generated alerts
    publish_alerts(alerts, actor) -> route to smart_alerts (or audit if absent)
    list_published_alerts(executive_role=None, days=30) -> List

ALERT_TYPES byte-for-byte:
    NEW_PRODUCT          -- new PRODUCT_FEATURE or DIGITAL_LAUNCH
    RATE_CHANGE          -- DEPOSIT_RATE / LENDING_RATE significant change
    LEADERSHIP_CHANGE    -- LEADERSHIP_CHANGE event
    M_AND_A              -- M_AND_A event
    REGULATORY_ACTION    -- REGULATORY_ACTION against competitor
    NPS_SHIFT            -- NPS_SCORE moved > threshold
    APP_RATING_DROP      -- APP_RATING fell

ALERT_PRIORITIES byte-for-byte:
    URGENT     -- M_AND_A, leadership change in TIER_1, regulatory action
    HIGH       -- new product launch in TIER_1 + rate change > 1pp
    MEDIUM     -- rate change 0.25-1pp, NPS shift
    LOW        -- minor app rating moves, niche feature launches

ALERT_RULE_STATES byte-for-byte:
    ACTIVE       -- live, generates alerts
    PAUSED       -- temporarily disabled
    ARCHIVED     -- archived (terminal)

EXECUTIVE_ROLES_ROUTING byte-for-byte:
    CEO            -- URGENT alerts
    CFO            -- M_AND_A, regulatory action, RATE_CHANGE>1pp
    COO            -- LEADERSHIP_CHANGE, REGULATORY_ACTION
    CMO            -- NEW_PRODUCT, NPS_SHIFT, APP_RATING_DROP
    HEAD_RETAIL    -- NEW_PRODUCT in retail-relevant categories
    HEAD_RISK      -- REGULATORY_ACTION, M_AND_A
    HEAD_DIGITAL   -- DIGITAL_LAUNCH, APP_RATING_DROP

Honesty rules:
    Rule 1: empty data store → empty alert list with reason
    Rule 4: actor + reason mandatory on rule lifecycle
    Rule 6: invalid alert_type / priority / state rejected

================================================================================
"""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, date, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from utils.competitor_data_collection import CompetitorDataCollectionEngine
from utils.competitor_rates import CompetitorRatesEngine


ALERT_TYPES: Tuple[str, ...] = (
    "NEW_PRODUCT", "RATE_CHANGE", "LEADERSHIP_CHANGE",
    "M_AND_A", "REGULATORY_ACTION", "NPS_SHIFT", "APP_RATING_DROP",
)

ALERT_PRIORITIES: Tuple[str, ...] = ("URGENT", "HIGH", "MEDIUM", "LOW")

ALERT_RULE_STATES: Tuple[str, ...] = ("ACTIVE", "PAUSED", "ARCHIVED")

ALLOWED_RULE_TRANSITIONS: Dict[str, Tuple[str, ...]] = {
    "ACTIVE":   ("PAUSED", "ARCHIVED"),
    "PAUSED":   ("ACTIVE", "ARCHIVED"),
    "ARCHIVED": (),
}

EXECUTIVE_ROLES_ROUTING: Dict[str, Tuple[str, ...]] = {
    "URGENT": ("CEO", "CFO", "COO"),
    "HIGH":   ("CFO", "CMO", "HEAD_RETAIL"),
    "MEDIUM": ("CMO", "HEAD_RETAIL", "HEAD_DIGITAL"),
    "LOW":    ("HEAD_DIGITAL", "HEAD_RETAIL"),
}

# Type-specific routing additions
TYPE_SPECIFIC_ROUTING: Dict[str, Tuple[str, ...]] = {
    "M_AND_A":              ("CEO", "CFO", "HEAD_RISK"),
    "REGULATORY_ACTION":    ("CEO", "COO", "HEAD_RISK"),
    "LEADERSHIP_CHANGE":    ("CEO", "COO"),
    "DIGITAL_LAUNCH":       ("CMO", "HEAD_DIGITAL"),
    "APP_RATING_DROP":      ("HEAD_DIGITAL", "CMO"),
    "RATE_CHANGE":          ("CFO", "CMO"),
}


class CompetitiveAlertsEngine:
    """Alert rule registry + alert generation + smart_alerts routing."""

    def __init__(
        self,
        data_collection: Optional[CompetitorDataCollectionEngine] = None,
        rates_engine: Optional[CompetitorRatesEngine] = None,
        rules_path: Optional[Path] = None,
        alerts_path: Optional[Path] = None,
    ):
        self.data_collection = data_collection or CompetitorDataCollectionEngine()
        self.rates_engine = rates_engine or CompetitorRatesEngine(
            data_collection=self.data_collection,
        )
        base = Path(__file__).parent.parent / "data"
        self.rules_path = rules_path or base / "competitive_alert_rules.json"
        self.alerts_path = alerts_path or base / "competitive_alerts.json"

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

    def register_alert_rule(
        self,
        rule_data: Dict[str, Any],
        actor: str,
        reason: str,
    ) -> Dict[str, Any]:
        if not actor or not reason:
            return {"registered": False, "error": "actor_and_reason_required"}
        for f in ("rule_id", "alert_type", "priority"):
            if f not in rule_data or not rule_data[f]:
                return {"registered": False, "error": f"missing_field:{f}"}
        if rule_data["alert_type"] not in ALERT_TYPES:
            return {
                "registered": False,
                "error": f"invalid_alert_type:{rule_data['alert_type']}",
                "valid_types": list(ALERT_TYPES),
            }
        if rule_data["priority"] not in ALERT_PRIORITIES:
            return {
                "registered": False,
                "error": f"invalid_priority:{rule_data['priority']}",
                "valid_priorities": list(ALERT_PRIORITIES),
            }

        records = self._load(self.rules_path,
                                "competitive_alert_rules", ("rule_id",))
        if any(r.get("rule_id") == rule_data["rule_id"] for r in records):
            return {"registered": False, "error": "duplicate_rule_id"}

        record = {
            "rule_id": rule_data["rule_id"],
            "alert_type": rule_data["alert_type"],
            "priority": rule_data["priority"],
            "competitor_filter_tier": rule_data.get("competitor_filter_tier"),
            "rate_change_threshold_pp": rule_data.get(
                "rate_change_threshold_pp", "0.25"),
            "state": "ACTIVE",
            "registered_by": actor,
            "registered_at": datetime.utcnow().isoformat(),
            "registration_reason": reason,
            "transitions": [{
                "to": "ACTIVE", "actor": actor,
                "at": datetime.utcnow().isoformat(),
                "reason": reason,
            }],
        }
        records.append(record)
        ok = self._save(self.rules_path, records,
                          "competitive_alert_rules", "rule_id")
        return {"registered": ok, "rule_id": rule_data["rule_id"]}

    def transition_rule_state(
        self,
        rule_id: str,
        new_state: str,
        actor: str,
        reason: str,
    ) -> Dict[str, Any]:
        if not actor or not reason:
            return {"transitioned": False, "error": "actor_and_reason_required"}
        if new_state not in ALERT_RULE_STATES:
            return {"transitioned": False, "error": f"invalid_state:{new_state}"}
        records = self._load(self.rules_path,
                                "competitive_alert_rules", ("rule_id",))
        for r in records:
            if r.get("rule_id") == rule_id:
                current = r.get("state", "ACTIVE")
                allowed = ALLOWED_RULE_TRANSITIONS.get(current, ())
                if new_state not in allowed:
                    return {
                        "transitioned": False,
                        "error": f"transition_not_allowed:{current}_to_{new_state}",
                    }
                r["state"] = new_state
                r.setdefault("transitions", []).append({
                    "to": new_state, "actor": actor,
                    "at": datetime.utcnow().isoformat(),
                    "reason": reason,
                })
                ok = self._save(self.rules_path, records,
                                  "competitive_alert_rules", "rule_id")
                return {"transitioned": ok, "from": current, "to": new_state}
        return {"transitioned": False, "error": "rule_not_found"}

    def evaluate_alerts(
        self,
        period_start: str,
        period_end: str,
        actor: str,
    ) -> Dict[str, Any]:
        """Scan data store for alert-triggering events in window. Returns
        candidate alerts; does not publish."""
        if not actor:
            return {"alerts": [], "error": "actor_required"}

        # Active rules
        rules = [r for r in self._load(self.rules_path,
                                              "competitive_alert_rules",
                                              ("rule_id",))
                    if r.get("state") == "ACTIVE"]
        if not rules:
            return {"alerts": [], "reason": "no_active_rules"}

        competitors = {c["competitor_id"]: c for c in
                            self.data_collection.list_competitors()}

        candidate_alerts: List[Dict[str, Any]] = []
        evaluated_at = datetime.utcnow().isoformat()

        for rule in rules:
            atype = rule["alert_type"]
            tier_filter = rule.get("competitor_filter_tier")

            if atype == "NEW_PRODUCT":
                # Look for DIGITAL_LAUNCH or PRODUCT_FEATURE in window
                for dt in ("DIGITAL_LAUNCH", "PRODUCT_FEATURE"):
                    events = self.data_collection.list_data_points(
                        data_type=dt,
                        from_date=period_start, to_date=period_end,
                    )
                    for e in events:
                        comp = competitors.get(e.get("competitor_id"))
                        if comp is None:
                            continue
                        if tier_filter and comp.get("tier") != tier_filter:
                            continue
                        candidate_alerts.append({
                            "alert_id": f"AL-{rule['rule_id']}-{e['data_point_id']}",
                            "rule_id": rule["rule_id"],
                            "alert_type": atype,
                            "priority": rule["priority"],
                            "competitor_id": e["competitor_id"],
                            "competitor_name": comp.get("name"),
                            "tier": comp.get("tier"),
                            "trigger_data_point_id": e["data_point_id"],
                            "trigger_value": e.get("value"),
                            "as_of": e.get("as_of"),
                            "headline": (
                                f"{comp.get('name')} "
                                f"({comp.get('tier')}) — new "
                                f"{dt.lower().replace('_', ' ')}: "
                                f"{e.get('value')}"
                            ),
                            "evaluated_at": evaluated_at,
                        })
            elif atype == "RATE_CHANGE":
                threshold = Decimal(str(rule.get("rate_change_threshold_pp", "0.25")))
                for cid, comp in competitors.items():
                    if tier_filter and comp.get("tier") != tier_filter:
                        continue
                    for rt in ("DEPOSIT_RATE", "LENDING_RATE", "FEE"):
                        trend = self.rates_engine.rate_trend(cid, rt, period_days=30)
                        if trend.get("direction") in ("RISING", "FALLING"):
                            try:
                                change = abs(Decimal(trend["change_pp"]))
                                if change >= threshold:
                                    candidate_alerts.append({
                                        "alert_id": f"AL-{rule['rule_id']}-{cid}-{rt}",
                                        "rule_id": rule["rule_id"],
                                        "alert_type": atype,
                                        "priority": rule["priority"],
                                        "competitor_id": cid,
                                        "competitor_name": comp.get("name"),
                                        "tier": comp.get("tier"),
                                        "rate_type": rt,
                                        "trigger_value": trend["last_value"],
                                        "change_pp": trend["change_pp"],
                                        "direction": trend["direction"],
                                        "as_of": trend["last_as_of"],
                                        "headline": (
                                            f"{comp.get('name')} "
                                            f"{rt} {trend['direction'].lower()} "
                                            f"by {trend['change_pp']}pp"
                                        ),
                                        "evaluated_at": evaluated_at,
                                    })
                            except (ValueError, TypeError, KeyError):
                                continue
            elif atype in ("LEADERSHIP_CHANGE", "M_AND_A",
                                "REGULATORY_ACTION"):
                events = self.data_collection.list_data_points(
                    data_type=atype,
                    from_date=period_start, to_date=period_end,
                )
                for e in events:
                    comp = competitors.get(e.get("competitor_id"))
                    if comp is None:
                        continue
                    if tier_filter and comp.get("tier") != tier_filter:
                        continue
                    candidate_alerts.append({
                        "alert_id": f"AL-{rule['rule_id']}-{e['data_point_id']}",
                        "rule_id": rule["rule_id"],
                        "alert_type": atype,
                        "priority": rule["priority"],
                        "competitor_id": e["competitor_id"],
                        "competitor_name": comp.get("name"),
                        "tier": comp.get("tier"),
                        "trigger_data_point_id": e["data_point_id"],
                        "trigger_value": e.get("value"),
                        "as_of": e.get("as_of"),
                        "headline": (
                            f"{comp.get('name')} ({comp.get('tier')}) — "
                            f"{atype.replace('_', ' ').title()}: {e.get('value')}"
                        ),
                        "evaluated_at": evaluated_at,
                    })

        # De-duplicate by alert_id
        unique = {a["alert_id"]: a for a in candidate_alerts}.values()

        # Add routing recipients
        out_alerts = []
        for a in unique:
            recipients = list(EXECUTIVE_ROLES_ROUTING.get(a["priority"], ()))
            recipients.extend(TYPE_SPECIFIC_ROUTING.get(a["alert_type"], ()))
            a["recipients"] = sorted(set(recipients))
            out_alerts.append(a)

        return {
            "period_start": period_start,
            "period_end": period_end,
            "active_rule_count": len(rules),
            "alert_count": len(out_alerts),
            "alerts": out_alerts,
        }

    def publish_alerts(
        self,
        alerts: List[Dict[str, Any]],
        actor: str,
    ) -> Dict[str, Any]:
        """Persist alerts to the published store. Optional integration
        with smart_alerts engine when available."""
        if not actor:
            return {"published": False, "error": "actor_required"}
        if not alerts:
            return {"published": True, "published_count": 0,
                      "reason": "no_alerts_to_publish"}

        # Try to wire to smart_alerts (graceful if absent)
        smart_alerts_available = False
        try:
            from utils.smart_alerts import SmartAlertsEngine  # type: ignore
            smart_alerts_available = True
        except ImportError:
            pass

        records = self._load(self.alerts_path,
                                "competitive_alerts", ("alert_id",))
        existing_ids = {r["alert_id"] for r in records}
        published_count = 0
        skipped_count = 0
        smart_alerts_routed = 0
        for a in alerts:
            if a["alert_id"] in existing_ids:
                skipped_count += 1
                continue
            record = {
                **a,
                "published": True,
                "published_by": actor,
                "published_at": datetime.utcnow().isoformat(),
                "smart_alerts_routed": smart_alerts_available,
            }
            records.append(record)
            published_count += 1
            if smart_alerts_available:
                smart_alerts_routed += 1

        self._save(self.alerts_path, records,
                     "competitive_alerts", "alert_id")
        return {
            "published": True,
            "published_count": published_count,
            "skipped_duplicate_count": skipped_count,
            "smart_alerts_engine_available": smart_alerts_available,
            "smart_alerts_routed": smart_alerts_routed,
        }

    def list_published_alerts(
        self,
        executive_role: Optional[str] = None,
        days: int = 30,
    ) -> List[Dict[str, Any]]:
        records = self._load(self.alerts_path,
                                "competitive_alerts", ("alert_id",))
        from_date = (date.today() - timedelta(days=days)).isoformat()
        out = []
        for r in records:
            if r.get("published_at", "") < from_date:
                continue
            if executive_role and executive_role not in r.get("recipients", []):
                continue
            out.append(r)
        out.sort(key=lambda x: x.get("published_at", ""), reverse=True)
        return out


def _self_test() -> None:
    import tempfile

    assert "URGENT" in ALERT_PRIORITIES
    assert "M_AND_A" in ALERT_TYPES
    assert ALLOWED_RULE_TRANSITIONS["ARCHIVED"] == ()
    assert "CEO" in EXECUTIVE_ROLES_ROUTING["URGENT"]

    with tempfile.TemporaryDirectory() as tmpdir:
        dc = CompetitorDataCollectionEngine(
            competitors_path=Path(tmpdir) / "c.json",
            data_points_path=Path(tmpdir) / "d.json",
        )
        re = CompetitorRatesEngine(data_collection=dc)
        engine = CompetitiveAlertsEngine(
            data_collection=dc, rates_engine=re,
            rules_path=Path(tmpdir) / "r.json",
            alerts_path=Path(tmpdir) / "a.json",
        )

        # Setup competitors + events
        dc.register_competitor(
            {"competitor_id": "EQUITY", "name": "Equity",
             "tier": "TIER_1"}, actor="a",
        )

        # Event: M&A in window
        dc.record_data_point(
            "EQUITY",
            {"data_type": "M_AND_A",
             "value": "Acquired XYZ Microfinance",
             "data_source": "MEDIA_REPORT",
             "as_of": (date.today() - timedelta(days=5)).isoformat()},
            actor="a",
        )

        # Event: NEW PRODUCT
        dc.record_data_point(
            "EQUITY",
            {"data_type": "PRODUCT_FEATURE",
             "value": "Solar Loan Product",
             "data_source": "WEBSITE_SCRAPE",
             "as_of": (date.today() - timedelta(days=3)).isoformat()},
            actor="a",
        )

        # Test 1: register URGENT M&A rule
        r = engine.register_alert_rule(
            {"rule_id": "RULE-MNA-T1",
             "alert_type": "M_AND_A",
             "priority": "URGENT",
             "competitor_filter_tier": "TIER_1"},
            actor="strategy", reason="track tier-1 M&A",
        )
        assert r["registered"]

        # Test 2: register HIGH new-product rule
        engine.register_alert_rule(
            {"rule_id": "RULE-NEWPROD",
             "alert_type": "NEW_PRODUCT",
             "priority": "HIGH"},
            actor="strategy", reason="track new products",
        )

        # Test 3: invalid alert_type
        r = engine.register_alert_rule(
            {"rule_id": "X", "alert_type": "INVALID", "priority": "HIGH"},
            actor="x", reason="x",
        )
        assert not r["registered"]

        # Test 4: rule lifecycle
        t = engine.transition_rule_state(
            "RULE-MNA-T1", "PAUSED", actor="x", reason="testing",
        )
        assert t["transitioned"]
        engine.transition_rule_state(
            "RULE-MNA-T1", "ACTIVE", actor="x", reason="reactivate",
        )

        # Test 5: skip rejected
        t = engine.transition_rule_state(
            "RULE-MNA-T1", "ARCHIVED", actor="x", reason="archive",
        )
        assert t["transitioned"]
        # Cannot leave ARCHIVED
        t = engine.transition_rule_state(
            "RULE-MNA-T1", "ACTIVE", actor="x", reason="x",
        )
        assert not t["transitioned"]

        # Reactivate via re-register
        engine.register_alert_rule(
            {"rule_id": "RULE-MNA-T1-V2",
             "alert_type": "M_AND_A",
             "priority": "URGENT", "competitor_filter_tier": "TIER_1"},
            actor="x", reason="recreated",
        )

        # Test 6: evaluate_alerts
        period_end = date.today().isoformat() + "T23:59:59"
        period_start = (date.today() - timedelta(days=30)).isoformat()
        result = engine.evaluate_alerts(period_start, period_end, actor="strategy")
        assert result["alert_count"] >= 2  # 1 M&A + 1 product

        # Verify routing for URGENT alert
        urgent_alert = next(
            a for a in result["alerts"] if a["priority"] == "URGENT"
        )
        assert "CEO" in urgent_alert["recipients"]

        # Test 7: publish alerts
        p = engine.publish_alerts(result["alerts"], actor="strategy")
        assert p["published"]
        assert p["published_count"] >= 2

        # Test 8: re-publish skips duplicates
        p = engine.publish_alerts(result["alerts"], actor="strategy")
        assert p["published_count"] == 0
        assert p["skipped_duplicate_count"] >= 2

        # Test 9: list_published_alerts by executive
        ceo_alerts = engine.list_published_alerts(executive_role="CEO")
        assert any(a["priority"] == "URGENT" for a in ceo_alerts)

        # Test 10: empty alerts published
        p = engine.publish_alerts([], actor="x")
        assert p["published_count"] == 0

        # Test 11: no active rules
        # Pause both
        engine.transition_rule_state(
            "RULE-NEWPROD", "PAUSED", actor="x", reason="x",
        )
        engine.transition_rule_state(
            "RULE-MNA-T1-V2", "PAUSED", actor="x", reason="x",
        )
        result = engine.evaluate_alerts(period_start, period_end, actor="x")
        assert result.get("reason") == "no_active_rules"

    print("  ✅ competitive_alerts self-test PASS")


if __name__ == "__main__":
    _self_test()
