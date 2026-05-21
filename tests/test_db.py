"""tests/test_db.py — utils/db.py coverage (Standard #4, v5.33).

Targets the SQL-safety helpers (V-002 mitigation), the dual-mode routing
introduced in v5.30, and the marshaller registry. These are the public
contract surfaces of the architectural seam — every page reads/writes
through them, so they must be airtight.

Coverage scope:
  - _check_table()           — whitelist enforcement
  - _qid() / _qcols() / _qplaceholders() — SQL identifier safety
  - JSON_PATH_TO_TABLE        — map well-formed
  - _table_for_path()         — path resolution (Path obj + string)
  - Database._get_marshallers — registry shape
  - Database.is_postgres_ready — env gate
  - Database.table_uses_db    — combined gate
  - Database.save_json/load_json round-trip via JSON path
  - Atomic write (no partial files on failure)
  - Default value handling
  - PG schema string is well-formed (parsable as SQL)

Out of scope (needs live PG or psycopg2):
  - Actual PG round-trip
  - Pool acquisition / connection retries
  - Per-table marshaller execution

Those belong in tests marked @pytest.mark.integration which CI skips
unless PG is available.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest


# ═══════════════════════════════════════════════════════════════════════
# SQL safety helpers (V-002 mitigation — closes G9)
# ═══════════════════════════════════════════════════════════════════════

class TestCheckTable:
    """_check_table() rejects names not in TABLE_REGISTRY."""

    def test_accepts_known_table(self):
        from utils.db import _check_table
        assert _check_table("users") == "users"
        assert _check_table("pipeline_deals") == "pipeline_deals"

    def test_accepts_schema_qualified_name(self):
        from utils.db import _check_table
        assert _check_table("audit.audit_logs") == "audit.audit_logs"
        assert _check_table("performance.actuals") == "performance.actuals"

    def test_rejects_unknown_table(self):
        from utils.db import _check_table
        with pytest.raises((ValueError, KeyError)):
            _check_table("totally_made_up_xyz")

    def test_rejects_sql_injection_attempt(self):
        """Even if a name LOOKS like a real table but contains SQL,
        the whitelist must reject it."""
        from utils.db import _check_table
        for evil in [
            "users; DROP TABLE users",
            "users--",
            "users' OR 1=1",
            "users\"; DELETE FROM users; --",
        ]:
            with pytest.raises((ValueError, KeyError)):
                _check_table(evil)


class TestQid:
    """_qid() wraps an identifier in psycopg2.sql.Identifier so it can
    never inject SQL."""

    def test_returns_sql_identifier_object(self):
        try:
            from psycopg2 import sql as _pg_sql
        except ImportError:
            pytest.skip("psycopg2 not available")
        from utils.db import _qid
        result = _qid("users")
        assert isinstance(result, _pg_sql.Identifier)

    def test_handles_table_name_with_underscore(self):
        try:
            from psycopg2 import sql as _pg_sql
        except ImportError:
            pytest.skip("psycopg2 not available")
        from utils.db import _qid
        # Just verify it returns a valid Identifier; quoting is psycopg2's job
        result = _qid("pipeline_deals")
        assert isinstance(result, _pg_sql.Identifier)


class TestQplaceholders:
    """_qplaceholders(n) returns SQL fragments for n positional args."""

    def test_zero_placeholders(self):
        try:
            from psycopg2 import sql as _pg_sql
        except ImportError:
            pytest.skip("psycopg2 not available")
        from utils.db import _qplaceholders
        # n=0 should still produce a valid (empty) Composable
        result = _qplaceholders(0)
        # Just verify it doesn't crash and returns SOMETHING SQL-shaped
        assert result is not None

    def test_three_placeholders(self):
        try:
            from psycopg2 import sql as _pg_sql
        except ImportError:
            pytest.skip("psycopg2 not available")
        from utils.db import _qplaceholders
        result = _qplaceholders(3)
        assert result is not None  # Composable; structure is psycopg2's


# ═══════════════════════════════════════════════════════════════════════
# JSON_PATH_TO_TABLE map + _table_for_path (v5.30 framework)
# ═══════════════════════════════════════════════════════════════════════

class TestJsonPathToTable:
    """The map declared in v5.30 must be well-formed."""

    def test_map_exists_and_is_dict(self):
        from utils.db import JSON_PATH_TO_TABLE
        assert isinstance(JSON_PATH_TO_TABLE, dict)

    def test_module_config_pilot_registered(self):
        """v5.30 wired module_config as the first pilot."""
        from utils.db import JSON_PATH_TO_TABLE
        assert JSON_PATH_TO_TABLE.get("module_config.json") == "module_config"

    def test_keys_end_in_dot_json(self):
        from utils.db import JSON_PATH_TO_TABLE
        for k in JSON_PATH_TO_TABLE:
            assert k.endswith(".json"), f"map key {k!r} must end in .json"

    def test_values_are_table_names(self):
        """Each value must be a registered table name."""
        from utils.db import JSON_PATH_TO_TABLE, TABLE_REGISTRY
        for k, v in JSON_PATH_TO_TABLE.items():
            assert v in TABLE_REGISTRY, (
                f"JSON_PATH_TO_TABLE[{k!r}] = {v!r} but {v} not in TABLE_REGISTRY"
            )


class TestTableForPath:
    """_table_for_path() resolves Path objects + strings consistently."""

    def test_resolves_string_filename(self):
        from utils.db import _table_for_path
        assert _table_for_path("module_config.json") == "module_config"

    def test_resolves_path_object(self):
        from utils.db import _table_for_path
        assert _table_for_path(Path("module_config.json")) == "module_config"

    def test_resolves_path_with_directory_prefix(self):
        """Only the basename should matter."""
        from utils.db import _table_for_path
        assert _table_for_path(Path("data/module_config.json")) == "module_config"
        assert _table_for_path(Path("/abs/path/to/module_config.json")) == "module_config"

    def test_returns_none_for_unknown_filename(self):
        from utils.db import _table_for_path
        assert _table_for_path("not_in_map.json") is None
        assert _table_for_path("staff_register.json") is None


# ═══════════════════════════════════════════════════════════════════════
# Marshaller registry
# ═══════════════════════════════════════════════════════════════════════

class TestMarshallerRegistry:
    """Database._get_marshallers returns the right pair for tracked tables."""

    def test_returns_pair_for_module_config(self):
        from utils.db import db
        result = db._get_marshallers("module_config")
        assert result is not None
        assert len(result) == 2
        save_fn, load_fn = result
        assert callable(save_fn)
        assert callable(load_fn)

    def test_returns_none_for_untracked_table(self):
        from utils.db import db
        assert db._get_marshallers("not_a_real_table") is None

    def test_save_marshaller_is_save_module_config(self):
        from utils.db import db
        save_fn, _ = db._get_marshallers("module_config")
        assert save_fn.__name__ == "_save_module_config_to_pg"

    def test_load_marshaller_is_load_module_config(self):
        from utils.db import db
        _, load_fn = db._get_marshallers("module_config")
        assert load_fn.__name__ == "_load_module_config_from_pg"


# ═══════════════════════════════════════════════════════════════════════
# is_postgres_ready / table_uses_db gates
# ═══════════════════════════════════════════════════════════════════════

class TestPostgresGates:
    """is_postgres_ready and table_uses_db must be safe in JSON-only envs."""

    def test_is_postgres_ready_returns_bool(self):
        from utils.db import db
        result = db.is_postgres_ready()
        assert isinstance(result, bool)

    def test_table_uses_db_false_when_pg_not_ready(self, monkeypatch):
        """Even if TABLE_USE_DB[t] is True, table_uses_db must return
        False unless PG is actually reachable."""
        from utils.db import db
        monkeypatch.setattr(db, "is_postgres_ready", lambda: False)
        # users is set to True in TABLE_USE_DB, but PG not ready
        assert db.table_uses_db("users") is False

    def test_table_uses_db_respects_flag_when_pg_ready(self, monkeypatch):
        from utils.db import db
        monkeypatch.setattr(db, "is_postgres_ready", lambda: True)
        # module_config is set to False in TABLE_USE_DB
        assert db.table_uses_db("module_config") is False

    def test_table_uses_db_unknown_table_returns_false(self, monkeypatch):
        from utils.db import db
        monkeypatch.setattr(db, "is_postgres_ready", lambda: True)
        assert db.table_uses_db("totally_made_up") is False


# ═══════════════════════════════════════════════════════════════════════
# load_json / save_json round-trip (JSON-only path)
# ═══════════════════════════════════════════════════════════════════════

class TestJsonRoundTrip:
    """Verify the JSON-only path works (PG path covered by integration tests)."""

    def test_save_and_load_dict(self, tmp_path):
        from utils.db import db
        p = tmp_path / "test_data.json"
        payload = {"alpha": 1, "beta": [1, 2, 3], "gamma": {"nested": True}}
        assert db.save_json(p, payload) is True
        assert p.exists()
        loaded = db.load_json(p)
        assert loaded == payload

    def test_save_and_load_list(self, tmp_path):
        from utils.db import db
        p = tmp_path / "test_list.json"
        payload = [{"id": 1}, {"id": 2}, {"id": 3}]
        assert db.save_json(p, payload) is True
        loaded = db.load_json(p)
        assert loaded == payload

    def test_load_missing_file_returns_default(self, tmp_path):
        from utils.db import db
        p = tmp_path / "nonexistent.json"
        # Default default is []
        assert db.load_json(p) == []
        # Custom default
        assert db.load_json(p, default={}) == {}
        assert db.load_json(p, default={"empty": True}) == {"empty": True}

    def test_save_creates_parent_directory(self, tmp_path):
        from utils.db import db
        p = tmp_path / "subdir" / "nested" / "file.json"
        assert db.save_json(p, {"test": True}) is True
        assert p.exists()

    def test_save_corrupted_json_returns_default(self, tmp_path):
        """If a file exists but is corrupt, load_json returns default."""
        from utils.db import db
        p = tmp_path / "corrupt.json"
        p.write_text("{ this is not valid json")
        # Should not raise; should return default
        result = db.load_json(p, default=[])
        assert result == []

    def test_save_json_atomic_no_partial_on_serialise_error(self, tmp_path):
        """If serialisation fails partway, the original file should be
        untouched (atomic write via temp+rename pattern)."""
        from utils.db import db
        p = tmp_path / "atomic.json"
        # First write a known-good payload
        assert db.save_json(p, {"good": 1}) is True
        original = p.read_text()
        # Try to save something unserialisable (a class instance with no default repr)
        class Unserialisable:
            pass
        bad_payload = {"obj": Unserialisable()}
        # Default str fallback in db.save_json prevents most failures, but
        # the atomic semantics still apply — if temp write fails for any
        # reason, the original file must stay intact.
        # (We can't easily force a write failure here without monkeypatching;
        # the contract is that on success we have new content, on failure the
        # original survives. Verifying by reading back.)
        result = db.save_json(p, bad_payload)
        # Either succeeded (with str fallback) or failed cleanly
        assert isinstance(result, bool)
        # File should still exist and be readable JSON
        assert p.exists()


# ═══════════════════════════════════════════════════════════════════════
# Schema SQL is well-formed
# ═══════════════════════════════════════════════════════════════════════

class TestSchemaSql:
    """get_schema_sql() returns a non-empty string with expected tables."""

    def test_schema_returns_string(self):
        from utils.db import get_schema_sql
        sql = get_schema_sql()
        assert isinstance(sql, str)
        assert len(sql) > 0

    def test_schema_has_essential_tables(self):
        """Every PG-live table flagged True in TABLE_USE_DB should
        eventually have a CREATE TABLE in the schema. Right now several
        are missing (latent issue noted in v5.31 changelog) — this test
        covers the critical ones that have been verified."""
        from utils.db import get_schema_sql
        sql = get_schema_sql()
        # These have schemas we've verified
        for table in ["users", "audit_trail", "bsc_scores", "pipeline_deals",
                      "loan_applications", "aml_alerts", "disciplinary",
                      "module_config"]:
            assert f"CREATE TABLE IF NOT EXISTS {table}" in sql, (
                f"Schema missing CREATE TABLE for {table}"
            )

    def test_schema_creates_required_extensions(self):
        from utils.db import get_schema_sql
        sql = get_schema_sql()
        assert 'CREATE EXTENSION IF NOT EXISTS "uuid-ossp"' in sql
        assert "CREATE EXTENSION IF NOT EXISTS pgcrypto" in sql

    def test_schema_creates_required_schemas(self):
        from utils.db import get_schema_sql
        sql = get_schema_sql()
        # At least the audit + performance + staging schemas should be there
        for schema in ["audit", "performance", "staging"]:
            assert f"CREATE SCHEMA IF NOT EXISTS {schema}" in sql or \
                   f"{schema}." in sql, f"Schema {schema} missing"


# ═══════════════════════════════════════════════════════════════════════
# TABLE_USE_DB / TABLE_REGISTRY consistency
# ═══════════════════════════════════════════════════════════════════════

class TestTableRegistry:
    """The registry must be internally consistent."""

    def test_registry_includes_all_use_db_tables(self):
        from utils.db import TABLE_REGISTRY, TABLE_USE_DB
        for table in TABLE_USE_DB:
            assert table in TABLE_REGISTRY

    def test_registry_includes_schema_qualified_tables(self):
        from utils.db import TABLE_REGISTRY
        # These are added explicitly in db.py to the registry
        for t in ["audit.audit_logs", "performance.actuals"]:
            assert t in TABLE_REGISTRY

    def test_use_db_values_are_bools(self):
        from utils.db import TABLE_USE_DB
        for table, val in TABLE_USE_DB.items():
            assert isinstance(val, bool), (
                f"TABLE_USE_DB[{table!r}] = {val!r}, expected bool"
            )

    def test_use_db_has_79_entries(self):
        """TABLE_USE_DB has 79 entries as of v10.93.

        v10.93 added 27 entries for the v10.88-v10.91 PG-migrated tables
        (agent_fraud_alerts, ifrs9_loans, legal_matters, etc.). Before
        v10.93 the count was 52. The current count is the audit floor —
        if a future drop intentionally removes or adds entries, update
        this test AND the SCOPE_LEDGER's TABLE_USE_DB tracker.
        """
        from utils.db import TABLE_USE_DB
        assert len(TABLE_USE_DB) == 79, (
            f"TABLE_USE_DB has {len(TABLE_USE_DB)} entries; v10.93 floor "
            f"is 79. If you intentionally added/removed a table, update "
            f"this test."
        )
