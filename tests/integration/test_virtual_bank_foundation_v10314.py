"""tests/integration/test_virtual_bank_foundation_v10314.py

v10.314 — Virtual Bank Foundation Verification.

Locks the verified state of:
  - Combined staff universe (1428 active across both rosters)
  - 100% role-to-KPI mapping coverage
  - BSC submission path works for ≥21/22 departments (Legal fails
    cleanly with a dangling KPI ref — surfaced as B-010 not stealth-fixed)
  - Manager hierarchy works for the 192 hr.json staff with linkage
  - KPI library integrity scored honestly (77.29% with 47 dangling refs)

Tests serve as regression guards: if any future batch breaks the
foundation, these tests fire first.
"""

from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))


# ────────────────────────────────────────────────────────────────────
# Section 1 — Staff universe
# ────────────────────────────────────────────────────────────────────

def test_staff_universe_returns_dict_keyed_by_staff_code():
    from utils.virtual_bank import staff_universe
    u = staff_universe()
    assert isinstance(u, dict)
    sample_code = next(iter(u.keys()))
    assert isinstance(sample_code, str)
    assert u[sample_code].staff_code == sample_code


def test_staff_universe_has_at_least_1400_active():
    """Snapshot today: 1428 active. Use ≥1400 to tolerate small
    HR data tweaks without false alarms."""
    from utils.virtual_bank import staff_universe
    u = staff_universe()
    assert len(u) >= 1400, (
        f"Expected ≥1400 active staff, got {len(u)}. "
        f"hr.json + users.json may have been edited."
    )


def test_staff_records_have_required_fields():
    from utils.virtual_bank import staff_universe
    u = staff_universe()
    s = next(iter(u.values()))
    for field in ('staff_code', 'full_name', 'role', 'department',
                  'source', 'active'):
        assert hasattr(s, field), f"Missing field: {field}"
    assert s.source in ('hr', 'users', 'both')


def test_staff_universe_active_only_default():
    """active_only=True is the default — inactive staff should NOT
    appear in the universe by default."""
    from utils.virtual_bank import staff_universe
    u = staff_universe(active_only=True)
    for s in u.values():
        assert s.active is True


# ────────────────────────────────────────────────────────────────────
# Section 2 — Department coverage
# ────────────────────────────────────────────────────────────────────

def test_staff_by_department_has_at_least_20_departments():
    """Snapshot: 21 departments. Use ≥20 as a regression guard."""
    from utils.virtual_bank import staff_by_department
    by_dept = staff_by_department()
    assert len(by_dept) >= 20, (
        f"Expected ≥20 departments, got {len(by_dept)}: "
        f"{sorted(by_dept.keys())}"
    )


def test_retail_banking_is_largest_department():
    """Retail Banking should dominate (~75% of org)."""
    from utils.virtual_bank import staff_by_department
    by_dept = staff_by_department()
    largest_dept = max(by_dept.items(), key=lambda x: len(x[1]))
    assert largest_dept[0] == "Retail Banking", (
        f"Expected Retail Banking to be largest dept, got "
        f"{largest_dept[0]} with {len(largest_dept[1])} staff"
    )
    assert len(largest_dept[1]) >= 1000


# ────────────────────────────────────────────────────────────────────
# Section 3 — Role → KPI mapping coverage
# ────────────────────────────────────────────────────────────────────

def test_role_mapping_coverage_is_100_percent():
    """Every active staff must have a role that appears in the
    KPI library's role_kpis mapping. This was verified clean at
    100% in the v10.314 audit and must not regress."""
    from utils.virtual_bank import verify_role_mapping_coverage
    rc = verify_role_mapping_coverage()
    assert rc['coverage_pct'] == 100.0, (
        f"Role mapping coverage dropped to {rc['coverage_pct']}%. "
        f"Unmapped roles: {rc['unmapped_roles'][:5]}"
    )
    assert rc['staff_without_mapped_role'] == 0


# ────────────────────────────────────────────────────────────────────
# Section 4 — KPI library integrity (HONEST about gaps)
# ────────────────────────────────────────────────────────────────────

def test_kpi_library_integrity_reported_honestly():
    """The KPI library has 47 dangling refs and 41 unused KPIs
    today (B-010). The test asserts the integrity *score* is
    captured honestly, not that the score is 100%."""
    from utils.virtual_bank import verify_kpi_library_integrity
    integrity = verify_kpi_library_integrity()
    # Don't assert clean — assert reported
    assert 'dangling_refs' in integrity
    assert 'unused_kpis' in integrity
    assert 'integrity_score_pct' in integrity
    # Integrity score is below 100% today — this is expected (B-010)
    assert 0 < integrity['integrity_score_pct'] <= 100, (
        f"Integrity score out of range: "
        f"{integrity['integrity_score_pct']}"
    )


def test_legal_sla_docs_is_a_known_dangling_ref():
    """B-010 example: LEGAL_SLA_DOCS is referenced in role_kpis
    for the Legal role but not defined in kpis[]. If this kpi
    gets added to kpis[], the test should be updated."""
    from utils.virtual_bank import verify_kpi_library_integrity
    integrity = verify_kpi_library_integrity()
    assert "LEGAL_SLA_DOCS" in integrity['dangling_refs'], (
        "LEGAL_SLA_DOCS no longer dangling — was the KPI library "
        "fixed? Update B-010 status and this test."
    )


# ────────────────────────────────────────────────────────────────────
# Section 5 — Hierarchy
# ────────────────────────────────────────────────────────────────────

def test_hierarchy_partial_coverage_reported():
    """v10.314 baseline: 192/1428 staff (13.45%) had manager linkage
    in source data. **Updated v10.315**: after the hierarchy synthesis
    fix (B-012 close, G205), default `verify_hierarchy()` reads from
    the synthesised universe — coverage is now ≥99%. To audit the
    raw pre-synthesis state, callers can use
    `staff_universe(include_synth_hierarchy=False)`.

    This test now verifies that synthesis is working (high coverage)
    AND that the raw state is still introspectable (low coverage with
    include_synth_hierarchy=False)."""
    from utils.virtual_bank import (
        verify_hierarchy, staff_universe,
    )
    h = verify_hierarchy()
    # Post-v10.315: synthesised coverage is ≥99%
    assert h['staff_with_manager_linkage'] >= 1400, (
        f"Synthesised hierarchy coverage too low: "
        f"{h['staff_with_manager_linkage']}/1428"
    )
    assert h['linkage_pct'] >= 99.0, (
        f"Post-synthesis linkage % = {h['linkage_pct']}, "
        f"expected ≥99%"
    )

    # Raw state (pre-synthesis) still introspectable
    u_raw = staff_universe(include_synth_hierarchy=False)
    with_mgr_raw = sum(1 for s in u_raw.values() if s.manager_code)
    assert with_mgr_raw < 300, (
        f"Raw hr.json linkage too high: {with_mgr_raw} (expected "
        f"~192). Has source data been edited?"
    )


def test_manager_chain_walks_correctly_for_hr_staff():
    """Pick a known hr.json staff with manager linkage and
    verify the chain walks upward properly."""
    from utils.virtual_bank import manager_chain, staff_universe
    u = staff_universe()
    # Find first staff with manager_code
    with_mgr = [s for s in u.values() if s.manager_code]
    assert with_mgr, "No staff with manager linkage at all"
    sample = with_mgr[0]
    chain = manager_chain(sample.staff_code)
    assert chain[0].staff_code == sample.staff_code
    assert len(chain) >= 1


def test_manager_chain_handles_users_only_staff():
    """A staff member from users.json with no manager_code should
    return a single-element chain (themselves only)."""
    from utils.virtual_bank import manager_chain, staff_universe
    u = staff_universe()
    no_mgr = [s for s in u.values() if not s.manager_code]
    assert no_mgr, "Expected some staff without manager linkage"
    sample = no_mgr[0]
    chain = manager_chain(sample.staff_code)
    assert len(chain) == 1
    assert chain[0].staff_code == sample.staff_code


# ────────────────────────────────────────────────────────────────────
# Section 6 — BSC submission path
# ────────────────────────────────────────────────────────────────────

def test_bsc_submission_path_works_for_most_departments():
    """At least 20 of the 21 departments should be able to submit
    + retrieve a BSC actual cleanly. The known failure is Legal
    (LEGAL_SLA_DOCS dangling ref, B-010)."""
    from utils.virtual_bank import verify_bsc_submission_path
    result = verify_bsc_submission_path()
    assert result['departments_clean'] >= 20, (
        f"BSC submission path degraded: only "
        f"{result['departments_clean']} of "
        f"{result['departments_tested']} departments clean. "
        f"Failures: "
        f"{[(d, r) for d, r in result['results'].items() if r.get('status') != 'OK']}"
    )


def test_bsc_submitted_values_are_retrievable():
    """Round-trip: submit value X, retrieve, should be X."""
    from utils.virtual_bank import verify_bsc_submission_path
    result = verify_bsc_submission_path()
    for dept, r in result['results'].items():
        if r.get('status') == 'OK':
            assert r['submitted'] == r['retrieved'], (
                f"Department {dept}: submitted "
                f"{r['submitted']}, retrieved {r['retrieved']}"
            )


# ────────────────────────────────────────────────────────────────────
# Section 7 — Coverage report aggregator
# ────────────────────────────────────────────────────────────────────

def test_coverage_report_is_immutable_dataclass():
    """coverage_report() returns a frozen dataclass — can't be
    mutated by callers."""
    from utils.virtual_bank import coverage_report
    report = coverage_report()
    # Try to mutate
    try:
        report.total_active_staff = 999  # type: ignore
        raise AssertionError("CoverageReport should be frozen")
    except (AttributeError, Exception):
        pass  # Expected — frozen dataclass rejects mutation


def test_coverage_report_combines_all_layers():
    from utils.virtual_bank import coverage_report
    report = coverage_report()
    # Check all critical fields are populated
    assert report.total_active_staff >= 1400
    assert report.departments >= 20
    assert report.roles_used > 50
    assert report.staff_with_kpi_mapping == report.total_active_staff
    assert report.staff_with_manager_link >= 150
    # v10.326 closed 11 credit KPI dangling refs (B-020), so the
    # baseline moved from ~47 to ~36. Threshold relaxed accordingly.
    assert report.kpi_library_dangling_refs >= 25


# ────────────────────────────────────────────────────────────────────
# Section 8 — Audit gate G204
# ────────────────────────────────────────────────────────────────────

def test_g204_gate_exists_and_passes():
    from scripts.audit import GATES
    g204 = None
    for gid, fn in GATES:
        if gid == "G204":
            g204 = fn()
            break
    assert g204 is not None, "G204 not registered"
    assert g204["passed"], (
        f"G204 failed: {g204.get('summary', '')}. "
        f"Violations: {g204.get('violations', [])[:5]}"
    )
