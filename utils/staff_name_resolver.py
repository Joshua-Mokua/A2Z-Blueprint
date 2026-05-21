"""utils/staff_name_resolver.py — v10.111.

Resolves full-name strings ("Stephen Shimba") to staff codes ("300217")
via the staff register (data/users.json). Some operational tables —
notably aml_alerts.assigned_to, incidents.assigned_to, and
agent_fraud_alerts.assigned_to — record the assignee as a full name
rather than a staff code, which made them unreachable to the v10.108-
v10.110 ownership pipeline (which keys on staff_code throughout).

USAGE
─────
    from utils.staff_name_resolver import name_to_code

    code = name_to_code("Stephen Shimba")        # → "300217"
    code = name_to_code(" Stephen  Shimba ")      # whitespace-tolerant
    code = name_to_code("STEPHEN SHIMBA")          # case-insensitive
    code = name_to_code("Nobody Here")             # → None (with metric)

DISAMBIGUATION
──────────────
When two staff share a full name (e.g., two "Mary Waweru" in different
units), name_to_code() returns None and increments the
`ambiguous_misses` counter. The deploying admin sees the warning in
the resolution-metrics report (surfaced in the Module Config Centre)
and disambiguates by adding the unit suffix to the operational table's
assignee field, or by editing users.json.

THE BOUNDARY
────────────
The name resolver is bank-DATA — its accuracy depends entirely on the
deploying bank's users.json being populated. The resolver itself is
universal (the lookup logic is the same at every bank). Following the
v10.110 boundary discipline:

  Hard-coded:    The lookup algorithm, normalization, disambiguation
                 rule, metrics counter, cache invalidation.
  Configurable:  data/users.json is the source of truth (per-bank
                 staff register).

PERFORMANCE
───────────
Lookup table built once on first call; cached at module level.
Invalidated via refresh_cache() — admins call this after editing
users.json.

METRICS
───────
get_resolution_metrics() returns a dict:
  {
    "lookups_total":      int,
    "lookups_hit":        int,
    "lookups_miss":       int,
    "ambiguous_misses":   int,    # name appears 2+ times in users.json
    "miss_examples":      list,   # last 20 missed names (for debugging)
  }
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional


logger = logging.getLogger(__name__)


# ─── Module-level cache ───────────────────────────────────────────────

# name (normalized lower-case stripped) → staff_code
# When a name is ambiguous (appears multiple times), we set the value
# to None so name_to_code can return None and raise the ambiguity
# counter.
_NAME_LOOKUP: Optional[dict[str, Optional[str]]] = None
_AMBIGUOUS: set[str] = set()

# Resolution metrics
_METRICS = {
    "lookups_total":     0,
    "lookups_hit":       0,
    "lookups_miss":      0,
    "ambiguous_misses":  0,
    "miss_examples":     [],   # last 20
}

_MISS_EXAMPLE_CAP = 20


def _users_json_path() -> Path:
    """Where data/users.json lives, regardless of cwd."""
    here = Path(__file__).resolve().parent
    return here.parent / "data" / "users.json"


def _normalize(name: str) -> str:
    """Strip outer whitespace, collapse internal whitespace, lower-case.
    Stable across small typing variations."""
    if not isinstance(name, str):
        return ""
    parts = name.strip().split()
    return " ".join(parts).lower()


def _build_lookup() -> dict[str, Optional[str]]:
    """Read users.json, build the name → code lookup. Detects
    ambiguous names (2+ users with the same normalized full_name).
    Caches the result at module level."""
    global _AMBIGUOUS
    path = _users_json_path()
    if not path.exists():
        logger.warning(
            f"staff_name_resolver: {path} not found; lookups will all "
            f"miss until users.json is provided")
        return {}

    try:
        with open(path, encoding="utf-8") as f:
            users = json.load(f)
    except Exception as e:
        logger.warning(
            f"staff_name_resolver: failed to read {path}: "
            f"{type(e).__name__}: {e}")
        return {}

    # users.json may be a dict (keyed by username) or a list. Handle both.
    if isinstance(users, dict):
        records = users.values()
    elif isinstance(users, list):
        records = users
    else:
        return {}

    counts: dict[str, int] = {}
    table: dict[str, Optional[str]] = {}
    for u in records:
        if not isinstance(u, dict):
            continue
        full_name = u.get("full_name")
        staff_code = u.get("staff_code")
        if not full_name or not staff_code:
            continue
        if not u.get("active", True):
            # Inactive users skipped — they shouldn't be assignees on
            # current operational records.
            continue
        key = _normalize(full_name)
        if not key:
            continue
        counts[key] = counts.get(key, 0) + 1
        if counts[key] == 1:
            table[key] = str(staff_code)
        else:
            # Second occurrence — mark ambiguous and clear the entry
            table[key] = None

    # Track which names are ambiguous so we can report
    _AMBIGUOUS = {k for k, n in counts.items() if n >= 2}
    return table


def _ensure_lookup() -> dict[str, Optional[str]]:
    global _NAME_LOOKUP
    if _NAME_LOOKUP is None:
        _NAME_LOOKUP = _build_lookup()
    return _NAME_LOOKUP


def refresh_cache() -> None:
    """Clear the name-lookup cache and the metrics. Call after admin
    edits users.json."""
    global _NAME_LOOKUP
    _NAME_LOOKUP = None
    _METRICS["lookups_total"] = 0
    _METRICS["lookups_hit"] = 0
    _METRICS["lookups_miss"] = 0
    _METRICS["ambiguous_misses"] = 0
    _METRICS["miss_examples"].clear()


def name_to_code(name: Optional[str]) -> Optional[str]:
    """Resolve a full name to staff_code. Returns None on miss
    (no match or ambiguous). Increments resolution metrics."""
    _METRICS["lookups_total"] += 1
    if not name:
        _METRICS["lookups_miss"] += 1
        return None
    table = _ensure_lookup()
    key = _normalize(name)
    if key in _AMBIGUOUS:
        _METRICS["ambiguous_misses"] += 1
        _METRICS["lookups_miss"] += 1
        if name not in _METRICS["miss_examples"]:
            _METRICS["miss_examples"].append(f"{name} (ambiguous)")
            if len(_METRICS["miss_examples"]) > _MISS_EXAMPLE_CAP:
                _METRICS["miss_examples"].pop(0)
        return None
    code = table.get(key)
    if code is None:
        _METRICS["lookups_miss"] += 1
        if name not in _METRICS["miss_examples"]:
            _METRICS["miss_examples"].append(name)
            if len(_METRICS["miss_examples"]) > _MISS_EXAMPLE_CAP:
                _METRICS["miss_examples"].pop(0)
        return None
    _METRICS["lookups_hit"] += 1
    return code


def get_resolution_metrics() -> dict:
    """Return current resolution metrics. The deploying admin views
    this in the Module Config Centre's Resolution Metrics tab to
    debug staff-register coverage."""
    return {
        "lookups_total":     _METRICS["lookups_total"],
        "lookups_hit":       _METRICS["lookups_hit"],
        "lookups_miss":      _METRICS["lookups_miss"],
        "ambiguous_misses":  _METRICS["ambiguous_misses"],
        "miss_examples":     list(_METRICS["miss_examples"]),
        "hit_rate_pct": (
            round(100.0 * _METRICS["lookups_hit"] / _METRICS["lookups_total"], 2)
            if _METRICS["lookups_total"] > 0 else 0.0),
    }


def get_known_ambiguous() -> set[str]:
    """The set of normalized names that appear 2+ times in
    users.json. Useful for admin-side reports recommending which
    operational tables need disambiguation."""
    _ensure_lookup()  # ensure built
    return set(_AMBIGUOUS)
