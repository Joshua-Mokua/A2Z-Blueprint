-- create_tables_v10.257.sql — DDL for next-5 high-value tables
-- v10.257 PG Migration Sub-Campaign — Batch 5 of 8
--
-- Purpose: 5 more high-value tables. Picked over loan_applications +
-- aml_alerts (already in create_tables.sql v8). v10.258 will add the
-- matching migrate_*() functions.

-- ─────────────────────────────────────────────────────────────────
-- 11. legal_matters (~675 KB JSON, 362 records)
-- Source: data/legal_matters.json (top-level list)
-- Used by: pages/26_legal.py + pages/65_contracts.py
-- ─────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS legal_matters (
    id                  TEXT PRIMARY KEY,
    matter_type         TEXT,
    status              TEXT,
    priority            TEXT,
    opened_date         DATE,
    sla_due_date        DATE,
    completed_date      DATE,
    days_elapsed        INTEGER,
    days_to_sla         INTEGER,
    sla_days            INTEGER,
    -- Full row JSONB for description, parties, attachments
    extra               JSONB,
    -- Audit columns
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_lm_matter_type ON legal_matters (matter_type);
CREATE INDEX IF NOT EXISTS idx_lm_status      ON legal_matters (status);
CREATE INDEX IF NOT EXISTS idx_lm_priority    ON legal_matters (priority);
CREATE INDEX IF NOT EXISTS idx_lm_sla_due     ON legal_matters (sla_due_date);

-- ─────────────────────────────────────────────────────────────────
-- 12. leave_requests (~516 KB JSON, 1,416 records)
-- Source: data/leave_requests.json (top-level list)
-- Used by: pages/2_people.py
-- ─────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS leave_requests (
    id                  TEXT PRIMARY KEY,
    staff_code          TEXT NOT NULL,
    staff_name          TEXT,
    leave_type          TEXT,
    start_date          DATE,
    end_date            DATE,
    days                NUMERIC(6, 2),
    status              TEXT,
    submitted_date      DATE,
    approved_date       DATE,
    -- Full row JSONB for approver, comments, etc.
    extra               JSONB,
    -- Audit columns
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_lr_staff_code ON leave_requests (staff_code);
CREATE INDEX IF NOT EXISTS idx_lr_status     ON leave_requests (status);
CREATE INDEX IF NOT EXISTS idx_lr_leave_type ON leave_requests (leave_type);
CREATE INDEX IF NOT EXISTS idx_lr_start_date ON leave_requests (start_date);

-- ─────────────────────────────────────────────────────────────────
-- 13. lms_enrollments (~399 KB JSON, 1,146 records)
-- Source: data/lms_enrollments.json (top-level list)
-- Used by: pages/42_lms.py
-- ─────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS lms_enrollments (
    -- Composite key: staff_code + course_id (no native id field)
    enrollment_key      TEXT PRIMARY KEY,
    staff_code          TEXT NOT NULL,
    staff_name          TEXT,
    role                TEXT,
    dept                TEXT,
    course_id           TEXT NOT NULL,
    course_title        TEXT,
    cbk_mandatory       BOOLEAN,
    status              TEXT,
    completion_date     DATE,
    score               NUMERIC(6, 2),
    -- Full row JSONB
    extra               JSONB,
    -- Audit columns
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_le_staff_code     ON lms_enrollments (staff_code);
CREATE INDEX IF NOT EXISTS idx_le_course_id      ON lms_enrollments (course_id);
CREATE INDEX IF NOT EXISTS idx_le_status         ON lms_enrollments (status);
CREATE INDEX IF NOT EXISTS idx_le_cbk_mandatory  ON lms_enrollments (cbk_mandatory);
CREATE INDEX IF NOT EXISTS idx_le_dept           ON lms_enrollments (dept);

-- ─────────────────────────────────────────────────────────────────
-- 14. pipeline_deals_full (~350 KB JSON)
-- NOTE: pipeline_deals already in create_tables.sql with FLAT cols.
-- This table preserves the FULL pipeline.json (which has dict-shaped
-- entries with nested deal stages, owner history, etc.) as a JSONB-
-- heavy mirror used for read-heavy analytics.
-- Source: data/pipeline.json
-- Used by: pages/3_pipeline.py
-- ─────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS pipeline_deals_full (
    id                  TEXT PRIMARY KEY,
    client_name         TEXT,
    client_cif          TEXT,
    product             TEXT,
    amount              NUMERIC(20, 2),
    currency            TEXT,
    stage               TEXT,
    swim_lane           TEXT,
    owner_code          TEXT,
    owner_name          TEXT,
    branch_code         TEXT,
    expected_close_date DATE,
    -- Full row JSONB for stage history, attachments, comments
    extra               JSONB,
    -- Audit columns
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_pdf_client_cif    ON pipeline_deals_full (client_cif);
CREATE INDEX IF NOT EXISTS idx_pdf_owner_code    ON pipeline_deals_full (owner_code);
CREATE INDEX IF NOT EXISTS idx_pdf_stage         ON pipeline_deals_full (stage);
CREATE INDEX IF NOT EXISTS idx_pdf_branch        ON pipeline_deals_full (branch_code);
CREATE INDEX IF NOT EXISTS idx_pdf_expected_close ON pipeline_deals_full (expected_close_date);

-- ─────────────────────────────────────────────────────────────────
-- 15. rms_reconciliations (~241 KB JSON)
-- Source: data/rms_reconciliations.json
-- Used by: pages/30_rms.py + utils/reconciliation_engine.py
-- ─────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS rms_reconciliations (
    id                  TEXT PRIMARY KEY,
    recon_type          TEXT,
    period              TEXT,
    source_a            TEXT,
    source_b            TEXT,
    matched_count       INTEGER,
    break_count         INTEGER,
    total_count         INTEGER,
    match_rate_pct      NUMERIC(6, 2),
    status              TEXT,
    completed_date      DATE,
    -- Full row JSONB for break details, resolutions
    extra               JSONB,
    -- Audit columns
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_rms_recon_type ON rms_reconciliations (recon_type);
CREATE INDEX IF NOT EXISTS idx_rms_period     ON rms_reconciliations (period);
CREATE INDEX IF NOT EXISTS idx_rms_status     ON rms_reconciliations (status);

-- ─────────────────────────────────────────────────────────────────
-- Summary
-- ─────────────────────────────────────────────────────────────────
-- Tables added:        5 (legal_matters, leave_requests,
--                         lms_enrollments, pipeline_deals_full,
--                         rms_reconciliations)
-- Total DDL'd tables:  22 → 27
-- Indexes added:       19
-- v10.258 will add migrate_*() functions for these 5 tables.
