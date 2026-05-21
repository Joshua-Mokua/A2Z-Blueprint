"""utils/staff_role_resolver.py — v10.113.

Resolves role titles ("Agency Banking Manager") to staff codes via the
staff register at `data/users.json::role`. Some operational tables
record assignees by role rather than by name — agent_fraud_alerts is
the headline example, where every record is assigned to the abstract
"Agency Banking Manager" position regardless of who actually holds it.

This is a structurally different problem from name resolution
(`utils/staff_name_resolver.py`):

  Name resolution:    1 name → 0 or 1 staff_code (one specific person)
                      Returns None on miss or ambiguity.

  Role resolution:    1 role title → 0, 1, or N staff_codes (the
                      population currently holding that role).
                      For BSC actuals submission we need ONE staff
                      code per (role, alert) pair, so we pick the
                      single canonical holder from admin config when
                      there are multiple.

DESIGN — THREE RESOLUTION LAYERS
─────────────────────────────────
Priority order (highest first):

  1. **Admin-pinned mapping** — `role_to_staff_code` in
     integration_layer_config.json::agent_alerts_config maps a role
     title directly to one specific staff_code. Useful when the bank
     wants a specific person to own the alerts permanently regardless
     of the role-population on a given day.

  2. **Role-alias normalization** — `role_aliases` in
     integration_layer_config.json maps the operational-table label
     to the staff-register label ("Agency Banking Manager" →
     "Manager Agency Banking"). Then we look up users with that
     normalized role.

  3. **Direct role match** — look up the role title verbatim in
     users.json. If exactly one active user holds it, use that
     staff_code. If multiple, return None (admin must pin).

If all three fail, return None and increment the resolution metric
counter.

THE BOUNDARY
────────────
Hard-coded:    The 3-layer resolution algorithm + metrics counter.
Configurable:  role_to_staff_code, role_aliases (per-bank deployment
               via Module Config Centre).

PERFORMANCE
───────────
Lookup table built once on first call. Invalidated via refresh_cache()
after admin saves.

METRICS
───────
get_resolution_metrics() returns a dict with the same shape as the
name resolver's metrics (lookups_total/hit/miss/ambiguous_misses/
miss_examples/hit_rate_pct), plus `resolved_via` breakdown showing
which of the 3 layers handled each hit.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional


logger = logging.getLogger(__name__)


# ─── Module-level cache ───────────────────────────────────────────────

_ROLE_TABLE: Optional[dict[str, list[str]]] = None    # role → [staff_codes]
_ALIASES: Optional[dict[str, str]] = None              # opl_role → register_role
_PINNED: Optional[dict[str, str]] = None               # role → staff_code

_METRICS = {
    "lookups_total":    0,
    "lookups_hit":      0,
    "lookups_miss":     0,
    "ambiguous_misses": 0,
    "miss_examples":    [],
    "resolved_via":     {"pinned": 0, "alias": 0, "direct": 0},
}

_MISS_EXAMPLE_CAP = 20


def _data_dir() -> Path:
    here = Path(__file__).resolve().parent
    return here.parent / "data"


def _normalize(role: str) -> str:
    """Strip + collapse whitespace + lower-case. Stable across small
    typing variations."""
    if not isinstance(role, str):
        return ""
    return " ".join(role.strip().split()).lower()


def _build_role_table() -> dict[str, list[str]]:
    """Read users.json and build {normalized_role → [staff_codes]}.
    Includes only active users."""
    path = _data_dir() / "users.json"
    if not path.exists():
        logger.warning(
            f"staff_role_resolver: {path} not found")
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            users = json.load(f)
    except Exception as e:
        logger.warning(
            f"staff_role_resolver: failed to read {path}: {e}")
        return {}

    if isinstance(users, dict):
        records = users.values()
    elif isinstance(users, list):
        records = users
    else:
        return {}

    table: dict[str, list[str]] = {}
    for u in records:
        if not isinstance(u, dict):
            continue
        if not u.get("active", True):
            continue
        role = u.get("role")
        sc = u.get("staff_code")
        if not role or not sc:
            continue
        key = _normalize(role)
        if not key:
            continue
        table.setdefault(key, []).append(str(sc))
    return table


def _load_admin_config() -> tuple[dict[str, str], dict[str, str]]:
    """Read role_aliases and role_to_staff_code (under
    `agent_alerts_config`) from integration_layer_config.json.
    Returns ({normalized_alias → normalized_target},
             {normalized_role → staff_code})."""
    path = _data_dir() / "integration_layer_config.json"
    if not path.exists():
        return {}, {}
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        logger.warning(f"staff_role_resolver: config load failed: {e}")
        return {}, {}

    cfg = data.get("agent_alerts_config", {}) or {}
    aliases_raw = cfg.get("role_aliases", {}) or {}
    pinned_raw = cfg.get("role_to_staff_code", {}) or {}

    # Normalize keys so case/whitespace doesn't matter
    aliases = {_normalize(k): _normalize(v)
               for k, v in aliases_raw.items() if k and v}
    pinned = {_normalize(k): str(v).strip()
              for k, v in pinned_raw.items() if k and v}
    return aliases, pinned


def _ensure_caches() -> None:
    global _ROLE_TABLE, _ALIASES, _PINNED
    if _ROLE_TABLE is None:
        _ROLE_TABLE = _build_role_table()
    if _ALIASES is None or _PINNED is None:
        _ALIASES, _PINNED = _load_admin_config()


def refresh_cache() -> None:
    """Clear the role/alias/pinned caches and reset metrics."""
    global _ROLE_TABLE, _ALIASES, _PINNED
    _ROLE_TABLE = None
    _ALIASES = None
    _PINNED = None
    _METRICS["lookups_total"] = 0
    _METRICS["lookups_hit"] = 0
    _METRICS["lookups_miss"] = 0
    _METRICS["ambiguous_misses"] = 0
    _METRICS["miss_examples"].clear()
    for k in _METRICS["resolved_via"]:
        _METRICS["resolved_via"][k] = 0


def role_to_code(role: Optional[str]) -> Optional[str]:
    """Resolve a role title to a single staff_code via the 3-layer
    chain (admin-pinned → alias-normalized → direct match). Returns
    None on miss or ambiguity."""
    _METRICS["lookups_total"] += 1
    if not role:
        _METRICS["lookups_miss"] += 1
        return None
    _ensure_caches()
    key = _normalize(role)

    # Layer 1: admin-pinned mapping
    if key in _PINNED:
        _METRICS["lookups_hit"] += 1
        _METRICS["resolved_via"]["pinned"] += 1
        return _PINNED[key]

    # Layer 2: alias-normalized lookup
    if key in _ALIASES:
        normalized_target = _ALIASES[key]
        codes = _ROLE_TABLE.get(normalized_target, [])
        if len(codes) == 1:
            _METRICS["lookups_hit"] += 1
            _METRICS["resolved_via"]["alias"] += 1
            return codes[0]
        if len(codes) > 1:
            _METRICS["ambiguous_misses"] += 1
            _METRICS["lookups_miss"] += 1
            _record_miss_example(
                f"{role} (alias→{normalized_target}, ambiguous: "
                f"{len(codes)} holders)")
            return None
        # Alias resolves to no users — fall through to direct
        # (defensive)

    # Layer 3: direct match
    codes = _ROLE_TABLE.get(key, [])
    if len(codes) == 1:
        _METRICS["lookups_hit"] += 1
        _METRICS["resolved_via"]["direct"] += 1
        return codes[0]
    if len(codes) > 1:
        _METRICS["ambiguous_misses"] += 1
        _METRICS["lookups_miss"] += 1
        _record_miss_example(
            f"{role} (ambiguous: {len(codes)} holders — pin via admin)")
        return None

    # Total miss
    _METRICS["lookups_miss"] += 1
    _record_miss_example(role)
    return None


def _record_miss_example(label: str) -> None:
    if label not in _METRICS["miss_examples"]:
        _METRICS["miss_examples"].append(label)
        if len(_METRICS["miss_examples"]) > _MISS_EXAMPLE_CAP:
            _METRICS["miss_examples"].pop(0)


def get_resolution_metrics() -> dict:
    """Return current resolution metrics. The deploying admin views
    this in the Module Config Centre's Resolution Metrics tab to
    debug role-pinning gaps."""
    total = _METRICS["lookups_total"]
    return {
        "lookups_total":     total,
        "lookups_hit":       _METRICS["lookups_hit"],
        "lookups_miss":      _METRICS["lookups_miss"],
        "ambiguous_misses":  _METRICS["ambiguous_misses"],
        "miss_examples":     list(_METRICS["miss_examples"]),
        "resolved_via":      dict(_METRICS["resolved_via"]),
        "hit_rate_pct": (
            round(100.0 * _METRICS["lookups_hit"] / total, 2)
            if total > 0 else 0.0),
    }


def get_known_roles() -> set[str]:
    """All distinct active-staff roles in the register. Useful for
    admin UI suggestions."""
    _ensure_caches()
    return set(_ROLE_TABLE.keys())
