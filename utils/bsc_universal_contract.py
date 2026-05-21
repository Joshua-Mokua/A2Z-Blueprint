"""utils/bsc_universal_contract.py — v10.377 Universal BSC Data Contract.

The nervous system of the body. Per the official Technical Governance
Framework (Section 5.1): "Every module MUST output data in the following
standardized structure: staff_code, kpi_id, value, period, source_module.
All performance data MUST ultimately flow into performance.actuals.
No module may bypass this structure."

This module establishes the contract layer that all canonical engines
output through. v10.376 surfaced canonical PBT in the MD cockpit via a
read-only bridge; v10.377 generalizes the pattern: any canonical engine,
any KPI, conforming to one schema.

Module purity
-------------
Leaf module. Zero upward imports. Pure validation + conversion logic.

Contract enforcement
--------------------
The 5 mandatory fields per Section 5.1:
  - staff_code:    str (non-empty)
  - kpi_id:        str (matches kpi_library if known; non-empty)
  - value:         numeric (int / float / Decimal)
  - period:        str (period code like '2026' / '2026-Q2' / '2026-04')
  - source_module: str (provenance: who produced this record)

Optional metadata fields:
  - actor:         str (which user/process submitted; default 'system')
  - metadata:      dict (engine-specific context: tier, branch_code, sbu, etc.)

Validation rules (strict):
  - All 5 mandatory fields present and non-empty
  - staff_code is a string (no numeric coercion silent)
  - kpi_id is a string
  - value coerces to float without raising (None / 'NaN' / 'inf' rejected)
  - period matches one of the period formats
  - source_module follows convention (snake_case, ends with '_v<batch>' optional)

The source_module convention (per Section 5.2 — every record traceable to
its producing module):
  canonical_<dimension>_engine_v<batch>
    e.g. canonical_pbt_staff_engine_v10377
         canonical_pbt_branch_engine_v10377
         canonical_pbt_sbu_engine_v10377
         canonical_pbt_bank_engine_v10377
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, asdict
from decimal import Decimal
from typing import Any, Dict, List, Optional, Union

# Accepted period formats. Bank can extend this list (e.g. add weekly).
PERIOD_FORMATS = (
    re.compile(r"^\d{4}$"),                # 2026
    re.compile(r"^\d{4}-Q[1-4]$"),         # 2026-Q2
    re.compile(r"^\d{4}-(0[1-9]|1[0-2])$"),  # 2026-04
    re.compile(r"^\d{4}-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])$"),  # 2026-04-15 daily
)

# Source module naming convention — informative for traceability per Section 5.2
SOURCE_MODULE_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")


@dataclass
class UniversalBSCRecord:
    """One record in the Universal BSC Data Contract (Section 5.1).

    Maps verbatim to bsc_engine.submit() signature so write-bridge is a
    no-friction call.
    """
    staff_code:    str
    kpi_id:        str
    value:         float       # internal storage as float
    period:        str
    source_module: str
    actor:         str = "system"
    metadata:      Dict[str, Any] = field(default_factory=dict)

    def to_submit_kwargs(self) -> Dict[str, Any]:
        """Return kwargs ready for bsc_engine.submit(**record.to_submit_kwargs())."""
        return {
            "staff_code":    self.staff_code,
            "kpi_id":        self.kpi_id,
            "value":         self.value,
            "period":        self.period,
            "source_module": self.source_module,
            "actor":         self.actor,
            "metadata":      dict(self.metadata),
        }

    def to_dict(self) -> Dict[str, Any]:
        """Plain dict for serialization / logging."""
        return asdict(self)


class ContractViolation(ValueError):
    """Raised when a record fails contract validation. Per Section 5.4 —
    silent failures are prohibited."""


def _coerce_value(v: Any) -> float:
    """Coerce numeric input to float, raising ContractViolation if invalid."""
    if v is None:
        raise ContractViolation("value is None — explicit numeric required")
    if isinstance(v, bool):
        # Reject bool — Python's bool is technically int, but it's meaningless as a KPI value
        raise ContractViolation("value is bool — numeric required")
    if isinstance(v, (int, float, Decimal)):
        try:
            f = float(v)
        except (ValueError, OverflowError) as exc:
            raise ContractViolation(f"value not convertible to float: {exc}") from exc
        # Reject NaN and inf — banking data MUST be finite
        if f != f:  # NaN
            raise ContractViolation("value is NaN — banking data must be finite")
        if f == float("inf") or f == float("-inf"):
            raise ContractViolation("value is infinite — banking data must be finite")
        return f
    raise ContractViolation(f"value type {type(v).__name__} not numeric")


def validate_universal_record(record: UniversalBSCRecord) -> None:
    """Strict validation per the contract.

    Raises ContractViolation on any breach. Per Section 5.4 — silent
    failures are prohibited.
    """
    if not record.staff_code or not isinstance(record.staff_code, str):
        raise ContractViolation("staff_code must be a non-empty string")
    if not record.kpi_id or not isinstance(record.kpi_id, str):
        raise ContractViolation("kpi_id must be a non-empty string")
    # value: already coerced in builder; re-validate
    _ = _coerce_value(record.value)
    if not record.period or not isinstance(record.period, str):
        raise ContractViolation("period must be a non-empty string")
    if not any(p.match(record.period) for p in PERIOD_FORMATS):
        raise ContractViolation(
            f"period {record.period!r} does not match any accepted format: "
            f"YYYY / YYYY-QN / YYYY-MM / YYYY-MM-DD"
        )
    if not record.source_module or not isinstance(record.source_module, str):
        raise ContractViolation("source_module must be a non-empty string")
    if not SOURCE_MODULE_PATTERN.match(record.source_module):
        raise ContractViolation(
            f"source_module {record.source_module!r} must be snake_case "
            f"(lowercase + digits + underscores; starts with letter)"
        )
    if not isinstance(record.metadata, dict):
        raise ContractViolation("metadata must be a dict (can be empty)")


def make_record(
    staff_code:    str,
    kpi_id:        str,
    value:         Union[int, float, Decimal],
    period:        str,
    source_module: str,
    actor:         str = "system",
    metadata:      Optional[Dict[str, Any]] = None,
) -> UniversalBSCRecord:
    """Construct and validate a UniversalBSCRecord in one call.

    Use this rather than UniversalBSCRecord(...) directly so validation
    runs at construction time. Raises ContractViolation on bad input.
    """
    record = UniversalBSCRecord(
        staff_code=str(staff_code) if staff_code is not None else "",
        kpi_id=str(kpi_id) if kpi_id is not None else "",
        value=_coerce_value(value),
        period=str(period) if period is not None else "",
        source_module=str(source_module) if source_module is not None else "",
        actor=str(actor) if actor is not None else "system",
        metadata=dict(metadata) if metadata else {},
    )
    validate_universal_record(record)
    return record


def validate_batch(records: List[UniversalBSCRecord]) -> Dict[str, Any]:
    """Validate a batch of records. Returns aggregate stats per Section 5.4.

    Does NOT raise on individual violations — collects them for batch
    inspection. Caller decides whether to proceed.
    """
    valid: List[UniversalBSCRecord] = []
    violations: List[Dict[str, Any]] = []
    for i, r in enumerate(records):
        try:
            validate_universal_record(r)
            valid.append(r)
        except ContractViolation as exc:
            violations.append({
                "index": i,
                "staff_code": getattr(r, "staff_code", "?"),
                "kpi_id": getattr(r, "kpi_id", "?"),
                "error": str(exc),
            })
    return {
        "total":          len(records),
        "valid":          len(valid),
        "violations":     len(violations),
        "violation_detail": violations,
        "valid_records":  valid,
    }


def records_summary(records: List[UniversalBSCRecord]) -> Dict[str, Any]:
    """Return summary stats for a batch — useful for logging + tests."""
    if not records:
        return {"count": 0, "by_kpi": {}, "by_source": {}, "periods": [], "total_value": 0.0}
    by_kpi: Dict[str, int] = {}
    by_source: Dict[str, int] = {}
    periods = set()
    total = 0.0
    for r in records:
        by_kpi[r.kpi_id] = by_kpi.get(r.kpi_id, 0) + 1
        by_source[r.source_module] = by_source.get(r.source_module, 0) + 1
        periods.add(r.period)
        total += r.value
    return {
        "count":       len(records),
        "by_kpi":      by_kpi,
        "by_source":   by_source,
        "periods":     sorted(periods),
        "total_value": total,
    }


def self_test() -> None:
    """v10.377 self_test — uses hand-rolled fixtures only (v10.364 rule)."""
    tests = 0

    # Test 1: valid record constructs + validates
    r = make_record(
        staff_code="300001",
        kpi_id="PBT",
        value=22_000_000_000.0,
        period="2026",
        source_module="canonical_pbt_bank_engine_v10377",
        metadata={"dimension": "bank"},
    )
    assert r.staff_code == "300001"
    assert r.kpi_id == "PBT"
    assert r.value == 22_000_000_000.0
    tests += 1

    # Test 2: empty staff_code rejected
    try:
        make_record(staff_code="", kpi_id="PBT", value=100, period="2026",
                    source_module="canonical_pbt_bank_engine_v10377")
        assert False, "should reject empty staff_code"
    except ContractViolation as e:
        assert "staff_code" in str(e)
    tests += 1

    # Test 3: NaN value rejected
    try:
        make_record(staff_code="X", kpi_id="PBT", value=float("nan"), period="2026",
                    source_module="canonical_pbt_bank_engine_v10377")
        assert False, "should reject NaN"
    except ContractViolation as e:
        assert "NaN" in str(e)
    tests += 1

    # Test 4: bad period format rejected
    try:
        make_record(staff_code="X", kpi_id="PBT", value=1, period="Q2-2026",
                    source_module="canonical_pbt_bank_engine_v10377")
        assert False, "should reject Q2-2026"
    except ContractViolation as e:
        assert "period" in str(e)
    tests += 1

    # Test 5: bad source_module pattern rejected
    try:
        make_record(staff_code="X", kpi_id="PBT", value=1, period="2026",
                    source_module="Canonical PBT Engine v10.377")
        assert False, "should reject non-snake_case source_module"
    except ContractViolation as e:
        assert "snake_case" in str(e)
    tests += 1

    # Test 6: to_submit_kwargs mirrors bsc_engine.submit signature exactly
    r = make_record(staff_code="300001", kpi_id="PBT", value=1.0, period="2026",
                    source_module="canonical_pbt_bank_engine_v10377")
    kw = r.to_submit_kwargs()
    assert set(kw.keys()) == {"staff_code", "kpi_id", "value", "period",
                                "source_module", "actor", "metadata"}
    tests += 1

    # Test 7: validate_batch surfaces violations per Section 5.4 (no silent fail)
    good = make_record(staff_code="A", kpi_id="PBT", value=1, period="2026",
                       source_module="canonical_pbt_bank_engine_v10377")
    bad = UniversalBSCRecord(staff_code="", kpi_id="PBT", value=1, period="2026",
                              source_module="canonical_pbt_bank_engine_v10377")
    result = validate_batch([good, bad])
    assert result["total"] == 2
    assert result["valid"] == 1
    assert result["violations"] == 1
    tests += 1

    # Test 8: records_summary aggregates correctly
    r1 = make_record(staff_code="A", kpi_id="PBT", value=10, period="2026",
                     source_module="canonical_pbt_staff_engine_v10377")
    r2 = make_record(staff_code="B", kpi_id="PBT", value=20, period="2026",
                     source_module="canonical_pbt_staff_engine_v10377")
    r3 = make_record(staff_code="C", kpi_id="NPL_RATIO", value=5, period="2026-Q2",
                     source_module="canonical_npl_engine_v10377")
    summary = records_summary([r1, r2, r3])
    assert summary["count"] == 3
    assert summary["by_kpi"]["PBT"] == 2
    assert summary["by_kpi"]["NPL_RATIO"] == 1
    assert summary["total_value"] == 35
    tests += 1

    # Test 9: bool rejected as value (Python tomfoolery)
    try:
        make_record(staff_code="X", kpi_id="PBT", value=True, period="2026",
                    source_module="canonical_pbt_bank_engine_v10377")
        assert False, "should reject bool"
    except ContractViolation:
        pass
    tests += 1

    # Test 10: Decimal value accepted
    r = make_record(staff_code="X", kpi_id="PBT", value=Decimal("12345.67"),
                    period="2026",
                    source_module="canonical_pbt_bank_engine_v10377")
    assert r.value == 12345.67
    tests += 1

    print(f"✓ bsc_universal_contract self_test passed ({tests} tests)")


if __name__ == "__main__":
    self_test()
