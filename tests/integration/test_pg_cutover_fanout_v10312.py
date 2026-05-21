"""
tests/integration/test_pg_cutover_fanout_v10312.py
================================================================================
v10.312 — Fan out the production cutover toggles to the
remaining 4 v10.306-migrated tables.

v10.311 set the first production cutover toggle:
  per_table.compliance_regulatory_returns = "auto"

This batch extends the pattern to the other 4 v10.306 tables:
  per_table.audit_reviews        = "auto"
  per_table.incidents            = "auto"
  per_table.nps_responses        = "auto"
  per_table.rcsa_register        = "auto"

After this batch, all 5 v10.306-migrated tables are in
auto-cutover mode. PG unreachable → JSON fallback silently
(current behavior preserved). Operators populating PG get
PG reads with no further config changes.

Production records expected (from data/ JSON files):
  audit_reviews     → 250 (AUD00001, AUD00002, ...)
  incidents         →  80 (INC00001, INC00002, ...)
  nps_responses     → 150 (NPS00001, NPS00002, ...)
  rcsa_register     →  80 (RSK0001, RSK0002, ...)

Test sections:
  1. Each table set to "auto" in per_table
  2. Each composer returns expected count (production)
  3. Each composer returns expected sample IDs (sanity)
  4. Equivalence: auto mode = json mode in current env
  5. Reversibility: roundtrip per table
  6. G202 audit gate
  7. v10.311's compliance toggle unchanged
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))


@pytest.fixture
def tmp_data_dir():
    d = tempfile.mkdtemp(prefix="pg_cutover_v10312_")
    yield Path(d)
    shutil.rmtree(d, ignore_errors=True)


# Production counts + sample IDs for the 4 new tables.
# Single source of truth — used across multiple tests.
TABLE_EXPECTATIONS = {
    "audit_reviews": {
        "count": 250,
        "sample_ids": ("AUD00001", "AUD00002"),
        "composer": "audit_reviews_records",
        "json_filename": "audit_reviews.json",
    },
    "incidents": {
        "count": 80,
        "sample_ids": ("INC00001", "INC00002"),
        "composer": "incidents_records",
        "json_filename": "incidents.json",
    },
    "nps_responses": {
        "count": 150,
        "sample_ids": ("NPS00001", "NPS00002"),
        "composer": "nps_responses_records",
        "json_filename": "nps.json",
    },
    "rcsa_register": {
        "count": 80,
        "sample_ids": ("RSK0001", "RSK0002"),
        "composer": "rcsa_register_records",
        "json_filename": "rcsa_register.json",
    },
}


# ============================================================
# Section 1 — Config has all 4 tables in per_table
# ============================================================

def test_audit_reviews_set_to_auto():
    cfg = json.loads(
        (REPO_ROOT / "data"
         / "integration_layer_config.json").read_text()
    )
    per_table = cfg["_data_source"]["per_table"]
    assert per_table.get("audit_reviews") == "auto", (
        f"per_table.audit_reviews should be 'auto', got "
        f"{per_table.get('audit_reviews')!r}"
    )


def test_incidents_set_to_auto():
    cfg = json.loads(
        (REPO_ROOT / "data"
         / "integration_layer_config.json").read_text()
    )
    per_table = cfg["_data_source"]["per_table"]
    assert per_table.get("incidents") == "auto"


def test_nps_responses_set_to_auto():
    cfg = json.loads(
        (REPO_ROOT / "data"
         / "integration_layer_config.json").read_text()
    )
    per_table = cfg["_data_source"]["per_table"]
    assert per_table.get("nps_responses") == "auto"


def test_rcsa_register_set_to_auto():
    cfg = json.loads(
        (REPO_ROOT / "data"
         / "integration_layer_config.json").read_text()
    )
    per_table = cfg["_data_source"]["per_table"]
    assert per_table.get("rcsa_register") == "auto"


# ============================================================
# Section 2 — Production counts preserved
# ============================================================

def test_audit_reviews_composer_returns_expected_count():
    from utils.cockpit_read import audit_reviews_records
    records = audit_reviews_records(data_dir="data")
    assert len(records) == 250, (
        f"audit_reviews_records under auto mode returned "
        f"{len(records)} records; expected 250 "
        f"(JSON fallback should preserve count)"
    )


def test_incidents_composer_returns_expected_count():
    from utils.cockpit_read import incidents_records
    records = incidents_records(data_dir="data")
    assert len(records) == 80


def test_nps_responses_composer_returns_expected_count():
    from utils.cockpit_read import nps_responses_records
    records = nps_responses_records(data_dir="data")
    assert len(records) == 150


def test_rcsa_register_composer_returns_expected_count():
    from utils.cockpit_read import rcsa_register_records
    records = rcsa_register_records(data_dir="data")
    assert len(records) == 80


# ============================================================
# Section 3 — Known IDs still appear
# ============================================================

def test_audit_reviews_known_ids_present():
    from utils.cockpit_read import audit_reviews_records
    ids = {r["id"] for r in audit_reviews_records(data_dir="data")}
    for known in ("AUD00001", "AUD00002"):
        assert known in ids, (
            f"Known ID {known} missing from auto-mode read"
        )


def test_incidents_known_ids_present():
    from utils.cockpit_read import incidents_records
    ids = {r["id"] for r in incidents_records(data_dir="data")}
    for known in ("INC00001", "INC00002"):
        assert known in ids


def test_nps_responses_known_ids_present():
    from utils.cockpit_read import nps_responses_records
    ids = {r["id"] for r in nps_responses_records(data_dir="data")}
    for known in ("NPS00001", "NPS00002"):
        assert known in ids


def test_rcsa_register_known_ids_present():
    from utils.cockpit_read import rcsa_register_records
    ids = {r["id"] for r in rcsa_register_records(data_dir="data")}
    for known in ("RSK0001", "RSK0002"):
        assert known in ids


# ============================================================
# Section 4 — Equivalence: auto mode = json mode in current env
# ============================================================

def test_auto_mode_equals_json_mode_across_all_4_tables(
    tmp_data_dir,
):
    """Equivalence proof, replicated from v10.311 across all 4
    new tables. For each table: explicit `json` mode and `auto`
    mode (PG unreachable) must return identical data — the
    safety guarantee for safe rollback."""
    from utils.cockpit_read import _load_table_via_shim

    for table, spec in TABLE_EXPECTATIONS.items():
        # Setup synthetic data
        synthetic = [
            {"id": f"X{i}", "value": i}
            for i in range(5)
        ]
        (tmp_data_dir / spec["json_filename"]).write_text(
            json.dumps(synthetic))

        # json mode
        (tmp_data_dir / "integration_layer_config.json"
         ).write_text(json.dumps({
            "_data_source": {
                "default": "json",
                "per_table": {table: "json"},
            }}))
        json_result = _load_table_via_shim(
            table,
            json_filename=spec["json_filename"],
            data_dir=tmp_data_dir,
        )

        # auto mode
        (tmp_data_dir / "integration_layer_config.json"
         ).write_text(json.dumps({
            "_data_source": {
                "default": "json",
                "per_table": {table: "auto"},
            }}))
        auto_result = _load_table_via_shim(
            table,
            json_filename=spec["json_filename"],
            data_dir=tmp_data_dir,
        )

        assert json_result == auto_result, (
            f"Table {table}: json mode and auto mode "
            f"(PG unreachable) returned different results"
        )

        # Clean up synthetic JSON so the next iteration is clean
        (tmp_data_dir / spec["json_filename"]).unlink()


# ============================================================
# Section 5 — Reversibility per table
# ============================================================

def test_each_table_reversibility(tmp_data_dir):
    """Roundtrip: no-config → auto → json must yield
    identical data for each of the 4 tables. Same safety
    guarantee as v10.311's reversibility test."""
    from utils.cockpit_read import _load_table_via_shim

    for table, spec in TABLE_EXPECTATIONS.items():
        synthetic = [{"id": "RT1", "n": 1}, {"id": "RT2", "n": 2}]
        (tmp_data_dir / spec["json_filename"]).write_text(
            json.dumps(synthetic))

        # Baseline: no config file
        config_file = tmp_data_dir / "integration_layer_config.json"
        if config_file.exists():
            config_file.unlink()
        baseline = _load_table_via_shim(
            table,
            json_filename=spec["json_filename"],
            data_dir=tmp_data_dir,
        )

        # Flip to auto
        config_file.write_text(json.dumps({
            "_data_source": {
                "default": "json",
                "per_table": {table: "auto"},
            }}))
        after_flip = _load_table_via_shim(
            table,
            json_filename=spec["json_filename"],
            data_dir=tmp_data_dir,
        )

        # Roll back to json
        config_file.write_text(json.dumps({
            "_data_source": {
                "default": "json",
                "per_table": {table: "json"},
            }}))
        after_rollback = _load_table_via_shim(
            table,
            json_filename=spec["json_filename"],
            data_dir=tmp_data_dir,
        )

        assert baseline == after_flip == after_rollback, (
            f"Table {table}: round-trip not idempotent"
        )

        # Cleanup
        (tmp_data_dir / spec["json_filename"]).unlink()


# ============================================================
# Section 6 — v10.311's toggle unchanged (regression guard)
# ============================================================

def test_compliance_regulatory_returns_still_auto():
    """v10.311's toggle must not be regressed by this batch.
    G201 already guards this, but the test reinforces it."""
    cfg = json.loads(
        (REPO_ROOT / "data"
         / "integration_layer_config.json").read_text()
    )
    per_table = cfg["_data_source"]["per_table"]
    assert per_table.get("compliance_regulatory_returns") == "auto"


def test_default_mode_still_json():
    cfg = json.loads(
        (REPO_ROOT / "data"
         / "integration_layer_config.json").read_text()
    )
    assert cfg["_data_source"]["default"] == "json"


# ============================================================
# Section 7 — pg_capable_tables registry unchanged
# ============================================================

def test_pg_capable_tables_registry_unchanged():
    """This batch flips already-capable tables' modes; doesn't
    add new tables to the capable set. Registry should hold
    at the v10.307 set of 5."""
    from utils.cockpit_read import pg_capable_tables
    tables = set(pg_capable_tables())
    expected = {
        "audit_reviews",
        "compliance_regulatory_returns",
        "incidents",
        "nps_responses",
        "rcsa_register",
    }
    assert tables == expected


# ============================================================
# Section 8 — All 5 v10.306 tables now in per_table
# ============================================================

def test_all_5_v10306_tables_now_in_per_table():
    """After this batch, every PG-capable table is exercising
    the shim in production config. This is the milestone the
    batch closes."""
    cfg = json.loads(
        (REPO_ROOT / "data"
         / "integration_layer_config.json").read_text()
    )
    per_table = cfg["_data_source"]["per_table"]
    expected = {
        "audit_reviews",
        "compliance_regulatory_returns",
        "incidents",
        "nps_responses",
        "rcsa_register",
    }
    actual = set(per_table.keys())
    assert expected.issubset(actual), (
        f"per_table missing v10.306 tables: {expected - actual}"
    )


# ============================================================
# Section 9 — Audit gate G202
# ============================================================

def test_g202_gate_exists_and_passes():
    from scripts.audit import GATES
    g202 = None
    for gid, fn in GATES:
        if gid == "G202":
            g202 = fn()
            break
    assert g202 is not None, "G202 not registered"
    assert g202["passed"], (
        f"G202 failed. {g202.get('summary', '')}. "
        f"Violations: {g202.get('violations', [])[:5]}"
    )


# ============================================================
# Section 10 — G201 still passes (v10.311 invariant)
# ============================================================

def test_g201_still_passes_after_fanout():
    """G201 was shipped in v10.311 and locks the compliance
    toggle. It must still pass after this batch extends the
    config."""
    from scripts.audit import GATES
    g201 = None
    for gid, fn in GATES:
        if gid == "G201":
            g201 = fn()
            break
    assert g201 is not None, "G201 missing"
    assert g201["passed"], (
        f"G201 regressed in v10.312: {g201.get('summary', '')}"
    )
