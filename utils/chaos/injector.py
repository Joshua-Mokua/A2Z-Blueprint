"""utils/chaos/injector.py — chaos injector singleton.

The injector holds active chaos events and channel hooks query it
during ``submit()`` to decide whether to fail / slow / degrade the
request. Activation lives in a time window starting at ``event.when``
and lasting ``event.duration``.

Pattern:
    injector = get_chaos_injector()
    injector.activate(ChaosEvent(
        name="Safaricom outage", kind=ChaosKind.CHANNEL_OUTAGE,
        when=sim_now(), duration=timedelta(minutes=30),
        target="mpesa",
    ))
    # During the window, every mpesa submit() returns FAILED_HOST_UNAVAILABLE
"""

from __future__ import annotations

import threading
from datetime import datetime
from typing import Any, Dict, List, Optional

from utils.chaos.base import ChaosEvent, ChaosKind, ChaosSeverity


class ChaosInjector:
    """Singleton holding active chaos events. Thread-safe."""

    def __init__(self):
        self._active: List[ChaosEvent] = []
        self._history: List[ChaosEvent] = []
        self._lock = threading.RLock()

    # ── activation ────────────────────────────────────────────────

    def activate(self, event: ChaosEvent) -> None:
        """Activate a chaos event (called by scheduler at event.when)."""
        with self._lock:
            self._active.append(event)
            self._history.append(event)
        self._emit_activated(event)

    def deactivate(self, event_name: str) -> bool:
        """Manually deactivate by name. Returns True if removed."""
        with self._lock:
            for i, ev in enumerate(self._active):
                if ev.name == event_name:
                    self._active.pop(i)
                    self._emit_deactivated(ev)
                    return True
        return False

    def clear(self) -> int:
        """Clear all active chaos. Returns count removed."""
        with self._lock:
            n = len(self._active)
            self._active.clear()
            return n

    # ── queries used by channel hooks ─────────────────────────────

    def _prune_expired(self, now: datetime) -> None:
        """Remove events whose window has passed. Internal."""
        with self._lock:
            still_active = []
            for ev in self._active:
                if ev.ends_at() > now:
                    still_active.append(ev)
                else:
                    self._emit_deactivated(ev)
            self._active = still_active

    def active_for_channel(self, channel: str,
                             now: Optional[datetime] = None) -> List[ChaosEvent]:
        """Return chaos events active for ``channel`` at ``now``."""
        if now is None:
            from utils.simulation_clock import sim_now
            now = sim_now()
        self._prune_expired(now)
        with self._lock:
            return [
                ev for ev in self._active
                if (ev.target == "*" or ev.target == channel
                    or channel in ev.target.split(","))
                and ev.when <= now < ev.ends_at()
            ]

    def is_channel_outage(self, channel: str,
                            now: Optional[datetime] = None) -> bool:
        """True if any active CHANNEL_OUTAGE applies to ``channel``."""
        for ev in self.active_for_channel(channel, now):
            if ev.kind == ChaosKind.CHANNEL_OUTAGE:
                return True
        return False

    def elevated_failure_rate(self, channel: str,
                                now: Optional[datetime] = None) -> float:
        """Aggregate elevated failure rate from active events.

        Multiple events compound multiplicatively as independent
        failure mechanisms: combined_pass = (1-r1)*(1-r2)*...
        """
        combined_pass = 1.0
        for ev in self.active_for_channel(channel, now):
            if ev.kind == ChaosKind.ELEVATED_FAILURE:
                rate = float(ev.payload.get("failure_rate", 0.0))
                combined_pass *= max(0.0, 1.0 - rate)
        return 1.0 - combined_pass

    def latency_multiplier(self, channel: str,
                             now: Optional[datetime] = None) -> float:
        """Aggregate latency multiplier (product of active spikes)."""
        m = 1.0
        for ev in self.active_for_channel(channel, now):
            if ev.kind == ChaosKind.LATENCY_SPIKE:
                m *= float(ev.payload.get("multiplier", 1.0))
        return m

    def active_events(self) -> List[ChaosEvent]:
        """Snapshot of currently-active events (post-prune)."""
        from utils.simulation_clock import sim_now
        self._prune_expired(sim_now())
        with self._lock:
            return list(self._active)

    def history(self) -> List[ChaosEvent]:
        """All events ever activated through this injector."""
        with self._lock:
            return list(self._history)

    # ── telemetry ─────────────────────────────────────────────────

    def _emit_activated(self, ev: ChaosEvent) -> None:
        self._emit("chaos.activated", ev)

    def _emit_deactivated(self, ev: ChaosEvent) -> None:
        self._emit("chaos.deactivated", ev)

    def _emit(self, event_type: str, ev: ChaosEvent) -> None:
        try:
            from utils.event_bus import get_event_bus
            bus = get_event_bus()
            bus.emit(
                event_type=event_type,
                actor="chaos_injector",
                entity_id=ev.name,
                module="chaos",
                payload={
                    "name": ev.name,
                    "kind": ev.kind.value,
                    "severity": ev.severity.value,
                    "target": ev.target,
                    "duration_seconds": int(ev.duration.total_seconds()),
                    "tags": list(ev.tags),
                },
            )
        except Exception:
            pass  # telemetry never breaks chaos


# ── Module singleton ────────────────────────────────────────────────

_GLOBAL_INJECTOR: Optional[ChaosInjector] = None
_INJECTOR_LOCK = threading.Lock()


def get_chaos_injector() -> ChaosInjector:
    """Return the global chaos injector (lazy singleton)."""
    global _GLOBAL_INJECTOR
    with _INJECTOR_LOCK:
        if _GLOBAL_INJECTOR is None:
            _GLOBAL_INJECTOR = ChaosInjector()
        return _GLOBAL_INJECTOR


def reset_chaos_injector() -> None:
    """Reset the injector (for test isolation)."""
    global _GLOBAL_INJECTOR
    with _INJECTOR_LOCK:
        _GLOBAL_INJECTOR = None


__all__ = ["ChaosInjector", "get_chaos_injector", "reset_chaos_injector"]
