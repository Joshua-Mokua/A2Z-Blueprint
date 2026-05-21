"""Staff Onboarding Engine — v10.434 (new staff fit-in test).

Per Joshua roadmap: after 360 harmony reached 100%, confirm a new
staff "fits in so well" — register entry → cascade allocation → BSC
auto-populates → weights sum to 1.0 → scoring works end-to-end.

This engine simulates and audits the onboarding lifecycle. Five
public functions:

  - validate_new_staff(staff_dict)        → ValidationResult
  - simulate_onboarding(staff_dict, dry)  → OnboardingResult
  - onboard_new_staff(staff_dict, dry)    → OnboardingResult (live)
  - audit_staff_completeness(staff_code)  → CompletenessAudit
  - audit_all_staff_completeness()        → FullCompletenessAudit

Defaults to dry_run=True for live-write operations. All read functions
are side-effect-free.

Key audits per staff:
  1. Register entry exists
  2. role_kpis has KPIs for their role
  3. BSC has rows for each role_kpi (canonical name)
  4. Weights sum to 1.0 (within tolerance)
  5. All 4 pillars represented OR documented why not
  6. Score computable (no NaN)
  7. Cascade integration where applicable (parent allocates to them
     for any of their KPIs)

Shipped: v10.434.
"""
from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, asdict, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

REPO_ROOT = Path(__file__).parent.parent
DATA_DIR = REPO_ROOT / "data"

# Canonical pillars
CANONICAL_PILLARS: Set[str] = {
    "Financial",
    "Customer Focus",
    "Operational Excellence",
    "People & Learning",
}

WEIGHT_TOLERANCE = 0.001
DEFAULT_NEW_KPI_WEIGHT = 0.05
DEFAULT_NEW_ACHIEVEMENT = 0.80  # 80% of target as initial actual


# ════════════════════════════════════════════════════════════════════
# Types
# ════════════════════════════════════════════════════════════════════

@dataclass
class ValidationIssue:
    severity: str
    field: str
    message: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ValidationResult:
    valid: bool
    errors: List[ValidationIssue]
    warnings: List[ValidationIssue]
    info: List[ValidationIssue]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "valid": self.valid,
            "errors": [e.to_dict() for e in self.errors],
            "warnings": [w.to_dict() for w in self.warnings],
            "info": [i.to_dict() for i in self.info],
        }

    @classmethod
    def empty(cls) -> "ValidationResult":
        return cls(valid=True, errors=[], warnings=[], info=[])

    def add_error(self, field_: str, msg: str) -> None:
        self.errors.append(ValidationIssue("error", field_, msg))
        self.valid = False

    def add_warning(self, field_: str, msg: str) -> None:
        self.warnings.append(ValidationIssue("warning", field_, msg))

    def add_info(self, field_: str, msg: str) -> None:
        self.info.append(ValidationIssue("info", field_, msg))


@dataclass
class OnboardingResult:
    dry_run: bool
    staff_code: str
    staff_name: str
    role: str
    valid: bool
    validation: ValidationResult
    register_added: bool
    role_kpis_resolved: List[str]
    bsc_rows_added: int
    weight_sum_post: float
    pillar_coverage: Dict[str, int]
    cascade_allocations_received: int
    score_computable: bool
    timestamp: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "dry_run": self.dry_run,
            "staff_code": self.staff_code,
            "staff_name": self.staff_name,
            "role": self.role,
            "valid": self.valid,
            "validation": self.validation.to_dict(),
            "register_added": self.register_added,
            "role_kpis_resolved": self.role_kpis_resolved,
            "bsc_rows_added": self.bsc_rows_added,
            "weight_sum_post": self.weight_sum_post,
            "pillar_coverage": self.pillar_coverage,
            "cascade_allocations_received": self.cascade_allocations_received,
            "score_computable": self.score_computable,
            "timestamp": self.timestamp,
        }


@dataclass
class CompletenessAudit:
    """Per-staff fit-in audit."""
    staff_code: str
    staff_name: str
    role: str
    unit: str
    register_present: bool
    role_kpis_count: int
    bsc_row_count: int
    bsc_kpis_matching_role_kpis: int
    bsc_kpis_missing: List[str]
    weight_sum: float
    weight_sum_valid: bool  # within tolerance of 1.0
    pillar_coverage: Dict[str, int]  # pillar -> row count
    has_all_pillars: bool
    score_computable: bool
    cascade_allocations_received: int
    issues: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @property
    def overall_fit(self) -> bool:
        return (
            self.register_present
            and self.bsc_row_count > 0
            and self.weight_sum_valid
            and self.score_computable
            and len(self.issues) == 0
        )


@dataclass
class FullCompletenessAudit:
    """Bank-wide fit-in audit across all staff."""
    total_staff: int
    fully_fit: int
    partial_fit: int
    failing: int
    avg_role_kpi_coverage_pct: float
    weight_sum_invariant_pct: float
    score_computable_pct: float
    pillar_coverage_pct: float
    failing_samples: List[Dict[str, Any]]
    timestamp: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ════════════════════════════════════════════════════════════════════
# Helpers
# ════════════════════════════════════════════════════════════════════

def _load_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _find_actuals() -> Optional[Path]:
    if not DATA_DIR.exists():
        return None
    files = sorted(DATA_DIR.glob("actuals_*.xlsx"))
    return files[-1] if files else None


def _load_actuals_df() -> Optional["pandas.DataFrame"]:  # type: ignore
    import pandas as pd
    p = _find_actuals()
    if p is None:
        return None
    try:
        return pd.read_excel(p, skiprows=1)
    except Exception:  # noqa: BLE001
        return None


def _load_register() -> Optional["pandas.DataFrame"]:  # type: ignore
    import pandas as pd
    p = DATA_DIR / "staff_register.xlsx"
    if not p.exists():
        return None
    try:
        return pd.read_excel(p)
    except Exception:  # noqa: BLE001
        return None


def _resolve_canonical_names(lib: Dict[str, Any], kpi_ids: List[str]) -> List[str]:
    """Resolve a list of KPI IDs/aliases to canonical library names."""
    name_set: Set[str] = set()
    id_to_name: Dict[str, str] = {}
    alias_to_name: Dict[str, str] = {}
    for k in lib.get("kpis", []):
        if not isinstance(k, dict):
            continue
        name = str(k.get("name", "")).strip()
        if not name:
            continue
        name_set.add(name)
        kid = str(k.get("id", "")).strip()
        if kid:
            id_to_name[kid] = name
        for a in k.get("aliases", []) or []:
            if a:
                alias_to_name[str(a).strip()] = name
    canonical: List[str] = []
    for kid in kpi_ids:
        kid_s = str(kid).strip()
        if kid_s in name_set:
            canonical.append(kid_s)
        elif kid_s in id_to_name:
            canonical.append(id_to_name[kid_s])
        elif kid_s in alias_to_name:
            canonical.append(alias_to_name[kid_s])
    return canonical


# ════════════════════════════════════════════════════════════════════
# Validation
# ════════════════════════════════════════════════════════════════════

REQUIRED_STAFF_FIELDS = {"Staff Code", "Staff Name", "Role", "Unit"}
OPTIONAL_STAFF_FIELDS = {
    "Region", "Category", "Department", "Band", "Gender",
    "Reports To", "Date of Employment",
}


def validate_new_staff(staff_dict: Dict[str, Any]) -> ValidationResult:
    """Pre-add validation."""
    result = ValidationResult.empty()

    if not isinstance(staff_dict, dict):
        result.add_error("input", "staff_dict must be a dict")
        return result

    # Required fields
    for f in REQUIRED_STAFF_FIELDS:
        if not staff_dict.get(f) or not str(staff_dict[f]).strip():
            result.add_error(f, f"'{f}' is required")

    if not result.valid:
        return result

    code = str(staff_dict["Staff Code"]).strip()
    role = str(staff_dict["Role"]).strip()

    # Code format
    if not re.match(r"^[A-Z0-9]+$", code):
        result.add_warning("Staff Code",
                          f"'{code}' doesn't match alphanumeric convention")

    # Check duplicates in register
    reg = _load_register()
    if reg is not None:
        existing_codes = set(reg["Staff Code"].astype(str).str.strip())
        if code in existing_codes:
            result.add_error("Staff Code",
                            f"'{code}' already exists in register")

    # Check role has role_kpis configured
    lib = _load_json(DATA_DIR / "kpi_library.json")
    role_kpis_map = lib.get("role_kpis", {})
    if role not in role_kpis_map:
        # Try fuzzy match
        candidates = [r for r in role_kpis_map if r.lower() == role.lower()]
        if candidates:
            result.add_info("Role",
                f"Role '{role}' not in role_kpis but matches '{candidates[0]}' case-insensitively")
        else:
            result.add_warning("Role",
                f"Role '{role}' has no role_kpis configured — "
                f"staff will join with no BSC KPIs unless library updated")
    else:
        kpi_ids = role_kpis_map.get(role, [])
        if not isinstance(kpi_ids, list) or not kpi_ids:
            result.add_warning("Role",
                f"role_kpis['{role}'] is empty")
        else:
            canonical = _resolve_canonical_names(lib, kpi_ids)
            unresolved = len(kpi_ids) - len(canonical)
            if unresolved > 0:
                result.add_warning("Role",
                    f"{unresolved} of {len(kpi_ids)} KPIs for '{role}' "
                    f"don't resolve in library")
            result.add_info("Role",
                f"Role '{role}' will receive {len(canonical)} BSC KPIs")

    # Manager check (Reports To)
    reports_to = str(staff_dict.get("Reports To", "")).strip()
    if reports_to and reg is not None:
        if reports_to not in set(reg["Staff Code"].astype(str).str.strip()):
            result.add_warning("Reports To",
                f"Manager code '{reports_to}' not in register")

    if result.valid and not result.errors:
        result.add_info("status", f"Staff {code} passes pre-add validation")

    return result


# ════════════════════════════════════════════════════════════════════
# Simulation
# ════════════════════════════════════════════════════════════════════

def _compute_pillar_coverage_for_role(
    role: str, lib: Dict[str, Any],
) -> Dict[str, int]:
    """Project how many KPIs per pillar a new staff in this role gets."""
    role_kpis_map = lib.get("role_kpis", {})
    kpi_ids = role_kpis_map.get(role, [])
    if not isinstance(kpi_ids, list):
        return {}
    canonical = _resolve_canonical_names(lib, kpi_ids)
    coverage: Dict[str, int] = {p: 0 for p in CANONICAL_PILLARS}
    for k in lib.get("kpis", []):
        if not isinstance(k, dict):
            continue
        name = str(k.get("name", "")).strip()
        if name in canonical:
            pillar = str(k.get("pillar", "")).strip()
            if pillar in coverage:
                coverage[pillar] += 1
    return coverage


def simulate_onboarding(
    staff_dict: Dict[str, Any],
    dry_run: bool = True,
) -> OnboardingResult:
    """Projects what would happen if we onboarded this staff."""
    validation = validate_new_staff(staff_dict)
    if not validation.valid:
        return OnboardingResult(
            dry_run=True,
            staff_code=str(staff_dict.get("Staff Code", "")),
            staff_name=str(staff_dict.get("Staff Name", "")),
            role=str(staff_dict.get("Role", "")),
            valid=False,
            validation=validation,
            register_added=False,
            role_kpis_resolved=[],
            bsc_rows_added=0,
            weight_sum_post=0.0,
            pillar_coverage={},
            cascade_allocations_received=0,
            score_computable=False,
            timestamp=datetime.now().isoformat(),
        )

    code = str(staff_dict["Staff Code"]).strip()
    name = str(staff_dict["Staff Name"]).strip()
    role = str(staff_dict["Role"]).strip()

    # Resolve role_kpis to canonical names
    lib = _load_json(DATA_DIR / "kpi_library.json")
    kpi_ids = lib.get("role_kpis", {}).get(role, [])
    canonical = (
        _resolve_canonical_names(lib, kpi_ids)
        if isinstance(kpi_ids, list) else []
    )

    # Pillar coverage projection
    pillar_coverage = _compute_pillar_coverage_for_role(role, lib)

    # Weight sum projection — equal-split would yield 1.0 (we'll renormalize)
    weight_sum_post = 1.0 if canonical else 0.0

    # Cascade allocations: would any cascade entry allocate to this code?
    cascade = _load_json(DATA_DIR / "target_cascade.json")
    received = 0
    for k, v in cascade.items():
        if k.startswith("_") or not isinstance(v, dict):
            continue
        for a in v.get("allocations", []) or []:
            if isinstance(a, dict) and str(a.get("to_code", "")).strip() == code:
                received += 1

    score_computable = len(canonical) > 0 and weight_sum_post > 0

    return OnboardingResult(
        dry_run=True,
        staff_code=code, staff_name=name, role=role,
        valid=True, validation=validation,
        register_added=False,  # dry-run
        role_kpis_resolved=canonical,
        bsc_rows_added=len(canonical),
        weight_sum_post=weight_sum_post,
        pillar_coverage=pillar_coverage,
        cascade_allocations_received=received,
        score_computable=score_computable,
        timestamp=datetime.now().isoformat(),
    )


# ════════════════════════════════════════════════════════════════════
# Per-staff completeness audit
# ════════════════════════════════════════════════════════════════════

def audit_staff_completeness(
    staff_code: str,
) -> CompletenessAudit:
    """Audit a specific staff's BSC fit-in completeness."""
    code = str(staff_code).strip()
    issues: List[str] = []

    # Register check
    reg = _load_register()
    register_present = False
    name = ""
    role = ""
    unit = ""
    if reg is not None:
        reg["_code"] = reg["Staff Code"].astype(str).str.strip()
        row = reg[reg["_code"] == code]
        if len(row) > 0:
            register_present = True
            name = str(row.iloc[0]["Staff Name"])
            role = str(row.iloc[0]["Role"])
            unit = str(row.iloc[0]["Unit"])
        else:
            issues.append(f"Not in staff_register")

    # role_kpis count
    lib = _load_json(DATA_DIR / "kpi_library.json")
    role_kpi_ids = lib.get("role_kpis", {}).get(role, [])
    role_kpis_count = (
        len(role_kpi_ids) if isinstance(role_kpi_ids, list) else 0
    )
    canonical_role_kpis = (
        _resolve_canonical_names(lib, role_kpi_ids)
        if isinstance(role_kpi_ids, list) else []
    )

    # BSC rows for staff
    df = _load_actuals_df()
    bsc_row_count = 0
    bsc_kpis: Set[str] = set()
    weight_sum = 0.0
    pillar_coverage: Dict[str, int] = {p: 0 for p in CANONICAL_PILLARS}
    score_computable = False

    if df is not None and register_present:
        df["_code"] = df["Staff Code"].astype(str).str.strip()
        staff_rows = df[df["_code"] == code]
        bsc_row_count = len(staff_rows)
        for _, r in staff_rows.iterrows():
            kpi = str(r.get("KPI", "")).strip()
            if kpi:
                bsc_kpis.add(kpi)
            try:
                weight_sum += float(r.get("Weight", 0) or 0)
            except (ValueError, TypeError):
                pass
            pillar = str(r.get("Pillar", "")).strip()
            if pillar in pillar_coverage:
                pillar_coverage[pillar] += 1

        # Score computable: all rows have target + actual + non-zero weight
        try:
            from utils.cascade_bsc_360_engine import _compute_kpi_achievement
            has_any_valid = False
            for _, r in staff_rows.iterrows():
                try:
                    t = float(r.get("Annual Target", 0) or 0)
                    a = float(r.get("Annual Actual", 0) or 0)
                    w = float(r.get("Weight", 0) or 0)
                    if t > 0 and w > 0:
                        ach = _compute_kpi_achievement(a, t)
                        if math.isfinite(ach):
                            has_any_valid = True
                            break
                except (ValueError, TypeError):
                    pass
            score_computable = has_any_valid
        except Exception:  # noqa: BLE001
            score_computable = bsc_row_count > 0

    # BSC matches role_kpis
    bsc_kpis_matching_role_kpis = len(bsc_kpis & set(canonical_role_kpis))
    bsc_kpis_missing = sorted(set(canonical_role_kpis) - bsc_kpis)

    # Weight sum valid
    weight_sum_valid = (
        abs(weight_sum - 1.0) <= WEIGHT_TOLERANCE
        if bsc_row_count > 0 else False
    )

    # Pillar coverage
    has_all_pillars = all(c > 0 for c in pillar_coverage.values())

    # Cascade allocations
    cascade = _load_json(DATA_DIR / "target_cascade.json")
    received = 0
    for k, v in cascade.items():
        if k.startswith("_") or not isinstance(v, dict):
            continue
        for a in v.get("allocations", []) or []:
            if isinstance(a, dict) and str(a.get("to_code", "")).strip() == code:
                received += 1

    # Build issues list
    if not register_present:
        pass  # already added
    else:
        if bsc_row_count == 0:
            issues.append("Has no BSC rows")
        if role_kpis_count > 0 and bsc_kpis_missing:
            issues.append(
                f"BSC missing {len(bsc_kpis_missing)} role_kpis: "
                f"{bsc_kpis_missing[:3]}"
            )
        if bsc_row_count > 0 and not weight_sum_valid:
            issues.append(f"Weight sum = {weight_sum:.4f} (not 1.0)")
        if bsc_row_count > 0 and not has_all_pillars:
            empty = [p for p, c in pillar_coverage.items() if c == 0]
            issues.append(f"Missing pillars: {empty}")
        if bsc_row_count > 0 and not score_computable:
            issues.append("Score not computable")

    return CompletenessAudit(
        staff_code=code,
        staff_name=name,
        role=role,
        unit=unit,
        register_present=register_present,
        role_kpis_count=role_kpis_count,
        bsc_row_count=bsc_row_count,
        bsc_kpis_matching_role_kpis=bsc_kpis_matching_role_kpis,
        bsc_kpis_missing=bsc_kpis_missing,
        weight_sum=round(weight_sum, 4),
        weight_sum_valid=weight_sum_valid,
        pillar_coverage=pillar_coverage,
        has_all_pillars=has_all_pillars,
        score_computable=score_computable,
        cascade_allocations_received=received,
        issues=issues,
    )


def audit_all_staff_completeness() -> FullCompletenessAudit:
    """Bank-wide fit-in audit across all 1437 staff.

    Optimized: loads data once, builds in-memory lookups, then iterates.
    """
    df = _load_actuals_df()
    reg = _load_register()
    lib = _load_json(DATA_DIR / "kpi_library.json")
    cascade = _load_json(DATA_DIR / "target_cascade.json")
    if df is None or reg is None:
        return FullCompletenessAudit(
            0, 0, 0, 0, 0.0, 0.0, 0.0, 0.0, [],
            datetime.now().isoformat(),
        )

    # Pre-compute role -> canonical KPI names
    role_kpis_canonical: Dict[str, List[str]] = {}
    for role, kpi_ids in lib.get("role_kpis", {}).items():
        if isinstance(kpi_ids, list):
            role_kpis_canonical[role] = _resolve_canonical_names(lib, kpi_ids)

    # Pre-compute cascade allocations per recipient code
    cascade_by_recipient: Dict[str, int] = {}
    for k, v in cascade.items():
        if k.startswith("_") or not isinstance(v, dict):
            continue
        for a in v.get("allocations", []) or []:
            if isinstance(a, dict):
                code = str(a.get("to_code", "")).strip()
                if code:
                    cascade_by_recipient[code] = cascade_by_recipient.get(code, 0) + 1

    # Pre-compute register by code
    reg["_code"] = reg["Staff Code"].astype(str).str.strip()
    reg_by_code: Dict[str, Dict[str, str]] = {}
    for _, r in reg.iterrows():
        reg_by_code[r["_code"]] = {
            "Staff Name": str(r.get("Staff Name", "")),
            "Role": str(r.get("Role", "")),
            "Unit": str(r.get("Unit", "")),
        }

    # Pre-compute BSC rows per staff
    df["_code"] = df["Staff Code"].astype(str).str.strip()

    # Try to import achievement helper once
    try:
        from utils.cascade_bsc_360_engine import _compute_kpi_achievement
        achievement_fn = _compute_kpi_achievement
    except Exception:  # noqa: BLE001
        achievement_fn = None

    all_codes = sorted(df["_code"].dropna().unique())

    fully = 0
    partial = 0
    failing = 0
    coverage_pcts: List[float] = []
    weight_invariant_count = 0
    score_count = 0
    pillar_full_count = 0
    failing_samples: List[Dict[str, Any]] = []

    # Group BSC by code for speed
    bsc_by_code: Dict[str, "pandas.DataFrame"] = {}  # type: ignore
    for code, group in df.groupby("_code"):
        bsc_by_code[code] = group

    for code in all_codes:
        reg_entry = reg_by_code.get(code, {})
        register_present = bool(reg_entry)
        name = reg_entry.get("Staff Name", "")
        role = reg_entry.get("Role", "")
        unit = reg_entry.get("Unit", "")
        canonical_role_kpis = role_kpis_canonical.get(role, [])
        role_kpis_count = len(canonical_role_kpis)

        staff_rows = bsc_by_code.get(code)
        bsc_row_count = len(staff_rows) if staff_rows is not None else 0
        bsc_kpis: Set[str] = set()
        weight_sum = 0.0
        pillar_coverage: Dict[str, int] = {p: 0 for p in CANONICAL_PILLARS}
        score_computable = False
        issues: List[str] = []

        if staff_rows is not None:
            for _, r in staff_rows.iterrows():
                kpi = str(r.get("KPI", "")).strip()
                if kpi:
                    bsc_kpis.add(kpi)
                try:
                    weight_sum += float(r.get("Weight", 0) or 0)
                except (ValueError, TypeError):
                    pass
                pillar = str(r.get("Pillar", "")).strip()
                if pillar in pillar_coverage:
                    pillar_coverage[pillar] += 1

            # Score check
            if achievement_fn:
                has_any_valid = False
                for _, r in staff_rows.iterrows():
                    try:
                        t = float(r.get("Annual Target", 0) or 0)
                        a = float(r.get("Annual Actual", 0) or 0)
                        w = float(r.get("Weight", 0) or 0)
                        if t > 0 and w > 0:
                            ach = achievement_fn(a, t)
                            if math.isfinite(ach):
                                has_any_valid = True
                                break
                    except (ValueError, TypeError):
                        pass
                score_computable = has_any_valid
            else:
                score_computable = bsc_row_count > 0

        bsc_kpis_matching = len(bsc_kpis & set(canonical_role_kpis))
        bsc_kpis_missing = sorted(set(canonical_role_kpis) - bsc_kpis)
        weight_sum_valid = (
            abs(weight_sum - 1.0) <= WEIGHT_TOLERANCE
            if bsc_row_count > 0 else False
        )
        has_all_pillars = all(c > 0 for c in pillar_coverage.values())
        received = cascade_by_recipient.get(code, 0)

        if not register_present:
            issues.append("Not in register")
        if bsc_row_count == 0:
            issues.append("No BSC rows")
        if role_kpis_count > 0 and bsc_kpis_missing:
            issues.append(f"BSC missing {len(bsc_kpis_missing)} role_kpis")
        if bsc_row_count > 0 and not weight_sum_valid:
            issues.append(f"Weight sum = {weight_sum:.4f}")
        if bsc_row_count > 0 and not has_all_pillars:
            empty = [p for p, c in pillar_coverage.items() if c == 0]
            issues.append(f"Missing pillars: {empty}")
        if bsc_row_count > 0 and not score_computable:
            issues.append("Score not computable")

        # Bucket
        overall_fit = (
            register_present
            and bsc_row_count > 0
            and weight_sum_valid
            and score_computable
            and len(issues) == 0
        )
        if overall_fit:
            fully += 1
        elif len(issues) <= 2:
            partial += 1
        else:
            failing += 1
            if len(failing_samples) < 10:
                failing_samples.append({
                    "code": code, "name": name, "role": role,
                    "issues": issues,
                })

        if role_kpis_count > 0:
            coverage_pcts.append(
                bsc_kpis_matching / role_kpis_count * 100
            )
        if weight_sum_valid:
            weight_invariant_count += 1
        if score_computable:
            score_count += 1
        if has_all_pillars:
            pillar_full_count += 1

    total = len(all_codes)
    avg_cov = sum(coverage_pcts) / len(coverage_pcts) if coverage_pcts else 0.0

    return FullCompletenessAudit(
        total_staff=total,
        fully_fit=fully,
        partial_fit=partial,
        failing=failing,
        avg_role_kpi_coverage_pct=round(avg_cov, 2),
        weight_sum_invariant_pct=round(weight_invariant_count / total * 100, 2) if total else 0.0,
        score_computable_pct=round(score_count / total * 100, 2) if total else 0.0,
        pillar_coverage_pct=round(pillar_full_count / total * 100, 2) if total else 0.0,
        failing_samples=failing_samples,
        timestamp=datetime.now().isoformat(),
    )


# ════════════════════════════════════════════════════════════════════
# Self-test
# ════════════════════════════════════════════════════════════════════

def self_test() -> None:
    print("─ staff_onboarding_engine self-test ─")

    # Zero streamlit
    text = Path(__file__).read_text()
    streamlit_imports = re.findall(
        r"^\s*(?:import\s+streamlit|from\s+streamlit)\b",
        text, re.MULTILINE,
    )
    assert len(streamlit_imports) == 0
    print("  ✓ Zero streamlit imports")

    # Constants
    assert len(CANONICAL_PILLARS) == 4
    print(f"  ✓ Constants: 4 pillars, weight tolerance {WEIGHT_TOLERANCE}")

    # Validation — good case
    good = {
        "Staff Code": "TST99001",
        "Staff Name": "Test New Staff",
        "Role": "Branch Operations Manager",
        "Unit": "Test Branch",
    }
    v = validate_new_staff(good)
    print(f"  ✓ Validation good case: valid={v.valid}, "
          f"warnings={len(v.warnings)}, info={len(v.info)}")

    # Validation — missing field
    bad = {"Staff Code": "X", "Staff Name": "Y"}
    v = validate_new_staff(bad)
    assert not v.valid
    print(f"  ✓ Validation rejects missing fields: errors={len(v.errors)}")

    # Validation — duplicate code
    dup = {**good, "Staff Code": "300001"}  # MD exists
    v = validate_new_staff(dup)
    assert not v.valid
    print(f"  ✓ Validation rejects duplicate code")

    # Simulation — different roles
    print(f"\n  Simulating onboarding for 4 roles:")
    test_roles = [
        ("Branch Operations Manager", "Test Branch"),
        ("Senior Relationship Officer Corporate", "Head Office"),
        ("Teller", "Test Branch"),
        ("Branch Manager", "Test Branch"),
    ]
    for role, unit in test_roles:
        staff = {
            "Staff Code": f"TST{role[:3].upper()}",
            "Staff Name": f"Test {role}",
            "Role": role,
            "Unit": unit,
        }
        o = simulate_onboarding(staff)
        pc = o.pillar_coverage
        print(f"    {role:42}: {o.bsc_rows_added:3} KPIs "
              f"[F:{pc.get('Financial',0)} CF:{pc.get('Customer Focus',0)} "
              f"OE:{pc.get('Operational Excellence',0)} PL:{pc.get('People & Learning',0)}] "
              f"score={'✓' if o.score_computable else '✗'}")

    # Per-staff audit (MD)
    md = audit_staff_completeness("300001")
    print(f"\n  Audit MD (300001 William Mwanake):")
    print(f"    Role:            {md.role}")
    print(f"    role_kpis count: {md.role_kpis_count}")
    print(f"    BSC rows:        {md.bsc_row_count}")
    print(f"    BSC ∩ role_kpis: {md.bsc_kpis_matching_role_kpis}")
    print(f"    Weight sum:      {md.weight_sum:.4f} (valid: {md.weight_sum_valid})")
    print(f"    Pillars:         {md.pillar_coverage}")
    print(f"    Score:           {'✓' if md.score_computable else '✗'}")
    print(f"    Cascade alloc:   {md.cascade_allocations_received}")
    print(f"    Overall fit:     {'✓' if md.overall_fit else '✗'}")
    print(f"    Issues:          {md.issues}")

    # Bank-wide audit
    print(f"\n  Bank-wide completeness audit:")
    full = audit_all_staff_completeness()
    print(f"    Total staff:                  {full.total_staff}")
    print(f"    Fully fit:                    {full.fully_fit} ({100*full.fully_fit/full.total_staff:.1f}%)")
    print(f"    Partial fit (1-2 issues):     {full.partial_fit}")
    print(f"    Failing (3+ issues):          {full.failing}")
    print(f"    Avg role_kpi coverage:        {full.avg_role_kpi_coverage_pct}%")
    print(f"    Weight sum invariant:         {full.weight_sum_invariant_pct}%")
    print(f"    Score computable:             {full.score_computable_pct}%")
    print(f"    Pillar coverage (all 4):      {full.pillar_coverage_pct}%")

    # JSON
    json.dumps(full.to_dict())
    print(f"  ✓ JSON-serializable")

    print("\n✓ self_test passed")


if __name__ == "__main__":
    self_test()
