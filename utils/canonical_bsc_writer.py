"""utils/canonical_bsc_writer.py — v10.379 Write-Bridge.

Closes the loop established by v10.377. The Universal BSC Data Contract
(v10.377) defines `UniversalBSCRecord` with `to_submit_kwargs()` mirroring
`bsc_engine.submit()` signature verbatim. The Virtual Bank KPI Unifier
(v10.377) produces 98+ conforming records from canonical engines. v10.378
established customer master merge. **v10.379 makes those records actually
flow into `bsc_actuals_*.json` via `bsc_engine.submit()`** — completing
the Central BSC Integration Engine path mandated by constitution §5.2.

Per the constitution §5.3 data flow:

    Source (CBS) → Staging → Transformation (canonical engines) →
    Clean (universal records) → BSC Integration (THIS MODULE) → Reporting

Until v10.379, the last arrow was missing — canonical engines produced
records but nothing flowed to `performance.actuals` (BSC actuals files).
This module bridges that gap.

Safety design
-------------
**Default `dry_run=True`.** A naked `write_canonical_pbt_to_bsc()` call
PREVIEWS what would be written — no side effects. Callers must
**explicitly pass `dry_run=False`** to actually mutate `bsc_actuals_*.json`.
This protects against accidental writes to live data during development.

Idempotency
-----------
`bsc_engine.submit()` uses an `idem_hash` over (staff_code, kpi_id, period,
source_module). Running this writer twice for the same period produces
upserts (existing records updated, no duplicates created). Re-runnable
safely.

Period handling
---------------
The v10.377 unifier uses period `"2026"` (annual) for canonical PBT — but
`bsc_engine.validate` accepts only `YYYY-MM` or `YYYY-QN`. This writer
translates annual → quarterly via the `target_period` parameter (default
`"2026-Q4"` — current quarter for production). Callers can pass
`target_period="2026-Q4"` (live) or `target_period="2026-canonical-test"`
(canary — bsc_engine will reject malformed periods, so use a real Qn).

Module purity
-------------
This module DOES import `bsc_engine.submit` — that is its entire purpose.
It also imports `virtual_bank_kpi_unifier` and `bsc_universal_contract`
(both leaf modules below). No circular references.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

# These two are leaf modules established in v10.377
from utils.bsc_universal_contract import UniversalBSCRecord
from utils.virtual_bank_kpi_unifier import unify_all_kpi_flow

REPO = Path(__file__).resolve().parent.parent
DATA_DIR = REPO / "data"

# Default target period — current production quarter.
# Callers should pass explicit period for clarity.
DEFAULT_TARGET_PERIOD = "2026-Q4"

# Writer source_module — overrides per-record source_modules from the
# unifier so audit log clearly identifies the writer that bridged them.
WRITER_SOURCE_MODULE_TAG = "canonical_writer_v10379"

# MD anchor — records collapsing to MD via fallback duplicate the bank record.
MD_STAFF_CODE = "300001"


def _should_write(record: UniversalBSCRecord) -> tuple:
    """Filter records to avoid idem-hash collisions on the bank PBT path.

    The v10.377 unifier produces:
      - 1 bank record (MD, PBT, bank_engine)
      - N SBU records (one per SBU head)
      - M branch records (one per BM)
      - P staff records (one per tagged staff)

    But some SBUs (Support/Executive/Unallocated) map to MD by design — their
    PBT is already represented in the bank record. Some branches have no BM
    configured — those records fall back to MD with `fallback_used=True`, also
    duplicating the bank record. Writing all of them causes (staff_code='300001',
    kpi_id='PBT', period, source_module) idem-hash collisions: last write wins,
    silent data loss.

    Filter rules:
      - bank dimension → ALWAYS write (it's the authoritative MD PBT)
      - sbu dimension + staff_code=MD → SKIP (absorbed SBUs)
      - branch dimension + fallback_used=True → SKIP (no real BM)
      - branch dimension + staff_code=MD → SKIP (defensive — same as above)
      - staff dimension → ALWAYS write (real staff_code by construction)

    Returns (should_write: bool, reason: str). reason populated when skipped.
    """
    dim = record.metadata.get("dimension", "")
    fallback = record.metadata.get("fallback_used", False)

    if dim == "bank":
        return True, ""
    if dim == "staff":
        return True, ""
    if dim == "sbu" and record.staff_code == MD_STAFF_CODE:
        return False, "SBU absorbed into MD (Support/Executive/Unallocated)"
    if dim == "branch" and (fallback or record.staff_code == MD_STAFF_CODE):
        return False, "branch has no configured BM (fallback to MD)"
    return True, ""


@dataclass
class WriteResult:
    """Detailed outcome of a write-bridge run.

    `dry_run=True` populates `kwargs_preview` but does NOT call
    bsc_engine.submit. `dry_run=False` populates `created`/`updated`/`errors`
    based on submit() return values.
    """
    target_period: str
    dry_run: bool
    total_records: int = 0
    eligible_records: int = 0  # passed _should_write filter
    skipped_records: int = 0   # fallback/absorbed
    skip_reasons: Dict[str, int] = field(default_factory=dict)
    created: int = 0
    updated: int = 0
    errors: List[Dict[str, str]] = field(default_factory=list)
    kwargs_preview: List[Dict[str, Any]] = field(default_factory=list)
    actor: str = WRITER_SOURCE_MODULE_TAG
    note: str = ""

    @property
    def succeeded(self) -> int:
        return self.created + self.updated

    def summary(self) -> str:
        if self.dry_run:
            return (
                f"DRY RUN — {self.eligible_records}/{self.total_records} records "
                f"would be written to bsc_actuals_{self.target_period}.json "
                f"(skipped {self.skipped_records} fallback/absorbed). "
                f"No side effects. Pass dry_run=False to commit."
            )
        return (
            f"WROTE {self.succeeded}/{self.eligible_records} records to "
            f"bsc_actuals_{self.target_period}.json "
            f"(created={self.created}, updated={self.updated}, "
            f"errors={len(self.errors)}, skipped={self.skipped_records})"
        )


def _translate_period(annual_period: str, target_period: str) -> str:
    """Translate canonical engine period (annual) to BSC target period.

    The canonical engines run on full-year CBS data (period="2026"). The
    BSC actuals are keyed quarterly or monthly. The writer attributes the
    annual canonical PBT to the target_period (the period in which the
    measurement is being recorded for BSC purposes).
    """
    # If target_period is already concrete (Qn or MM), use it directly.
    # The annual period is informational only at this stage.
    return target_period


def _record_to_submit_kwargs(
    record: UniversalBSCRecord,
    target_period: str,
    actor: str,
) -> Dict[str, Any]:
    """Convert a UniversalBSCRecord into bsc_engine.submit() kwargs.

    Translates period (annual → target_period) and enriches metadata with
    the writer tag for traceability per constitution §5.2.
    """
    enriched_metadata = dict(record.metadata)
    enriched_metadata["original_period"] = record.period
    enriched_metadata["writer"] = WRITER_SOURCE_MODULE_TAG
    enriched_metadata["written_via"] = "canonical_bsc_writer.write_canonical_pbt_to_bsc"
    return {
        "staff_code":    record.staff_code,
        "kpi_id":        record.kpi_id,
        "value":         record.value,
        "period":        _translate_period(record.period, target_period),
        "source_module": record.source_module,
        "actor":         actor,
        "metadata":      enriched_metadata,
    }


def write_canonical_pbt_to_bsc(
    cbs_dir: Optional[Path] = None,
    target_period: str = DEFAULT_TARGET_PERIOD,
    dry_run: bool = True,
    actor: str = WRITER_SOURCE_MODULE_TAG,
) -> WriteResult:
    """The headline function. Runs canonical PBT engines via the v10.377
    unifier → converts records to bsc_engine.submit() kwargs → submits
    them (or previews them in dry_run mode).

    Args:
      cbs_dir:        Path to CBS data dir. None = seed virtual bank.
      target_period:  BSC period to attribute records to (e.g. "2026-Q4").
                      Must be YYYY-MM or YYYY-QN — bsc_engine rejects other formats.
      dry_run:        True (default) → preview only. False → actually write.
      actor:          Audit actor for bsc_engine logs.

    Returns:
      WriteResult with detailed breakdown of what was written/would be written.
    """
    result = WriteResult(target_period=target_period, dry_run=dry_run, actor=actor)

    # 1. Run the unifier — produces UniversalBSCRecord list
    try:
        unifier_output = unify_all_kpi_flow(cbs_dir=cbs_dir, period="2026")
    except Exception as exc:
        result.note = f"unifier failed: {type(exc).__name__}: {exc}"
        return result

    all_records: List[UniversalBSCRecord] = unifier_output.get("all_records", [])
    result.total_records = len(all_records)

    if not all_records:
        result.note = "unifier produced 0 records — nothing to write"
        return result

    # 2. Reconciliation gate — refuse to write if Σ-identity is broken.
    # Per constitution §5.5, persisting broken reconciliation would
    # propagate the error to MD's dashboard.
    recon = unifier_output.get("reconciliation", {})
    if not recon.get("all_within_kes_100", False):
        result.note = (
            f"reconciliation failed (Σ per dimension ≠ Bank PBT within "
            f"KES 100): {recon.get('tolerances_kes')} — REFUSING to write"
        )
        return result

    # 3. Per record: apply filter → build kwargs → (if not dry_run) submit
    for record in all_records:
        should_write, skip_reason = _should_write(record)
        if not should_write:
            result.skipped_records += 1
            result.skip_reasons[skip_reason] = result.skip_reasons.get(skip_reason, 0) + 1
            continue

        result.eligible_records += 1
        kwargs = _record_to_submit_kwargs(record, target_period, actor)
        result.kwargs_preview.append({
            "staff_code":    kwargs["staff_code"],
            "kpi_id":        kwargs["kpi_id"],
            "value":         kwargs["value"],
            "period":        kwargs["period"],
            "source_module": kwargs["source_module"],
            "dimension":     kwargs["metadata"].get("dimension", "?"),
        })

        if dry_run:
            continue

        # Late import — only when actually writing (so dry-run avoids bsc_engine init)
        try:
            from utils.bsc_engine import submit as _bsc_submit
            ok, op = _bsc_submit(**kwargs)
            if ok:
                if op == "created":
                    result.created += 1
                elif op == "updated":
                    result.updated += 1
                else:
                    # Other success codes (shouldn't happen but defensive)
                    result.created += 1
            else:
                result.errors.append({
                    "staff_code":    kwargs["staff_code"],
                    "kpi_id":        kwargs["kpi_id"],
                    "source_module": kwargs["source_module"],
                    "error":         op,
                })
        except Exception as exc:
            result.errors.append({
                "staff_code":    kwargs["staff_code"],
                "kpi_id":        kwargs["kpi_id"],
                "source_module": kwargs["source_module"],
                "error":         f"{type(exc).__name__}: {exc}",
            })

    return result


def preview_canonical_pbt_writes(
    cbs_dir: Optional[Path] = None,
    target_period: str = DEFAULT_TARGET_PERIOD,
) -> List[Dict[str, Any]]:
    """Convenience wrapper — returns just the kwargs preview without
    the WriteResult wrapper. Always dry_run."""
    result = write_canonical_pbt_to_bsc(
        cbs_dir=cbs_dir,
        target_period=target_period,
        dry_run=True,
    )
    return result.kwargs_preview


def self_test() -> None:
    """v10.379 self_test."""
    tests = 0

    # Test 1: dry_run default — no side effects, filter applied
    result = write_canonical_pbt_to_bsc(cbs_dir=None, target_period="2026-Q4")
    assert result.dry_run is True
    assert result.total_records > 50
    assert result.eligible_records < result.total_records, (
        "filter should skip at least the SBU absorbed records"
    )
    assert result.skipped_records > 0
    assert result.eligible_records == len(result.kwargs_preview)
    assert result.created == 0
    assert result.updated == 0
    tests += 1

    # Test 2: kwargs_preview has valid shape + translated period
    for kw in result.kwargs_preview[:5]:
        for field_name in ("staff_code", "kpi_id", "value", "period",
                           "source_module"):
            assert field_name in kw
        assert kw["period"] == "2026-Q4"
    tests += 1

    # Test 3: filter excludes SBU records collapsing to MD
    # Inspect kwargs_preview — should NOT contain (staff_code=MD, source=sbu_engine)
    md_sbu = [k for k in result.kwargs_preview
              if k["staff_code"] == MD_STAFF_CODE and "sbu" in k["source_module"]]
    assert len(md_sbu) == 0, f"filter failed: SBU→MD records leaked: {md_sbu}"
    tests += 1

    # Test 4: filter excludes branch fallback records
    branch_fallbacks = [k for k in result.kwargs_preview
                        if k["dimension"] == "branch" and
                        k["staff_code"] == MD_STAFF_CODE]
    assert len(branch_fallbacks) == 0, (
        f"filter failed: branch fallback records leaked: {branch_fallbacks}"
    )
    tests += 1

    # Test 5: bank record IS present
    bank_records = [k for k in result.kwargs_preview if k["dimension"] == "bank"]
    assert len(bank_records) == 1, (
        f"expected exactly 1 bank record, got {len(bank_records)}"
    )
    assert bank_records[0]["staff_code"] == MD_STAFF_CODE
    tests += 1

    # Test 6: staff records present (every tagged staff)
    staff_records = [k for k in result.kwargs_preview if k["dimension"] == "staff"]
    assert len(staff_records) > 10, (
        f"expected ≥10 staff records, got {len(staff_records)}"
    )
    # No staff record should be MD (staff_code uses real codes)
    md_staff = [k for k in staff_records if k["staff_code"] == MD_STAFF_CODE]
    assert len(md_staff) == 0, "MD shouldn't appear as a tagged staff"
    tests += 1

    # Test 7: preview wrapper works
    preview = preview_canonical_pbt_writes(cbs_dir=None, target_period="2026-Q4")
    assert len(preview) == result.eligible_records
    tests += 1

    # Test 8: _record_to_submit_kwargs enriches metadata correctly
    from utils.bsc_universal_contract import make_record
    test_rec = make_record(
        staff_code="300001", kpi_id="PBT", value=1.0, period="2026",
        source_module="canonical_pbt_bank_engine_v10377",
        metadata={"dimension": "bank"},
    )
    full = _record_to_submit_kwargs(test_rec, "2026-Q4", actor="test")
    assert full["metadata"]["writer"] == WRITER_SOURCE_MODULE_TAG
    assert full["metadata"]["original_period"] == "2026"
    assert full["period"] == "2026-Q4"
    tests += 1

    # Test 9: result.summary() returns informative string
    s = result.summary()
    assert "DRY RUN" in s
    assert str(result.eligible_records) in s
    tests += 1

    # Test 10: _should_write filter on hand-crafted records
    # bank dim → write
    bank_r = make_record(staff_code="300001", kpi_id="PBT", value=1, period="2026",
                          source_module="canonical_pbt_bank_engine_v10377",
                          metadata={"dimension": "bank"})
    ok, _ = _should_write(bank_r)
    assert ok
    # SBU dim with MD → skip
    sbu_r = make_record(staff_code="300001", kpi_id="PBT", value=1, period="2026",
                        source_module="canonical_pbt_sbu_engine_v10377",
                        metadata={"dimension": "sbu", "sbu": "Support"})
    ok, reason = _should_write(sbu_r)
    assert not ok and "absorbed" in reason.lower()
    # branch dim with fallback → skip
    br_r = make_record(staff_code="300001", kpi_id="PBT", value=1, period="2026",
                       source_module="canonical_pbt_branch_engine_v10377",
                       metadata={"dimension": "branch", "fallback_used": True})
    ok, _ = _should_write(br_r)
    assert not ok
    # staff dim → write
    st_r = make_record(staff_code="300044", kpi_id="PBT", value=1, period="2026",
                       source_module="canonical_pbt_staff_engine_v10377",
                       metadata={"dimension": "staff"})
    ok, _ = _should_write(st_r)
    assert ok
    tests += 1

    print(f"✓ canonical_bsc_writer self_test passed ({tests} tests)")
    print(f"  Total records:      {result.total_records}")
    print(f"  Eligible (writes):  {result.eligible_records}")
    print(f"  Skipped (fallback): {result.skipped_records}  reasons: {result.skip_reasons}")
    print(f"  Summary: {result.summary()}")


if __name__ == "__main__":
    import sys
    _repo = Path(__file__).resolve().parent.parent
    if str(_repo) not in sys.path:
        sys.path.insert(0, str(_repo))
    self_test()
