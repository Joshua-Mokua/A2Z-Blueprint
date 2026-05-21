"""Role Weight Renormalization Engine — v10.419 (Phase 2d).

Per Joshua's locked backlog: "Role weight renormalization (225/227 broken)".

The current canonical structure stores ONLY global per-KPI weights
(kpi_weights: {kpi: float}). When a role's score is computed, weights
are pulled from this global dict for KPIs assigned to that role. The
existing scoring code auto-normalizes by dividing through the sum, but
the implicit assumption that "sum of weights for a role = 1.0" is NOT
verified anywhere - and 225 of 227 roles in the current library don't
satisfy it.

This engine surfaces the gap transparently:

  - audit_role_weight: per-role audit (is sum 1.0?)
  - bank_role_weight_audit: bank-wide rollup
  - compute_role_normalized_weights: per-role normalized dict
  - migrate_normalize_all_roles: writes role_normalized_weights field
    additively into kpi_library.json (doesn't change kpi_weights)

The migration is ADDITIVE: existing code reading kpi_weights continues
unchanged. New consumers (audit dashboards, React BSC, etc.) can read
role_normalized_weights to get per-role normalized values directly.

ARCHITECTURAL NOTE (API-first discipline locked v10.412):
  ZERO streamlit imports. JSON-serializable dataclass returns.

Shipped: v10.419.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).parent.parent
DATA_DIR = REPO_ROOT / "data"
KPI_LIBRARY_FILE = DATA_DIR / "kpi_library.json"

# Tolerance: how close to 1.0 counts as "normalized"
NORMALIZATION_TOLERANCE = 0.001  # 0.1%


# ════════════════════════════════════════════════════════════════════
# Types
# ════════════════════════════════════════════════════════════════════

@dataclass
class RoleWeightAudit:
    """Audit result for one role."""
    role: str
    kpi_count: int
    kpis_assigned: List[str]
    kpis_with_weight: int        # KPIs present in global kpi_weights
    kpis_missing_weight: int     # KPIs without global weight (defaults)
    sum_of_weights: float        # raw sum across assigned KPIs
    is_normalized: bool          # sum ≈ 1.0
    normalization_factor: float  # multiply each weight by this → sums to 1.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class BankRoleWeightAudit:
    """Bank-wide rollup of role-weight audit."""
    total_roles: int
    normalized_count: int
    broken_count: int
    zero_sum_count: int           # sum == 0 (all KPIs missing weights)
    broken_roles: List[str] = field(default_factory=list)
    timestamp: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ════════════════════════════════════════════════════════════════════
# Library access
# ════════════════════════════════════════════════════════════════════

def _load_library() -> Dict[str, Any]:
    if not KPI_LIBRARY_FILE.exists():
        return {}
    try:
        return json.loads(KPI_LIBRARY_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _save_library(lib: Dict[str, Any]) -> bool:
    try:
        KPI_LIBRARY_FILE.write_text(
            json.dumps(lib, indent=2, default=str),
            encoding="utf-8",
        )
        return True
    except OSError:
        return False


# ════════════════════════════════════════════════════════════════════
# Public API — Audit
# ════════════════════════════════════════════════════════════════════

def audit_role_weight(
    role: str,
    role_kpis_list: List[str],
    kpi_weights_dict: Dict[str, float],
    default_weight: float = 0.05,
) -> RoleWeightAudit:
    """Audit a single role's weight situation.

    Args:
      role: role name
      role_kpis_list: list of KPI codes assigned to this role
      kpi_weights_dict: global {kpi: weight} dict
      default_weight: fallback when KPI has no entry (used by existing code)

    Returns RoleWeightAudit with sum, is_normalized, factor for fixing.
    """
    if not isinstance(role_kpis_list, list):
        return RoleWeightAudit(
            role=str(role), kpi_count=0, kpis_assigned=[],
            kpis_with_weight=0, kpis_missing_weight=0,
            sum_of_weights=0.0, is_normalized=False, normalization_factor=0.0,
        )

    kpis = [str(k) for k in role_kpis_list if isinstance(k, (str, int))]
    with_weight = 0
    missing = 0
    total = 0.0
    for k in kpis:
        w = kpi_weights_dict.get(k)
        if w is None:
            missing += 1
        else:
            try:
                total += float(w)
                with_weight += 1
            except (TypeError, ValueError):
                missing += 1

    is_norm = abs(total - 1.0) <= NORMALIZATION_TOLERANCE
    factor = (1.0 / total) if total > 0 else 0.0

    return RoleWeightAudit(
        role=str(role),
        kpi_count=len(kpis),
        kpis_assigned=kpis,
        kpis_with_weight=with_weight,
        kpis_missing_weight=missing,
        sum_of_weights=total,
        is_normalized=is_norm,
        normalization_factor=factor,
    )


def bank_role_weight_audit(
    library: Optional[Dict[str, Any]] = None,
) -> BankRoleWeightAudit:
    """Bank-wide audit. Loads from kpi_library.json if no library passed."""
    if library is None:
        library = _load_library()

    role_kpis = library.get("role_kpis", {})
    kpi_weights = library.get("kpi_weights", {})

    total = 0
    normalized = 0
    broken: List[str] = []
    zero_sum = 0

    for role, kpis in role_kpis.items():
        if role.startswith("_"):
            continue  # skip meta keys
        if not isinstance(kpis, list):
            continue
        total += 1
        audit = audit_role_weight(role, kpis, kpi_weights)
        if audit.sum_of_weights <= 0:
            zero_sum += 1
            broken.append(role)
        elif audit.is_normalized:
            normalized += 1
        else:
            broken.append(role)

    return BankRoleWeightAudit(
        total_roles=total,
        normalized_count=normalized,
        broken_count=len(broken),
        zero_sum_count=zero_sum,
        broken_roles=broken,
        timestamp=datetime.now().isoformat(),
    )


# ════════════════════════════════════════════════════════════════════
# Public API — Normalization
# ════════════════════════════════════════════════════════════════════

def compute_role_normalized_weights(
    role: str,
    role_kpis_list: List[str],
    kpi_weights_dict: Dict[str, float],
    default_weight: float = 0.05,
) -> Dict[str, float]:
    """Return {kpi: normalized_weight} for a role, summing to 1.0.

    Logic:
      - For each KPI in role_kpis_list:
          - If in kpi_weights_dict, use that weight
          - Else use default_weight
      - Divide each by the total to normalize
      - If total is 0 (all defaults are 0), return equal weights
    """
    if not isinstance(role_kpis_list, list) or not role_kpis_list:
        return {}

    raw: Dict[str, float] = {}
    for k in role_kpis_list:
        if not isinstance(k, (str, int)):
            continue
        kc = str(k)
        w = kpi_weights_dict.get(kc, default_weight)
        try:
            raw[kc] = float(w)
        except (TypeError, ValueError):
            raw[kc] = float(default_weight)

    total = sum(raw.values())
    if total <= 0:
        # Equal weights fallback
        if not raw:
            return {}
        equal = 1.0 / len(raw)
        return {k: equal for k in raw}

    return {k: w / total for k, w in raw.items()}


def migrate_normalize_all_roles(
    library: Optional[Dict[str, Any]] = None,
    write_back: bool = True,
) -> Tuple[BankRoleWeightAudit, Dict[str, Dict[str, float]]]:
    """Compute normalized weights for every role; write to library if requested.

    Adds a new field 'role_normalized_weights' to kpi_library.json:
      {role: {kpi: normalized_weight}}

    This is ADDITIVE: existing code reading kpi_weights continues to work
    unchanged. New consumers (audit dashboards, React BSC) can read the
    normalized field directly.

    Args:
      library: optional pre-loaded library; if None, load from file
      write_back: if True and library was loaded, write back to file

    Returns (BankRoleWeightAudit, {role: {kpi: weight}})
    """
    if library is None:
        library = _load_library()
        loaded = True
    else:
        loaded = False

    role_kpis = library.get("role_kpis", {})
    kpi_weights = library.get("kpi_weights", {})

    normalized: Dict[str, Dict[str, float]] = {}
    for role, kpis in role_kpis.items():
        if role.startswith("_"):
            continue
        if not isinstance(kpis, list):
            continue
        normalized[role] = compute_role_normalized_weights(role, kpis, kpi_weights)

    # Audit
    audit = bank_role_weight_audit(library)

    # Write back
    if write_back and loaded:
        library["role_normalized_weights"] = normalized
        # Stamp migration metadata
        library["_v10419_role_weight_normalization"] = {
            "shipped": "v10.419",
            "ts": datetime.now().isoformat(),
            "audit_summary": audit.to_dict(),
            "roles_normalized": len(normalized),
        }
        _save_library(library)

    return audit, normalized


def get_role_normalized_weight(
    role: str,
    kpi: str,
    library: Optional[Dict[str, Any]] = None,
) -> Optional[float]:
    """Look up a single role+kpi normalized weight from the library.

    Returns None if not configured (caller falls back to existing kpi_weights
    lookup or the auto-normalize-on-the-fly code in core.py).
    """
    if library is None:
        library = _load_library()
    rnw = library.get("role_normalized_weights", {})
    role_map = rnw.get(role)
    if not isinstance(role_map, dict):
        return None
    w = role_map.get(kpi)
    try:
        return float(w) if w is not None else None
    except (TypeError, ValueError):
        return None


# ════════════════════════════════════════════════════════════════════
# Self-test
# ════════════════════════════════════════════════════════════════════

def self_test() -> None:
    print("─ role_weight_engine self-test ─")
    # Synthetic library
    lib = {
        "role_kpis": {
            "Test Role A": ["K001", "K002", "K003"],
            "Test Role B": ["K001", "K004"],
            "Test Role C": [],  # empty
            "_meta_key": ["should be skipped"],
        },
        "kpi_weights": {
            "K001": 0.20,
            "K002": 0.30,
            "K003": 0.10,
            # K004 missing → uses default
        },
    }

    # Role A: 0.20 + 0.30 + 0.10 = 0.60 (not normalized)
    a = audit_role_weight("Test Role A", lib["role_kpis"]["Test Role A"], lib["kpi_weights"])
    assert a.kpi_count == 3
    assert a.kpis_with_weight == 3
    assert a.kpis_missing_weight == 0
    assert abs(a.sum_of_weights - 0.60) < 1e-9
    assert a.is_normalized is False
    assert abs(a.normalization_factor - (1.0 / 0.60)) < 1e-9
    print(f"  ✓ Role A audit: sum={a.sum_of_weights:.2f}, factor={a.normalization_factor:.4f}")

    # Role B: 0.20 + default(0.05) = 0.25
    b = audit_role_weight("Test Role B", lib["role_kpis"]["Test Role B"], lib["kpi_weights"])
    assert b.kpis_missing_weight == 1
    print(f"  ✓ Role B audit: {b.kpis_with_weight} with weight, {b.kpis_missing_weight} missing")

    # Role C: empty
    c = audit_role_weight("Test Role C", lib["role_kpis"]["Test Role C"], lib["kpi_weights"])
    assert c.kpi_count == 0
    assert c.sum_of_weights == 0.0
    print(f"  ✓ Empty role handled")

    # Normalized weights for Role A: each should be its weight / 0.60
    norm_a = compute_role_normalized_weights("Test Role A", lib["role_kpis"]["Test Role A"], lib["kpi_weights"])
    assert abs(sum(norm_a.values()) - 1.0) < 1e-6
    assert abs(norm_a["K001"] - (0.20 / 0.60)) < 1e-9
    print(f"  ✓ Normalized Role A: sum = {sum(norm_a.values()):.4f} (target 1.0)")

    # Bank audit
    bank = bank_role_weight_audit(lib)
    assert bank.total_roles == 3
    assert bank.normalized_count == 0  # none are normalized
    assert bank.broken_count == 3      # all three are broken
    # Meta key skipped
    print(f"  ✓ Bank audit: {bank.normalized_count}/{bank.total_roles} normalized, {bank.broken_count} broken")

    # Migration (write_back=False since we're using a synthetic library)
    audit, normalized = migrate_normalize_all_roles(lib, write_back=False)
    assert "Test Role A" in normalized
    assert "Test Role C" in normalized
    assert "_meta_key" not in normalized
    # Verify each role's normalized weights sum to 1.0 (except empty C which is {})
    for role, w_map in normalized.items():
        if w_map:
            assert abs(sum(w_map.values()) - 1.0) < 1e-6, f"{role} doesn't sum to 1.0"
    print(f"  ✓ Migration normalized {len(normalized)} roles (all sum to 1.0)")

    # get_role_normalized_weight with library that has role_normalized_weights
    lib_with = dict(lib)
    lib_with["role_normalized_weights"] = normalized
    w = get_role_normalized_weight("Test Role A", "K001", lib_with)
    assert w is not None
    assert abs(w - (0.20 / 0.60)) < 1e-9
    print(f"  ✓ get_role_normalized_weight retrieves normalized value")

    # Missing role returns None
    assert get_role_normalized_weight("Nonexistent", "K001", lib_with) is None

    # Zero streamlit imports
    import re
    this_file = Path(__file__).read_text()
    streamlit_imports = re.findall(
        r"^\s*(?:import\s+streamlit|from\s+streamlit)\b",
        this_file, re.MULTILINE,
    )
    assert len(streamlit_imports) == 0
    print("  ✓ Zero streamlit imports (React-ready)")

    print("✓ self_test passed")


if __name__ == "__main__":
    self_test()
