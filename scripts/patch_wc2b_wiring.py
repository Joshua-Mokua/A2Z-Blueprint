#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
WC-2b — wire the work calendar into the calculations that were getting it wrong.

Until now workcal only fed the header. This is the correctness batch.

WHAT CHANGES

1. utils/branch_log_analytics.py
   _target_for()  — the daily index target is now WEIGHTED by the calendar:
                    weekday 1.0, Saturday 0.5, Sunday/public holiday 0.0.
                    (The docstring always said a per-date target would slot in
                    here; this is that.)
   carried_forward() — Sundays and public holidays are SKIPPED entirely: no
                    target, no variance, the running balance passes through
                    untouched. Every row now carries `working_day` so the
                    history grid can render rest days distinctly.

2. utils/branch_log_state.py
   _deadline_for() — the auto-submit cutoff moves to deadline_time on the NEXT
                    WORKING DAY rather than blindly D+1. A Saturday log is due
                    Monday 09:00, not Sunday 09:00.
   return/lock     — the 3-day window counts BUSINESS days. A log submitted on
                    Friday no longer burns its return window over a weekend the
                    manager was never expected to work.

WHY IT MATTERED
   Before: every Sunday charged each of 487 staff a full day's deficit, and the
   carried-forward balance drifted by roughly one target per week per person,
   permanently and invisibly. Public holidays did the same. The lock sweep could
   also expire a Friday submission before the manager's next working day.

EVERY CALENDAR CALL FALLS BACK. If utils.workcal is unavailable or the config is
unreadable, each site reverts to the previous calendar-day behaviour rather than
raising. A broken calendar must not stop the Daily Log working.

Usage (from project root, .venv active):
    python scripts\\patch_wc2b_wiring.py             # dry run
    python scripts\\patch_wc2b_wiring.py --apply     # write, then self-test
    python scripts\\patch_wc2b_wiring.py --selftest  # re-run the tests only
"""
import os
import shutil
import sys

ANALYTICS = os.path.join("utils", "branch_log_analytics.py")
STATE = os.path.join("utils", "branch_log_state.py")
BACKUP_SUFFIX = ".pre_wc2b"

# ── analytics: calendar-weighted target ──────────────────────────────────────
AN_OLD_TARGET = '''def _target_for(log: dict) -> float:
    """Daily index target for a log's date. Currently a single global target;
    a per-role/per-date target can slot in here later without changing callers."""
    return daily_index_target()'''

AN_NEW_TARGET = '''def _working_weight(log: dict) -> float:
    """Work-calendar weight for a log's date: 1.0 weekday, 0.5 Saturday,
    0.0 Sunday / public holiday.

    Falls back to 1.0 (a full working day) whenever the calendar cannot be
    consulted. Over-counting a working day is recoverable; silently zeroing
    everyone's target because a config file went missing is not.
    """
    try:
        from utils import workcal
        return float(workcal.target_weight(str(log.get("log_date", ""))[:10]))
    except Exception:
        return 1.0


def _is_working_day(log: dict) -> bool:
    """True when the log's date is one on which work was expected at all."""
    return _working_weight(log) > 0.0


def _target_for(log: dict) -> float:
    """Daily index target for a log's date, weighted by the work calendar.

    A Saturday carries half the weekday target (branches run half days); a
    Sunday or gazetted public holiday carries none. A per-role target can still
    slot in here later without changing callers.
    """
    return round(daily_index_target() * _working_weight(log), 2)'''

AN_OLD_LOOP = '''        tgt = _target_for(r)
        idx = _effective_index(r)
        var = round(idx - tgt, 2)
        running = round(running + var, 2)
        r["target"] = tgt
        r["variance"] = var
        r["cf_variance"] = running
    return rows'''

AN_NEW_LOOP = '''        idx = _effective_index(r)
        if not _is_working_day(r):
            # RULING: Sundays and public holidays are excluded from the walk
            # entirely — no target, so no deficit can accrue. Work genuinely
            # done on a rest day stays visible as `index` but is not banked
            # into the running balance either way.
            r["target"] = 0.0
            r["variance"] = 0.0
            r["cf_variance"] = running
            r["working_day"] = False
            continue
        tgt = _target_for(r)
        var = round(idx - tgt, 2)
        running = round(running + var, 2)
        r["target"] = tgt
        r["variance"] = var
        r["cf_variance"] = running
        r["working_day"] = True
    return rows'''

# ── state: rolling deadline + business-day windows ───────────────────────────
ST_OLD_DEADLINE = '''def _deadline_for(log_date_str: str) -> datetime:
    """The auto-submit cutoff for a given log date = (log_date + 1 day) at deadline_time."""
    d = date.fromisoformat(str(log_date_str))
    hh, mm = deadline_time().split(":")
    return datetime.combine(d + timedelta(days=1), datetime.min.time()).replace(
        hour=int(hh), minute=int(mm)
    )'''

ST_NEW_DEADLINE = '''def _deadline_for(log_date_str: str) -> datetime:
    """The auto-submit cutoff for a log date: deadline_time on the NEXT WORKING DAY.

    Section 57 of the Interpretation and General Provisions Act rolls a deadline
    falling on a Sunday or public holiday to the next working day, and the same
    logic is what staff expect: a Saturday log is due Monday 09:00, not Sunday
    09:00. Falls back to the old D+1 rule if the calendar is unavailable.
    """
    d = date.fromisoformat(str(log_date_str))
    hh, mm = deadline_time().split(":")
    try:
        from utils import workcal
        due_day = workcal.next_working_day(d)
    except Exception:
        due_day = d + timedelta(days=1)
    return datetime.combine(due_day, datetime.min.time()).replace(
        hour=int(hh), minute=int(mm)
    )


def _window_elapsed(stamped: datetime, now: datetime,
                    days: int = RETURN_WINDOW_DAYS) -> bool:
    """True when more than `days` WORKING days have passed since `stamped`.

    Business days, not calendar days: a log submitted on a Friday must not burn
    its return window over a weekend nobody was rostered for. Falls back to the
    old wall-clock comparison when the calendar cannot be consulted.
    """
    try:
        from utils import workcal
        return workcal.business_days_between(stamped.date(), now.date()) > days
    except Exception:
        return (now - stamped) > timedelta(days=days)'''

ST_OLD_RETURN = '''    if stamped and (now - stamped) > timedelta(days=RETURN_WINDOW_DAYS):
        raise ValueError(f"Return window ({RETURN_WINDOW_DAYS} days) has elapsed — admin unlock required")'''

ST_NEW_RETURN = '''    if stamped and _window_elapsed(stamped, now):
        raise ValueError(f"Return window ({RETURN_WINDOW_DAYS} working days) has elapsed — admin unlock required")'''

ST_OLD_LOCK = '''        if stamped and (now - stamped) > timedelta(days=RETURN_WINDOW_DAYS):
            l["locked"] = True'''

ST_NEW_LOCK = '''        if stamped and _window_elapsed(stamped, now):
            l["locked"] = True'''

EDITS = [
    (ANALYTICS, "analytics — calendar-weighted _target_for", AN_OLD_TARGET, AN_NEW_TARGET),
    (ANALYTICS, "analytics — carried_forward skips rest days", AN_OLD_LOOP, AN_NEW_LOOP),
    (STATE, "state — deadline rolls to next working day", ST_OLD_DEADLINE, ST_NEW_DEADLINE),
    (STATE, "state — return window in business days", ST_OLD_RETURN, ST_NEW_RETURN),
    (STATE, "state — lock sweep in business days", ST_OLD_LOCK, ST_NEW_LOCK),
]

FILES = [ANALYTICS, STATE]


def selftest():
    """Exercises the REAL modules, not mocks."""
    sys.path.insert(0, os.getcwd())
    from datetime import datetime, date
    import importlib
    from utils import branch_log_analytics as an
    from utils import branch_log_state as st
    from utils import workcal
    importlib.reload(workcal)
    importlib.reload(an)
    importlib.reload(st)

    fails = []

    def check(label, got, want):
        ok = got == want
        print("  %s  %-50s got=%r want=%r" % ("ok " if ok else "FAIL", label, got, want))
        if not ok:
            fails.append(label)

    base = an.daily_index_target()
    print("\n-- calendar-weighted targets (base target = %s)" % base)
    check("Mon 2026-08-03 target", an._target_for({"log_date": "2026-08-03"}), round(base * 1.0, 2))
    check("Sat 2026-08-08 target", an._target_for({"log_date": "2026-08-08"}), round(base * 0.5, 2))
    check("Sun 2026-08-09 target", an._target_for({"log_date": "2026-08-09"}), 0.0)
    check("Xmas 2026-12-25 target", an._target_for({"log_date": "2026-12-25"}), 0.0)
    check("bad date falls back to full", an._target_for({"log_date": "not-a-date"}),
          round(base * 1.0, 2))

    print("\n-- carried-forward across a week (index = base every day)")
    logs = [{"log_date": d, "index": base} for d in
            ("2026-08-03", "2026-08-04", "2026-08-05", "2026-08-06",
             "2026-08-07", "2026-08-08", "2026-08-09", "2026-08-10")]
    rows = an.carried_forward(logs)
    by = {r["log_date"]: r for r in rows}
    check("Mon variance is 0", by["2026-08-03"]["variance"], 0.0)
    check("Sat variance is +half", by["2026-08-08"]["variance"], round(base * 0.5, 2))
    check("Sun target is 0", by["2026-08-09"]["target"], 0.0)
    check("Sun variance is 0", by["2026-08-09"]["variance"], 0.0)
    check("Sun flagged not working", by["2026-08-09"]["working_day"], False)
    check("Sat flagged working", by["2026-08-08"]["working_day"], True)
    check("Sun does not move the balance",
          by["2026-08-09"]["cf_variance"], by["2026-08-08"]["cf_variance"])

    print("\n-- the bug this fixes: an EMPTY Sunday must not create a deficit")
    empty = [{"log_date": "2026-08-08", "index": 0.0},
             {"log_date": "2026-08-09", "index": 0.0},
             {"log_date": "2026-08-10", "index": 0.0}]
    er = {r["log_date"]: r for r in an.carried_forward(empty)}
    check("empty Sat deficit is half a day", er["2026-08-08"]["variance"], round(-base * 0.5, 2))
    check("empty Sun deficit is ZERO", er["2026-08-09"]["variance"], 0.0)
    check("empty Mon deficit is a full day", er["2026-08-10"]["variance"], round(-base, 2))
    check("balance = half + full only",
          er["2026-08-10"]["cf_variance"], round(-base * 1.5, 2))

    print("\n-- rolling deadlines")
    check("Thu log due Fri 09:00", st._deadline_for("2026-08-06"),
          datetime(2026, 8, 7, 9, 0))
    check("Fri log due Sat 09:00", st._deadline_for("2026-08-07"),
          datetime(2026, 8, 8, 9, 0))
    check("Sat log due MON 09:00 (not Sun)", st._deadline_for("2026-08-08"),
          datetime(2026, 8, 10, 9, 0))
    check("24 Dec log due MON 28 Dec", st._deadline_for("2026-12-24"),
          datetime(2026, 12, 28, 9, 0))

    print("\n-- business-day return/lock window (3 working days)")
    fri = datetime(2026, 8, 7, 16, 0)
    check("Fri -> Mon: still open", st._window_elapsed(fri, datetime(2026, 8, 10, 16, 0)), False)
    check("Fri -> Tue: still open", st._window_elapsed(fri, datetime(2026, 8, 11, 16, 0)), False)
    check("Fri -> Wed: elapsed", st._window_elapsed(fri, datetime(2026, 8, 12, 16, 0)), True)
    mon = datetime(2026, 8, 3, 16, 0)
    check("Mon -> Thu: still open", st._window_elapsed(mon, datetime(2026, 8, 6, 16, 0)), False)
    check("Mon -> Fri: elapsed", st._window_elapsed(mon, datetime(2026, 8, 7, 16, 0)), True)

    print("\n" + ("=" * 62))
    if fails:
        print("SELFTEST FAILED — %d check(s): %s" % (len(fails), ", ".join(fails)))
        return 1
    print("SELFTEST PASSED — all checks green.")
    return 0


def main():
    if "--selftest" in sys.argv:
        return selftest()
    apply = "--apply" in sys.argv

    for path in FILES:
        if not os.path.isfile(path):
            print("ABORT: %s not found. Run from the project root." % path)
            return 1
    if not os.path.isfile(os.path.join("utils", "workcal.py")):
        print("ABORT: utils/workcal.py missing — run install_wc1_workcal.py --apply first.")
        return 1

    srcs = {}
    for path in FILES:
        with open(path, "r", encoding="utf-8") as fh:
            srcs[path] = fh.read()

    if "_working_weight" in srcs[ANALYTICS]:
        print("ABORT: analytics already has _working_weight — WC-2b looks applied.")
        return 1

    for path, name, old, new in EDITS:
        n = srcs[path].count(old)
        if n != 1:
            print("ABORT: anchor '%s' matched %d times in %s (expected 1)."
                  % (name, n, os.path.basename(path)))
            return 1
        srcs[path] = srcs[path].replace(old, new, 1)
        print("  ok  %s" % name)

    print("\n%d/%d anchors matched across %d files." % (len(EDITS), len(EDITS), len(FILES)))

    if not apply:
        print("\nDRY RUN — nothing written. Re-run with --apply.")
        return 0

    for path in FILES:
        shutil.copy2(path, path + BACKUP_SUFFIX)
        with open(path, "w", encoding="utf-8", newline="") as fh:
            fh.write(srcs[path])
        print("APPLIED %s  (backup: %s)" % (path, os.path.basename(path) + BACKUP_SUFFIX))

    print("\nCompiling...")
    import py_compile
    for path in FILES:
        try:
            py_compile.compile(path, doraise=True)
            print("  ok  %s compiles" % os.path.basename(path))
        except Exception as exc:
            print("  FAIL %s: %s" % (path, exc))
            print("\nRestore with: copy %s%s %s" % (path, BACKUP_SUFFIX, path))
            return 1

    print("\nRunning self-test against the patched modules...")
    rc = selftest()
    if rc == 0:
        print("\nWC2B_PASSED_PROCEED_WITH_COMMIT")
        print("NOTE: restart uvicorn — the sweeps run in /pending and /analytics.")
    else:
        print("\nSelf-test failed. Restore with:")
        for path in FILES:
            print("  copy %s%s %s" % (path, BACKUP_SUFFIX, path))
    return rc


if __name__ == "__main__":
    sys.exit(main())
