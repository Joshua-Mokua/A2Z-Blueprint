"""utils/smart_alerts.py — Customer alerts CONSUMER (v8.4).

Subscribes to channel reliability events from the event bus and produces
customer-facing alert payloads. CONSUMER side of L14 feedback loop
(Channel reliability → Customer experience alerts).

Per Charter §6/§7: this module is the CONSUMER of L14. It picks up
events emitted by `utils.channels_reliability` (PRODUCER) and creates
alert messages targeted to affected customers.

Three alert tiers based on severity + estimated_affected_customers:
    - URGENT (push notification + SMS): outage with >5000 affected
    - HIGH (push notification): degradation or outage with 100-5000 affected
    - INFO (in-app banner only): SLA breach or outage <100 affected

Subscription model:
    - Caller passes `since_event_id` (defaults to 0); consumer returns
      all alerts derived from events newer than that ID.
    - Caller stores the highest event_id received and passes it back on
      next call for incremental consumption (matches event_bus contract).
    - This pattern is identical to Kafka consumer offsets + works with
      Streamlit's stateless-render model.
"""
from __future__ import annotations
import json
import threading
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


# ════════════════════════════════════════════════════════════════════
# Constants
# ════════════════════════════════════════════════════════════════════

ALERT_TIER_URGENT = "URGENT"
ALERT_TIER_HIGH = "HIGH"
ALERT_TIER_INFO = "INFO"

ALERT_CHANNEL_PUSH = "PUSH"
ALERT_CHANNEL_SMS = "SMS"
ALERT_CHANNEL_IN_APP_BANNER = "IN_APP_BANNER"

# v8.25 → v9.8 — alert history persistence migrated to StateBackend.
# Backend key convention: "alert_history" is a list of JSON-serialized
# alert entries with FIFO truncation at ALERT_HISTORY_MAX_ENTRIES.
# Persistence to disk preserved for InMemoryBackend only — Redis backend
# has its own durability.
ALERT_HISTORY_PATH = Path("smart_alerts_data") / "alert_history.json"
ALERT_HISTORY_MAX_ENTRIES = 500  # rolling window — most recent N alerts
_ALERT_HISTORY_KEY = "alert_history"

_ALERT_HISTORY_LOCK = threading.Lock()
_ALERT_HISTORY_LOADED = False  # one-shot load flag


def _alert_backend():
    """Lazy import of state_backend for circular-import safety."""
    from utils.state_backend import get_default_backend
    return get_default_backend()


def _load_alert_history() -> None:
    """v8.25 → v9.8 — load persisted alert history into backend.

    Only meaningful for InMemoryBackend; RedisBackend is its own durability
    layer so this is a no-op when remote.
    """
    global _ALERT_HISTORY_LOADED
    if _ALERT_HISTORY_LOADED:
        return
    _ALERT_HISTORY_LOADED = True
    backend = _alert_backend()
    if backend.is_remote():
        return
    try:
        if not ALERT_HISTORY_PATH.exists():
            return
        raw = json.loads(ALERT_HISTORY_PATH.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            return
        entries = raw.get("entries", [])
        if not isinstance(entries, list):
            return
        # Cap to window in case persisted file was oversized
        if len(entries) > ALERT_HISTORY_MAX_ENTRIES:
            entries = entries[-ALERT_HISTORY_MAX_ENTRIES:]
        for e in entries:
            if isinstance(e, dict):
                backend.list_append(
                    _ALERT_HISTORY_KEY, e,
                    max_length=ALERT_HISTORY_MAX_ENTRIES)
    except Exception:
        pass


def _persist_alert_history() -> None:
    """v8.25 → v9.8 — atomic-write alert history to disk. Best-effort.

    Skipped for RedisBackend (Redis has its own durability). Must be
    called inside _ALERT_HISTORY_LOCK.
    """
    backend = _alert_backend()
    if backend.is_remote():
        return
    try:
        ALERT_HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
        entries = backend.list_range(_ALERT_HISTORY_KEY)
        snapshot = {
            "saved_at_iso": datetime.now(timezone.utc).isoformat(),
            "entries": entries,
        }
        tmp = ALERT_HISTORY_PATH.with_suffix(
            ALERT_HISTORY_PATH.suffix + ".tmp")
        tmp.write_text(
            json.dumps(snapshot, separators=(",", ":")),
            encoding="utf-8")
        tmp.replace(ALERT_HISTORY_PATH)
    except Exception:
        pass


def record_alert_history(alert: Dict[str, Any]) -> None:
    """v8.25 → v9.8 — append an alert to the persistent history.

    Backend-backed; idempotent on alert_id.
    """
    if not isinstance(alert, dict):
        return
    aid = alert.get("alert_id")
    if not aid:
        return
    backend = _alert_backend()
    with _ALERT_HISTORY_LOCK:
        if not _ALERT_HISTORY_LOADED:
            _load_alert_history()
        # Idempotency check — read existing entries, skip if alert_id present
        existing = backend.list_range(_ALERT_HISTORY_KEY)
        for e in existing:
            if isinstance(e, dict) and e.get("alert_id") == aid:
                return
        entry = {
            **alert,
            "recorded_at_iso": datetime.now(timezone.utc).isoformat(),
            "acknowledged_at_iso": None,
            "acknowledged_by": None,
        }
        backend.list_append(_ALERT_HISTORY_KEY, entry,
                             max_length=ALERT_HISTORY_MAX_ENTRIES)
        _persist_alert_history()


def acknowledge_alert(alert_id: str, acked_by: str = "operator") -> bool:
    """v8.25 → v9.8 — mark an alert as acknowledged.

    Returns True if found and marked, False if not found. Idempotent.

    v9.8 implementation: read all entries, modify the matching one,
    replace the list. Acks are operator-driven so this O(n) replace is
    acceptable for current alert volumes (max 500 entries).
    """
    backend = _alert_backend()
    with _ALERT_HISTORY_LOCK:
        if not _ALERT_HISTORY_LOADED:
            _load_alert_history()
        entries = backend.list_range(_ALERT_HISTORY_KEY)
        found = False
        modified = False
        for e in entries:
            if isinstance(e, dict) and e.get("alert_id") == alert_id:
                found = True
                if e.get("acknowledged_at_iso") is None:
                    e["acknowledged_at_iso"] = (
                        datetime.now(timezone.utc).isoformat())
                    e["acknowledged_by"] = acked_by
                    modified = True
                break
        if modified:
            # Rewrite the list with updated entries (atomic clear+append)
            backend.list_clear(_ALERT_HISTORY_KEY)
            for e in entries:
                backend.list_append(_ALERT_HISTORY_KEY, e,
                                     max_length=ALERT_HISTORY_MAX_ENTRIES)
            _persist_alert_history()
        return found


def get_alert_history(
    limit: Optional[int] = None,
    only_unacknowledged: bool = False,
) -> List[Dict[str, Any]]:
    """v8.25 → v9.8 — return alert history (newest first).

    Args:
        limit: max entries to return; None = all
        only_unacknowledged: if True, only entries with acknowledged_at_iso=None
    """
    backend = _alert_backend()
    with _ALERT_HISTORY_LOCK:
        if not _ALERT_HISTORY_LOADED:
            _load_alert_history()
        entries = backend.list_range(_ALERT_HISTORY_KEY)
        # Newest first
        entries = list(reversed(entries))
        if only_unacknowledged:
            entries = [e for e in entries
                        if isinstance(e, dict)
                        and e.get("acknowledged_at_iso") is None]
        if limit is not None:
            entries = entries[:limit]
        return entries


def get_alert_history_stats() -> Dict[str, Any]:
    """v8.25 → v9.8 — return summary stats for alert history."""
    backend = _alert_backend()
    with _ALERT_HISTORY_LOCK:
        if not _ALERT_HISTORY_LOADED:
            _load_alert_history()
        entries = backend.list_range(_ALERT_HISTORY_KEY)
        total = len(entries)
        acked = sum(1 for e in entries
                     if isinstance(e, dict)
                     and e.get("acknowledged_at_iso") is not None)
        unacked = total - acked
        by_tier = {"URGENT": 0, "HIGH": 0, "INFO": 0}
        for e in entries:
            if not isinstance(e, dict):
                continue
            t = e.get("tier", "")
            if t in by_tier:
                by_tier[t] += 1
        ack_rate = (round(100.0 * acked / total, 1)
                     if total > 0 else None)
        return {
            "total": total,
            "acknowledged": acked,
            "unacknowledged": unacked,
            "acknowledgement_rate_pct": ack_rate,
            "by_tier": by_tier,
            "max_entries": ALERT_HISTORY_MAX_ENTRIES,
        }


def reset_alert_history() -> Dict[str, Any]:
    """v8.25 → v9.8 — admin function to clear alert history."""
    backend = _alert_backend()
    with _ALERT_HISTORY_LOCK:
        if not _ALERT_HISTORY_LOADED:
            _load_alert_history()
        prior_count = backend.list_length(_ALERT_HISTORY_KEY)
        backend.list_clear(_ALERT_HISTORY_KEY)
        try:
            if ALERT_HISTORY_PATH.exists():
                ALERT_HISTORY_PATH.unlink()
        except Exception:
            pass
        return {
            "reset_at_iso": datetime.now(timezone.utc).isoformat(),
            "prior_entries": prior_count,
        }


# ════════════════════════════════════════════════════════════════════
# Alert dataclass
# ════════════════════════════════════════════════════════════════════

@dataclass
class CustomerAlert:
    """A customer-facing alert derived from a channel reliability event."""
    alert_id: str  # derived from source event_id
    source_event_id: int
    tier: str  # URGENT / HIGH / INFO
    delivery_channels: List[str]  # PUSH / SMS / IN_APP_BANNER
    headline: str
    body: str
    affected_channel: str
    affected_location: str
    estimated_recipients: int
    created_at_iso: str
    consumed_payload_version: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ════════════════════════════════════════════════════════════════════
# Consumer logic
# ════════════════════════════════════════════════════════════════════

def _classify_tier(severity: str, affected_count: int) -> str:
    """Map severity + affected_count to alert tier."""
    if severity == "OUTAGE" and affected_count > 5000:
        return ALERT_TIER_URGENT
    if severity in ("OUTAGE", "DEGRADATION") and affected_count >= 100:
        return ALERT_TIER_HIGH
    return ALERT_TIER_INFO


def _delivery_channels_for_tier(tier: str) -> List[str]:
    """Map tier to delivery channels."""
    if tier == ALERT_TIER_URGENT:
        return [ALERT_CHANNEL_PUSH, ALERT_CHANNEL_SMS,
                ALERT_CHANNEL_IN_APP_BANNER]
    if tier == ALERT_TIER_HIGH:
        return [ALERT_CHANNEL_PUSH, ALERT_CHANNEL_IN_APP_BANNER]
    return [ALERT_CHANNEL_IN_APP_BANNER]


def _craft_headline(channel_type: str, severity: str, location: str) -> str:
    """Generate a short customer-facing headline."""
    channel_pretty = {
        "ATM": "ATM",
        "MOBILE_APP": "Mobile App",
        "INTERNET_BANKING": "Internet Banking",
        "AGENT_BANKING": "Agent Banking",
        "USSD": "USSD Banking",
    }.get(channel_type, channel_type)

    if severity == "OUTAGE":
        return f"{channel_pretty} temporarily unavailable"
    if severity == "DEGRADATION":
        return f"{channel_pretty} experiencing slow response"
    return f"{channel_pretty} service notice"


def _craft_body(payload: Dict[str, Any]) -> str:
    """Generate customer-facing alert body with alternative-channel guidance."""
    channel_type = payload.get("channel_type", "")
    description = payload.get("description", "")
    expected = payload.get("expected_resolution_iso")
    location = payload.get("location", "")

    # Suggest alternatives based on which channel is impacted
    alternatives = {
        "ATM": "Please use mobile app, internet banking, or visit an agent.",
        "MOBILE_APP": "Please use internet banking or USSD (*xxx#) for urgent transactions.",
        "INTERNET_BANKING": "Please use mobile app or USSD (*xxx#) for urgent transactions.",
        "AGENT_BANKING": "Please use mobile app, internet banking, or visit your branch.",
        "USSD": "Please use mobile app or internet banking for urgent transactions.",
    }.get(channel_type, "Please contact our support line for assistance.")

    parts = []
    if description:
        parts.append(description)
    parts.append(alternatives)
    if expected:
        parts.append(f"Expected resolution: {expected}.")
    if location and location != "BANK_WIDE":
        parts.append(f"Affected location: {location}.")

    return " ".join(parts)


# ════════════════════════════════════════════════════════════════════
# Public CONSUMER API
# ════════════════════════════════════════════════════════════════════

class SmartAlertsConsumer:
    """L14 consumer — derives customer alerts from channel reliability events."""

    @staticmethod
    def consume(since_event_id: int = 0) -> Dict[str, Any]:
        """Read new events from the bus and produce alerts.

        Returns dict with:
            alerts: list of CustomerAlert dicts (in order, oldest first)
            new_max_event_id: highest event_id consumed (caller stores this
                              and passes back on next consume() call)
            consumed_count: number of events processed
            pattern: PUBLISHED_LANGUAGE marker
            payload_version: '1.0'
        """
        try:
            from utils.event_bus import subscribe
            from utils.channels_reliability import CHANNEL_RELIABILITY_TOPIC
            events = subscribe(CHANNEL_RELIABILITY_TOPIC,
                                since_event_id=since_event_id)
        except Exception as e:
            return {
                "status": "FAILED",
                "reason": f"event_bus subscribe failed: {type(e).__name__}: {e}",
                "alerts": [],
                "new_max_event_id": since_event_id,
                "consumed_count": 0,
            }

        alerts: List[Dict[str, Any]] = []
        max_id = since_event_id

        for event in events:
            if event.event_id > max_id:
                max_id = event.event_id

            payload = event.payload
            severity = payload.get("severity", "")
            affected_count = payload.get("estimated_affected_customers", 0)

            tier = _classify_tier(severity, affected_count)
            delivery = _delivery_channels_for_tier(tier)

            alert = CustomerAlert(
                alert_id=f"alert_{event.event_id}",
                source_event_id=event.event_id,
                tier=tier,
                delivery_channels=delivery,
                headline=_craft_headline(
                    payload.get("channel_type", ""),
                    severity,
                    payload.get("location", "")),
                body=_craft_body(payload),
                affected_channel=payload.get("channel_type", ""),
                affected_location=payload.get("location", ""),
                estimated_recipients=affected_count,
                created_at_iso=datetime.now(timezone.utc).isoformat(),
                consumed_payload_version=event.payload_version,
            )
            alerts.append(alert.to_dict())
            # v8.25: persist generated alert to history (idempotent on alert_id)
            record_alert_history(alert.to_dict())

        return {
            "status": "OK",
            "alerts": alerts,
            "new_max_event_id": max_id,
            "consumed_count": len(alerts),
            "pattern": "PUBLISHED_LANGUAGE",
            "payload_version": "1.0",
        }


# ════════════════════════════════════════════════════════════════════
# Self-test
# ════════════════════════════════════════════════════════════════════

def self_test() -> bool:
    """Round-trip test: producer → bus → consumer."""
    from utils.event_bus import clear_topic
    from utils.channels_reliability import (
        ChannelReliabilityProducer,
        CHANNEL_RELIABILITY_TOPIC,
        SEVERITY_OUTAGE, SEVERITY_DEGRADATION, SEVERITY_SLA_BREACH,
    )

    clear_topic(CHANNEL_RELIABILITY_TOPIC)

    # Produce 3 events of varying severity + affected count
    ChannelReliabilityProducer.report_event(
        channel_type="MOBILE_APP", severity=SEVERITY_OUTAGE,
        location="BANK_WIDE",
        description="Mobile banking app down",
        estimated_affected_customers=15000,  # → URGENT
    )
    ChannelReliabilityProducer.report_event(
        channel_type="ATM", severity=SEVERITY_OUTAGE,
        location="NRB001",
        description="ATM offline at Nairobi branch",
        estimated_affected_customers=300,  # → HIGH
    )
    ChannelReliabilityProducer.report_event(
        channel_type="AGENT_BANKING", severity=SEVERITY_SLA_BREACH,
        location="MSA002",
        description="Agent SLA breach",
        estimated_affected_customers=50,  # → INFO
    )

    # Consume from start
    result = SmartAlertsConsumer.consume(since_event_id=0)
    assert result["status"] == "OK"
    assert result["consumed_count"] == 3
    assert result["new_max_event_id"] == 3
    assert len(result["alerts"]) == 3

    # Tier classification
    tiers = [a["tier"] for a in result["alerts"]]
    assert tiers[0] == ALERT_TIER_URGENT, f"got {tiers[0]}"
    assert tiers[1] == ALERT_TIER_HIGH, f"got {tiers[1]}"
    assert tiers[2] == ALERT_TIER_INFO, f"got {tiers[2]}"

    # URGENT should have all 3 delivery channels
    assert ALERT_CHANNEL_PUSH in result["alerts"][0]["delivery_channels"]
    assert ALERT_CHANNEL_SMS in result["alerts"][0]["delivery_channels"]
    assert ALERT_CHANNEL_IN_APP_BANNER in result["alerts"][0]["delivery_channels"]
    # INFO should be banner-only
    assert result["alerts"][2]["delivery_channels"] == [ALERT_CHANNEL_IN_APP_BANNER]

    # Body should mention alternative channels
    assert "internet banking" in result["alerts"][0]["body"].lower() \
        or "USSD" in result["alerts"][0]["body"]

    # Incremental consumption — pass new_max_event_id back
    result2 = SmartAlertsConsumer.consume(
        since_event_id=result["new_max_event_id"])
    assert result2["consumed_count"] == 0  # nothing new

    # Add one more event, consume again
    ChannelReliabilityProducer.report_event(
        channel_type="USSD", severity=SEVERITY_DEGRADATION,
        location="BANK_WIDE",
        description="USSD slow response",
        estimated_affected_customers=8000,
    )
    result3 = SmartAlertsConsumer.consume(
        since_event_id=result2["new_max_event_id"])
    assert result3["consumed_count"] == 1
    assert result3["alerts"][0]["source_event_id"] == 4
    assert result3["alerts"][0]["tier"] == ALERT_TIER_HIGH  # 8000 > 100, DEGRADATION

    return True


if __name__ == "__main__":
    print("A2Z MIS 360 — utils.smart_alerts self-test")
    ok = self_test()
    print(f"Result: {'PASS' if ok else 'FAIL'}")
