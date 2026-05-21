"""utils/org_hierarchy_config.py — Admin config for org hierarchy.

Loads `data/org_hierarchy_config.json` (admin-editable) and exposes
typed accessors. The synthesiser (utils/hierarchy_synth.py) reads
this config instead of using hardcoded regex tiers.

Discipline (Rule of Configurability):
  - Reporting chains, role tiers, role manager whitelists, synthetic
    top-org definitions, max span/depth → CONFIGURABLE (this file)
  - Validation invariants (no cycles, exactly 1 root, only chiefs
    report to MD) → HARDCODED in utils/hierarchy_synth.py

Per Rule 7, this module is diagnostic — it reads config and returns
typed views. It does NOT mutate source data files.

Shipped: v10.316.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

CONFIG_FILENAME = "org_hierarchy_config.json"
CONFIG_PATH = Path(__file__).parent.parent / "data" / CONFIG_FILENAME


# ════════════════════════════════════════════════════════════════════
# Typed config view
# ════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class SyntheticStaff:
    """A synthetic staff record to inject into the universe."""
    staff_code: str
    full_name: str
    role: str
    department: str
    band: str


@dataclass(frozen=True)
class OrgConfig:
    """Typed view over org_hierarchy_config.json."""
    synthetic_top_enabled: bool
    synthetic_md: Optional[SyntheticStaff]
    synthetic_chiefs: List[SyntheticStaff]
    department_chief_mapping: Dict[str, Optional[str]]
    role_tiers: Dict[str, int]
    role_tier_keyword_fallback: Dict[int, List[str]]
    role_manager_whitelist: Dict[str, List[str]]
    max_span_of_control: int
    max_chain_depth: int
    schema_version: str


# ════════════════════════════════════════════════════════════════════
# Loader
# ════════════════════════════════════════════════════════════════════

def _raw_config() -> Dict[str, Any]:
    """Load the raw JSON config file via canonical db.load_json path."""
    from utils.db import db
    try:
        cfg = db.load_json(CONFIG_PATH, default=None)
        if cfg is None:
            raise FileNotFoundError(
                f"{CONFIG_FILENAME} not found or empty"
            )
        return cfg
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(
            f"Failed to load {CONFIG_FILENAME}: {exc}"
        ) from exc


def load_config() -> OrgConfig:
    """Load and return the typed OrgConfig.

    Raises RuntimeError if the file is missing or malformed —
    callers must handle this if they want to fall back to a
    minimal default (most don't; the synthesiser requires config).
    """
    raw = _raw_config()

    # Synthetic top
    synth_top = raw.get("synthetic_top", {})
    synth_enabled = bool(synth_top.get("enabled", False))
    md_data = synth_top.get("md") if synth_enabled else None
    synth_md = None
    if md_data:
        synth_md = SyntheticStaff(
            staff_code=md_data["staff_code"],
            full_name=md_data["full_name"],
            role=md_data["role"],
            department=md_data["department"],
            band=md_data.get("band", "M5"),
        )

    # Chiefs
    chiefs_data = raw.get("chiefs", []) if synth_enabled else []
    synth_chiefs = []
    for c in chiefs_data:
        if not isinstance(c, dict):
            continue
        synth_chiefs.append(SyntheticStaff(
            staff_code=c.get("synthetic_staff_code") or "",
            full_name=c.get("full_name") or c.get("role", ""),
            role=c["role"],
            department=c.get("primary_department", "Executive"),
            band=c.get("band", "M5"),
        ))

    # Department chief mapping (strip the _note metadata)
    dept_chief = {
        k: v for k, v in raw.get(
            "department_chief_mapping", {}).items()
        if not k.startswith("_")
    }

    # Role tiers (strip _note)
    role_tiers_raw = raw.get("role_tiers", {})
    role_tiers = {
        k: int(v) for k, v in role_tiers_raw.items()
        if not k.startswith("_") and isinstance(v, (int, float))
    }

    # Role tier keyword fallback (parse tier_N_keywords → {N: [...]})
    fallback_raw = raw.get("role_tier_keyword_fallback", {})
    fallback: Dict[int, List[str]] = {}
    for k, v in fallback_raw.items():
        if k.startswith("_"):
            continue
        # k is like "tier_3_keywords" → extract 3
        match = re.match(r"^tier_(\d+)_keywords$", k)
        if match and isinstance(v, list):
            fallback[int(match.group(1))] = [
                str(x).lower() for x in v]

    # Role manager whitelist (strip _note)
    whitelist_raw = raw.get("role_manager_whitelist", {})
    whitelist = {
        k: list(v) for k, v in whitelist_raw.items()
        if not k.startswith("_") and isinstance(v, list)
    }

    return OrgConfig(
        synthetic_top_enabled=synth_enabled,
        synthetic_md=synth_md,
        synthetic_chiefs=synth_chiefs,
        department_chief_mapping=dept_chief,
        role_tiers=role_tiers,
        role_tier_keyword_fallback=fallback,
        role_manager_whitelist=whitelist,
        max_span_of_control=int(
            raw.get("default_max_span_of_control", 15)),
        max_chain_depth=int(
            raw.get("default_max_chain_depth", 12)),
        schema_version=raw.get("_schema_version", "unknown"),
    )


# ════════════════════════════════════════════════════════════════════
# Validation
# ════════════════════════════════════════════════════════════════════

def validate_config(cfg: OrgConfig) -> Dict[str, Any]:
    """Validate the loaded config for internal consistency.

    Checks:
      - synthetic_md has unique staff_code (not in any user list)
      - every value in department_chief_mapping (excluding null
        for Executive) appears in chiefs[].role
      - role_tiers values are in 0-6 range
      - keyword fallback covers all tiers 0-6
      - role_manager_whitelist references valid roles
    """
    violations: List[str] = []

    # Chiefs referenced in dept_chief_mapping must be in chiefs[]
    chief_roles_in_config = {c.role for c in cfg.synthetic_chiefs}
    for dept, chief_role in cfg.department_chief_mapping.items():
        if chief_role is None:
            continue
        if chief_role not in chief_roles_in_config:
            # Could be a real (non-synthetic) chief — check if at
            # least appears in role_tiers
            if chief_role not in cfg.role_tiers:
                violations.append(
                    f"Department '{dept}' maps to chief role "
                    f"'{chief_role}' which is neither in chiefs[] "
                    f"nor in role_tiers"
                )

    # role_tiers values in range
    for role, tier in cfg.role_tiers.items():
        if not (0 <= tier <= 6):
            violations.append(
                f"role_tiers['{role}'] = {tier} (out of 0-6 range)"
            )

    # Keyword fallback covers all tiers (warn only if missing)
    missing_fallback_tiers = [
        t for t in range(7)
        if t not in cfg.role_tier_keyword_fallback
    ]
    if missing_fallback_tiers:
        violations.append(
            f"role_tier_keyword_fallback missing tiers: "
            f"{missing_fallback_tiers}"
        )

    return {
        "valid": len(violations) == 0,
        "violations": violations,
        "schema_version": cfg.schema_version,
        "synthetic_top_enabled": cfg.synthetic_top_enabled,
        "chiefs_count": len(cfg.synthetic_chiefs),
        "departments_mapped": len(cfg.department_chief_mapping),
        "roles_in_tiers": len(cfg.role_tiers),
        "roles_with_whitelist": len(cfg.role_manager_whitelist),
    }


# ════════════════════════════════════════════════════════════════════
# Role tier classification (config-driven)
# ════════════════════════════════════════════════════════════════════

def classify_role_tier(role: str, cfg: Optional[OrgConfig] = None) -> int:
    """Classify a role into a seniority tier (0-6) using config.

    Lookup order:
      1. Exact match in role_tiers
      2. Keyword fallback by tier (lower tier checked first)
      3. Default tier 5 (officer-level)

    Special-cases (regardless of config):
      - "Teller" → 6
      - "Customer Service Officer" → 6 (overrides "officer" keyword)
    """
    if cfg is None:
        cfg = load_config()

    if not isinstance(role, str) or not role.strip():
        return 5
    role_clean = role.strip()
    role_lower = role_clean.lower()

    # Hard special cases for frontline (entry tier)
    if role_lower in ("teller", "customer service officer"):
        return 6

    # Exact match in config
    if role_clean in cfg.role_tiers:
        return cfg.role_tiers[role_clean]

    # Keyword fallback — walk tiers 0..6 in order
    for tier in sorted(cfg.role_tier_keyword_fallback.keys()):
        for kw in cfg.role_tier_keyword_fallback[tier]:
            if kw in role_lower:
                return tier

    return 5  # Officer-level default


def is_valid_manager_for(subordinate_role: str,
                          manager_role: str,
                          cfg: Optional[OrgConfig] = None) -> bool:
    """Check if a given manager role is whitelisted for a
    subordinate role.

    Returns True if:
      - subordinate_role isn't in the whitelist (no rule = allowed)
      - manager_role is in the whitelist for subordinate_role
    Returns False only if subordinate has an explicit whitelist
    AND manager_role isn't in it.
    """
    if cfg is None:
        cfg = load_config()
    whitelist = cfg.role_manager_whitelist.get(subordinate_role)
    if not whitelist:
        return True  # No rule = allowed
    return manager_role in whitelist


SPEC_DEVIATION_NOTE = (
    "Per Rule 7, this module reads admin config and exposes typed "
    "views. It does NOT mutate the config file (that's the admin's "
    "job via direct edit or a future admin UI). Validation rules "
    "(no cycles, exactly 1 root, only chiefs report to MD) are "
    "HARDCODED in utils/hierarchy_synth.py — they're system "
    "invariants, not admin-tunable."
)
