"""tests/test_cascade_library_reconciliation.py — v10.107.

Locks in the v10.107 cascade↔library reconciliation. Every KPI name
referenced in `data/target_cascade.json` must resolve to a library
entry (via id, code, name, or alias). Without this gate, the autofit
pipeline would silently drop actuals for un-resolvable cascade KPIs.

Pre-v10.107 baseline: 18 of 21 cascade names had no library entry.
Post-v10.107: all 21 resolve.

Going forward: any new KPI added to the cascade MUST have a corresponding
library entry. New cascade KPIs without library entries fail this test.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


@pytest.fixture(scope="module")
def cascade_kpi_names():
    """Collect every distinct KPI name referenced by target_cascade.json."""
    cascade_path = REPO_ROOT / "data" / "target_cascade.json"
    with open(cascade_path, encoding="utf-8") as f:
        cascade = json.load(f)
    names = set()
    for entry in cascade.values():
        if isinstance(entry, dict) and "kpi" in entry:
            names.add(entry["kpi"])
    return sorted(names)


@pytest.fixture(scope="module")
def library_lookup():
    """Build the same lookup index that bsc_engine._load_kpi_index does:
    keyed by id, code, name, and aliases."""
    lib_path = REPO_ROOT / "data" / "kpi_library.json"
    with open(lib_path, encoding="utf-8") as f:
        lib = json.load(f)
    idx = {}
    for kpi in lib.get("kpis", []) or []:
        for key_field in ("id", "code", "name"):
            key = kpi.get(key_field)
            if key and str(key) not in idx:
                idx[str(key)] = kpi
        for alias in kpi.get("aliases", []) or []:
            if str(alias) not in idx:
                idx[str(alias)] = kpi
    return idx


def test_cascade_has_at_least_v10_107_floor(cascade_kpi_names):
    """The cascade should reference at least the v10.107 baseline of
    21 distinct KPIs. If this drops, something was deleted from the
    cascade that shouldn't have been."""
    assert len(cascade_kpi_names) >= 21, (
        f"Cascade now references only {len(cascade_kpi_names)} KPIs; "
        f"v10.107 baseline was 21. If KPIs were intentionally removed, "
        f"update this floor."
    )


def test_every_cascade_kpi_resolves_to_library(
        cascade_kpi_names, library_lookup):
    """The contract: every cascade KPI name must be resolvable via the
    library's id/code/name/aliases lookup. A failure here means the
    autofit pipeline can't route actuals for that KPI back to the BSC
    scorecard — staff allocations would silently disappear."""
    unresolved = [n for n in cascade_kpi_names if n not in library_lookup]
    assert not unresolved, (
        f"{len(unresolved)} cascade KPI(s) don't resolve to library "
        f"entries. The autofit pipeline cannot route actuals for these "
        f"KPIs. Either add them to data/kpi_library.json with id/code/"
        f"name matching, OR add as aliases on existing entries.\n"
        f"Unresolved: {unresolved}"
    )


def test_library_entries_for_v10_107_additions_are_well_formed():
    """The 18 KPI entries added in v10.107 must have all mandatory
    fields the BSC pipeline depends on."""
    REQUIRED_FIELDS = (
        "id", "name", "pillar", "weight", "unit", "direction",
        "active", "description", "source",
    )
    V10_107_ADDITIONS = {
        "Account Dormancy", "Audit Score", "CASA Ratio", "CX Score",
        "Channel Dormancy", "Collection Throughput",
        "Commercial Deposit Growth", "Disbursements Corporate Loans",
        "Disbursements MSME Loans", "Disbursements Retail Loans",
        "Loan Book Growth", "Number of Business Borrowers", "PAR",
        "PBT", "Retail & MSME Deposit Growth", "Staff Productivity",
        "Top 100 Customers Deposit", "Total NFI",
    }
    lib_path = REPO_ROOT / "data" / "kpi_library.json"
    with open(lib_path, encoding="utf-8") as f:
        lib = json.load(f)
    by_id = {k.get("id"): k for k in lib.get("kpis", [])}

    missing = []
    malformed = []
    valid_pillars = {p["id"] for p in lib.get("pillars", [])}

    for cascade_name in V10_107_ADDITIONS:
        entry = by_id.get(cascade_name)
        if entry is None:
            missing.append(cascade_name)
            continue
        for field in REQUIRED_FIELDS:
            if field not in entry:
                malformed.append(f"{cascade_name}: missing '{field}'")
        if entry.get("pillar") not in valid_pillars:
            malformed.append(
                f"{cascade_name}: pillar '{entry.get('pillar')}' "
                f"not in valid_pillars {valid_pillars}")
        if entry.get("direction") not in ("higher", "lower"):
            malformed.append(
                f"{cascade_name}: direction '{entry.get('direction')}' "
                f"not in (higher, lower)")
        weight = entry.get("weight")
        if not isinstance(weight, (int, float)) or weight <= 0 or weight > 1:
            malformed.append(
                f"{cascade_name}: weight {weight} not in (0, 1]")

    assert not missing, (
        f"v10.107 additions missing from library: {missing}")
    assert not malformed, (
        f"v10.107 additions malformed:\n  " + "\n  ".join(malformed))


def test_aliases_resolve_correctly(library_lookup):
    """The 3 alias entries added in v10.107 must resolve to the
    correct library KPIs."""
    EXPECTED_ALIASES = {
        "NPL Ratio": "K004",
        "New Accounts": "K006",
        "Compliance Score": "K014",
    }
    for alias, expected_id in EXPECTED_ALIASES.items():
        entry = library_lookup.get(alias)
        assert entry is not None, (
            f"Alias '{alias}' does not resolve to any library entry")
        assert entry.get("id") == expected_id, (
            f"Alias '{alias}' resolves to {entry.get('id')}, "
            f"expected {expected_id}")


def test_library_kpi_count_floor():
    """Library must have ≥129 KPIs (111 pre-v10.107 + 18 added)."""
    lib_path = REPO_ROOT / "data" / "kpi_library.json"
    with open(lib_path, encoding="utf-8") as f:
        lib = json.load(f)
    n = len(lib.get("kpis", []))
    assert n >= 129, (
        f"Library has only {n} KPIs; v10.107 floor is 129. "
        f"If removals were intentional, update this floor.")
