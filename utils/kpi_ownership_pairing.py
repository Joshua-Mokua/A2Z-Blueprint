"""KPI Ownership Pairing Engine — v10.410.

Per Joshua's directive:
  'MD could select the chief to cascade to or pair with another chief
   who shares same KPI e.g Commercial and retail chief could be paired.'

Reads data/kpi_ownership_map.json and provides:
  - get_co_owners(kpi)       → primary_owners, secondary_owners, default_pairing
  - is_shared_kpi(kpi)       → True if 2+ primary owners
  - apply_pairing_strategy(kpi, total, recipients, strategy)
                              → dict of {role/staff: amount}

Strategies:
  - equal_split: total / N
  - by_prior_year: proportional to prior year actual per recipient
  - manual: caller provides shares dict; we normalize to total

Per Rule 7, this is a COMPUTATION module — reads metadata, returns
computed allocations. Caller separately persists via CascadeManager.

Shipped: v10.410.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).parent.parent
DATA_DIR = REPO_ROOT / "data"


# ════════════════════════════════════════════════════════════════════
# Types
# ════════════════════════════════════════════════════════════════════

@dataclass
class CoOwnership:
    kpi: str
    primary_owners: List[str] = field(default_factory=list)   # role names
    secondary_owners: List[str] = field(default_factory=list)
    default_pairing: str = "equal_split"
    note: str = ""


@dataclass
class PairingResult:
    kpi: str
    strategy: str
    total_target: float
    allocations: Dict[str, float] = field(default_factory=dict)   # role → amount
    notes: List[str] = field(default_factory=list)


# ════════════════════════════════════════════════════════════════════
# Map loader (cached)
# ════════════════════════════════════════════════════════════════════

_MAP_CACHE: Optional[Dict[str, Any]] = None


def _load_map() -> Dict[str, Any]:
    global _MAP_CACHE
    if _MAP_CACHE is not None:
        return _MAP_CACHE
    path = DATA_DIR / "kpi_ownership_map.json"
    if not path.exists():
        _MAP_CACHE = {}
        return _MAP_CACHE
    raw = json.loads(path.read_text(encoding="utf-8"))
    # Strip meta keys (_note, _version, etc.)
    _MAP_CACHE = {k: v for k, v in raw.items() if not k.startswith("_")}
    return _MAP_CACHE


def clear_cache() -> None:
    global _MAP_CACHE
    _MAP_CACHE = None


# ════════════════════════════════════════════════════════════════════
# Lookups
# ════════════════════════════════════════════════════════════════════

def get_co_owners(kpi: str) -> Optional[CoOwnership]:
    """Return co-ownership metadata for a KPI, or None if not shared."""
    raw = _load_map().get(kpi)
    if not raw or not isinstance(raw, dict):
        return None
    return CoOwnership(
        kpi=kpi,
        primary_owners=list(raw.get("primary_owners", [])),
        secondary_owners=list(raw.get("secondary_owners", [])),
        default_pairing=str(raw.get("default_pairing", "equal_split")),
        note=str(raw.get("note", "")),
    )


def is_shared_kpi(kpi: str) -> bool:
    """True if KPI has 2+ primary owners."""
    co = get_co_owners(kpi)
    return co is not None and len(co.primary_owners) >= 2


def list_shared_kpis() -> List[str]:
    """List all KPIs marked as shared."""
    return [k for k in _load_map().keys() if is_shared_kpi(k)]


# ════════════════════════════════════════════════════════════════════
# Pairing strategies
# ════════════════════════════════════════════════════════════════════

def _staff_codes_for_roles(roles: List[str]) -> Dict[str, str]:
    """Resolve role → staff_code (first match in users.json)."""
    out: Dict[str, str] = {}
    users_path = DATA_DIR / "users.json"
    if not users_path.exists():
        return out
    users = json.loads(users_path.read_text(encoding="utf-8"))
    for u in users.values():
        if isinstance(u, dict):
            role = u.get("role", "")
            if role in roles and role not in out:
                out[role] = str(u.get("staff_code", ""))
    return out


def _prior_year_actual_for_role(role: str, kpi: str) -> float:
    """Sum of prior-year actuals across staff in this role.

    Reads bsc_actuals_2025 (and quarter variants) for staff with the role,
    sums their actual values for the given kpi. Used by by_prior_year
    pairing strategy.
    """
    # Resolve role → staff_codes
    users_path = DATA_DIR / "users.json"
    if not users_path.exists():
        return 0.0
    users = json.loads(users_path.read_text(encoding="utf-8"))
    matching = [str(u.get("staff_code", "")) for u in users.values()
                if isinstance(u, dict) and u.get("role") == role]
    if not matching:
        return 0.0

    total = 0.0
    for variant in ("2025", "2025-Q4", "2025-Q3", "2025-Q2"):
        path = DATA_DIR / f"bsc_actuals_{variant}.json"
        if not path.exists():
            continue
        try:
            recs = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(recs, list):
                continue
            for rec in recs:
                if isinstance(rec, dict):
                    sc = str(rec.get("staff_code", ""))
                    kid = rec.get("kpi_id") or rec.get("kpi")
                    if sc in matching and kid == kpi:
                        try:
                            total += float(rec.get("actual", 0) or 0)
                        except (TypeError, ValueError):
                            pass
        except (json.JSONDecodeError, OSError):
            continue
    return total


def apply_pairing_strategy(
    kpi: str,
    total_target: float,
    recipients: List[str],
    strategy: str = "equal_split",
    manual_shares: Optional[Dict[str, float]] = None,
) -> PairingResult:
    """Compute per-recipient amounts under a pairing strategy.

    Args:
      kpi: KPI being cascaded
      total_target: bank total to distribute
      recipients: list of role names (or staff codes) to receive
      strategy: 'equal_split' / 'by_prior_year' / 'manual'
      manual_shares: dict of {recipient: share_pct} when strategy='manual'

    Returns:
      PairingResult with allocations dict
    """
    result = PairingResult(
        kpi=kpi,
        strategy=strategy,
        total_target=total_target,
    )

    if not recipients:
        result.notes.append("No recipients selected")
        return result

    if strategy == "equal_split":
        per = total_target / len(recipients)
        for r in recipients:
            result.allocations[r] = round(per, 2)

    elif strategy == "by_prior_year":
        weights = []
        for r in recipients:
            w = _prior_year_actual_for_role(r, kpi)
            weights.append(w)
        total_w = sum(weights)
        if total_w <= 0:
            # Fall back to equal split if no prior data
            result.notes.append(
                "No prior-year actuals found; falling back to equal split."
            )
            return apply_pairing_strategy(
                kpi, total_target, recipients, "equal_split"
            )
        for r, w in zip(recipients, weights):
            result.allocations[r] = round(total_target * w / total_w, 2)

    elif strategy == "manual":
        if not manual_shares:
            result.notes.append("Manual strategy needs shares dict")
            return result
        # Normalize shares to sum to total_target
        share_sum = sum(manual_shares.values())
        if share_sum <= 0:
            result.notes.append("Manual shares sum to 0")
            return result
        for r in recipients:
            share = float(manual_shares.get(r, 0))
            result.allocations[r] = round(
                total_target * share / share_sum, 2
            )

    else:
        result.notes.append(f"Unknown strategy: {strategy}")

    # Verify coverage
    allocated = sum(result.allocations.values())
    if abs(allocated - total_target) > 0.5:
        result.notes.append(
            f"Coverage check: allocated {allocated:,.2f} of "
            f"{total_target:,.2f} ({allocated/total_target*100:.1f}%)"
        )
    return result


# ════════════════════════════════════════════════════════════════════
# Self-test
# ════════════════════════════════════════════════════════════════════

def self_test() -> None:
    print("─ kpi_ownership_pairing self-test ─")
    shared = list_shared_kpis()
    print(f"  Shared KPIs: {len(shared)}")
    assert len(shared) >= 5

    co = get_co_owners("PBT")
    print(f"  PBT co-ownership: {co.primary_owners} + secondary {co.secondary_owners}")
    assert co is not None
    assert len(co.primary_owners) >= 2

    # Equal split
    r1 = apply_pairing_strategy(
        "PBT", 10000.0,
        ["Director Retail Banking", "Director Commercial Banking"],
        "equal_split",
    )
    print(f"  Equal split: {r1.allocations}")
    assert all(v == 5000.0 for v in r1.allocations.values())

    # By prior year
    r2 = apply_pairing_strategy(
        "PBT", 10000.0,
        ["Director Retail Banking", "Director Commercial Banking"],
        "by_prior_year",
    )
    print(f"  By prior year: {r2.allocations} (notes: {r2.notes})")
    assert sum(r2.allocations.values()) > 0

    # Manual
    r3 = apply_pairing_strategy(
        "PBT", 10000.0,
        ["Director Retail Banking", "Director Commercial Banking"],
        "manual",
        manual_shares={"Director Retail Banking": 60,
                       "Director Commercial Banking": 40},
    )
    print(f"  Manual 60/40: {r3.allocations}")
    assert r3.allocations["Director Retail Banking"] == 6000.0
    assert r3.allocations["Director Commercial Banking"] == 4000.0
    print("✓ self_test passed")


if __name__ == "__main__":
    self_test()
