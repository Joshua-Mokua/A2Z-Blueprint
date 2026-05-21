"""
================================================================================
A2Z MIS 360 — Standard #387: SLA Calendar Management
================================================================================

Risk classification: Cat B (deterministic working-hours calendar)

Working-hours / public-holiday-aware SLA calculation. Multi-region
calendar support. Custom weekend/holiday rules.

Public API:
    add_holiday(date, region, name)             -- register holiday
    is_business_day(date, region)               -- bool
    business_hours_between(start, end, region)  -- elapsed business hours
    business_days_between(start, end, region)   -- elapsed business days
    sla_deadline(start, target_days, region)    -- working-day deadline

Default Kenya business calendar byte-for-byte:
    KE_WORKING_DAYS         = (Mon, Tue, Wed, Thu, Fri)  -- ISO 1-5
    KE_BUSINESS_HOURS_START = 08:00
    KE_BUSINESS_HOURS_END   = 17:00
    KE_PUBLIC_HOLIDAYS_2026 = New Year, Labour Day, Madaraka Day,
                              Mashujaa Day, Jamhuri Day, Christmas

Regions supported byte-for-byte:
    KE -- Kenya (default)
    UG -- Uganda
    TZ -- Tanzania
    RW -- Rwanda
    GLOBAL -- 5-day week, no holidays

Honesty rules:
    Rule 1: business_hours_between = None when end < start
    Rule 6: unknown region surfaced (NEVER silently treated as KE)

================================================================================
"""

from __future__ import annotations

import json
from datetime import datetime, date, time, timedelta
from decimal import Decimal, getcontext
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

getcontext().prec = 28

# ────────────────────────────────────────────────────────────────────
# Default calendars — byte-for-byte
# ────────────────────────────────────────────────────────────────────

WORKING_DAYS_BY_REGION: Dict[str, Tuple[int, ...]] = {
    "KE": (1, 2, 3, 4, 5),  # Mon-Fri
    "UG": (1, 2, 3, 4, 5),
    "TZ": (1, 2, 3, 4, 5),
    "RW": (1, 2, 3, 4, 5),
    "GLOBAL": (1, 2, 3, 4, 5),
}

BUSINESS_HOURS_BY_REGION: Dict[str, Tuple[time, time]] = {
    "KE": (time(8, 0), time(17, 0)),
    "UG": (time(8, 0), time(17, 0)),
    "TZ": (time(8, 0), time(16, 30)),
    "RW": (time(8, 0), time(17, 0)),
    "GLOBAL": (time(9, 0), time(17, 0)),
}

# 2026 public holidays — Kenya (CBK + national)
KE_PUBLIC_HOLIDAYS_2026: Set[str] = {
    "2026-01-01",  # New Year
    "2026-04-03",  # Good Friday
    "2026-04-06",  # Easter Monday
    "2026-05-01",  # Labour Day
    "2026-06-01",  # Madaraka Day
    "2026-10-20",  # Mashujaa Day
    "2026-12-12",  # Jamhuri Day
    "2026-12-25",  # Christmas
    "2026-12-26",  # Boxing Day
}

DEFAULT_HOLIDAYS_BY_REGION: Dict[str, Set[str]] = {
    "KE": KE_PUBLIC_HOLIDAYS_2026,
    "UG": set(),
    "TZ": set(),
    "RW": set(),
    "GLOBAL": set(),
}

SUPPORTED_REGIONS: Tuple[str, ...] = tuple(WORKING_DAYS_BY_REGION.keys())


class SlaCalendarEngine:
    """Working-hours-aware SLA deadline calculation."""

    def __init__(self, calendar_path: Optional[Path] = None):
        self.calendar_path = (
            calendar_path
            if calendar_path is not None
            else Path(__file__).parent.parent / "data" / "sla_calendar.json"
        )
        self.custom_holidays: Dict[str, Set[str]] = {}
        self._load_custom_holidays()

    def _load_custom_holidays(self) -> None:
        try:
            from utils.db import db as _db   # singleton Database instance
            records = _db.dual_load(
                self.calendar_path,
                table="sla_custom_holidays",
                index_cols=("region", "holiday_date"))
            if isinstance(records, list):
                for rec in records:
                    if not isinstance(rec, dict):
                        continue
                    region = rec.get("region")
                    holiday_date = rec.get("holiday_date") or rec.get("date")
                    if region and holiday_date:
                        self.custom_holidays.setdefault(region, set()).add(holiday_date)
        except Exception:
            pass

    def _save_custom_holidays(self) -> bool:
        try:
            from utils.db import db as _db   # singleton Database instance
            self.calendar_path.parent.mkdir(parents=True, exist_ok=True)
            records = []
            for region, dates in self.custom_holidays.items():
                for d in sorted(dates):
                    records.append({"region": region, "holiday_date": d})
            _db.dual_save(
                self.calendar_path,
                data=records,
                table="sla_custom_holidays",
                pk_col=None)
            return True
        except Exception:
            return False

    def _holidays_for_region(self, region: str) -> Set[str]:
        defaults = DEFAULT_HOLIDAYS_BY_REGION.get(region, set())
        custom = self.custom_holidays.get(region, set())
        return defaults | custom

    def add_holiday(
        self, holiday_date: str, region: str = "KE", name: str = ""
    ) -> Dict[str, Any]:
        """Register custom holiday. Rule 6: unknown region rejected."""
        if region not in SUPPORTED_REGIONS:
            return {
                "added": False,
                "error": f"unknown_region:{region}",
                "supported": list(SUPPORTED_REGIONS),
            }

        # Validate date format
        try:
            datetime.strptime(holiday_date, "%Y-%m-%d")
        except ValueError:
            return {"added": False, "error": "invalid_date_format"}

        self.custom_holidays.setdefault(region, set()).add(holiday_date)
        ok = self._save_custom_holidays()
        return {"added": ok, "date": holiday_date, "region": region, "name": name}

    def is_business_day(
        self, check_date: date, region: str = "KE"
    ) -> Optional[bool]:
        """
        Is this a business day for the region?

        Rule 6: unknown region returns None.
        """
        if region not in SUPPORTED_REGIONS:
            return None

        # Weekend check (ISO weekday: Mon=1, Sun=7)
        if check_date.isoweekday() not in WORKING_DAYS_BY_REGION[region]:
            return False

        # Holiday check
        date_str = check_date.strftime("%Y-%m-%d")
        if date_str in self._holidays_for_region(region):
            return False

        return True

    def business_days_between(
        self, start_date: date, end_date: date, region: str = "KE"
    ) -> Optional[int]:
        """
        Count business days between dates (inclusive of end, exclusive of start).

        Rule 1: returns None when end < start.
        Rule 6: unknown region returns None.
        """
        if region not in SUPPORTED_REGIONS:
            return None
        if end_date < start_date:
            return None

        count = 0
        current = start_date + timedelta(days=1)
        while current <= end_date:
            if self.is_business_day(current, region):
                count += 1
            current += timedelta(days=1)
        return count

    def business_hours_between(
        self,
        start: datetime,
        end: datetime,
        region: str = "KE",
    ) -> Optional[Decimal]:
        """
        Compute business hours between two datetimes.

        Rule 1: returns None when end < start.
        Rule 6: unknown region returns None.
        """
        if region not in SUPPORTED_REGIONS:
            return None
        if end < start:
            return None

        bh_start, bh_end = BUSINESS_HOURS_BY_REGION[region]
        total_hours = Decimal("0")

        # Iterate per business day
        current_day = start.date()
        while current_day <= end.date():
            if not self.is_business_day(current_day, region):
                current_day += timedelta(days=1)
                continue

            day_start = datetime.combine(current_day, bh_start)
            day_end = datetime.combine(current_day, bh_end)

            # Clip to actual start/end on edge days
            window_start = max(day_start, start)
            window_end = min(day_end, end)

            if window_end > window_start:
                delta = window_end - window_start
                hrs = Decimal(delta.total_seconds()) / Decimal("3600")
                total_hours += hrs

            current_day += timedelta(days=1)

        return total_hours.quantize(Decimal("0.01"))

    def sla_deadline(
        self,
        start: datetime,
        target_business_days: int,
        region: str = "KE",
    ) -> Optional[datetime]:
        """
        Compute SLA deadline from a start datetime + business-day target.

        E.g. CBK 30-day complaint resolution starting 2026-04-01 in KE
        → exclude weekends + holidays.

        Rule 6: unknown region returns None.
        """
        if region not in SUPPORTED_REGIONS:
            return None
        if target_business_days <= 0:
            return start

        current = start.date()
        days_added = 0
        while days_added < target_business_days:
            current += timedelta(days=1)
            if self.is_business_day(current, region):
                days_added += 1

        # Set to end of business day on deadline date
        _, bh_end = BUSINESS_HOURS_BY_REGION[region]
        return datetime.combine(current, bh_end)


def _self_test() -> None:
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as tmpdir:
        engine = SlaCalendarEngine(
            calendar_path=Path(tmpdir) / "sla_calendar.json"
        )

        # Test 1: Kenya business day check
        # 2026-05-04 is Monday — business day
        assert engine.is_business_day(date(2026, 5, 4), "KE") is True
        # 2026-05-09 is Saturday — not business day
        assert engine.is_business_day(date(2026, 5, 9), "KE") is False
        # 2026-05-01 is Labour Day in KE — public holiday
        assert engine.is_business_day(date(2026, 5, 1), "KE") is False

        # Test 2: Rule 6 — unknown region returns None
        assert engine.is_business_day(date(2026, 5, 4), "ZZ") is None

        # Test 3: business_days_between
        # Mon Apr 6 → Mon Apr 13 = 5 business days (no holidays in this week)
        # Wait, 2026-04-06 is Easter Monday in KE — holiday
        # Let's use a clean week: Mon May 4 → Mon May 11
        # Mon-Fri (May 4-8): excluded start, includes 5-8 = 4 business days
        # Sat-Sun May 9-10: 0
        # Mon May 11: 1
        # Total: 5
        bd = engine.business_days_between(
            date(2026, 5, 4), date(2026, 5, 11), "KE"
        )
        assert bd == 5, f"Expected 5, got {bd}"

        # Test 4: Rule 1 — end before start
        bd_neg = engine.business_days_between(
            date(2026, 5, 11), date(2026, 5, 4), "KE"
        )
        assert bd_neg is None

        # Test 5: business_hours_between within single day
        # 9:00 to 12:00 on a Monday = 3 hours
        bh = engine.business_hours_between(
            datetime(2026, 5, 4, 9, 0),
            datetime(2026, 5, 4, 12, 0),
            "KE",
        )
        assert bh == Decimal("3.00"), f"Got {bh}"

        # Test 6: business_hours_between across weekend
        # Friday 16:00 to Monday 09:00 = 1 hour (Fri) + 1 hour (Mon) = 2 hours
        # Fri 2026-05-08 16:00 → Mon 2026-05-11 09:00
        # Friday: 16:00-17:00 = 1 hour
        # Sat-Sun: 0
        # Monday: 08:00-09:00 = 1 hour
        bh2 = engine.business_hours_between(
            datetime(2026, 5, 8, 16, 0),
            datetime(2026, 5, 11, 9, 0),
            "KE",
        )
        assert bh2 == Decimal("2.00"), f"Got {bh2}"

        # Test 7: sla_deadline — 5 business days from Mon
        deadline = engine.sla_deadline(
            datetime(2026, 5, 4, 10, 0),  # Monday May 4
            target_business_days=5,
            region="KE",
        )
        # 5 business days from Mon May 4 → Mon May 11 (Tue 5, Wed 6, Thu 7, Fri 8, Mon 11)
        assert deadline.date() == date(2026, 5, 11), f"Got {deadline.date()}"

        # Test 8: add custom holiday
        result = engine.add_holiday("2026-07-04", "KE", "Custom holiday")
        assert result["added"]
        assert engine.is_business_day(date(2026, 7, 4), "KE") is False

        # Test 9: Rule 6 — invalid region rejected
        result = engine.add_holiday("2026-12-31", "ZZ")
        assert not result["added"]
        assert "unknown_region" in result["error"]

    print("  ✅ sla_calendar self-test PASS")


if __name__ == "__main__":
    _self_test()
