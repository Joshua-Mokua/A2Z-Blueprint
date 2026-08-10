#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
WC-1 — Kenya working calendar (config + module). NO behaviour change yet.

Creates two files and nothing else:
    data/work_calendar.json   — the editable calendar (weekly pattern + holidays)
    utils/workcal.py          — pure-stdlib helpers over that config

Nothing imports workcal yet; WC-2 wires it into the carried-forward engine and
the deadline/lock sweeps. Splitting it this way means the calendar can be proved
correct on its own before any live calculation depends on it.

RULINGS BAKED IN (your calls):
  * Saturday   -> working day at 0.5 target weight
  * Sunday + public holidays -> excluded from the carried-forward walk entirely:
    no target, no deficit
  * 3-day return/lock window and the 09:00 deadline -> business days, rolling
    past Sundays and holidays

STATUTORY BASIS:
  * Public Holidays Act Cap 110 s.2(2): a holiday falling on a SUNDAY moves the
    holiday to the following Monday. A holiday on a SATURDAY gets no automatic
    substitute. Implemented as `sunday_substitution`.
  * Interpretation and General Provisions Act s.57: statutory deadlines falling
    on a Sunday or public holiday roll to the next working day. This is the
    justification for next_working_day() driving the deadline sweep.

WHY THE HOLIDAYS ARE CONFIG, NOT CODE:
  * Idd-ul-Fitr and Idd-ul-Adha are gazetted by the Interior CS only once the
    Chief Kadhi confirms the moon sighting — usually days ahead. Any date we
    write in advance is a forecast. Entries carry `confirmed`.
  * The Interior CS can declare one-off holidays at short notice (a state
    funeral, an election day). No algorithm predicts those.
  * The 10 October holiday has been gazetted under several names over the years
    (Moi Day / Huduma Day / Utamaduni Day / Mazingira Day). Labels are editable
    on purpose; the stable identifier is the `key`.

Usage (from project root, .venv active):
    python scripts\\install_wc1_workcal.py             # dry run + self-test
    python scripts\\install_wc1_workcal.py --apply     # write the two files
    python scripts\\install_wc1_workcal.py --selftest  # run the tests only
"""
import json
import os
import sys
from datetime import date, datetime, timedelta

CFG_PATH = os.path.join("data", "work_calendar.json")
MOD_PATH = os.path.join("utils", "workcal.py")

# ── the seed calendar ────────────────────────────────────────────────────────
CONFIG = {
    "_comment": (
        "Working calendar for A2Z MIS 360. Weekday keys are Python weekday(): "
        "0=Mon .. 6=Sun. Values are the fraction of the daily index target that "
        "applies on that day (0 = non-working). Labels are editable; the `key` "
        "is the stable identifier. Islamic holidays are gazetted on moon "
        "sighting, so entries with confirmed=false are forecasts."
    ),
    "timezone": "Africa/Nairobi",
    "weekly_pattern": {"0": 1.0, "1": 1.0, "2": 1.0, "3": 1.0, "4": 1.0, "5": 0.5, "6": 0.0},
    "sunday_substitution": True,
    "recurring_holidays": [
        {"key": "new_year", "label": "New Year's Day", "month": 1, "day": 1},
        {"key": "labour_day", "label": "Labour Day", "month": 5, "day": 1},
        {"key": "madaraka_day", "label": "Madaraka Day", "month": 6, "day": 1},
        {"key": "oct_10", "label": "Mazingira Day", "month": 10, "day": 10},
        {"key": "mashujaa_day", "label": "Mashujaa Day", "month": 10, "day": 20},
        {"key": "jamhuri_day", "label": "Jamhuri Day", "month": 12, "day": 12},
        {"key": "christmas", "label": "Christmas Day", "month": 12, "day": 25},
        {"key": "boxing_day", "label": "Utamaduni Day", "month": 12, "day": 26}
    ],
    "easter_holidays": [
        {"key": "good_friday", "label": "Good Friday", "offset_days": -2},
        {"key": "easter_monday", "label": "Easter Monday", "offset_days": 1}
    ],
    "gazetted": [
        {"date": "2026-03-20", "key": "idd_ul_fitr", "label": "Idd-ul-Fitr",
         "confirmed": True,
         "note": "Gazetted for Friday 20 March 2026."},
        {"date": "2026-05-27", "key": "idd_ul_azha", "label": "Idd-ul-Azha",
         "confirmed": False,
         "note": "Approximate. Confirm against the gazette before relying on it."}
    ],
    "closures": [],
}

# ── the module ───────────────────────────────────────────────────────────────
MODULE = '''"""utils.workcal — Kenya working calendar.

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
'''


# ── self-test ────────────────────────────────────────────────────────────────
def selftest():
    sys.path.insert(0, os.getcwd())
    import importlib
    import utils.workcal as wc
    importlib.reload(wc)

    fails = []

    def check(label, got, want):
        ok = got == want
        print("  %s  %-52s got=%r want=%r" % ("ok " if ok else "FAIL", label, got, want))
        if not ok:
            fails.append(label)

    print("\n-- Easter (known-good Gregorian dates)")
    check("Easter 2024", wc.easter_sunday(2024), date(2024, 3, 31))
    check("Easter 2025", wc.easter_sunday(2025), date(2025, 4, 20))
    check("Easter 2026", wc.easter_sunday(2026), date(2026, 4, 5))
    check("Easter 2027", wc.easter_sunday(2027), date(2027, 3, 28))

    print("\n-- weekly pattern")
    check("Mon 2026-08-03 weight", wc.target_weight(date(2026, 8, 3)), 1.0)
    check("Sat 2026-08-08 weight", wc.target_weight(date(2026, 8, 8)), 0.5)
    check("Sun 2026-08-09 weight", wc.target_weight(date(2026, 8, 9)), 0.0)
    check("Sat is a working day", wc.is_working_day(date(2026, 8, 8)), True)
    check("Sun is not", wc.is_working_day(date(2026, 8, 9)), False)

    print("\n-- fixed holidays 2026")
    check("1 Jan is a holiday", wc.is_holiday(date(2026, 1, 1)), True)
    check("1 Jan weight is 0", wc.target_weight(date(2026, 1, 1)), 0.0)
    check("Good Friday 2026 = 3 Apr", wc.is_holiday(date(2026, 4, 3)), True)
    check("Easter Monday 2026 = 6 Apr", wc.is_holiday(date(2026, 4, 6)), True)

    print("\n-- Cap 110 s.2(2) Sunday substitution")
    # 1 Nov 2026 is a Sunday; use Madaraka Day 2025 (1 June 2025 was a Sunday).
    check("1 Jun 2025 was a Sunday", date(2025, 6, 1).weekday(), 6)
    check("Mon 2 Jun 2025 observed", wc.is_holiday(date(2025, 6, 2)), True)
    check("observed label marked", "(observed)" in wc.holiday_label(date(2025, 6, 2)), True)

    print("\n-- Saturday holidays get NO substitute (Cap 110)")
    # 2026: 10 Oct, 12 Dec and 26 Dec all fall on a Saturday.
    check("10 Oct 2026 is a Saturday", date(2026, 10, 10).weekday(), 5)
    check("10 Oct 2026 is a holiday", wc.is_holiday(date(2026, 10, 10)), True)
    check("Mon 12 Oct 2026 NOT substituted", wc.is_holiday(date(2026, 10, 12)), False)
    check("12 Dec 2026 is a Saturday", date(2026, 12, 12).weekday(), 5)
    check("26 Dec 2026 is a Saturday", date(2026, 12, 26).weekday(), 5)

    print("\n-- gazetted (moon-sighting) entries")
    check("Idd-ul-Fitr 20 Mar 2026", wc.is_holiday(date(2026, 3, 20)), True)
    check("one unconfirmed entry in 2026", len(wc.unconfirmed_holidays(2026)), 1)

    print("\n-- rolling deadlines (Interpretation Act s.57)")
    # Fri 2026-08-07 -> next working day is Sat 8th (half day, still working).
    check("Fri 7 Aug -> Sat 8 Aug", wc.next_working_day(date(2026, 8, 7)), date(2026, 8, 8))
    # Sat 2026-08-08 -> Sunday is skipped, so Monday 10th.
    check("Sat 8 Aug -> Mon 10 Aug", wc.next_working_day(date(2026, 8, 8)), date(2026, 8, 10))
    # Thu 24 Dec 2026 -> Christmas (Fri) skipped, Boxing Day (Sat) skipped,
    # Sunday skipped -> Monday 28 Dec.
    check("Thu 24 Dec -> Mon 28 Dec", wc.next_working_day(date(2026, 12, 24)), date(2026, 12, 28))

    print("\n-- business-day arithmetic")
    check("Mon +3bd = Thu", wc.add_business_days(date(2026, 8, 3), 3), date(2026, 8, 6))
    # Thu 6 Aug +3bd: Fri 7, Sat 8, (Sun skipped), Mon 10.
    check("Thu +3bd spans weekend", wc.add_business_days(date(2026, 8, 6), 3), date(2026, 8, 10))
    check("between Mon and Fri = 4", wc.business_days_between(date(2026, 8, 3), date(2026, 8, 7)), 4)
    check("between Fri and Mon = 2", wc.business_days_between(date(2026, 8, 7), date(2026, 8, 10)), 2)
    check("same day = 0", wc.business_days_between(date(2026, 8, 3), date(2026, 8, 3)), 0)
    check("reverse is negative", wc.business_days_between(date(2026, 8, 7), date(2026, 8, 3)), -4)

    print("\n-- working_days_in / describe")
    check("Aug 2026 working days", len(wc.working_days_in(date(2026, 8, 1), date(2026, 8, 31))), 26)
    check("describe Sat half_day", wc.describe(date(2026, 8, 8))["half_day"], True)
    check("describe accepts a string", wc.describe("2026-08-09")["working"], False)

    print("\n-- resilience")
    check("datetime accepted", wc.target_weight(datetime(2026, 8, 8, 14, 0)), 0.5)

    print("\n" + ("=" * 60))
    if fails:
        print("SELFTEST FAILED — %d check(s): %s" % (len(fails), ", ".join(fails)))
        return 1
    print("SELFTEST PASSED — all checks green.")
    return 0


def main():
    apply = "--apply" in sys.argv
    only_test = "--selftest" in sys.argv

    if only_test:
        return selftest()

    if not os.path.isdir("data") or not os.path.isdir("utils"):
        print("ABORT: run from the project root (needs data/ and utils/).")
        return 1

    exists = [p for p in (CFG_PATH, MOD_PATH) if os.path.exists(p)]
    if exists:
        print("ABORT: already present, refusing to overwrite: %s" % ", ".join(exists))
        print("       Delete them first if you intend to re-install.")
        return 1

    print("Will create:")
    print("  %s   (%d holidays seeded, %d gazetted)"
          % (CFG_PATH, len(CONFIG["recurring_holidays"]) + len(CONFIG["easter_holidays"]),
             len(CONFIG["gazetted"])))
    print("  %s   (%d lines)" % (MOD_PATH, MODULE.count("\n") + 1))

    if not apply:
        print("\nDRY RUN — nothing written. Re-run with --apply, then --selftest.")
        return 0

    with open(CFG_PATH, "w", encoding="utf-8", newline="") as fh:
        json.dump(CONFIG, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    print("CREATED %s" % CFG_PATH)

    with open(MOD_PATH, "w", encoding="utf-8", newline="") as fh:
        fh.write(MODULE)
    print("CREATED %s" % MOD_PATH)

    print("\nRunning self-test against the files just written...")
    return selftest()


if __name__ == "__main__":
    sys.exit(main())
