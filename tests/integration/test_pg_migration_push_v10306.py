"""
tests/integration/test_pg_migration_push_v10306.py
================================================================================
v10.306 — PG migration push: 5 new migrators + 5 new DDL tables
for genuinely unmigrated JSON files in the platform.

Today's state (G163 baseline at v10.305):
    ddl_tables = 32
    migrators  = 18

After v10.306:
    ddl_tables = 37 (+5)
    migrators  = 23 (+5)

The 5 new tables cover genuinely unmigrated files surfaced by
inventory of FLAT_MIGRATIONS + explicit migrate_X() functions:

    1. audit_reviews             (#201-#210 audit module)
    2. compliance_regulatory_returns (Compliance cockpit's
                                       compliance.json file —
                                       odd name kept for legacy)
    3. incidents                 (IT incidents register)
    4. nps_responses             (customer NPS survey data)
    5. rcsa_register             (Risk RCSA register)

Scope honesty: this is a real inventory pass, not a sprint.
Many tables that conversation history suggested were unmigrated
(loan_applications, compliance_cases, aml_alerts,
sanctions_register) are actually ALREADY MIGRATED via the
FLAT_MIGRATIONS declarative table. The 48/79 framing was
imprecise.

Pattern follows v10.260+: each migrate_<name>() reads the JSON
file, truncates the table, inserts rows. Schema mirrors the
JSON keys, with unknown fields parked in a `payload JSONB`
column for forward compatibility.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))


EXPECTED_NEW_TABLES = [
    "audit_reviews",
    "compliance_regulatory_returns",
    "incidents",
    "nps_responses",
    "rcsa_register",
]


# ============================================================
# Section 1 — DDL file exists
# ============================================================

def test_v10306_ddl_file_exists():
    """A new SQL file must ship with the 5 CREATE TABLE
    statements. The audit script scans all *.sql files at
    repo root so the filename pattern matters less than the
    content."""
    sql_files = list(REPO_ROOT.glob("create_tables_v10.306*.sql"))
    assert len(sql_files) >= 1, (
        f"No create_tables_v10.306*.sql file found. "
        f"Got: {[p.name for p in REPO_ROOT.glob('*.sql')]}"
    )


def test_v10306_ddl_has_five_create_table_statements():
    """The new SQL file must contain exactly 5 CREATE TABLE
    statements — one per new table."""
    sql_files = list(REPO_ROOT.glob("create_tables_v10.306*.sql"))
    if not sql_files:
        pytest.skip("DDL file not yet present")
    content = sql_files[0].read_text()
    create_count = len(re.findall(
        r"^CREATE\s+TABLE\b",
        content, re.IGNORECASE | re.MULTILINE,
    ))
    assert create_count == 5, (
        f"Expected 5 CREATE TABLE statements, found "
        f"{create_count} in {sql_files[0].name}"
    )


def test_v10306_ddl_references_each_expected_table():
    """Each of the 5 expected tables must appear in the DDL."""
    sql_files = list(REPO_ROOT.glob("create_tables_v10.306*.sql"))
    if not sql_files:
        pytest.skip("DDL file not yet present")
    content = sql_files[0].read_text().lower()
    for table in EXPECTED_NEW_TABLES:
        assert table in content, (
            f"Table `{table}` not referenced in DDL file "
            f"{sql_files[0].name}"
        )


# ============================================================
# Section 2 — Migrators defined
# ============================================================

def test_each_migrate_function_exists():
    """One migrate_<name>() function per new table, in
    scripts/migrate_to_postgres.py."""
    src = (REPO_ROOT / "scripts/migrate_to_postgres.py").read_text()
    for table in EXPECTED_NEW_TABLES:
        pattern = rf"^def\s+migrate_{table}\s*\("
        assert re.search(pattern, src, re.MULTILINE), (
            f"def migrate_{table}() not found in "
            f"scripts/migrate_to_postgres.py"
        )


def test_migrate_function_signatures_have_no_required_args():
    """The audit script calls each migrate function with no
    args; signatures must accept that. Default params allowed."""
    src = (REPO_ROOT / "scripts/migrate_to_postgres.py").read_text()
    for table in EXPECTED_NEW_TABLES:
        # Match `def migrate_<name>(<args>)` — args may be empty
        match = re.search(
            rf"^def\s+migrate_{table}\s*\(([^)]*)\)",
            src, re.MULTILINE,
        )
        assert match, f"Could not parse migrate_{table} signature"
        args_str = match.group(1).strip()
        # Allow no args or kwargs with defaults
        if args_str:
            for arg in args_str.split(","):
                if "=" not in arg and arg.strip() != "":
                    pytest.fail(
                        f"migrate_{table} has required arg "
                        f"`{arg.strip()}` — audit script calls "
                        f"with no args"
                    )


def test_each_migrate_reads_correct_source_file():
    """Each migrator must reference its source JSON file by
    name. Quick textual check — the migrator's docstring or
    body should mention the source file."""
    src = (REPO_ROOT / "scripts/migrate_to_postgres.py").read_text()
    source_map = {
        "audit_reviews": "audit_reviews.json",
        "compliance_regulatory_returns": "compliance.json",
        "incidents": "incidents.json",
        "nps_responses": "nps.json",
        "rcsa_register": "rcsa_register.json",
    }
    for table, json_file in source_map.items():
        # Find migrator block
        match = re.search(
            rf"^def\s+migrate_{table}\s*\([^)]*\):"
            rf"(.*?)(?=^def\s|\Z)",
            src, re.MULTILINE | re.DOTALL,
        )
        assert match, f"Could not isolate migrate_{table}"
        body = match.group(1)
        assert json_file in body, (
            f"migrate_{table} doesn't reference {json_file} — "
            f"check the DATA / path"
        )


# ============================================================
# Section 3 — G163 ratchet bumped
# ============================================================

def test_g163_baseline_bumped_to_v10306_counts():
    """G163 is INVERSE — counts may only increase. Confirm
    baseline is at or above the v10.306 expected counts."""
    import json
    baselines = json.loads(
        (REPO_ROOT / "data/audit_baselines.json").read_text()
    )
    g163 = baselines.get("g163_pg_migration_progress")
    assert g163 is not None, "G163 baseline missing"
    assert g163["ddl_tables"] >= 37, (
        f"G163 ddl_tables baseline {g163['ddl_tables']} < "
        f"37 (5 new tables in v10.306)"
    )
    assert g163["migrators"] >= 23, (
        f"G163 migrators baseline {g163['migrators']} < 23 "
        f"(5 new migrators in v10.306)"
    )


def test_g163_gate_currently_passes():
    """Running the gate itself must pass after the bump."""
    from scripts.audit import GATES
    g163 = None
    for gid, fn in GATES:
        if gid == "G163":
            g163 = fn()
            break
    assert g163 is not None, "G163 not registered"
    assert g163["passed"], (
        f"G163 failed. Summary: {g163.get('summary', '')}. "
        f"Violations: {g163.get('violations', [])[:5]}"
    )


# ============================================================
# Section 4 — G15 dual-write registry not regressed
# ============================================================

def test_g15_still_passes():
    """G15 checks that dual-write registry (if any) is well-
    formed. Adding migrators must not break it."""
    from scripts.audit import GATES
    g15 = None
    for gid, fn in GATES:
        if gid == "G15":
            g15 = fn()
            break
    assert g15 is not None, "G15 not registered"
    assert g15["passed"], (
        f"G15 regressed in v10.306. Summary: "
        f"{g15.get('summary', '')}"
    )


# ============================================================
# Section 5 — Audit overall PASS
# ============================================================

def test_overall_audit_still_passes_after_v10306():
    """Sanity: the full audit must remain at 100% after this
    batch's changes."""
    from scripts.audit import GATES
    fails = []
    for gid, fn in GATES:
        try:
            r = fn()
            if not r.get("passed"):
                fails.append(f"{gid}: {r.get('summary', '')}")
        except Exception as exc:
            fails.append(f"{gid}: gate raised {exc}")
    assert not fails, (
        f"v10.306 audit regressions: " + " | ".join(fails[:5])
    )
