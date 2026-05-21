"""utils/virtual_bank_kpi_unifier.py — v10.377 Virtual Bank KPI Flow Unifier.

Per Joshua's directive at v10.377 entry: "Let's have our virtual bank unify
how all KPIs flow, test all modules and ensure every staff works and is
measured."

This module is the demonstration that the seeded virtual bank produces
records conforming to the Universal BSC Data Contract (Section 5.1) for
every level of the PBT canonical engine output:

    1 record:  Bank PBT       (staff_code = MD = "300001")
    N records: SBU PBTs       (staff_code = SBU head Chief)
    M records: Branch PBTs    (staff_code = Branch Manager)
    P records: Staff PBTs     (staff_code = tagged staff)

Every record validates against bsc_universal_contract. Body-system framing:
this is the **nervous system** — signal-carrying records flowing from every
organ (engine) into the BSC sink, in one common contract format.

PBT is the prototype. Phase D extends to all 109 active KPIs.

Module purity
-------------
Consumes the canonical engines (pbt_computation, customer_pbt_allocator,
branch_pbt_allocator) and the role taxonomy (role_taxonomy). Produces
universal records (bsc_universal_contract). Read-only — does NOT submit
to bsc_actuals. Write-bridge is v10.379 scope.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from utils.bsc_universal_contract import (
    UniversalBSCRecord, make_record, records_summary, validate_batch,
)

REPO = Path(__file__).resolve().parent.parent
DATA_DIR = REPO / "data"

# Anchor IDs per the canonical org hierarchy (org_hierarchy_config.json)
MD_STAFF_CODE = "300001"

# SBU head mapping — per org_hierarchy_config::chiefs.
# v10.403: Updated from synthetic EXEC-* codes to real chief staff codes
# (EXEC-* placeholders were removed in v10.403 cleanup batch).
SBU_HEAD_STAFF_CODE = {
    "Retail Banking":     "300002",  # Chief Retail Banking Officer (was EXEC-CRO-001)
    "Commercial Banking": "300003",  # Chief Commercial Officer (was EXEC-CCMO-001)
    "Corporate Banking":  "300003",  # Per Joshua's note, Commercial covers Corporate
    "Treasury":           "300003",  # Treasury reports to Commercial in this bank
    "Digital_Agency":     "300007",  # Chief Information Officer (was EXEC-CIO-001)
    "Support":            MD_STAFF_CODE,    # Support functions roll up to MD
    "Executive":          MD_STAFF_CODE,
    "Unallocated":        MD_STAFF_CODE,    # absorbed bucket
}

# Default period for the virtual bank — calendar year for now
DEFAULT_PERIOD = "2026"

# Source module naming follows Section 5.2 convention
SRC_BANK_ENGINE     = "canonical_pbt_bank_engine_v10377"
SRC_SBU_ENGINE      = "canonical_pbt_sbu_engine_v10377"
SRC_BRANCH_ENGINE   = "canonical_pbt_branch_engine_v10377"
SRC_STAFF_ENGINE    = "canonical_pbt_staff_engine_v10377"


def _load_users() -> Dict[str, Dict[str, str]]:
    """Build a staff_code → {role, full_name, department, branch_code} lookup."""
    users_path = DATA_DIR / "users.json"
    if not users_path.exists():
        return {}
    out: Dict[str, Dict[str, str]] = {}
    try:
        u = json.loads(users_path.read_text(encoding="utf-8"))
        for login, rec in u.items():
            if isinstance(rec, dict):
                sc = rec.get("staff_code", "")
                if sc:
                    out[sc] = {
                        "role":        rec.get("role", ""),
                        "full_name":   rec.get("full_name", login),
                        "department":  rec.get("department", ""),
                        "branch_code": rec.get("branch_code", ""),
                    }
    except Exception:
        pass
    return out


def _branch_to_manager_staff_code(branch_code: str) -> Optional[str]:
    """Find the Branch Manager's staff_code for a given branch_code.

    Walks users.json for the staff with role='Branch Manager' and matching
    branch_code. If none found, returns None (caller chooses fallback).
    """
    users = _load_users()
    for sc, info in users.items():
        if (info.get("role") == "Branch Manager" and
                info.get("branch_code") == branch_code):
            return sc
    return None





def _normalise_period(period: str) -> str:
    """Normalise common period spellings to BSC universal contract format.

    Accepts:
        '2026'         -> '2026'
        '2026Q1'       -> '2026-Q1'
        '2026-Q1'      -> '2026-Q1'
        '2026q1'       -> '2026-Q1'
        '2026-01'      -> '2026-01'
        '2026-01-15'   -> '2026-01-15'

    Raises ValueError for anything outside these shapes.
    """
    import re as _re
    if not isinstance(period, str) or not period:
        raise ValueError(f"period must be a non-empty string, got {period!r}")
    p = period.strip().upper().replace(" ", "")
    # YYYYQn -> YYYY-Qn
    m = _re.match(r"^(\d{4})Q([1-4])$", p)
    if m:
        return f"{m.group(1)}-Q{m.group(2)}"
    # YYYY-QN (already canonical) or other accepted formats
    accepted = (
        _re.compile(r"^\d{4}$"),
        _re.compile(r"^\d{4}-Q[1-4]$"),
        _re.compile(r"^\d{4}-(0[1-9]|1[0-2])$"),
        _re.compile(r"^\d{4}-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])$"),
    )
    if any(rx.match(p) for rx in accepted):
        return p
    raise ValueError(
        f"period {period!r} not in accepted format. Use YYYY, YYYY-QN, "
        f"YYYY-MM, YYYY-MM-DD, or YYYYQN (will be normalised)."
    )


def unify_bank_pbt(
    bank_pbt_value: float,
    period: str = DEFAULT_PERIOD,
) -> UniversalBSCRecord:
    """Convert canonical bank PBT (one number) into one universal record.

    The bank PBT is attributed to MD per the cascade structure
    (target_cascade.json::300001|PBT|2026 → 22B).
    """
    period = _normalise_period(period)
    return make_record(
        staff_code=MD_STAFF_CODE,
        kpi_id="PBT",
        value=bank_pbt_value,
        period=period,
        source_module=SRC_BANK_ENGINE,
        metadata={"dimension": "bank", "engine_gate": "G250"},
    )


def unify_sbu_pbt(
    sbu_pbts: Dict[str, Any],
    period: str = DEFAULT_PERIOD,
) -> List[UniversalBSCRecord]:
    """Convert compute_pbt_by_sbu output → universal records (one per SBU head).

    Maps each SBU to its head Chief via SBU_HEAD_STAFF_CODE. PBT value is
    attributed to that Chief in the universal contract.
    """
    period = _normalise_period(period)
    records: List[UniversalBSCRecord] = []
    for sbu_name, pbt_components in sbu_pbts.items():
        head_staff = SBU_HEAD_STAFF_CODE.get(sbu_name, MD_STAFF_CODE)
        records.append(make_record(
            staff_code=head_staff,
            kpi_id="PBT",
            value=float(pbt_components.pbt),
            period=period,
            source_module=SRC_SBU_ENGINE,
            metadata={
                "dimension": "sbu",
                "sbu":       sbu_name,
                "engine_gate": "G254",
            },
        ))
    return records


def unify_branch_pbt(
    branch_pbts: Dict[str, Any],
    period: str = DEFAULT_PERIOD,
) -> List[UniversalBSCRecord]:
    """Convert compute_pbt_by_branch output → universal records.

    Maps each branch_code to its Branch Manager via users.json lookup.
    If a branch has no manager configured, falls back to MD (with note in
    metadata) — surfaced as data-quality issue.
    """
    period = _normalise_period(period)
    records: List[UniversalBSCRecord] = []
    for branch_code, pbt_components in branch_pbts.items():
        bm_staff = _branch_to_manager_staff_code(branch_code)
        fallback_used = False
        if bm_staff is None:
            bm_staff = MD_STAFF_CODE
            fallback_used = True
        records.append(make_record(
            staff_code=bm_staff,
            kpi_id="PBT",
            value=float(pbt_components.pbt),
            period=period,
            source_module=SRC_BRANCH_ENGINE,
            metadata={
                "dimension":     "branch",
                "branch_code":   branch_code,
                "fallback_used": fallback_used,
                "engine_gate":   "G255",
            },
        ))
    return records


def unify_staff_pbt(
    staff_pbts: Dict[str, Any],
    period: str = DEFAULT_PERIOD,
) -> List[UniversalBSCRecord]:
    """Convert compute_pbt_by_staff output → universal records.

    Each tagged staff produces one record. The role taxonomy
    (v10.374) classification is included in metadata so consumers can
    distinguish portfolio_owner vs proposition vs structural vs service vs
    support records.
    """
    period = _normalise_period(period)
    try:
        from utils.role_taxonomy import classify_role
        taxonomy_available = True
    except Exception:
        taxonomy_available = False

    users = _load_users()
    records: List[UniversalBSCRecord] = []

    for staff_code, pbt_components in staff_pbts.items():
        # Skip the UNASSIGNED_STAFF_BUCKET — it isn't a staff record
        # (it's a data-quality marker). Caller can include separately if needed.
        if staff_code == "Unassigned":
            continue
        info = users.get(staff_code, {})
        role = info.get("role", "Unknown")
        tier = "unknown"
        sbu = "unknown"
        if taxonomy_available and role:
            try:
                c = classify_role(role)
                tier = c.tier
                sbu = c.sbu
            except Exception:
                pass
        records.append(make_record(
            staff_code=staff_code,
            kpi_id="PBT",
            value=float(pbt_components.pbt),
            period=period,
            source_module=SRC_STAFF_ENGINE,
            metadata={
                "dimension":          "staff",
                "role":               role,
                "profitability_tier": tier,
                "sbu":                sbu,
                "department":         info.get("department", ""),
                "branch_code":        info.get("branch_code", ""),
                "engine_gate":        "G257",
            },
        ))
    return records


def unify_all_kpi_flow(
    cbs_dir: Optional[Path] = None,
    period: str = DEFAULT_PERIOD,
) -> Dict[str, Any]:
    """The headline function: run all canonical PBT engines against the
    virtual bank and produce universal records for every dimension.

    Returns:
      {
        'bank_record':    UniversalBSCRecord,
        'sbu_records':    List[UniversalBSCRecord],
        'branch_records': List[UniversalBSCRecord],
        'staff_records':  List[UniversalBSCRecord],
        'all_records':    List[UniversalBSCRecord],
        'summary':        records_summary output,
        'validation':     validate_batch output,
        'reconciliation': dict showing Σ at each dimension = bank PBT,
      }

    If cbs_dir is None, seeds a virtual bank deterministically.
    Caller can pass a live CBS dir for production runs.
    """
    period = _normalise_period(period)
    from utils.virtual_bank_seed import seed_virtual_bank, SeedConfig
    from utils.virtual_bank_cbs_writer import persist_bank_to_cbs
    from utils.pbt_computation import (
        compute_pbt_from_cbs, compute_pbt_by_sbu,
    )
    from utils.branch_pbt_allocator import compute_pbt_by_branch
    from utils.customer_pbt_allocator import compute_pbt_by_staff

    # Set up CBS context
    if cbs_dir is None:
        bank, _ = seed_virtual_bank(config=SeedConfig.small())
        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            persist_bank_to_cbs(bank, output_dir=td_path)
            return _run_unification(td_path, period)
    else:
        return _run_unification(cbs_dir, period)


def _run_unification(cbs_dir: Path, period: str) -> Dict[str, Any]:
    """Internal helper — runs all engines against an existing CBS dir."""
    from utils.pbt_computation import (
        compute_pbt_from_cbs, compute_pbt_by_sbu,
    )
    from utils.branch_pbt_allocator import compute_pbt_by_branch
    from utils.customer_pbt_allocator import compute_pbt_by_staff

    # Run canonical engines
    bank_pbt = compute_pbt_from_cbs(cbs_dir)
    sbu_pbts = compute_pbt_by_sbu(cbs_dir)
    branch_pbts = compute_pbt_by_branch(cbs_dir)
    staff_pbts = compute_pbt_by_staff(cbs_dir)

    # Convert to universal records
    bank_record = unify_bank_pbt(float(bank_pbt.pbt), period=period)
    sbu_records = unify_sbu_pbt(sbu_pbts, period=period)
    branch_records = unify_branch_pbt(branch_pbts, period=period)
    staff_records = unify_staff_pbt(staff_pbts, period=period)

    all_records = [bank_record] + sbu_records + branch_records + staff_records

    # Validate the entire batch (Section 5.4: silent failures prohibited)
    validation = validate_batch(all_records)
    summary = records_summary(all_records)

    # Reconciliation — confirm each dimension's records sum to bank PBT
    bank_pbt_value = float(bank_pbt.pbt)
    reconciliation = {
        "bank_pbt":         bank_pbt_value,
        "sbu_sum":          sum(r.value for r in sbu_records),
        "branch_sum":       sum(r.value for r in branch_records),
        "staff_sum":        sum(r.value for r in staff_records),
        "tolerances_kes": {
            "sbu":    abs(bank_pbt_value - sum(r.value for r in sbu_records)),
            "branch": abs(bank_pbt_value - sum(r.value for r in branch_records)),
            "staff":  abs(bank_pbt_value - sum(r.value for r in staff_records)),
        },
        "all_within_kes_100": all(
            abs(bank_pbt_value - s) <= 100
            for s in (
                sum(r.value for r in sbu_records),
                sum(r.value for r in branch_records),
                sum(r.value for r in staff_records),
            )
        ),
    }

    return {
        "bank_record":     bank_record,
        "sbu_records":     sbu_records,
        "branch_records":  branch_records,
        "staff_records":   staff_records,
        "all_records":     all_records,
        "summary":         summary,
        "validation":      {k: v for k, v in validation.items() if k != "valid_records"},
        "reconciliation":  reconciliation,
    }


def self_test() -> None:
    """v10.377 self_test — end-to-end against seeded virtual bank."""
    tests = 0

    # Test 1: unify_bank_pbt produces one valid record
    r = unify_bank_pbt(bank_pbt_value=-7_900_000_000.0, period="2026")
    assert r.kpi_id == "PBT"
    assert r.staff_code == MD_STAFF_CODE
    assert r.value == -7_900_000_000.0
    assert r.source_module == SRC_BANK_ENGINE
    assert r.metadata["dimension"] == "bank"
    tests += 1

    # Test 2: SBU head mapping covers known SBUs
    for sbu in ("Retail Banking", "Commercial Banking", "Corporate Banking"):
        assert sbu in SBU_HEAD_STAFF_CODE, f"missing mapping for {sbu}"
    tests += 1

    # Test 3: end-to-end against seeded bank
    result = unify_all_kpi_flow(cbs_dir=None, period="2026")
    assert "bank_record" in result
    assert isinstance(result["bank_record"], UniversalBSCRecord)
    assert len(result["sbu_records"]) > 0
    assert len(result["branch_records"]) > 0
    assert len(result["staff_records"]) > 0
    tests += 1

    # Test 4: all records validate
    validation = result["validation"]
    assert validation["violations"] == 0, (
        f"contract violations: {validation.get('violation_detail', [])}"
    )
    tests += 1

    # Test 5: reconciliation passes (Σ each dim = Bank PBT within KES 100)
    recon = result["reconciliation"]
    assert recon["all_within_kes_100"], (
        f"reconciliation failed: {recon['tolerances_kes']}"
    )
    tests += 1

    # Test 6: every staff record has profitability_tier metadata (v10.374 axis)
    for sr in result["staff_records"]:
        assert "profitability_tier" in sr.metadata, (
            f"staff record missing tier: {sr.staff_code}"
        )
    tests += 1

    # Test 7: source_module follows naming convention for every record
    for r in result["all_records"]:
        assert r.source_module.startswith("canonical_pbt_"), (
            f"bad source_module: {r.source_module}"
        )
        assert r.source_module.endswith("_v10377")
    tests += 1

    # Test 8: every record has its engine_gate documented in metadata
    for r in result["all_records"]:
        assert "engine_gate" in r.metadata, (
            f"missing engine_gate on {r.staff_code}/{r.kpi_id}"
        )
        assert r.metadata["engine_gate"] in ("G250", "G254", "G255", "G257")
    tests += 1

    print(f"✓ virtual_bank_kpi_unifier self_test passed ({tests} tests)")
    print(f"  Bank PBT: KES {result['bank_record'].value/1e9:,.2f}B")
    print(f"  SBU records: {len(result['sbu_records'])} (Σ tolerance KES "
          f"{result['reconciliation']['tolerances_kes']['sbu']:.0f})")
    print(f"  Branch records: {len(result['branch_records'])} (Σ tolerance KES "
          f"{result['reconciliation']['tolerances_kes']['branch']:.0f})")
    print(f"  Staff records: {len(result['staff_records'])} (Σ tolerance KES "
          f"{result['reconciliation']['tolerances_kes']['staff']:.0f})")
    print(f"  Total universal records: {len(result['all_records'])}")


if __name__ == "__main__":
    # Allow standalone execution: add repo root to sys.path
    import sys
    _repo = Path(__file__).resolve().parent.parent
    if str(_repo) not in sys.path:
        sys.path.insert(0, str(_repo))
    self_test()
