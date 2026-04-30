-- ============================================================
-- MCP BILLING + ANALYTICS — Complete PostgreSQL Schema
-- ============================================================
-- Generated from:  mcp/mcp-billing/src/{schemas,db,audit,tools/*.rs}
--                  mcp/mcp-analytics/src/{schemas,db,audit,tools/*.rs}
--
-- Execution modes:
--   FRESH DATABASE:  run this file as-is; all CREATE TABLE statements
--                    are guarded by IF NOT EXISTS.
--   EXISTING BACKEND DB:  the backend Alembic migrations (0001-0005)
--                    already created `organizations` and `users` with
--                    `org_id` / `is_active` / `full_name` naming.
--                    Jump to SECTION 8 (ALTER TABLE bridge statements)
--                    before running the rest of this file.
-- ============================================================

-- ============================================================
-- SECTION 0 — Extensions
-- ============================================================
CREATE EXTENSION IF NOT EXISTS "pgcrypto";


-- ============================================================
-- SECTION 1 — Enum types
-- ============================================================

-- invoice_status
-- Derived from: mcp-billing/src/schemas.rs InvoiceStatus
-- sqlx(type_name = "invoice_status", rename_all = "snake_case")
DO $$ BEGIN
    CREATE TYPE invoice_status AS ENUM (
        'draft',
        'pending',
        'paid',
        'overdue',
        'void',
        'refunded'
    );
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

-- subscription_status
-- Derived from: mcp-billing/src/schemas.rs SubscriptionStatus
-- sqlx(type_name = "subscription_status", rename_all = "snake_case")
DO $$ BEGIN
    CREATE TYPE subscription_status AS ENUM (
        'trialing',
        'active',
        'past_due',
        'canceled',
        'suspended',
        'paused'
    );
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;


-- ============================================================
-- SECTION 2 — organizations  (shared tenant anchor table)
-- ============================================================
-- Queried by: mcp-billing/src/db.rs validate_tenant()
--             mcp-analytics/src/db.rs validate_tenant()
--   SELECT EXISTS(SELECT 1 FROM organizations WHERE id = $1 AND active = true)
-- Queried by: mcp-billing/src/tools/invoices.rs list_overdue_payments()
--   LEFT JOIN organizations o ON o.id = i.tenant_id  →  o.billing_email
-- ============================================================

CREATE TABLE IF NOT EXISTS organizations (
    id            UUID         NOT NULL PRIMARY KEY DEFAULT gen_random_uuid(),
    name          VARCHAR(255) NOT NULL,
    slug          VARCHAR(100) NOT NULL,
    plan          VARCHAR(50)  NOT NULL DEFAULT 'free',
    -- MCP requirement: validate_tenant checks active = true
    active        BOOLEAN      NOT NULL DEFAULT true,
    -- MCP requirement: list_overdue_payments reads billing_email
    billing_email VARCHAR(255),
    created_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_organizations_slug ON organizations (slug);


-- ============================================================
-- SECTION 3 — users  (shared user table)
-- ============================================================
-- Queried by: mcp-billing/src/tools/subscriptions.rs check_subscription_status()
--   SELECT COUNT(*)::bigint FROM users WHERE tenant_id = $1 AND active = true
-- Queried by: mcp-analytics/src/tools/performance.rs get_team_leaderboard()
--   LEFT JOIN users u ON u.id = d.assigned_to AND u.tenant_id = d.tenant_id
--   COALESCE(u.name, u.id::text)
--
-- NOTE: the existing backend Alembic schema uses `org_id` (not `tenant_id`),
-- `is_active` (not `active`), and `full_name` (not `name`).
-- See SECTION 8 for bridge ALTER TABLE statements when using the existing DB.
-- ============================================================

CREATE TABLE IF NOT EXISTS users (
    id            UUID         NOT NULL PRIMARY KEY DEFAULT gen_random_uuid(),
    -- tenant_id == org_id in the backend Alembic schema
    tenant_id     UUID         NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    email         VARCHAR(255) NOT NULL,
    password_hash VARCHAR(255),
    -- `name` is what the Rust analytics queries (COALESCE(u.name, u.id::text))
    name          VARCHAR(255),
    full_name     VARCHAR(255),
    job_title     VARCHAR(255),
    avatar        TEXT,
    roles         TEXT[]       NOT NULL DEFAULT '{}',
    permissions   TEXT[]       NOT NULL DEFAULT '{}',
    -- `active` is what the Rust billing queries (active = true)
    active        BOOLEAN      NOT NULL DEFAULT true,
    is_active     BOOLEAN      NOT NULL DEFAULT true,   -- backend compat alias
    created_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_users_email        ON users (email);
CREATE INDEX        IF NOT EXISTS ix_users_tenant_id    ON users (tenant_id);


-- ============================================================
-- SECTION 4 — user_permissions
-- ============================================================
-- Queried by: mcp-billing/src/tools/subscriptions.rs update_subscription_status()
--   SELECT EXISTS(
--       SELECT 1 FROM user_permissions
--       WHERE user_id = $1 AND tenant_id = $2
--         AND permission = 'billing:subscriptions:write'
--   )
-- ============================================================

CREATE TABLE IF NOT EXISTS user_permissions (
    user_id    UUID        NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    tenant_id  UUID        NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    permission TEXT        NOT NULL,
    granted_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (user_id, tenant_id, permission)
);

CREATE INDEX IF NOT EXISTS ix_user_permissions_tenant ON user_permissions (tenant_id);


-- ============================================================
-- SECTION 5 — accounts  (shared: CRM + billing at-risk + analytics)
-- ============================================================
-- Queried by: mcp-analytics/src/tools/churn.rs get_at_risk_accounts()
--   FROM accounts a
--   LEFT JOIN subscriptions s ON s.account_id = a.id AND s.tenant_id = a.tenant_id
--   LEFT JOIN activities   act ON act.entity_id = a.id AND act.tenant_id = a.tenant_id
--   LEFT JOIN invoices     inv ON inv.account_id = a.id AND inv.tenant_id = a.tenant_id
--   WHERE a.tenant_id = $1
-- ============================================================

CREATE TABLE IF NOT EXISTS accounts (
    id         UUID         NOT NULL PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id  UUID         NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    name       VARCHAR(255) NOT NULL,
    domain     VARCHAR(255),
    industry   VARCHAR(100),
    size       VARCHAR(50),
    status     VARCHAR(50)  NOT NULL DEFAULT 'active',
    created_at TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_accounts_tenant_id ON accounts (tenant_id);
CREATE INDEX IF NOT EXISTS ix_accounts_tenant_name ON accounts (tenant_id, name);

ALTER TABLE accounts ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS mcp_tenant_isolation ON accounts;
CREATE POLICY mcp_tenant_isolation ON accounts
    USING     (tenant_id::text = current_setting('app.current_tenant_id', true))
    WITH CHECK (tenant_id::text = current_setting('app.current_tenant_id', true));


-- ============================================================
-- SECTION 6 — BILLING tables
-- ============================================================

-- ----------------------------------------------------------
-- 6a. subscriptions
-- ----------------------------------------------------------
-- Queried by: mcp-billing/src/tools/subscriptions.rs
--   SELECT id, tenant_id, plan_id, plan_name,
--          status, seats, mrr, currency,
--          current_period_start, current_period_end,
--          cancel_at_period_end, trial_end, features, created_at
--   FROM subscriptions WHERE ...
--   UPDATE subscriptions SET status = $1, updated_at = $2 WHERE ...
-- Queried by: mcp-billing/src/tools/summary.rs get_mrr()
--   SELECT mrr, currency, current_period_end FROM subscriptions WHERE ...
-- Queried by: mcp-analytics/src/tools/revenue.rs get_mrr_trend()
--   SELECT DATE_TRUNC('month', started_at)::date, mrr, status, churned_at
--   FROM subscriptions WHERE ...
-- Queried by: mcp-analytics/src/tools/churn.rs compute_churn_rate()
--   WITH starting AS (...FROM subscriptions WHERE started_at < $2 ...)
--   churned AS (...FROM subscriptions WHERE churned_at BETWEEN $2 AND $3)
--   expansion AS (JOIN subscriptions ON s.account_id = s_prev.account_id ...)
-- ----------------------------------------------------------

CREATE TABLE IF NOT EXISTS subscriptions (
    id                   UUID               NOT NULL PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id            UUID               NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    -- account_id for churn expansion CTE: JOIN subscriptions ON s.account_id = s_prev.account_id
    account_id           UUID               REFERENCES accounts(id) ON DELETE SET NULL,
    plan_id              VARCHAR(100)       NOT NULL,
    plan_name            VARCHAR(255)       NOT NULL,
    status               subscription_status NOT NULL DEFAULT 'active',
    seats                INTEGER            NOT NULL DEFAULT 1,
    mrr                  NUMERIC(14, 2)     NOT NULL DEFAULT 0,
    currency             VARCHAR(3)         NOT NULL DEFAULT 'USD',
    current_period_start TIMESTAMPTZ        NOT NULL,
    current_period_end   TIMESTAMPTZ        NOT NULL,
    cancel_at_period_end BOOLEAN            NOT NULL DEFAULT false,
    trial_end            TIMESTAMPTZ,
    -- features stored as JSON array of strings: ["feature_a", "feature_b"]
    features             JSONB              NOT NULL DEFAULT '[]',
    -- started_at: used by get_mrr_trend() GROUP BY DATE_TRUNC('month', started_at)
    started_at           TIMESTAMPTZ        NOT NULL DEFAULT NOW(),
    -- churned_at: used by compute_churn_rate() WHERE churned_at BETWEEN $2 AND $3
    churned_at           TIMESTAMPTZ,
    created_at           TIMESTAMPTZ        NOT NULL DEFAULT NOW(),
    updated_at           TIMESTAMPTZ        NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_subscriptions_tenant_id      ON subscriptions (tenant_id);
CREATE INDEX IF NOT EXISTS ix_subscriptions_tenant_status  ON subscriptions (tenant_id, status);
CREATE INDEX IF NOT EXISTS ix_subscriptions_account_id     ON subscriptions (account_id);
CREATE INDEX IF NOT EXISTS ix_subscriptions_started_at     ON subscriptions (tenant_id, started_at);

ALTER TABLE subscriptions ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS mcp_tenant_isolation ON subscriptions;
CREATE POLICY mcp_tenant_isolation ON subscriptions
    USING     (tenant_id::text = current_setting('app.current_tenant_id', true))
    WITH CHECK (tenant_id::text = current_setting('app.current_tenant_id', true));


-- ----------------------------------------------------------
-- 6b. invoices
-- ----------------------------------------------------------
-- Queried by: mcp-billing/src/tools/invoices.rs
--   SELECT id, tenant_id, subscription_id, invoice_number,
--          status, amount, currency, due_date, paid_at, created_at
--   FROM invoices WHERE id = $1 AND tenant_id = $2
--   (list, overdue variants also filter by status, due_date)
-- Queried by: mcp-analytics/src/tools/churn.rs get_at_risk_accounts()
--   LEFT JOIN invoices inv ON inv.account_id = a.id AND inv.tenant_id = a.tenant_id
--   COUNT(inv.id) FILTER (WHERE inv.status = 'unpaid')
--   COUNT(inv.id) FILTER (WHERE inv.status = 'overdue')
-- ----------------------------------------------------------

CREATE TABLE IF NOT EXISTS invoices (
    id              UUID            NOT NULL PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID            NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    subscription_id UUID            NOT NULL REFERENCES subscriptions(id) ON DELETE RESTRICT,
    -- account_id used by at-risk join: inv.account_id = a.id
    account_id      UUID            REFERENCES accounts(id) ON DELETE SET NULL,
    invoice_number  VARCHAR(100)    NOT NULL,
    status          invoice_status  NOT NULL DEFAULT 'draft',
    amount          NUMERIC(14, 2)  NOT NULL DEFAULT 0,
    currency        VARCHAR(3)      NOT NULL DEFAULT 'USD',
    due_date        DATE            NOT NULL,
    paid_at         TIMESTAMPTZ,
    created_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_invoices_tenant_number  ON invoices (tenant_id, invoice_number);
CREATE INDEX        IF NOT EXISTS ix_invoices_tenant_id       ON invoices (tenant_id);
CREATE INDEX        IF NOT EXISTS ix_invoices_tenant_status   ON invoices (tenant_id, status);
CREATE INDEX        IF NOT EXISTS ix_invoices_due_date        ON invoices (tenant_id, due_date);
CREATE INDEX        IF NOT EXISTS ix_invoices_account_id      ON invoices (account_id);

ALTER TABLE invoices ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS mcp_tenant_isolation ON invoices;
CREATE POLICY mcp_tenant_isolation ON invoices
    USING     (tenant_id::text = current_setting('app.current_tenant_id', true))
    WITH CHECK (tenant_id::text = current_setting('app.current_tenant_id', true));


-- ----------------------------------------------------------
-- 6c. invoice_line_items
-- ----------------------------------------------------------
-- Queried by: mcp-billing/src/tools/invoices.rs fetch_line_items()
--   SELECT description, quantity, unit_price, amount
--   FROM invoice_line_items
--   WHERE invoice_id = $1
--   ORDER BY id ASC          ← requires ordered PK (BIGSERIAL)
-- ----------------------------------------------------------

CREATE TABLE IF NOT EXISTS invoice_line_items (
    id          BIGSERIAL      NOT NULL PRIMARY KEY,
    invoice_id  UUID           NOT NULL REFERENCES invoices(id) ON DELETE CASCADE,
    description TEXT           NOT NULL,
    quantity    INTEGER        NOT NULL DEFAULT 1,
    unit_price  NUMERIC(14, 2) NOT NULL,
    amount      NUMERIC(14, 2) NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_line_items_invoice_id ON invoice_line_items (invoice_id);


-- ----------------------------------------------------------
-- 6d. payment_methods
-- ----------------------------------------------------------
-- Queried by: mcp-billing/src/tools/summary.rs get_customer_billing_summary()
--   SELECT last4 FROM payment_methods
--   WHERE tenant_id = $1 AND is_default = true LIMIT 1
-- ----------------------------------------------------------

CREATE TABLE IF NOT EXISTS payment_methods (
    id         UUID         NOT NULL PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id  UUID         NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    last4      VARCHAR(4)   NOT NULL,
    brand      VARCHAR(50),
    is_default BOOLEAN      NOT NULL DEFAULT false,
    created_at TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_payment_methods_tenant_id ON payment_methods (tenant_id);

ALTER TABLE payment_methods ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS mcp_tenant_isolation ON payment_methods;
CREATE POLICY mcp_tenant_isolation ON payment_methods
    USING     (tenant_id::text = current_setting('app.current_tenant_id', true))
    WITH CHECK (tenant_id::text = current_setting('app.current_tenant_id', true));


-- ----------------------------------------------------------
-- 6e. mrr_snapshots
-- ----------------------------------------------------------
-- Queried by: mcp-billing/src/tools/summary.rs get_mrr()
--   SELECT DATE_TRUNC('month', snapshot_date)::date AS month_date,
--          AVG(mrr), SUM(new_mrr), SUM(expansion_mrr), SUM(churned_mrr)
--   FROM mrr_snapshots
--   WHERE tenant_id = $1
--     AND snapshot_date >= $2 AND snapshot_date <= $3
--   GROUP BY DATE_TRUNC('month', snapshot_date)
-- ----------------------------------------------------------

CREATE TABLE IF NOT EXISTS mrr_snapshots (
    id            UUID           NOT NULL PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id     UUID           NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    snapshot_date DATE           NOT NULL,
    mrr           NUMERIC(14, 2) NOT NULL DEFAULT 0,
    new_mrr       NUMERIC(14, 2) NOT NULL DEFAULT 0,
    expansion_mrr NUMERIC(14, 2) NOT NULL DEFAULT 0,
    churned_mrr   NUMERIC(14, 2) NOT NULL DEFAULT 0,
    created_at    TIMESTAMPTZ    NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_mrr_snapshots_tenant_date ON mrr_snapshots (tenant_id, snapshot_date);
CREATE INDEX        IF NOT EXISTS ix_mrr_snapshots_tenant_range ON mrr_snapshots (tenant_id, snapshot_date);

ALTER TABLE mrr_snapshots ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS mcp_tenant_isolation ON mrr_snapshots;
CREATE POLICY mcp_tenant_isolation ON mrr_snapshots
    USING     (tenant_id::text = current_setting('app.current_tenant_id', true))
    WITH CHECK (tenant_id::text = current_setting('app.current_tenant_id', true));


-- ============================================================
-- SECTION 7 — ANALYTICS tables
-- ============================================================

-- ----------------------------------------------------------
-- 7a. deals  (analytics view of CRM deals)
-- ----------------------------------------------------------
-- Queried by: mcp-analytics/src/tools/pipeline.rs  (stage, value, assigned_to,
--             close_date, created_at, closed_at, probability)
-- Queried by: mcp-analytics/src/tools/revenue.rs   (stage, value, close_date,
--             probability, closed_at)
-- Queried by: mcp-analytics/src/tools/performance.rs (stage, value, assigned_to,
--             created_at, closed_at)
-- Queried by: mcp-analytics/src/tools/churn.rs get_at_risk_accounts()
--   (no direct join, but subscriptions.account_id links to accounts which links here)
--
-- NOTE: The existing CRM migration (0002) creates `deals` with `org_id`, `amount`,
--       `owner_id` naming.  If sharing that table, add the alias columns in SECTION 8.
-- ----------------------------------------------------------

CREATE TABLE IF NOT EXISTS deals (
    id          UUID           NOT NULL PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id   UUID           NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    account_id  UUID           REFERENCES accounts(id) ON DELETE SET NULL,
    -- stage uses TEXT (not enum) so the Rust code can cast: stage::text
    -- values: prospecting, qualification, proposal, negotiation, closed_won, closed_lost
    stage       TEXT           NOT NULL,
    -- `value` is what the analytics Rust queries reference (NOT `amount`)
    value       NUMERIC(14, 2) NOT NULL DEFAULT 0,
    -- probability: 0.0 – 1.0 for weighted-pipeline forecast
    probability NUMERIC(5, 4)  NOT NULL DEFAULT 0,
    close_date  DATE,
    -- assigned_to: FK to users.id — used in deal velocity rep breakdown
    assigned_to UUID           REFERENCES users(id) ON DELETE SET NULL,
    created_at  TIMESTAMPTZ    NOT NULL DEFAULT NOW(),
    -- closed_at: set when stage IN ('closed_won', 'closed_lost')
    closed_at   TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS ix_deals_tenant_id        ON deals (tenant_id);
CREATE INDEX IF NOT EXISTS ix_deals_tenant_stage      ON deals (tenant_id, stage);
CREATE INDEX IF NOT EXISTS ix_deals_tenant_created    ON deals (tenant_id, created_at);
CREATE INDEX IF NOT EXISTS ix_deals_assigned_to       ON deals (tenant_id, assigned_to);

ALTER TABLE deals ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS mcp_tenant_isolation ON deals;
CREATE POLICY mcp_tenant_isolation ON deals
    USING     (tenant_id::text = current_setting('app.current_tenant_id', true))
    WITH CHECK (tenant_id::text = current_setting('app.current_tenant_id', true));


-- ----------------------------------------------------------
-- 7b. activities
-- ----------------------------------------------------------
-- Queried by: mcp-analytics/src/tools/performance.rs get_rep_performance()
--   SELECT COUNT(*) FROM activities
--   WHERE tenant_id = $1 AND performed_by = $2
--     AND occurred_at::date BETWEEN $3 AND $4
-- Queried by: mcp-analytics/src/tools/activity.rs get_activity_metrics()
--   SELECT activity_type::text, COUNT(*) FROM activities
--   WHERE tenant_id = $1 AND occurred_at::date BETWEEN ...
--     AND ($4::uuid IS NULL OR performed_by = $4)
--     AND ($5::text IS NULL OR activity_type::text = $5)
--   GROUP BY activity_type
-- Queried by: mcp-analytics/src/tools/churn.rs get_at_risk_accounts()
--   LEFT JOIN activities act ON act.entity_id = a.id AND act.tenant_id = a.tenant_id
--   MAX(act.occurred_at)  →  last_activity_days_ago
-- ----------------------------------------------------------

CREATE TABLE IF NOT EXISTS activities (
    id            UUID         NOT NULL PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id     UUID         NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    -- entity_id: the account/deal/contact this activity belongs to
    entity_id     UUID,
    -- activity_type cast to TEXT in queries; typical values: call, email, meeting, task
    activity_type TEXT         NOT NULL,
    performed_by  UUID         REFERENCES users(id) ON DELETE SET NULL,
    occurred_at   TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    notes         TEXT,
    created_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_activities_tenant_id      ON activities (tenant_id);
CREATE INDEX IF NOT EXISTS ix_activities_tenant_date     ON activities (tenant_id, occurred_at);
CREATE INDEX IF NOT EXISTS ix_activities_performed_by    ON activities (tenant_id, performed_by);
CREATE INDEX IF NOT EXISTS ix_activities_entity_id       ON activities (tenant_id, entity_id);

ALTER TABLE activities ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS mcp_tenant_isolation ON activities;
CREATE POLICY mcp_tenant_isolation ON activities
    USING     (tenant_id::text = current_setting('app.current_tenant_id', true))
    WITH CHECK (tenant_id::text = current_setting('app.current_tenant_id', true));


-- ----------------------------------------------------------
-- 7c. quotas
-- ----------------------------------------------------------
-- Queried by: mcp-analytics/src/tools/performance.rs get_rep_performance()
--   SELECT COALESCE(SUM(amount), 0) FROM quotas
--   WHERE tenant_id = $1 AND user_id = $2
--     AND period_start <= $3 AND period_end >= $4
-- ----------------------------------------------------------

CREATE TABLE IF NOT EXISTS quotas (
    id           UUID           NOT NULL PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id    UUID           NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    user_id      UUID           NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    amount       NUMERIC(14, 2) NOT NULL,
    period_start DATE           NOT NULL,
    period_end   DATE           NOT NULL,
    created_at   TIMESTAMPTZ    NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_quotas_tenant_user ON quotas (tenant_id, user_id);

ALTER TABLE quotas ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS mcp_tenant_isolation ON quotas;
CREATE POLICY mcp_tenant_isolation ON quotas
    USING     (tenant_id::text = current_setting('app.current_tenant_id', true))
    WITH CHECK (tenant_id::text = current_setting('app.current_tenant_id', true));


-- ============================================================
-- SECTION 8 — audit_events  (shared by BOTH mcp-billing AND mcp-analytics)
-- ============================================================
-- billing write_audit INSERT:
--   (id, tenant_id, user_id, tool_name, params_hash, result_code,
--    duration_ms, timestamp, metadata)       ← includes metadata JSONB
-- analytics write_audit INSERT:
--   (id, tenant_id, user_id, tool_name, params_hash, result_code,
--    duration_ms, timestamp)                 ← no metadata column
-- → metadata is nullable to satisfy both callers
-- ============================================================

CREATE TABLE IF NOT EXISTS audit_events (
    id          UUID         NOT NULL PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id   UUID         NOT NULL,
    user_id     UUID,
    tool_name   VARCHAR(100) NOT NULL,
    -- SHA-256 hex digest of sanitised input params (64 chars)
    params_hash VARCHAR(64)  NOT NULL,
    result_code VARCHAR(50)  NOT NULL,
    duration_ms BIGINT       NOT NULL,
    -- column named `timestamp` exactly as bound in the Rust INSERT
    "timestamp" TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    -- nullable: only mcp-billing populates this field
    metadata    JSONB
);

CREATE INDEX IF NOT EXISTS ix_audit_events_tenant_id   ON audit_events (tenant_id);
CREATE INDEX IF NOT EXISTS ix_audit_events_tool_name   ON audit_events (tenant_id, tool_name);
CREATE INDEX IF NOT EXISTS ix_audit_events_timestamp   ON audit_events (tenant_id, "timestamp" DESC);

ALTER TABLE audit_events ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS mcp_tenant_isolation ON audit_events;
-- Audit is append-only from the tenant's own perspective; reads are unrestricted
-- by RLS (admin tools query cross-tenant). Adjust as needed.
CREATE POLICY mcp_tenant_isolation ON audit_events
    USING     (tenant_id::text = current_setting('app.current_tenant_id', true))
    WITH CHECK (tenant_id::text = current_setting('app.current_tenant_id', true));


-- ============================================================
-- SECTION 9 — Bridge ALTER TABLE statements
-- ============================================================
-- Run these ONLY when applying this schema on top of an existing
-- backend database that was created by the Alembic 0001-0005 migrations.
-- They are safe to run repeatedly (ADD COLUMN IF NOT EXISTS).
-- ============================================================

-- organizations: add columns required by validate_tenant() and list_overdue_payments()
ALTER TABLE organizations
    ADD COLUMN IF NOT EXISTS active        BOOLEAN      NOT NULL DEFAULT true,
    ADD COLUMN IF NOT EXISTS billing_email VARCHAR(255);

-- users: add the column names the Rust code uses
--   `tenant_id`  = physical alias for `org_id`
--   `active`     = physical alias for `is_active`
--   `name`       = physical alias for `full_name`
--
-- PostgreSQL does NOT support generated columns that merely alias another column
-- (stored generated columns require a deterministic expression). We therefore
-- add real columns and keep them in sync via triggers below.

ALTER TABLE users
    ADD COLUMN IF NOT EXISTS tenant_id UUID,
    ADD COLUMN IF NOT EXISTS active    BOOLEAN NOT NULL DEFAULT true,
    ADD COLUMN IF NOT EXISTS name      VARCHAR(255);

-- Back-fill from the existing columns on first apply
UPDATE users
SET tenant_id = org_id,
    active    = is_active,
    name      = full_name
WHERE tenant_id IS NULL;

-- Trigger: keep tenant_id / active / name in sync when their source columns change
CREATE OR REPLACE FUNCTION sync_user_mcp_columns()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    NEW.tenant_id := COALESCE(NEW.tenant_id, NEW.org_id);
    NEW.active    := COALESCE(NEW.active,    NEW.is_active);
    NEW.name      := COALESCE(NEW.name,      NEW.full_name);
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_sync_user_mcp_columns ON users;
CREATE TRIGGER trg_sync_user_mcp_columns
    BEFORE INSERT OR UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION sync_user_mcp_columns();

-- deals: the existing CRM table uses `org_id` / `amount` / `owner_id`
--        add alias columns so the analytics Rust queries resolve correctly
ALTER TABLE deals
    ADD COLUMN IF NOT EXISTS tenant_id  UUID,
    ADD COLUMN IF NOT EXISTS value      NUMERIC(14, 2),
    ADD COLUMN IF NOT EXISTS assigned_to UUID;

UPDATE deals
SET tenant_id   = org_id,
    value       = amount,
    assigned_to = owner_id
WHERE tenant_id IS NULL;

CREATE OR REPLACE FUNCTION sync_deal_mcp_columns()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    NEW.tenant_id   := COALESCE(NEW.tenant_id,   NEW.org_id);
    NEW.value       := COALESCE(NEW.value,        NEW.amount);
    NEW.assigned_to := COALESCE(NEW.assigned_to,  NEW.owner_id);
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_sync_deal_mcp_columns ON deals;
CREATE TRIGGER trg_sync_deal_mcp_columns
    BEFORE INSERT OR UPDATE ON deals
    FOR EACH ROW EXECUTE FUNCTION sync_deal_mcp_columns();

-- accounts: the existing CRM table uses `org_id`; add `tenant_id` alias
ALTER TABLE accounts
    ADD COLUMN IF NOT EXISTS tenant_id UUID;

UPDATE accounts SET tenant_id = org_id WHERE tenant_id IS NULL;

CREATE OR REPLACE FUNCTION sync_account_mcp_columns()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    NEW.tenant_id := COALESCE(NEW.tenant_id, NEW.org_id);
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_sync_account_mcp_columns ON accounts;
CREATE TRIGGER trg_sync_account_mcp_columns
    BEFORE INSERT OR UPDATE ON accounts
    FOR EACH ROW EXECUTE FUNCTION sync_account_mcp_columns();


-- ============================================================
-- SECTION 10 — updated_at auto-update trigger (subscriptions)
-- ============================================================
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    NEW.updated_at := NOW();
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_subscriptions_updated_at ON subscriptions;
CREATE TRIGGER trg_subscriptions_updated_at
    BEFORE UPDATE ON subscriptions
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

DROP TRIGGER IF EXISTS trg_accounts_updated_at ON accounts;
CREATE TRIGGER trg_accounts_updated_at
    BEFORE UPDATE ON accounts
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();


-- ============================================================
-- END OF FILE
-- ============================================================
