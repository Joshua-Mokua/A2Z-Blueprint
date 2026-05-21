"""
================================================================================
A2Z MIS 360 — Standard #287: Scheduled Reports & Alerts
================================================================================

Risk classification: Cat C (delivery orchestration; read-side over upstream
report-producing engines).

Subcategory: analytics_hub

Schedule report generation and delivery via email, Slack, and Teams.
Scheduling, recipient management, delivery state, and alert thresholds
that turn metric breaches into delivery events. Does NOT generate the
report content — composes upstream report engines (CBK reports,
performance dashboards, analytics hub views).

Public API:
    register_schedule(schedule_data, actor, reason)
    transition_schedule_state(schedule_id, new_state, actor, reason)
    register_alert_rule(alert_data, actor, reason)
    transition_alert_state(alert_id, new_state, actor, reason)
    record_delivery(delivery_data, actor)
    delivery_metrics(days=30) -> Dict
    schedules_due(within_minutes=60) -> List

DELIVERY_CHANNELS byte-for-byte (4):
    EMAIL, SLACK, TEAMS, DOWNLOAD_LINK

SCHEDULE_FREQUENCIES byte-for-byte (6):
    HOURLY, DAILY, WEEKLY, MONTHLY, QUARTERLY, ON_DEMAND

SCHEDULE_STATES byte-for-byte (4):
    ACTIVE, PAUSED, FAILED, ARCHIVED

ALLOWED_SCHEDULE_TRANSITIONS (Rule 4):
    ACTIVE   → PAUSED | FAILED | ARCHIVED
    PAUSED   → ACTIVE | ARCHIVED
    FAILED   → ACTIVE | ARCHIVED
    ARCHIVED → ()

ALERT_TRIGGER_TYPES byte-for-byte (5):
    THRESHOLD_BREACH, TREND_DEVIATION, ANOMALY, MISSING_DATA, MANUAL

ALERT_STATES byte-for-byte (4):
    ACTIVE, SILENCED, ACKNOWLEDGED, RESOLVED

ALLOWED_ALERT_TRANSITIONS (Rule 4):
    ACTIVE       → SILENCED | ACKNOWLEDGED | RESOLVED
    SILENCED     → ACTIVE | RESOLVED
    ACKNOWLEDGED → RESOLVED
    RESOLVED     → ()

DELIVERY_STATES byte-for-byte (4):
    QUEUED, SENT, DELIVERED, FAILED

DEFAULT_DELIVERY_TIMEOUT_SECONDS = 60
DEFAULT_RETRY_LIMIT = 3

================================================================================
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


DELIVERY_CHANNELS: Tuple[str, ...] = (
    "EMAIL", "SLACK", "TEAMS", "DOWNLOAD_LINK",
)

SCHEDULE_FREQUENCIES: Tuple[str, ...] = (
    "HOURLY", "DAILY", "WEEKLY", "MONTHLY", "QUARTERLY", "ON_DEMAND",
)

SCHEDULE_STATES: Tuple[str, ...] = (
    "ACTIVE", "PAUSED", "FAILED", "ARCHIVED",
)

ALLOWED_SCHEDULE_TRANSITIONS: Dict[str, Tuple[str, ...]] = {
    "ACTIVE":   ("PAUSED", "FAILED", "ARCHIVED"),
    "PAUSED":   ("ACTIVE", "ARCHIVED"),
    "FAILED":   ("ACTIVE", "ARCHIVED"),
    "ARCHIVED": (),
}

ALERT_TRIGGER_TYPES: Tuple[str, ...] = (
    "THRESHOLD_BREACH", "TREND_DEVIATION", "ANOMALY",
    "MISSING_DATA", "MANUAL",
)

ALERT_STATES: Tuple[str, ...] = (
    "ACTIVE", "SILENCED", "ACKNOWLEDGED", "RESOLVED",
)

ALLOWED_ALERT_TRANSITIONS: Dict[str, Tuple[str, ...]] = {
    "ACTIVE":       ("SILENCED", "ACKNOWLEDGED", "RESOLVED"),
    "SILENCED":     ("ACTIVE", "RESOLVED"),
    "ACKNOWLEDGED": ("RESOLVED",),
    "RESOLVED":     (),
}

DELIVERY_STATES: Tuple[str, ...] = (
    "QUEUED", "SENT", "DELIVERED", "FAILED",
)

DEFAULT_DELIVERY_TIMEOUT_SECONDS = 60
DEFAULT_RETRY_LIMIT = 3


class ScheduledReportsEngine:
    """Schedule + alert + delivery registry — read-side composition."""

    def __init__(
        self,
        schedules_path: Optional[Path] = None,
        alerts_path: Optional[Path] = None,
        deliveries_path: Optional[Path] = None,
    ):
        base = Path(__file__).parent.parent / "data"
        self.schedules_path = schedules_path or base / "report_schedules.json"
        self.alerts_path = alerts_path or base / "report_alerts.json"
        self.deliveries_path = (
            deliveries_path or base / "report_deliveries.json"
        )

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

    def register_schedule(
        self, schedule_data: Dict[str, Any], actor: str, reason: str,
    ) -> Dict[str, Any]:
        if not actor or not reason:
            return {"registered": False, "error": "actor_and_reason_required"}
        for f in ("schedule_id", "report_id", "frequency",
                      "channel", "recipients"):
            if f not in schedule_data or schedule_data[f] in (None, "", []):
                return {"registered": False, "error": f"missing_field:{f}"}
        if schedule_data["frequency"] not in SCHEDULE_FREQUENCIES:
            return {"registered": False,
                       "error": f"invalid_frequency:{schedule_data['frequency']}"}
        if schedule_data["channel"] not in DELIVERY_CHANNELS:
            return {"registered": False,
                       "error": f"invalid_channel:{schedule_data['channel']}"}
        if not isinstance(schedule_data["recipients"], list):
            return {"registered": False, "error": "recipients_must_be_list"}
        records = self._load(self.schedules_path,
                                "report_schedules", ("schedule_id",))
        if any(r.get("schedule_id") == schedule_data["schedule_id"]
                 for r in records):
            return {"registered": False, "error": "duplicate_schedule_id"}
        record = {
            "schedule_id": schedule_data["schedule_id"],
            "report_id": schedule_data["report_id"],
            "frequency": schedule_data["frequency"],
            "channel": schedule_data["channel"],
            "recipients": list(schedule_data["recipients"]),
            "next_run_at": schedule_data.get(
                "next_run_at",
                (datetime.utcnow() + timedelta(hours=1)).isoformat(),
            ),
            "state": "ACTIVE",
            "registered_by": actor,
            "registered_at": datetime.utcnow().isoformat(),
            "registration_reason": reason,
            "transitions": [{
                "to": "ACTIVE", "actor": actor,
                "at": datetime.utcnow().isoformat(),
            }],
        }
        records.append(record)
        ok = self._save(self.schedules_path, records,
                          "report_schedules", "schedule_id")
        return {"registered": ok, "schedule_id": schedule_data["schedule_id"]}

    def transition_schedule_state(
        self, schedule_id: str, new_state: str, actor: str, reason: str,
    ) -> Dict[str, Any]:
        if not actor or not reason:
            return {"transitioned": False, "error": "actor_and_reason_required"}
        if new_state not in SCHEDULE_STATES:
            return {"transitioned": False, "error": f"invalid_state:{new_state}"}
        records = self._load(self.schedules_path,
                                "report_schedules", ("schedule_id",))
        for r in records:
            if r.get("schedule_id") == schedule_id:
                current = r.get("state", "ACTIVE")
                allowed = ALLOWED_SCHEDULE_TRANSITIONS.get(current, ())
                if new_state not in allowed:
                    return {"transitioned": False,
                               "error": f"transition_not_allowed:{current}_to_{new_state}"}
                r["state"] = new_state
                r.setdefault("transitions", []).append({
                    "to": new_state, "actor": actor,
                    "at": datetime.utcnow().isoformat(),
                    "reason": reason,
                })
                ok = self._save(self.schedules_path, records,
                                  "report_schedules", "schedule_id")
                return {"transitioned": ok, "from": current, "to": new_state}
        return {"transitioned": False, "error": "schedule_not_found"}

    def register_alert_rule(
        self, alert_data: Dict[str, Any], actor: str, reason: str,
    ) -> Dict[str, Any]:
        if not actor or not reason:
            return {"registered": False, "error": "actor_and_reason_required"}
        for f in ("alert_id", "metric_id", "trigger_type",
                      "channel", "recipients"):
            if f not in alert_data or alert_data[f] in (None, "", []):
                return {"registered": False, "error": f"missing_field:{f}"}
        if alert_data["trigger_type"] not in ALERT_TRIGGER_TYPES:
            return {"registered": False,
                       "error": f"invalid_trigger:{alert_data['trigger_type']}"}
        if alert_data["channel"] not in DELIVERY_CHANNELS:
            return {"registered": False,
                       "error": f"invalid_channel:{alert_data['channel']}"}
        if not isinstance(alert_data["recipients"], list):
            return {"registered": False, "error": "recipients_must_be_list"}
        records = self._load(self.alerts_path,
                                "report_alerts", ("alert_id",))
        if any(r.get("alert_id") == alert_data["alert_id"] for r in records):
            return {"registered": False, "error": "duplicate_alert_id"}
        record = {
            "alert_id": alert_data["alert_id"],
            "metric_id": alert_data["metric_id"],
            "trigger_type": alert_data["trigger_type"],
            "threshold_value": alert_data.get("threshold_value"),
            "channel": alert_data["channel"],
            "recipients": list(alert_data["recipients"]),
            "state": "ACTIVE",
            "registered_by": actor,
            "registered_at": datetime.utcnow().isoformat(),
            "registration_reason": reason,
            "transitions": [{
                "to": "ACTIVE", "actor": actor,
                "at": datetime.utcnow().isoformat(),
            }],
        }
        records.append(record)
        ok = self._save(self.alerts_path, records,
                          "report_alerts", "alert_id")
        return {"registered": ok, "alert_id": alert_data["alert_id"]}

    def transition_alert_state(
        self, alert_id: str, new_state: str, actor: str, reason: str,
    ) -> Dict[str, Any]:
        if not actor or not reason:
            return {"transitioned": False, "error": "actor_and_reason_required"}
        if new_state not in ALERT_STATES:
            return {"transitioned": False, "error": f"invalid_state:{new_state}"}
        records = self._load(self.alerts_path,
                                "report_alerts", ("alert_id",))
        for r in records:
            if r.get("alert_id") == alert_id:
                current = r.get("state", "ACTIVE")
                allowed = ALLOWED_ALERT_TRANSITIONS.get(current, ())
                if new_state not in allowed:
                    return {"transitioned": False,
                               "error": f"transition_not_allowed:{current}_to_{new_state}"}
                r["state"] = new_state
                r.setdefault("transitions", []).append({
                    "to": new_state, "actor": actor,
                    "at": datetime.utcnow().isoformat(),
                    "reason": reason,
                })
                ok = self._save(self.alerts_path, records,
                                  "report_alerts", "alert_id")
                return {"transitioned": ok, "from": current, "to": new_state}
        return {"transitioned": False, "error": "alert_not_found"}

    def record_delivery(
        self, delivery_data: Dict[str, Any], actor: str,
    ) -> Dict[str, Any]:
        if not actor:
            return {"recorded": False, "error": "actor_required"}
        for f in ("delivery_id", "schedule_id", "channel"):
            if f not in delivery_data or not delivery_data[f]:
                return {"recorded": False, "error": f"missing_field:{f}"}
        if delivery_data["channel"] not in DELIVERY_CHANNELS:
            return {"recorded": False,
                       "error": f"invalid_channel:{delivery_data['channel']}"}
        records = self._load(self.deliveries_path,
                                "report_deliveries", ("delivery_id",))
        if any(r.get("delivery_id") == delivery_data["delivery_id"]
                 for r in records):
            return {"recorded": False, "error": "duplicate_delivery_id"}
        record = {
            "delivery_id": delivery_data["delivery_id"],
            "schedule_id": delivery_data["schedule_id"],
            "alert_id": delivery_data.get("alert_id", ""),
            "channel": delivery_data["channel"],
            "recipients": list(delivery_data.get("recipients", [])),
            "state": delivery_data.get("state", "QUEUED"),
            "queued_at": datetime.utcnow().isoformat(),
            "queued_by": actor,
            "retry_count": 0,
        }
        if record["state"] not in DELIVERY_STATES:
            return {"recorded": False,
                       "error": f"invalid_state:{record['state']}"}
        records.append(record)
        ok = self._save(self.deliveries_path, records,
                          "report_deliveries", "delivery_id")
        return {"recorded": ok, "delivery_id": delivery_data["delivery_id"]}

    def delivery_metrics(self, days: int = 30) -> Dict[str, Any]:
        cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()
        records = self._load(self.deliveries_path,
                                "report_deliveries", ("delivery_id",))
        recent = [r for r in records
                       if r.get("queued_at", "") >= cutoff]
        delivered = sum(1 for r in recent
                              if r.get("state") == "DELIVERED")
        failed = sum(1 for r in recent
                          if r.get("state") == "FAILED")
        # Per-channel breakdown
        per_channel: Dict[str, Dict[str, int]] = {}
        for r in recent:
            ch = r.get("channel", "")
            per_channel.setdefault(ch, {"total": 0, "delivered": 0,
                                                  "failed": 0})
            per_channel[ch]["total"] += 1
            if r.get("state") == "DELIVERED":
                per_channel[ch]["delivered"] += 1
            elif r.get("state") == "FAILED":
                per_channel[ch]["failed"] += 1
        return {
            "window_days": days,
            "total_deliveries": len(recent),
            "delivered": delivered,
            "failed": failed,
            "delivery_rate_pct": round(
                (delivered / len(recent) * 100) if recent else 0, 1,
            ),
            "per_channel": per_channel,
        }

    def schedules_due(self, within_minutes: int = 60) -> List[Dict[str, Any]]:
        cutoff = (datetime.utcnow() + timedelta(minutes=within_minutes)).isoformat()
        records = self._load(self.schedules_path,
                                "report_schedules", ("schedule_id",))
        active = [r for r in records if r.get("state") == "ACTIVE"]
        due = [r for r in active
                  if r.get("next_run_at", "") <= cutoff]
        due.sort(key=lambda x: x.get("next_run_at", ""))
        return due


def _self_test() -> None:
    import tempfile

    assert DELIVERY_CHANNELS == ("EMAIL", "SLACK", "TEAMS", "DOWNLOAD_LINK")
    assert SCHEDULE_FREQUENCIES == (
        "HOURLY", "DAILY", "WEEKLY", "MONTHLY", "QUARTERLY", "ON_DEMAND",
    )
    assert ALLOWED_SCHEDULE_TRANSITIONS["ARCHIVED"] == ()
    assert ALERT_TRIGGER_TYPES == (
        "THRESHOLD_BREACH", "TREND_DEVIATION", "ANOMALY",
        "MISSING_DATA", "MANUAL",
    )
    assert ALLOWED_ALERT_TRANSITIONS["RESOLVED"] == ()
    assert DELIVERY_STATES == ("QUEUED", "SENT", "DELIVERED", "FAILED")
    assert DEFAULT_DELIVERY_TIMEOUT_SECONDS == 60
    assert DEFAULT_RETRY_LIMIT == 3

    with tempfile.TemporaryDirectory() as tmpdir:
        e = ScheduledReportsEngine(
            schedules_path=Path(tmpdir) / "s.json",
            alerts_path=Path(tmpdir) / "a.json",
            deliveries_path=Path(tmpdir) / "d.json",
        )
        # Schedule
        r = e.register_schedule(
            {"schedule_id": "SCH-DAILY-CBK",
             "report_id": "RPT-CBK-CAR",
             "frequency": "DAILY",
             "channel": "EMAIL",
             "recipients": ["compliance@bank.ke"]},
            actor="compliance", reason="daily CAR digest",
        )
        assert r["registered"]
        # Invalid frequency
        r = e.register_schedule(
            {"schedule_id": "X", "report_id": "Y",
             "frequency": "WHATEVER", "channel": "EMAIL",
             "recipients": ["a@b"]},
            actor="x", reason="x",
        )
        assert not r["registered"]
        # Invalid channel
        r = e.register_schedule(
            {"schedule_id": "Z", "report_id": "Y",
             "frequency": "DAILY", "channel": "FAX",
             "recipients": ["a@b"]},
            actor="x", reason="x",
        )
        assert not r["registered"]
        # Recipients must be list
        r = e.register_schedule(
            {"schedule_id": "W", "report_id": "Y",
             "frequency": "DAILY", "channel": "EMAIL",
             "recipients": "single@string"},
            actor="x", reason="x",
        )
        assert not r["registered"]

        # State machine
        r = e.transition_schedule_state("SCH-DAILY-CBK", "PAUSED",
                                              actor="compliance",
                                              reason="freeze for audit")
        assert r["transitioned"]
        r = e.transition_schedule_state("SCH-DAILY-CBK", "ACTIVE",
                                              actor="compliance",
                                              reason="resume")
        assert r["transitioned"]
        r = e.transition_schedule_state("SCH-DAILY-CBK", "ARCHIVED",
                                              actor="compliance",
                                              reason="end of program")
        assert r["transitioned"]
        # ARCHIVED is terminal
        r = e.transition_schedule_state("SCH-DAILY-CBK", "ACTIVE",
                                              actor="x", reason="x")
        assert not r["transitioned"]

        # Alert rule
        r = e.register_alert_rule(
            {"alert_id": "ALERT-CAR-LOW",
             "metric_id": "CAR",
             "trigger_type": "THRESHOLD_BREACH",
             "threshold_value": "14.5",
             "channel": "EMAIL",
             "recipients": ["cfo@bank.ke", "cro@bank.ke"]},
            actor="cro", reason="CBK CAR floor",
        )
        assert r["registered"]
        # Invalid trigger
        r = e.register_alert_rule(
            {"alert_id": "X", "metric_id": "Y",
             "trigger_type": "WHATEVER", "channel": "EMAIL",
             "recipients": ["a"]},
            actor="x", reason="x",
        )
        assert not r["registered"]

        # Alert state machine — ACKNOWLEDGED can only go to RESOLVED
        r = e.transition_alert_state("ALERT-CAR-LOW", "ACKNOWLEDGED",
                                            actor="cro", reason="seen")
        assert r["transitioned"]
        # Can't go back to ACTIVE from ACKNOWLEDGED
        r = e.transition_alert_state("ALERT-CAR-LOW", "ACTIVE",
                                            actor="x", reason="x")
        assert not r["transitioned"]
        r = e.transition_alert_state("ALERT-CAR-LOW", "RESOLVED",
                                            actor="cro", reason="fixed")
        assert r["transitioned"]
        # RESOLVED terminal
        r = e.transition_alert_state("ALERT-CAR-LOW", "ACTIVE",
                                            actor="x", reason="x")
        assert not r["transitioned"]

        # Delivery
        r = e.record_delivery(
            {"delivery_id": "DEL-001",
             "schedule_id": "SCH-DAILY-CBK",
             "channel": "EMAIL",
             "recipients": ["compliance@bank.ke"],
             "state": "DELIVERED"},
            actor="delivery-svc",
        )
        assert r["recorded"]
        # Invalid state
        r = e.record_delivery(
            {"delivery_id": "X", "schedule_id": "Y",
             "channel": "EMAIL", "state": "WHATEVER"},
            actor="x",
        )
        assert not r["recorded"]

        # Metrics
        m = e.delivery_metrics(days=30)
        assert m["total_deliveries"] == 1
        assert m["delivered"] == 1
        assert m["delivery_rate_pct"] == 100.0
        assert "EMAIL" in m["per_channel"]

        # Schedules due — register one with near-future next_run_at
        e.register_schedule(
            {"schedule_id": "SCH-NOW",
             "report_id": "RPT-X",
             "frequency": "HOURLY",
             "channel": "SLACK",
             "recipients": ["#alerts"],
             "next_run_at": (
                 datetime.utcnow() + timedelta(minutes=10)
             ).isoformat()},
            actor="ops", reason="hourly heartbeat",
        )
        due = e.schedules_due(within_minutes=30)
        assert len(due) >= 1

    print("  ✅ analytics_scheduled_reports self-test PASS")


if __name__ == "__main__":
    _self_test()
