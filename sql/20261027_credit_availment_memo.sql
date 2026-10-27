-- Universal Credit Availment Memo: additive PostgreSQL migration
-- Review before execution; no application or database changes performed by this script creation.
CREATE SCHEMA IF NOT EXISTS credit;
CREATE TABLE IF NOT EXISTS credit.availment_memos (
    id VARCHAR(80) PRIMARY KEY,
    credit_admin_case_id VARCHAR(80) NOT NULL UNIQUE,
    application_id VARCHAR(80) NOT NULL,
    status VARCHAR(40) NOT NULL DEFAULT 'draft',
    current_version INTEGER NOT NULL DEFAULT 0,
    data JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_by VARCHAR(200) NOT NULL,
    created_by_code VARCHAR(200),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_by VARCHAR(200) NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    approval_assignee_code VARCHAR(200),
    approval_assignee_name VARCHAR(200),
    approval_assignee_role VARCHAR(200),
    approval_requested_by VARCHAR(200),
    approval_requested_by_code VARCHAR(200),
    approval_requested_at TIMESTAMPTZ,
    approval_note TEXT,
    approved_by VARCHAR(200),
    approved_at TIMESTAMPTZ,
    sent_to_trops_by VARCHAR(200),
    sent_to_trops_at TIMESTAMPTZ
);
ALTER TABLE credit.availment_memos ADD COLUMN IF NOT EXISTS created_by_code VARCHAR(200);
ALTER TABLE credit.availment_memos ADD COLUMN IF NOT EXISTS sent_to_trops_by VARCHAR(200);
ALTER TABLE credit.availment_memos ADD COLUMN IF NOT EXISTS sent_to_trops_at TIMESTAMPTZ;
CREATE INDEX IF NOT EXISTS idx_availment_application ON credit.availment_memos (application_id);
CREATE INDEX IF NOT EXISTS idx_availment_status ON credit.availment_memos (status);
CREATE TABLE IF NOT EXISTS credit.availment_versions (
    memo_id VARCHAR(80) NOT NULL,
    version INTEGER NOT NULL,
    snapshot JSONB NOT NULL,
    created_by VARCHAR(200) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (memo_id, version),
    CONSTRAINT fk_availment_version_memo FOREIGN KEY (memo_id) REFERENCES credit.availment_memos(id) ON DELETE RESTRICT
);
CREATE INDEX IF NOT EXISTS idx_availment_versions_memo ON credit.availment_versions (memo_id, version DESC);
