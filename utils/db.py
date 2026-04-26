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
        cols   = list(data.keys())
        vals   = [data[c] for c in cols]
        placeholders = ", ".join(["%s"] * len(cols))
        col_str      = ", ".join(cols)
        update_str   = ", ".join(f"{c} = EXCLUDED.{c}" for c in cols if c != conflict_col)
        sql = (
            f"INSERT INTO {table} ({col_str}) VALUES ({placeholders}) "
            f"ON CONFLICT ({conflict_col}) DO UPDATE SET {update_str}"
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
                rows = self.fetch_all(f"SELECT * FROM {table}")
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
                result = {}
                for json_key, table in table_map.items():
                    if json_key == "esg_score":
                        # singleton dict — fetch latest row
                        row = self.fetch_one(f"SELECT * FROM {table} ORDER BY as_of DESC LIMIT 1")
                        result[json_key] = row or {}
                    else:
                        rows = self.fetch_all(f"SELECT * FROM {table}")
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
                with self.transaction() as conn:
                    # Truncate-and-insert is the simplest safe pattern for full-table saves
                    self.execute(f"DELETE FROM {table}", conn=conn)
                    for record in data:
                        if not isinstance(record, dict):
                            continue
                        # Split into flat columns vs JSONB data
                        flat_data = {k: record.get(k) for k in flat_cols if k in record}
                        nested = {k: v for k, v in record.items() if k not in flat_cols}
                        flat_data["data"] = _json.dumps(nested)

                        cols = list(flat_data.keys())
                        vals = list(flat_data.values())
                        placeholders = ", ".join(["%s"] * len(cols))
                        col_str = ", ".join(f'"{c}"' for c in cols)
                        sql = f"INSERT INTO {table} ({col_str}) VALUES ({placeholders})"
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

    inserted = 0
    for record in json_data:
        if not isinstance(record, dict):
            continue
        cols = list(record.keys())
        vals = [json.dumps(v) if isinstance(v, (dict, list)) else v for v in record.values()]
        placeholders = ", ".join(["%s"] * len(cols))
        col_str      = ", ".join(f'"{c}"' for c in cols)
        sql = f"INSERT INTO {table} ({col_str}) VALUES ({placeholders}) ON CONFLICT DO NOTHING"
        try:
            db.execute(sql, tuple(vals), conn=conn)
            inserted += 1
        except Exception as e:
            logger.warning(f"Row skipped during migration of {table}: {e}")

    return inserted
