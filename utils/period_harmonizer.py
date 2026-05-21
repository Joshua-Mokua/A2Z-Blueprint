"""utils/period_harmonizer.py — Period scheme harmonization (LEAF MODULE).

Resolves TC38 — periods inconsistent across the three core files:
  - fixed_kpis.json: quarterly keys (2026-Q1, 2026-Q2, ...)
  - bank_targets.json: annual keys (PBT|2026)
  - target_cascade.json: annual keys (300001|PBT|2026)

Design:
  - Annual cascade is the norm (bank_targets + target_cascade are annual)
  - Fixed KPIs CAN be quarterly (MD changes locks per quarter per Joshua A1)
  - BUT can also be explicitly annual (e.g. "2026" key directly)

When annual cascade asks "is X fixed for year Y?":
  1. If annual key (Y) exists in fixed_kpis → use that list (authoritative)
  2. Else fall back to union of quarters (Y-Q1, Y-Q2, Y-Q3, Y-Q4)
  3. If only some quarters exist, union what's there

LEAF MODULE: zero upward utils.* imports. Stdlib only.

Shipped: v10.401.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

__all__ = [
    "get_fixed_kpis_for_period",
    "get_quarters_for_year",
    "promote_quarters_to_annual",
    "validate_period_consistency",
    "list_periods",
    "set_annual_fixed_kpis",
    "QUARTER_KEYS",
]

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
FIXED_KPIS_PATH = DATA_DIR / "fixed_kpis.json"

QUARTER_KEYS = ("Q1", "Q2", "Q3", "Q4")


# ────────────────────────────────────────────────────────────────────
# Read helpers
# ────────────────────────────────────────────────────────────────────

def _load_fixed_kpis() -> Dict[str, Any]:
    if not FIXED_KPIS_PATH.exists():
        return {}
    try:
        return json.loads(FIXED_KPIS_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_fixed_kpis(data: Dict[str, Any], *, who: str = "system",
                     reason: str = "") -> bool:
    try:
        # Stamp last-modified
        data.setdefault("_v10401_period_meta", {})
        data["_v10401_period_meta"]["last_modified"] = datetime.now().isoformat()
        data["_v10401_period_meta"]["last_modified_by"] = who
        if reason:
            data["_v10401_period_meta"]["last_reason"] = reason
        FIXED_KPIS_PATH.write_text(
            json.dumps(data, indent=2, ensure_ascii=False),
            encoding="utf-8"
        )
        return True
    except Exception:
        return False


def list_periods() -> Dict[str, List[str]]:
    """List all periods in fixed_kpis.json grouped by type."""
    data = _load_fixed_kpis()
    annual: List[str] = []
    quarterly: List[str] = []
    for k, v in data.items():
        if k.startswith("_"):
            continue
        if not isinstance(v, dict):
            continue
        if "-Q" in k:
            quarterly.append(k)
        elif k.isdigit() or (len(k) == 4 and k.isdigit()):
            annual.append(k)
    return {"annual": sorted(annual), "quarterly": sorted(quarterly)}


# ────────────────────────────────────────────────────────────────────
# Core: get fixed KPIs for any period (annual prefers, then quarters)
# ────────────────────────────────────────────────────────────────────

def get_fixed_kpis_for_period(period: str) -> Set[str]:
    """Return set of fixed KPI names for the given period.

    For annual periods like '2026':
      1. If '2026' annual key exists in fixed_kpis → use directly
      2. Else union all '2026-Q*' quarters present
      3. Returns empty set if neither exists

    For quarterly periods like '2026-Q2':
      1. Return that quarter's list exactly
      2. Returns empty set if not present
    """
    data = _load_fixed_kpis()
    if not data:
        return set()

    # Direct match (annual or quarterly key)
    if period in data and isinstance(data[period], dict):
        kpis = data[period].get("kpis", [])
        if isinstance(kpis, list):
            return {k for k in kpis if isinstance(k, str)}

    # If period is annual (e.g. '2026') and no direct key, union quarters
    if period.isdigit() or (len(period) == 4 and period.isdigit()):
        union: Set[str] = set()
        for q in QUARTER_KEYS:
            q_key = f"{period}-{q}"
            if q_key in data and isinstance(data[q_key], dict):
                kpis = data[q_key].get("kpis", [])
                if isinstance(kpis, list):
                    union.update(k for k in kpis if isinstance(k, str))
        return union

    return set()


def get_quarters_for_year(year: str) -> Dict[str, Set[str]]:
    """Return {quarter_key: set_of_kpis} for all 4 quarters of year, empty if missing."""
    data = _load_fixed_kpis()
    out: Dict[str, Set[str]] = {}
    for q in QUARTER_KEYS:
        q_key = f"{year}-{q}"
        if q_key in data and isinstance(data[q_key], dict):
            kpis = data[q_key].get("kpis", [])
            out[q_key] = {k for k in kpis if isinstance(k, str)} if isinstance(kpis, list) else set()
        else:
            out[q_key] = set()
    return out


# ────────────────────────────────────────────────────────────────────
# Validation
# ────────────────────────────────────────────────────────────────────

def validate_period_consistency(year: str) -> Dict[str, Any]:
    """Check consistency between annual and quarterly entries for a year.

    Returns dict with:
      - 'consistent': True if annual matches quarter union, OR if only one
                      scheme exists
      - 'annual_kpis': annual list (if present)
      - 'quarterly_union': union of quarters (if any present)
      - 'difference': symmetric difference if both present
      - 'issues': list of human-readable issues
    """
    data = _load_fixed_kpis()
    issues: List[str] = []

    annual_present = year in data and isinstance(data[year], dict)
    annual_kpis: Set[str] = set()
    if annual_present:
        kpis = data[year].get("kpis", [])
        if isinstance(kpis, list):
            annual_kpis = {k for k in kpis if isinstance(k, str)}

    quarters = get_quarters_for_year(year)
    quarterly_present = any(len(v) > 0 for v in quarters.values())
    quarterly_union: Set[str] = set()
    for q_kpis in quarters.values():
        quarterly_union.update(q_kpis)

    # Check 1 — at least one scheme present
    if not annual_present and not quarterly_present:
        issues.append(f"No fixed KPIs defined for {year}")

    # Check 2 — quarters consistent with each other
    quarterly_sets = {q: kpis for q, kpis in quarters.items() if kpis}
    if len(quarterly_sets) >= 2:
        first_q = next(iter(quarterly_sets.values()))
        for q_key, q_kpis in quarterly_sets.items():
            diff = q_kpis ^ first_q
            if diff:
                issues.append(
                    f"Quarter {q_key} differs from baseline by {sorted(diff)}"
                )

    # Check 3 — annual matches quarterly union (if both present)
    if annual_present and quarterly_present:
        diff = annual_kpis ^ quarterly_union
        if diff:
            issues.append(
                f"Annual {year} differs from quarterly union by {sorted(diff)}"
            )

    return {
        "year": year,
        "annual_present": annual_present,
        "quarterly_present": quarterly_present,
        "annual_kpis": sorted(annual_kpis),
        "quarterly_union": sorted(quarterly_union),
        "difference": sorted(annual_kpis ^ quarterly_union) if (annual_present and quarterly_present) else [],
        "consistent": len(issues) == 0,
        "issues": issues,
    }


# ────────────────────────────────────────────────────────────────────
# Mutators
# ────────────────────────────────────────────────────────────────────

def promote_quarters_to_annual(year: str, *, who: str = "system",
                               reason: str = "") -> Tuple[bool, str]:
    """Create or update annual key from union of quarter entries.

    Returns (ok, message).
    """
    quarters = get_quarters_for_year(year)
    union: Set[str] = set()
    for q_kpis in quarters.values():
        union.update(q_kpis)

    if not union:
        return False, f"No quarterly KPIs found for {year}; nothing to promote"

    data = _load_fixed_kpis()
    data[year] = {
        "kpis": sorted(union),
        "_doc": f"Annual fixed KPI list — promoted from quarters by {who}",
        "_promoted_from_quarters": [q for q, kpis in quarters.items() if kpis],
        "_promoted_at": datetime.now().isoformat(),
    }
    if _save_fixed_kpis(data, who=who, reason=reason or f"promote {year} quarters to annual"):
        return True, f"Promoted {len(union)} KPIs to annual {year}"
    return False, "Save failed"


def set_annual_fixed_kpis(year: str, kpis: List[str], *,
                          who: str = "system",
                          reason: str = "") -> Tuple[bool, str]:
    """Set explicit annual fixed KPI list for a year (overwrites)."""
    if not year or not isinstance(kpis, list):
        return False, "Invalid arguments"
    data = _load_fixed_kpis()
    clean_kpis = sorted({k for k in kpis if isinstance(k, str) and k})
    data[year] = {
        "kpis": clean_kpis,
        "_doc": f"Annual fixed KPI list set by {who}",
        "_set_at": datetime.now().isoformat(),
    }
    if _save_fixed_kpis(data, who=who, reason=reason or f"set annual {year}"):
        return True, f"Set {len(clean_kpis)} KPIs as fixed for {year}"
    return False, "Save failed"


# ────────────────────────────────────────────────────────────────────
# Self-test
# ────────────────────────────────────────────────────────────────────

def self_test() -> int:
    tests = 0

    periods = list_periods()
    assert isinstance(periods, dict)
    assert "annual" in periods
    assert "quarterly" in periods
    tests += 1

    # Test that union-based lookup still works (backward compat)
    fixed_2026 = get_fixed_kpis_for_period("2026")
    assert isinstance(fixed_2026, set)
    tests += 1

    # Test quarterly lookup
    q_kpis = get_fixed_kpis_for_period("2026-Q1")
    assert isinstance(q_kpis, set)
    tests += 1

    # Test consistency check
    val = validate_period_consistency("2026")
    assert "consistent" in val
    assert "issues" in val
    tests += 1

    # Quarters helper
    quarters = get_quarters_for_year("2026")
    assert isinstance(quarters, dict)
    assert all(k in quarters for k in ("2026-Q1", "2026-Q2", "2026-Q3", "2026-Q4"))
    tests += 1

    print(f"✓ period_harmonizer self_test passed ({tests} tests)")
    print(f"  Annual periods:        {periods['annual']}")
    print(f"  Quarterly periods:     {periods['quarterly']}")
    print(f"  Fixed KPIs for 2026:   {len(fixed_2026)} ({'annual' if '2026' in [p['year'] if isinstance(p, dict) else p for p in periods['annual']] else 'quarterly-union'})")
    print(f"  2026 consistency:      {val['consistent']} ({len(val['issues'])} issues)")
    return tests


if __name__ == "__main__":
    self_test()
