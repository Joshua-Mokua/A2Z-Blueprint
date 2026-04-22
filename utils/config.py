"""utils/config.py — Centralised config loader.
All modules read thresholds, labels, and settings from org_config.json.
Never hard-code a threshold in a page — always use cfg("key", default).
"""
import json
import streamlit as st
from pathlib import Path

_CFG_PATH = Path(__file__).parent.parent / "data" / "org_config.json"

@st.cache_data(ttl=30, show_spinner=False)
def load_org_config() -> dict:
    """Load the full org config. Cached 30s."""
    try:
        return json.loads(_CFG_PATH.read_text())
    except Exception:
        return {}

def cfg(key: str, default=None):
    """Get a threshold or setting by key. Falls back to default."""
    org = load_org_config()
    val = org.get("thresholds", {}).get(key)
    if val is None:
        val = org.get("module_config", {}).get(key)
    return val if val is not None else default

def get_departments(active_only=True) -> list:
    """Return departments list from org_config."""
    org  = load_org_config()
    deps = org.get("departments", [])
    return [d for d in deps if not active_only or d.get("active", True)]

def get_dept_by_name(name: str) -> dict:
    """Return a department record by name."""
    for d in get_departments(active_only=False):
        if d["name"] == name:
            return d
    return {}

def get_branches(active_only=True, region=None) -> list:
    """Return branches, optionally filtered by region."""
    org = load_org_config()
    brs = org.get("branches", [])
    if active_only:
        brs = [b for b in brs if b.get("active", True)]
    if region:
        brs = [b for b in brs if b.get("region") == region]
    return sorted(brs, key=lambda x: x["name"])

def get_modules(active_only=True) -> list:
    """Return all module definitions."""
    org = load_org_config()
    mods = org.get("modules", [])
    return [m for m in mods if not active_only or m.get("active", True)]

def get_dept_modules(dept_id: str) -> list:
    """Return module keys assigned to a department."""
    org = load_org_config()
    return org.get("dept_module_assignments", {}).get(dept_id, [])

def get_roles() -> list:
    """Return roles library."""
    return load_org_config().get("roles", [])

def get_clusters() -> list:
    """Return cluster definitions."""
    return load_org_config().get("clusters", [])

def save_org_config(updated: dict):
    """Persist updated org config back to disk."""
    import datetime
    updated["_last_modified"] = str(datetime.date.today())
    _CFG_PATH.write_text(json.dumps(updated, indent=2, ensure_ascii=False))
    load_org_config.clear()  # bust the cache

def update_threshold(key: str, value):
    """Update a single threshold and save."""
    org = load_org_config()
    org.setdefault("thresholds", {})[key] = value
    save_org_config(org)

def update_dept_modules(dept_id: str, module_keys: list):
    """Update module assignments for a department."""
    org = load_org_config()
    org.setdefault("dept_module_assignments", {})[dept_id] = module_keys
    save_org_config(org)
