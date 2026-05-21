-- create_tables_v10.253.sql — DDL for top-5 high-value tables
-- v10.253 PG Migration Sub-Campaign — Batch 1 of 8
--
-- Purpose: Add CREATE TABLE statements for the 5 highest-value JSON
-- data files identified in v10.251's PG migration audit. After this
-- DDL is applied, v10.254 will add corresponding migrate_*() functions
-- to scripts/migrate_to_postgres.py to load the JSON data into PG.
--
-- All tables include audit columns (created_at, updated_at) for
-- consistency with existing schema. Primary keys match the JSON's
-- unique-identifier fields where present.
--
-- Apply via: psql -d a2z -f create_tables_v10.253.sql
-- Or via the platform's PG bootstrap: utils/db.bootstrap_schema()

-- ─────────────────────────────────────────────────────────────────
-- 1. credit_monitoring (5.3 MB JSON, 5,001 watchlist items)
-- Source: data/credit_monitoring.json (under "watchlist" key)
-- Used by: pages/19_credit_monitoring.py
-- ─────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS credit_watchlist (
    id                  TEXT PRIMARY KEY,
    account_number      TEXT NOT NULL,
    cif                 TEXT NOT NULL,
    branch_code         TEXT,
    branch_name         TEXT,
    region              TEXT,
    rm_code             TEXT,
    rm_name             TEXT,
    -- Risk indicators (full row stored as JSONB for flexibility)
    risk_data           JSONB NOT NULL,
    -- Watchlist status
    status              TEXT,
    severity            TEXT,
    added_date          DATE,
    -- Audit columns
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_cw_branch_code ON credit_watchlist (branch_code);
CREATE INDEX IF NOT EXISTS idx_cw_rm_code     ON credit_watchlist (rm_code);
CREATE INDEX IF NOT EXISTS idx_cw_status      ON credit_watchlist (status);
CREATE INDEX IF NOT EXISTS idx_cw_severity    ON credit_watchlist (severity);

-- ─────────────────────────────────────────────────────────────────
-- 2. target_cascade (4.8 MB JSON, key = "from_code|kpi|period")
-- Source: data/target_cascade.json
-- Used by: pages/12_cascade.py + utils/cascade_engine.py
-- ─────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS target_cascade (
    -- Composite key
    cascade_key         TEXT PRIMARY KEY,  -- "300001|PBT|2026" format
    from_code           TEXT NOT NULL,
    from_name           TEXT,
    kpi                 TEXT NOT NULL,
    period              TEXT NOT NULL,
    -- Target values
    total_target        NUMERIC(20, 2),
    allocated_sum       NUMERIC(20, 2),
    -- Allocations (variable-shape array of dicts)
    allocations         JSONB NOT NULL,
    -- Audit columns
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_tc_from_code ON target_cascade (from_code);
CREATE INDEX IF NOT EXISTS idx_tc_kpi       ON target_cascade (kpi);
CREATE INDEX IF NOT EXISTS idx_tc_period    ON target_cascade (period);

-- ─────────────────────────────────────────────────────────────────
-- 3. training_completions (3.6 MB JSON, 8,679 records)
-- Source: data/training_completions.json (top-level list)
-- Used by: pages/42_lms.py + utils/lms_engine.py
-- ─────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS training_completions (
    id                  TEXT PRIMARY KEY,
    staff_code          TEXT NOT NULL,
    staff_name          TEXT,
    training_id         TEXT NOT NULL,
    training_name       TEXT NOT NULL,
    mandatory           BOOLEAN NOT NULL DEFAULT FALSE,
    hours               NUMERIC(6, 2),
    completed           BOOLEAN NOT NULL DEFAULT FALSE,
    status              TEXT,
    completion_date     DATE,
    -- Full row also stored as JSONB for fields not modelled above
    extra               JSONB,
    -- Audit columns
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_tc_staff_code ON training_completions (staff_code);
CREATE INDEX IF NOT EXISTS idx_tc_completed  ON training_completions (completed);
CREATE INDEX IF NOT EXISTS idx_tc_mandatory  ON training_completions (mandatory);

-- ─────────────────────────────────────────────────────────────────
-- 4. ifrs9_loan_classifications (1.8 MB JSON, 5,045 records)
-- Source: data/ifrs9_loans.json (top-level list)
-- Used by: pages/32_ifrs9.py + utils/ifrs9_engine.py
-- ─────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS ifrs9_loan_classifications (
    account_id          TEXT PRIMARY KEY,
    client_name         TEXT,
    product             TEXT,
    outstanding         NUMERIC(20, 2),
    stage               INTEGER NOT NULL CHECK (stage IN (1, 2, 3)),
    ecl_basis           TEXT,
    npl_days            INTEGER,
    pd_12m              NUMERIC(8, 6),
    lgd                 NUMERIC(8, 6),
    ead                 NUMERIC(20, 2),
    -- Full row JSONB for any additional fields
    extra               JSONB,
    -- Audit columns
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_ifrs9_stage   ON ifrs9_loan_classifications (stage);
CREATE INDEX IF NOT EXISTS idx_ifrs9_product ON ifrs9_loan_classifications (product);

-- ─────────────────────────────────────────────────────────────────
-- 5. customer_intelligence (1.7 MB JSON, key = CIF)
-- Source: data/customer_intelligence.json (dict keyed by CIF)
-- Used by: pages/34_customer360.py + utils/customer_intelligence.py
-- ─────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS customer_intelligence (
    cif                 TEXT PRIMARY KEY,
    segment             TEXT,
    -- Tags (string array)
    tags                JSONB,           -- list of strings
    -- Propensity scores (dict of product → score)
    propensity_scores   JSONB,
    -- Next best action recommendations
    nba                 JSONB,           -- list of dicts
    churn_risk          NUMERIC(6, 4),
    clv_estimate        NUMERIC(20, 2),
    digital_engagement  JSONB,
    -- Full row JSONB for additional fields
    extra               JSONB,
    -- Audit columns
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_ci_segment    ON customer_intelligence (segment);
CREATE INDEX IF NOT EXISTS idx_ci_churn_risk ON customer_intelligence (churn_risk);

-- ─────────────────────────────────────────────────────────────────
-- Summary
-- ─────────────────────────────────────────────────────────────────
-- Tables added:           5 (credit_watchlist, target_cascade,
--                            training_completions,
--                            ifrs9_loan_classifications,
--                            customer_intelligence)
-- Total DDL'd tables:     12 → 17
-- Indexes added:          12
-- Schema strategy:        explicit columns for fields used in WHERE
--                         + JSONB for everything else (flexibility
--                         + minimal schema-evolution risk)
-- v10.254 will add migrate_*() functions for these 5 tables.
