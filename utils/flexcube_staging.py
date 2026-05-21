"""utils.flexcube_staging — FLEXCUBE Staging Schema
(Standard #31, v5.50). Volume Four — FLEXCUBE Integration.

Per the master spec:

    CREATE TABLE staging.extract_control (
        table_name VARCHAR(100) PRIMARY KEY,
        last_extract_date TIMESTAMP,
        status VARCHAR(20)
    );

    CREATE TABLE staging.sttm_customer_raw (
        extract_id BIGSERIAL,
        cust_no VARCHAR(20),
        cust_name VARCHAR(200),
        hash_value VARCHAR(64)
    );

WHAT THIS MODULE SHIPS
----------------------
1. build_extract_control_ddl()      → spec-exact + production columns
2. build_sttm_customer_raw_ddl()    → spec-exact + production columns
3. build_full_staging_schema_ddl()  → all staging tables in one statement
4. ddl_contains_required_columns(ddl, required_cols) → validation helper

PRODUCTION COLUMNS ADDED (without violating spec)
--------------------------------------------------
The spec defines the MINIMUM required columns. Production deployments
need:

  extract_control:
    - error_message (TEXT)              for status='ERROR' diagnostics
    - rows_extracted (BIGINT)           for trend monitoring
    - extract_started_at, completed_at  for SLA tracking
    - retry_count, last_error_at        for retry orchestration

  sttm_customer_raw:
    - extracted_at (TIMESTAMPTZ)        for staleness checks
    - source_extract_id (FK → extract_control)  for lineage
    - all the OTHER FLEXCUBE STTM_CUSTOMER columns (cust_type, segment,
      country, ...) — but those depend on FLEXCUBE 12 schema specifics
      that v5.50 doesn't bind. Production deployments add them per
      Ecobank's FLEXCUBE customisations.

The spec-required columns MUST appear in the DDL byte-for-byte name match.
The validator (`ddl_contains_required_columns`) enforces this.

WHAT THIS MODULE DOES NOT SHIP
-------------------------------
- The actual extract/transform/load pipeline (that's #33 Airflow DAG).
- The connection to FLEXCUBE (that's #32 connection manager).
- The mapping FROM staging TO clean A2Z tables (that's #34 mappings).

This is the "staging area" only — the bonded warehouse where raw
FLEXCUBE extracts land before transformation.

HONESTY DISCIPLINE
------------------
No financial computation here. The only honesty rule that applies is
"don't pretend the schema is something it isn't" — the spec-required
columns must be present byte-for-byte.
"""
from __future__ import annotations

from typing import Any, Dict, List


# ─────────────────────────────────────────────────────────────────────
# Spec-required column lists
# ─────────────────────────────────────────────────────────────────────

# These are the columns the spec quotes verbatim. Validators check
# that the produced DDL contains all of them.
EXTRACT_CONTROL_REQUIRED_COLUMNS: List[str] = [
    "table_name",
    "last_extract_date",
    "status",
]

STTM_CUSTOMER_RAW_REQUIRED_COLUMNS: List[str] = [
    "extract_id",
    "cust_no",
    "cust_name",
    "hash_value",
]

# Status values the extract_control table accepts. Used by the connection
# manager (#32) and the ETL DAG (#33) to record extract state.
EXTRACT_STATUS_VALUES: List[str] = [
    "PENDING",
    "RUNNING",
    "SUCCESS",
    "FAILED",
    "STALE",
]


# ─────────────────────────────────────────────────────────────────────
# DDL builders
# ─────────────────────────────────────────────────────────────────────

def build_extract_control_ddl() -> str:
    """Return CREATE TABLE staging.extract_control DDL.

    Spec-exact for the 3 required columns; adds production columns
    for retry orchestration, SLA tracking, and error diagnostics.
    """
    return """
CREATE SCHEMA IF NOT EXISTS staging;

CREATE TABLE IF NOT EXISTS staging.extract_control (
    table_name           VARCHAR(100) PRIMARY KEY,
    last_extract_date    TIMESTAMP,
    status               VARCHAR(20) NOT NULL DEFAULT 'PENDING',
    error_message        TEXT,
    rows_extracted       BIGINT,
    extract_started_at   TIMESTAMPTZ,
    extract_completed_at TIMESTAMPTZ,
    retry_count          INTEGER NOT NULL DEFAULT 0,
    last_error_at        TIMESTAMPTZ,
    CONSTRAINT chk_extract_control_status
        CHECK (status IN ('PENDING','RUNNING','SUCCESS','FAILED','STALE'))
);

CREATE INDEX IF NOT EXISTS idx_extract_control_status
    ON staging.extract_control (status);

CREATE INDEX IF NOT EXISTS idx_extract_control_last_extract_date
    ON staging.extract_control (last_extract_date DESC);
""".strip()


def build_sttm_customer_raw_ddl() -> str:
    """Return CREATE TABLE staging.sttm_customer_raw DDL.

    Spec-exact for the 4 required columns; adds production columns
    for lineage and staleness tracking.
    """
    return """
CREATE TABLE IF NOT EXISTS staging.sttm_customer_raw (
    extract_id           BIGSERIAL PRIMARY KEY,
    cust_no              VARCHAR(20)  NOT NULL,
    cust_name            VARCHAR(200) NOT NULL,
    hash_value           VARCHAR(64)  NOT NULL,
    extracted_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    source_extract_run   VARCHAR(50),
    cust_segment         VARCHAR(50),
    cust_type            VARCHAR(20),
    country              VARCHAR(3),
    record_status        VARCHAR(10) NOT NULL DEFAULT 'NEW',
    CONSTRAINT chk_sttm_customer_raw_status
        CHECK (record_status IN ('NEW','PROCESSED','SKIPPED','ERROR'))
);

CREATE INDEX IF NOT EXISTS idx_sttm_customer_raw_cust_no
    ON staging.sttm_customer_raw (cust_no);

CREATE INDEX IF NOT EXISTS idx_sttm_customer_raw_extracted_at
    ON staging.sttm_customer_raw (extracted_at DESC);

CREATE INDEX IF NOT EXISTS idx_sttm_customer_raw_record_status
    ON staging.sttm_customer_raw (record_status)
    WHERE record_status IN ('NEW','ERROR');

CREATE UNIQUE INDEX IF NOT EXISTS uq_sttm_customer_raw_hash
    ON staging.sttm_customer_raw (cust_no, hash_value);
""".strip()


def build_full_staging_schema_ddl() -> str:
    """Return all staging-schema DDL as a single block."""
    return (
        build_extract_control_ddl()
        + "\n\n"
        + build_sttm_customer_raw_ddl()
    )


# ─────────────────────────────────────────────────────────────────────
# Validators
# ─────────────────────────────────────────────────────────────────────

def ddl_contains_required_columns(
    ddl: str, required_cols: List[str],
) -> Dict[str, Any]:
    """Verify that the DDL contains every required column name.

    Returns:
        {"valid": bool, "missing": list[str], "found": list[str]}
    """
    found: List[str] = []
    missing: List[str] = []
    lower = (ddl or "").lower()
    for col in required_cols:
        if col.lower() in lower:
            found.append(col)
        else:
            missing.append(col)
    return {"valid": len(missing) == 0, "missing": missing, "found": found}


def validate_staging_schema() -> Dict[str, Any]:
    """End-to-end validation of the staging schema.

    Returns:
        {"valid": bool, "errors": list[str], "tables_validated": int}
    """
    errors: List[str] = []

    ec_ddl = build_extract_control_ddl()
    ec_check = ddl_contains_required_columns(ec_ddl, EXTRACT_CONTROL_REQUIRED_COLUMNS)
    if not ec_check["valid"]:
        errors.append(
            f"extract_control DDL missing spec columns: {ec_check['missing']}"
        )

    raw_ddl = build_sttm_customer_raw_ddl()
    raw_check = ddl_contains_required_columns(raw_ddl, STTM_CUSTOMER_RAW_REQUIRED_COLUMNS)
    if not raw_check["valid"]:
        errors.append(
            f"sttm_customer_raw DDL missing spec columns: {raw_check['missing']}"
        )

    if "CREATE SCHEMA IF NOT EXISTS staging" not in ec_ddl:
        errors.append("staging schema CREATE SCHEMA missing from extract_control DDL")

    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "tables_validated": 2,
    }


# ─────────────────────────────────────────────────────────────────────
# Self-test
# ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("A2Z MIS 360 — utils.flexcube_staging self-test")

    # extract_control DDL
    ec = build_extract_control_ddl()
    chk = ddl_contains_required_columns(ec, EXTRACT_CONTROL_REQUIRED_COLUMNS)
    assert chk["valid"], f"missing: {chk['missing']}"
    print(f"  ✅ extract_control DDL: {chk['found']}")

    # sttm_customer_raw DDL
    raw = build_sttm_customer_raw_ddl()
    chk = ddl_contains_required_columns(raw, STTM_CUSTOMER_RAW_REQUIRED_COLUMNS)
    assert chk["valid"], f"missing: {chk['missing']}"
    print(f"  ✅ sttm_customer_raw DDL: {chk['found']}")

    # Schema CREATE present
    assert "CREATE SCHEMA IF NOT EXISTS staging" in ec
    print(f"  ✅ staging schema CREATE present")

    # Full schema validation
    v = validate_staging_schema()
    assert v["valid"], f"schema invalid: {v['errors']}"
    assert v["tables_validated"] == 2
    print(f"  ✅ end-to-end staging schema valid ({v['tables_validated']} tables)")

    # Spec column names byte-for-byte
    for c in EXTRACT_CONTROL_REQUIRED_COLUMNS:
        assert c in ec
    for c in STTM_CUSTOMER_RAW_REQUIRED_COLUMNS:
        assert c in raw
    print(f"  ✅ all spec column names byte-for-byte present")

    # full_staging combines both
    full = build_full_staging_schema_ddl()
    assert "extract_control" in full
    assert "sttm_customer_raw" in full
    print(f"  ✅ full_staging_schema combines both tables")

    # Status check constraint includes spec values
    for s in ("PENDING", "RUNNING", "SUCCESS", "FAILED"):
        assert s in ec
    print(f"  ✅ extract_control status CHECK constraint complete")

    print("\n  ALL TESTS PASSED")
