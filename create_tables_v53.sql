
-- Partnerships & MOUs tables (v5.3)
CREATE TABLE IF NOT EXISTS partnerships (
    id                    VARCHAR(50) PRIMARY KEY,
    title                 VARCHAR(300),
    partner_name          VARCHAR(200),
    partner_type          VARCHAR(50),
    mou_type              VARCHAR(50),
    department            VARCHAR(200),
    relationship_manager  VARCHAR(100),
    signed_date           DATE,
    effective_date        DATE,
    expiry_date           DATE,
    status                VARCHAR(50),
    auto_renew            BOOLEAN DEFAULT false,
    renewal_notice_days   INT DEFAULT 90,
    deal_value_kes_m      NUMERIC(12,2),
    revenue_share_pct     NUMERIC(5,2),
    referral_revenue_ytd_m NUMERIC(12,2) DEFAULT 0,
    leads_generated_ytd   INT DEFAULT 0,
    accounts_opened_ytd   INT DEFAULT 0,
    cbk_approval_required BOOLEAN DEFAULT false,
    cbk_approval_ref      VARCHAR(100),
    board_approved        BOOLEAN DEFAULT false,
    legal_reviewed        BOOLEAN DEFAULT false,
    kpis                  JSONB DEFAULT '[]',
    milestones            JSONB DEFAULT '[]',
    notes                 TEXT,
    created_at            DATE,
    created_by            VARCHAR(100),
    metadata              JSONB DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_partnerships_status  ON partnerships (status);
CREATE INDEX IF NOT EXISTS idx_partnerships_expiry  ON partnerships (expiry_date);

CREATE TABLE IF NOT EXISTS referrals (
    id                VARCHAR(50) PRIMARY KEY,
    referral_date     DATE,
    referral_source   VARCHAR(100),
    referrer_name     VARCHAR(200),
    referrer_code     VARCHAR(50),
    referee_name      VARCHAR(200),
    referee_phone     VARCHAR(50),
    product_interested VARCHAR(200),
    mou_id            VARCHAR(50),
    branch            VARCHAR(200),
    rm_assigned       VARCHAR(100),
    status            VARCHAR(50),
    converted         BOOLEAN DEFAULT false,
    conversion_date   DATE,
    account_opened    VARCHAR(50),
    referral_fee_kes  NUMERIC(10,2) DEFAULT 0,
    fee_paid          BOOLEAN DEFAULT false,
    notes             TEXT,
    created_at        TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_referrals_source    ON referrals (referral_source);
CREATE INDEX IF NOT EXISTS idx_referrals_converted ON referrals (converted);

CREATE TABLE IF NOT EXISTS sponsored_events (
    id                     VARCHAR(50) PRIMARY KEY,
    name                   VARCHAR(300),
    event_category         VARCHAR(50),
    category_name          VARCHAR(100),
    partner                VARCHAR(200),
    mou_id                 VARCHAR(50),
    branch                 VARCHAR(200),
    department             VARCHAR(200),
    rm_owner               VARCHAR(100),
    start_date             DATE,
    end_date               DATE,
    status                 VARCHAR(50),
    budget_kes             NUMERIC(14,2),
    spent_kes              NUMERIC(14,2),
    target_leads           INT DEFAULT 0,
    actual_leads           INT DEFAULT 0,
    target_accounts        INT DEFAULT 0,
    actual_accounts        INT DEFAULT 0,
    target_deposits_m      NUMERIC(10,2) DEFAULT 0,
    actual_deposits_m      NUMERIC(10,2) DEFAULT 0,
    catchment_population   INT DEFAULT 0,
    reached_count          INT DEFAULT 0,
    penetration_pct        NUMERIC(6,2) DEFAULT 0,
    roi_pct                NUMERIC(8,2) DEFAULT 0,
    cost_per_lead_kes      NUMERIC(10,2) DEFAULT 0,
    cost_per_account_kes   NUMERIC(10,2) DEFAULT 0,
    notes                  TEXT,
    created_by             VARCHAR(100),
    metadata               JSONB DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_events_status   ON sponsored_events (status);
CREATE INDEX IF NOT EXISTS idx_events_category ON sponsored_events (event_category);

CREATE TABLE IF NOT EXISTS agent_fraud_alerts (
    id                VARCHAR(50) PRIMARY KEY,
    alert_type        VARCHAR(100),
    severity          VARCHAR(20),
    agent_id          VARCHAR(50),
    agent_name        VARCHAR(200),
    branch            VARCHAR(200),
    customer_ref      VARCHAR(100),
    txn_date          DATE,
    txn_count         INT DEFAULT 0,
    total_amount_kes  NUMERIC(14,2) DEFAULT 0,
    threshold_kes     NUMERIC(14,2) DEFAULT 0,
    commission_earned NUMERIC(10,2) DEFAULT 0,
    excess_commission NUMERIC(10,2) DEFAULT 0,
    txn_ids           JSONB DEFAULT '[]',
    amounts           JSONB DEFAULT '[]',
    status            VARCHAR(50),
    assigned_to       VARCHAR(200),
    detected_at       DATE,
    action_taken      TEXT,
    notes             TEXT
);
CREATE INDEX IF NOT EXISTS idx_fraud_severity ON agent_fraud_alerts (severity);
CREATE INDEX IF NOT EXISTS idx_fraud_status   ON agent_fraud_alerts (status);
CREATE INDEX IF NOT EXISTS idx_fraud_agent    ON agent_fraud_alerts (agent_id);
