"""utils/bank_targets_schema.py — v10.371 Multi-Level Targets Schema.

Fourth concrete unification step from the v10.367 architecture arc. Extends
bank_targets.json from a flat 2-segment schema (`<metric>|<year>`) to a
hierarchical 4-segment schema (`<metric>|<level>|<entity>|<year>`).

Why this matters
----------------
After v10.368-v10.370 the ACTUALS side of profitability has a fully-reconciled
four-deep tree: Bank → SBU → Branch → Customer (atomic) + Staff. But the
TARGETS side still only has bank-level numbers. The MD's "Is the bank on
track?" answer can be given for the whole bank but not for any SBU, branch,
or RM. v10.371 closes that gap by allowing targets at every level.

Schema
------
Legacy (kept for backward compatibility):
    "PBT|2026": {target, buffer_pct, ...}

New (added incrementally — admin populates per-level):
    "PBT|bank|all|2026":              {target, buffer_pct, ...}
    "PBT|sbu|Retail Banking|2026":    {target, buffer_pct, ...}
    "PBT|sbu|Commercial Banking|2026": {target, buffer_pct, ...}
    "PBT|branch|BR001|2026":          {target, buffer_pct, ...}
    "PBT|branch|BR002|2026":          {target, buffer_pct, ...}
    "PBT|staff|300046|2026":          {target, buffer_pct, ...}
    "PBT|customer|1000000088|2026":   {target, buffer_pct, ...}  # rare

Migration (in-memory on load — file stays as written by admin):
    "PBT|2026" → exposed AS-IF "PBT|bank|all|2026"

Hierarchy identity
------------------
For any (metric, year) where children targets exist at a level:

    Σ(targets at child level for that metric/year)
        ==  target at parent level (within tolerance)

Tolerance default: 0.1% (10 basis points). Configurable per-call.

Levels (hierarchical, top to bottom):
    bank  →  sbu | branch | staff | customer

(SBU and Branch are PARALLEL views from the bank, not hierarchical to
each other — a customer belongs to both an SBU and a branch. So we
check Σ(sbu) == bank AND Σ(branch) == bank AND Σ(staff) == bank AND
Σ(customer) == bank, not Σ(staff) == Σ(branch).)

Enforcement
-----------
validate_target_hierarchy() returns a list of violations (empty list on
success). On save, callers SHOULD reject if violations exist unless
explicit override flag `_force_unbalanced_targets=True` is set. The
enforcement decision lives at the admin UI / API layer; this module
provides the validation primitive.

Module purity
-------------
Pure schema utility. Zero imports from utils.*. Reads only the bank_targets
dict you pass in. Self-test uses synthetic dicts.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

REPO = Path(__file__).resolve().parent.parent
DATA_DIR = REPO / "data"

LEVEL_BANK = "bank"
LEVEL_SBU = "sbu"
LEVEL_BRANCH = "branch"
LEVEL_STAFF = "staff"
LEVEL_CUSTOMER = "customer"
ALL_LEVELS = (LEVEL_BANK, LEVEL_SBU, LEVEL_BRANCH, LEVEL_STAFF, LEVEL_CUSTOMER)

BANK_ENTITY_ALL = "all"  # Conventional entity name for bank-level targets

DEFAULT_TOLERANCE_PCT = Decimal("0.1")  # 10bp

# Sentinel for override flag in bank_targets.json
OVERRIDE_FLAG_KEY = "_force_unbalanced_targets"


@dataclass(frozen=True)
class TargetKey:
    """Parsed target key: <metric>|<level>|<entity>|<year>."""
    metric: str
    level: str   # one of ALL_LEVELS
    entity: str  # 'all' for bank; SBU name, branch_code, staff_code, or CIF
    year: str

    def compose(self) -> str:
        return f"{self.metric}|{self.level}|{self.entity}|{self.year}"


def parse_target_key(key: str) -> Optional[TargetKey]:
    """Parse a target key. Handles both legacy 2-segment and new 4-segment.

    Legacy: "PBT|2026"             → metric=PBT, level=bank, entity=all, year=2026
    New:    "PBT|sbu|Retail|2026"  → metric=PBT, level=sbu,  entity=Retail, year=2026

    Returns None for keys that don't look like target keys (starts with '_'
    for schema metadata, or doesn't have at least 2 segments).
    """
    if not key or key.startswith("_"):
        return None
    parts = key.split("|")
    if len(parts) == 2:
        # Legacy 2-segment: implicit bank|all
        return TargetKey(
            metric=parts[0].strip(),
            level=LEVEL_BANK,
            entity=BANK_ENTITY_ALL,
            year=parts[1].strip(),
        )
    if len(parts) == 4:
        # New 4-segment
        return TargetKey(
            metric=parts[0].strip(),
            level=parts[1].strip(),
            entity=parts[2].strip(),
            year=parts[3].strip(),
        )
    # Unrecognised
    return None


def compose_target_key(
    metric: str, level: str, entity: str, year: str
) -> str:
    """Compose a 4-segment target key in canonical form."""
    return TargetKey(metric, level, entity, year).compose()


def migrate_legacy_targets(
    raw_targets: Dict[str, Any]
) -> Dict[str, Any]:
    """Return a NEW dict with legacy 2-segment keys exposed AS the equivalent
    4-segment keys. Original raw_targets is not modified.

    Legacy key "PBT|2026" → exposed under both:
        "PBT|2026" (original, preserved)
        "PBT|bank|all|2026" (alias)

    Metadata keys (those starting with '_') are preserved as-is.
    """
    migrated: Dict[str, Any] = {}
    for k, v in raw_targets.items():
        if k.startswith("_"):
            migrated[k] = v
            continue
        migrated[k] = v
        parsed = parse_target_key(k)
        if parsed and len(k.split("|")) == 2:
            # Legacy — also expose under the canonical 4-segment alias
            alias = parsed.compose()
            if alias != k and alias not in migrated:
                migrated[alias] = v
    return migrated


def get_target(
    targets: Dict[str, Any],
    metric: str,
    level: str,
    entity: str,
    year: str,
) -> Optional[Dict[str, Any]]:
    """Read a target. Honors legacy fallback for bank|all level."""
    # Try canonical first
    canonical = compose_target_key(metric, level, entity, year)
    if canonical in targets:
        return targets[canonical]
    # Fallback: bank|all has legacy equivalent
    if level == LEVEL_BANK and entity == BANK_ENTITY_ALL:
        legacy = f"{metric}|{year}"
        if legacy in targets:
            return targets[legacy]
    return None


def set_target(
    targets: Dict[str, Any],
    metric: str,
    level: str,
    entity: str,
    year: str,
    value: Dict[str, Any],
) -> Dict[str, Any]:
    """Write a target. Always writes the canonical 4-segment key.

    Returns the targets dict (modified in place, also returned for chaining).
    """
    if level not in ALL_LEVELS:
        raise ValueError(f"level '{level}' not in {ALL_LEVELS}")
    if not isinstance(value, dict):
        raise ValueError("value must be a dict (at minimum {'target': N})")
    if "target" not in value:
        raise ValueError("value dict must include 'target' key")
    canonical = compose_target_key(metric, level, entity, year)
    targets[canonical] = value
    return targets


def list_targets_at_level(
    targets: Dict[str, Any],
    metric: str,
    level: str,
    year: str,
) -> List[Tuple[str, Dict[str, Any]]]:
    """Return all (entity, target_record) pairs for a given (metric, level, year).

    Walks both legacy and new schema keys. For bank|all, includes the legacy
    2-segment key as canonical bank|all.
    """
    out: List[Tuple[str, Dict[str, Any]]] = []
    seen_entities = set()
    for key, value in targets.items():
        if key.startswith("_"):
            continue
        parsed = parse_target_key(key)
        if parsed is None:
            continue
        if parsed.metric != metric:
            continue
        if parsed.level != level:
            continue
        if parsed.year != year:
            continue
        if parsed.entity in seen_entities:
            continue
        seen_entities.add(parsed.entity)
        out.append((parsed.entity, value))
    return out


def sum_children_at_level(
    targets: Dict[str, Any],
    metric: str,
    level: str,
    year: str,
) -> Decimal:
    """Σ of target values at a level. Returns 0 if no entries."""
    total = Decimal("0")
    for _entity, rec in list_targets_at_level(targets, metric, level, year):
        try:
            total += Decimal(str(rec.get("target", 0)))
        except Exception:
            pass
    return total


def validate_target_hierarchy(
    targets: Dict[str, Any],
    metric: str,
    year: str,
    tolerance_pct: Optional[Decimal] = None,
    levels_to_check: Optional[Tuple[str, ...]] = None,
) -> List[str]:
    """Verify Σ(child level targets) == bank target for each child level
    that has any populated entries.

    Skips child levels with no populated entries (you don't have to populate
    every level — sparse is OK). Only checks levels that have data.

    Returns list of violation messages (empty list = pass). Honors the
    `_force_unbalanced_targets` override flag in `targets`.

    Args:
        targets: bank_targets dict (after migrate_legacy_targets if desired)
        metric: e.g. 'PBT'
        year: e.g. '2026'
        tolerance_pct: max deviation as percentage of bank target.
                       Default 0.1% (10bp).
        levels_to_check: which child levels to verify. Default: all four
                         child levels (sbu, branch, staff, customer).
    """
    violations: List[str] = []

    if targets.get(OVERRIDE_FLAG_KEY, False):
        return ["[OVERRIDE] _force_unbalanced_targets=True — validation skipped"]

    tol = tolerance_pct if tolerance_pct is not None else DEFAULT_TOLERANCE_PCT
    levels = levels_to_check or (
        LEVEL_SBU, LEVEL_BRANCH, LEVEL_STAFF, LEVEL_CUSTOMER,
    )

    # Bank-level (parent) target
    bank_rec = get_target(
        targets, metric, LEVEL_BANK, BANK_ENTITY_ALL, year
    )
    if bank_rec is None:
        # No bank target — cannot validate children against it
        # If any child level has data, that's a violation
        for level in levels:
            children = list_targets_at_level(targets, metric, level, year)
            if children:
                violations.append(
                    f"{metric}|{level}|*|{year} has {len(children)} entries "
                    f"but no parent {metric}|bank|all|{year} target set"
                )
        return violations

    bank_target = Decimal(str(bank_rec.get("target", 0)))
    if bank_target == 0:
        # No nonzero parent — nothing to validate against
        return violations

    abs_tolerance = abs(bank_target) * tol / Decimal("100")

    for level in levels:
        children = list_targets_at_level(targets, metric, level, year)
        if not children:
            continue  # Sparse is OK
        child_sum = sum_children_at_level(targets, metric, level, year)
        delta = abs(bank_target - child_sum)
        if delta > abs_tolerance:
            pct = float(delta / abs(bank_target) * 100)
            violations.append(
                f"{metric}|{year} hierarchy: Σ({level}|*) = "
                f"{float(child_sum):,.0f} != bank|all {float(bank_target):,.0f} "
                f"(Δ {float(delta):,.0f}, {pct:.2f}% > {float(tol)}%); "
                f"{len(children)} child entries"
            )

    return violations


def load_bank_targets(
    path: Optional[Path] = None,
    migrate: bool = True,
) -> Dict[str, Any]:
    """Load bank_targets.json, optionally migrating legacy keys to new schema.

    Args:
        path: defaults to data/bank_targets.json
        migrate: when True (default), legacy 2-segment keys are also exposed
                 under their canonical 4-segment alias. Returns a NEW dict.
    """
    p = path if path is not None else (DATA_DIR / "bank_targets.json")
    if not p.exists():
        return {}
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if migrate:
        return migrate_legacy_targets(raw)
    return raw


def save_bank_targets(
    targets: Dict[str, Any],
    path: Optional[Path] = None,
    strip_aliases: bool = True,
) -> None:
    """Write bank_targets.json. By default strips alias entries (the 4-segment
    bank|all entries that mirror legacy 2-segment keys) to keep the file
    minimal — admins write either legacy OR new format, not both.
    """
    p = path if path is not None else (DATA_DIR / "bank_targets.json")
    out: Dict[str, Any] = {}
    for k, v in targets.items():
        if not strip_aliases:
            out[k] = v
            continue
        parsed = parse_target_key(k)
        if parsed is None:
            out[k] = v
            continue
        # If it's the canonical bank|all 4-segment AND a legacy 2-segment
        # exists, drop the canonical alias (legacy wins for backward compat)
        if (parsed.level == LEVEL_BANK and parsed.entity == BANK_ENTITY_ALL):
            legacy = f"{parsed.metric}|{parsed.year}"
            if legacy in targets and k != legacy:
                continue  # drop the 4-segment alias
        out[k] = v
    p.write_text(json.dumps(out, indent=2), encoding="utf-8")


def self_test() -> None:
    """v10.371 self_test — synthetic dicts."""
    tests_run = 0

    # Test 1: parse legacy key
    k = parse_target_key("PBT|2026")
    assert k is not None
    assert k.metric == "PBT"
    assert k.level == LEVEL_BANK
    assert k.entity == BANK_ENTITY_ALL
    assert k.year == "2026"
    tests_run += 1

    # Test 2: parse new 4-segment key
    k = parse_target_key("PBT|sbu|Retail Banking|2026")
    assert k.metric == "PBT"
    assert k.level == "sbu"
    assert k.entity == "Retail Banking"
    tests_run += 1

    # Test 3: parse invalid keys
    assert parse_target_key("") is None
    assert parse_target_key("_schema_version") is None
    assert parse_target_key("malformed|three|segments") is None  # 3 segments not allowed
    tests_run += 1

    # Test 4: compose
    assert compose_target_key("PBT", "sbu", "Retail", "2026") == "PBT|sbu|Retail|2026"
    tests_run += 1

    # Test 5: migrate legacy → 4-segment alias
    raw = {"PBT|2026": {"target": 1000, "buffer_pct": 0}}
    mig = migrate_legacy_targets(raw)
    assert "PBT|2026" in mig
    assert "PBT|bank|all|2026" in mig
    # Both point to same record
    assert mig["PBT|2026"] is mig["PBT|bank|all|2026"]
    tests_run += 1

    # Test 6: get_target with legacy fallback
    raw = {"PBT|2026": {"target": 1000, "buffer_pct": 0}}
    rec = get_target(raw, "PBT", LEVEL_BANK, BANK_ENTITY_ALL, "2026")
    assert rec is not None and rec["target"] == 1000
    tests_run += 1

    # Test 7: set_target writes canonical 4-segment
    t = {}
    set_target(t, "PBT", LEVEL_SBU, "Retail Banking", "2026", {"target": 500, "buffer_pct": 0})
    assert "PBT|sbu|Retail Banking|2026" in t
    tests_run += 1

    # Test 8: set_target rejects invalid level
    try:
        set_target({}, "PBT", "bogus_level", "X", "2026", {"target": 1})
        assert False, "should have raised"
    except ValueError:
        pass
    tests_run += 1

    # Test 9: sum_children_at_level — empty
    assert sum_children_at_level({}, "PBT", LEVEL_SBU, "2026") == Decimal("0")
    tests_run += 1

    # Test 10: Σ identity holds
    t = {"PBT|2026": {"target": 1000}}
    set_target(t, "PBT", LEVEL_SBU, "Retail", "2026", {"target": 600})
    set_target(t, "PBT", LEVEL_SBU, "Commercial", "2026", {"target": 400})
    assert sum_children_at_level(t, "PBT", LEVEL_SBU, "2026") == Decimal("1000")
    violations = validate_target_hierarchy(t, "PBT", "2026")
    assert violations == [], f"expected no violations, got {violations}"
    tests_run += 1

    # Test 11: Σ identity broken — surfaces violation
    t = {"PBT|2026": {"target": 1000}}
    set_target(t, "PBT", LEVEL_SBU, "Retail", "2026", {"target": 600})
    set_target(t, "PBT", LEVEL_SBU, "Commercial", "2026", {"target": 300})  # short by 100
    violations = validate_target_hierarchy(t, "PBT", "2026")
    assert len(violations) > 0, "should detect Σ(sbu) != bank"
    assert "PBT|2026 hierarchy" in violations[0]
    tests_run += 1

    # Test 12: tolerance honored
    t = {"PBT|2026": {"target": 1000}}
    set_target(t, "PBT", LEVEL_BRANCH, "BR01", "2026", {"target": 1001})  # 0.1% off
    violations = validate_target_hierarchy(t, "PBT", "2026", tolerance_pct=Decimal("0.2"))
    # Within 0.2% tolerance — should pass
    assert violations == []
    violations = validate_target_hierarchy(t, "PBT", "2026", tolerance_pct=Decimal("0.05"))
    # Tighter tolerance — should fail
    assert len(violations) > 0
    tests_run += 1

    # Test 13: sparse levels OK — only check populated
    t = {"PBT|2026": {"target": 1000}}
    set_target(t, "PBT", LEVEL_SBU, "Retail", "2026", {"target": 1000})
    # No branch/staff/customer targets — should NOT fail (sparse OK)
    violations = validate_target_hierarchy(t, "PBT", "2026")
    assert violations == []
    tests_run += 1

    # Test 14: bank target missing but children exist → violation
    t = {}
    set_target(t, "PBT", LEVEL_SBU, "Retail", "2026", {"target": 500})
    violations = validate_target_hierarchy(t, "PBT", "2026")
    assert len(violations) > 0
    assert "no parent" in violations[0]
    tests_run += 1

    # Test 15: override flag short-circuits
    t = {"PBT|2026": {"target": 1000},
         OVERRIDE_FLAG_KEY: True}
    set_target(t, "PBT", LEVEL_SBU, "Retail", "2026", {"target": 1})  # massively off
    violations = validate_target_hierarchy(t, "PBT", "2026")
    assert len(violations) == 1
    assert "OVERRIDE" in violations[0]
    tests_run += 1

    # Test 16: list_targets_at_level
    t = {"PBT|2026": {"target": 1000}}
    set_target(t, "PBT", LEVEL_SBU, "Retail", "2026", {"target": 600})
    set_target(t, "PBT", LEVEL_SBU, "Commercial", "2026", {"target": 400})
    children = list_targets_at_level(t, "PBT", LEVEL_SBU, "2026")
    assert len(children) == 2
    entities = {e for e, _ in children}
    assert entities == {"Retail", "Commercial"}
    tests_run += 1

    print(f"✓ bank_targets_schema self-test passed ({tests_run} tests)")


if __name__ == "__main__":
    self_test()
