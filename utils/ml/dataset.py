"""utils/ml/dataset.py — extract ML datasets from the event bus stream.

DatasetBuilder reads from the event_bus, joins channel calls with their
success/failure outcomes, attaches macro state at the moment of the call,
and produces rows suitable for ML training/evaluation.

Each row is a (correlation_id, channel, latency_ms, success_label,
feature_dict, label_dict) tuple. Labels include:
  - success            (bool): did the channel call succeed
  - chaos_at_call      (bool): was a chaos event active for this channel
  - latency_class      (str): fast / normal / slow / very_slow

Features extracted per call:
  - channel name (one-hot via FeatureEngine)
  - hour-of-day, day-of-week (cyclical)
  - amount (log-transformed)
  - macro snapshot at call: CBR, USD/KES, NPL ratio
  - chaos features: outage_active, elevated_failure_rate,
    latency_multiplier (queried by injector at call time)

The builder is deterministic given the same event-bus contents.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


@dataclass
class DatasetSpec:
    """Specification for what dataset to build."""
    # Which channels to include (None = all)
    channels: Optional[List[str]] = None
    # Time window (inclusive of both)
    since: Optional[datetime] = None
    until: Optional[datetime] = None
    # Maximum rows to emit
    max_rows: int = 100_000
    # Include rows even if outcome event not found
    require_outcome: bool = True


@dataclass
class DatasetRow:
    """A single ML training example."""
    correlation_id: str
    channel: str
    timestamp: str
    features: Dict[str, float] = field(default_factory=dict)
    labels: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "correlation_id": self.correlation_id,
            "channel": self.channel,
            "timestamp": self.timestamp,
            "features": dict(self.features),
            "labels": dict(self.labels),
        }


class DatasetBuilder:
    """Build a dataset by replaying the event bus."""

    def __init__(self, *, bus=None):
        if bus is None:
            from utils.event_bus import get_event_bus
            bus = get_event_bus()
        self.bus = bus

    def build(self, spec: DatasetSpec) -> List[DatasetRow]:
        """Walk the event bus and produce dataset rows."""
        # Pull all integration call events in the window
        kwargs: Dict[str, Any] = {"limit": 1_000_000}
        if spec.since:
            kwargs["since"] = spec.since.isoformat()
        if spec.until:
            kwargs["until"] = spec.until.isoformat()

        all_events = self.bus.query(**kwargs)

        # Group by correlation_id so we can join call → outcome
        by_corr: Dict[str, List[Any]] = {}
        for ev in all_events:
            cid = getattr(ev, "correlation_id", "") or ""
            if not cid:
                continue
            by_corr.setdefault(cid, []).append(ev)

        rows: List[DatasetRow] = []
        for corr_id, events in by_corr.items():
            # Sort by timestamp for stable joining
            events.sort(key=lambda e: e.timestamp)

            # Find the .call event (start of the channel interaction)
            call_event = None
            outcome_event = None
            for ev in events:
                et = ev.event_type
                if et.startswith("integration.") and et.endswith(".call"):
                    call_event = ev
                elif (et.startswith("integration.")
                      and (et.endswith(".success")
                           or et.endswith(".failure"))):
                    outcome_event = ev

            if call_event is None:
                continue
            if spec.require_outcome and outcome_event is None:
                continue

            # Identify channel from event_type "integration.<chan>.<phase>"
            parts = call_event.event_type.split(".")
            if len(parts) < 3:
                continue
            channel = parts[1]
            if spec.channels and channel not in spec.channels:
                continue

            row = self._build_row(corr_id, channel, call_event,
                                    outcome_event)
            if row is not None:
                rows.append(row)
                if len(rows) >= spec.max_rows:
                    break

        return rows

    def _build_row(self, corr_id: str, channel: str, call_event,
                    outcome_event) -> Optional[DatasetRow]:
        """Build a single row from a call + outcome pair."""
        payload = getattr(call_event, "payload", {}) or {}

        # Parse call timestamp
        try:
            ts = call_event.timestamp
            when = datetime.fromisoformat(
                ts.replace("Z", "+00:00") if ts.endswith("Z") else ts
            )
        except Exception:
            return None

        # ── Features ─────────────────────────────────────────────
        amount = float(payload.get("amount") or 0.0)
        amount_log = math.log1p(max(0.0, amount))
        hour = when.hour
        # Cyclical encoding of hour-of-day
        hour_sin = math.sin(2 * math.pi * hour / 24.0)
        hour_cos = math.cos(2 * math.pi * hour / 24.0)
        # Cyclical encoding of day-of-week
        dow = when.weekday()
        dow_sin = math.sin(2 * math.pi * dow / 7.0)
        dow_cos = math.cos(2 * math.pi * dow / 7.0)

        features: Dict[str, float] = {
            f"channel_{channel}": 1.0,
            "amount_log": amount_log,
            "hour_sin": hour_sin,
            "hour_cos": hour_cos,
            "dow_sin": dow_sin,
            "dow_cos": dow_cos,
        }

        # Macro features at call time
        try:
            from utils.macro_state import get_macro_state
            ms = get_macro_state()
            features["cbr"] = ms.cbk_central_bank_rate
            features["usd_kes"] = ms.usd_kes
            features["npl_ratio"] = ms.npl_ratio
            features["inflation_yoy"] = ms.inflation_yoy
        except Exception:
            pass

        # Chaos features at call time
        chaos_outage_active = 0.0
        chaos_elevated_rate = 0.0
        chaos_latency_mult = 1.0
        try:
            from utils.chaos.injector import get_chaos_injector
            injector = get_chaos_injector()
            if injector.is_channel_outage(channel, now=when):
                chaos_outage_active = 1.0
            chaos_elevated_rate = injector.elevated_failure_rate(
                channel, now=when)
            chaos_latency_mult = injector.latency_multiplier(
                channel, now=when)
        except Exception:
            pass
        features["chaos_outage_active"] = chaos_outage_active
        features["chaos_elevated_rate"] = chaos_elevated_rate
        features["chaos_latency_mult"] = chaos_latency_mult

        # ── Labels ───────────────────────────────────────────────
        labels: Dict[str, Any] = {}
        if outcome_event is not None:
            success = outcome_event.event_type.endswith(".success")
            labels["success"] = bool(success)
            op = getattr(outcome_event, "payload", {}) or {}
            latency_ms = float(op.get("latency_ms", 0.0) or 0.0)
            labels["latency_ms"] = latency_ms
            # Latency class buckets (channel-agnostic coarse bands)
            if latency_ms < 1000:
                labels["latency_class"] = "fast"
            elif latency_ms < 10_000:
                labels["latency_class"] = "normal"
            elif latency_ms < 60_000:
                labels["latency_class"] = "slow"
            else:
                labels["latency_class"] = "very_slow"
            labels["error_code"] = op.get("error_code")
        labels["chaos_at_call"] = bool(chaos_outage_active or
                                          chaos_elevated_rate > 0)

        return DatasetRow(
            correlation_id=corr_id,
            channel=channel,
            timestamp=call_event.timestamp,
            features=features,
            labels=labels,
        )

    def fingerprint(self, rows: List[DatasetRow]) -> str:
        """Stable hash of the row contents for provenance tracking."""
        h = hashlib.sha256()
        for r in sorted(rows, key=lambda x: x.correlation_id):
            h.update(r.correlation_id.encode("utf-8"))
            h.update(json.dumps(r.features, sort_keys=True).encode("utf-8"))
            h.update(json.dumps(r.labels, sort_keys=True,
                                  default=str).encode("utf-8"))
        return h.hexdigest()[:16]


__all__ = ["DatasetSpec", "DatasetRow", "DatasetBuilder"]
