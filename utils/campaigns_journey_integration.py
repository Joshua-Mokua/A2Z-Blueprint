"""
================================================================================
A2Z MIS 360 — Standard #398: Campaign Customer Journey Integration
================================================================================

Risk classification: Cat A (consumer protection — over-messaging
                              prevention with hard cap enforcement)

Campaign integration with customer journey: trigger from journey
events, contribute to journey state, prevent over-messaging.

Public API:
    register_journey_event_subscription(subscription_data, actor, reason)
    check_messaging_quota(customer_id) -> {within_quota, current, limit}
    record_message_sent(customer_id, campaign_id, channel, actor)
    suppress_customer(customer_id, reason, actor)
    is_suppressed(customer_id) -> bool
    journey_event_to_campaign(event_data, actor) -> List of triggered

DEFAULT_QUOTAS_PER_DAY byte-for-byte:
    EMAIL: 3, SMS: 2, PUSH: 5, RM: 1, BRANCH: 1, SOCIAL: 5

JOURNEY_EVENT_TYPES byte-for-byte (8): aligned with campaigns_triggers
    TRIGGER_EVENT_TYPES for cross-engine consistency

SUPPRESSION_REASONS byte-for-byte (5):
    OPT_OUT, COMPLAINT, REGULATORY_HOLD, BEREAVEMENT, MANUAL

Honesty rules:
    Rule 1: over-quota messages rejected with explicit reason — never
            silently dropped; campaign team sees the suppression
    Rule 4: actor + reason mandatory on suppression
    Rule 6: invalid channel / suppression reason rejected

================================================================================
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, date, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from utils.campaigns_orchestration import CHANNEL_DISPATCHERS


DEFAULT_QUOTAS_PER_DAY: Dict[str, int] = {
    "EMAIL": 3, "SMS": 2, "PUSH": 5, "RM": 1, "BRANCH": 1, "SOCIAL": 5,
}

JOURNEY_EVENT_TYPES: Tuple[str, ...] = (
    "SALARY_CREDIT", "ANNIVERSARY", "PRODUCT_EXPIRY",
    "LIFE_EVENT", "BALANCE_THRESHOLD", "INACTIVITY",
    "LOAN_COMPLETION", "BIRTHDAY",
)

SUPPRESSION_REASONS: Tuple[str, ...] = (
    "OPT_OUT", "COMPLAINT", "REGULATORY_HOLD", "BEREAVEMENT", "MANUAL",
)


class CampaignsJourneyIntegrationEngine:
    """Journey integration + over-messaging prevention."""

    def __init__(
        self,
        message_log_path: Optional[Path] = None,
        suppressions_path: Optional[Path] = None,
        subscriptions_path: Optional[Path] = None,
    ):
        base = Path(__file__).parent.parent / "data"
        self.message_log_path = message_log_path or base / "campaign_message_log.json"
        self.suppressions_path = suppressions_path or base / "customer_suppressions.json"
        self.subscriptions_path = subscriptions_path or base / "journey_subscriptions.json"

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

    def register_journey_event_subscription(
        self, subscription_data: Dict[str, Any], actor: str, reason: str,
    ) -> Dict[str, Any]:
        if not actor or not reason:
            return {"registered": False, "error": "actor_and_reason_required"}
        for f in ("subscription_id", "campaign_id", "event_type"):
            if f not in subscription_data:
                return {"registered": False, "error": f"missing_field:{f}"}
        if subscription_data["event_type"] not in JOURNEY_EVENT_TYPES:
            return {
                "registered": False,
                "error": f"invalid_event_type:{subscription_data['event_type']}",
                "valid_types": list(JOURNEY_EVENT_TYPES),
            }
        records = self._load(self.subscriptions_path,
                                  "journey_subscriptions",
                                  ("subscription_id",))
        if any(r.get("subscription_id") == subscription_data["subscription_id"]
                  for r in records):
            return {"registered": False, "error": "duplicate_subscription_id"}
        records.append({
            "subscription_id": subscription_data["subscription_id"],
            "campaign_id": subscription_data["campaign_id"],
            "event_type": subscription_data["event_type"],
            "active": subscription_data.get("active", True),
            "registered_by": actor,
            "registered_at": datetime.utcnow().isoformat(),
            "registration_reason": reason,
        })
        ok = self._save(self.subscriptions_path, records,
                          "journey_subscriptions", "subscription_id")
        return {"registered": ok}

    def check_messaging_quota(
        self, customer_id: str, channel: str, day: Optional[str] = None,
    ) -> Dict[str, Any]:
        if channel not in CHANNEL_DISPATCHERS:
            return {"within_quota": False,
                      "error": f"invalid_channel:{channel}"}
        target_day = day or date.today().isoformat()
        records = self._load(self.message_log_path,
                                 "campaign_message_log", ("log_id",))
        sent_today = sum(
            1 for r in records
            if r.get("customer_id") == customer_id
            and r.get("channel") == channel
            and r.get("sent_at", "").startswith(target_day)
        )
        limit = DEFAULT_QUOTAS_PER_DAY.get(channel, 100)
        return {
            "customer_id": customer_id,
            "channel": channel,
            "day": target_day,
            "current": sent_today,
            "limit": limit,
            "within_quota": sent_today < limit,
            "remaining": max(0, limit - sent_today),
        }

    def record_message_sent(
        self, customer_id: str, campaign_id: str, channel: str, actor: str,
    ) -> Dict[str, Any]:
        if not actor:
            return {"recorded": False, "error": "actor_required"}
        if channel not in CHANNEL_DISPATCHERS:
            return {"recorded": False,
                      "error": f"invalid_channel:{channel}"}

        # Check suppression
        if self.is_suppressed(customer_id):
            return {
                "recorded": False,
                "error": "customer_suppressed",
                "reason": "consumer_protection_suppression_active",
            }

        # Check quota
        quota = self.check_messaging_quota(customer_id, channel)
        if not quota["within_quota"]:
            return {
                "recorded": False,
                "error": "quota_exceeded",
                "current": quota["current"],
                "limit": quota["limit"],
            }

        records = self._load(self.message_log_path,
                                 "campaign_message_log", ("log_id",))
        log_id = (f"MSG-{customer_id}-{campaign_id}-{channel}-"
                       f"{int(datetime.utcnow().timestamp() * 1000)}")
        records.append({
            "log_id": log_id,
            "customer_id": customer_id,
            "campaign_id": campaign_id,
            "channel": channel,
            "actor": actor,
            "sent_at": datetime.utcnow().isoformat(),
        })
        ok = self._save(self.message_log_path, records,
                          "campaign_message_log", "log_id")
        return {"recorded": ok, "log_id": log_id,
                  "remaining_in_channel_quota": quota["remaining"] - 1}

    def suppress_customer(
        self, customer_id: str, reason: str, actor: str, notes: str = "",
    ) -> Dict[str, Any]:
        if not actor:
            return {"suppressed": False, "error": "actor_required"}
        if reason not in SUPPRESSION_REASONS:
            return {
                "suppressed": False,
                "error": f"invalid_reason:{reason}",
                "valid_reasons": list(SUPPRESSION_REASONS),
            }
        records = self._load(self.suppressions_path,
                                 "customer_suppressions",
                                 ("suppression_id",))
        # Idempotent: if active suppression exists, return it
        existing = next((r for r in records
                            if r.get("customer_id") == customer_id
                            and r.get("active")), None)
        if existing:
            return {"suppressed": True, "already_suppressed": True,
                      "suppression_id": existing["suppression_id"]}
        sup_id = (f"SUP-{customer_id}-"
                       f"{int(datetime.utcnow().timestamp())}")
        records.append({
            "suppression_id": sup_id,
            "customer_id": customer_id,
            "reason": reason,
            "notes": notes,
            "active": True,
            "actor": actor,
            "applied_at": datetime.utcnow().isoformat(),
        })
        ok = self._save(self.suppressions_path, records,
                          "customer_suppressions", "suppression_id")
        return {"suppressed": ok, "suppression_id": sup_id}

    def lift_suppression(
        self, customer_id: str, actor: str, reason: str,
    ) -> Dict[str, Any]:
        if not actor or not reason:
            return {"lifted": False, "error": "actor_and_reason_required"}
        records = self._load(self.suppressions_path,
                                 "customer_suppressions",
                                 ("suppression_id",))
        lifted = 0
        for r in records:
            if r.get("customer_id") == customer_id and r.get("active"):
                r["active"] = False
                r["lifted_at"] = datetime.utcnow().isoformat()
                r["lifted_by"] = actor
                r["lift_reason"] = reason
                lifted += 1
        if lifted:
            self._save(self.suppressions_path, records,
                         "customer_suppressions", "suppression_id")
        return {"lifted": lifted > 0, "count": lifted}

    def is_suppressed(self, customer_id: str) -> bool:
        records = self._load(self.suppressions_path,
                                 "customer_suppressions",
                                 ("suppression_id",))
        return any(r.get("customer_id") == customer_id and r.get("active")
                       for r in records)

    def journey_event_to_campaign(
        self, event_data: Dict[str, Any], actor: str,
    ) -> Dict[str, Any]:
        if not actor:
            return {"triggered": [], "error": "actor_required"}
        event_type = event_data.get("event_type")
        if event_type not in JOURNEY_EVENT_TYPES:
            return {"triggered": [],
                      "error": f"invalid_event_type:{event_type}"}
        subs = [r for r in self._load(self.subscriptions_path,
                                              "journey_subscriptions",
                                              ("subscription_id",))
                   if r.get("active") and r.get("event_type") == event_type]
        if not subs:
            return {
                "event_type": event_type,
                "triggered": [],
                "reason": "no_active_subscriptions",
            }

        customer_id = event_data.get("customer_id")
        if customer_id and self.is_suppressed(customer_id):
            return {
                "event_type": event_type,
                "customer_id": customer_id,
                "triggered": [],
                "reason": "customer_suppressed",
            }

        triggered = [
            {"subscription_id": s["subscription_id"],
             "campaign_id": s["campaign_id"]}
            for s in subs
        ]
        return {
            "event_type": event_type,
            "customer_id": customer_id,
            "subscriptions_matched": len(subs),
            "triggered": triggered,
        }


def _self_test() -> None:
    import tempfile

    assert "OPT_OUT" in SUPPRESSION_REASONS
    assert DEFAULT_QUOTAS_PER_DAY["EMAIL"] == 3

    with tempfile.TemporaryDirectory() as tmpdir:
        engine = CampaignsJourneyIntegrationEngine(
            message_log_path=Path(tmpdir) / "msg.json",
            suppressions_path=Path(tmpdir) / "sup.json",
            subscriptions_path=Path(tmpdir) / "sub.json",
        )

        # Test 1: register subscription
        r = engine.register_journey_event_subscription(
            {"subscription_id": "SUB-1", "campaign_id": "CAMP-001",
             "event_type": "ANNIVERSARY"},
            actor="x", reason="r",
        )
        assert r["registered"]

        # Test 2: invalid event_type
        r = engine.register_journey_event_subscription(
            {"subscription_id": "X", "campaign_id": "Y",
             "event_type": "INVALID"},
            actor="x", reason="r",
        )
        assert not r["registered"]

        # Test 3: check quota for fresh customer
        q = engine.check_messaging_quota("C1", "EMAIL")
        assert q["within_quota"]
        assert q["current"] == 0
        assert q["limit"] == 3

        # Test 4: send 3 messages → quota exceeded on 4th
        for i in range(3):
            r = engine.record_message_sent("C1", "CAMP-001", "EMAIL", actor="a")
            assert r["recorded"], i
        r = engine.record_message_sent("C1", "CAMP-001", "EMAIL", actor="a")
        assert not r["recorded"]
        assert r["error"] == "quota_exceeded"

        # Test 5: different channel still has quota
        r = engine.record_message_sent("C1", "CAMP-001", "SMS", actor="a")
        assert r["recorded"]

        # Test 6: invalid channel
        r = engine.record_message_sent("C1", "CAMP-001", "INVALID", actor="a")
        assert not r["recorded"]

        # Test 7: suppression
        r = engine.suppress_customer("C1", "OPT_OUT", actor="dpo",
                                              notes="customer requested")
        assert r["suppressed"]
        assert engine.is_suppressed("C1")

        # Test 8: suppressed customer cannot receive messages
        r = engine.record_message_sent("C1", "CAMP-001", "PUSH", actor="a")
        assert not r["recorded"]
        assert r["error"] == "customer_suppressed"

        # Test 9: invalid suppression reason
        r = engine.suppress_customer("C2", "INVALID", actor="dpo")
        assert not r["suppressed"]

        # Test 10: idempotent suppression
        r = engine.suppress_customer("C1", "OPT_OUT", actor="dpo")
        assert r["suppressed"]
        assert r.get("already_suppressed")

        # Test 11: lift suppression
        r = engine.lift_suppression("C1", actor="dpo",
                                            reason="opt-in re-confirmed")
        assert r["lifted"]
        assert not engine.is_suppressed("C1")

        # Test 12: journey event triggers
        r = engine.journey_event_to_campaign(
            {"event_type": "ANNIVERSARY", "customer_id": "C5"},
            actor="adapter",
        )
        assert r["subscriptions_matched"] == 1
        assert len(r["triggered"]) == 1

        # Test 13: suppressed customer's journey event blocked
        engine.suppress_customer("C5", "REGULATORY_HOLD", actor="dpo")
        r = engine.journey_event_to_campaign(
            {"event_type": "ANNIVERSARY", "customer_id": "C5"},
            actor="adapter",
        )
        assert r["reason"] == "customer_suppressed"
        assert r["triggered"] == []

    print("  ✅ campaigns_journey_integration self-test PASS")


if __name__ == "__main__":
    _self_test()
