"""
================================================================================
A2Z MIS 360 — Standard #337: Interaction Capture Framework
================================================================================

Risk classification: Cat C (event ingestion + structured event stream)

Capture every customer touch (branch, ATM, call center, app, web, email, SMS)
as a structured event stream with searchable history. This is the
foundational engine for the Customer Behavioral cluster — all downstream
profiling, journey mapping, anomaly detection, and ML hooks read from
this event store.

Public API:
    capture_event(customer_id, event_data, actor)
    list_events(customer_id, channel=None, event_type=None, ...)
    search_events(query, customer_id=None) -> filtered events
    interaction_summary(customer_id, period_start, period_end)
    channel_distribution(customer_id, period_start, period_end)

INTERACTION_CHANNELS byte-for-byte (Continuation.docx #337):
    BRANCH       -- in-person branch visit
    ATM          -- ATM transaction
    CALL_CENTER  -- inbound/outbound call
    MOBILE_APP   -- mobile app session/event
    WEB          -- web banking session/event
    EMAIL        -- email sent or received
    SMS          -- SMS sent or received
    USSD         -- USSD session
    CHATBOT      -- chatbot interaction
    SOCIAL_MEDIA -- social media touch (DM, mention)

EVENT_TYPES byte-for-byte:
    LOGIN              -- session start
    LOGOUT             -- session end
    TRANSACTION        -- payment / transfer / deposit / withdrawal
    INQUIRY            -- balance / statement / info request
    APPLICATION        -- product application started
    COMPLAINT          -- complaint logged
    INTERACTION        -- general touch (counted)
    ERROR              -- failed operation / error encountered
    NOTIFICATION       -- system-initiated notification
    SUPPORT_REQUEST    -- support ticket / chat with agent

EVENT_OUTCOMES byte-for-byte:
    SUCCESS            -- completed normally
    FAILURE            -- failed with error
    ABANDONED          -- user abandoned mid-flow
    PENDING            -- awaiting downstream action
    UNKNOWN            -- outcome not captured (fail-honest)

Honesty rules:
    Rule 1: list_events / search_events return [] for unknown customer
            (not None)
    Rule 6: invalid channel / event_type / outcome rejected
    Rule 4: actor required on capture (audit trail)

================================================================================
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, date
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


# ────────────────────────────────────────────────────────────────────
# Catalogs — byte-for-byte
# ────────────────────────────────────────────────────────────────────

INTERACTION_CHANNELS: Tuple[str, ...] = (
    "BRANCH", "ATM", "CALL_CENTER", "MOBILE_APP", "WEB",
    "EMAIL", "SMS", "USSD", "CHATBOT", "SOCIAL_MEDIA",
)

EVENT_TYPES: Tuple[str, ...] = (
    "LOGIN", "LOGOUT", "TRANSACTION", "INQUIRY", "APPLICATION",
    "COMPLAINT", "INTERACTION", "ERROR", "NOTIFICATION", "SUPPORT_REQUEST",
)

EVENT_OUTCOMES: Tuple[str, ...] = (
    "SUCCESS", "FAILURE", "ABANDONED", "PENDING", "UNKNOWN",
)


class InteractionCaptureEngine:
    """Foundational structured event capture for all customer touches."""

    def __init__(self, events_path: Optional[Path] = None):
        self.events_path = (
            events_path
            if events_path is not None
            else Path(__file__).parent.parent / "data" / "customer_interactions.json"
        )

    def _load(self) -> List[Dict[str, Any]]:
        try:
            from utils.db import db as _db
            data = _db.dual_load(
                self.events_path,
                table="customer_interactions",
                index_cols=("event_id",))
            return data if isinstance(data, list) else []
        except Exception:
            return []

    def _save(self, records: List[Dict[str, Any]]) -> bool:
        try:
            from utils.db import db as _db
            self.events_path.parent.mkdir(parents=True, exist_ok=True)
            _db.dual_save(
                self.events_path,
                data=records,
                table="customer_interactions",
                pk_col="event_id")
            return True
        except Exception:
            return False

    def capture_event(
        self,
        customer_id: str,
        event_data: Dict[str, Any],
        actor: str,
    ) -> Dict[str, Any]:
        """Capture a single interaction event."""
        if not actor:
            return {"captured": False, "error": "actor_required"}
        if not customer_id:
            return {"captured": False, "error": "customer_id_required"}

        # Required fields
        for f in ("event_id", "channel", "event_type", "occurred_at"):
            if f not in event_data or not event_data[f]:
                return {"captured": False, "error": f"missing_field:{f}"}

        # Validate enums
        if event_data["channel"] not in INTERACTION_CHANNELS:
            return {
                "captured": False,
                "error": f"invalid_channel:{event_data['channel']}",
                "valid_channels": list(INTERACTION_CHANNELS),
            }
        if event_data["event_type"] not in EVENT_TYPES:
            return {
                "captured": False,
                "error": f"invalid_event_type:{event_data['event_type']}",
                "valid_types": list(EVENT_TYPES),
            }
        outcome = event_data.get("outcome", "UNKNOWN")
        if outcome not in EVENT_OUTCOMES:
            return {
                "captured": False,
                "error": f"invalid_outcome:{outcome}",
                "valid_outcomes": list(EVENT_OUTCOMES),
            }

        # Validate timestamp
        try:
            datetime.fromisoformat(event_data["occurred_at"].replace("Z", ""))
        except (ValueError, TypeError, AttributeError):
            return {"captured": False, "error": "invalid_occurred_at_iso8601"}

        records = self._load()
        # Reject duplicates
        if any(r.get("event_id") == event_data["event_id"] for r in records):
            return {"captured": False, "error": "duplicate_event_id"}

        record = {
            "event_id": event_data["event_id"],
            "customer_id": customer_id,
            "channel": event_data["channel"],
            "event_type": event_data["event_type"],
            "outcome": outcome,
            "occurred_at": event_data["occurred_at"],
            "session_id": event_data.get("session_id"),
            "device_id": event_data.get("device_id"),
            "location": event_data.get("location"),
            "amount_kes": str(event_data["amount_kes"])
                            if event_data.get("amount_kes") is not None else None,
            "metadata": event_data.get("metadata", {}),
            "captured_by": actor,
            "captured_at": datetime.utcnow().isoformat(),
        }
        records.append(record)
        ok = self._save(records)
        return {"captured": ok, "event_id": event_data["event_id"]}

    def list_events(
        self,
        customer_id: str,
        channel: Optional[str] = None,
        event_type: Optional[str] = None,
        outcome: Optional[str] = None,
        period_start: Optional[str] = None,
        period_end: Optional[str] = None,
        limit: int = 1000,
    ) -> List[Dict[str, Any]]:
        """List events for a customer with optional filters."""
        if not customer_id:
            return []
        records = self._load()
        out = []
        for r in records:
            if r.get("customer_id") != customer_id:
                continue
            if channel and r.get("channel") != channel:
                continue
            if event_type and r.get("event_type") != event_type:
                continue
            if outcome and r.get("outcome") != outcome:
                continue
            if period_start and r.get("occurred_at", "") < period_start:
                continue
            if period_end and r.get("occurred_at", "") > period_end:
                continue
            out.append(r)
        # Sort by occurred_at desc
        out.sort(key=lambda x: x.get("occurred_at", ""), reverse=True)
        return out[:limit]

    def search_events(
        self,
        query: str,
        customer_id: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """Free-text search across event metadata + standard fields."""
        if not query:
            return []
        q = query.lower()
        records = self._load()
        out = []
        for r in records:
            if customer_id and r.get("customer_id") != customer_id:
                continue
            haystack_parts = [
                str(r.get("event_type", "")),
                str(r.get("channel", "")),
                str(r.get("outcome", "")),
                str(r.get("location", "")),
                str(r.get("metadata", "")),
            ]
            haystack = " ".join(haystack_parts).lower()
            if q in haystack:
                out.append(r)
        out.sort(key=lambda x: x.get("occurred_at", ""), reverse=True)
        return out[:limit]

    def interaction_summary(
        self,
        customer_id: str,
        period_start: Optional[str] = None,
        period_end: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Per-customer interaction summary."""
        events = self.list_events(
            customer_id, period_start=period_start, period_end=period_end,
            limit=10**9,
        )
        if not events:
            return {
                "customer_id": customer_id,
                "event_count": 0,
                "by_channel": {},
                "by_event_type": {},
                "by_outcome": {},
                "first_event_at": None,
                "last_event_at": None,
                "reason": "no_events",
            }

        by_channel = Counter(e.get("channel") for e in events)
        by_type = Counter(e.get("event_type") for e in events)
        by_outcome = Counter(e.get("outcome") for e in events)

        timestamps = sorted(e.get("occurred_at", "") for e in events
                              if e.get("occurred_at"))

        return {
            "customer_id": customer_id,
            "event_count": len(events),
            "by_channel": dict(by_channel),
            "by_event_type": dict(by_type),
            "by_outcome": dict(by_outcome),
            "first_event_at": timestamps[0] if timestamps else None,
            "last_event_at": timestamps[-1] if timestamps else None,
        }

    def channel_distribution(
        self,
        customer_id: str,
        period_start: Optional[str] = None,
        period_end: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Per-channel event share for a customer-period."""
        events = self.list_events(
            customer_id, period_start=period_start, period_end=period_end,
            limit=10**9,
        )
        if not events:
            return {
                "customer_id": customer_id,
                "period_start": period_start,
                "period_end": period_end,
                "channels": {},
                "primary_channel": None,
                "reason": "no_events",
            }

        by_channel = Counter(e.get("channel") for e in events)
        total = sum(by_channel.values())
        from decimal import Decimal as _D
        share_pct = {
            ch: str((_D(n) / _D(total) * _D("100")).quantize(_D("0.01")))
            for ch, n in by_channel.items()
        }
        primary = by_channel.most_common(1)[0][0] if by_channel else None

        return {
            "customer_id": customer_id,
            "period_start": period_start,
            "period_end": period_end,
            "total_events": total,
            "channels": dict(by_channel),
            "channel_share_pct": share_pct,
            "primary_channel": primary,
        }


def _self_test() -> None:
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        engine = InteractionCaptureEngine(
            events_path=Path(tmpdir) / "ev.json",
        )

        # Test 1: capture valid event
        r = engine.capture_event(
            "CUST-001",
            {"event_id": "EV-001",
             "channel": "MOBILE_APP",
             "event_type": "LOGIN",
             "outcome": "SUCCESS",
             "occurred_at": "2026-04-15T08:30:00",
             "device_id": "DEV-AND-123"},
            actor="event_pipeline",
        )
        assert r["captured"], r

        # Test 2: missing customer_id
        r = engine.capture_event(
            "",
            {"event_id": "EV-X", "channel": "BRANCH",
             "event_type": "INQUIRY",
             "occurred_at": "2026-04-15T09:00:00"},
            actor="x",
        )
        assert not r["captured"]

        # Test 3: invalid channel rejected
        r = engine.capture_event(
            "CUST-001",
            {"event_id": "EV-X2", "channel": "INVALID",
             "event_type": "LOGIN",
             "occurred_at": "2026-04-15T09:00:00"},
            actor="x",
        )
        assert not r["captured"]
        assert "invalid_channel" in r["error"]

        # Test 4: invalid event_type rejected
        r = engine.capture_event(
            "CUST-001",
            {"event_id": "EV-X3", "channel": "BRANCH",
             "event_type": "INVALID",
             "occurred_at": "2026-04-15T09:00:00"},
            actor="x",
        )
        assert not r["captured"]
        assert "invalid_event_type" in r["error"]

        # Test 5: invalid outcome rejected
        r = engine.capture_event(
            "CUST-001",
            {"event_id": "EV-X4", "channel": "BRANCH",
             "event_type": "INQUIRY",
             "outcome": "MAYBE",
             "occurred_at": "2026-04-15T09:00:00"},
            actor="x",
        )
        assert not r["captured"]
        assert "invalid_outcome" in r["error"]

        # Test 6: invalid timestamp rejected
        r = engine.capture_event(
            "CUST-001",
            {"event_id": "EV-X5", "channel": "BRANCH",
             "event_type": "INQUIRY",
             "occurred_at": "yesterday"},
            actor="x",
        )
        assert not r["captured"]

        # Test 7: duplicate event_id rejected
        r = engine.capture_event(
            "CUST-001",
            {"event_id": "EV-001", "channel": "WEB",
             "event_type": "LOGIN",
             "occurred_at": "2026-04-16T08:30:00"},
            actor="x",
        )
        assert not r["captured"]
        assert r["error"] == "duplicate_event_id"

        # Test 8: capture multiple events
        for i, (ch, t, ts) in enumerate([
            ("MOBILE_APP", "TRANSACTION", "2026-04-15T08:35:00"),
            ("MOBILE_APP", "LOGOUT", "2026-04-15T08:40:00"),
            ("BRANCH", "INQUIRY", "2026-04-16T10:00:00"),
            ("CALL_CENTER", "COMPLAINT", "2026-04-17T11:30:00"),
            ("ATM", "TRANSACTION", "2026-04-18T14:00:00"),
        ]):
            engine.capture_event(
                "CUST-001",
                {"event_id": f"EV-00{i+2}",
                 "channel": ch, "event_type": t,
                 "outcome": "SUCCESS",
                 "occurred_at": ts},
                actor="event_pipeline",
            )

        # Test 9: list_events filtered by channel
        mobile_events = engine.list_events("CUST-001", channel="MOBILE_APP")
        assert len(mobile_events) == 3  # LOGIN + TRANSACTION + LOGOUT

        # Test 10: list_events filtered by period
        mid_period = engine.list_events(
            "CUST-001",
            period_start="2026-04-16",
            period_end="2026-04-17T23:59:59",
        )
        assert len(mid_period) == 2

        # Test 11: list_events sorted desc
        all_events = engine.list_events("CUST-001")
        assert len(all_events) == 6
        # First event has latest timestamp
        assert all_events[0]["occurred_at"] >= all_events[-1]["occurred_at"]

        # Test 12: Rule 1 — unknown customer returns []
        empty = engine.list_events("UNKNOWN")
        assert empty == []

        # Test 13: search_events finds by metadata text
        # Channel + event_type are searchable
        complaints = engine.search_events("complaint", customer_id="CUST-001")
        assert len(complaints) == 1

        # Test 14: interaction_summary
        summary = engine.interaction_summary("CUST-001")
        assert summary["event_count"] == 6
        assert summary["by_channel"]["MOBILE_APP"] == 3
        assert summary["by_event_type"]["TRANSACTION"] == 2

        # Test 15: empty summary surfaces reason
        empty_summary = engine.interaction_summary("UNKNOWN")
        assert empty_summary["event_count"] == 0
        assert empty_summary["reason"] == "no_events"

        # Test 16: channel_distribution
        dist = engine.channel_distribution("CUST-001")
        assert dist["primary_channel"] == "MOBILE_APP"
        # 3 of 6 = 50.00
        assert dist["channel_share_pct"]["MOBILE_APP"] == "50.00"

        # Test 17: empty distribution surfaces reason
        empty_dist = engine.channel_distribution("UNKNOWN")
        assert empty_dist["primary_channel"] is None
        assert empty_dist["reason"] == "no_events"

    print("  ✅ interaction_capture self-test PASS")


if __name__ == "__main__":
    _self_test()
