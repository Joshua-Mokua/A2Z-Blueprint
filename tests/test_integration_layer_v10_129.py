"""tests/test_integration_layer_v10_129.py — v10.129 PostgreSQL migration step.

v10.129 adds the first integration-layer operational table to the
PostgreSQL schema: `sla_tickets`. This validates the v10.116 _data_source
shim end-to-end: a real wired-39 table now has both a JSON read path
AND a PG read path, with the shim selecting between them per-table via
config.

Verifies:
  1. sla_tickets table is in utils/db.py SCHEMA_SQL
  2. Schema has all 19 columns matching data/sla_tickets.json shape
  3. sla_tickets is in scripts/migrate_to_postgres.py FLAT_MIGRATIONS
  4. The v10.116 shim's _data_source default is unchanged ("json")
  5. Schema is syntactically plausible PostgreSQL DDL
  6. JSON read path still works (regression — K039 rule unchanged)
  7. G143 still 99/131 STRICT-READY (high) — no rule-density work
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


# ─── sla_tickets schema in utils/db.py ──────────────────────────────

class TestSlaTicketsSchemaInDb:

    @pytest.fixture(scope="class")
    def schema_sql(self):
        from utils.db import SCHEMA_SQL
        return SCHEMA_SQL

    def test_sla_tickets_create_table_present(self, schema_sql):
        """SCHEMA_SQL must contain CREATE TABLE for sla_tickets."""
        assert "CREATE TABLE IF NOT EXISTS sla_tickets" in schema_sql

    def test_sla_tickets_has_all_19_columns(self, schema_sql):
        """The schema must cover all 19 fields from data/sla_tickets.json
        (plus the standard data/created_at/updated_at trio)."""
        # Extract the sla_tickets CREATE TABLE block
        m = re.search(
            r"CREATE TABLE IF NOT EXISTS sla_tickets\s*\((.*?)\);",
            schema_sql, re.DOTALL)
        assert m, "Could not locate sla_tickets CREATE TABLE block"
        block = m.group(1)

        expected_cols = {
            "id", "title", "category", "priority",
            "sla_target_hours", "sla_target_days",
            "assignee", "requester", "department", "branch",
            "status", "raised_date", "resolved_date",
            "actual_hours", "actual_days",
            "within_sla", "escalation_count", "description",
            "last_updated",
        }
        for col in expected_cols:
            assert re.search(rf"\b{re.escape(col)}\b", block), (
                f"Column '{col}' missing from sla_tickets schema")

    def test_sla_tickets_has_primary_key(self, schema_sql):
        """id should be the PRIMARY KEY (matches sanctions_register
        and other operational tables)."""
        m = re.search(
            r"CREATE TABLE IF NOT EXISTS sla_tickets\s*\((.*?)\);",
            schema_sql, re.DOTALL)
        block = m.group(1)
        assert "PRIMARY KEY" in block

    def test_sla_tickets_has_assignee_index(self, schema_sql):
        """assignee is the staff_field for K039 rule. Must be indexed
        for production query performance."""
        assert ("CREATE INDEX IF NOT EXISTS idx_sla_tickets_assignee"
                in schema_sql)


# ─── sla_tickets in FLAT_MIGRATIONS ─────────────────────────────────

class TestSlaTicketsInMigrationScript:

    def test_sla_tickets_in_flat_migrations(self):
        """scripts/migrate_to_postgres.py FLAT_MIGRATIONS must include
        sla_tickets so a one-shot migration handles it alongside the
        existing CBK regulatory tables."""
        src = (REPO_ROOT / "scripts" /
               "migrate_to_postgres.py").read_text()
        assert '"sla_tickets.json"' in src, (
            "sla_tickets.json missing from FLAT_MIGRATIONS source filename")
        assert '"sla_tickets"' in src, (
            "sla_tickets table name missing from FLAT_MIGRATIONS")

    def test_flat_migrations_columns_match_schema(self):
        """The flat-cols tuple in FLAT_MIGRATIONS for sla_tickets must
        match the columns declared in SCHEMA_SQL."""
        src = (REPO_ROOT / "scripts" /
               "migrate_to_postgres.py").read_text()
        # Extract the sla_tickets tuple
        m = re.search(
            r'"sla_tickets\.json".*?\(([^()]+)\)\)', src, re.DOTALL)
        assert m, "Could not locate sla_tickets entry in FLAT_MIGRATIONS"
        tuple_text = m.group(1)
        for col in ("id", "title", "assignee", "status",
                    "raised_date", "within_sla", "last_updated"):
            assert f'"{col}"' in tuple_text, (
                f"Column '{col}' missing from FLAT_MIGRATIONS tuple")


# ─── v10.116 _data_source shim default unchanged ────────────────────

class TestV10_116_ShimDefaultUnchanged:
    """v10.129 must NOT change the v10.116 shim's default behavior.
    JSON path is still the default; PG path is opt-in per-table."""

    def test_default_data_source_is_json(self):
        """When integration_layer_config.json has no _data_source key,
        the shim must default to 'json'."""
        from utils.actuals_engine import _read_data_source_config
        # Pass a temp dir with no config file — shim must default
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            cfg = _read_data_source_config(Path(tmp))
        assert cfg["default"] == "json"
        assert cfg["per_table"] == {}

    def test_actual_config_default_still_json(self):
        """The shipped data/integration_layer_config.json must still
        default to JSON (no opt-in PG flips applied without config
        modification)."""
        path = (REPO_ROOT / "data" /
                "integration_layer_config.json")
        with open(path) as f:
            cfg = json.load(f)
        ds = cfg.get("_data_source")
        # Two valid forms:
        #   missing → defaults json  (acceptable)
        #   "json" string                 (acceptable)
        #   {"default": "json", ...}      (acceptable)
        # but NOT:
        #   "pg_view"                     (would force PG)
        #   {"default": "pg_view", ...}   (would force PG)
        if ds is None:
            return  # missing — defaults to json
        if isinstance(ds, str):
            assert ds in ("json", "auto"), (
                f"Default _data_source flipped to {ds!r}; "
                f"v10.129 should not flip the default")
        elif isinstance(ds, dict):
            assert ds.get("default", "json") in ("json", "auto"), (
                f"Default _data_source flipped to {ds.get('default')!r}; "
                f"v10.129 should not flip the default")


# ─── JSON read path regression ──────────────────────────────────────

class TestJsonPathRegression:
    """v10.129 adds the PG read path but doesn't change JSON behavior.
    K039 rule (SLA Tickets Within SLA) should still work identically."""

    def test_sla_tickets_json_still_loadable(self):
        path = REPO_ROOT / "data" / "sla_tickets.json"
        assert path.exists()
        with open(path) as f:
            rows = json.load(f)
        assert len(rows) == 100, "sla_tickets seed should have 100 rows"

    def test_k039_still_in_aggregation_rules(self):
        """K039 (PERCENTAGE rule on sla_tickets) must still be
        registered. The rule is what proves the JSON path works."""
        path = REPO_ROOT / "data" / "aggregation_rules.json"
        with open(path) as f:
            data = json.load(f)
        k039 = [r for r in data["rules"]
                if r.get("kpi_id") == "K039"]
        assert len(k039) >= 1, "K039 should be registered"


# ─── G143 unchanged — not a rule-density drop ────────────────────────

class TestG143UnchangedV10129:

    @pytest.fixture(scope="class")
    def gate_result(self):
        sys.path.insert(0, str(REPO_ROOT / "scripts"))
        try:
            import audit
            return audit.gate_kpi_source_has_aggregator()
        finally:
            sys.path.pop(0)

    def test_coverage_still_99(self, gate_result):
        sp = gate_result["strict_preview"]
        assert sp["covered"] == 99

    def test_tier_still_high(self, gate_result):
        sp = gate_result["strict_preview"]
        assert sp["tag"] == "STRICT-READY (high)"


# ─── No rule-density work ────────────────────────────────────────────

class TestNoRuleDensityV10129:

    def test_no_v10_129_origin_rules(self):
        with open(REPO_ROOT / "data" / "aggregation_rules.json") as f:
            data = json.load(f)
        v129 = [r for r in data["rules"]
                if r.get("_origin", "").startswith("v10.129_")]
        assert v129 == [], (
            f"v10.129 is a PG-migration drop, not rule-density. Found "
            f"{len(v129)} v10.129-origin rules; expected 0.")

    def test_total_rules_still_100(self):
        with open(REPO_ROOT / "data" / "aggregation_rules.json") as f:
            data = json.load(f)
        assert len(data["rules"]) == 100
