"""utils/tick_scheduler.py — Phase O4-A tick-based event scheduling.

A deterministic scheduler that fires callbacks at specific simulation
times. Built on top of SimulationClock — when you call ``tick(advance_by)``
the scheduler advances the clock and fires any callbacks whose ``when``
is now in the past.

Used to:
    - Schedule batch cutoffs (KIC morning batch closes at sim 11:30am)
    - Schedule periodic events (event bus heartbeat every 60 sim seconds)
    - Trigger time-of-day behaviour in scenarios

Deterministic ordering: callbacks scheduled at the same sim moment fire
in insertion order, modified by priority (higher priority = earlier).

Thread-safe via internal RLock.
"""

from __future__ import annotations

import heapq
import itertools
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, List, Optional

from utils.simulation_clock import (
    SimulationClock, get_simulation_clock,
)


# Insertion counter for deterministic tie-breaking
_INSERTION_SEQ = itertools.count()
_SEQ_LOCK = threading.Lock()


def _next_seq() -> int:
    with _SEQ_LOCK:
        return next(_INSERTION_SEQ)


@dataclass(order=False)
class ScheduledCallback:
    """A callback scheduled to fire at a specific sim time."""
    when: datetime
    callback: Callable[[], Any]
    priority: int = 0          # higher fires earlier when ties
    interval: Optional[timedelta] = None    # if set, re-schedule
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    seq: int = field(default_factory=_next_seq)
    label: str = ""

    def _heap_key(self):
        # Lower key fires first
        # (when, -priority, seq) — earlier when, then higher priority,
        # then earlier insertion
        return (self.when, -self.priority, self.seq)


class TickScheduler:
    """A deterministic tick-based scheduler.

    Usage:
        clock = get_simulation_clock()
        clock.set(datetime(2026, 5, 15, 11, 0, tzinfo=NAIROBI_TZ))
        sched = TickScheduler(clock)
        sched.schedule_at(
            datetime(2026, 5, 15, 11, 30, tzinfo=NAIROBI_TZ),
            lambda: print("KIC morning cutoff hit"),
            label="kic_morning_cutoff",
        )
        sched.tick(advance_by=timedelta(minutes=45))  # advance 45 min
        # → fires the callback at 11:30 and clock now at 11:45
    """

    def __init__(self, clock: Optional[SimulationClock] = None):
        self.clock = clock or get_simulation_clock()
        self._heap: List[tuple] = []   # (heap_key, ScheduledCallback)
        self._lock = threading.RLock()
        self._fired_count = 0

    # ── scheduling ───────────────────────────────────────────────

    def schedule_at(self, when: datetime, callback: Callable[[], Any],
                     *, priority: int = 0, label: str = "") -> str:
        """Schedule a one-shot callback at sim time ``when``."""
        if when.tzinfo is None:
            raise ValueError("schedule_at requires tz-aware datetime")
        cb = ScheduledCallback(
            when=when.astimezone(timezone.utc),
            callback=callback,
            priority=priority,
            label=label or callback.__name__ or "anon",
        )
        with self._lock:
            heapq.heappush(self._heap, (cb._heap_key(), cb))
        return cb.id

    def schedule_recurring(self, *, start_at: datetime,
                            interval: timedelta,
                            callback: Callable[[], Any],
                            priority: int = 0, label: str = "") -> str:
        """Schedule a callback that fires every ``interval`` starting
        at ``start_at``. Re-schedules itself after each fire.
        """
        if interval.total_seconds() <= 0:
            raise ValueError("recurring interval must be positive")
        cb = ScheduledCallback(
            when=start_at.astimezone(timezone.utc),
            callback=callback,
            priority=priority,
            interval=interval,
            label=label or callback.__name__ or "anon_recurring",
        )
        with self._lock:
            heapq.heappush(self._heap, (cb._heap_key(), cb))
        return cb.id

    def cancel(self, callback_id: str) -> bool:
        """Cancel a scheduled callback by id. Returns True if removed."""
        with self._lock:
            for i, (_, cb) in enumerate(self._heap):
                if cb.id == callback_id:
                    self._heap.pop(i)
                    heapq.heapify(self._heap)
                    return True
            return False

    # ── execution ────────────────────────────────────────────────

    def tick(self, advance_by: Optional[timedelta] = None,
              max_fires: int = 10_000) -> List[Any]:
        """Advance the clock (if requested) and fire all due callbacks.

        Returns the list of return values from fired callbacks (in
        firing order). Recurring callbacks re-add themselves to the
        heap after firing.
        """
        if advance_by is not None:
            self.clock.advance(advance_by)
        now = self.clock.now()
        results: List[Any] = []
        with self._lock:
            fired_this_tick = 0
            while self._heap and fired_this_tick < max_fires:
                key, cb = self._heap[0]
                if cb.when > now:
                    break
                heapq.heappop(self._heap)
                try:
                    result = cb.callback()
                    results.append(result)
                except Exception as exc:
                    results.append({"error": str(exc),
                                      "callback_label": cb.label})
                self._fired_count += 1
                fired_this_tick += 1
                # Re-schedule if recurring
                if cb.interval:
                    next_when = cb.when + cb.interval
                    new_cb = ScheduledCallback(
                        when=next_when, callback=cb.callback,
                        priority=cb.priority, interval=cb.interval,
                        label=cb.label,
                    )
                    heapq.heappush(self._heap,
                                     (new_cb._heap_key(), new_cb))
        return results

    # ── introspection ────────────────────────────────────────────

    def pending(self) -> int:
        """Number of callbacks currently scheduled."""
        with self._lock:
            return len(self._heap)

    def fired_count(self) -> int:
        """Total callbacks fired by this scheduler."""
        with self._lock:
            return self._fired_count

    def peek_next(self) -> Optional[ScheduledCallback]:
        """Return the next callback to fire (without removing it)."""
        with self._lock:
            return self._heap[0][1] if self._heap else None

    def clear(self) -> int:
        """Cancel all pending callbacks. Returns count removed."""
        with self._lock:
            n = len(self._heap)
            self._heap.clear()
            return n


__all__ = ["TickScheduler", "ScheduledCallback"]
