"""utils/admin_registry.py — Generic module config plug-in pattern.

Lets any module register its admin configuration declaratively. The
Module Config Centre then renders all registered modules consistently —
no copy-paste form code, no scattered tabs.

USAGE
-----
from utils.admin_registry import register_module_config

register_module_config({
    "module_id":     "rms",
    "title":         "Reconciliation Management System",
    "icon":          "🔄",
    "category":      "operations",
    "config_path":   "proposition_config.json",
    "config_key":    "rms_config",
    "tabs": [
        {
            "name": "Recon Types",
            "fields": [
                {"type":"text_area_list", "key":"recon_types",
                 "label":"Recon types (one per line)", "height":180},
            ],
            "save_label":   "Save types",
            "audit_action": "RMS_TYPES_UPDATED",
        },
    ],
    "hardcoded_caption": "Methodology, escalation rules, audit trail.",
})

CONVENTION
----------
All module-specific admin configurations should use this pattern.
See docs/ADMIN_CONVENTIONS.md for the full convention.
"""
from __future__ import annotations
import logging
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger("a2z.admin_registry")

DATA = Path(__file__).parent.parent / "data"

# Module categories — used to group cards in the Module Config Centre
CATEGORIES = {
    "operations":  "🔧 Operations",
    "credit":      "💼 Credit",
    "treasury":    "💹 Treasury & Finance",
    "risk":        "🛡️ Risk & Compliance",
    "people":      "👥 People",
    "data":        "📁 Data & Documents",
    "strategy":    "🎯 Strategy",
    "integration": "🔌 Integration",
}

# Field types supported by the renderer
FIELD_TYPES = {
    "text_input":      "Single-line text",
    "text_area":       "Multi-line text",
    "text_area_list":  "Multi-line text, treated as list (split on newlines)",
    "number_input":    "Numeric input (int or float)",
    "multiselect":     "Pick multiple from options",
    "selectbox":       "Pick one from options",
    "checkbox":        "Boolean toggle",
    "dict_editor":     "Key→number map (e.g. SLA days, retention years)",
    "readonly_table":  "DataFrame shown but not editable",
    "bullet_list":     "Static bullet list display",
    "rich_caption":    "Markdown caption",
}

# Global registry — modules register themselves at import time
_REGISTRY: Dict[str, Dict[str, Any]] = {}


def register_module_config(spec: Dict[str, Any]) -> None:
    """Register a module configuration spec.

    Required spec keys:
      module_id:    unique slug (e.g. "rms", "edms")
      title:        human-readable title
      icon:         emoji icon for the card
      category:     one of CATEGORIES keys
      config_path:  JSON file path (relative to data/ or absolute)
      config_key:   key inside the JSON for this module config
      tabs:         list of tab specs

    Optional:
      hardcoded_caption: text describing what is hardcoded
      access_roles:      list of roles allowed (default: admin only)
      page_link:         "65_propositions.py" — link to the operational page
    """
    # Validate required keys
    required = ["module_id", "title", "icon", "category", "config_path",
                 "config_key", "tabs"]
    for k in required:
        if k not in spec:
            raise ValueError(f"register_module_config: missing required key {k!r}")

    if spec["category"] not in CATEGORIES:
        logger.warning(f"Unknown category {spec['category']!r} for {spec['module_id']}")

    # Validate field types in tabs
    for tab in spec.get("tabs", []):
        for field in tab.get("fields", []):
            if field.get("type") not in FIELD_TYPES:
                logger.warning(
                    f"Unknown field type {field.get('type')!r} in {spec['module_id']}"
                )

    _REGISTRY[spec["module_id"]] = spec
    logger.info(f"Registered module config: {spec['module_id']} ({spec['title']})")


def get_registered_modules() -> Dict[str, Dict[str, Any]]:
    """Return the full registry."""
    return dict(_REGISTRY)


def get_modules_by_category() -> Dict[str, List[Dict[str, Any]]]:
    """Group registered modules by category for display."""
    by_cat: Dict[str, List[Dict[str, Any]]] = {}
    for mod in _REGISTRY.values():
        cat = mod.get("category", "other")
        by_cat.setdefault(cat, []).append(mod)
    # Sort each category alphabetically
    for cat in by_cat:
        by_cat[cat].sort(key=lambda m: m.get("title", ""))
    return by_cat


def resolve_config_path(p) -> Path:
    """Take a string or Path and resolve to absolute path under data/."""
    if hasattr(p, "exists"):
        return p
    if str(p).startswith("/"):
        return Path(p)
    return DATA / str(p)


__all__ = [
    "register_module_config",
    "get_registered_modules",
    "get_modules_by_category",
    "resolve_config_path",
    "CATEGORIES",
    "FIELD_TYPES",
]
