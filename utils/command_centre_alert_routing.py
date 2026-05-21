"""
================================================================================
A2Z MIS 360 — Standard #312: Command Centre Alert Routing
================================================================================

Risk classification: Cat C (alert priority routing + executive escalation)

Smart alert routing for executives: severity-based, context-aware,
actionable. Suppresses noise. Composes v9.16 smart_alerts foundation.

Public API:
    register_routing_rule(rule_data, actor, reason)
    transition_rule_state(rule_id, new_state, actor, reason)
    route_alert(alert_data) -> Dict (recipients + suppressed reason)
    record_acknowledgement(alert_id, recipient_role, actor)
    snooze_alert(alert_id, until, actor, reason)
    executive_alert_queue(role) -> List

EXEC_ALERT_SEVERITIES byte-for-byte (5):
    CRITICAL    -- immediate action; escalate to MD
    HIGH        -- action this hour
    MEDIUM      -- action this day
    LOW         -- informational; for review
    INFO        -- audit trail only

EXEC_ROUTING_TARGETS byte-for-byte (6):
    MD, CEO, CFO, CRO, COO, BOARD

ROUTING_RULE_STATES byte-for-byte (3): ACTIVE, PAUSED, ARCHIVED

ALLOWED_RULE_TRANSITIONS (Rule 4):
    ACTIVE   → PAUSED | ARCHIVED
    PAUSED   → ACTIVE | ARCHIVED
    ARCHIVED → ()

SUPPRESSION_REASONS byte-for-byte (5):
    DUPLICATE_RECENT
    SNOOZED
    BELOW_SEVERITY_FLOOR
    QUOTA_EXCEEDED
    NO_MATCHING_RULE

DEFAULT_DEDUPE_WINDOW_MINUTES = 15
DEFAULT_DAILY_QUOTA_PER_ROLE = 50

================================================================================
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


EXEC_ALERT_SEVERITIES: Tuple[str, ...] = (
    "CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO",
)

EXEC_ROUTING_TARGETS: Tuple[str, ...] = (
    "MD", "CEO", "CFO", "CRO", "COO", "BOARD",
)

ROUTING_RULE_STATES: Tuple[str, ...] = ("ACTIVE", "PAUSED", "ARCHIVED")

ALLOWED_RULE_TRANSITIONS: Dict[str, Tuple[str, ...]] = {
    "ACTIVE":   ("PAUSED", "ARCHIVED"),
    "PAUSED":   ("ACTIVE", "ARCHIVED"),
    "ARCHIVED": (),
}

SUPPRESSION_REASONS: Tuple[str, ...] = (
    "DUPLICATE_RECENT", "SNOOZED", "BELOW_SEVERITY_FLOOR",
    "QUOTA_EXCEEDED", "NO_MATCHING_RULE",
)

DEFAULT_DEDUPE_WINDOW_MINUTES: int = 15
DEFAULT_DAILY_QUOTA_PER_ROLE: int = 50


class CommandCentreAlertRoutingEngine:
    """Executive alert routing with dedupe + quota + snooze."""

    def __init__(
        self,
        rules_path: Optional[Path] = None,
        routings_path: Optional[Path] = None,
        snoozes_path: Optional[Path] = None,
        ack_path: Optional[Path] = None,
    ):
        base = Path(__file__).parent.parent / "data"
        self.rules_path = rules_path or base / "exec_alert_rules.json"
        self.routings_path = routings_path or base / "exec_alert_routings.json"
        self.snoozes_path = snoozes_path or base / "exec_alert_snoozes.json"
        self.ack_path = ack_path or base / "exec_alert_acks.json"

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

    def register_routing_rule(
        self, rule_data: Dict[str, Any], actor: str, reason: str,
    ) -> Dict[str, Any]:
        if not actor or not reason:
            return {"registered": False, "error": "actor_and_reason_required"}
        for f in ("rule_id", "rule_name", "min_severity", "target_roles"):
            if f not in rule_data or rule_data[f] in (None, "", []):
                return {"registered": False, "error": f"missing_field:{f}"}
        if rule_data["min_severity"] not in EXEC_ALERT_SEVERITIES:
            return {"registered": False,
                       "error": f"invalid_severity:{rule_data['min_severity']}"}
        for t in rule_data["target_roles"]:
            if t not in EXEC_ROUTING_TARGETS:
                return {"registered": False, "error": f"invalid_target:{t}"}

        records = self._load(self.rules_path, "exec_alert_rules", ("rule_id",))
        if any(r.get("rule_id") == rule_data["rule_id"] for r in records):
            return {"registered": False, "error": "duplicate_rule_id"}

        record = {
            "rule_id": rule_data["rule_id"],
            "rule_name": rule_data["rule_name"],
            "min_severity": rule_data["min_severity"],
            "target_roles": list(rule_data["target_roles"]),
            "alert_type_filter": rule_data.get("alert_type_filter", []),
            "dedupe_window_minutes": rule_data.get(
                "dedupe_window_minutes", DEFAULT_DEDUPE_WINDOW_MINUTES,
            ),
            "daily_quota_per_role": rule_data.get(
                "daily_quota_per_role", DEFAULT_DAILY_QUOTA_PER_ROLE,
            ),
            "state": "ACTIVE",
            "registered_by": actor,
            "registered_at": datetime.utcnow().isoformat(),
            "registration_reason": reason,
        }
        records.append(record)
        ok = self._save(self.rules_path, records,
                          "exec_alert_rules", "rule_id")
        return {"registered": ok, "rule_id": rule_data["rule_id"]}

    def transition_rule_state(
        self, rule_id: str, new_state: str, actor: str, reason: str,
    ) -> Dict[str, Any]:
        if not actor or not reason:
            return {"transitioned": False, "error": "actor_and_reason_required"}
        if new_state not in ROUTING_RULE_STATES:
            return {"transitioned": False, "error": f"invalid_state:{new_state}"}
        records = self._load(self.rules_path, "exec_alert_rules", ("rule_id",))
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
                ok = self._save(self.rules_path, records,
                                  "exec_alert_rules", "rule_id")
                return {"transitioned": ok, "from": current, "to": new_state}
        return {"transitioned": False, "error": "rule_not_found"}

    def _severity_index(self, sev: str) -> int:
        return EXEC_ALERT_SEVERITIES.index(sev) if sev in EXEC_ALERT_SEVERITIES else 99

    def _is_duplicate(
        self, alert_data: Dict[str, Any], window_minutes: int,
    ) -> bool:
        cutoff = datetime.utcnow() - timedelta(minutes=window_minutes)
        records = self._load(self.routings_path, "exec_alert_routings",
                                ("routing_id",))
        for r in records:
            if r.get("alert_type") != alert_data.get("alert_type"):
                continue
            if r.get("source_entity_id") != alert_data.get("source_entity_id"):
                continue
            try:
                routed_at = datetime.fromisoformat(r.get("routed_at", ""))
                if routed_at >= cutoff:
                    return True
            except (ValueError, TypeError):
                continue
        return False

    def _is_snoozed(self, alert_id: str, role: str) -> bool:
        snoozes = self._load(self.snoozes_path, "exec_alert_snoozes",
                                  ("snooze_id",))
        now = datetime.utcnow()
        for s in snoozes:
            if s.get("alert_id") != alert_id or s.get("role") != role:
                continue
            try:
                until = datetime.fromisoformat(s.get("until", ""))
                if until > now:
                    return True
            except (ValueError, TypeError):
                continue
        return False

    def _quota_remaining(
        self, role: str, daily_quota: int,
    ) -> int:
        today_start = datetime.utcnow().replace(hour=0, minute=0,
                                                       second=0, microsecond=0)
        records = self._load(self.routings_path, "exec_alert_routings",
                                ("routing_id",))
        used = 0
        for r in records:
            if role not in r.get("recipients", []):
                continue
            try:
                routed_at = datetime.fromisoformat(r.get("routed_at", ""))
                if routed_at >= today_start:
                    used += 1
            except (ValueError, TypeError):
                continue
        return max(0, daily_quota - used)

    def route_alert(self, alert_data: Dict[str, Any]) -> Dict[str, Any]:
        for f in ("alert_id", "severity", "alert_type"):
            if f not in alert_data or not alert_data[f]:
                return {"routed": False, "error": f"missing_field:{f}"}
        if alert_data["severity"] not in EXEC_ALERT_SEVERITIES:
            return {"routed": False,
                       "error": f"invalid_severity:{alert_data['severity']}"}

        rules = [r for r in self._load(self.rules_path,
                                            "exec_alert_rules", ("rule_id",))
                    if r.get("state") == "ACTIVE"]

        # Find matching rules
        sev_idx = self._severity_index(alert_data["severity"])
        matched_rules = []
        for rule in rules:
            rule_sev_idx = self._severity_index(rule["min_severity"])
            if sev_idx > rule_sev_idx:  # below severity floor
                continue
            type_filter = rule.get("alert_type_filter", [])
            if type_filter and alert_data["alert_type"] not in type_filter:
                continue
            matched_rules.append(rule)

        if not matched_rules:
            return {
                "routed": False,
                "suppression_reason": "NO_MATCHING_RULE",
                "alert_id": alert_data["alert_id"],
            }

        # Aggregate target roles + dedupe window
        recipients: List[str] = []
        max_dedupe_window = 0
        max_quota = 0
        for rule in matched_rules:
            for t in rule["target_roles"]:
                if t not in recipients:
                    recipients.append(t)
            max_dedupe_window = max(max_dedupe_window,
                                          rule.get("dedupe_window_minutes", 0))
            max_quota = max(max_quota,
                                rule.get("daily_quota_per_role", 0))

        # Dedupe check
        if max_dedupe_window > 0 and self._is_duplicate(alert_data, max_dedupe_window):
            return {
                "routed": False,
                "suppression_reason": "DUPLICATE_RECENT",
                "alert_id": alert_data["alert_id"],
                "matched_rule_count": len(matched_rules),
            }

        # Filter recipients by snooze + quota
        filtered_recipients: List[str] = []
        suppressed_per_role: Dict[str, str] = {}
        for role in recipients:
            if self._is_snoozed(alert_data["alert_id"], role):
                suppressed_per_role[role] = "SNOOZED"
                continue
            remaining = self._quota_remaining(role, max_quota)
            if remaining <= 0:
                suppressed_per_role[role] = "QUOTA_EXCEEDED"
                continue
            filtered_recipients.append(role)

        if not filtered_recipients:
            return {
                "routed": False,
                "suppression_reason": "QUOTA_EXCEEDED",
                "alert_id": alert_data["alert_id"],
                "suppressed_per_role": suppressed_per_role,
            }

        # Record routing
        routings = self._load(self.routings_path, "exec_alert_routings",
                                  ("routing_id",))
        routing_id = (f"ROUTE-{alert_data['alert_id']}-"
                          f"{int(datetime.utcnow().timestamp() * 1000)}")
        routings.append({
            "routing_id": routing_id,
            "alert_id": alert_data["alert_id"],
            "alert_type": alert_data["alert_type"],
            "severity": alert_data["severity"],
            "source_entity_id": alert_data.get("source_entity_id", ""),
            "recipients": filtered_recipients,
            "suppressed_per_role": suppressed_per_role,
            "routed_at": datetime.utcnow().isoformat(),
        })
        self._save(self.routings_path, routings,
                     "exec_alert_routings", "routing_id")

        return {
            "routed": True,
            "routing_id": routing_id,
            "alert_id": alert_data["alert_id"],
            "recipients": filtered_recipients,
            "suppressed_per_role": suppressed_per_role,
            "matched_rule_count": len(matched_rules),
        }

    def record_acknowledgement(
        self, alert_id: str, recipient_role: str, actor: str,
    ) -> Dict[str, Any]:
        if not actor:
            return {"acknowledged": False, "error": "actor_required"}
        if recipient_role not in EXEC_ROUTING_TARGETS:
            return {"acknowledged": False,
                       "error": f"invalid_role:{recipient_role}"}
        acks = self._load(self.ack_path, "exec_alert_acks", ("ack_id",))
        ack_id = (f"ACK-{alert_id}-{recipient_role}-"
                      f"{int(datetime.utcnow().timestamp() * 1000)}")
        acks.append({
            "ack_id": ack_id,
            "alert_id": alert_id,
            "recipient_role": recipient_role,
            "acknowledged_by": actor,
            "acknowledged_at": datetime.utcnow().isoformat(),
        })
        ok = self._save(self.ack_path, acks, "exec_alert_acks", "ack_id")
        return {"acknowledged": ok, "ack_id": ack_id}

    def snooze_alert(
        self, alert_id: str, until: str, actor: str, reason: str,
        role: Optional[str] = None,
    ) -> Dict[str, Any]:
        if not actor or not reason:
            return {"snoozed": False, "error": "actor_and_reason_required"}
        try:
            until_dt = datetime.fromisoformat(until)
            if until_dt <= datetime.utcnow():
                return {"snoozed": False, "error": "until_must_be_future"}
        except (ValueError, TypeError):
            return {"snoozed": False, "error": "invalid_until_format"}
        snoozes = self._load(self.snoozes_path, "exec_alert_snoozes",
                                  ("snooze_id",))
        snooze_id = (f"SNZ-{alert_id}-{role or 'ALL'}-"
                          f"{int(datetime.utcnow().timestamp() * 1000)}")
        snoozes.append({
            "snooze_id": snooze_id,
            "alert_id": alert_id,
            "role": role,
            "until": until,
            "snoozed_by": actor,
            "reason": reason,
            "snoozed_at": datetime.utcnow().isoformat(),
        })
        ok = self._save(self.snoozes_path, snoozes,
                          "exec_alert_snoozes", "snooze_id")
        return {"snoozed": ok, "snooze_id": snooze_id}

    def executive_alert_queue(self, role: str) -> List[Dict[str, Any]]:
        if role not in EXEC_ROUTING_TARGETS:
            return []
        records = self._load(self.routings_path, "exec_alert_routings",
                                ("routing_id",))
        out = []
        for r in records:
            if role in r.get("recipients", []):
                out.append(r)
        # Sort newest first
        out.sort(key=lambda x: x.get("routed_at", ""), reverse=True)
        return out


def _self_test() -> None:
    import tempfile

    assert "CRITICAL" in EXEC_ALERT_SEVERITIES
    assert "MD" in EXEC_ROUTING_TARGETS
    assert ALLOWED_RULE_TRANSITIONS["ARCHIVED"] == ()
    assert "DUPLICATE_RECENT" in SUPPRESSION_REASONS
    assert DEFAULT_DEDUPE_WINDOW_MINUTES == 15

    with tempfile.TemporaryDirectory() as tmpdir:
        engine = CommandCentreAlertRoutingEngine(
            rules_path=Path(tmpdir) / "r.json",
            routings_path=Path(tmpdir) / "ro.json",
            snoozes_path=Path(tmpdir) / "s.json",
            ack_path=Path(tmpdir) / "a.json",
        )
        # Test 1: register
        r = engine.register_routing_rule(
            {"rule_id": "R-NPL", "rule_name": "NPL spike",
             "min_severity": "HIGH",
             "target_roles": ["MD", "CRO"],
             "dedupe_window_minutes": 60},
            actor="head", reason="cro routing",
        )
        assert r["registered"]
        # Test 2: invalid target
        r = engine.register_routing_rule(
            {"rule_id": "X", "rule_name": "Y", "min_severity": "HIGH",
             "target_roles": ["INVALID"]},
            actor="x", reason="x",
        )
        assert not r["registered"]
        # Test 3: route a CRITICAL alert
        r = engine.route_alert(
            {"alert_id": "AL-1", "severity": "CRITICAL",
             "alert_type": "NPL_SPIKE",
             "source_entity_id": "PROD-MORTGAGE"},
        )
        assert r["routed"]
        assert "MD" in r["recipients"]
        assert "CRO" in r["recipients"]
        # Test 4: dedupe — same alert within window
        r = engine.route_alert(
            {"alert_id": "AL-2", "severity": "CRITICAL",
             "alert_type": "NPL_SPIKE",
             "source_entity_id": "PROD-MORTGAGE"},
        )
        assert not r["routed"]
        assert r["suppression_reason"] == "DUPLICATE_RECENT"
        # Test 5: severity below floor
        r = engine.route_alert(
            {"alert_id": "AL-3", "severity": "LOW",
             "alert_type": "NPL_SPIKE",
             "source_entity_id": "PROD-AUTO"},
        )
        assert not r["routed"]
        assert r["suppression_reason"] == "NO_MATCHING_RULE"
        # Test 6: snooze
        future = (datetime.utcnow() + timedelta(hours=1)).isoformat()
        r = engine.snooze_alert("AL-4", future, actor="md",
                                     reason="reviewing", role="MD")
        assert r["snoozed"]
        # Test 7: ack
        r = engine.record_acknowledgement("AL-1", "MD", actor="md")
        assert r["acknowledged"]
        # Test 8: queue
        queue = engine.executive_alert_queue("MD")
        assert len(queue) >= 1
        # Test 9: queue invalid role
        assert engine.executive_alert_queue("INVALID") == []
        # Test 10: rule transition
        r = engine.transition_rule_state(
            "R-NPL", "PAUSED", actor="head", reason="reduce noise",
        )
        assert r["transitioned"]
        r = engine.transition_rule_state(
            "R-NPL", "PAUSED", actor="x", reason="x",
        )
        # PAUSED → PAUSED not allowed
        assert not r["transitioned"]

    print("  ✅ command_centre_alert_routing self-test PASS")


if __name__ == "__main__":
    _self_test()
