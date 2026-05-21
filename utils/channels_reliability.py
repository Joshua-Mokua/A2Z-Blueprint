"""utils/channels_reliability.py — Channel reliability events PRODUCER (v8.4).

Produces channel outage / degradation events for L14 feedback loop
(Channel reliability → Customer experience alerts).

Per Charter §6/§7: this module is the PRODUCER of L14. It emits
events to the `channel_reliability` topic on the event_bus, where
`utils.smart_alerts` (CONSUMER) picks them up and creates customer-
facing alerts.

Three event severities:
    - OUTAGE: full unavailability (ATM offline, mobile app crash)
    - DEGRADATION: partial functionality (slow response, intermittent)
    - SLA_BREACH: below contractual threshold

Five channel types tracked:
    - ATM
    - MOBILE_APP
    - INTERNET_BANKING
    - AGENT_BANKING
    - USSD

The PRODUCER side is intentionally lightweight — it just emits events.
The CONSUMER side (smart_alerts) does the heavy lifting (deciding which
customers to notify, generating the alert text, prioritising by impact).
"""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


# ════════════════════════════════════════════════════════════════════
# Constants
# ════════════════════════════════════════════════════════════════════

CHANNEL_RELIABILITY_TOPIC = "channel_reliability"
PAYLOAD_VERSION = "1.0"

CHANNEL_TYPES = ("ATM", "MOBILE_APP", "INTERNET_BANKING",
                  "AGENT_BANKING", "USSD")

SEVERITY_OUTAGE = "OUTAGE"
SEVERITY_DEGRADATION = "DEGRADATION"
SEVERITY_SLA_BREACH = "SLA_BREACH"

VALID_SEVERITIES = (SEVERITY_OUTAGE, SEVERITY_DEGRADATION, SEVERITY_SLA_BREACH)


# ════════════════════════════════════════════════════════════════════
# Event payload helpers
# ════════════════════════════════════════════════════════════════════

@dataclass
class ChannelReliabilityEvent:
    """A single channel reliability event. Producer-side dataclass."""
    channel_type: str
    severity: str
    location: str  # branch_code or "BANK_WIDE"
    description: str
    detected_at_iso: str
    estimated_affected_customers: int = 0
    expected_resolution_iso: Optional[str] = None

    def to_payload(self) -> Dict[str, Any]:
        """Convert to event payload dict per PUBLISHED_LANGUAGE contract."""
        return {
            "channel_type": self.channel_type,
            "severity": self.severity,
            "location": self.location,
            "description": self.description,
            "detected_at_iso": self.detected_at_iso,
            "estimated_affected_customers": self.estimated_affected_customers,
            "expected_resolution_iso": self.expected_resolution_iso,
            "pattern": "PUBLISHED_LANGUAGE",
            "payload_version": PAYLOAD_VERSION,
        }


# ════════════════════════════════════════════════════════════════════
# Producer API
# ════════════════════════════════════════════════════════════════════

class ChannelReliabilityProducer:
    """L14 producer — emits channel reliability events to the bus."""

    @staticmethod
    def report_event(
        channel_type: str,
        severity: str,
        location: str,
        description: str,
        estimated_affected_customers: int = 0,
        expected_resolution_iso: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Emit a channel reliability event to the bus.

        Returns the published event metadata (event_id, topic, timestamp)
        so callers can correlate later.
        """
        if channel_type not in CHANNEL_TYPES:
            return {
                "status": "REJECTED",
                "reason": f"channel_type must be one of {CHANNEL_TYPES}",
            }
        if severity not in VALID_SEVERITIES:
            return {
                "status": "REJECTED",
                "reason": f"severity must be one of {VALID_SEVERITIES}",
            }

        event = ChannelReliabilityEvent(
            channel_type=channel_type,
            severity=severity,
            location=location,
            description=description,
            detected_at_iso=datetime.now(timezone.utc).isoformat(),
            estimated_affected_customers=estimated_affected_customers,
            expected_resolution_iso=expected_resolution_iso,
        )

        try:
            from utils.event_bus import publish
            published = publish(
                CHANNEL_RELIABILITY_TOPIC,
                event.to_payload(),
                payload_version=PAYLOAD_VERSION)
        except Exception as e:
            return {
                "status": "FAILED",
                "reason": f"event_bus publish failed: {type(e).__name__}: {e}",
            }

        return {
            "status": "PUBLISHED",
            "event_id": published.event_id,
            "topic": published.topic,
            "timestamp_iso": published.timestamp_iso,
            "payload_version": PAYLOAD_VERSION,
        }

    @staticmethod
    def get_recent_events(n: int = 20) -> List[Dict[str, Any]]:
        """Read recent events from the bus (for UI display + monitoring)."""
        try:
            from utils.event_bus import get_latest
            events = get_latest(CHANNEL_RELIABILITY_TOPIC, n=n)
            return [
                {"event_id": e.event_id,
                 "timestamp_iso": e.timestamp_iso,
                 **e.payload}
                for e in events
            ]
        except Exception:
            return []

    @staticmethod
    def get_topic_stats() -> Dict[str, Any]:
        """Return summary stats for the channel_reliability topic."""
        try:
            from utils.event_bus import get_topic_stats
            return get_topic_stats(CHANNEL_RELIABILITY_TOPIC)
        except Exception:
            return {"topic": CHANNEL_RELIABILITY_TOPIC, "count": 0}


# ════════════════════════════════════════════════════════════════════
# Self-test
# ════════════════════════════════════════════════════════════════════

def self_test() -> bool:
    """Smoke-test the producer."""
    from utils.event_bus import clear_topic
    clear_topic(CHANNEL_RELIABILITY_TOPIC)

    # Emit one event of each severity
    r1 = ChannelReliabilityProducer.report_event(
        channel_type="ATM", severity=SEVERITY_OUTAGE,
        location="NRB001", description="ATM card reader malfunction",
        estimated_affected_customers=120,
    )
    assert r1["status"] == "PUBLISHED", f"got {r1}"
    assert r1["event_id"] == 1

    r2 = ChannelReliabilityProducer.report_event(
        channel_type="MOBILE_APP", severity=SEVERITY_DEGRADATION,
        location="BANK_WIDE",
        description="Login slow due to backend timeout",
        estimated_affected_customers=15000,
    )
    assert r2["status"] == "PUBLISHED" and r2["event_id"] == 2

    # Reject invalid inputs
    bad = ChannelReliabilityProducer.report_event(
        channel_type="WRONG", severity=SEVERITY_OUTAGE,
        location="X", description="x")
    assert bad["status"] == "REJECTED"

    # Read back
    recent = ChannelReliabilityProducer.get_recent_events(n=5)
    assert len(recent) == 2

    return True


if __name__ == "__main__":
    print("A2Z MIS 360 — utils.channels_reliability self-test")
    ok = self_test()
    print(f"Result: {'PASS' if ok else 'FAIL'}")
