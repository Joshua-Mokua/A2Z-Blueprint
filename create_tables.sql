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