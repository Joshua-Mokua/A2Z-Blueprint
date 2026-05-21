"""utils/macro_calendar.py — Phase O4-B scheduled macro economic events.

Calendar of known/expected macro economic events that fire at specific
sim times. The CBK Monetary Policy Committee, Treasury budget reading,
month-end/quarter-end mark-to-market events, and Kenya Bureau of
Statistics releases.

Used together with MacroBridge to fire scheduled state changes when
the sim clock advances past their timestamp.
"""

from __future__ import annotations

import bisect
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional


# Nairobi timezone for event timestamps
_NAIROBI_TZ = timezone(timedelta(hours=3))


@dataclass(frozen=True)
class MacroEvent:
    """A scheduled macro economic event."""
    name: str
    when: datetime                          # UTC sim moment
    event_type: str                         # cbk_mpc / budget / eom / eoq / kebs / fx_intervention
    payload: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if self.when.tzinfo is None:
            raise ValueError(f"MacroEvent {self.name}: when must be tz-aware")


class MacroCalendar:
    """Sorted list of scheduled macro events."""

    def __init__(self):
        self._events: List[MacroEvent] = []

    def add_event(self, event: MacroEvent) -> None:
        """Insert event in sorted order."""
        # Normalise to UTC
        when_utc = event.when.astimezone(timezone.utc)
        if when_utc != event.when:
            event = MacroEvent(
                name=event.name, when=when_utc,
                event_type=event.event_type, payload=event.payload,
            )
        # Binary insert keyed by when
        keys = [e.when for e in self._events]
        idx = bisect.bisect_left(keys, event.when)
        self._events.insert(idx, event)

    def events_between(self, start: datetime,
                         end: datetime) -> List[MacroEvent]:
        """Events strictly after start, up to and including end."""
        if start.tzinfo is None or end.tzinfo is None:
            raise ValueError("events_between requires tz-aware datetimes")
        s = start.astimezone(timezone.utc)
        e = end.astimezone(timezone.utc)
        return [ev for ev in self._events if s < ev.when <= e]

    def events_after(self, when: datetime) -> List[MacroEvent]:
        """Events strictly after the given moment."""
        if when.tzinfo is None:
            raise ValueError("events_after requires tz-aware")
        w = when.astimezone(timezone.utc)
        return [ev for ev in self._events if ev.when > w]

    def next_event_after(self, when: datetime) -> Optional[MacroEvent]:
        events = self.events_after(when)
        return events[0] if events else None

    def __len__(self) -> int:
        return len(self._events)

    def all_events(self) -> List[MacroEvent]:
        """Return a copy of all events."""
        return list(self._events)

    # ── Pre-built calendars ───────────────────────────────────────

    @classmethod
    def kenya_2026_calendar(cls) -> "MacroCalendar":
        """Pre-populated calendar for Kenya 2026 macro events.

        - CBK MPC: schedule every ~60 days (CBK MPC meets bi-monthly)
        - Budget reading: 11 June 2026 (typical Kenya Budget Day)
        - End-of-quarter: 31 Mar, 30 Jun, 30 Sep, 31 Dec 2026
        - End-of-month: every month-end
        - KEBS/CPI release: ~15th of each month (illustrative)
        """
        cal = cls()
        # CBK MPC meetings — bi-monthly, second Wednesday of the meeting
        # month, 09:00 EAT typical. 2026 schedule based on CBK pattern.
        mpc_dates = [
            datetime(2026, 1, 28, 9, 0, tzinfo=_NAIROBI_TZ),
            datetime(2026, 3, 26, 9, 0, tzinfo=_NAIROBI_TZ),
            datetime(2026, 5, 28, 9, 0, tzinfo=_NAIROBI_TZ),
            datetime(2026, 7, 29, 9, 0, tzinfo=_NAIROBI_TZ),
            datetime(2026, 9, 30, 9, 0, tzinfo=_NAIROBI_TZ),
            datetime(2026, 11, 25, 9, 0, tzinfo=_NAIROBI_TZ),
        ]
        for d in mpc_dates:
            cal.add_event(MacroEvent(
                name=f"CBK MPC {d.strftime('%b %Y')}",
                when=d, event_type="cbk_mpc",
                payload={"venue": "CBK Haile Selassie Avenue"},
            ))
        # Budget reading (typically 2nd Thursday of June, after 2:30pm EAT)
        cal.add_event(MacroEvent(
            name="Kenya National Budget 2026/27",
            when=datetime(2026, 6, 11, 14, 30, tzinfo=_NAIROBI_TZ),
            event_type="budget",
            payload={"speaker": "Cabinet Secretary National Treasury"},
        ))
        # End-of-quarter
        for q_date in [(3, 31), (6, 30), (9, 30), (12, 31)]:
            cal.add_event(MacroEvent(
                name=f"End of Q{(q_date[0])//3} 2026",
                when=datetime(2026, q_date[0], q_date[1], 23, 59,
                                tzinfo=_NAIROBI_TZ),
                event_type="eoq",
            ))
        # End-of-month (each month-end at 23:59 EAT)
        for month in range(1, 13):
            # Get last day of month
            if month == 12:
                last_day = datetime(2026, 12, 31)
            else:
                last_day = (datetime(2026, month + 1, 1)
                            - timedelta(days=1))
            cal.add_event(MacroEvent(
                name=f"End of {last_day.strftime('%B 2026')}",
                when=datetime(2026, last_day.month, last_day.day,
                                23, 59, tzinfo=_NAIROBI_TZ),
                event_type="eom",
            ))
        # KNBS CPI/inflation releases (~15th of each month)
        for month in range(1, 13):
            cal.add_event(MacroEvent(
                name=f"KNBS CPI Release {month:02d}/2026",
                when=datetime(2026, month, 15, 11, 0, tzinfo=_NAIROBI_TZ),
                event_type="cpi_release",
                payload={"source": "Kenya National Bureau of Statistics"},
            ))
        return cal


__all__ = ["MacroEvent", "MacroCalendar"]
