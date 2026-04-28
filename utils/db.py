"""utils/db.py — PostgreSQL abstraction layer for A2Z Blueprint MIS 360.

MIGRATION STRATEGY
──────────────────
Each table has a USE_POSTGRES flag. Set to True one table at a time
to migrate from JSON. The JSON backend always stays as a fallback.

USAGE
─────
from utils.db import db

# Read
users = db.fetch_all("SELECT * FROM users WHERE active = true")
user  = db.fetch_one("SELECT * FROM users WHERE username = %s", (uname,))

# Write
db.execute("UPDATE users SET password = %s WHERE username = %s", (pw_hash, uname))

# Transaction
with db.transaction() as conn:
    db.execute("INSERT INTO audit_trail ...", (...,), conn=conn)
    db.execute("UPDATE users ...", (...,), conn=conn)

ENVIRONMENT VARIABLES
──────────────────────
Set these in your deployment environment (never hardcode):
  A2Z_DB_HOST     = localhost (or RDS/Cloud SQL endpoint)
  A2Z_DB_PORT     = 5432
  A2Z_DB_NAME     = a2z_mис360
  A2Z_DB_USER     = a2z_app
  A2Z_DB_PASSWORD = (set in environment, never in code)
  A2Z_DB_SSLMODE  = require  (always in production)
  A2Z_USE_DB      = true     (set to 'true' to enable PostgreSQL)

TABLES MIGRATION STATUS
────────────────────────
Tier 1 (migrate first — auth & audit):
  users, audit_trail, sessions

Tier 2 (migrate second — core business):
  bsc_scores, kpi_definitions, targets, pipeline_deals, loan_applications

Tier 3 (migrate third — operational):
  watchlist, ews_cases, collateral, recoveries, compliance_cases

Tier 4 (migrate last — procurement, HR, projects):
  purchase_requests, purchase_orders, invoices, vendors, assets, contracts
  workforce, disciplinary, projects, initiatives

CBK DATA RESIDENCY: Use AWS Africa (Cape Town) or on-premise Kenyan servers.
Streamlit Community Cloud (US servers) is NOT compliant for production data.
"""

import os
import json
import logging
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("a2z.db")

# ── Configuration from environment ──────────────────────────────────────
_USE_DB     = os.getenv("A2Z_USE_DB", "false").lower() == "true"
_DB_HOST    = os.getenv("A2Z_DB_HOST", "localhost")
_DB_PORT    = int(os.getenv("A2Z_DB_PORT", "5432"))
_DB_NAME    = os.getenv("A2Z_DB_NAME", "a2z_mis360")
_DB_USER    = os.getenv("A2Z_DB_USER", "a2z_app")
_DB_PASS    = os.getenv("A2Z_DB_PASSWORD", "")
_DB_SSLMODE = os.getenv("A2Z_DB_SSLMODE", "prefer")   # "require" in production

# ── Per-table migration flags ─────────────────────────────────────────────
# Set individual tables to True as you migrate them.
# The system will use PostgreSQL for True tables and JSON for False tables.
TABLE_USE_DB = {
    # Tier 1 — Auth & Audit
    "users":            True,
    "audit_trail":      True,
    "sessions":         False,
    # Tier 2 — Core business
    "bsc_scores":       True,
    "kpi_definitions":  False,
    "targets":          False,
    "pipeline_deals":   True,
    "loan_applications":True,
    # Tier 3 — Operational
    "watchlist":        True,
    "ews_cases":        True,
    "collateral":       False,
    "recoveries":       False,
    "compliance_cases": False,
    "aml_alerts":       True,
    "rcsa_risks":       True,
    # Tier 4 — Procurement / HR / Projects
    "purchase_requests":True,
    "purchase_orders":  True,
    "invoices":         True,
    "vendors":          True,
    "assets":           True,
    "contracts":        True,
    "workforce":        True,
    "disciplinary":     True,
    "projects":         True,
    "initiatives":      False,
    # New modules v5.3
    "partnerships":     False,
    "referrals":        False,
    "agent_fraud":      False,
    "mou_categories":   False,
    "sponsored_events": False,
    "deal_rooms":       True,
    # ─── v5.8 — Phase 1, 2, 3 + FLEXCUBE modules (set True after migration) ──
    "cbk_returns":              False,
    "dpo_register":             False,
    "sanctions_register":       False,
    "capital_liquidity_metrics":False,
    "customer_onboarding":      False,
    "card_management":          False,
    "merchant_acquiring":       False,
    "alm_gap_analysis":         False,
    "alm_funding_sources":      False,
    "alm_alco_meetings":        False,
    "alm_contingency_plans":    False,
    "op_risk_losses":           False,
    "strategic_initiatives":    False,
    "board_papers":             False,
    "esg_green_loans":          False,
    "esg_initiatives":          False,
    "esg_climate_assessments":  False,
    "esg_score_snapshot":       False,
    "flexcube_events":          False,
    "flexcube_config":          False,
    "module_config":            False,
}

# ── SQL identifier safety (V-002 mitigation) ──────────────────────────────
# Direct f-string interpolation of table/column names into SQL strings is the
# CWE-89 SQL injection pattern. Even when current callers pass code constants,
# any future caller passing user input would enable injection.
#
# Rule: every table and column name passed into an SQL builder MUST go through
# _qid() (which uses psycopg2.sql.Identifier for safe quoting). Every table
# name MUST also be checked against the TABLE_REGISTRY whitelist before use.
#
# scripts/audit.py G9 enforces no f-string SQL with {table}/{col_str} patterns
# in this file.

# Whitelist of valid table names. Built from TABLE_USE_DB so we have one source
# of truth. Schema-qualified names (e.g. "audit.audit_logs") are added below.
TABLE_REGISTRY: set = set(TABLE_USE_DB.keys()) | {
    # Schema-qualified tables that aren't in TABLE_USE_DB
    "audit.audit_logs", "audit.etl_logs", "audit.error_logs",
    "audit.recon_runs", "audit.recon_breaks",
    "performance.actuals", "performance.targets", "performance.kpi_catalogue",
    "staging.flexcube_customers", "staging.flexcube_accounts",
    "staging.flexcube_loans",     "staging.flexcube_transactions",
    "staging.flexcube_gl_balances","staging.etl_batch_register",
}


# ── JSON-path → PG-table mapping (Standard #1, v5.30) ────────────────────
# When a page calls a2z_db.load_json("module_config.json"), the dual-mode
# router needs to know which PG table that file corresponds to. Add an
# entry here for every JSON file you want to migrate. Keys are the BARE
# filename (without "data/"); values are the table name as it appears in
# TABLE_USE_DB.
#
# Adding a key here is harmless on its own — it only changes behaviour
# when (a) PostgreSQL is reachable AND (b) `is_postgres_ready()` is True
# AND (c) the table-specific PG marshallers are wired up below.
#
# Phase 1 (dual-write): file is the source of truth; PG receives a copy
# on every save. Read still goes from file.
# Phase 2 (cutover):    flip TABLE_USE_DB[table] = True. Reads now come
# from PG; writes still go to both.
# Phase 3 (deprecation): remove the JSON write. PG is the only writer.
# Phase 4 (archive):    archive the JSON file under data/archive/.
JSON_PATH_TO_TABLE: dict = {
    "module_config.json": "module_config",
    # Add more pilots here as we migrate them. Each entry needs a matching
    # _save_<table>_to_pg() and _load_<table>_from_pg() pair in Database.
}


def _table_for_path(path) -> str | None:
    """Return the PG table name for a JSON file path, or None if the
    path isn't tracked. Accepts Path objects or strings."""
    from pathlib import Path as _Path
    if hasattr(path, "name"):
        name = path.name
    else:
        name = _Path(str(path)).name
    return JSON_PATH_TO_TABLE.get(name)


def _check_table(name: str) -> str:
    """Reject table names not in the whitelist. Returns the name unchanged
    if valid. Use this at every entry point that takes a table name from
    a caller.
    """
    if not isinstance(name, str) or not name:
        raise ValueError(f"Invalid table name: {name!r}")
    if name not in TABLE_REGISTRY:
        raise ValueError(
            f"Table {name!r} is not in TABLE_REGISTRY. "
            f"Add it to TABLE_USE_DB or TABLE_REGISTRY in utils/db.py before use."
        )
    return name


def _qid(name: str):
    """Return a safely-quoted SQL identifier (psycopg2.sql.Identifier).

    Handles both plain ('users') and schema-qualified ('audit.audit_logs')
    names. Each component is quoted independently so dots inside a single
    component are escaped, not parsed as separators.
    """
    from psycopg2 import sql as _pg_sql
    if "." in name:
        parts = name.split(".", 1)
        return _pg_sql.SQL(".").join(_pg_sql.Identifier(p) for p in parts)
    return _pg_sql.Identifier(name)


def _qcols(cols):
    """Return a comma-separated SQL fragment of safely-quoted column identifiers."""
    from psycopg2 import sql as _pg_sql
    return _pg_sql.SQL(", ").join(_pg_sql.Identifier(c) for c in cols)


def _qplaceholders(n: int):
    """Return a comma-separated SQL fragment of n %s placeholders."""
    from psycopg2 import sql as _pg_sql
    return _pg_sql.SQL(", ").join([_pg_sql.Placeholder()] * n)

# ── Connection pool ────────────────────────────────────────────────────────
_pool = None

def _get_pool():
    """Lazy-initialise connection pool. Returns None if psycopg2 not available."""
    global _pool
    if _pool is not None:
        return _pool
    if not _USE_DB:
        return None
    try:
        from psycopg2 import pool as _pg_pool
        _pool = _pg_pool.ThreadedConnectionPool(
            minconn=2,
            maxconn=20,
            host=_DB_HOST,
            port=_DB_PORT,
            dbname=_DB_NAME,
            user=_DB_USER,
            password=_DB_PASS,
            sslmode=_DB_SSLMODE,
            connect_timeout=10,
        )
        logger.info(f"PostgreSQL pool created: {_DB_HOST}:{_DB_PORT}/{_DB_NAME}")
        return _pool
    except ImportError:
        logger.warning("psycopg2 not installed. Run: pip install psycopg2-binary")
        return None
    except Exception as e:
        logger.error(f"PostgreSQL connection failed: {e}")
        return None


class Database:
    """PostgreSQL / JSON hybrid database interface."""

    def is_postgres_ready(self) -> bool:
        """True if PostgreSQL is configured and reachable."""
        return _USE_DB and _get_pool() is not None

    def table_uses_db(self, table: str) -> bool:
        """True if this table has been migrated to PostgreSQL."""
        return self.is_postgres_ready() and TABLE_USE_DB.get(table, False)

    @contextmanager
    def connection(self):
        """Context manager for a single connection from the pool."""
        pool = _get_pool()
        if pool is None:
            raise RuntimeError("PostgreSQL not available")
        conn = pool.getconn()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            pool.putconn(conn)

    @contextmanager
    def transaction(self):
        """Context manager for an explicit transaction block."""
        with self.connection() as conn:
            yield conn

    def execute(self, sql: str, params: tuple = (), conn=None) -> None:
        """Execute a DML statement (INSERT, UPDATE, DELETE)."""
        if conn is not None:
            with conn.cursor() as cur:
                cur.execute(sql, params)
            return
        with self.connection() as c:
            with c.cursor() as cur:
                cur.execute(sql, params)

    def fetch_one(self, sql: str, params: tuple = ()) -> Optional[Dict]:
        """Return a single row as a dict, or None."""
        with self.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                row = cur.fetchone()
                if row is None:
                    return None
                cols = [d[0] for d in cur.description]
                return dict(zip(cols, row))

    def fetch_all(self, sql: str, params: tuple = ()) -> List[Dict]:
        """Return all rows as a list of dicts."""
        with self.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                if cur.description is None:
                    return []
                cols = [d[0] for d in cur.description]
                return [dict(zip(cols, row)) for row in cur.fetchall()]

    def fetch_scalar(self, sql: str, params: tuple = ()) -> Any:
        """Return the first column of the first row."""
        row = self.fetch_one(sql, params)
        if row is None:
            return None
        return list(row.values())[0]

    def upsert(self, table: str, data: Dict, conflict_col: str) -> None:
        """INSERT ... ON CONFLICT DO UPDATE for simple key-value upserts."""
        from psycopg2 import sql as _pg_sql
        _check_table(table)
        cols   = list(data.keys())
        vals   = [data[c] for c in cols]
        # Build SQL via psycopg2.sql composition — every identifier is safely
        # quoted and validated. This replaces the previous f-string pattern.
        update_clause = _pg_sql.SQL(", ").join(
            _pg_sql.SQL("{c} = EXCLUDED.{c}").format(c=_pg_sql.Identifier(c))
            for c in cols if c != conflict_col
        )
        sql = _pg_sql.SQL(
            "INSERT INTO {tbl} ({cols}) VALUES ({vals}) "
            "ON CONFLICT ({pk}) DO UPDATE SET {update}"
        ).format(
            tbl    = _qid(table),
            cols   = _qcols(cols),
            vals   = _qplaceholders(len(cols)),
            pk     = _pg_sql.Identifier(conflict_col),
            update = update_clause,
        )
        self.execute(sql, tuple(vals))

    def health_check(self) -> Dict:
        """Returns DB health status for the Admin → System Health panel."""
        if not _USE_DB:
            return {"status": "disabled", "backend": "JSON files"}
        try:
            ver = self.fetch_scalar("SELECT version()")
            size = self.fetch_scalar(
                "SELECT pg_size_pretty(pg_database_size(current_database()))")
            conn_ct = self.fetch_scalar(
                "SELECT count(*) FROM pg_stat_activity WHERE datname = current_database()")
            return {
                "status":      "healthy",
                "backend":     "PostgreSQL",
                "version":     str(ver)[:40] if ver else "unknown",
                "db_size":     str(size) if size else "unknown",
                "connections": conn_ct or 0,
                "host":        f"{_DB_HOST}:{_DB_PORT}",
                "database":    _DB_NAME,
            }
        except Exception as e:
            return {"status": "error", "backend": "PostgreSQL", "error": str(e)}


    # ══════════════════════════════════════════════════════════════════════
    # DUAL-MODE ACCESSORS — read/write either PostgreSQL or JSON files
    # ══════════════════════════════════════════════════════════════════════

    def dual_load(self, json_path, table: str = "", index_cols: tuple = ()) -> list:
        """Load module data from PostgreSQL if migrated, else from JSON file.

        Args:
            json_path: Path to JSON file (the synthetic-mode source of truth)
            table:     PostgreSQL table name (must be in TABLE_USE_DB)
            index_cols: Column names extracted from the `data` JSONB to top-level

        Returns:
            list of dicts. Each dict has all original fields, regardless of mode.

        Falls back to JSON automatically if PG fails — dashboards never break.
        """
        from pathlib import Path as _Path
        import json as _json

        # Try PostgreSQL first if this table is migrated
        if table and self.table_uses_db(table):
            try:
                from psycopg2 import sql as _pg_sql
                _check_table(table)
                rows = self.fetch_all(
                    _pg_sql.SQL("SELECT * FROM {tbl}").format(tbl=_qid(table))
                )
                # Merge top-level columns with the JSONB `data` blob
                result = []
                for row in rows:
                    flat = {}
                    if "data" in row and isinstance(row["data"], dict):
                        flat.update(row["data"])
                    for k, v in row.items():
                        if k != "data" and v is not None:
                            flat[k] = v
                    result.append(flat)
                logger.debug(f"dual_load: {len(result)} rows from {table} (PostgreSQL)")
                return result
            except Exception as e:
                logger.warning(f"dual_load PG failed for {table}, falling back to JSON: {e}")

        # JSON fallback
        p = _Path(json_path) if not hasattr(json_path, "exists") else json_path
        if not p.exists():
            return []
        try:
            data = _json.loads(p.read_text(encoding="utf-8"))
            return data if isinstance(data, list) else []
        except Exception as e:
            logger.error(f"dual_load JSON failed for {p}: {e}")
            return []

    def dual_load_dict(self, json_path, table_map: dict = None) -> dict:
        """Load nested-dict data (like alm_liquidity, esg_climate) from PG or JSON.

        Args:
            json_path: Path to JSON file containing the nested dict
            table_map: dict mapping JSON top-level key → PG table name
                      e.g. {"green_loans":"esg_green_loans", "esg_score":"esg_score_snapshot"}

        Returns:
            dict matching the original JSON structure
        """
        from pathlib import Path as _Path
        import json as _json

        # Try PG first if all tables are migrated
        if table_map and all(self.table_uses_db(t) for t in table_map.values()):
            try:
                from psycopg2 import sql as _pg_sql
                result = {}
                for json_key, table in table_map.items():
                    _check_table(table)
                    if json_key == "esg_score":
                        # singleton dict — fetch latest row
                        row = self.fetch_one(
                            _pg_sql.SQL(
                                "SELECT * FROM {tbl} ORDER BY as_of DESC LIMIT 1"
                            ).format(tbl=_qid(table))
                        )
                        result[json_key] = row or {}
                    else:
                        rows = self.fetch_all(
                            _pg_sql.SQL("SELECT * FROM {tbl}").format(tbl=_qid(table))
                        )
                        result[json_key] = [
                            {**(r.get("data",{}) if isinstance(r.get("data"),dict) else {}),
                             **{k:v for k,v in r.items() if k!="data" and v is not None}}
                            for r in rows
                        ]
                return result
            except Exception as e:
                logger.warning(f"dual_load_dict PG failed, falling back: {e}")

        # JSON fallback
        p = _Path(json_path) if not hasattr(json_path, "exists") else json_path
        if not p.exists():
            return {}
        try:
            return _json.loads(p.read_text(encoding="utf-8"))
        except Exception as e:
            logger.error(f"dual_load_dict JSON failed: {e}")
            return {}

    def dual_save(self, json_path, data: list, table: str = "",
                  pk_col: str = "id", flat_cols: tuple = ()) -> bool:
        """Write module data to PostgreSQL if migrated, ALWAYS to JSON for backup.

        Args:
            json_path: Path to JSON file (always written for emergency restore)
            data:      list of dicts to persist
            table:     PG table name (writes only if table_uses_db is True)
            pk_col:    primary key column for upsert
            flat_cols: column names that are top-level in PG schema (rest goes to JSONB data)

        Returns True if write succeeded.
        """
        from pathlib import Path as _Path
        import json as _json

        # Always write JSON (cheap, gives us emergency restore + audit trail)
        try:
            p = _Path(json_path) if not hasattr(json_path, "write_text") else json_path
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(_json.dumps(data, indent=2, default=str), encoding="utf-8")
        except Exception as e:
            logger.error(f"dual_save JSON failed for {p}: {e}")
            return False

        # If migrated, also write to PostgreSQL
        if table and self.table_uses_db(table):
            try:
                from psycopg2 import sql as _pg_sql
                _check_table(table)
                with self.transaction() as conn:
                    # Truncate-and-insert is the simplest safe pattern for full-table saves
                    self.execute(
                        _pg_sql.SQL("DELETE FROM {tbl}").format(tbl=_qid(table)),
                        conn=conn,
                    )
                    for record in data:
                        if not isinstance(record, dict):
                            continue
                        # Split into flat columns vs JSONB data
                        flat_data = {k: record.get(k) for k in flat_cols if k in record}
                        nested = {k: v for k, v in record.items() if k not in flat_cols}
                        flat_data["data"] = _json.dumps(nested)

                        cols = list(flat_data.keys())
                        vals = list(flat_data.values())
                        sql = _pg_sql.SQL(
                            "INSERT INTO {tbl} ({cols}) VALUES ({vals})"
                        ).format(
                            tbl  = _qid(table),
                            cols = _qcols(cols),
                            vals = _qplaceholders(len(cols)),
                        )
                        try:
                            self.execute(sql, tuple(vals), conn=conn)
                        except Exception as e:
                            logger.warning(f"Row insert skipped in {table}: {e}")
                logger.debug(f"dual_save: {len(data)} rows written to {table} (PostgreSQL)")
            except Exception as e:
                logger.error(f"dual_save PG failed for {table}: {e}")
                # JSON write succeeded so we still return True
                return True

        return True

    # ══════════════════════════════════════════════════════════════════════
    # GENERIC JSON ACCESSORS — for legacy pages without dedicated PG tables
    #
    # These provide the architectural seam (no direct frontend-to-file I/O)
    # while keeping the data in JSON for now. Each can be promoted to a
    # real PG table later by adding it to TABLE_USE_DB.
    # ══════════════════════════════════════════════════════════════════════

    # ── Per-table PG marshallers (Standard #1, v5.30) ──────────────────
    # Each tracked JSON file gets a save/load pair. Add a new pair
    # whenever you add an entry to JSON_PATH_TO_TABLE.
    #
    # Convention: data shape mirrors the table's column structure. The
    # JSON file's top-level keys become PRIMARY KEY values; the rest is
    # serialised into JSONB columns.

    def _save_module_config_to_pg(self, data: dict) -> int:
        """Write the contents of module_config.json to the PG table
        `module_config`. Returns the number of rows upserted.

        Schema (see CREATE TABLE in SCHEMA_SQL):
            module_key      VARCHAR(100) PRIMARY KEY
            hardcoded       JSONB
            configurable    JSONB
            bsc_kpis        JSONB
            dept            VARCHAR(100)
            nav_groups      JSONB
            last_updated    TIMESTAMPTZ DEFAULT now()
            last_updated_by VARCHAR(100)
        """
        if not isinstance(data, dict) or not data:
            return 0
        from psycopg2 import sql as _pg_sql
        n = 0
        with self.transaction() as conn:
            cur = conn.cursor()
            for module_key, payload in data.items():
                if not isinstance(payload, dict):
                    continue
                cur.execute(
                    _pg_sql.SQL(
                        "INSERT INTO {tbl} ("
                        "module_key, hardcoded, configurable, bsc_kpis, "
                        "dept, nav_groups, last_updated_by"
                        ") VALUES (%s, %s, %s, %s, %s, %s, %s) "
                        "ON CONFLICT (module_key) DO UPDATE SET "
                        "hardcoded = EXCLUDED.hardcoded, "
                        "configurable = EXCLUDED.configurable, "
                        "bsc_kpis = EXCLUDED.bsc_kpis, "
                        "dept = EXCLUDED.dept, "
                        "nav_groups = EXCLUDED.nav_groups, "
                        "last_updated = now(), "
                        "last_updated_by = EXCLUDED.last_updated_by"
                    ).format(tbl=_qid("module_config")),
                    (
                        str(module_key)[:100],
                        json.dumps(payload.get("hardcoded", {})),
                        json.dumps(payload.get("configurable", {})),
                        json.dumps(payload.get("bsc_kpis", [])),
                        (payload.get("dept") or "")[:100],
                        json.dumps(payload.get("nav_groups", [])),
                        (payload.get("last_updated_by") or "")[:100],
                    ),
                )
                n += 1
            cur.close()
        return n

    def _load_module_config_from_pg(self) -> dict:
        """Read the `module_config` PG table and reconstruct the JSON shape
        that pages/_admin_module_config.py expects.

        Returns a dict keyed by module_key, with the same nested shape as
        data/module_config.json.
        """
        from psycopg2 import sql as _pg_sql
        out: dict = {}
        with self.connection() as conn:
            cur = conn.cursor()
            cur.execute(
                _pg_sql.SQL(
                    "SELECT module_key, hardcoded, configurable, bsc_kpis, "
                    "dept, nav_groups, last_updated, last_updated_by "
                    "FROM {tbl}"
                ).format(tbl=_qid("module_config"))
            )
            for row in cur.fetchall():
                key, hc, cfg, kpis, dept, navs, ts, by = row
                out[key] = {
                    "hardcoded":       hc   or {},
                    "configurable":    cfg  or {},
                    "bsc_kpis":        kpis or [],
                    "dept":            dept or "",
                    "nav_groups":      navs or [],
                    "last_updated":    ts.isoformat() if ts else None,
                    "last_updated_by": by   or "",
                }
            cur.close()
        return out

    # Lookup table mapping table name → marshaller pair. Used by the
    # dual-mode router below. Add a row for each new pilot.
    _PG_MARSHALLERS = {
        # populated lazily via _get_marshallers (instance methods)
    }

    def _get_marshallers(self, table: str):
        """Return (save_fn, load_fn) for a given tracked table, or None
        if no marshallers are registered for it."""
        registry = {
            "module_config": (self._save_module_config_to_pg,
                              self._load_module_config_from_pg),
        }
        return registry.get(table)

    def load_json(self, path, default=None):
        """Read a JSON file with fallback. Goes through the DB layer for
        consistency — a future migration can promote this to a real PG table
        without changing page code.

        Dual-mode routing (Standard #1, v5.30):
          - If the path corresponds to a tracked table (JSON_PATH_TO_TABLE)
            AND that table has been promoted (TABLE_USE_DB[table] = True)
            AND PostgreSQL is reachable AND a load marshaller is registered,
            read from PostgreSQL instead of the JSON file.
          - On any PG failure, fall back to the JSON file with a warning.
            JSON remains the safety net throughout the migration.

        Args:
            path:    Path to JSON file or filename string
            default: Value to return if file missing (default: [] or {})

        Returns:
            Parsed JSON content (from PG or file, depending on table state),
            or default if neither source has data.
        """
        from pathlib import Path as _Path
        import json as _json

        if hasattr(path, "exists"):
            p = path
        else:
            p = _Path(path) if str(path).startswith("/") else _Path(__file__).parent.parent / "data" / str(path)

        # ── Dual-mode read path ────────────────────────────────────────
        table = _table_for_path(p)
        if table is not None and self.table_uses_db(table):
            marshallers = self._get_marshallers(table)
            if marshallers is not None:
                _, load_fn = marshallers
                try:
                    return load_fn()
                except Exception as e:
                    logger.warning(
                        f"load_json: PG read for '{table}' failed ({e}); "
                        f"falling back to JSON file {p}"
                    )
                    # fall through to JSON read

        # ── Default: file read ──────────────────────────────────────────
        if not p.exists():
            return default if default is not None else []

        try:
            data = _json.loads(p.read_text(encoding="utf-8"))
            return data
        except Exception as e:
            logger.warning(f"load_json failed for {p}: {e}")
            return default if default is not None else []

    def save_json(self, path, data, indent: int = 2) -> bool:
        """Write data to JSON file. Atomic write where possible.

        Dual-mode routing (Standard #1, v5.30):
          - JSON file is ALWAYS written first. This is the safety net —
            if anything below fails, the file write has already succeeded
            and pages keep working.
          - If the path corresponds to a tracked table (JSON_PATH_TO_TABLE)
            AND PostgreSQL is reachable AND a save marshaller is registered,
            ALSO upsert to PostgreSQL. This is the dual-write phase.
          - If TABLE_USE_DB[table] is False (Phase 1), the PG write is
            best-effort: failures are logged but don't fail the save.
          - If TABLE_USE_DB[table] is True (Phase 2), the PG write
            failing is more serious — but we still don't fail the save,
            because the JSON write already succeeded and operators may
            need to fix PG without losing the change.

        Args:
            path:   Path to JSON file or filename string
            data:   Dict or list to serialise
            indent: JSON indent (default 2)

        Returns True if the JSON write succeeded (PG write status is
        logged but not reflected in the return value during dual-write).
        """
        from pathlib import Path as _Path
        import json as _json
        import tempfile
        import os

        if hasattr(path, "exists"):
            p = path
        else:
            p = _Path(path) if str(path).startswith("/") else _Path(__file__).parent.parent / "data" / str(path)

        # ── Step 1: write the JSON file (the safety net) ────────────────
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            # Atomic write: write to temp, then rename
            tmp_fd, tmp_name = tempfile.mkstemp(suffix=".json", dir=p.parent)
            try:
                with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
                    _json.dump(data, f, indent=indent, default=str, ensure_ascii=False)
                os.replace(tmp_name, p)
            except Exception:
                if os.path.exists(tmp_name):
                    os.remove(tmp_name)
                raise
        except Exception as e:
            logger.error(f"save_json failed for {p}: {e}")
            return False

        # ── Step 2: dual-write to PG (best-effort during Phase 1) ───────
        table = _table_for_path(p)
        if table is not None and self.is_postgres_ready():
            marshallers = self._get_marshallers(table)
            if marshallers is not None:
                save_fn, _ = marshallers
                try:
                    n = save_fn(data)
                    logger.info(
                        f"save_json: dual-write to PG '{table}' OK ({n} rows)"
                    )
                except Exception as e:
                    # Don't fail the overall save — JSON has already been
                    # written and is the source of truth in Phase 1.
                    logger.warning(
                        f"save_json: PG dual-write for '{table}' failed "
                        f"({e}); JSON write at {p} still succeeded"
                    )

        return True

# Singleton instance used by all modules
db = Database()


# ── PostgreSQL schema DDL ─────────────────────────────────────────────────
SCHEMA_SQL = """
-- A2Z Blueprint MIS 360 — PostgreSQL Schema
-- Run once to create all tables. Use Alembic for ongoing migrations.
-- Generated: 2026-04. Conforms to CBK ICT Guideline data requirements.

-- ── Extensions ────────────────────────────────────────────────────────────
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS pgcrypto;


-- ──────────────────────────────────────────────────────────────────────────
-- v5.9 — SCHEMA SEGREGATION (per master prompt requirement)
--
-- Schemas group related tables for security (RLS per schema), backup strategy
-- (back up `audit` schema separately for regulatory retention), and access
-- control (different roles see different schemas).
--
-- Migration approach: NEW tables go to dedicated schemas immediately.
-- Existing tables stay in `public` for now — moved table-by-table in v5.10
-- using ALTER TABLE ... SET SCHEMA. Zero-downtime.
-- ──────────────────────────────────────────────────────────────────────────

CREATE SCHEMA IF NOT EXISTS auth;
COMMENT ON SCHEMA auth IS 'Authentication, sessions, users, RBAC. CBK ICT Guideline scope.';

CREATE SCHEMA IF NOT EXISTS performance;
COMMENT ON SCHEMA performance IS 'BSC scores, KPIs, targets, role library, cascade.';

CREATE SCHEMA IF NOT EXISTS credit;
COMMENT ON SCHEMA credit IS 'Loan applications, monitoring, recovery, watchlist, EWS, RCSA.';

CREATE SCHEMA IF NOT EXISTS finance;
COMMENT ON SCHEMA finance IS 'Capital, liquidity, ALM, treasury, accounting, regulatory returns.';

CREATE SCHEMA IF NOT EXISTS risk;
COMMENT ON SCHEMA risk IS 'AML, sanctions, op risk, fraud, compliance cases, climate risk.';

CREATE SCHEMA IF NOT EXISTS staging;
COMMENT ON SCHEMA staging IS 'FLEXCUBE raw extracts. Validated and promoted to mart schemas nightly.';

CREATE SCHEMA IF NOT EXISTS audit;
COMMENT ON SCHEMA audit IS 'Append-only audit trails. 7-year retention per CBK. Backed up separately.';

-- Grant usage to the application role (idempotent)
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'a2z_app') THEN
    EXECUTE 'GRANT USAGE ON SCHEMA auth, performance, credit, finance, risk, staging, audit TO a2z_app';
    EXECUTE 'GRANT CREATE ON SCHEMA auth, performance, credit, finance, risk, staging, audit TO a2z_app';
  END IF;
END $$;

-- Set search path so unqualified table names still resolve (for backward compat)
-- Application code should still qualify as `staging.flexcube_accounts`, etc.

-- ── Audit trail (append-only, never DELETE) ────────────────────────────────
CREATE TABLE IF NOT EXISTS audit_trail (
    id            BIGSERIAL PRIMARY KEY,
    ts            TIMESTAMPTZ NOT NULL DEFAULT now(),
    username      VARCHAR(100) NOT NULL,
    action        VARCHAR(200) NOT NULL,
    detail        TEXT,
    module        VARCHAR(100),
    before_val    TEXT,
    after_val     TEXT,
    ip_address    INET,
    session_id    UUID
);
CREATE INDEX IF NOT EXISTS idx_audit_ts       ON audit_trail (ts DESC);
CREATE INDEX IF NOT EXISTS idx_audit_username ON audit_trail (username);
-- Prevent any DELETE or UPDATE on audit_trail rows (regulatory requirement)
-- ALTER TABLE audit_trail ENABLE ROW LEVEL SECURITY;
-- CREATE POLICY audit_insert_only ON audit_trail FOR INSERT WITH CHECK (true);

-- ── Users ──────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS users (
    username            VARCHAR(100) PRIMARY KEY,
    password_hash       VARCHAR(255) NOT NULL,   -- bcrypt, work factor 12
    full_name           VARCHAR(200),
    email               VARCHAR(200),
    role                VARCHAR(200),
    department          VARCHAR(200),
    unit                VARCHAR(200),
    staff_code          VARCHAR(50),
    active              BOOLEAN NOT NULL DEFAULT true,
    is_admin            BOOLEAN NOT NULL DEFAULT false,
    can_view_all        BOOLEAN NOT NULL DEFAULT false,
    is_dept_super_user  BOOLEAN NOT NULL DEFAULT false,
    dept_super_user_for VARCHAR(200),
    is_ict_admin        BOOLEAN NOT NULL DEFAULT false,
    must_change_password BOOLEAN NOT NULL DEFAULT false,
    login_attempts      INT NOT NULL DEFAULT 0,
    locked_until        TIMESTAMPTZ,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_login          TIMESTAMPTZ,
    metadata            JSONB DEFAULT '{}'
);
-- Row-level security: users can only see their own record unless admin
ALTER TABLE users ENABLE ROW LEVEL SECURITY;
CREATE POLICY users_self   ON users FOR SELECT USING (username = current_user OR current_setting('app.is_admin', true)::boolean);
CREATE POLICY users_admin  ON users FOR ALL    USING (current_setting('app.is_admin', true)::boolean);

-- ── BSC Scores ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS bsc_scores (
    id              BIGSERIAL PRIMARY KEY,
    username        VARCHAR(100) NOT NULL REFERENCES users(username),
    staff_code      VARCHAR(50),
    period          VARCHAR(20) NOT NULL,   -- e.g. "Feb 2026"
    final_score     NUMERIC(4,2),
    pillar_scores   JSONB,                  -- {"Financial": 3.8, "Customer Focus": 3.6, ...}
    kpi_scores      JSONB,                  -- {"K001": {"score": 4.0, "achievement_pct": 80}, ...}
    n_kpis          INT,
    avg_ach         NUMERIC(5,1),
    role            VARCHAR(200),
    unit            VARCHAR(200),
    dept            VARCHAR(200),
    computed_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (username, period)
);
CREATE INDEX IF NOT EXISTS idx_bsc_period ON bsc_scores (period);
CREATE INDEX IF NOT EXISTS idx_bsc_dept   ON bsc_scores (dept);

-- ── Pipeline deals ─────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS pipeline_deals (
    id                  VARCHAR(50) PRIMARY KEY,
    staff_code          VARCHAR(50),
    staff_name          VARCHAR(200),
    unit                VARCHAR(200),
    role                VARCHAR(200),
    client_name         VARCHAR(300),
    client_cif          VARCHAR(50),
    product             VARCHAR(200),
    stage               VARCHAR(100),
    deal_category       VARCHAR(50) DEFAULT 'New Facility',
    amount              NUMERIC(18,2),
    currency            CHAR(3) DEFAULT 'KES',
    open_date           DATE,
    expected_close      DATE,
    probability         NUMERIC(5,2),
    is_repeat_borrower  BOOLEAN DEFAULT false,
    existing_facility_id VARCHAR(50),
    repayment_history   VARCHAR(100),
    notes               TEXT,
    last_updated        DATE,
    metadata            JSONB DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_pipeline_stage   ON pipeline_deals (stage);
CREATE INDEX IF NOT EXISTS idx_pipeline_staff   ON pipeline_deals (staff_code);
CREATE INDEX IF NOT EXISTS idx_pipeline_client  ON pipeline_deals (client_cif);

-- ── Loan applications ──────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS loan_applications (
    id                  VARCHAR(50) PRIMARY KEY,
    pipeline_deal_id    VARCHAR(50),
    client_name         VARCHAR(300),
    client_cif          VARCHAR(50),
    product             VARCHAR(200),
    amount              NUMERIC(18,2),
    currency            CHAR(3) DEFAULT 'KES',
    swim_lane           VARCHAR(50),
    status              VARCHAR(50),
    deal_category       VARCHAR(50) DEFAULT 'New Facility',
    application_date    DATE,
    rm_code             VARCHAR(50),
    rm_name             VARCHAR(200),
    rm_unit             VARCHAR(200),
    analyst             VARCHAR(200),
    is_repeat_borrower  BOOLEAN DEFAULT false,
    completeness_score  NUMERIC(5,1),
    compliance_flag     BOOLEAN DEFAULT false,
    tat_days            INT,
    sla_target_days     INT,
    last_updated        TIMESTAMPTZ DEFAULT now(),
    metadata            JSONB DEFAULT '{}'
);

-- ── Disciplinary register (row-level security) ────────────────────────────
CREATE TABLE IF NOT EXISTS disciplinary (
    id              VARCHAR(50) PRIMARY KEY,
    staff_code      VARCHAR(50),
    staff_name      VARCHAR(200),
    department      VARCHAR(200),
    offence_category VARCHAR(100),
    offence_date    DATE,
    hearing_date    DATE,
    outcome         VARCHAR(100),
    sanction        VARCHAR(100),
    appeal_filed    BOOLEAN DEFAULT false,
    appeal_outcome  VARCHAR(100),
    hr_manager      VARCHAR(100),
    status          VARCHAR(50),
    confidential    BOOLEAN DEFAULT true,
    notes           TEXT,
    created_date    DATE,
    created_by      VARCHAR(100),
    metadata        JSONB DEFAULT '{}'
);
-- RLS: only HR team and admins can see disciplinary records
ALTER TABLE disciplinary ENABLE ROW LEVEL SECURITY;
CREATE POLICY disc_hr_only ON disciplinary FOR ALL
    USING (current_setting('app.dept', true) = 'People & HR'
           OR current_setting('app.is_admin', true)::boolean);

-- ── AML Alerts (strict access control) ────────────────────────────────────
CREATE TABLE IF NOT EXISTS aml_alerts (
    id              VARCHAR(50) PRIMARY KEY,
    account_number  VARCHAR(50),
    customer_name   VARCHAR(300),
    transaction_date DATE,
    amount          NUMERIC(18,2),
    transaction_type VARCHAR(100),
    rule_triggered  VARCHAR(200),
    risk_score      INT,
    risk_level      VARCHAR(20),
    status          VARCHAR(50),
    assigned_to     VARCHAR(200),
    str_filed       BOOLEAN DEFAULT false,
    str_reference   VARCHAR(50),
    notes           TEXT,
    created_at      TIMESTAMPTZ DEFAULT now(),
    updated_at      TIMESTAMPTZ DEFAULT now()
);
ALTER TABLE aml_alerts ENABLE ROW LEVEL SECURITY;
CREATE POLICY aml_compliance_only ON aml_alerts FOR ALL
    USING (current_setting('app.dept', true) IN ('Risk & Compliance', 'Internal Audit')
           OR current_setting('app.is_admin', true)::boolean);

-- ── Sessions table ─────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS sessions (
    session_id      UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    username        VARCHAR(100) NOT NULL REFERENCES users(username),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at      TIMESTAMPTZ NOT NULL,
    last_activity   TIMESTAMPTZ NOT NULL DEFAULT now(),
    ip_address      INET,
    user_agent      TEXT,
    invalidated     BOOLEAN NOT NULL DEFAULT false
);
CREATE INDEX IF NOT EXISTS idx_sessions_username ON sessions (username);
CREATE INDEX IF NOT EXISTS idx_sessions_expires  ON sessions (expires_at);

-- Auto-expire sessions older than 12 hours (run as a cron job)
-- DELETE FROM sessions WHERE expires_at < now() OR invalidated = true;


-- ──────────────────────────────────────────────────────────────────────────
-- v5.9 — STAGING TABLES (FLEXCUBE raw extracts)
--
-- These mirror FLEXCUBE source structures with permissive types.
-- ETL pipeline writes here first, then validates, then promotes to mart.
-- Data residency: Kenya. Retention: 30 days raw, then archived.
-- ──────────────────────────────────────────────────────────────────────────

-- ── Staging: FLEXCUBE customer extract ────────────────────────────────────
CREATE TABLE IF NOT EXISTS staging.flexcube_customers (
    extract_id           BIGSERIAL PRIMARY KEY,
    extract_ts           TIMESTAMPTZ NOT NULL DEFAULT now(),
    batch_id             VARCHAR(50) NOT NULL,
    source_system        VARCHAR(20) NOT NULL DEFAULT 'FLEXCUBE',
    -- FLEXCUBE columns (all VARCHAR for forgiving ingest)
    customer_id          VARCHAR(50),
    customer_name        VARCHAR(300),
    customer_type        VARCHAR(20),
    branch_code          VARCHAR(10),
    rm_code              VARCHAR(50),
    kyc_status           VARCHAR(20),
    risk_rating          VARCHAR(20),
    country              VARCHAR(10),
    id_number            VARCHAR(50),
    phone                VARCHAR(50),
    email                VARCHAR(200),
    customer_since       VARCHAR(50),  -- raw date from FLEXCUBE, parsed during validation
    -- ETL control
    validation_status    VARCHAR(20) DEFAULT 'PENDING',  -- PENDING / VALID / INVALID / PROMOTED
    validation_errors    JSONB DEFAULT '[]',
    promoted_to_mart_at  TIMESTAMPTZ,
    raw_payload          JSONB DEFAULT '{}'  -- full FLEXCUBE record for debugging
);
CREATE INDEX IF NOT EXISTS idx_stg_cust_batch  ON staging.flexcube_customers (batch_id);
CREATE INDEX IF NOT EXISTS idx_stg_cust_status ON staging.flexcube_customers (validation_status);
CREATE INDEX IF NOT EXISTS idx_stg_cust_ts     ON staging.flexcube_customers (extract_ts DESC);

-- ── Staging: FLEXCUBE accounts ────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS staging.flexcube_accounts (
    extract_id           BIGSERIAL PRIMARY KEY,
    extract_ts           TIMESTAMPTZ NOT NULL DEFAULT now(),
    batch_id             VARCHAR(50) NOT NULL,
    source_system        VARCHAR(20) NOT NULL DEFAULT 'FLEXCUBE',
    -- FLEXCUBE columns
    account_no           VARCHAR(50),
    customer_id          VARCHAR(50),
    branch_code          VARCHAR(10),
    product_code         VARCHAR(20),
    currency             VARCHAR(5),
    available_balance    VARCHAR(50),  -- numeric as string from FLEXCUBE
    ledger_balance       VARCHAR(50),
    blocked_amount       VARCHAR(50),
    account_status       VARCHAR(20),
    opened_date          VARCHAR(50),
    closed_date          VARCHAR(50),
    -- ETL control
    validation_status    VARCHAR(20) DEFAULT 'PENDING',
    validation_errors    JSONB DEFAULT '[]',
    promoted_to_mart_at  TIMESTAMPTZ,
    raw_payload          JSONB DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_stg_acct_batch  ON staging.flexcube_accounts (batch_id);
CREATE INDEX IF NOT EXISTS idx_stg_acct_status ON staging.flexcube_accounts (validation_status);

-- ── Staging: FLEXCUBE loans ───────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS staging.flexcube_loans (
    extract_id           BIGSERIAL PRIMARY KEY,
    extract_ts           TIMESTAMPTZ NOT NULL DEFAULT now(),
    batch_id             VARCHAR(50) NOT NULL,
    source_system        VARCHAR(20) NOT NULL DEFAULT 'FLEXCUBE',
    loan_id              VARCHAR(50),
    customer_id          VARCHAR(50),
    branch_code          VARCHAR(10),
    product_code         VARCHAR(20),
    principal_amount     VARCHAR(50),
    outstanding_amount   VARCHAR(50),
    interest_rate        VARCHAR(20),
    tenor_months         VARCHAR(10),
    disbursement_date    VARCHAR(50),
    maturity_date        VARCHAR(50),
    next_emi_date        VARCHAR(50),
    classification       VARCHAR(20),
    dpd                  VARCHAR(10),
    npl_flag             VARCHAR(5),
    rm_code              VARCHAR(50),
    -- ETL control
    validation_status    VARCHAR(20) DEFAULT 'PENDING',
    validation_errors    JSONB DEFAULT '[]',
    promoted_to_mart_at  TIMESTAMPTZ,
    raw_payload          JSONB DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_stg_loan_batch  ON staging.flexcube_loans (batch_id);
CREATE INDEX IF NOT EXISTS idx_stg_loan_status ON staging.flexcube_loans (validation_status);

-- ── Staging: FLEXCUBE transactions (daily) ─────────────────────────────
CREATE TABLE IF NOT EXISTS staging.flexcube_transactions (
    extract_id           BIGSERIAL PRIMARY KEY,
    extract_ts           TIMESTAMPTZ NOT NULL DEFAULT now(),
    batch_id             VARCHAR(50) NOT NULL,
    source_system        VARCHAR(20) NOT NULL DEFAULT 'FLEXCUBE',
    transaction_id       VARCHAR(50),
    account_no           VARCHAR(50),
    transaction_date     VARCHAR(50),
    value_date           VARCHAR(50),
    transaction_type     VARCHAR(20),
    debit_credit         VARCHAR(5),
    amount               VARCHAR(50),
    currency             VARCHAR(5),
    description          TEXT,
    channel              VARCHAR(20),
    reference            VARCHAR(100),
    posted_by            VARCHAR(50),
    -- ETL control
    validation_status    VARCHAR(20) DEFAULT 'PENDING',
    validation_errors    JSONB DEFAULT '[]',
    promoted_to_mart_at  TIMESTAMPTZ,
    raw_payload          JSONB DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_stg_txn_batch ON staging.flexcube_transactions (batch_id);
CREATE INDEX IF NOT EXISTS idx_stg_txn_date  ON staging.flexcube_transactions (transaction_date);
CREATE INDEX IF NOT EXISTS idx_stg_txn_acct  ON staging.flexcube_transactions (account_no);

-- ── Staging: FLEXCUBE GL balances (financial reporting) ────────────────
CREATE TABLE IF NOT EXISTS staging.flexcube_gl_balances (
    extract_id           BIGSERIAL PRIMARY KEY,
    extract_ts           TIMESTAMPTZ NOT NULL DEFAULT now(),
    batch_id             VARCHAR(50) NOT NULL,
    source_system        VARCHAR(20) NOT NULL DEFAULT 'FLEXCUBE',
    gl_code              VARCHAR(20),
    gl_description       TEXT,
    branch_code          VARCHAR(10),
    currency             VARCHAR(5),
    debit_balance        VARCHAR(50),
    credit_balance       VARCHAR(50),
    net_balance          VARCHAR(50),
    balance_date         VARCHAR(50),
    -- ETL control
    validation_status    VARCHAR(20) DEFAULT 'PENDING',
    validation_errors    JSONB DEFAULT '[]',
    promoted_to_mart_at  TIMESTAMPTZ,
    raw_payload          JSONB DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_stg_gl_batch ON staging.flexcube_gl_balances (batch_id);
CREATE INDEX IF NOT EXISTS idx_stg_gl_date  ON staging.flexcube_gl_balances (balance_date);

-- ── Staging: ETL batch register (one row per ETL run) ──────────────────
CREATE TABLE IF NOT EXISTS staging.etl_batch_register (
    batch_id             VARCHAR(50) PRIMARY KEY,
    extract_started      TIMESTAMPTZ NOT NULL DEFAULT now(),
    extract_completed    TIMESTAMPTZ,
    source_system        VARCHAR(20) NOT NULL,
    extract_type         VARCHAR(50),  -- "FULL" / "INCREMENTAL" / "REPLAY"
    record_count         INT DEFAULT 0,
    valid_count          INT DEFAULT 0,
    invalid_count        INT DEFAULT 0,
    promoted_count       INT DEFAULT 0,
    status               VARCHAR(20) DEFAULT 'RUNNING',  -- RUNNING / COMPLETED / FAILED / PARTIAL
    error_message        TEXT,
    triggered_by         VARCHAR(100),
    metadata             JSONB DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_stg_batch_started ON staging.etl_batch_register (extract_started DESC);
CREATE INDEX IF NOT EXISTS idx_stg_batch_status  ON staging.etl_batch_register (status);

-- ──────────────────────────────────────────────────────────────────────────
-- v5.8 — NEW MODULE TABLES (Phase 1, Phase 2, Phase 3 + FLEXCUBE)
-- All tables use the "JSONB-flexible" pattern:
--   id (PK), a few indexed query columns, and `data` JSONB for everything else.
-- This keeps schema migrations minimal as fields evolve.
-- ──────────────────────────────────────────────────────────────────────────

-- ── CBK Returns Centre (Phase 1) ──────────────────────────────────────────
CREATE TABLE IF NOT EXISTS cbk_returns (
    id              VARCHAR(50) PRIMARY KEY,
    return_code     VARCHAR(20),
    return_name     VARCHAR(200),
    frequency       VARCHAR(20),
    period          VARCHAR(10),
    due_date        DATE,
    submitted       BOOLEAN DEFAULT false,
    on_time         BOOLEAN,
    status          VARCHAR(20),
    department      VARCHAR(100),
    data            JSONB DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_cbk_due_date    ON cbk_returns (due_date);
CREATE INDEX IF NOT EXISTS idx_cbk_status      ON cbk_returns (status);
CREATE INDEX IF NOT EXISTS idx_cbk_dept        ON cbk_returns (department);

-- ── Data Protection Office (Phase 1) ──────────────────────────────────────
CREATE TABLE IF NOT EXISTS dpo_register (
    id              VARCHAR(50) PRIMARY KEY,
    type            VARCHAR(20),                -- DPIA | Breach | ROPA
    subject         VARCHAR(300),
    risk_level      VARCHAR(20),
    status          VARCHAR(50),
    started_date    DATE,
    due_date        DATE,
    completed_date  DATE,
    department      VARCHAR(100),
    data            JSONB DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_dpo_type        ON dpo_register (type);
CREATE INDEX IF NOT EXISTS idx_dpo_status      ON dpo_register (status);
ALTER TABLE dpo_register ENABLE ROW LEVEL SECURITY;
CREATE POLICY dpo_compliance_only ON dpo_register FOR ALL
    USING (current_setting('app.dept', true) IN ('Compliance','Legal','Risk & Compliance')
           OR current_setting('app.is_admin', true)::boolean);

-- ── Sanctions Screening (Phase 1) ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS sanctions_register (
    id                   VARCHAR(50) PRIMARY KEY,
    screening_date       DATE,
    customer_cif         VARCHAR(50),
    customer_name        VARCHAR(300),
    list_matched         VARCHAR(50),
    match_score          INT,
    status               VARCHAR(50),
    transaction_blocked  BOOLEAN DEFAULT false,
    filed_with_cbk       BOOLEAN DEFAULT false,
    data                 JSONB DEFAULT '{}',
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_sanc_date       ON sanctions_register (screening_date);
CREATE INDEX IF NOT EXISTS idx_sanc_cif        ON sanctions_register (customer_cif);
CREATE INDEX IF NOT EXISTS idx_sanc_score      ON sanctions_register (match_score);
ALTER TABLE sanctions_register ENABLE ROW LEVEL SECURITY;
CREATE POLICY sanc_compliance_only ON sanctions_register FOR ALL
    USING (current_setting('app.dept', true) IN ('Compliance','Risk & Compliance')
           OR current_setting('app.is_admin', true)::boolean);

-- ── Regulatory Capital & Liquidity (Phase 1) ──────────────────────────────
CREATE TABLE IF NOT EXISTS capital_liquidity_metrics (
    id                       VARCHAR(50) PRIMARY KEY,
    metric_date              DATE NOT NULL,
    tier1_ratio_pct          NUMERIC(6,2),
    total_capital_ratio_pct  NUMERIC(6,2),
    leverage_ratio_pct       NUMERIC(6,2),
    lcr_pct                  NUMERIC(6,1),
    nsfr_pct                 NUMERIC(6,1),
    all_compliant            BOOLEAN DEFAULT true,
    data                     JSONB DEFAULT '{}',
    created_at               TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_cap_date        ON capital_liquidity_metrics (metric_date DESC);

-- ── Customer Onboarding (Phase 2) ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS customer_onboarding (
    id                  VARCHAR(50) PRIMARY KEY,
    customer_name       VARCHAR(300),
    phone               VARCHAR(50),
    channel             VARCHAR(50),
    product             VARCHAR(100),
    started_date        DATE,
    completed_date      DATE,
    current_stage       VARCHAR(50),
    stages_completed    INT,
    abandoned           BOOLEAN DEFAULT false,
    rm_assigned         VARCHAR(50),
    branch_assigned     VARCHAR(100),
    data                JSONB DEFAULT '{}',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_ob_started      ON customer_onboarding (started_date);
CREATE INDEX IF NOT EXISTS idx_ob_stage        ON customer_onboarding (current_stage);
CREATE INDEX IF NOT EXISTS idx_ob_rm           ON customer_onboarding (rm_assigned);

-- ── Card Management (Phase 2) ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS card_management (
    id                  VARCHAR(50) PRIMARY KEY,
    card_number_masked  VARCHAR(20),
    customer_cif        VARCHAR(50),
    customer_name       VARCHAR(300),
    card_type           VARCHAR(50),
    issue_date          DATE,
    expiry_date         DATE,
    status              VARCHAR(20),
    ytd_spend_kes       NUMERIC(18,2),
    has_dispute         BOOLEAN DEFAULT false,
    fraud_flagged       BOOLEAN DEFAULT false,
    branch              VARCHAR(100),
    rm_code             VARCHAR(50),
    data                JSONB DEFAULT '{}',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_card_cif        ON card_management (customer_cif);
CREATE INDEX IF NOT EXISTS idx_card_status     ON card_management (status);
CREATE INDEX IF NOT EXISTS idx_card_disputes   ON card_management (has_dispute) WHERE has_dispute = true;

-- ── Merchant Acquiring (Phase 2) ──────────────────────────────────────────
CREATE TABLE IF NOT EXISTS merchant_acquiring (
    id               VARCHAR(50) PRIMARY KEY,
    merchant_name    VARCHAR(300),
    merchant_type    VARCHAR(50),
    kra_pin          VARCHAR(50),
    onboarding_date  DATE,
    status           VARCHAR(20),
    active           BOOLEAN DEFAULT false,
    pos_terminals    INT,
    active_terminals INT,
    ytd_revenue_kes  NUMERIC(18,2),
    branch           VARCHAR(100),
    rm_code          VARCHAR(50),
    category         VARCHAR(50),
    data             JSONB DEFAULT '{}',
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_mer_active      ON merchant_acquiring (active) WHERE active = true;
CREATE INDEX IF NOT EXISTS idx_mer_branch      ON merchant_acquiring (branch);

-- ── ALM Liquidity (Phase 2) — multi-table ────────────────────────────────
CREATE TABLE IF NOT EXISTS alm_gap_analysis (
    id                  VARCHAR(50) PRIMARY KEY,
    metric_date         DATE,
    tenor_bucket        VARCHAR(20),
    assets_kes          NUMERIC(20,2),
    liabilities_kes     NUMERIC(20,2),
    gap_kes             NUMERIC(20,2),
    cumulative_gap_kes  NUMERIC(20,2),
    data                JSONB DEFAULT '{}',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_alm_date        ON alm_gap_analysis (metric_date DESC);

CREATE TABLE IF NOT EXISTS alm_funding_sources (
    source              VARCHAR(100) PRIMARY KEY,
    amount_kes_b        NUMERIC(12,2),
    concentration_pct   NUMERIC(5,1),
    tenor_avg_days      INT,
    rate_pct            NUMERIC(5,2),
    as_of               DATE,
    data                JSONB DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS alm_alco_meetings (
    id              VARCHAR(50) PRIMARY KEY,
    meeting_date    DATE,
    agenda_items    INT,
    decisions_taken INT,
    action_items    INT,
    actions_closed  INT,
    attendance_pct  NUMERIC(5,1),
    data            JSONB DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS alm_contingency_plans (
    id           VARCHAR(50) PRIMARY KEY,
    trigger      TEXT,
    action       TEXT,
    tested_date  DATE,
    test_result  VARCHAR(50),
    data         JSONB DEFAULT '{}'
);

-- ── Operational Risk Losses (Phase 2) ─────────────────────────────────────
CREATE TABLE IF NOT EXISTS op_risk_losses (
    id                    VARCHAR(50) PRIMARY KEY,
    event_date            DATE,
    discovered_date       DATE,
    category              VARCHAR(100),
    type                  VARCHAR(50),
    description           TEXT,
    gross_loss_kes        NUMERIC(18,2),
    recovered_kes         NUMERIC(18,2),
    net_loss_kes          NUMERIC(18,2),
    department            VARCHAR(100),
    branch                VARCHAR(100),
    status                VARCHAR(50),
    regulatory_reportable BOOLEAN DEFAULT false,
    data                  JSONB DEFAULT '{}',
    created_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at            TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_op_event_date   ON op_risk_losses (event_date DESC);
CREATE INDEX IF NOT EXISTS idx_op_category     ON op_risk_losses (category);
CREATE INDEX IF NOT EXISTS idx_op_dept         ON op_risk_losses (department);

-- ── Strategic Initiatives (Phase 3) ───────────────────────────────────────
CREATE TABLE IF NOT EXISTS strategic_initiatives (
    id                VARCHAR(50) PRIMARY KEY,
    name              VARCHAR(300),
    pillar            VARCHAR(100),
    sponsor           VARCHAR(100),
    owner             VARCHAR(100),
    owner_username    VARCHAR(100),
    start_date        DATE,
    target_end_date   DATE,
    actual_end_date   DATE,
    completion_pct    INT,
    status            VARCHAR(50),
    rag_status        VARCHAR(20),
    budget_kes_m      NUMERIC(10,1),
    spent_kes_m       NUMERIC(10,1),
    department        VARCHAR(100),
    data              JSONB DEFAULT '{}',
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_strat_pillar    ON strategic_initiatives (pillar);
CREATE INDEX IF NOT EXISTS idx_strat_rag       ON strategic_initiatives (rag_status);
CREATE INDEX IF NOT EXISTS idx_strat_owner     ON strategic_initiatives (owner_username);

-- ── Board Pack & Papers (Phase 3) ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS board_papers (
    id                  VARCHAR(50) PRIMARY KEY,
    title               VARCHAR(300),
    type                VARCHAR(50),
    committee           VARCHAR(100),
    meeting_date        DATE,
    submission_deadline DATE,
    submitted_date      DATE,
    submitted_on_time   BOOLEAN,
    submitted_by        VARCHAR(100),
    status              VARCHAR(50),
    action_items        INT,
    actions_closed      INT,
    department          VARCHAR(100),
    data                JSONB DEFAULT '{}',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_board_committee ON board_papers (committee);
CREATE INDEX IF NOT EXISTS idx_board_meeting   ON board_papers (meeting_date DESC);

-- ── ESG & Climate (Phase 3) — multi-table ─────────────────────────────────
CREATE TABLE IF NOT EXISTS esg_green_loans (
    id                       VARCHAR(50) PRIMARY KEY,
    customer                 VARCHAR(300),
    sector                   VARCHAR(100),
    amount_kes_m             NUMERIC(10,1),
    tenor_years              INT,
    interest_rate            NUMERIC(5,2),
    carbon_offset_tons_yr    INT,
    status                   VARCHAR(50),
    verified                 BOOLEAN DEFAULT false,
    esg_score                NUMERIC(5,1),
    data                     JSONB DEFAULT '{}',
    created_at               TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_esg_sector      ON esg_green_loans (sector);

CREATE TABLE IF NOT EXISTS esg_initiatives (
    id              VARCHAR(50) PRIMARY KEY,
    name            VARCHAR(300),
    category        VARCHAR(50),
    budget_kes_m    NUMERIC(10,1),
    spent_kes_m     NUMERIC(10,1),
    beneficiaries   INT,
    completion_pct  INT,
    department      VARCHAR(100),
    data            JSONB DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS esg_climate_assessments (
    id                  VARCHAR(50) PRIMARY KEY,
    risk_type           VARCHAR(100),
    portfolio_segment   VARCHAR(100),
    exposure_kes_b      NUMERIC(10,2),
    risk_score          NUMERIC(5,1),
    completed           BOOLEAN DEFAULT false,
    cbk_reportable      BOOLEAN DEFAULT false,
    data                JSONB DEFAULT '{}',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS esg_score_snapshot (
    as_of           DATE PRIMARY KEY,
    overall         NUMERIC(5,1),
    environmental   NUMERIC(5,1),
    social          NUMERIC(5,1),
    governance      NUMERIC(5,1),
    rated_by        VARCHAR(100),
    previous        NUMERIC(5,1),
    trend           VARCHAR(20),
    data            JSONB DEFAULT '{}'
);

-- ── FLEXCUBE Integration ──────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS flexcube_events (
    id           BIGSERIAL PRIMARY KEY,
    timestamp    TIMESTAMPTZ NOT NULL DEFAULT now(),
    topic        VARCHAR(200),
    payload      JSONB DEFAULT '{}',
    mode         VARCHAR(20)
);
CREATE INDEX IF NOT EXISTS idx_flx_ts          ON flexcube_events (timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_flx_topic       ON flexcube_events (topic);

CREATE TABLE IF NOT EXISTS flexcube_config (
    id           VARCHAR(50) PRIMARY KEY DEFAULT 'singleton',
    mode         VARCHAR(20) DEFAULT 'synthetic',
    config_json  JSONB NOT NULL DEFAULT '{}',
    last_updated TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_by   VARCHAR(100)
);

-- ── Module configuration (centralised, governs all 19 modules) ────────────
CREATE TABLE IF NOT EXISTS module_config (
    module_key      VARCHAR(100) PRIMARY KEY,
    hardcoded       JSONB NOT NULL DEFAULT '{}',
    configurable    JSONB NOT NULL DEFAULT '{}',
    bsc_kpis        JSONB DEFAULT '[]',
    dept            VARCHAR(100),
    nav_groups      JSONB DEFAULT '[]',
    last_updated    TIMESTAMPTZ DEFAULT now(),
    last_updated_by VARCHAR(100)
);


-- ──────────────────────────────────────────────────────────────────────────
-- v5.9 — RECONCILIATION FRAMEWORK
--
-- Daily checks: A2Z numbers vs FLEXCUBE numbers (deposits, loans, fees, NPL%).
-- Breaks (mismatches > tolerance) trigger alerts to Finance.
-- 30-day clean run = signal to deprecate JSON cache.
--
-- Lives in `audit` schema for tamper-proof retention (CBK 7-year requirement).
-- ──────────────────────────────────────────────────────────────────────────

-- ── Reconciliation runs (one row per check execution) ──────────────────
CREATE TABLE IF NOT EXISTS audit.recon_runs (
    run_id               BIGSERIAL PRIMARY KEY,
    run_ts               TIMESTAMPTZ NOT NULL DEFAULT now(),
    check_name           VARCHAR(100) NOT NULL,
    check_category       VARCHAR(50),  -- DEPOSITS / LOANS / FEES / NPL / CAPITAL / GENERIC
    a2z_value            NUMERIC(20,2),
    flexcube_value       NUMERIC(20,2),
    variance             NUMERIC(20,2),
    variance_pct         NUMERIC(10,4),
    tolerance_kes        NUMERIC(20,2),
    tolerance_pct        NUMERIC(10,4),
    status               VARCHAR(20),  -- MATCH / BREAK / WARN
    duration_ms          INT,
    triggered_by         VARCHAR(100),  -- "scheduled" or username
    notes                TEXT,
    metadata             JSONB DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_recon_ts     ON audit.recon_runs (run_ts DESC);
CREATE INDEX IF NOT EXISTS idx_recon_status ON audit.recon_runs (status);
CREATE INDEX IF NOT EXISTS idx_recon_check  ON audit.recon_runs (check_name);

-- ── Reconciliation breaks (only entries where status = BREAK) ──────────
CREATE TABLE IF NOT EXISTS audit.recon_breaks (
    break_id             BIGSERIAL PRIMARY KEY,
    run_id               BIGINT REFERENCES audit.recon_runs(run_id),
    break_ts             TIMESTAMPTZ NOT NULL DEFAULT now(),
    check_name           VARCHAR(100) NOT NULL,
    check_category       VARCHAR(50),
    a2z_value            NUMERIC(20,2),
    flexcube_value       NUMERIC(20,2),
    variance             NUMERIC(20,2),
    variance_pct         NUMERIC(10,4),
    severity             VARCHAR(20),  -- CRITICAL / HIGH / MEDIUM / LOW
    status               VARCHAR(20) DEFAULT 'OPEN',  -- OPEN / INVESTIGATING / RESOLVED / WAIVED
    assigned_to          VARCHAR(100),
    resolution           TEXT,
    resolved_ts          TIMESTAMPTZ,
    resolved_by          VARCHAR(100),
    metadata             JSONB DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_break_open ON audit.recon_breaks (status) WHERE status = 'OPEN';
CREATE INDEX IF NOT EXISTS idx_break_ts   ON audit.recon_breaks (break_ts DESC);

-- Recon results are append-only (no UPDATE/DELETE on recon_runs)
-- audit.recon_breaks allows status updates as breaks get investigated/resolved

"""


def get_schema_sql() -> str:
    """Returns the full PostgreSQL DDL schema for A2Z Blueprint."""
    return SCHEMA_SQL


def migrate_json_to_db(table: str, json_data: list, conn=None) -> int:
    """
    Utility: bulk-load a JSON array into a PostgreSQL table.
    Used during migration. Safe to run repeatedly (uses upsert).

    Example:
        import json
        from pathlib import Path
        data = json.loads((Path('data') / 'pipeline.json').read_text())
        n = migrate_json_to_db('pipeline_deals', data)
        print(f"Migrated {n} rows")
    """
    if not db.is_postgres_ready():
        raise RuntimeError("PostgreSQL not available. Set A2Z_USE_DB=true and configure connection.")
    if not json_data:
        return 0

    from psycopg2 import sql as _pg_sql
    _check_table(table)

    inserted = 0
    for record in json_data:
        if not isinstance(record, dict):
            continue
        cols = list(record.keys())
        vals = [json.dumps(v) if isinstance(v, (dict, list)) else v for v in record.values()]
        sql = _pg_sql.SQL(
            "INSERT INTO {tbl} ({cols}) VALUES ({vals}) ON CONFLICT DO NOTHING"
        ).format(
            tbl  = _qid(table),
            cols = _qcols(cols),
            vals = _qplaceholders(len(cols)),
        )
        try:
            db.execute(sql, tuple(vals), conn=conn)
            inserted += 1
        except Exception as e:
            logger.warning(f"Row skipped during migration of {table}: {e}")

    return inserted
