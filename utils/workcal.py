"""utils.workcal — Kenya working calendar.

Single source of truth for "is this a working day, and how much of the daily
index target applies to it". Read by the carried-forward variance engine and by
the Daily Log deadline / lock sweeps.

Pure stdlib on purpose: no pandas, no streamlit, no DB. It must be importable
from a bare script, a test, or a request handler without dragging the app in.

CONFIG: data/work_calendar.json
    weekly_pattern       {"0".."6": weight}   0=Mon .. 6=Sun, Python weekday()
    sunday_substitution  bool  — holiday on Sunday moves to the Monday
    recurring_holidays   fixed month/day entries
    easter_holidays      offsets from Easter Sunday (computed, not stored)
    gazetted             explicit dates (Islamic holidays, one-off proclamations)
    closures             bank-specific non-working days (not public holidays)

RULINGS:
    Saturday                   -> working, 0.5 weight
    Sunday + public holidays   -> non-working, weight 0.0, excluded from the
                                  carried-forward walk (no target, no deficit)
    Deadline / lock windows    -> business days, rolling past non-working days

STATUTE:
    Public Holidays Act Cap 110 s.2(2) — a holiday on a SUNDAY is observed on the
    following Monday; a holiday on a SATURDAY has no automatic substitute.
    Interpretation and General Provisions Act s.57 — statutory deadlines falling
    on a Sunday or public holiday roll to the next working day.

CAVEAT: Idd-ul-Fitr and Idd-ul-Azha are gazetted on moon sighting, days ahead.
Entries carry `confirmed`; unconfirmed_holidays() reports the forecasts so an
admin can reconcile them against the gazette.
"""
from __future__ import annotations

import json
import os
import threading
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Tuple

_HERE = os.path.dirname(os.path.abspath(__file__))
_DATA_DIR = os.path.join(os.path.dirname(_HERE), "data")
CONFIG_PATH = os.path.join(_DATA_DIR, "work_calendar.json")

# Used only when the config file is missing or unreadable. Deliberately a full
# working week with no holidays: if the calendar disappears, the system must
# over-count working days rather than silently erase everyone's targets.
_FALLBACK = {
    "weekly_pattern": {"0": 1.0, "1": 1.0, "2": 1.0, "3": 1.0, "4": 1.0, "5": 0.5, "6": 0.0},
    "sunday_substitution": True,
    "recurring_holidays": [],
    "easter_holidays": [],
    "gazetted": [],
    "closures": [],
}

_lock = threading.Lock()
_cache: Optional[dict] = None
_cache_mtime: Optional[float] = None


def _load() -> dict:
    """Config, cached on file mtime so a hot edit is picked up without restart."""
    global _cache, _cache_mtime
    try:
        mtime = os.path.getmtime(CONFIG_PATH)
    except OSError:
        return dict(_FALLBACK)
    with _lock:
        if _cache is not None and _cache_mtime == mtime:
            return _cache
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as fh:
                cfg = json.load(fh)
            if not isinstance(cfg, dict) or "weekly_pattern" not in cfg:
                raise ValueError("work_calendar.json missing weekly_pattern")
            _cache, _cache_mtime = cfg, mtime
            return cfg
        except Exception:
            # Never return {} — a silent empty config would zero every target.
            return dict(_FALLBACK)


def reload_config() -> dict:
    """Drop the cache and re-read. Call after an admin edit."""
    global _cache, _cache_mtime
    with _lock:
        _cache, _cache_mtime = None, None
    return _load()


def _as_date(value) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    s = str(value).strip()[:10]
    return date.fromisoformat(s)


# ── Easter (Anonymous Gregorian algorithm) ───────────────────────────────────
def easter_sunday(year: int) -> date:
    """Gregorian Easter Sunday. Good Friday and Easter Monday hang off this."""
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = ((h + l - 7 * m + 114) % 31) + 1
    return date(year, month, day)


# ── holiday set for a year ───────────────────────────────────────────────────
def holidays(year: int) -> Dict[date, str]:
    """All public holidays observed in `year`, as {date: label}.

    Applies the Cap 110 s.2(2) Sunday rule: a holiday landing on a Sunday is
    OBSERVED on the following Monday. The original Sunday is kept too — it is a
    Sunday, so already non-working, and dropping it would misreport the day.
    A Saturday holiday gets no substitute, per the same section.
    """
    cfg = _load()
    out: Dict[date, str] = {}

    def _place(d: date, label: str) -> None:
        out.setdefault(d, label)
        if d.weekday() == 6 and cfg.get("sunday_substitution", True):
            out.setdefault(d + timedelta(days=1), label + " (observed)")

    for h in cfg.get("recurring_holidays", []) or []:
        try:
            _place(date(year, int(h["month"]), int(h["day"])), str(h.get("label", h.get("key", ""))))
        except Exception:
            continue

    if cfg.get("easter_holidays"):
        es = easter_sunday(year)
        for h in cfg["easter_holidays"]:
            try:
                _place(es + timedelta(days=int(h["offset_days"])),
                       str(h.get("label", h.get("key", ""))))
            except Exception:
                continue

    for group in ("gazetted", "closures"):
        for h in cfg.get(group, []) or []:
            try:
                d = _as_date(h["date"])
            except Exception:
                continue
            if d.year != year:
                continue
            _place(d, str(h.get("label", h.get("key", ""))))

    return out


def is_holiday(d) -> bool:
    d = _as_date(d)
    return d in holidays(d.year)


def holiday_label(d) -> str:
    d = _as_date(d)
    return holidays(d.year).get(d, "")


def unconfirmed_holidays(year: Optional[int] = None) -> List[dict]:
    """Gazetted entries still flagged confirmed=false — forecasts to reconcile.

    Also reports years with NO Islamic holiday entries at all, which is the more
    dangerous case: a silent absence looks exactly like a working day.
    """
    cfg = _load()
    rows = []
    for h in cfg.get("gazetted", []) or []:
        if h.get("confirmed") is True:
            continue
        try:
            d = _as_date(h["date"])
        except Exception:
            continue
        if year is not None and d.year != year:
            continue
        rows.append(dict(h))
    return rows


def years_missing_gazetted() -> List[int]:
    """Years covered by gazetted entries — callers can diff against the years
    they actually need. Empty list means nothing is seeded at all."""
    cfg = _load()
    ys = set()
    for h in cfg.get("gazetted", []) or []:
        try:
            ys.add(_as_date(h["date"]).year)
        except Exception:
            continue
    return sorted(ys)


# ── the core questions ───────────────────────────────────────────────────────
def target_weight(d) -> float:
    """Fraction of the daily index target that applies on this date.

    1.0 weekday, 0.5 Saturday, 0.0 Sunday, 0.0 on any public holiday or closure.
    """
    d = _as_date(d)
    if is_holiday(d):
        return 0.0
    pattern = _load().get("weekly_pattern", _FALLBACK["weekly_pattern"])
    try:
        return float(pattern.get(str(d.weekday()), 1.0))
    except (TypeError, ValueError):
        return 1.0


def is_working_day(d) -> bool:
    """True when any work is expected — Saturday counts (at half weight)."""
    return target_weight(d) > 0.0


def next_working_day(d) -> date:
    """The first working day strictly after `d`. Used to roll deadlines per
    the Interpretation and General Provisions Act s.57."""
    d = _as_date(d)
    for _ in range(1, 400):
        d = d + timedelta(days=1)
        if is_working_day(d):
            return d
    raise RuntimeError("no working day found within a year — check work_calendar.json")


def previous_working_day(d) -> date:
    d = _as_date(d)
    for _ in range(1, 400):
        d = d - timedelta(days=1)
        if is_working_day(d):
            return d
    raise RuntimeError("no working day found within a year — check work_calendar.json")


def add_business_days(d, n: int) -> date:
    """`n` working days after (n>0) or before (n<0) `d`. n=0 returns `d`."""
    d = _as_date(d)
    if n == 0:
        return d
    step = next_working_day if n > 0 else previous_working_day
    for _ in range(abs(int(n))):
        d = step(d)
    return d


def business_days_between(start, end) -> int:
    """Count of working days in (start, end] — i.e. excluding `start`,
    including `end`. Negative when end precedes start.
    """
    a, b = _as_date(start), _as_date(end)
    if a == b:
        return 0
    sign = 1 if b > a else -1
    lo, hi = (a, b) if b > a else (b, a)
    n, cur = 0, lo
    while cur < hi:
        cur += timedelta(days=1)
        if is_working_day(cur):
            n += 1
    return sign * n


def working_days_in(start, end) -> List[date]:
    """Every working day in the inclusive range [start, end]."""
    a, b = _as_date(start), _as_date(end)
    out, cur = [], a
    while cur <= b:
        if is_working_day(cur):
            out.append(cur)
        cur += timedelta(days=1)
    return out


def describe(d) -> dict:
    """Everything a UI needs about one date, in one call."""
    d = _as_date(d)
    return {
        "date": d.isoformat(),
        "weekday": d.strftime("%A"),
        "working": is_working_day(d),
        "weight": target_weight(d),
        "holiday": is_holiday(d),
        "label": holiday_label(d),
        "half_day": target_weight(d) == 0.5,
    }
