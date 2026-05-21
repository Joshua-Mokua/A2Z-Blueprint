"""utils/cascade_hierarchy.py — Bridge between v10.316 hierarchy
synthesis and the cascade page (pages/12_cascade.py) plus any other
caller that needs a role→children map.

Why this exists (v10.318):
  - pages/12_cascade.py uses an inverted "role: [parents]" config
    loaded from data/org_config.json
  - utils/hierarchy_synth.py uses a "staff_code: HierarchyLink" map
    keyed by individual staff
  - Both views are valid; this module bridges them so any caller can
    get the role→children map AND the staff-level hierarchy from a
    single import without duplicating logic.

Per Rule 7, this module is diagnostic — it reads org config and the
synthesised hierarchy, returns derived views. No source data mutation.

Shipped: v10.318.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Set


def _load_org_config_safe() -> Dict[str, Any]:
    """Load data/org_config.json directly via utils.db.load_json.

    Bypasses utils.core.get_org_config which has a hard dependency
    on streamlit. The cascade page itself uses utils.core
    (Streamlit context); this module is also called from audit
    gates and tests that may not have streamlit installed.
    """
    from pathlib import Path
    from utils.db import db
    path = Path(__file__).parent.parent / "data" / "org_config.json"
    try:
        return db.load_json(path, default={}) or {}
    except Exception:  # noqa: BLE001
        return {}


def role_children_map() -> Dict[str, List[str]]:
    """Return role → list of valid child roles.

    Reads from data/org_config.json's `hierarchy` key (admin-editable
    via the admin UI or direct JSON edit). The config stores
    `role: [parent_roles]`; this function inverts to
    `role: [child_roles]` so callers can find direct reports by role.

    Includes EVERY role mentioned (as key or value), so leaf roles
    like Teller appear as keys with empty lists.
    """
    cfg = _load_org_config_safe()
    raw = cfg.get("hierarchy", {}) or {}

    children: Dict[str, List[str]] = {}
    # First pass: ensure every role appears as a key
    for role in raw:
        children.setdefault(role, [])

    # Second pass: invert role:[parents] → parent:[children]
    for role, parents in raw.items():
        if not isinstance(parents, list):
            continue
        for parent in parents:
            children.setdefault(parent, [])
            if role not in children[parent]:
                children[parent].append(role)

    # Sort each children list for determinism
    for parent in children:
        children[parent].sort()

    return children


def role_root() -> Optional[str]:
    """Return the role with no parent — the org root.

    Walks role_children_map to find the role appearing as parent
    but never as child. Prefers names containing "managing" /
    "chief executive" if multiple roots exist.
    """
    children = role_children_map()
    if not children:
        return None
    all_children: Set[str] = set()
    for kids in children.values():
        for kid in kids:
            all_children.add(kid)
    roots = [r for r in children if r not in all_children]
    if not roots:
        return None
    preferred = [
        r for r in roots
        if "managing" in r.lower()
        or "chief executive" in r.lower()
    ]
    return (preferred[0] if preferred
            else sorted(roots)[0])


def direct_report_roles(role: str) -> List[str]:
    """Return the list of roles that report directly to `role`.

    Empty list if `role` isn't in the config or has no reports
    (e.g. a leaf role like Teller).
    """
    return role_children_map().get(role, [])


def cascade_chain_from_role(role: str) -> List[str]:
    """Walk upward from `role` through its parent chain to the root.

    Returns a list starting with `role` at index 0 and ending at
    the root. Stops at cycles or unresolved parents.
    """
    cfg = _load_org_config_safe()
    raw = cfg.get("hierarchy", {}) or {}
    if not raw:
        return [role]

    chain: List[str] = [role]
    seen: Set[str] = {role}
    current = role
    while current in raw and raw[current]:
        parents = raw[current]
        if not parents:
            break
        next_parent = parents[0]
        if next_parent in seen:
            break  # cycle guard
        chain.append(next_parent)
        seen.add(next_parent)
        current = next_parent
        if len(chain) > 15:
            break  # depth guard
    return chain


def md_direct_reports() -> List[str]:
    """Return roles that report directly to the MD/root.

    Equivalent to `direct_report_roles(role_root())` but handled
    cleanly when no root is configured.
    """
    root = role_root()
    if not root:
        return []
    return direct_report_roles(root)


SPEC_DEVIATION_NOTE = (
    "Per Rule 7, this module is diagnostic. It reads "
    "data/org_config.json (via utils.core.get_org_config) and "
    "returns derived role-hierarchy views. It does NOT mutate the "
    "config file or any source data. Edits to org_config.json "
    "(specifically the `hierarchy` key) flow through here on next "
    "call — no caching, no restart needed."
)
