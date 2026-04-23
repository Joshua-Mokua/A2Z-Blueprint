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
    "watchlist":        False,
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
    "workforce":        False,
    "disciplinary":     True,
    "projects":         True,
    "initiatives":      False,
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
