-- credit_admin schema (Batch CA-1)
-- Design: stable scalar columns for query/index + a COMPLETE-case `data` JSONB.
-- The complete case lives in `data` so NO sub-flow field (collateral, legal,
-- perfection, insurance, authorizations, override, ...) can ever be lost under
-- DB-first reads. This deliberately differs from the pipeline_deals `metadata`
-- (partial) approach, which hit the Phase-B0 "missing field vanished" trap.
-- Idempotent: safe to run repeatedly.

CREATE TABLE IF NOT EXISTS credit_admin (
    id                      VARCHAR(50) PRIMARY KEY,
    application_id          VARCHAR(50),
    client_name             VARCHAR(300),
    product                 VARCHAR(200),
    amount                  NUMERIC(18,2),
    rm_code                 VARCHAR(50),
    rm_name                 VARCHAR(200),
    approval_date           DATE,
    all_conditions_met      BOOLEAN     DEFAULT false,
    ready_for_disbursement  BOOLEAN     DEFAULT false,
    disbursed               BOOLEAN     DEFAULT false,
    disbursement_date       DATE,
    last_updated            TIMESTAMPTZ DEFAULT now(),
    data                    JSONB       NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_credit_admin_app       ON credit_admin (application_id);
CREATE INDEX IF NOT EXISTS idx_credit_admin_disbursed ON credit_admin (disbursed);
