"""
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
