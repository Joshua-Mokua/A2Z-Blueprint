"""utils/kpi_ownership.py — v10.108 Integration Layer.

The single ownership contract every autofit aggregator queries before
submitting an actual to bsc_engine. A staff is "owned" by a KPI for a
given period iff EITHER:

    (a) The KPI is in role_kpis[staff.role]  — role-default ownership
                                                (no cascade lock needed)
    (b) The KPI is cascade-locked for staff in period — cascade-allocated
                                                ownership (lock required)

The union is intentional: a Branch Manager's role gives them a standing
set of KPIs (AML compliance, training hours, etc.) that don't require a
cascade allocation; cascade-allocated KPIs are added on top once the
target is locked. Cascade lock gates the cascade portion only.

Cascade lock signal lives in `data/target_cascade.json` as records keyed
`deadline|<staff_code>|<period>` with `targets_locked: true`.

Role lookup uses `data/users.json` (staff_code → role) and
`data/kpi_library.json::role_kpis` (role → list of KPI codes/ids).

Public API:
    is_kpi_owned_by_staff(staff_code, kpi, period) -> bool
    owned_kpis_for_staff(staff_code, period) -> set[str]
    is_cascade_locked(staff_code, period) -> bool

The ``kpi`` argument may be a library id, code, or alias — it is
resolved through the same index that ``bsc_engine._load_kpi_index``
builds. This means cascade names like "Loan Book Growth" and engine
codes like "LOAN_GROWTH" both work.
"""
from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


# ─── Path resolution ────────────────────────────────────────────────────

def _data_dir() -> Path:
    """Resolve the repo's data/ directory regardless of cwd."""
    here = Path(__file__).resolve().parent
    return here.parent / "data"


# ─── Cached loaders ─────────────────────────────────────────────────────
#
# These caches are mtime-invalidated via the helper below so that hot
# pages picking up an admin-panel KPI library edit don't need a process
# restart. Tests can call _refresh_caches() explicitly.

_users_cache: dict = {}
_users_mtime: float = 0.0
_lib_cache: dict = {}
_lib_mtime: float = 0.0
_cascade_cache: dict = {}
_cascade_mtime: float = 0.0


def _load_json_with_cache(path: Path, cache_dict: dict, cache_mtime: float):
    """Reload `path` if the file has changed; otherwise return cached."""
    try:
        mtime = path.stat().st_mtime
    except FileNotFoundError:
        return {}, 0.0

    if cache_dict and mtime == cache_mtime:
        return cache_dict, cache_mtime

    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data, mtime
    except Exception as e:
        logger.warning(f"_load_json_with_cache({path}): {e}")
        return cache_dict or {}, cache_mtime


def _get_users() -> dict:
    global _users_cache, _users_mtime
    _users_cache, _users_mtime = _load_json_with_cache(
        _data_dir() / "users.json", _users_cache, _users_mtime)
    return _users_cache


def _get_library() -> dict:
    global _lib_cache, _lib_mtime
    _lib_cache, _lib_mtime = _load_json_with_cache(
        _data_dir() / "kpi_library.json", _lib_cache, _lib_mtime)
    return _lib_cache


def _get_cascade() -> dict:
    global _cascade_cache, _cascade_mtime
    _cascade_cache, _cascade_mtime = _load_json_with_cache(
        _data_dir() / "target_cascade.json",
        _cascade_cache, _cascade_mtime)
    return _cascade_cache


def _refresh_caches() -> None:
    """Force reload on next access. Used by tests."""
    global _users_cache, _users_mtime
    global _lib_cache, _lib_mtime
    global _cascade_cache, _cascade_mtime
    _users_cache, _users_mtime = {}, 0.0
    _lib_cache, _lib_mtime = {}, 0.0
    _cascade_cache, _cascade_mtime = {}, 0.0


# ─── KPI key normalisation ──────────────────────────────────────────────

def _normalise_kpi_key(kpi: str) -> str:
    """Resolve a KPI reference (id, code, name, or alias) to its
    canonical engine code. Returns the code if found, else returns the
    input unchanged so callers can still compare against role_kpis lists
    that might contain non-canonical entries."""
    if not kpi:
        return ""
    lib = _get_library()
    target = str(kpi).strip()

    for entry in lib.get("kpis", []) or []:
        # Direct match on id, code, name, or any alias
        if (entry.get("id") == target or
                entry.get("code") == target or
                entry.get("name") == target or
                target in (entry.get("aliases", []) or [])):
            # Prefer code (the engine's identifier) when available;
            # fall back to id (which equals the cascade name for
            # v10.107 reconciliation entries).
            return entry.get("code") or entry.get("id") or target
    return target


# ─── Role-based ownership ───────────────────────────────────────────────

def _staff_role(staff_code: str) -> Optional[str]:
    """Look up the role for a staff_code via users.json."""
    if not staff_code:
        return None
    sc = str(staff_code).strip()
    for user in _get_users().values():
        if isinstance(user, dict) and str(user.get("staff_code", "")) == sc:
            return user.get("role")
    return None


def _role_kpis_for(role: str) -> set[str]:
    """Return the set of KPI codes assigned to `role`. Each entry is
    normalised through the library so role_kpis lists referencing
    legacy IDs still resolve."""
    if not role:
        return set()
    lib = _get_library()
    raw = lib.get("role_kpis", {}).get(role, []) or []
    return {_normalise_kpi_key(k) for k in raw if k}


def _kpi_in_role(staff_code: str, kpi_code: str) -> bool:
    """True iff the KPI (canonical code) is in the staff's role's
    role_kpis list."""
    role = _staff_role(staff_code)
    if not role:
        return False
    return kpi_code in _role_kpis_for(role)


# ─── Cascade-based ownership ────────────────────────────────────────────

def is_cascade_locked(staff_code: str, period: str) -> bool:
    """True iff the cascade has a `deadline|staff|period` record with
    `targets_locked: true` for this (staff, period) pair.

    Cascade lock is the gate: until the staff confirms their cascaded
    targets, the autofit pipeline does NOT submit cascade-allocated
    KPIs — only role-default ones. This prevents pre-confirmation
    actuals from polluting the BSC.
    """
    if not staff_code or not period:
        return False
    cascade = _get_cascade()
    key = f"deadline|{staff_code}|{period}"
    record = cascade.get(key)
    if not isinstance(record, dict):
        return False
    return bool(record.get("targets_locked"))


def _cascade_kpis_for(staff_code: str, period: str) -> set[str]:
    """Return the set of KPI codes the cascade has allocated to this
    staff for this period, normalised. Empty if cascade is not locked.

    Walks every cascade allocation entry and collects ones where
    `staff_code` appears as a `to_code`.
    """
    if not is_cascade_locked(staff_code, period):
        return set()
    cascade = _get_cascade()
    sc = str(staff_code).strip()
    p = str(period).strip()
    owned: set[str] = set()

    for key, rec in cascade.items():
        if not isinstance(rec, dict):
            continue
        if "kpi" not in rec:
            continue
        if str(rec.get("period", "")) != p:
            continue
        for alloc in rec.get("allocations", []) or []:
            if str(alloc.get("to_code", "")) == sc:
                kpi_name = rec.get("kpi", "")
                code = _normalise_kpi_key(kpi_name)
                if code:
                    owned.add(code)
                break
    return owned


# ─── Public API ─────────────────────────────────────────────────────────

def is_kpi_owned_by_staff(staff_code: str, kpi, period: str) -> bool:
    """The ownership contract.

    Returns True iff this staff owns this KPI for this period. The KPI
    can be referenced by id, code, name, or alias; normalisation is
    handled internally.

    Ownership = (KPI in role_kpis[staff.role])
                OR (cascade-locked for staff in period AND KPI in
                    staff's cascade allocations).

    Empty inputs -> False (defensive: never accidentally claim ownership).
    """
    if not staff_code or not kpi or not period:
        return False
    code = _normalise_kpi_key(kpi)
    if not code:
        return False

    # Path (a): role-default — no lock required
    if _kpi_in_role(staff_code, code):
        return True

    # Path (b): cascade-allocated — lock required
    if code in _cascade_kpis_for(staff_code, period):
        return True

    return False


def owned_kpis_for_staff(staff_code: str, period: str) -> set[str]:
    """The full set of KPI codes this staff owns for this period.

    Useful for batch operations (e.g. dashboard rendering) that need
    every owned KPI rather than checking one at a time.
    """
    if not staff_code or not period:
        return set()
    role_set = set()
    role = _staff_role(staff_code)
    if role:
        role_set = _role_kpis_for(role)
    cascade_set = _cascade_kpis_for(staff_code, period)
    return role_set | cascade_set
