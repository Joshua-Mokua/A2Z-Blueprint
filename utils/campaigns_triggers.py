"""
================================================================================
A2Z MIS 360 — Standard #391: Behavioral Trigger Engine
================================================================================

Risk classification: Cat C (event-based deterministic trigger evaluation)

Event-based campaign triggers: salary credit, anniversary, product
expiry, life event. Real-time campaign activation.

Public API:
    register_trigger(trigger_data, actor, reason)
    transition_trigger_state(trigger_id, new_state, actor, reason)
    evaluate_event(event_data, actor) -> List of triggered campaigns
    list_triggers(state=None, event_type=None) -> List

TRIGGER_EVENT_TYPES byte-for-byte (8):
    SALARY_CREDIT, ANNIVERSARY, PRODUCT_EXPIRY,
    LIFE_EVENT, BALANCE_THRESHOLD, INACTIVITY,
    LOAN_COMPLETION, BIRTHDAY

TRIGGER_STATES byte-for-byte (3):
    ACTIVE, PAUSED, ARCHIVED

Honesty rules:
    Rule 4: actor + reason mandatory
    Rule 6: invalid event_type / state rejected
    Rule 1: empty rules → empty triggered list with reason

================================================================================
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


TRIGGER_EVENT_TYPES: Tuple[str, ...] = (
    "SALARY_CREDIT", "ANNIVERSARY", "PRODUCT_EXPIRY",
    "LIFE_EVENT", "BALANCE_THRESHOLD", "INACTIVITY",
    "LOAN_COMPLETION", "BIRTHDAY",
)

TRIGGER_STATES: Tuple[str, ...] = ("ACTIVE", "PAUSED", "ARCHIVED")

ALLOWED_TRIGGER_TRANSITIONS: Dict[str, Tuple[str, ...]] = {
    "ACTIVE":   ("PAUSED", "ARCHIVED"),
    "PAUSED":   ("ACTIVE", "ARCHIVED"),
    "ARCHIVED": (),
}


class CampaignsTriggersEngine:
    """Behavioral trigger registry + event evaluation."""

    def __init__(
        self,
        triggers_path: Optional[Path] = None,
        firings_path: Optional[Path] = None,
    ):
        base = Path(__file__).parent.parent / "data"
        self.triggers_path = triggers_path or base / "campaign_triggers.json"
        self.firings_path = firings_path or base / "trigger_firings.json"

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

    def register_trigger(
        self, trigger_data: Dict[str, Any],
        actor: str, reason: str,
    ) -> Dict[str, Any]:
        if not actor or not reason:
            return {"registered": False, "error": "actor_and_reason_required"}
        for f in ("trigger_id", "campaign_id", "event_type"):
            if f not in trigger_data or not trigger_data[f]:
                return {"registered": False, "error": f"missing_field:{f}"}
        if trigger_data["event_type"] not in TRIGGER_EVENT_TYPES:
            return {
                "registered": False,
                "error": f"invalid_event_type:{trigger_data['event_type']}",
                "valid_types": list(TRIGGER_EVENT_TYPES),
            }

        records = self._load(self.triggers_path,
                                "campaign_triggers", ("trigger_id",))
        if any(r.get("trigger_id") == trigger_data["trigger_id"]
                 for r in records):
            return {"registered": False, "error": "duplicate_trigger_id"}

        records.append({
            "trigger_id": trigger_data["trigger_id"],
            "campaign_id": trigger_data["campaign_id"],
            "event_type": trigger_data["event_type"],
            "predicate": trigger_data.get("predicate", {}),
            "state": "ACTIVE",
            "registered_by": actor,
            "registered_at": datetime.utcnow().isoformat(),
            "registration_reason": reason,
        })
        ok = self._save(self.triggers_path, records,
                          "campaign_triggers", "trigger_id")
        return {"registered": ok, "trigger_id": trigger_data["trigger_id"]}

    def transition_trigger_state(
        self, trigger_id: str, new_state: str, actor: str, reason: str,
    ) -> Dict[str, Any]:
        if not actor or not reason:
            return {"transitioned": False, "error": "actor_and_reason_required"}
        if new_state not in TRIGGER_STATES:
            return {"transitioned": False, "error": f"invalid_state:{new_state}"}
        records = self._load(self.triggers_path,
                                "campaign_triggers", ("trigger_id",))
        for r in records:
            if r.get("trigger_id") == trigger_id:
                current = r.get("state", "ACTIVE")
                if new_state not in ALLOWED_TRIGGER_TRANSITIONS.get(current, ()):
                    return {
                        "transitioned": False,
                        "error": f"transition_not_allowed:{current}_to_{new_state}",
                    }
                r["state"] = new_state
                ok = self._save(self.triggers_path, records,
                                  "campaign_triggers", "trigger_id")
                return {"transitioned": ok, "from": current, "to": new_state}
        return {"transitioned": False, "error": "trigger_not_found"}

    def _matches_predicate(
        self, predicate: Dict[str, Any], event_data: Dict[str, Any],
    ) -> bool:
        """Simple predicate matching: all keys in predicate must match
        event_data values, with comparison operators where specified."""
        for k, condition in predicate.items():
            actual = event_data.get(k)
            if isinstance(condition, dict):
                # {"min": "10000"} or {"in": ["DIASPORA"]}
                if "min" in condition:
                    try:
                        if Decimal(str(actual)) < Decimal(str(condition["min"])):
                            return False
                    except (ValueError, TypeError):
                        return False
                if "max" in condition:
                    try:
                        if Decimal(str(actual)) > Decimal(str(condition["max"])):
                            return False
                    except (ValueError, TypeError):
                        return False
                if "in" in condition:
                    if actual not in condition["in"]:
                        return False
            else:
                # Direct equality
                if actual != condition:
                    return False
        return True

    def evaluate_event(
        self, event_data: Dict[str, Any], actor: str,
    ) -> Dict[str, Any]:
        if not actor:
            return {"triggered": [], "error": "actor_required"}
        event_type = event_data.get("event_type")
        if event_type not in TRIGGER_EVENT_TYPES:
            return {
                "triggered": [],
                "error": f"invalid_event_type:{event_type}",
            }

        active_triggers = [
            r for r in self._load(self.triggers_path,
                                       "campaign_triggers", ("trigger_id",))
            if r.get("state") == "ACTIVE" and r.get("event_type") == event_type
        ]
        if not active_triggers:
            return {
                "event_type": event_type,
                "triggered": [],
                "reason": "no_active_triggers_for_event_type",
            }

        triggered: List[Dict[str, Any]] = []
        firings = self._load(self.firings_path,
                                  "trigger_firings", ("firing_id",))
        for trigger in active_triggers:
            if self._matches_predicate(trigger.get("predicate", {}), event_data):
                firing_id = (f"FIRE-{trigger['trigger_id']}-"
                                  f"{int(datetime.utcnow().timestamp() * 1000)}")
                firing_record = {
                    "firing_id": firing_id,
                    "trigger_id": trigger["trigger_id"],
                    "campaign_id": trigger["campaign_id"],
                    "event_type": event_type,
                    "event_data": event_data,
                    "customer_id": event_data.get("customer_id"),
                    "actor": actor,
                    "fired_at": datetime.utcnow().isoformat(),
                }
                firings.append(firing_record)
                triggered.append(firing_record)

        self._save(self.firings_path, firings,
                     "trigger_firings", "firing_id")
        return {
            "event_type": event_type,
            "active_triggers_for_event": len(active_triggers),
            "triggered_count": len(triggered),
            "triggered": triggered,
        }

    def list_triggers(
        self, state: Optional[str] = None,
        event_type: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        records = self._load(self.triggers_path,
                                "campaign_triggers", ("trigger_id",))
        out = []
        for r in records:
            if state and r.get("state") != state:
                continue
            if event_type and r.get("event_type") != event_type:
                continue
            out.append(r)
        return out


def _self_test() -> None:
    import tempfile

    assert "SALARY_CREDIT" in TRIGGER_EVENT_TYPES
    assert ALLOWED_TRIGGER_TRANSITIONS["ARCHIVED"] == ()

    with tempfile.TemporaryDirectory() as tmpdir:
        engine = CampaignsTriggersEngine(
            triggers_path=Path(tmpdir) / "t.json",
            firings_path=Path(tmpdir) / "f.json",
        )

        # Test 1: register
        r = engine.register_trigger(
            {"trigger_id": "TRG-001", "campaign_id": "CAMP-001",
             "event_type": "SALARY_CREDIT",
             "predicate": {"amount_kes": {"min": "50000"},
                                "segment": {"in": ["DIASPORA", "WOMEN"]}}},
            actor="x", reason="r",
        )
        assert r["registered"]

        # Test 2: invalid event_type
        r = engine.register_trigger(
            {"trigger_id": "X", "campaign_id": "C", "event_type": "INVALID"},
            actor="x", reason="r",
        )
        assert not r["registered"]

        # Test 3: matching event
        r = engine.evaluate_event(
            {"event_type": "SALARY_CREDIT",
             "customer_id": "C1", "amount_kes": "75000",
             "segment": "DIASPORA"}, actor="adapter",
        )
        assert r["triggered_count"] == 1

        # Test 4: non-matching event (amount too low)
        r = engine.evaluate_event(
            {"event_type": "SALARY_CREDIT",
             "customer_id": "C2", "amount_kes": "10000",
             "segment": "DIASPORA"}, actor="adapter",
        )
        assert r["triggered_count"] == 0

        # Test 5: non-matching event (wrong segment)
        r = engine.evaluate_event(
            {"event_type": "SALARY_CREDIT",
             "customer_id": "C3", "amount_kes": "75000",
             "segment": "YOUTH"}, actor="adapter",
        )
        assert r["triggered_count"] == 0

        # Test 6: pause + verify no fire
        engine.transition_trigger_state(
            "TRG-001", "PAUSED", actor="x", reason="r",
        )
        r = engine.evaluate_event(
            {"event_type": "SALARY_CREDIT", "customer_id": "C4",
             "amount_kes": "100000", "segment": "WOMEN"},
            actor="adapter",
        )
        assert r.get("reason") == "no_active_triggers_for_event_type"

        # Test 7: archive lifecycle
        engine.transition_trigger_state(
            "TRG-001", "ACTIVE", actor="x", reason="r",
        )
        engine.transition_trigger_state(
            "TRG-001", "ARCHIVED", actor="x", reason="r",
        )
        # Cannot leave ARCHIVED
        t = engine.transition_trigger_state(
            "TRG-001", "ACTIVE", actor="x", reason="r",
        )
        assert not t["transitioned"]

        # Test 8: invalid event_type to evaluate
        r = engine.evaluate_event(
            {"event_type": "INVALID", "customer_id": "X"}, actor="a",
        )
        assert "error" in r

    print("  ✅ campaigns_triggers self-test PASS")


if __name__ == "__main__":
    _self_test()
