"""Admin Validation Engine — v10.431 (admin polish).

Pre-validates admin edits BEFORE they're written to kpi_library.json or
other config stores. Prevents the exact classes of bugs the BSC Rescue
arc (v10.424-v10.429) fixed:

  - Non-canonical pillars (v10.425 / v10.426 fixed)
  - Duplicate IDs / names (no auto-fix; v10.426 enforced canonical)
  - Pillar weights not summing to 1.0 (data integrity)
  - role_kpis referencing unresolvable IDs (v10.427 CODE_ALIAS_MAP)
  - Negative / zero weights, out-of-range values

Design pattern: each validator returns a ValidationResult with
errors (block save), warnings (informational), and passes (positive
confirmation). UI consumers can render colored panels per category.

Public API (API-first, ZERO streamlit):
  - validate_kpi_change(new_kpi, existing_lib) -> ValidationResult
  - validate_pillar_weights(weights) -> ValidationResult
  - validate_role_kpis_change(role, kpi_ids, lib) -> ValidationResult
  - validate_full_library(lib) -> ValidationResult
  - validate_target_override(staff, kpi, target) -> ValidationResult

Each validation is read-only and side-effect-free. No file writes; no
network calls; no engine state mutations.

Shipped: v10.431.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

REPO_ROOT = Path(__file__).parent.parent
DATA_DIR = REPO_ROOT / "data"

# Canonical (v10.423)
CANONICAL_PILLARS: Set[str] = {
    "Financial",
    "Customer Focus",
    "Operational Excellence",
    "People & Learning",
}

# Allowed direction values for KPI metadata
ALLOWED_DIRECTIONS: Set[str] = {"higher", "lower"}

# Weight tolerance for "sum should equal 1.0" checks
PILLAR_WEIGHT_TOLERANCE = 0.001  # 0.1% — pillar weights are precise

# Reasonable bounds for per-KPI weight (not pillar weight)
MIN_KPI_WEIGHT = 0.01
MAX_KPI_WEIGHT = 0.50


# ════════════════════════════════════════════════════════════════════
# Types
# ════════════════════════════════════════════════════════════════════

@dataclass
class ValidationIssue:
    severity: str       # "error" | "warning" | "info"
    field: str
    message: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ValidationResult:
    valid: bool                          # False if any errors present
    errors: List[ValidationIssue]
    warnings: List[ValidationIssue]
    info: List[ValidationIssue]
    timestamp: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "valid": self.valid,
            "errors": [e.to_dict() for e in self.errors],
            "warnings": [w.to_dict() for w in self.warnings],
            "info": [i.to_dict() for i in self.info],
            "timestamp": self.timestamp,
        }

    @classmethod
    def empty(cls) -> "ValidationResult":
        return cls(
            valid=True, errors=[], warnings=[], info=[],
            timestamp=datetime.now().isoformat(),
        )

    def add_error(self, field_: str, msg: str) -> None:
        self.errors.append(ValidationIssue("error", field_, msg))
        self.valid = False

    def add_warning(self, field_: str, msg: str) -> None:
        self.warnings.append(ValidationIssue("warning", field_, msg))

    def add_info(self, field_: str, msg: str) -> None:
        self.info.append(ValidationIssue("info", field_, msg))


# ════════════════════════════════════════════════════════════════════
# Helpers
# ════════════════════════════════════════════════════════════════════

def _load_lib() -> Dict[str, Any]:
    path = DATA_DIR / "kpi_library.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _existing_ids_and_names(
    lib: Dict[str, Any],
) -> Tuple[Set[str], Set[str], Set[str]]:
    """Return (ids, names, aliases) sets from current library."""
    ids: Set[str] = set()
    names: Set[str] = set()
    aliases: Set[str] = set()
    for k in lib.get("kpis", []):
        if not isinstance(k, dict):
            continue
        if k.get("id"):
            ids.add(str(k["id"]).strip())
        if k.get("name"):
            names.add(str(k["name"]).strip())
        for a in k.get("aliases", []) or []:
            if a:
                aliases.add(str(a).strip())
    return ids, names, aliases


# ════════════════════════════════════════════════════════════════════
# Public API — KPI library entry validation
# ════════════════════════════════════════════════════════════════════

def validate_kpi_change(
    new_kpi: Dict[str, Any],
    existing_lib: Optional[Dict[str, Any]] = None,
    is_update: bool = False,
) -> ValidationResult:
    """Validate a single KPI library entry (add or update).

    Args:
        new_kpi: the dict being proposed for insertion or update
        existing_lib: optional library snapshot for collision checks.
            If None, loads from disk.
        is_update: True if updating an existing entry (skips ID-collision
            check). Default False (add).
    """
    result = ValidationResult.empty()

    if not isinstance(new_kpi, dict):
        result.add_error("entry", "KPI entry must be a dict")
        return result

    # Required fields
    kid = str(new_kpi.get("id", "")).strip()
    kname = str(new_kpi.get("name", "")).strip()
    pillar = str(new_kpi.get("pillar", "")).strip()
    weight = new_kpi.get("weight")

    if not kid:
        result.add_error("id", "id is required")
    if not kname:
        result.add_error("name", "name is required")
    if not pillar:
        result.add_error("pillar", "pillar is required")

    # Canonical pillar
    if pillar and pillar not in CANONICAL_PILLARS:
        result.add_error(
            "pillar",
            f"pillar '{pillar}' is non-canonical. "
            f"Must be one of: {sorted(CANONICAL_PILLARS)}",
        )

    # Weight type + range
    if weight is None:
        result.add_warning("weight", "weight not specified — will default")
    else:
        try:
            wf = float(weight)
            if wf < MIN_KPI_WEIGHT:
                result.add_warning(
                    "weight",
                    f"weight {wf} is below {MIN_KPI_WEIGHT} — "
                    f"KPI may have negligible impact",
                )
            elif wf > MAX_KPI_WEIGHT:
                result.add_warning(
                    "weight",
                    f"weight {wf} exceeds {MAX_KPI_WEIGHT} — "
                    f"KPI may overwhelm scoring",
                )
        except (ValueError, TypeError):
            result.add_error("weight", f"weight must be numeric, got {weight!r}")

    # Direction (if specified)
    direction = str(new_kpi.get("direction", "")).strip()
    if direction and direction.lower() not in ALLOWED_DIRECTIONS:
        result.add_error(
            "direction",
            f"direction '{direction}' invalid. "
            f"Must be one of: {sorted(ALLOWED_DIRECTIONS)}",
        )

    # ID format — recommend UPPER_SNAKE_CASE or K-prefixed
    if kid and not re.match(r"^[A-Z][A-Z0-9_]+$|^K\d{3}$", kid):
        result.add_warning(
            "id",
            f"id '{kid}' doesn't follow UPPER_SNAKE_CASE or K-prefix convention",
        )

    # Collision check
    if not is_update and (result.valid or len(result.errors) == 0):
        lib = existing_lib if existing_lib is not None else _load_lib()
        existing_ids, existing_names, existing_aliases = _existing_ids_and_names(lib)
        if kid in existing_ids:
            result.add_error(
                "id", f"id '{kid}' already exists in library",
            )
        if kid in existing_aliases:
            result.add_error(
                "id",
                f"id '{kid}' clashes with existing alias",
            )
        if kname in existing_names:
            result.add_error(
                "name", f"name '{kname}' already exists in library",
            )

    # Optional positive infos
    if result.valid and not result.errors:
        result.add_info("status", f"KPI '{kname}' validates clean")

    return result


# ════════════════════════════════════════════════════════════════════
# Public API — Pillar weights validation
# ════════════════════════════════════════════════════════════════════

def validate_pillar_weights(
    weights: Dict[str, float],
) -> ValidationResult:
    """Validate a pillar_weights dict.

    Must contain all 4 canonical pillars and sum to 1.0 (within tolerance).
    """
    result = ValidationResult.empty()

    if not isinstance(weights, dict):
        result.add_error("weights", "pillar_weights must be a dict")
        return result

    # All 4 canonical pillars present
    missing = CANONICAL_PILLARS - set(weights.keys())
    extra = set(weights.keys()) - CANONICAL_PILLARS
    if missing:
        result.add_error(
            "keys",
            f"missing canonical pillars: {sorted(missing)}",
        )
    if extra:
        result.add_error(
            "keys",
            f"non-canonical pillar keys: {sorted(extra)}",
        )

    # Each value numeric + non-negative
    total = 0.0
    for p, w in weights.items():
        try:
            wf = float(w)
        except (ValueError, TypeError):
            result.add_error(
                f"weights.{p}",
                f"weight must be numeric, got {w!r}",
            )
            continue
        if wf < 0:
            result.add_error(
                f"weights.{p}",
                f"weight {wf} is negative",
            )
        if wf > 1.0:
            result.add_error(
                f"weights.{p}",
                f"weight {wf} exceeds 1.0",
            )
        total += wf

    # Sum check
    if not result.errors and abs(total - 1.0) > PILLAR_WEIGHT_TOLERANCE:
        result.add_error(
            "sum",
            f"weights sum to {total:.4f}, expected 1.0 "
            f"(tolerance {PILLAR_WEIGHT_TOLERANCE})",
        )

    # Sanity warnings: extreme distributions
    if not result.errors and weights:
        for p, w in weights.items():
            wf = float(w)
            if wf < 0.05:
                result.add_warning(
                    f"weights.{p}",
                    f"'{p}' weight is {wf} (<5%) — "
                    f"may indicate the pillar is under-emphasized",
                )
            elif wf > 0.60:
                result.add_warning(
                    f"weights.{p}",
                    f"'{p}' weight is {wf} (>60%) — "
                    f"may dominate the scorecard",
                )

    if result.valid and not result.errors:
        result.add_info(
            "status",
            f"Pillar weights validate clean: sum = {total:.4f}",
        )

    return result


# ════════════════════════════════════════════════════════════════════
# Public API — Role-KPI mapping validation
# ════════════════════════════════════════════════════════════════════

def validate_role_kpis_change(
    role: str,
    kpi_ids: List[str],
    existing_lib: Optional[Dict[str, Any]] = None,
) -> ValidationResult:
    """Validate a role_kpis[role] assignment.

    All listed KPI IDs must resolve in kpi_library by id, name, or alias.
    """
    result = ValidationResult.empty()

    if not role or not isinstance(role, str):
        result.add_error("role", "role is required")
        return result
    if not isinstance(kpi_ids, list):
        result.add_error("kpi_ids", "kpi_ids must be a list")
        return result
    if not kpi_ids:
        result.add_warning("kpi_ids", "role has no KPIs assigned")

    # Unique check
    if len(kpi_ids) != len(set(kpi_ids)):
        seen: Set[str] = set()
        dupes = set()
        for k in kpi_ids:
            if k in seen:
                dupes.add(k)
            seen.add(k)
        result.add_error(
            "kpi_ids",
            f"duplicate KPI IDs in role: {sorted(dupes)}",
        )

    # Resolve check
    lib = existing_lib if existing_lib is not None else _load_lib()
    existing_ids, existing_names, existing_aliases = _existing_ids_and_names(lib)
    universe = existing_ids | existing_names | existing_aliases

    unresolved = [k for k in kpi_ids if k not in universe]
    if unresolved:
        result.add_error(
            "kpi_ids",
            f"unresolved KPI references (not in library): "
            f"{unresolved[:10]}",
        )

    # Coverage warning — too few KPIs for role
    if len(kpi_ids) < 3 and not result.errors:
        result.add_warning(
            "kpi_ids",
            f"role has only {len(kpi_ids)} KPIs — "
            f"BSC may be too narrow",
        )

    if result.valid and not result.errors:
        result.add_info(
            "status",
            f"Role '{role}' validates: {len(kpi_ids)} KPIs all resolve",
        )

    return result


# ════════════════════════════════════════════════════════════════════
# Public API — Target override validation
# ════════════════════════════════════════════════════════════════════

def validate_target_override(
    staff_name: str,
    kpi_name: str,
    new_target: Any,
    current_target: Optional[float] = None,
) -> ValidationResult:
    """Validate an admin's manual target override for a staff member."""
    result = ValidationResult.empty()

    if not staff_name:
        result.add_error("staff_name", "staff_name is required")
    if not kpi_name:
        result.add_error("kpi_name", "kpi_name is required")

    try:
        nt = float(new_target)
    except (ValueError, TypeError):
        result.add_error(
            "new_target",
            f"new_target must be numeric, got {new_target!r}",
        )
        return result

    if nt < 0:
        result.add_warning(
            "new_target",
            f"new_target {nt} is negative (only valid for inverse KPIs)",
        )

    # If current_target provided, flag large swings
    if current_target is not None and current_target > 0:
        try:
            ct = float(current_target)
            change_pct = abs(nt - ct) / ct * 100
            if change_pct > 50:
                result.add_warning(
                    "new_target",
                    f"target changes by {change_pct:.1f}% "
                    f"({ct} -> {nt}) — verify intent",
                )
        except (ValueError, TypeError):
            pass

    if result.valid and not result.errors:
        result.add_info(
            "status",
            f"Target override validates: {staff_name} / {kpi_name} -> {nt}",
        )

    return result


# ════════════════════════════════════════════════════════════════════
# Public API — Full library validation (snapshot)
# ════════════════════════════════════════════════════════════════════

def validate_full_library(
    lib: Optional[Dict[str, Any]] = None,
) -> ValidationResult:
    """Snapshot validation of the entire kpi_library.json.

    Surfaces:
      - duplicate IDs/names across kpis array
      - non-canonical pillars in any entry
      - pillar weights not summing to 1.0
      - orphan role_kpis references
    """
    result = ValidationResult.empty()

    if lib is None:
        lib = _load_lib()
    if not lib:
        result.add_error("library", "kpi_library.json missing or empty")
        return result

    # Duplicate IDs
    from collections import Counter
    ids = [
        str(k.get("id", "")).strip()
        for k in lib.get("kpis", [])
        if isinstance(k, dict) and k.get("id")
    ]
    id_counts = Counter(ids)
    dupes = {i: c for i, c in id_counts.items() if c > 1}
    if dupes:
        result.add_error("kpis.id", f"duplicate IDs: {dupes}")

    # Duplicate names
    names = [
        str(k.get("name", "")).strip()
        for k in lib.get("kpis", [])
        if isinstance(k, dict) and k.get("name")
    ]
    name_counts = Counter(names)
    dupe_names = {n: c for n, c in name_counts.items() if c > 1}
    if dupe_names:
        result.add_error("kpis.name", f"duplicate names: {dupe_names}")

    # Non-canonical pillars in entries
    non_canon_kpis = [
        k.get("id")
        for k in lib.get("kpis", [])
        if isinstance(k, dict) and k.get("pillar") and k["pillar"] not in CANONICAL_PILLARS
    ]
    if non_canon_kpis:
        result.add_error(
            "kpis.pillar",
            f"{len(non_canon_kpis)} entries with non-canonical pillar: "
            f"{non_canon_kpis[:10]}",
        )

    # Pillar weights
    pw = lib.get("pillar_weights", {})
    if pw:
        pw_result = validate_pillar_weights(pw)
        for e in pw_result.errors:
            result.errors.append(e)
            result.valid = False
        for w in pw_result.warnings:
            result.warnings.append(w)

    # Role-KPI orphans
    role_kpis = lib.get("role_kpis", {})
    if role_kpis:
        existing_ids, existing_names, existing_aliases = _existing_ids_and_names(lib)
        universe = existing_ids | existing_names | existing_aliases
        for role, kpi_list in role_kpis.items():
            if not isinstance(kpi_list, list):
                continue
            orphans = [k for k in kpi_list if k not in universe]
            if orphans:
                result.add_warning(
                    f"role_kpis.{role}",
                    f"{len(orphans)} unresolved KPI references: "
                    f"{orphans[:5]}",
                )

    if result.valid and not result.errors:
        result.add_info(
            "status",
            f"Library validates clean: {len(ids)} KPIs, "
            f"{len(role_kpis)} roles configured",
        )

    return result


# ════════════════════════════════════════════════════════════════════
# Public API — Role-KPI code alias migration (v10.431)
# ════════════════════════════════════════════════════════════════════

# Mapping of legacy SNAKE_CASE codes (from old role_kpis) -> canonical
# library entry names. Each mapping adds the code as an alias on the
# corresponding library entry, so role_kpis lookups resolve.
#
# Built by validation: codes that appeared as "unresolved" warnings in
# validate_full_library, manually disambiguated against library names.
LEGACY_CODE_ALIAS_MAP: Dict[str, str] = {
    "ACCOUNT_DORMANCY":       "Account Dormancy",
    "BUSINESS_BORROWERS":     "Number of Business Borrowers",
    "CASA_RATIO":             "CASA Ratio",
    "CHANNEL_DORMANCY":       "Channel Dormancy",
    "COLLECTION_THROUGHPUT":  "Collection Throughput",
    "COMMERCIAL_DEPOSIT":     "Commercial Deposit Growth",
    "COMPLIANCE":             "Compliance Score",
    "CX_SCORE":               "CX Score",
    "DIGITAL_ACT":            "Digital Transactions (%)",
    "DISB_CORPORATE":         "Disbursements Corporate Loans",
    "DISB_MSME":              "Disbursements MSME Loans",
    "DISB_RETAIL":            "Disbursements Retail Loans",
    "FEES_COMM":              "Fee Income (KES M)",
    "LOAN_DISB":              "Loans Disbursed (KES M)",
    "NEW_CUST":               "New Customers Acquired",
    "NPS":                    "WB NPS Score",
    "RETAIL_MSME_DEPOSIT":    "Retail & MSME Deposit Growth",
    "STAFF_PROD":             "Staff Productivity",
    "TOP100_CUSTOMERS":       "Top 100 Customers Deposit",
    "TOTAL_NFI":              "Total NFI",
    "TRADE_FIN":              "Trade Finance Revenue",
    "TRANSACTIONS":           "Digital Transactions (%)",
    # ACTIVE_ACCTS is ambiguous — left for admin disambiguation
}


@dataclass
class LegacyAliasResult:
    dry_run: bool
    aliases_added: int
    library_entries_updated: int
    skipped_unresolved: List[str]
    backup_path: str
    timestamp: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def apply_legacy_code_aliases(
    dry_run: bool = True,
) -> LegacyAliasResult:
    """Add LEGACY_CODE_ALIAS_MAP entries as aliases on library KPIs.

    For each (SNAKE_CASE, canonical_name) pair, find the library entry
    by name and append the SNAKE_CASE code to its `aliases` list.

    Idempotent. Safety-first: dry_run=True default. Creates backup.
    """
    import shutil

    lib_path = DATA_DIR / "kpi_library.json"
    if not lib_path.exists():
        return LegacyAliasResult(
            dry_run=dry_run, aliases_added=0,
            library_entries_updated=0,
            skipped_unresolved=[], backup_path="",
            timestamp=datetime.now().isoformat(),
        )

    lib = json.loads(lib_path.read_text(encoding="utf-8"))

    # Find what would change
    to_add: List[Tuple[str, str]] = []  # (code, target_name)
    skipped: List[str] = []
    for code, target_name in LEGACY_CODE_ALIAS_MAP.items():
        target_entry = None
        for k in lib.get("kpis", []):
            if isinstance(k, dict) and str(k.get("name", "")).strip() == target_name:
                target_entry = k
                break
        if target_entry is None:
            skipped.append(code)
            continue
        existing = target_entry.get("aliases", []) or []
        if code not in existing:
            to_add.append((code, target_name))

    if dry_run:
        return LegacyAliasResult(
            dry_run=True,
            aliases_added=len(to_add),
            library_entries_updated=len({t for _, t in to_add}),
            skipped_unresolved=skipped,
            backup_path="",
            timestamp=datetime.now().isoformat(),
        )

    if not to_add:
        return LegacyAliasResult(
            dry_run=False, aliases_added=0,
            library_entries_updated=0,
            skipped_unresolved=skipped, backup_path="",
            timestamp=datetime.now().isoformat(),
        )

    # Backup
    backup_dir = DATA_DIR / "_v10431_backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup_path = backup_dir / "kpi_library.json.before"
    shutil.copy2(lib_path, backup_path)

    # Apply
    aliases_added = 0
    entries_updated: Set[str] = set()
    for code, target_name in to_add:
        for k in lib.get("kpis", []):
            if isinstance(k, dict) and str(k.get("name", "")).strip() == target_name:
                aliases = k.get("aliases", []) or []
                if code not in aliases:
                    aliases.append(code)
                    k["aliases"] = aliases
                    aliases_added += 1
                    entries_updated.add(target_name)
                break

    # Stamp
    lib["_v10431_legacy_code_aliases"] = {
        "shipped": "v10.431",
        "ts": datetime.now().isoformat(),
        "aliases_added": aliases_added,
        "entries_updated": len(entries_updated),
    }

    lib_path.write_text(
        json.dumps(lib, indent=2, default=str), encoding="utf-8",
    )

    return LegacyAliasResult(
        dry_run=False,
        aliases_added=aliases_added,
        library_entries_updated=len(entries_updated),
        skipped_unresolved=skipped,
        backup_path=str(backup_path),
        timestamp=datetime.now().isoformat(),
    )


# ════════════════════════════════════════════════════════════════════
# Self-test
# ════════════════════════════════════════════════════════════════════

def self_test() -> None:
    print("─ admin_validation_engine self-test ─")
    import re as _re

    # Zero streamlit
    text = Path(__file__).read_text()
    streamlit_imports = _re.findall(
        r"^\s*(?:import\s+streamlit|from\s+streamlit)\b",
        text, _re.MULTILINE,
    )
    assert len(streamlit_imports) == 0
    print("  ✓ Zero streamlit imports")

    # Constants
    assert len(CANONICAL_PILLARS) == 4
    print(f"  ✓ Constants: 4 pillars, 2 directions, tolerance {PILLAR_WEIGHT_TOLERANCE}")

    # KPI validation — good case
    good_kpi = {
        "id": "TEST_KPI_001", "name": "Test KPI 1",
        "pillar": "Financial", "weight": 0.05, "direction": "higher",
    }
    r = validate_kpi_change(good_kpi, existing_lib={"kpis": []})
    assert r.valid is True
    assert len(r.errors) == 0
    print(f"  ✓ KPI good case: valid")

    # KPI validation — bad pillar
    bad_kpi = {
        "id": "BAD_KPI", "name": "Bad",
        "pillar": "Process",  # non-canonical
    }
    r = validate_kpi_change(bad_kpi, existing_lib={"kpis": []})
    assert r.valid is False
    assert any("non-canonical" in e.message for e in r.errors)
    print(f"  ✓ KPI rejects non-canonical pillar")

    # KPI validation — duplicate ID
    lib_with_one = {"kpis": [{"id": "EXIST", "name": "Existing", "pillar": "Financial"}]}
    dup_kpi = {"id": "EXIST", "name": "New", "pillar": "Financial"}
    r = validate_kpi_change(dup_kpi, existing_lib=lib_with_one)
    assert r.valid is False
    assert any("already exists" in e.message for e in r.errors)
    print(f"  ✓ KPI rejects duplicate ID")

    # Pillar weights — good
    good_weights = {
        "Financial": 0.40, "Customer Focus": 0.25,
        "Operational Excellence": 0.25, "People & Learning": 0.10,
    }
    r = validate_pillar_weights(good_weights)
    assert r.valid is True
    print(f"  ✓ Pillar weights good case: valid (Kaplan-Norton)")

    # Pillar weights — sum != 1.0
    bad_sum = {
        "Financial": 0.50, "Customer Focus": 0.30,
        "Operational Excellence": 0.30, "People & Learning": 0.10,
    }
    r = validate_pillar_weights(bad_sum)
    assert r.valid is False
    assert any("sum" in e.field for e in r.errors)
    print(f"  ✓ Pillar weights rejects sum != 1.0")

    # Pillar weights — missing pillar
    missing_pillar = {
        "Financial": 0.50, "Customer Focus": 0.30, "People & Learning": 0.20,
    }
    r = validate_pillar_weights(missing_pillar)
    assert r.valid is False
    print(f"  ✓ Pillar weights rejects missing canonical pillar")

    # Role KPIs — good
    lib_full = {"kpis": [
        {"id": "K001", "name": "Loans", "pillar": "Financial"},
        {"id": "K002", "name": "Deposits", "pillar": "Financial"},
    ]}
    r = validate_role_kpis_change("MD", ["K001", "K002"], existing_lib=lib_full)
    assert r.valid is True
    print(f"  ✓ Role KPIs good case: valid")

    # Role KPIs — orphan
    r = validate_role_kpis_change("MD", ["K001", "ORPHAN"], existing_lib=lib_full)
    assert r.valid is False
    assert any("unresolved" in e.message for e in r.errors)
    print(f"  ✓ Role KPIs rejects orphan reference")

    # Target override — good
    r = validate_target_override("Alice", "Loans", 100.0, current_target=90.0)
    assert r.valid is True
    print(f"  ✓ Target override good case: valid")

    # Target override — large swing warning
    r = validate_target_override("Alice", "Loans", 200.0, current_target=90.0)
    assert r.valid is True  # warning, not error
    assert any("changes by" in w.message for w in r.warnings)
    print(f"  ✓ Target override warns on large swings")

    # Full library — on real data
    r = validate_full_library()
    print(f"  ✓ Full library validation: "
          f"{len(r.errors)} errors, {len(r.warnings)} warnings")

    # JSON serialization
    json.dumps(r.to_dict())
    print(f"  ✓ JSON-serializable")

    print("✓ self_test passed")


if __name__ == "__main__":
    self_test()
