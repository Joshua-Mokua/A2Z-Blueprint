-- create_tables_v10.261.sql — Direct-write cleanup sub-sub-campaign Phase A.1
-- DDL for partnership cluster (4 tables written by pages/66_partnerships.py)
--
-- Per v10.259 audit: pages/66_partnerships.py writes to 4 different
-- JSON files via direct (DATA/"X.json").write_text(json.dumps(data))
-- pattern, bypassing utils.db.dual_save. This DDL is the foundation
-- for migrating those writes through the dual-mode seam.
--
-- v10.262 adds matching migrators. v10.263 refactors the 7 write
-- sites in 66_partnerships.py to use db.dual_save.
--
-- Apply via: psql -d a2z -f create_tables_v10.261.sql

-- ─────────────────────────────────────────────────────────────────
-- 28. partnerships_mous (~30 records)
-- Source: data/partnerships_mous.json (top-level list)
-- Used by: pages/66_partnerships.py (Strategic Partnerships > MoUs)
-- ─────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS partnerships_mous (
    id                  TEXT PRIMARY KEY,
    title               TEXT NOT NULL,
    partner_name        TEXT,
    partner_type        TEXT,
    mou_type            TEXT,
    department          TEXT,
    relationship_manager TEXT,
    signed_date         DATE,
    effective_date      DATE,
    expiry_date         DATE,
    status              TEXT,
    -- Full row JSONB for terms, attachments, notes
    extra               JSONB,
    -- Audit columns
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_pm_partner_name  ON partnerships_mous (partner_name);
CREATE INDEX IF NOT EXISTS idx_pm_partner_type  ON partnerships_mous (partner_type);
CREATE INDEX IF NOT EXISTS idx_pm_mou_type      ON partnerships_mous (mou_type);
CREATE INDEX IF NOT EXISTS idx_pm_department    ON partnerships_mous (department);
CREATE INDEX IF NOT EXISTS idx_pm_expiry_date   ON partnerships_mous (expiry_date);
CREATE INDEX IF NOT EXISTS idx_pm_status        ON partnerships_mous (status);

-- ─────────────────────────────────────────────────────────────────
-- 29. sponsored_events (~12 records)
-- Source: data/sponsored_events.json (top-level list)
-- Used by: pages/66_partnerships.py (Strategic Partnerships > Events)
-- ─────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS sponsored_events (
    id                  TEXT PRIMARY KEY,
    name                TEXT NOT NULL,
    event_category      TEXT,
    category_name       TEXT,
    partner             TEXT,
    mou_id              TEXT,           -- FK reference (loose) to partnerships_mous.id
    branch              TEXT,
    department          TEXT,
    rm_owner            TEXT,
    start_date          DATE,
    end_date            DATE,
    sponsorship_amount  NUMERIC(20, 2),
    status              TEXT,
    -- Full row JSONB for attendees, outcomes, photos
    extra               JSONB,
    -- Audit columns
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_se_partner        ON sponsored_events (partner);
CREATE INDEX IF NOT EXISTS idx_se_mou_id         ON sponsored_events (mou_id);
CREATE INDEX IF NOT EXISTS idx_se_event_category ON sponsored_events (event_category);
CREATE INDEX IF NOT EXISTS idx_se_branch         ON sponsored_events (branch);
CREATE INDEX IF NOT EXISTS idx_se_start_date     ON sponsored_events (start_date);

-- ─────────────────────────────────────────────────────────────────
-- 30. partnership_referrals (~200 records)
-- Source: data/referrals.json (top-level list)
-- NOTE: table named partnership_referrals (not just "referrals") to
-- avoid collision with future RM-driven referrals or other systems.
-- Used by: pages/66_partnerships.py (Strategic Partnerships > Referrals)
-- ─────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS partnership_referrals (
    id                  TEXT PRIMARY KEY,
    referral_date       DATE,
    referral_source     TEXT,
    referrer_name       TEXT,
    referrer_code       TEXT,
    referee_name        TEXT,
    referee_phone       TEXT,
    product_interested  TEXT,
    mou_id              TEXT,           -- FK reference (loose) to partnerships_mous.id
    branch              TEXT,
    status              TEXT,
    converted_date      DATE,
    -- Full row JSONB for conversion details, follow-up notes
    extra               JSONB,
    -- Audit columns
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_pr_referrer_code     ON partnership_referrals (referrer_code);
CREATE INDEX IF NOT EXISTS idx_pr_referral_source   ON partnership_referrals (referral_source);
CREATE INDEX IF NOT EXISTS idx_pr_mou_id            ON partnership_referrals (mou_id);
CREATE INDEX IF NOT EXISTS idx_pr_status            ON partnership_referrals (status);
CREATE INDEX IF NOT EXISTS idx_pr_referral_date    ON partnership_referrals (referral_date);
CREATE INDEX IF NOT EXISTS idx_pr_product           ON partnership_referrals (product_interested);

-- ─────────────────────────────────────────────────────────────────
-- 31. partnership_config (config — single row)
-- Source: data/partnership_config.json (top-level dict)
-- Stores configurable taxonomy: MoU types, partner types, event
-- categories, referral sources, beyond-banking products. Pattern
-- mirrors org_config / module_config — single config row, full
-- contents in JSONB.
-- Used by: pages/66_partnerships.py (Admin tab)
-- ─────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS partnership_config (
    config_key          TEXT PRIMARY KEY DEFAULT 'default',
    -- Sub-dicts stored as JSONB
    mou_types           JSONB NOT NULL DEFAULT '[]'::jsonb,
    partner_types       JSONB NOT NULL DEFAULT '[]'::jsonb,
    event_categories    JSONB NOT NULL DEFAULT '[]'::jsonb,
    referral_sources    JSONB NOT NULL DEFAULT '[]'::jsonb,
    beyond_banking_products JSONB NOT NULL DEFAULT '[]'::jsonb,
    -- Audit columns
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ─────────────────────────────────────────────────────────────────
-- Summary
-- ─────────────────────────────────────────────────────────────────
-- Tables added:        4 (partnerships_mous, sponsored_events,
--                         partnership_referrals, partnership_config)
-- Total DDL'd tables:  27 → 31
-- Indexes added:       17
-- Schema strategy:     same hybrid (explicit cols + JSONB extras)
--                      partnership_config uses single-row config
--                      pattern (config_key='default' as PK)
-- v10.262 will add migrate_*() functions for these 4 tables.
-- v10.263 will refactor pages/66_partnerships.py's 7 write sites
--         to use db.dual_save instead of direct write_text.
