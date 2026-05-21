"""utils/canonical_admin.py — Canonical hierarchy admin operations (LEAF MODULE).

Per Joshua's directive: "the reporting lines can be set from the admin".

This module wraps read/write operations on:
- data/org_hierarchy_config.json::role_manager_whitelist
- data/org_hierarchy_config.json::role_tiers
- data/org_hierarchy_config.json::branch_tier_threshold

Used by pages/_admin_canonical.py for the UI; also callable from scripts for
batch operations. Single source of truth for canonical hierarchy changes.

LEAF MODULE: zero upward utils.* imports. Stdlib only.

Shipped: v10.400.
"""

from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

__all__ = [
    "load_canonical",
    "save_canonical",
    "list_role_managers",
    "list_role_tiers",
    "get_branch_tier_threshold",
    "set_role_managers",
    "remove_role",
    "set_role_tier",
    "set_branch_tier_threshold",
    "regenerate_cascade_from_canonical",
    "validate_canonical",
    "log_change",
    "read_change_log",
    "DEFAULT_BRANCH_TIER_THRESHOLD",
]

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
CONFIG_PATH = DATA_DIR / "org_hierarchy_config.json"
CHANGE_LOG_PATH = DATA_DIR / "canonical_change_log.json"
DEFAULT_BRANCH_TIER_THRESHOLD = 4

# ────────────────────────────────────────────────────────────────────
# Load / Save
# ────────────────────────────────────────────────────────────────────

def load_canonical() -> Dict[str, Any]:
    """Load org_hierarchy_config.json."""
    if not CONFIG_PATH.exists():
        return {"role_manager_whitelist": {}, "role_tiers": {}}
    try:
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"role_manager_whitelist": {}, "role_tiers": {}}


def save_canonical(cfg: Dict[str, Any], *, who: str = "admin",
                   reason: str = "manual edit") -> bool:
    """Save canonical config with auto-backup + provenance.

    Backs up existing file before writing. Returns True on success.
    """
    if not isinstance(cfg, dict):
        return False
    try:
        # Backup prior
        if CONFIG_PATH.exists():
            backup_dir = DATA_DIR / "_canonical_backups"
            backup_dir.mkdir(parents=True, exist_ok=True)
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            shutil.copy(CONFIG_PATH, backup_dir / f"org_hierarchy_config.{ts}.before.json")

        # Stamp last-modified into config itself
        cfg.setdefault("_canonical_admin_meta", {})
        cfg["_canonical_admin_meta"]["last_modified"] = datetime.now().isoformat()
        cfg["_canonical_admin_meta"]["last_modified_by"] = who
        cfg["_canonical_admin_meta"]["last_reason"] = reason

        CONFIG_PATH.write_text(
            json.dumps(cfg, indent=2, ensure_ascii=False),
            encoding="utf-8"
        )
        return True
    except Exception:
        return False


# ────────────────────────────────────────────────────────────────────
# Read helpers (return clean dicts without meta keys)
# ────────────────────────────────────────────────────────────────────

def _clean(d: Dict[str, Any]) -> Dict[str, Any]:
    """Drop keys starting with underscore."""
    return {k: v for k, v in d.items() if not k.startswith("_")}


def list_role_managers() -> Dict[str, List[str]]:
    """Return role_manager_whitelist: {role: [valid_managers]}."""
    cfg = load_canonical()
    rmw = cfg.get("role_manager_whitelist", {})
    return {k: list(v) for k, v in _clean(rmw).items() if isinstance(v, list)}


def list_role_tiers() -> Dict[str, int]:
    """Return role_tiers: {role: tier_int}."""
    cfg = load_canonical()
    tiers = cfg.get("role_tiers", {})
    return {k: int(v) for k, v in _clean(tiers).items()
            if isinstance(v, (int, float))}


def get_branch_tier_threshold() -> int:
    """Return branch_tier_threshold (default 4)."""
    cfg = load_canonical()
    try:
        return int(cfg.get("branch_tier_threshold", DEFAULT_BRANCH_TIER_THRESHOLD))
    except (TypeError, ValueError):
        return DEFAULT_BRANCH_TIER_THRESHOLD


# ────────────────────────────────────────────────────────────────────
# Mutators
# ────────────────────────────────────────────────────────────────────

def set_role_managers(role: str, managers: List[str], *,
                      who: str = "admin", reason: str = "") -> bool:
    """Set canonical managers for a role. Empty list clears the entry."""
    if not role or not isinstance(role, str):
        return False
    cfg = load_canonical()
    cfg.setdefault("role_manager_whitelist", {})
    old = cfg["role_manager_whitelist"].get(role, [])
    if managers:
        cfg["role_manager_whitelist"][role] = [m for m in managers if isinstance(m, str) and m]
    else:
        cfg["role_manager_whitelist"].pop(role, None)
    log_change(who, "set_role_managers", role,
               old, managers, reason)
    return save_canonical(cfg, who=who, reason=reason or f"set managers for {role}")


def remove_role(role: str, *, who: str = "admin", reason: str = "") -> bool:
    """Remove a role from BOTH role_manager_whitelist AND role_tiers."""
    if not role:
        return False
    cfg = load_canonical()
    rmw_had = role in cfg.get("role_manager_whitelist", {})
    tiers_had = role in cfg.get("role_tiers", {})
    cfg.get("role_manager_whitelist", {}).pop(role, None)
    cfg.get("role_tiers", {}).pop(role, None)
    log_change(who, "remove_role", role,
               {"in_rmw": rmw_had, "in_tiers": tiers_had}, None, reason)
    return save_canonical(cfg, who=who, reason=reason or f"remove role {role}")


def set_role_tier(role: str, tier: int, *,
                  who: str = "admin", reason: str = "") -> bool:
    """Set role tier (0..6). Tier 0 = MD root, 4+ = branch-level."""
    if not role or not isinstance(tier, int) or tier < 0 or tier > 9:
        return False
    cfg = load_canonical()
    cfg.setdefault("role_tiers", {})
    old = cfg["role_tiers"].get(role)
    cfg["role_tiers"][role] = tier
    log_change(who, "set_role_tier", role, old, tier, reason)
    return save_canonical(cfg, who=who,
                          reason=reason or f"set tier {tier} for {role}")


def set_branch_tier_threshold(threshold: int, *,
                              who: str = "admin", reason: str = "") -> bool:
    """Set branch_tier_threshold (typically 4)."""
    if not isinstance(threshold, int) or threshold < 0 or threshold > 9:
        return False
    cfg = load_canonical()
    old = cfg.get("branch_tier_threshold", DEFAULT_BRANCH_TIER_THRESHOLD)
    cfg["branch_tier_threshold"] = threshold
    log_change(who, "set_branch_tier_threshold", "<global>",
               old, threshold, reason)
    return save_canonical(cfg, who=who,
                          reason=reason or f"set threshold {threshold}")


# ────────────────────────────────────────────────────────────────────
# Cascade regeneration (calls regenerator)
# ────────────────────────────────────────────────────────────────────

def regenerate_cascade_from_canonical(*, who: str = "admin",
                                       reason: str = "",
                                       preserve_manual: bool = True
                                       ) -> Tuple[bool, int, str]:
    """Re-run cascade_regenerator using current canonical.

    v10.404: preserve_manual defaults to True (per Joshua F4) — admin regen
    keeps manager-set manual allocations intact; only fills in gaps from
    canonical. Pass preserve_manual=False for full rebuild.

    Returns (success, entries_count, message).
    """
    try:
        # Import the regenerator (not a leaf import — we're a sibling utility)
        # Caller must ensure utils.cascade_regenerator is importable
        import importlib
        for mod_name in ("utils.cascade_regenerator", "utils.cascade_structure_engine"):
            if mod_name in __import__('sys').modules:
                importlib.reload(__import__('sys').modules[mod_name])
        regen_mod = importlib.import_module("utils.cascade_regenerator")
        new_cascade = regen_mod.regenerate_target_cascade(
            write=True, preserve_manual=preserve_manual
        )
        count = sum(1 for k in new_cascade.keys()
                   if not k.startswith("_") and "|" in k)
        manual_preserved = sum(
            1 for k, v in new_cascade.items()
            if isinstance(v, dict) and v.get("_v10404_manual")
        )
        log_change(who, "regenerate_cascade", "<cascade>",
                   None, {"count": count, "preserve_manual": preserve_manual,
                          "manual_preserved": manual_preserved}, reason)
        msg = (f"Regenerated {count} cascade entries "
               f"({manual_preserved} manual entries preserved)"
               if preserve_manual else
               f"Force-rebuilt {count} cascade entries (manual entries overwritten)")
        return True, count, msg
    except Exception as exc:
        return False, 0, f"Regeneration failed: {type(exc).__name__}: {exc}"


# ────────────────────────────────────────────────────────────────────
# Validation
# ────────────────────────────────────────────────────────────────────

def validate_canonical() -> Dict[str, Any]:
    """Validate canonical for common issues.

    Returns dict with 'valid' bool and 'issues' list.
    """
    issues: List[str] = []
    cfg = load_canonical()
    rmw = _clean(cfg.get("role_manager_whitelist", {}))
    tiers = _clean(cfg.get("role_tiers", {}))

    # 1. Every role in rmw has at least one manager
    for role, mgrs in rmw.items():
        if not isinstance(mgrs, list) or not mgrs:
            issues.append(f"Role '{role}' has empty manager list")

    # 2. Manager roles referenced should ideally exist in tiers (warn only)
    referenced_managers = set()
    for mgrs in rmw.values():
        if isinstance(mgrs, list):
            referenced_managers.update(m for m in mgrs if isinstance(m, str))

    for mgr in referenced_managers:
        if mgr not in tiers:
            issues.append(
                f"Manager role '{mgr}' referenced in canonical "
                f"but has no tier defined"
            )

    # 3. Tier sanity: subordinate tier should be >= manager tier
    for role, mgrs in rmw.items():
        sub_tier = tiers.get(role)
        if sub_tier is None:
            continue
        for mgr in mgrs:
            mgr_tier = tiers.get(mgr)
            if mgr_tier is None:
                continue
            if mgr_tier > sub_tier:
                issues.append(
                    f"Tier inversion: {role} (tier {sub_tier}) reports to "
                    f"{mgr} (tier {mgr_tier})"
                )

    # 4. Detect cycles in canonical (manager → reports back to)
    cycles = _find_cycles(rmw)
    for cyc in cycles:
        issues.append(f"Cycle in canonical: {' → '.join(cyc)}")

    return {
        "valid": len(issues) == 0,
        "issues": issues,
        "role_count": len(rmw),
        "tier_count": len(tiers),
    }


def _find_cycles(rmw: Dict[str, List[str]]) -> List[List[str]]:
    """Simple cycle detection in role_manager_whitelist."""
    cycles: List[List[str]] = []
    visited_global: set = set()

    def dfs(role: str, path: List[str]):
        if role in path:
            i = path.index(role)
            cycles.append(path[i:] + [role])
            return
        if role in visited_global:
            return
        new_path = path + [role]
        managers = rmw.get(role, [])
        if isinstance(managers, list):
            for m in managers:
                if isinstance(m, str):
                    dfs(m, new_path)
        visited_global.add(role)

    for role in list(rmw.keys()):
        dfs(role, [])
    return cycles


# ────────────────────────────────────────────────────────────────────
# Change log
# ────────────────────────────────────────────────────────────────────

def log_change(who: str, action: str, target: str,
               old_value: Any, new_value: Any, reason: str = "") -> bool:
    """Append a change to the canonical change log."""
    try:
        log = read_change_log()
        log.append({
            "ts": datetime.now().isoformat(),
            "who": str(who) if who else "?",
            "action": str(action),
            "target": str(target) if target else "",
            "old": old_value,
            "new": new_value,
            "reason": str(reason) if reason else "",
        })
        # Keep last 1000 entries
        if len(log) > 1000:
            log = log[-1000:]
        CHANGE_LOG_PATH.write_text(
            json.dumps(log, indent=2, ensure_ascii=False, default=str),
            encoding="utf-8"
        )
        return True
    except Exception:
        return False


def read_change_log(limit: int = 50) -> List[Dict[str, Any]]:
    """Return recent change log entries (newest last)."""
    if not CHANGE_LOG_PATH.exists():
        return []
    try:
        data = json.loads(CHANGE_LOG_PATH.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return data[-limit:] if limit else data
    except Exception:
        pass
    return []


# ────────────────────────────────────────────────────────────────────
# Self-test
# ────────────────────────────────────────────────────────────────────

def self_test() -> int:
    """In-place sanity tests."""
    tests = 0

    cfg = load_canonical()
    assert isinstance(cfg, dict)
    tests += 1

    rmw = list_role_managers()
    assert isinstance(rmw, dict)
    assert len(rmw) > 0, "canonical should not be empty"
    tests += 1

    tiers = list_role_tiers()
    assert isinstance(tiers, dict)
    tests += 1

    threshold = get_branch_tier_threshold()
    assert isinstance(threshold, int)
    assert 0 <= threshold <= 9
    tests += 1

    validation = validate_canonical()
    assert "valid" in validation
    assert isinstance(validation["issues"], list)
    tests += 1

    log = read_change_log()
    assert isinstance(log, list)
    tests += 1

    print(f"✓ canonical_admin self_test passed ({tests} tests)")
    print(f"  Role mappings:           {len(rmw)}")
    print(f"  Role tiers:              {len(tiers)}")
    print(f"  Branch tier threshold:   {threshold}")
    print(f"  Canonical valid:         {validation['valid']}")
    if not validation["valid"]:
        print(f"  Issues ({len(validation['issues'])}):")
        for issue in validation["issues"][:5]:
            print(f"    - {issue}")
    print(f"  Change log entries:      {len(log)}")
    return tests


if __name__ == "__main__":
    self_test()
