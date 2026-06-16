"""utils/collateral_coverage.py — coverage ratio + security classification (P4-3).

Pure, dependency-free (stdlib + utils.fx_engine for KES normalization). The
disbursement gate (P4-6) consumes the classification; this module only computes.

Contract (docs/PHASE4_SECURED_LENDING_DESIGN.md §6 + DELTA):
  coverage_ratio = Σ(forced_sale_value of linked collateral, KES-equiv,
                     capped at allocated_value if set)
                   / facility_amount_kes_equiv

  security_classification (gradient, derived from coverage vs required ratio):
    unsecured          coverage_ratio == 0 (no acceptable collateral)
    partially_secured  0 < coverage_ratio < required_ratio
    fully_secured      required_ratio <= coverage_ratio <= required*over_mult
    over_secured       coverage_ratio > required_ratio * over_secured_multiple

Required ratio comes from the admin Credit Policy Matrix, keyed by collateral
type. When a facility links multiple collateral types, the CONSERVATIVE (max)
required ratio across linked types applies unless an explicit security_subtype
override is supplied.
"""
from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from typing import List, Optional

_DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DEFAULT_MATRIX_PATH = _DATA_DIR / "credit_policy_matrix.json"

UNSECURED = "unsecured"
PARTIALLY = "partially_secured"
FULLY = "fully_secured"
OVER = "over_secured"


class CreditPolicyMatrix:
    """Admin-configurable required-coverage matrix. Loud on corrupt file;
    tolerant of an absent file (returns conservative defaults)."""

    def __init__(self, path: Optional[Path] = None):
        self.path = Path(path) if path else DEFAULT_MATRIX_PATH
        self._pct = {}
        self._over_multiple = Decimal("1.25")
        self._valuation_max_age_days = 365
        self.load()

    def load(self) -> None:
        if not self.path.exists():
            self._pct = {}
            return
        raw = self.path.read_text(encoding="utf-8")
        if not raw.strip():
            self._pct = {}
            return
        data = json.loads(raw)  # corrupt -> raises, by design
        self._pct = dict(data.get("required_coverage_pct", {}))
        self._over_multiple = Decimal(str(data.get("over_secured_multiple", "1.25")))
        self._valuation_max_age_days = int(data.get("valuation_max_age_days", 365))

    @property
    def over_secured_multiple(self) -> Decimal:
        return self._over_multiple

    @property
    def valuation_max_age_days(self) -> int:
        return self._valuation_max_age_days

    def required_ratio(self, collateral_type: str) -> Optional[Decimal]:
        """Required coverage ratio (as a decimal, e.g. 1.25) for a collateral
        type, or None if the type is not in the matrix."""
        if collateral_type in self._pct:
            return Decimal(str(self._pct[collateral_type])) / Decimal("100")
        return None

    def required_ratio_for(self, types: List[str],
                           subtype_override: Optional[str] = None) -> Decimal:
        """Conservative required ratio across linked collateral types. If an
        explicit subtype is given and known, it wins. Falls back to the highest
        configured ratio (or 1.0 if nothing matches — never below par)."""
        if subtype_override:
            r = self.required_ratio(subtype_override)
            if r is not None:
                return r
        ratios = [self.required_ratio(t) for t in (types or [])]
        ratios = [r for r in ratios if r is not None]
        return max(ratios) if ratios else Decimal("1.0")


def _kes_value(item: dict) -> Decimal:
    """Resolve a linked-collateral item's KES-equiv forced-sale value, capped at
    the allocated value if one is set. Prefers pre-normalized *_kes fields;
    falls back to fx_engine for native+currency."""
    # allocated value (KES) caps the contribution
    fsv_kes = item.get("forced_sale_value_kes")
    if fsv_kes is None:
        native = item.get("forced_sale_value")
        cur = item.get("currency", "KES")
        if native is not None:
            try:
                from utils.fx_engine import normalize_money
                fsv_kes = float(normalize_money(native, cur).amount_kes)
            except Exception:
                fsv_kes = None
    fsv = Decimal(str(fsv_kes)) if fsv_kes is not None else Decimal("0")
    alloc = item.get("allocated_value_kes")
    if alloc is not None:
        try:
            return min(fsv, Decimal(str(alloc)))
        except Exception:
            return fsv
    return fsv


def compute_coverage_ratio(facility_amount_kes, linked: List[dict]) -> Decimal:
    """coverage_ratio = Σ(FSV KES, capped at allocation) / facility KES.
    Returns 0 if facility amount is non-positive or no collateral."""
    try:
        fac = Decimal(str(facility_amount_kes or 0))
    except Exception:
        fac = Decimal("0")
    if fac <= 0:
        return Decimal("0")
    total = sum((_kes_value(i) for i in (linked or [])), Decimal("0"))
    return (total / fac).quantize(Decimal("0.0001"))


def classify_security(coverage_ratio: Decimal, required_ratio: Decimal,
                      over_secured_multiple: Decimal = Decimal("1.25")) -> str:
    cov = Decimal(str(coverage_ratio or 0))
    req = Decimal(str(required_ratio or 0))
    if cov <= 0:
        return UNSECURED
    if req <= 0:
        # no requirement configured -> any positive coverage is "fully"
        return FULLY
    if cov < req:
        return PARTIALLY
    if cov <= req * over_secured_multiple:
        return FULLY
    return OVER


def assess_facility(facility_amount_kes, linked: List[dict],
                    subtype_override: Optional[str] = None,
                    matrix: Optional[CreditPolicyMatrix] = None) -> dict:
    """One-shot assessment for a facility: coverage ratio, required ratio,
    classification, and the contributing security total. Pure."""
    m = matrix or CreditPolicyMatrix()
    types = [str(i.get("collateral_type", "")) for i in (linked or []) if i.get("collateral_type")]
    required = m.required_ratio_for(types, subtype_override)
    coverage = compute_coverage_ratio(facility_amount_kes, linked)
    classification = classify_security(coverage, required, m.over_secured_multiple)
    return {
        "facility_amount_kes": float(Decimal(str(facility_amount_kes or 0))),
        "security_total_kes": float(sum((_kes_value(i) for i in (linked or [])), Decimal("0"))),
        "coverage_ratio": float(coverage),
        "required_ratio": float(required),
        "over_secured_multiple": float(m.over_secured_multiple),
        "security_classification": classification,
        "collateral_types": types,
    }
