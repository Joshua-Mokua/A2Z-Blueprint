"""
api_lms_committee_tiers.py — multi-tier credit committee ladder (CF-8).

The bank's credit committees form an ORDERED ladder. A case passes through
tiers sequentially; the committee AT EACH TIER decides whether to approve /
decline, or SUBMIT UPWARD to the next tier. Tier authority limits (admin-
configured) inform that decision but the committee decides.

Tiers (default):
  1. Branch Credit Committee (BCC)   — origin for most cases
  2. Management Credit Committee     — convenes under the MD
  3. Board Credit Committee          — above management's limit
  4. Group Credit Committee          — Ecobank group level

Leeway: a case need not enter at tier 1. CIB / head-office cases can enter
ABOVE the branch tier (skip BCC) by specifying an entry tier.

Config-driven: lms_config.json -> committee_tiers (ordered list). Falls back
to a sensible default ladder. Tier limits are admin-editable.
"""
from __future__ import annotations

import json as _json
from pathlib import Path as _Path
from typing import Any, Dict, List, Optional


_TIERS_DEFAULT: List[Dict[str, Any]] = [
    {"tier": 1, "key": "branch_cc", "name": "Branch Credit Committee",
     "authority_limit_kes": 5_000_000, "can_be_entry": True},
    {"tier": 2, "key": "management_cc", "name": "Management Credit Committee",
     "authority_limit_kes": 100_000_000, "can_be_entry": True},
    {"tier": 3, "key": "board_cc", "name": "Board Credit Committee",
     "authority_limit_kes": 500_000_000, "can_be_entry": True},
    {"tier": 4, "key": "group_cc", "name": "Group Credit Committee",
     "authority_limit_kes": None, "can_be_entry": True},  # None = no ceiling
]


def get_committee_tiers() -> List[Dict[str, Any]]:
    """Ordered committee tier ladder from lms_config.json -> committee_tiers,
    falling back to the default ladder. Always returned sorted by tier."""
    tiers = None
    try:
        p = _Path(__file__).resolve().parent.parent / "data" / "lms_config.json"
        if p.exists():
            cfg = _json.loads(p.read_text(encoding="utf-8")) or {}
            t = cfg.get("committee_tiers")
            if isinstance(t, list) and t:
                tiers = t
    except Exception:
        tiers = None
    if not tiers:
        tiers = _TIERS_DEFAULT
    # Normalise + sort by tier number.
    out = []
    for entry in tiers:
        if not isinstance(entry, dict):
            continue
        try:
            tn = int(entry.get("tier"))
        except (TypeError, ValueError):
            continue
        out.append({
            "tier": tn,
            "key": str(entry.get("key", f"tier_{tn}")),
            "name": str(entry.get("name", f"Tier {tn}")),
            "authority_limit_kes": entry.get("authority_limit_kes"),
            "can_be_entry": bool(entry.get("can_be_entry", True)),
        })
    out.sort(key=lambda x: x["tier"])
    return out or list(_TIERS_DEFAULT)


def tier_by_number(tier_no: int) -> Optional[Dict[str, Any]]:
    for t in get_committee_tiers():
        if t["tier"] == tier_no:
            return t
    return None


def first_tier() -> Dict[str, Any]:
    tiers = get_committee_tiers()
    return tiers[0]


def next_tier(current_tier_no: int) -> Optional[Dict[str, Any]]:
    """The tier immediately above the current one, or None if at the top."""
    tiers = get_committee_tiers()
    for i, t in enumerate(tiers):
        if t["tier"] == current_tier_no and i + 1 < len(tiers):
            return tiers[i + 1]
    return None


def resolve_entry_tier(requested: Any = None, amount_kes: float = 0) -> Dict[str, Any]:
    """Pick the entry tier for a case.

    - If `requested` (a tier number) is given and valid AND that tier allows
      entry, use it — this is the CIB / head-office leeway to skip the branch
      BCC and enter higher.
    - Otherwise default to the first (lowest) tier — most cases originate at
      the Branch Credit Committee.

    Amount is accepted for future amount-aware defaulting but, per the bank's
    model, the committee (not the amount) drives upward movement, so amount
    does not auto-skip tiers here.
    """
    tiers = get_committee_tiers()
    if requested is not None:
        try:
            rn = int(requested)
        except (TypeError, ValueError):
            rn = None
        if rn is not None:
            for t in tiers:
                if t["tier"] == rn and t.get("can_be_entry", True):
                    return t
    return tiers[0]


def tier_label(tier_no: int) -> str:
    t = tier_by_number(tier_no)
    return t["name"] if t else f"Tier {tier_no}"
