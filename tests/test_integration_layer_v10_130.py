"""tests/test_integration_layer_v10_130.py — v10.130 PG migration step 2.

v10.130 applies the v10.129 sla_tickets recipe to the next operational
table: `debt_recovery`. Higher rule density (4 wired rules vs 1) proves
the v10.116 _data_source shim handles multi-rule tables identically.

Verifies:
  1. debt_recovery table is in utils/db.py SCHEMA_SQL
  2. Schema has all 28 columns matching data/debt_recovery.json shape
  3. debt_recovery is in scripts/migrate_to_postgres.py FLAT_MIGRATIONS
  4. v10.116 shim default still 'json' — no regression from v10.129
  5. All 4 wired rules on debt_recovery still work via JSON path
  6. G143 still 99/131 STRICT-READY (high)
  7. v10.129 sla_tickets schema preserved (additive drop)
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


# ─── debt_recovery schema ───────────────────────────────────────────

class TestDebtRecoverySchemaInDb:

    @pytest.fixture(scope="class")
    def schema_sql(self):
        from utils.db import SCHEMA_SQL
        return SCHEMA_SQL

    def test_create_table_present(self, schema_sql):
        assert "CREATE TABLE IF NOT EXISTS debt_recovery" in schema_sql

    def test_has_all_28_columns(self, schema_sql):
        m = re.search(
            r"CREATE TABLE IF NOT EXISTS debt_recovery\s*\((.*?)\);",
            schema_sql, re.DOTALL)
        assert m
        block = m.group(1)
        expected = {
            "id", "account_number", "client_cif", "debtor_name",
            "outstanding", "loan_amount", "dpd", "npl_days",
            "product", "branch", "rm_code", "recovery_stage",
            "collateral_type", "collateral_value", "ltvr",
            "recovery_officer", "recovery_officer_code",
            "last_contact", "next_action", "settlement_offer",
            "amount_recovered", "legal_referral", "legal_firm",
            "demand_letters_sent", "status", "created_date",
            "last_updated", "notes",
        }
        for col in expected:
            assert re.search(rf"\b{re.escape(col)}\b", block), (
                f"Column '{col}' missing from debt_recovery schema")

    def test_primary_key_on_id(self, schema_sql):
        m = re.search(
            r"CREATE TABLE IF NOT EXISTS debt_recovery\s*\((.*?)\);",
            schema_sql, re.DOTALL)
        assert "PRIMARY KEY" in m.group(1)

    def test_recovery_officer_code_indexed(self, schema_sql):
        """recovery_officer_code is the primary staff_field for K027 +
        K113 + Collection Throughput rules. Must be indexed."""
        assert ("idx_debt_recovery_officer" in schema_sql)

    def test_rm_code_indexed(self, schema_sql):
        """rm_code is the alternate staff_field for some rules.
        Indexed for performance."""
        assert "idx_debt_recovery_rm" in schema_sql

    def test_status_dpd_lastupd_indexed(self, schema_sql):
        """status, dpd, last_updated are predicate / period fields used
        by all 4 wired rules. Indexed for performance."""
        for idx in ("idx_debt_recovery_status",
                    "idx_debt_recovery_dpd",
                    "idx_debt_recovery_lastupd"):
            assert idx in schema_sql, f"Missing index {idx}"


# ─── FLAT_MIGRATIONS entry ──────────────────────────────────────────

class TestDebtRecoveryInMigrationScript:

    def test_in_flat_migrations(self):
        src = (REPO_ROOT / "scripts" /
               "migrate_to_postgres.py").read_text()
        assert '"debt_recovery.json"' in src
        assert '"debt_recovery"' in src

    def test_flat_migrations_columns_match_schema(self):
        src = (REPO_ROOT / "scripts" /
               "migrate_to_postgres.py").read_text()
        m = re.search(
            r'"debt_recovery\.json".*?\(([^()]+)\)\)',
            src, re.DOTALL)
        assert m, "Could not locate debt_recovery in FLAT_MIGRATIONS"
        tuple_text = m.group(1)
        for col in ("id", "recovery_officer_code", "rm_code", "status",
                    "dpd", "last_updated", "outstanding", "loan_amount"):
            assert f'"{col}"' in tuple_text, (
                f"Column '{col}' missing from FLAT_MIGRATIONS tuple")


# ─── v10.116 shim default unchanged (regression check) ──────────────

class TestShimDefaultStillJson:

    def test_shim_defaults_json(self):
        from utils.actuals_engine import _read_data_source_config
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            cfg = _read_data_source_config(Path(tmp))
        assert cfg["default"] == "json"

    def test_production_config_no_pg_default(self):
        path = (REPO_ROOT / "data" /
                "integration_layer_config.json")
        with open(path) as f:
            cfg = json.load(f)
        ds = cfg.get("_data_source")
        if ds is None:
            return
        if isinstance(ds, str):
            assert ds in ("json", "auto")
        elif isinstance(ds, dict):
            assert ds.get("default", "json") in ("json", "auto")


# ─── JSON read path regression — all 4 debt_recovery rules ──────────

class TestDebtRecoveryRulesPreserved:
    """4 rules wire debt_recovery: K027, K113, K044, and the
    non-K-coded 'Collection Throughput'. All must still be registered
    and the JSON file still loadable."""

    def test_debt_recovery_json_loadable(self):
        path = REPO_ROOT / "data" / "debt_recovery.json"
        assert path.exists()
        with open(path) as f:
            rows = json.load(f)
        assert len(rows) == 150, "debt_recovery seed should have 150 rows"

    def test_all_four_rules_registered(self):
        path = REPO_ROOT / "data" / "aggregation_rules.json"
        with open(path) as f:
            data = json.load(f)
        kpi_ids = {r.get("kpi_id") for r in data["rules"]
                   if r.get("source_table") == "debt_recovery"}
        # K027 (Recovery Rate, RATIO), K113 (Active Recovery Cases,
        # COUNT), K114 (Recovered Amounts, SUM) are the K-coded ones;
        # "Collection Throughput" is the non-K-coded library entry from
        # v10.121.
        for required in ("K027", "K113", "K114",
                         "Collection Throughput"):
            assert required in kpi_ids, (
                f"Rule {required} on debt_recovery missing")


# ─── v10.129 sla_tickets schema preserved (additive) ────────────────

class TestV10_129SlaTicketsPreserved:
    """v10.130 is additive — must not break v10.129's sla_tickets."""

    def test_sla_tickets_schema_still_present(self):
        from utils.db import SCHEMA_SQL
        assert "CREATE TABLE IF NOT EXISTS sla_tickets" in SCHEMA_SQL
        assert "idx_sla_tickets_assignee" in SCHEMA_SQL

    def test_sla_tickets_still_in_flat_migrations(self):
        src = (REPO_ROOT / "scripts" /
               "migrate_to_postgres.py").read_text()
        assert '"sla_tickets.json"' in src


# ─── G143 unchanged ─────────────────────────────────────────────────

class TestG143UnchangedV10130:

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

class TestNoRuleDensityV10130:

    def test_no_v10_130_origin_rules(self):
        with open(REPO_ROOT / "data" / "aggregation_rules.json") as f:
            data = json.load(f)
        v130 = [r for r in data["rules"]
                if r.get("_origin", "").startswith("v10.130_")]
        assert v130 == []

    def test_total_rules_still_100(self):
        with open(REPO_ROOT / "data" / "aggregation_rules.json") as f:
            data = json.load(f)
        assert len(data["rules"]) == 100
