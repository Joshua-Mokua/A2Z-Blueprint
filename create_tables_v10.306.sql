-- =====================================================================
-- create_tables_v10.306.sql
-- v10.306 — PG migration push: 5 new tables for genuinely unmigrated
-- platform data.
-- =====================================================================
--
-- Scope honesty: inventory of FLAT_MIGRATIONS (41 entries) + explicit
-- migrate_X() functions (18) revealed many tables that conversation
-- history suggested were unmigrated were actually already migrated.
-- This batch closes 5 *genuinely* unmigrated registries:
--   audit_reviews                 (#201-#210 audit module)
--   compliance_regulatory_returns (Compliance cockpit / compliance.json)
--   incidents                     (IT incidents register)
--   nps_responses                 (customer NPS survey data)
--   rcsa_register                 (Risk RCSA register)
--
-- Schema pattern (consistent with v10.253 onwards):
--   - id TEXT PRIMARY KEY
--   - explicit columns for fields the cockpit composers actually read
--   - payload JSONB NOT NULL for forward-compatibility (full row)
--   - migrated_at TIMESTAMPTZ DEFAULT NOW() for audit trail
--
-- All tables use IF NOT EXISTS — safe to re-run.
-- =====================================================================


-- =====================================================================
-- 1. audit_reviews — internal audit review register (#201-#210)
-- =====================================================================
-- Backing data: data/audit_reviews.json (250 records).
-- Used by audit module pages. JSON keys: id, audit_title, audit_type,
-- category, branch, auditor_code, auditor_name, auditor_username, +
-- assorted finding/status fields parked in JSONB.

CREATE TABLE IF NOT EXISTS audit_reviews (
    id              TEXT PRIMARY KEY,
    audit_title     TEXT,
    audit_type      TEXT,
    category        TEXT,
    branch          TEXT,
    auditor_code    TEXT,
    auditor_name    TEXT,
    auditor_username TEXT,
    -- Full row stored as JSONB for forward compatibility — fields like
    -- findings/recommendations/status/dates evolve with the audit
    -- module's standards (#201-#210) and aren't pinned here.
    payload         JSONB NOT NULL,
    -- Audit columns
    migrated_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_audit_reviews_branch
    ON audit_reviews(branch);
CREATE INDEX IF NOT EXISTS idx_audit_reviews_auditor
    ON audit_reviews(auditor_code);


-- =====================================================================
-- 2. compliance_regulatory_returns — CBK/KRA filing register
-- =====================================================================
-- Backing data: data/compliance.json (60 records). The file is named
-- compliance.json for legacy reasons; the table name is more explicit.
-- Used by Compliance cockpit tab 5 (filing calendar).

CREATE TABLE IF NOT EXISTS compliance_regulatory_returns (
    id              TEXT PRIMARY KEY,
    return_name     TEXT,
    frequency       TEXT,
    due_date        DATE,
    filed_date      DATE,
    filer           TEXT,
    status          TEXT,
    on_time         BOOLEAN,
    -- Full row JSONB for additional fields (period, reviewed_by, etc.)
    payload         JSONB NOT NULL,
    -- Audit columns
    migrated_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_compliance_returns_due_date
    ON compliance_regulatory_returns(due_date);
CREATE INDEX IF NOT EXISTS idx_compliance_returns_status
    ON compliance_regulatory_returns(status);


-- =====================================================================
-- 3. incidents — IT/operations incident register
-- =====================================================================
-- Backing data: data/incidents.json (80 records).
-- Used by IT&Digital + Observability modules.

CREATE TABLE IF NOT EXISTS incidents (
    id              TEXT PRIMARY KEY,
    title           TEXT,
    system          TEXT,
    priority        TEXT,
    status          TEXT,
    raised_by       TEXT,
    assigned_to     TEXT,
    raised_date     TIMESTAMP,
    -- Full row JSONB for additional fields (resolution, root cause, etc.)
    payload         JSONB NOT NULL,
    -- Audit columns
    migrated_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_incidents_status
    ON incidents(status);
CREATE INDEX IF NOT EXISTS idx_incidents_priority
    ON incidents(priority);


-- =====================================================================
-- 4. nps_responses — customer NPS survey data
-- =====================================================================
-- Backing data: data/nps.json (150 records).
-- Used by Customer Behavioral Intelligence + Analytics Hub modules.

CREATE TABLE IF NOT EXISTS nps_responses (
    id              TEXT PRIMARY KEY,
    response_date   DATE,
    customer_cif    TEXT,
    score           INTEGER,
    band            TEXT,
    category        TEXT,
    channel         TEXT,
    branch          TEXT,
    -- Full row JSONB for additional fields (comments, follow-up, etc.)
    payload         JSONB NOT NULL,
    -- Audit columns
    migrated_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_nps_response_date
    ON nps_responses(response_date);
CREATE INDEX IF NOT EXISTS idx_nps_band
    ON nps_responses(band);


-- =====================================================================
-- 5. rcsa_register — Risk Control Self-Assessment register
-- =====================================================================
-- Backing data: data/rcsa_register.json (80 records).
-- Used by Risk module (#211-#220).

CREATE TABLE IF NOT EXISTS rcsa_register (
    id                    TEXT PRIMARY KEY,
    category              TEXT,
    description           TEXT,
    department            TEXT,
    inherent_likelihood   INTEGER,
    inherent_impact       INTEGER,
    inherent_score        INTEGER,
    control_description   TEXT,
    -- Full row JSONB for residual scores, owner, dates, evidence
    payload               JSONB NOT NULL,
    -- Audit columns
    migrated_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_rcsa_department
    ON rcsa_register(department);
CREATE INDEX IF NOT EXISTS idx_rcsa_inherent_score
    ON rcsa_register(inherent_score);
