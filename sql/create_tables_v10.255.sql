-- create_tables_v10.255.sql — DDL for next-5 high-value tables
-- v10.255 PG Migration Sub-Campaign — Batch 3 of 8
--
-- Purpose: Add CREATE TABLE statements for the next 5 high-value JSON
-- data files (performance_reviews, growth_plans, edms_documents,
-- customer_onboarding, board_papers). v10.256 will add the matching
-- migrate_*() functions.
--
-- Same hybrid schema strategy as v10.253: explicit columns for
-- WHERE-clause fields + JSONB for variable-shape sub-structures.
--
-- Apply via: psql -d a2z -f create_tables_v10.255.sql

-- ─────────────────────────────────────────────────────────────────
-- 6. performance_reviews (1.2 MB JSON, 2,876 records)
-- Source: data/performance_reviews.json (top-level list)
-- Used by: pages/1_perform.py + utils/performance_review_engine.py
-- ─────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS performance_reviews (
    id                  TEXT PRIMARY KEY,
    reviewee_code       TEXT NOT NULL,
    reviewee_name       TEXT,
    reviewer_code       TEXT,
    reviewer_name       TEXT,
    period              TEXT NOT NULL,
    due_date            DATE,
    submitted_date      DATE,
    submitted_on_time   BOOLEAN,
    status              TEXT,
    -- Full row JSONB for additional fields
    extra               JSONB,
    -- Audit columns
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_pr_reviewee  ON performance_reviews (reviewee_code);
CREATE INDEX IF NOT EXISTS idx_pr_reviewer  ON performance_reviews (reviewer_code);
CREATE INDEX IF NOT EXISTS idx_pr_period    ON performance_reviews (period);
CREATE INDEX IF NOT EXISTS idx_pr_status    ON performance_reviews (status);

-- ─────────────────────────────────────────────────────────────────
-- 7. staff_growth_plans (1.1 MB JSON, dict keyed by staff_code)
-- Source: data/growth_plans.json
-- Used by: pages/43_pip.py + utils/growth_path_engine.py
-- ─────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS staff_growth_plans (
    staff_code          TEXT PRIMARY KEY,
    -- Sub-dicts stored as JSONB
    meta                JSONB,
    promotion_readiness JSONB,
    recommended_actions JSONB,    -- list of action dicts
    skill_gaps          JSONB,    -- list of skill-gap dicts
    -- Audit columns
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ─────────────────────────────────────────────────────────────────
-- 8. edms_documents (~360 KB JSON, 500 records)
-- Source: data/edms_documents.json (top-level list)
-- Used by: pages/31_edms.py + utils/edms_engine.py
-- ─────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS edms_documents (
    id                  TEXT PRIMARY KEY,
    category            TEXT,
    document_type       TEXT,
    title               TEXT,
    client_name         TEXT,
    client_cif          TEXT,
    linked_type         TEXT,
    linked_id           TEXT,
    file_name           TEXT,
    file_size_kb        NUMERIC(12, 2),
    -- Full row JSONB for additional fields
    extra               JSONB,
    -- Audit columns
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_edms_category   ON edms_documents (category);
CREATE INDEX IF NOT EXISTS idx_edms_doctype    ON edms_documents (document_type);
CREATE INDEX IF NOT EXISTS idx_edms_client_cif ON edms_documents (client_cif);
CREATE INDEX IF NOT EXISTS idx_edms_linked     ON edms_documents (linked_type, linked_id);

-- ─────────────────────────────────────────────────────────────────
-- 9. customer_onboarding (~360 KB JSON, 500 records)
-- Source: data/customer_onboarding.json (top-level list)
-- Used by: pages/78_onboarding.py + utils/onboarding_engine.py
-- ─────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS customer_onboarding (
    id                  TEXT PRIMARY KEY,
    customer_name       TEXT,
    phone               TEXT,
    channel             TEXT,
    product             TEXT,
    started_date        DATE,
    completed_date      DATE,
    current_stage       TEXT,
    stages_completed    INTEGER,
    total_stages        INTEGER,
    -- Full row JSONB for stage details, KYC docs, etc.
    extra               JSONB,
    -- Audit columns
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_co_channel       ON customer_onboarding (channel);
CREATE INDEX IF NOT EXISTS idx_co_product       ON customer_onboarding (product);
CREATE INDEX IF NOT EXISTS idx_co_current_stage ON customer_onboarding (current_stage);
CREATE INDEX IF NOT EXISTS idx_co_started_date  ON customer_onboarding (started_date);

-- ─────────────────────────────────────────────────────────────────
-- 10. board_papers (60 records)
-- Source: data/board_papers.json (top-level list)
-- Used by: pages/84_board.py + utils/board_papers_engine.py
-- ─────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS board_papers (
    id                  TEXT PRIMARY KEY,
    title               TEXT NOT NULL,
    type                TEXT,
    committee           TEXT,
    meeting_date        DATE,
    submission_deadline DATE,
    submitted_date      DATE,
    submitted_on_time   BOOLEAN,
    submitted_by        TEXT,
    approved_by         TEXT,
    -- Full row JSONB for paper content metadata, attachments, etc.
    extra               JSONB,
    -- Audit columns
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_bp_committee    ON board_papers (committee);
CREATE INDEX IF NOT EXISTS idx_bp_meeting_date ON board_papers (meeting_date);
CREATE INDEX IF NOT EXISTS idx_bp_type         ON board_papers (type);

-- ─────────────────────────────────────────────────────────────────
-- Summary
-- ─────────────────────────────────────────────────────────────────
-- Tables added:           5 (performance_reviews, staff_growth_plans,
--                            edms_documents, customer_onboarding,
--                            board_papers)
-- Total DDL'd tables:     17 → 22
-- Indexes added:          14
-- Schema strategy:        same hybrid (explicit cols + JSONB extra)
-- v10.256 will add migrate_*() functions for these 5 tables.
