#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
E1 - absence exceptions: a missed day gets a reason before it gets acted on.

DRIVING RULING (2026-08-08, your words):
    "if it outvalidates then they may not have an opportunity to explain when
     action is being taken"

A missed day silently becomes a deficit, and the staff member first hears about
it when someone acts on the number. An exception record is how a manager states,
inside the window, WHY a day is missing - before the number is used.

THE RULE THAT DECIDES EVERYTHING

    Excusing an absence removes that day's target. Refusal does not.

        on_leave / sick / training / bereavement / system_outage -> target 0
        refused / no_explanation / other                          -> full target

    If every reason zeroed the target, an exception becomes a way to erase a
    deficit and the index stops measuring anything. If none did, someone on
    approved leave is punished for approved leave - the phantom-deficit problem
    WC-2b fixed for Sundays, reappearing one person at a time.

An EXCUSED day behaves exactly like a rest day for that person: no target, no
variance, skipped by the carried-forward walk. The BRANCH TARGET REBALANCES FOR
FREE, because the branch target is the sum of its staff's daily targets.

MEASURED on the real engine - one person, five working days, files nothing:

    no exceptions                       balance -125.0
    2 days excused (on_leave, sick)     balance  -75.0   <- 2 days lifted
    1 further day marked "refused"      balance  -75.0   <- refusal still charges

    recording "refused" with no note    REFUSED: a note is required for a
                                        reason that still carries the target

THE TAXONOMY IS CONFIG, NOT CODE. data/branch_log_config.json ->
`daily_log_exception_reasons`. Which reasons excuse is a policy decision the
bank may revise, and revising it must not need a deploy. An UNKNOWN reason does
NOT excuse - failing closed keeps accountability rather than quietly erasing a
deficit.

WHAT THIS ADDS
  utils/branch_log_exceptions.py (new) - the store. Atomic writes, mtime-cached
      reads (this is consulted once per grid row; re-parsing per call is the O(n)
      mistake this codebase has already made twice).
  utils/branch_log_analytics.py - _excused(), honoured by _working_weight() and
      surfaced by carried_forward() as excused / exception_reason /
      exception_note, so the grid can distinguish "the bank was closed" from
      "this person was excused".

STILL TO COME: E2 manager submit-on-behalf, E3 the non-submitter follow-up list,
E4 notification hooks. E1 first because everything else depends on what an
exception MEANS arithmetically, and that is the part that is painful to change
once managers have recorded hundreds of them.

Usage (from project root, .venv active):
    python scripts\\patch_e1_exceptions.py            # dry run
    python scripts\\patch_e1_exceptions.py --apply    # write + .pre_e1 backup
"""
import os
import shutil
import sys

MOD = os.path.join("utils", "branch_log_exceptions.py")
AN = os.path.join("utils", "branch_log_analytics.py")
BACKUP_SUFFIX = ".pre_e1"

MODULE = r'''"""
A2Z Daily Log — absence / non-submission exceptions (additive, new module).

WHY THIS EXISTS (ruling 2026-08-08):
    "if it outvalidates then they may not have an opportunity to explain when
     action is being taken"

A missed day silently becomes a deficit, and the staff member first learns of it
when someone acts on the number. An exception record is how a manager states,
inside the window, WHY a day is missing — before the number is used.

THE ONE RULE THAT MATTERS

    Excusing an absence removes that day's target.
    Refusal does not.

    on_leave / sick / training / bereavement / system_outage -> target 0
    refused / no_explanation                                  -> full target

If every reason zeroed the target, an exception would be a way to erase a
deficit and the index would stop measuring anything. If none did, someone on
approved leave is punished for being on approved leave — the phantom-deficit
problem WC-2b fixed for Sundays, reappearing one person at a time.

An EXCUSED day behaves exactly like a rest day for that person: no target, no
variance, skipped by the carried-forward walk. The branch target rebalances for
free, because the branch target is the sum of its staff's daily targets.

The taxonomy lives in data/branch_log_config.json under
`daily_log_exception_reasons`, NOT in code — which reasons excuse is a policy
decision the bank may revise, and revising it must not need a deploy.

Store: data/daily_log_exceptions.json, atomic writes.
"""
from __future__ import annotations

import json
import os
import tempfile
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional

from utils.core import DATA_DIR

_STORE = Path(DATA_DIR) / "daily_log_exceptions.json"
_CONFIG = Path(DATA_DIR) / "branch_log_config.json"

# Used only when the config key is absent. Deliberately conservative: the two
# accountability reasons do NOT excuse.
_DEFAULT_REASONS = [
    {"key": "on_leave",       "label": "On leave",              "excuses_target": True},
    {"key": "sick",           "label": "Sick",                  "excuses_target": True},
    {"key": "training",       "label": "Training / off-site",   "excuses_target": True},
    {"key": "bereavement",    "label": "Bereavement / public duty", "excuses_target": True},
    {"key": "system_outage",  "label": "System outage",         "excuses_target": True},
    {"key": "refused",        "label": "Refused to submit",     "excuses_target": False},
    {"key": "no_explanation", "label": "No explanation given",  "excuses_target": False},
    {"key": "other",          "label": "Other (state the reason)", "excuses_target": False},
]

_lock = threading.Lock()
_cache = None
_cache_mtime = None


def reasons() -> list:
    """The exception taxonomy, from config, falling back to the defaults."""
    try:
        cfg = json.loads(_CONFIG.read_text(encoding="utf-8"))
        rs = cfg.get("daily_log_exception_reasons")
        if isinstance(rs, list) and rs:
            return [r for r in rs if isinstance(r, dict) and r.get("key")]
    except Exception:
        pass
    return list(_DEFAULT_REASONS)


def excuses_target(reason_key: str) -> bool:
    """Does this reason remove the day's target? Unknown reasons do NOT —
    failing closed keeps accountability rather than quietly erasing a deficit.
    """
    k = str(reason_key or "").strip()
    for r in reasons():
        if str(r.get("key")) == k:
            return bool(r.get("excuses_target"))
    return False


def _key(staff_code: str, day: str) -> str:
    return f"{str(staff_code).strip()}|{str(day)[:10]}"


def _load() -> dict:
    """Cached on file mtime — this is read once per grid row, so re-parsing the
    file each time would be the O(n) mistake this codebase has made twice."""
    global _cache, _cache_mtime
    try:
        mtime = os.path.getmtime(_STORE)
    except OSError:
        return {}
    with _lock:
        if _cache is not None and _cache_mtime == mtime:
            return _cache
        try:
            raw = json.loads(_STORE.read_text(encoding="utf-8"))
            _cache = raw if isinstance(raw, dict) else {}
            _cache_mtime = mtime
            return _cache
        except Exception:
            return _cache or {}


def _save(data: dict) -> None:
    global _cache, _cache_mtime
    _STORE.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(_STORE.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, ensure_ascii=False)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, _STORE)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    with _lock:
        _cache, _cache_mtime = None, None


def set_exception(staff_code: str, day: str, reason_key: str, note: str,
                  by_code: str, by_name: str = "") -> dict:
    """Record why this person has no log for this day.

    `note` is REQUIRED for a reason that does not excuse the target: a deficit
    that will be acted upon must carry an explanation the person can answer.
    """
    reason_key = str(reason_key or "").strip()
    if not reason_key:
        raise ValueError("a reason is required")
    known = {str(r.get("key")) for r in reasons()}
    if reason_key not in known:
        raise ValueError(f"unknown reason {reason_key!r}")
    if not excuses_target(reason_key) and not str(note or "").strip():
        raise ValueError(
            "a note is required for a reason that still carries the day's target")

    data = _load()
    data = dict(data)
    rec = {
        "staff_code": str(staff_code).strip(),
        "date": str(day)[:10],
        "reason": reason_key,
        "excuses_target": excuses_target(reason_key),
        "note": str(note or "").strip(),
        "recorded_by": str(by_code or ""),
        "recorded_by_name": str(by_name or ""),
        "recorded_at": datetime.now().isoformat(),
    }
    data[_key(staff_code, day)] = rec
    _save(data)
    return rec


def clear_exception(staff_code: str, day: str) -> bool:
    data = dict(_load())
    k = _key(staff_code, day)
    if k not in data:
        return False
    data.pop(k)
    _save(data)
    return True


def exception_for(staff_code: str, day: str) -> Optional[dict]:
    return _load().get(_key(staff_code, day))


def is_excused(staff_code: str, day: str) -> bool:
    """True when this staff-day carries a reason that removes its target."""
    rec = exception_for(staff_code, day)
    return bool(rec and rec.get("excuses_target"))


def list_for_day(day: str) -> dict:
    """{staff_code: record} for one date."""
    d = str(day)[:10]
    return {v.get("staff_code"): v for k, v in _load().items()
            if isinstance(v, dict) and v.get("date") == d}
'''

EXCUSED_NEW = r'''def _excused(log: dict) -> bool:
    """True when this staff-day carries an exception that removes its target.

    An EXCUSED day behaves exactly like a rest day for that person: no target,
    no variance, skipped by the carried-forward walk. Refusal and "no
    explanation" do NOT excuse — see utils.branch_log_exceptions.
    """
    try:
        from utils.branch_log_exceptions import is_excused
        return is_excused(str(log.get("staff_code", "") or ""),
                          str(log.get("log_date", ""))[:10])
    except Exception:
        return False


'''

WT_NEW = r'''    if _excused(log):
        return 0.0
    try:
        from utils import workcal
        return float(workcal.target_weight(str(log.get("log_date", ""))[:10]))
    except Exception:
        return 1.0'''

CF_NEW = r'''            r["working_day"] = False
            # Distinguish "the bank was closed" from "this person was excused",
            # so the grid can say which and a manager is not left guessing.
            if _excused(r):
                try:
                    from utils.branch_log_exceptions import exception_for
                    exc = exception_for(str(r.get("staff_code", "") or ""),
                                        str(r.get("log_date", ""))[:10]) or {}
                except Exception:
                    exc = {}
                r["excused"] = True
                r["exception_reason"] = exc.get("reason", "")
                r["exception_note"] = exc.get("note", "")
            continue'''


WT_OLD = """    try:
        from utils import workcal
        return float(workcal.target_weight(str(log.get("log_date", ""))[:10]))
    except Exception:
        return 1.0"""

CF_OLD = """            r["working_day"] = False
            continue"""

AN_ANCHOR = "def _working_weight(log: dict) -> float:"


def main():
    apply = "--apply" in sys.argv
    if not os.path.isfile(AN):
        print("ABORT: %s not found. Run from the project root." % AN)
        return 1
    if os.path.exists(MOD):
        print("ABORT: %s already exists - E1 looks applied." % MOD)
        return 1

    an = open(AN, encoding="utf-8").read()
    if "_excused" in an:
        print("ABORT: analytics already has _excused.")
        return 1
    if "_working_weight" not in an:
        print("ABORT: apply patch_wc2b_wiring.py first (calendar weighting).")
        return 1
    for label, mark in (("weight body", WT_OLD), ("carried-forward skip", CF_OLD),
                        ("weight fn", AN_ANCHOR)):
        if an.count(mark) != 1:
            print("ABORT: %s anchor matched %d times (expected 1)."
                  % (label, an.count(mark)))
            return 1

    an = an.replace(AN_ANCHOR, EXCUSED_NEW + AN_ANCHOR, 1)
    an = an.replace(WT_OLD, WT_NEW, 1)
    an = an.replace(CF_OLD, CF_NEW, 1)
    print("  ok  analytics - _excused(), honoured by _working_weight")
    print("  ok  analytics - carried_forward surfaces excused/reason/note")

    if an.count("def _excused(") != 1:
        print("ABORT: post-check - _excused defined %d times." % an.count("def _excused("))
        return 1
    if an.count("if _excused(log):") != 1:
        print("ABORT: post-check - weight override not wired exactly once.")
        return 1
    for token in ("excuses_target", "os.replace", "_DEFAULT_REASONS"):
        if token not in MODULE:
            print("ABORT: embedded module missing %r." % token)
            return 1
    print("  ok  post-checks: one _excused, one weight override")

    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        return 0

    open(MOD, "w", encoding="utf-8", newline="").write(MODULE)
    print("CREATED %s" % MOD)
    shutil.copy2(AN, AN + BACKUP_SUFFIX)
    open(AN, "w", encoding="utf-8", newline="").write(an)
    print("APPLIED %s  (backup: %s)" % (AN, os.path.basename(AN) + BACKUP_SUFFIX))

    import py_compile
    for path in (MOD, AN):
        try:
            py_compile.compile(path, doraise=True)
            print("  ok  %s compiles" % os.path.basename(path))
        except Exception as exc:
            print("  FAIL %s: %s" % (path, exc))
            return 1

    print("\nNo endpoint yet - E2 exposes recording an exception. Restart uvicorn")
    print("so the analytics change is live for the grid and the queue.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
