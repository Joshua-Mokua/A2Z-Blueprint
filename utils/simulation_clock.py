"""utils/simulation_clock.py — Phase O4-A simulation clock.

A controllable virtual clock that can be set, advanced, and frozen
independently of the wall clock. When inactive, sim_now() returns
wall-clock UTC — meaning every caller that uses sim_now() instead of
datetime.now() gets backward-compatible behaviour by default.

Patterns:
    clock = get_simulation_clock()
    clock.set(datetime(2026, 5, 15, 16, 25, tzinfo=NAIROBI))  # 4:25pm
    submit_channel("rtgs", ...)   # within cutoff, passes
    clock.advance(timedelta(minutes=10))                       # → 4:35pm
    submit_channel("rtgs", ...)   # past cutoff, fails

Why this exists (per Phase O4):
    - Channels have time-dependent behaviour (KIC batch windows, RTGS
      4:30pm cutoff). Without a controllable clock, testing these
      requires waiting wall-clock time or monkey-patching datetime.
    - Time-evolution scenarios (interest accrual, position aging,
      multi-day customer journeys) need a clock they can fast-forward.
    - Reproducibility: any sim state can be replayed by replaying both
      the random seed AND the clock trajectory.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional

# Nairobi timezone (UTC+3, no DST in Kenya)
NAIROBI_TZ = timezone(timedelta(hours=3))


@dataclass
class _ClockState:
    active: bool = False
    frozen_at: Optional[datetime] = None
    offset: timedelta = field(default_factory=lambda: timedelta(0))


class SimulationClock:
    """A controllable virtual clock for the digital twin.

    Thread-safe (uses an internal RLock around state mutations). When
    inactive, ``now()`` falls back to ``datetime.now(timezone.utc)`` so
    callers can use it as a drop-in for the wall clock.
    """

    def __init__(self):
        self._lock = threading.RLock()
        self._state = _ClockState()

    # ── state queries ────────────────────────────────────────────

    def is_active(self) -> bool:
        with self._lock:
            return self._state.active

    def is_frozen(self) -> bool:
        """True when the clock is set but not advancing on its own."""
        return self.is_active()

    # ── state changes ────────────────────────────────────────────

    def activate(self) -> None:
        """Turn on sim time. now() returns sim time after this."""
        with self._lock:
            self._state.active = True
            if self._state.frozen_at is None:
                # Default to current wall time if nothing was set yet
                self._state.frozen_at = datetime.now(timezone.utc)

    def deactivate(self) -> None:
        """Turn off sim time. now() returns wall UTC after this."""
        with self._lock:
            self._state.active = False

    def set(self, when: datetime) -> None:
        """Set the clock to a specific moment.

        Implicitly activates the clock. The clock will stay at this
        moment until ``advance()`` or another ``set()`` is called.
        """
        if when.tzinfo is None:
            raise ValueError("set() requires timezone-aware datetime")
        # Normalise to UTC internally
        when_utc = when.astimezone(timezone.utc)
        with self._lock:
            self._state.active = True
            self._state.frozen_at = when_utc
            self._state.offset = timedelta(0)

    def advance(self, delta: timedelta) -> datetime:
        """Move the clock forward by ``delta``. Returns new now().

        Raises if the clock isn't set yet.
        """
        with self._lock:
            if self._state.frozen_at is None:
                raise RuntimeError(
                    "advance() called before set() — clock has no anchor"
                )
            self._state.active = True
            self._state.offset += delta
            return self._state.frozen_at + self._state.offset

    def reset(self) -> None:
        """Clear all state. now() returns wall UTC after this."""
        with self._lock:
            self._state = _ClockState()

    # ── time access ──────────────────────────────────────────────

    def now(self) -> datetime:
        """Return current sim time if active, else wall-clock UTC."""
        with self._lock:
            if not self._state.active or self._state.frozen_at is None:
                return datetime.now(timezone.utc)
            return self._state.frozen_at + self._state.offset

    def now_nairobi(self) -> datetime:
        """Convenience: now() converted to Nairobi local time."""
        return self.now().astimezone(NAIROBI_TZ)


# Module-level singleton accessor
_GLOBAL_CLOCK: Optional[SimulationClock] = None
_CLOCK_LOCK = threading.Lock()


def get_simulation_clock() -> SimulationClock:
    """Return the global simulation clock (created lazily)."""
    global _GLOBAL_CLOCK
    with _CLOCK_LOCK:
        if _GLOBAL_CLOCK is None:
            _GLOBAL_CLOCK = SimulationClock()
        return _GLOBAL_CLOCK


def sim_now() -> datetime:
    """Drop-in replacement for ``datetime.now(timezone.utc)``.

    If the sim clock is active, returns sim time. Otherwise returns
    wall-clock UTC. Use this anywhere in the codebase that needs to
    respect the sim clock when one is active.
    """
    return get_simulation_clock().now()


def sim_now_nairobi() -> datetime:
    """Sim time converted to Nairobi local timezone."""
    return get_simulation_clock().now_nairobi()


def reset_simulation_clock() -> None:
    """Reset the global clock to fresh state. Use for test isolation."""
    get_simulation_clock().reset()


__all__ = [
    "SimulationClock", "get_simulation_clock", "sim_now",
    "sim_now_nairobi", "reset_simulation_clock", "NAIROBI_TZ",
]
