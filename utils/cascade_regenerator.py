"""utils/cascade_regenerator.py — Cascade regenerator (LEAF MODULE).

Per Joshua's directives across v10.391-v10.396:
- Cascade follows canonical line manager hierarchy (role_manager_whitelist)
- Fixed KPIs (MD's reserve) are NOT cascaded — they replicate bank-wide value
- Not all ratios are fixed (NPL varies per branch — cascade it)
- Role names + reporting lines come from admin config (no hardcoded names)
- SBM is branch top for big branches (v10.396 alignment)

This module rebuilds `data/target_cascade.json` from scratch using:
- Canonical hierarchy (org_hierarchy_config.json::role_manager_whitelist)
- Bank targets (bank_targets.json)
- Fixed KPI list (fixed_kpis.json) — skip these
- Staff data (users.json) — find actual managers

Resolves Phase C2 findings TC18 (cross-branch), TC21 (BOM at one branch
gets cascade from BM at another), TC22 (multi-sender ambiguity), TC25
(63% over-allocation from MD), TC32 (representative-sender pattern where
only 50 of 1449 staff appear as senders).

LEAF MODULE: zero upward `utils.*` imports. Stdlib only.

Shipped: v10.397.
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

DEFAULT_BRANCH_TIER_THRESHOLD = 4
DEFAULT_PERIOD = "2026"


# ─── Helpers ────────────────────────────────────────────────────────


def _load_json(filename: str) -> Dict[str, Any]:
    path = DATA_DIR / filename
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _strip_meta(d: Dict[str, Any]) -> Dict[str, Any]:
    return {k: v for k, v in d.items() if not k.startswith("_")}


def _build_staff_index(
    users: Dict[str, Any],
    role_tiers: Optional[Dict[str, int]] = None,
) -> Dict[str, Dict[str, Any]]:
    """staff_code → {role, unit, name, username}. Skips entries without staff_code.

    When duplicate staff_codes exist in users.json (data bug — e.g., two
    users with staff_code '300001'), STILL keep BOTH by using a fallback
    composite key for the second occurrence (staff_code + '__' + username
    suffix). This ensures no staff is lost; just the lookup key differs.

    The primary staff_code (no suffix) is given to the entry with the LOWER
    tier (more senior role). Duplicates get suffixed keys.

    v10.403 exclusions:
      - Admin role: monitoring/login account; not a P&L responsibility center
      - EXEC-* synthetic codes: residual seed data, fully replaced by real chiefs
    """
    if role_tiers is None:
        role_tiers = {}
    # v10.403: roles excluded from cascade allocation
    EXCLUDED_ROLES = {"Admin"}
    # First pass: collect by username with full info
    by_username: Dict[str, Dict[str, Any]] = {}
    for username, u in users.items():
        if not isinstance(u, dict):
            continue
        code = u.get("staff_code")
        if not code or not isinstance(code, str):
            continue
        role = str(u.get("role", "")).strip()
        # v10.403 — exclude Admin role + EXEC-* synthetic codes
        if role in EXCLUDED_ROLES:
            continue
        if code.startswith("EXEC-"):
            continue
        by_username[username] = {
            "code": code,
            "role": role,
            "unit": str(u.get("unit", "")).strip(),
            "name": str(u.get("full_name", u.get("name", username))).strip(),
            "username": username,
        }
    # Group by code
    by_code: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for info in by_username.values():
        by_code[info["code"]].append(info)
    # Assign keys: primary = code (more senior wins); duplicates = code__username
    idx: Dict[str, Dict[str, Any]] = {}
    for code, infos in by_code.items():
        if len(infos) == 1:
            idx[code] = {k: v for k, v in infos[0].items() if k != "code"}
        else:
            # Sort by tier (lower = more senior)
            infos.sort(key=lambda i: role_tiers.get(i["role"], 999))
            # First (most senior) gets the bare code
            idx[code] = {k: v for k, v in infos[0].items() if k != "code"}
            # Others get suffixed
            for dup in infos[1:]:
                suffix_key = f"{code}__{dup['username']}"
                idx[suffix_key] = {k: v for k, v in dup.items() if k != "code"}
    return idx


def _build_role_unit_lookup(
    staff_idx: Dict[str, Dict[str, Any]],
) -> Dict[str, Dict[str, List[str]]]:
    """role → unit → [staff_codes]. For fast same-branch lookups."""
    out: Dict[str, Dict[str, List[str]]] = defaultdict(lambda: defaultdict(list))
    for code, info in staff_idx.items():
        out[info["role"]][info["unit"]].append(code)
    return out


# ─── Reporting tree ──────────────────────────────────────────────────


def _select_md_code(
    staff_idx: Dict[str, Dict[str, Any]],
    role_tiers: Dict[str, int],
) -> Optional[str]:
    """Select the actual MD code.

    Multiple tier-0 staff may exist (e.g., synthetic EXEC-MD-001 placeholder
    alongside real staff like 300001). Prefer numeric-code real staff over
    synthetic EXEC-* placeholders.
    """
    candidates = [
        (code, info) for code, info in staff_idx.items()
        if role_tiers.get(info["role"]) == 0
    ]
    if not candidates:
        return None
    # Prefer real staff (numeric codes, no EXEC- prefix)
    real = [c for c, _ in candidates if not c.startswith("EXEC-")]
    if real:
        real.sort()
        return real[0]
    # Fall back to any tier-0
    return sorted(c for c, _ in candidates)[0]


def find_manager_code(
    sub_role: str,
    sub_unit: str,
    role_manager_whitelist: Dict[str, List[str]],
    role_tiers: Dict[str, int],
    role_unit_lookup: Dict[str, Dict[str, List[str]]],
    area_manager_codes: List[str],
    branch_tier_threshold: int = DEFAULT_BRANCH_TIER_THRESHOLD,
    md_code: Optional[str] = None,
) -> Optional[str]:
    """Find a single manager code for a staff with role/unit.

    Resolution order:
    1. For each valid manager role in whitelist priority order:
       - tier >= branch_tier_threshold (branch-level): find at same unit
       - tier == branch_tier_threshold-1 (regional like Area Manager):
         deterministically assign one of the area_manager_codes by unit hash
       - tier 0 (MD root): return md_code
       - else (HQ tier 1-2): find at "Head Office"
    2. IMPLICIT FALLBACK: if no manager found AND staff is C-suite (tier 1),
       assign MD as manager. This bridges the canonical gap where C-suite
       isn't listed as subordinate of MD in role_manager_whitelist.
    3. Returns first match; None if nothing matches.
    """
    sub_tier = role_tiers.get(sub_role, -1)
    valid_mgr_roles = role_manager_whitelist.get(sub_role, [])

    for mgr_role in valid_mgr_roles:
        mgr_tier = role_tiers.get(mgr_role, -1)

        if mgr_tier >= branch_tier_threshold:
            # Branch-level: same unit
            candidates = role_unit_lookup.get(mgr_role, {}).get(sub_unit, [])
            if candidates:
                return candidates[0]

        elif mgr_tier == (branch_tier_threshold - 1):
            # Regional: distribute across multiple managers by unit hash
            if mgr_role == "Area Manager" and area_manager_codes:
                idx = abs(hash(sub_unit)) % len(area_manager_codes)
                return area_manager_codes[idx]
            candidates = role_unit_lookup.get(mgr_role, {}).get("Head Office", [])
            if candidates:
                return candidates[0]

        elif mgr_tier == 0:
            if md_code:
                return md_code
            candidates = role_unit_lookup.get(mgr_role, {}).get("Head Office", [])
            if candidates:
                return candidates[0]

        else:
            # HQ (tier 1-2): Head Office
            candidates = role_unit_lookup.get(mgr_role, {}).get("Head Office", [])
            if candidates:
                return candidates[0]

    # IMPLICIT FALLBACK: C-suite (tier 1) reports to MD (tier 0)
    # Canonical whitelist doesn't enumerate C-suite as MD subordinates,
    # but structurally all chiefs report to MD.
    if sub_tier == 1 and md_code:
        return md_code

    return None


def build_reporting_tree(
    users: Dict[str, Any],
    role_manager_whitelist: Dict[str, List[str]],
    role_tiers: Dict[str, int],
    branch_tier_threshold: int = DEFAULT_BRANCH_TIER_THRESHOLD,
) -> Tuple[Dict[str, str], List[str], Dict[str, List[str]]]:
    """Build staff_code → manager_code mapping for all staff.

    Returns:
      tree: dict {staff_code: manager_code}
      orphans: list of staff_code with no valid manager (e.g., MD)
      reports_of: dict {manager_code: [report_codes]} — inverse for cascade
    """
    staff_idx = _build_staff_index(users, role_tiers)
    role_unit_lookup = _build_role_unit_lookup(staff_idx)

    # Locate MD (preferring real staff over synthetic EXEC-* placeholders)
    md_code = _select_md_code(staff_idx, role_tiers)

    # Locate Area Managers (regional, tier 3)
    area_manager_codes = [
        c for c, i in staff_idx.items() if i["role"] == "Area Manager"
    ]
    area_manager_codes.sort()  # deterministic ordering

    tree: Dict[str, str] = {}
    orphans: List[str] = []

    for code, info in staff_idx.items():
        if code == md_code:
            orphans.append(code)  # MD has no manager (root)
            continue
        mgr = find_manager_code(
            sub_role=info["role"],
            sub_unit=info["unit"],
            role_manager_whitelist=role_manager_whitelist,
            role_tiers=role_tiers,
            role_unit_lookup=role_unit_lookup,
            area_manager_codes=area_manager_codes,
            branch_tier_threshold=branch_tier_threshold,
            md_code=md_code,
        )
        if mgr and mgr != code:  # no self-loop
            tree[code] = mgr
        else:
            orphans.append(code)

    # Inverse mapping
    reports_of: Dict[str, List[str]] = defaultdict(list)
    for child, parent in tree.items():
        reports_of[parent].append(child)
    # Stabilize order
    for k in reports_of:
        reports_of[k].sort()

    return tree, orphans, dict(reports_of)


# ─── Cascade generation ──────────────────────────────────────────────


def _get_fixed_kpi_set(
    fixed_kpis: Dict[str, Any], year: str
) -> Set[str]:
    """Get fixed KPIs for the year.

    v10.401 TC38 fix: prefer explicit annual key when present, else union
    quarters (backward compatible with v10.397-v10.400 behavior).
    """
    # v10.401: explicit annual key wins (e.g. '2026')
    if year in fixed_kpis and isinstance(fixed_kpis[year], dict):
        kpis = fixed_kpis[year].get("kpis", [])
        if isinstance(kpis, list):
            return {k for k in kpis if isinstance(k, str)}

    # Fallback: union all quarter entries (legacy behavior)
    fixed: Set[str] = set()
    for period_key, period_val in fixed_kpis.items():
        if period_key.startswith(year) and "-Q" in period_key and isinstance(period_val, dict):
            kpis = period_val.get("kpis", [])
            if isinstance(kpis, list):
                fixed.update(kpis)
    return fixed


def _cascade_recursive(
    manager_code: str,
    kpi: str,
    period: str,
    total_target: float,
    reports_of: Dict[str, List[str]],
    staff_idx: Dict[str, Dict[str, Any]],
    cascade_out: Dict[str, Any],
) -> None:
    """Cascade target from manager down to their reports (equal split)."""
    reports = reports_of.get(manager_code, [])
    if not reports:
        return  # leaf

    share = total_target / len(reports) if total_target else 0.0
    mgr_info = staff_idx.get(manager_code, {"role": "?", "unit": "?", "name": "?"})

    allocations = []
    for r in reports:
        r_info = staff_idx.get(r, {"role": "?", "unit": "?", "name": "?"})
        allocations.append({
            "to_code": r,
            "to_name": r_info["name"],
            "to_role": r_info["role"],
            "to_unit": r_info["unit"],
            "amount": share,
        })

    key = f"{manager_code}|{kpi}|{period}"
    cascade_out[key] = {
        "from_code": manager_code,
        "from_name": mgr_info["name"],
        "from_role": mgr_info["role"],
        "from_unit": mgr_info["unit"],
        "kpi": kpi,
        "period": period,
        "total_target": total_target,
        "allocated_sum": share * len(reports),
        "allocations": allocations,
    }

    # Recurse into each report
    for r in reports:
        _cascade_recursive(r, kpi, period, share, reports_of,
                           staff_idx, cascade_out)


def regenerate_cascade_for_period(
    bank_targets: Dict[str, Any],
    fixed_kpi_set: Set[str],
    reports_of: Dict[str, List[str]],
    staff_idx: Dict[str, Dict[str, Any]],
    md_code: str,
    period: str = DEFAULT_PERIOD,
    existing_cascade: Optional[Dict[str, Any]] = None,
    preserve_manual: bool = True,
) -> Dict[str, Any]:
    """Generate cascade entries for all non-fixed KPIs in the period.

    v10.404 — preserve_manual mode (default True):
      - For each (manager, kpi, period) key that already has a MANUAL
        allocation in existing_cascade, the existing entry is preserved
        and we DO NOT recurse from that manager (their subtree is their
        responsibility).
      - For all other branches, fresh equal-split cascade is generated.
      - "Manual" detection: entry has 'updated_by' field (set by
        CascadeManager.set_allocation via UI) or '_v10404_manual' marker.

    When preserve_manual=False, behaves as v10.397-v10.403 (full rebuild).
    """
    cascade: Dict[str, Any] = {}
    manual_keys: Set[str] = set()

    # v10.404 — identify manual entries to preserve
    if preserve_manual and existing_cascade:
        for key, entry in existing_cascade.items():
            if key.startswith("_") or "|" not in key:
                continue
            if not isinstance(entry, dict):
                continue
            # Manual if marked or has updated_by (from UI set_allocation)
            if entry.get("_v10404_manual") or entry.get("updated_by"):
                manual_keys.add(key)
                # Bring forward the existing manual entry as-is
                cascade[key] = entry

    # v10.404 — collect manual subtree roots: any (from_code, kpi, period)
    # where from_code has a manual entry. We'll skip those recursions.
    manual_managers_per_kpi: Dict[Tuple[str, str], Set[str]] = defaultdict(set)
    for mk in manual_keys:
        parts = mk.split("|")
        if len(parts) >= 3:
            from_code, kpi, prd = parts[0], parts[1], "|".join(parts[2:])
            manual_managers_per_kpi[(kpi, prd)].add(from_code)

    for key, entry in bank_targets.items():
        if not isinstance(entry, dict):
            continue
        if not key.endswith(f"|{period}"):
            continue
        kpi = key.rsplit("|", 1)[0]
        if kpi in fixed_kpi_set:
            continue  # MD's fixed reserve — replicate, don't cascade
        try:
            target = float(entry.get("target", 0))
        except (TypeError, ValueError):
            continue
        if target == 0:
            continue
        # v10.404 — collect manual senders for this kpi+period
        skip_set = manual_managers_per_kpi.get((kpi, period), set())
        _cascade_recursive_with_skip(
            md_code, kpi, period, target, reports_of,
            staff_idx, cascade, skip_set
        )

    return cascade


def _cascade_recursive_with_skip(
    manager_code: str,
    kpi: str,
    period: str,
    total_target: float,
    reports_of: Dict[str, List[str]],
    staff_idx: Dict[str, Dict[str, Any]],
    cascade_out: Dict[str, Any],
    skip_set: Set[str],
) -> None:
    """v10.404 — Cascade recursive with manual-preserve skipping.

    If manager_code is in skip_set, this manager has a manual allocation;
    we leave it untouched and do NOT recurse below them (their subtree is
    their responsibility).
    """
    key = f"{manager_code}|{kpi}|{period}"
    # If this is a manual entry, preserve it (already in cascade_out) and
    # do not regenerate or recurse
    if manager_code in skip_set:
        return

    reports = reports_of.get(manager_code, [])
    if not reports:
        return  # leaf

    share = total_target / len(reports) if total_target else 0.0
    mgr_info = staff_idx.get(manager_code, {"role": "?", "unit": "?", "name": "?"})

    allocations = []
    for r in reports:
        r_info = staff_idx.get(r, {"role": "?", "unit": "?", "name": "?"})
        allocations.append({
            "to_code": r,
            "to_name": r_info["name"],
            "to_role": r_info["role"],
            "to_unit": r_info["unit"],
            "amount": share,
        })

    cascade_out[key] = {
        "from_code": manager_code,
        "from_role": mgr_info["role"],
        "from_unit": mgr_info["unit"],
        "kpi": kpi,
        "period": period,
        "total_target": total_target,
        "allocated_sum": share * len(reports),
        "allocations": allocations,
    }

    # Recurse into each report (with same skip_set)
    for r in reports:
        _cascade_recursive_with_skip(
            r, kpi, period, share, reports_of,
            staff_idx, cascade_out, skip_set
        )


# ─── Main entry ──────────────────────────────────────────────────────


def regenerate_target_cascade(
    period: str = DEFAULT_PERIOD,
    write: bool = False,
    preserve_manual: bool = True,
) -> Dict[str, Any]:
    """Top-level: load all inputs, regenerate cascade, optionally write.

    v10.404 — preserve_manual (default True):
      - When True: any existing cascade entry with 'updated_by' field (set
        by manager via UI) is preserved. Their subtree is not regenerated.
      - When False: full rebuild (v10.397-v10.403 behaviour).

    If write=True, backs up current target_cascade.json and writes new one.
    Returns the generated cascade dict (or empty if inputs missing).
    """
    users = _load_json("users.json")
    ohc = _load_json("org_hierarchy_config.json")
    bank_targets = _load_json("bank_targets.json")
    fixed_kpis = _load_json("fixed_kpis.json")
    existing_cascade = _load_json("target_cascade.json")  # v10.404

    if not users or not ohc or not bank_targets:
        return {}

    rmw = _strip_meta(ohc.get("role_manager_whitelist", {}))
    rmw = {k: v for k, v in rmw.items() if isinstance(v, list)}
    tiers = _strip_meta(ohc.get("role_tiers", {}))
    tiers = {k: int(v) for k, v in tiers.items()
             if isinstance(v, (int, float))}
    threshold = int(ohc.get("branch_tier_threshold", DEFAULT_BRANCH_TIER_THRESHOLD))

    year = period.split("-")[0]
    fixed_set = _get_fixed_kpi_set(fixed_kpis, year)

    tree, orphans, reports_of = build_reporting_tree(
        users, rmw, tiers, threshold
    )

    staff_idx = _build_staff_index(users, tiers)
    md_code = _select_md_code(staff_idx, tiers)

    if not md_code:
        return {}

    cascade = regenerate_cascade_for_period(
        bank_targets, fixed_set, reports_of, staff_idx, md_code, period,
        existing_cascade=existing_cascade,
        preserve_manual=preserve_manual,
    )

    if write:
        # Backup current then write new
        out_path = DATA_DIR / "target_cascade.json"
        backup_dir = DATA_DIR / "_v10397_backups"
        backup_dir.mkdir(parents=True, exist_ok=True)
        if out_path.exists():
            backup = backup_dir / "target_cascade.json.before"
            backup.write_text(out_path.read_text(encoding="utf-8"))
        # Preserve any meta keys from previous cascade
        meta = {k: v for k, v in existing_cascade.items() if k.startswith("_")}
        meta["_v10397_regenerated"] = {
            "_doc": ("Cascade regenerated v10.397 using canonical hierarchy "
                     "(role_manager_whitelist) + Fixed KPI mechanism. "
                     "Replaces representative-sender pattern (TC32) with "
                     "per-staff cascade. Resolves TC18/TC21/TC22/TC25/TC32."),
            "period": period,
            "entries_generated": len(cascade),
            "fixed_kpis_skipped": sorted(fixed_set),
            "orphans": orphans,
        }
        # v10.404 — record preserve_manual outcome
        manual_count = sum(
            1 for k, v in cascade.items()
            if isinstance(v, dict) and (v.get("_v10404_manual") or v.get("updated_by"))
        )
        meta["_v10404_preserve_manual"] = {
            "_doc": ("v10.404: regenerator preserves manual allocations by "
                     "default. Manual entries are those set via "
                     "CascadeManager.set_allocation (have 'updated_by' field) "
                     "or marked with '_v10404_manual'. Their subtree is not "
                     "regenerated (manager's responsibility)."),
            "preserve_manual": preserve_manual,
            "manual_entries_preserved": manual_count,
        }
        out = {**meta, **cascade}
        out_path.write_text(json.dumps(out, indent=2, ensure_ascii=False))

    return cascade


# ─── Self-test ───────────────────────────────────────────────────────


def self_test() -> None:
    users = _load_json("users.json")
    ohc = _load_json("org_hierarchy_config.json")
    if not users or not ohc:
        print("⚠ skip self-test (data missing)")
        return

    rmw = _strip_meta(ohc.get("role_manager_whitelist", {}))
    rmw = {k: v for k, v in rmw.items() if isinstance(v, list)}
    tiers = _strip_meta(ohc.get("role_tiers", {}))
    tiers = {k: int(v) for k, v in tiers.items() if isinstance(v, (int, float))}

    tests = 0
    staff_idx = _build_staff_index(users, tiers)

    # Test 1: tree builds
    tree, orphans, reports_of = build_reporting_tree(users, rmw, tiers, 4)
    assert len(tree) > 0
    tests += 1

    # Test 2: real MD is orphan (not synthetic EXEC-*)
    md_code = _select_md_code(staff_idx, tiers)
    assert md_code in orphans, "MD should be in orphans list"
    assert not md_code.startswith("EXEC-"), (
        f"MD detection should prefer real staff; got synthetic {md_code}"
    )
    tests += 1

    # Test 3: tree has no cycles
    for code in tree:
        visited = {code}
        cur = code
        while cur in tree:
            cur = tree[cur]
            assert cur not in visited, f"cycle detected starting from {code}"
            visited.add(cur)
            if len(visited) > 20:
                break
    tests += 1

    # Test 4: reports_of inverse is correct
    for child, parent in tree.items():
        assert child in reports_of.get(parent, []), (
            f"{child} → {parent} not in reports_of"
        )
    tests += 1

    # Test 5: substantial coverage given canonical whitelist limits
    # (whitelist has 26 subordinate roles; data has more — roles not in
    # canonical remain orphans. v10.398 admin work extends the whitelist.)
    coverage = len(tree) / len(staff_idx)
    assert coverage >= 0.7, f"only {coverage:.1%} of staff have managers"
    tests += 1

    # Test 6: within-branch sanity — branch staff don't report to managers at
    # different branches (unless tier <= 3, i.e., crossing into HQ/regional)
    cross_branch_violations = 0
    for child, parent in tree.items():
        c_info = staff_idx.get(child, {})
        p_info = staff_idx.get(parent, {})
        p_tier = tiers.get(p_info.get("role", ""), -1)
        if p_tier >= 4 and c_info.get("unit") != p_info.get("unit"):
            cross_branch_violations += 1
    assert cross_branch_violations == 0, (
        f"{cross_branch_violations} branch-level cross-branch in tree"
    )
    tests += 1

    print(f"✓ cascade_regenerator self_test passed ({tests} tests)")
    print(f"  Staff indexed: {len(staff_idx)}")
    print(f"  Tree size:     {len(tree)}")
    print(f"  Orphans:       {len(orphans)}")
    print(f"  Managers:      {len(reports_of)}")


if __name__ == "__main__":
    self_test()
