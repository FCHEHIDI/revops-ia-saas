-- ============================================================
-- 03_seed_demo.sql — Données de démonstration
-- ============================================================
-- Insère un tenant de démonstration complet avec des données
-- réalistes couvrant l'ensemble des features du dashboard.
--
-- Idempotent : chaque INSERT utilise ON CONFLICT DO NOTHING.
-- Sûr à relancer sans effet de bord.
--
-- Demo tenant : 00000000-0000-0000-0000-000000000001
-- Demo user   : 00000000-0000-0000-0000-000000000010
--
-- Ordre d'exécution (dépendances FK respectées) :
--   01_extensions.sql → 02_mcp_billing_analytics_schema.sql → CE FICHIER
-- ============================================================

-- ────────────────────────────────────────────────────────────
-- 0. Bypass RLS pour toute la session seed
-- ────────────────────────────────────────────────────────────
SELECT set_config('app.current_tenant_id', '00000000-0000-0000-0000-000000000001', false);


-- ────────────────────────────────────────────────────────────
-- 1. Enum types supplémentaires (sequences — absents de 02_)
-- ────────────────────────────────────────────────────────────
DO $$ BEGIN
    CREATE TYPE sequence_status AS ENUM ('draft', 'active', 'paused', 'archived');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE TYPE step_type AS ENUM ('email', 'linkedin_message', 'task', 'call', 'wait');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE TYPE exit_condition_type AS ENUM (
        'replied', 'clicked', 'meeting_booked', 'manual_unenroll', 'deal_stage_changed'
    );
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE TYPE enrollment_status AS ENUM (
        'pending', 'active', 'paused', 'completed', 'unenrolled', 'failed'
    );
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;


-- ────────────────────────────────────────────────────────────
-- 2. Table contacts (créée par Alembic 0002 — absente de 02_)
--    Colonne `org_id` pour compatibilité SQLAlchemy backend.
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS contacts (
    id         UUID         NOT NULL PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id     UUID         NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    account_id UUID         REFERENCES accounts(id) ON DELETE SET NULL,
    first_name VARCHAR(255) NOT NULL,
    last_name  VARCHAR(255) NOT NULL,
    email      VARCHAR(255) NOT NULL,
    phone      VARCHAR(50),
    job_title  VARCHAR(150),
    status     VARCHAR(50)  NOT NULL DEFAULT 'active',
    created_by UUID         REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX        IF NOT EXISTS ix_contacts_org_id      ON contacts (org_id);
CREATE UNIQUE INDEX IF NOT EXISTS uq_contacts_org_email   ON contacts (org_id, email);

ALTER TABLE contacts ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON contacts;
CREATE POLICY tenant_isolation ON contacts
    USING     (org_id::text = current_setting('app.current_tenant_id', true))
    WITH CHECK (org_id::text = current_setting('app.current_tenant_id', true));


-- ────────────────────────────────────────────────────────────
-- 3. Tables sequences / sequence_steps (absentes de 02_)
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS sequences (
    id              UUID            NOT NULL PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID            NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    name            VARCHAR(255)    NOT NULL,
    description     TEXT,
    status          sequence_status NOT NULL DEFAULT 'draft',
    exit_conditions JSONB           NOT NULL DEFAULT '[]',
    tags            TEXT[]          NOT NULL DEFAULT '{}',
    created_by      UUID            REFERENCES users(id) ON DELETE SET NULL,
    created_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_sequences_tenant_id     ON sequences (tenant_id);
CREATE INDEX IF NOT EXISTS ix_sequences_tenant_status ON sequences (tenant_id, status);

ALTER TABLE sequences ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS mcp_tenant_isolation ON sequences;
CREATE POLICY mcp_tenant_isolation ON sequences
    USING     (tenant_id::text = current_setting('app.current_tenant_id', true))
    WITH CHECK (tenant_id::text = current_setting('app.current_tenant_id', true));


CREATE TABLE IF NOT EXISTS sequence_steps (
    id            UUID      NOT NULL PRIMARY KEY DEFAULT gen_random_uuid(),
    sequence_id   UUID      NOT NULL REFERENCES sequences(id) ON DELETE CASCADE,
    tenant_id     UUID      NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    position      INTEGER   NOT NULL,
    step_type     step_type NOT NULL DEFAULT 'email',
    delay_days    INTEGER   NOT NULL DEFAULT 0,
    delay_hours   INTEGER   NOT NULL DEFAULT 0,
    template_id   UUID,
    subject       TEXT,
    body_template TEXT
);

CREATE INDEX IF NOT EXISTS ix_sequence_steps_sequence ON sequence_steps (sequence_id);


-- ────────────────────────────────────────────────────────────
-- 4. Bridges de compatibilité backend ↔ initdb
--    La 02_mcp_billing crée accounts avec `tenant_id`.
--    Le backend FastAPI (SQLAlchemy) utilise `org_id`.
--    On ajoute org_id comme alias pour éviter les erreurs ORM.
-- ────────────────────────────────────────────────────────────
ALTER TABLE accounts ADD COLUMN IF NOT EXISTS org_id UUID;
UPDATE accounts SET org_id = tenant_id WHERE org_id IS NULL;

-- deals : la 02_ crée avec `tenant_id` / `value` / `assigned_to`
-- Le backend CRM utilise `org_id` / `amount` / `owner_id`
ALTER TABLE deals ADD COLUMN IF NOT EXISTS org_id     UUID;
ALTER TABLE deals ADD COLUMN IF NOT EXISTS amount     NUMERIC(14, 2);
ALTER TABLE deals ADD COLUMN IF NOT EXISTS owner_id   UUID;
UPDATE deals SET org_id = tenant_id, amount = value, owner_id = assigned_to
WHERE org_id IS NULL;


-- ============================================================
-- SECTION A — Organisation (tenant de démo)
-- ============================================================
INSERT INTO organizations (id, name, slug, plan, active, billing_email, created_at)
VALUES (
    '00000000-0000-0000-0000-000000000001',
    'Acme RevOps',
    'acme-revops',
    'enterprise',
    true,
    'billing@acme-revops.io',
    NOW() - INTERVAL '18 months'
)
ON CONFLICT (id) DO NOTHING;


-- ============================================================
-- SECTION B — Utilisateur démo (admin RevOps)
-- ============================================================
INSERT INTO users (
    id, tenant_id, email, password_hash,
    name, full_name, job_title,
    roles, permissions, active, is_active, created_at
)
VALUES (
    '00000000-0000-0000-0000-000000000010',
    '00000000-0000-0000-0000-000000000001',
    'demo@acme-revops.io',
    -- bcrypt de 'demo1234' (cost=12) — placeholder non-utilisé en prod
    '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewdBPj2NJqhN8.',
    'Sarah Dupont',
    'Sarah Dupont',
    'Head of Revenue Operations',
    ARRAY['admin'],
    ARRAY[
        'crm:read','crm:write',
        'billing:read','billing:write',
        'analytics:read',
        'sequences:read','sequences:write'
    ],
    true,
    true,
    NOW() - INTERVAL '18 months'
)
ON CONFLICT (id) DO NOTHING;

-- Permission billing (vérifiée par mcp-billing)
INSERT INTO user_permissions (user_id, tenant_id, permission, granted_at)
VALUES (
    '00000000-0000-0000-0000-000000000010',
    '00000000-0000-0000-0000-000000000001',
    'billing:subscriptions:write',
    NOW()
)
ON CONFLICT DO NOTHING;

-- Carte bancaire de démo
INSERT INTO payment_methods (id, tenant_id, last4, brand, is_default, created_at)
VALUES (
    '00000000-0000-0000-0000-000000000020',
    '00000000-0000-0000-0000-000000000001',
    '4242', 'Visa', true,
    NOW() - INTERVAL '12 months'
)
ON CONFLICT (id) DO NOTHING;


-- ============================================================
-- SECTION C — Comptes clients (5)
-- ============================================================
INSERT INTO accounts (id, tenant_id, org_id, name, domain, industry, size, status, created_at, updated_at)
VALUES
    ('11111111-1111-1111-1111-000000000001',
     '00000000-0000-0000-0000-000000000001',
     '00000000-0000-0000-0000-000000000001',
     'Datastream SaaS',    'datastream.io',    'SaaS',       'enterprise', 'active',
     NOW() - INTERVAL '14 months', NOW()),

    ('11111111-1111-1111-1111-000000000002',
     '00000000-0000-0000-0000-000000000001',
     '00000000-0000-0000-0000-000000000001',
     'FinBridge Solutions', 'finbridge.com',   'FinTech',    'mid-market', 'active',
     NOW() - INTERVAL '10 months', NOW()),

    ('11111111-1111-1111-1111-000000000003',
     '00000000-0000-0000-0000-000000000001',
     '00000000-0000-0000-0000-000000000001',
     'NovaSky Cloud',      'novasky.cloud',    'Cloud/SaaS', 'smb',        'active',
     NOW() - INTERVAL '6 months',  NOW()),

    ('11111111-1111-1111-1111-000000000004',
     '00000000-0000-0000-0000-000000000001',
     '00000000-0000-0000-0000-000000000001',
     'RetailEdge Pro',     'retailedge.fr',    'Retail',     'enterprise', 'active',
     NOW() - INTERVAL '12 months', NOW()),

    ('11111111-1111-1111-1111-000000000005',
     '00000000-0000-0000-0000-000000000001',
     '00000000-0000-0000-0000-000000000001',
     'MediCore Health',    'medicore.health',  'Healthcare', 'mid-market', 'churned',
     NOW() - INTERVAL '20 months', NOW())
ON CONFLICT (id) DO NOTHING;


-- ============================================================
-- SECTION D — Contacts (20 — 4 par compte)
-- ============================================================
INSERT INTO contacts (
    id, org_id, account_id, first_name, last_name, email,
    phone, job_title, status, created_by, created_at
)
VALUES
    -- Datastream SaaS ─────────────────────────────────────────
    ('22222222-2222-2222-2222-000000000001',
     '00000000-0000-0000-0000-000000000001', '11111111-1111-1111-1111-000000000001',
     'Alice',    'Martin',  'alice.martin@datastream.io',   '+33612345601',
     'VP Sales',           'active',   '00000000-0000-0000-0000-000000000010',
     NOW() - INTERVAL '13 months'),

    ('22222222-2222-2222-2222-000000000002',
     '00000000-0000-0000-0000-000000000001', '11111111-1111-1111-1111-000000000001',
     'Baptiste', 'Leroy',   'b.leroy@datastream.io',        '+33612345602',
     'CTO',                'active',   '00000000-0000-0000-0000-000000000010',
     NOW() - INTERVAL '13 months'),

    ('22222222-2222-2222-2222-000000000003',
     '00000000-0000-0000-0000-000000000001', '11111111-1111-1111-1111-000000000001',
     'Clara',    'Dubois',  'clara.dubois@datastream.io',   '+33612345603',
     'Head of Product',    'active',   '00000000-0000-0000-0000-000000000010',
     NOW() - INTERVAL '12 months'),

    ('22222222-2222-2222-2222-000000000004',
     '00000000-0000-0000-0000-000000000001', '11111111-1111-1111-1111-000000000001',
     'David',    'Nkosi',   'd.nkosi@datastream.io',        '+33612345604',
     'Account Manager',    'lead',     '00000000-0000-0000-0000-000000000010',
     NOW() - INTERVAL '3 months'),

    -- FinBridge Solutions ──────────────────────────────────────
    ('22222222-2222-2222-2222-000000000005',
     '00000000-0000-0000-0000-000000000001', '11111111-1111-1111-1111-000000000002',
     'Emma',     'Rousseau','emma.rousseau@finbridge.com',  '+33612345605',
     'CEO',                'customer', '00000000-0000-0000-0000-000000000010',
     NOW() - INTERVAL '9 months'),

    ('22222222-2222-2222-2222-000000000006',
     '00000000-0000-0000-0000-000000000001', '11111111-1111-1111-1111-000000000002',
     'François', 'Bernard', 'f.bernard@finbridge.com',      '+33612345606',
     'CFO',                'active',   '00000000-0000-0000-0000-000000000010',
     NOW() - INTERVAL '9 months'),

    ('22222222-2222-2222-2222-000000000007',
     '00000000-0000-0000-0000-000000000001', '11111111-1111-1111-1111-000000000002',
     'Gabrielle','Petit',   'g.petit@finbridge.com',        '+33612345607',
     'DevOps Lead',        'active',   '00000000-0000-0000-0000-000000000010',
     NOW() - INTERVAL '8 months'),

    ('22222222-2222-2222-2222-000000000008',
     '00000000-0000-0000-0000-000000000001', '11111111-1111-1111-1111-000000000002',
     'Hugo',     'Martin',  'h.martin@finbridge.com',       '+33612345608',
     'Sales Director',     'lead',     '00000000-0000-0000-0000-000000000010',
     NOW() - INTERVAL '2 months'),

    -- NovaSky Cloud ────────────────────────────────────────────
    ('22222222-2222-2222-2222-000000000009',
     '00000000-0000-0000-0000-000000000001', '11111111-1111-1111-1111-000000000003',
     'Inès',     'Laurent', 'ines.laurent@novasky.cloud',   '+33612345609',
     'CTO',                'active',   '00000000-0000-0000-0000-000000000010',
     NOW() - INTERVAL '5 months'),

    ('22222222-2222-2222-2222-000000000010',
     '00000000-0000-0000-0000-000000000001', '11111111-1111-1111-1111-000000000003',
     'Jules',    'Moreau',  'j.moreau@novasky.cloud',       '+33612345610',
     'Head of Engineering','active',   '00000000-0000-0000-0000-000000000010',
     NOW() - INTERVAL '5 months'),

    ('22222222-2222-2222-2222-000000000011',
     '00000000-0000-0000-0000-000000000001', '11111111-1111-1111-1111-000000000003',
     'Karine',   'Simon',   'k.simon@novasky.cloud',        '+33612345611',
     'Product Manager',    'lead',     '00000000-0000-0000-0000-000000000010',
     NOW() - INTERVAL '1 month'),

    ('22222222-2222-2222-2222-000000000012',
     '00000000-0000-0000-0000-000000000001', '11111111-1111-1111-1111-000000000003',
     'Liam',     'Dumont',  'l.dumont@novasky.cloud',       '+33612345612',
     'Solutions Architect','active',   '00000000-0000-0000-0000-000000000010',
     NOW() - INTERVAL '4 months'),

    -- RetailEdge Pro ───────────────────────────────────────────
    ('22222222-2222-2222-2222-000000000013',
     '00000000-0000-0000-0000-000000000001', '11111111-1111-1111-1111-000000000004',
     'Marie',    'Girard',  'marie.girard@retailedge.fr',   '+33612345613',
     'CEO',                'customer', '00000000-0000-0000-0000-000000000010',
     NOW() - INTERVAL '11 months'),

    ('22222222-2222-2222-2222-000000000014',
     '00000000-0000-0000-0000-000000000001', '11111111-1111-1111-1111-000000000004',
     'Nicolas',  'Lambert', 'n.lambert@retailedge.fr',      '+33612345614',
     'VP Operations',      'active',   '00000000-0000-0000-0000-000000000010',
     NOW() - INTERVAL '11 months'),

    ('22222222-2222-2222-2222-000000000015',
     '00000000-0000-0000-0000-000000000001', '11111111-1111-1111-1111-000000000004',
     'Océane',   'Blanc',   'o.blanc@retailedge.fr',        '+33612345615',
     'Head of IT',         'active',   '00000000-0000-0000-0000-000000000010',
     NOW() - INTERVAL '10 months'),

    ('22222222-2222-2222-2222-000000000016',
     '00000000-0000-0000-0000-000000000001', '11111111-1111-1111-1111-000000000004',
     'Pierre',   'Faure',   'p.faure@retailedge.fr',        '+33612345616',
     'Sales Lead',         'churned',  '00000000-0000-0000-0000-000000000010',
     NOW() - INTERVAL '8 months'),

    -- MediCore Health ──────────────────────────────────────────
    ('22222222-2222-2222-2222-000000000017',
     '00000000-0000-0000-0000-000000000001', '11111111-1111-1111-1111-000000000005',
     'Quentin',  'Renard',  'q.renard@medicore.health',     '+33612345617',
     'CEO',                'churned',  '00000000-0000-0000-0000-000000000010',
     NOW() - INTERVAL '18 months'),

    ('22222222-2222-2222-2222-000000000018',
     '00000000-0000-0000-0000-000000000001', '11111111-1111-1111-1111-000000000005',
     'Raphaëlle','Clément', 'r.clement@medicore.health',    '+33612345618',
     'CTO',                'churned',  '00000000-0000-0000-0000-000000000010',
     NOW() - INTERVAL '18 months'),

    ('22222222-2222-2222-2222-000000000019',
     '00000000-0000-0000-0000-000000000001', '11111111-1111-1111-1111-000000000005',
     'Stéphane', 'Barbier', 's.barbier@medicore.health',    '+33612345619',
     'Sales Manager',      'churned',  '00000000-0000-0000-0000-000000000010',
     NOW() - INTERVAL '16 months'),

    ('22222222-2222-2222-2222-000000000020',
     '00000000-0000-0000-0000-000000000001', '11111111-1111-1111-1111-000000000005',
     'Thomas',   'Morin',   't.morin@medicore.health',      '+33612345620',
     'Account Executive',  'churned',  '00000000-0000-0000-0000-000000000010',
     NOW() - INTERVAL '15 months')
ON CONFLICT (org_id, email) DO NOTHING;


-- ============================================================
-- SECTION E — Abonnements (5)
-- ============================================================
INSERT INTO subscriptions (
    id, tenant_id, account_id,
    plan_id, plan_name, status,
    seats, mrr, currency,
    current_period_start, current_period_end,
    cancel_at_period_end, trial_end,
    features, started_at, created_at, updated_at
)
VALUES
    -- Datastream — Enterprise, active, MRR 8 500 €
    ('33333333-3333-3333-3333-000000000001',
     '00000000-0000-0000-0000-000000000001', '11111111-1111-1111-1111-000000000001',
     'enterprise', 'Enterprise', 'active',
     50, 8500.00, 'EUR',
     DATE_TRUNC('month', NOW()),
     DATE_TRUNC('month', NOW()) + INTERVAL '1 month' - INTERVAL '1 day',
     false, NULL,
     '["sso","api_access","dedicated_support","custom_roles","analytics_advanced"]',
     NOW() - INTERVAL '14 months',
     NOW() - INTERVAL '14 months', NOW()),

    -- FinBridge — Professional, active, MRR 3 200 €
    ('33333333-3333-3333-3333-000000000002',
     '00000000-0000-0000-0000-000000000001', '11111111-1111-1111-1111-000000000002',
     'professional', 'Professional', 'active',
     15, 3200.00, 'EUR',
     DATE_TRUNC('month', NOW()),
     DATE_TRUNC('month', NOW()) + INTERVAL '1 month' - INTERVAL '1 day',
     false, NULL,
     '["api_access","analytics_basic","sequences"]',
     NOW() - INTERVAL '10 months',
     NOW() - INTERVAL '10 months', NOW()),

    -- NovaSky — Starter, trialing, MRR 990 € (trial expire dans 8 j)
    ('33333333-3333-3333-3333-000000000003',
     '00000000-0000-0000-0000-000000000001', '11111111-1111-1111-1111-000000000003',
     'starter', 'Starter', 'trialing',
     5, 990.00, 'EUR',
     DATE_TRUNC('month', NOW()),
     DATE_TRUNC('month', NOW()) + INTERVAL '1 month' - INTERVAL '1 day',
     false, NOW() + INTERVAL '8 days',
     '["basic_crm","sequences"]',
     NOW() - INTERVAL '22 days',
     NOW() - INTERVAL '22 days', NOW()),

    -- RetailEdge — Professional, past_due (factures en retard)
    ('33333333-3333-3333-3333-000000000004',
     '00000000-0000-0000-0000-000000000001', '11111111-1111-1111-1111-000000000004',
     'professional', 'Professional', 'past_due',
     20, 3200.00, 'EUR',
     DATE_TRUNC('month', NOW()) - INTERVAL '1 month',
     DATE_TRUNC('month', NOW()) - INTERVAL '1 day',
     false, NULL,
     '["api_access","analytics_basic","sequences"]',
     NOW() - INTERVAL '12 months',
     NOW() - INTERVAL '12 months', NOW()),

    -- MediCore — Starter, canceled (churned il y a 8 mois)
    ('33333333-3333-3333-3333-000000000005',
     '00000000-0000-0000-0000-000000000001', '11111111-1111-1111-1111-000000000005',
     'starter', 'Starter', 'canceled',
     3, 990.00, 'EUR',
     NOW() - INTERVAL '20 months',
     NOW() - INTERVAL '8 months',
     true, NULL,
     '["basic_crm"]',
     NOW() - INTERVAL '20 months',
     NOW() - INTERVAL '20 months', NOW() - INTERVAL '8 months')
ON CONFLICT (id) DO NOTHING;

-- Dater le churn de MediCore
UPDATE subscriptions
SET churned_at = NOW() - INTERVAL '8 months'
WHERE id = '33333333-3333-3333-3333-000000000005';


-- ============================================================
-- SECTION F — Factures (12 — mix paid / overdue / pending / void)
-- ============================================================
INSERT INTO invoices (
    id, tenant_id, subscription_id, account_id,
    invoice_number, status, amount, currency,
    due_date, paid_at, created_at
)
VALUES
    -- Datastream : 3 payées + 1 en attente ────────────────────
    ('44444444-4444-4444-4444-000000000001',
     '00000000-0000-0000-0000-000000000001',
     '33333333-3333-3333-3333-000000000001', '11111111-1111-1111-1111-000000000001',
     'INV-2025-001', 'paid', 8500.00, 'EUR',
     (NOW() - INTERVAL '3 months')::date,
     NOW() - INTERVAL '3 months' + INTERVAL '2 days',
     NOW() - INTERVAL '3 months'),

    ('44444444-4444-4444-4444-000000000002',
     '00000000-0000-0000-0000-000000000001',
     '33333333-3333-3333-3333-000000000001', '11111111-1111-1111-1111-000000000001',
     'INV-2025-002', 'paid', 8500.00, 'EUR',
     (NOW() - INTERVAL '2 months')::date,
     NOW() - INTERVAL '2 months' + INTERVAL '3 days',
     NOW() - INTERVAL '2 months'),

    ('44444444-4444-4444-4444-000000000003',
     '00000000-0000-0000-0000-000000000001',
     '33333333-3333-3333-3333-000000000001', '11111111-1111-1111-1111-000000000001',
     'INV-2025-003', 'paid', 8500.00, 'EUR',
     (NOW() - INTERVAL '1 month')::date,
     NOW() - INTERVAL '1 month' + INTERVAL '1 day',
     NOW() - INTERVAL '1 month'),

    ('44444444-4444-4444-4444-000000000004',
     '00000000-0000-0000-0000-000000000001',
     '33333333-3333-3333-3333-000000000001', '11111111-1111-1111-1111-000000000001',
     'INV-2025-004', 'pending', 8500.00, 'EUR',
     (NOW() + INTERVAL '5 days')::date,
     NULL, NOW()),

    -- FinBridge : 2 payées ─────────────────────────────────────
    ('44444444-4444-4444-4444-000000000005',
     '00000000-0000-0000-0000-000000000001',
     '33333333-3333-3333-3333-000000000002', '11111111-1111-1111-1111-000000000002',
     'INV-2025-005', 'paid', 3200.00, 'EUR',
     (NOW() - INTERVAL '2 months')::date,
     NOW() - INTERVAL '2 months' + INTERVAL '5 days',
     NOW() - INTERVAL '2 months'),

    ('44444444-4444-4444-4444-000000000006',
     '00000000-0000-0000-0000-000000000001',
     '33333333-3333-3333-3333-000000000002', '11111111-1111-1111-1111-000000000002',
     'INV-2025-006', 'paid', 3200.00, 'EUR',
     (NOW() - INTERVAL '1 month')::date,
     NOW() - INTERVAL '1 month' + INTERVAL '2 days',
     NOW() - INTERVAL '1 month'),

    -- NovaSky : draft (période de trial) ──────────────────────
    ('44444444-4444-4444-4444-000000000007',
     '00000000-0000-0000-0000-000000000001',
     '33333333-3333-3333-3333-000000000003', '11111111-1111-1111-1111-000000000003',
     'INV-2025-007', 'draft', 990.00, 'EUR',
     (NOW() + INTERVAL '8 days')::date,
     NULL, NOW()),

    -- RetailEdge : 2 OVERDUE (subscription past_due) ──────────
    ('44444444-4444-4444-4444-000000000008',
     '00000000-0000-0000-0000-000000000001',
     '33333333-3333-3333-3333-000000000004', '11111111-1111-1111-1111-000000000004',
     'INV-2025-008', 'overdue', 3200.00, 'EUR',
     (NOW() - INTERVAL '45 days')::date,
     NULL, NOW() - INTERVAL '45 days'),

    ('44444444-4444-4444-4444-000000000009',
     '00000000-0000-0000-0000-000000000001',
     '33333333-3333-3333-3333-000000000004', '11111111-1111-1111-1111-000000000004',
     'INV-2025-009', 'overdue', 3200.00, 'EUR',
     (NOW() - INTERVAL '15 days')::date,
     NULL, NOW() - INTERVAL '45 days'),

    -- MediCore : 2 payées (historique) + 1 void ───────────────
    ('44444444-4444-4444-4444-000000000010',
     '00000000-0000-0000-0000-000000000001',
     '33333333-3333-3333-3333-000000000005', '11111111-1111-1111-1111-000000000005',
     'INV-2024-001', 'paid', 990.00, 'EUR',
     (NOW() - INTERVAL '18 months')::date,
     NOW() - INTERVAL '18 months' + INTERVAL '3 days',
     NOW() - INTERVAL '18 months'),

    ('44444444-4444-4444-4444-000000000011',
     '00000000-0000-0000-0000-000000000001',
     '33333333-3333-3333-3333-000000000005', '11111111-1111-1111-1111-000000000005',
     'INV-2024-002', 'paid', 990.00, 'EUR',
     (NOW() - INTERVAL '17 months')::date,
     NOW() - INTERVAL '17 months' + INTERVAL '2 days',
     NOW() - INTERVAL '17 months'),

    ('44444444-4444-4444-4444-000000000012',
     '00000000-0000-0000-0000-000000000001',
     '33333333-3333-3333-3333-000000000005', '11111111-1111-1111-1111-000000000005',
     'INV-2024-003', 'void', 990.00, 'EUR',
     (NOW() - INTERVAL '8 months')::date,
     NULL, NOW() - INTERVAL '9 months')
ON CONFLICT (tenant_id, invoice_number) DO NOTHING;


-- ============================================================
-- SECTION G — Deals (6 — répartis sur toutes les étapes)
-- ============================================================
INSERT INTO deals (
    id, tenant_id, org_id, account_id,
    stage, value, amount, probability,
    close_date, assigned_to, owner_id, created_at
)
VALUES
    -- closed_won : Platform Expansion (Datastream)
    ('55555555-5555-5555-5555-000000000001',
     '00000000-0000-0000-0000-000000000001',
     '00000000-0000-0000-0000-000000000001',
     '11111111-1111-1111-1111-000000000001',
     'closed_won', 45000.00, 45000.00, 1.0000,
     (NOW() - INTERVAL '2 months')::date,
     '00000000-0000-0000-0000-000000000010',
     '00000000-0000-0000-0000-000000000010',
     NOW() - INTERVAL '5 months'),

    -- negotiation : API Integration Pack (FinBridge)
    ('55555555-5555-5555-5555-000000000002',
     '00000000-0000-0000-0000-000000000001',
     '00000000-0000-0000-0000-000000000001',
     '11111111-1111-1111-1111-000000000002',
     'negotiation', 28000.00, 28000.00, 0.8000,
     (NOW() + INTERVAL '15 days')::date,
     '00000000-0000-0000-0000-000000000010',
     '00000000-0000-0000-0000-000000000010',
     NOW() - INTERVAL '2 months'),

    -- proposal : Cloud Migration (NovaSky)
    ('55555555-5555-5555-5555-000000000003',
     '00000000-0000-0000-0000-000000000001',
     '00000000-0000-0000-0000-000000000001',
     '11111111-1111-1111-1111-000000000003',
     'proposal', 15000.00, 15000.00, 0.6000,
     (NOW() + INTERVAL '30 days')::date,
     '00000000-0000-0000-0000-000000000010',
     '00000000-0000-0000-0000-000000000010',
     NOW() - INTERVAL '6 weeks'),

    -- qualification : Enterprise License Renewal (RetailEdge)
    ('55555555-5555-5555-5555-000000000004',
     '00000000-0000-0000-0000-000000000001',
     '00000000-0000-0000-0000-000000000001',
     '11111111-1111-1111-1111-000000000004',
     'qualification', 32000.00, 32000.00, 0.3000,
     (NOW() + INTERVAL '60 days')::date,
     '00000000-0000-0000-0000-000000000010',
     '00000000-0000-0000-0000-000000000010',
     NOW() - INTERVAL '3 weeks'),

    -- prospecting : Win-Back (MediCore)
    ('55555555-5555-5555-5555-000000000005',
     '00000000-0000-0000-0000-000000000001',
     '00000000-0000-0000-0000-000000000001',
     '11111111-1111-1111-1111-000000000005',
     'prospecting', 8500.00, 8500.00, 0.1000,
     (NOW() + INTERVAL '90 days')::date,
     '00000000-0000-0000-0000-000000000010',
     '00000000-0000-0000-0000-000000000010',
     NOW() - INTERVAL '1 week'),

    -- closed_won : AI Add-on (Datastream — second deal)
    ('55555555-5555-5555-5555-000000000006',
     '00000000-0000-0000-0000-000000000001',
     '00000000-0000-0000-0000-000000000001',
     '11111111-1111-1111-1111-000000000001',
     'closed_won', 22000.00, 22000.00, 1.0000,
     (NOW() - INTERVAL '1 month')::date,
     '00000000-0000-0000-0000-000000000010',
     '00000000-0000-0000-0000-000000000010',
     NOW() - INTERVAL '4 months')
ON CONFLICT (id) DO NOTHING;

-- Dater les deals fermés (utilisé par l'analytics revenue)
UPDATE deals
SET closed_at = close_date
WHERE stage = 'closed_won'
  AND tenant_id = '00000000-0000-0000-0000-000000000001';


-- ============================================================
-- SECTION H — Activités (10 — pour l'analytics rep performance)
-- ============================================================
INSERT INTO activities (
    id, tenant_id, entity_id, activity_type,
    performed_by, occurred_at, notes
)
VALUES
    ('66666666-6666-6666-6666-000000000001',
     '00000000-0000-0000-0000-000000000001', '11111111-1111-1111-1111-000000000001',
     'call', '00000000-0000-0000-0000-000000000010',
     NOW() - INTERVAL '8 days',  'Discovery call — confirmer budget Q2'),

    ('66666666-6666-6666-6666-000000000002',
     '00000000-0000-0000-0000-000000000001', '11111111-1111-1111-1111-000000000001',
     'email', '00000000-0000-0000-0000-000000000010',
     NOW() - INTERVAL '5 days',  'Envoi du devis renouvellement (PDF)'),

    ('66666666-6666-6666-6666-000000000003',
     '00000000-0000-0000-0000-000000000001', '11111111-1111-1111-1111-000000000002',
     'meeting', '00000000-0000-0000-0000-000000000010',
     NOW() - INTERVAL '12 days', 'Kick-off intégration API — FinBridge'),

    ('66666666-6666-6666-6666-000000000004',
     '00000000-0000-0000-0000-000000000001', '11111111-1111-1111-1111-000000000002',
     'email', '00000000-0000-0000-0000-000000000010',
     NOW() - INTERVAL '4 days',  'Relance sur le document SLA'),

    ('66666666-6666-6666-6666-000000000005',
     '00000000-0000-0000-0000-000000000001', '11111111-1111-1111-1111-000000000003',
     'call', '00000000-0000-0000-0000-000000000010',
     NOW() - INTERVAL '3 days',  'Health check trial — onboarding NovaSky'),

    ('66666666-6666-6666-6666-000000000006',
     '00000000-0000-0000-0000-000000000001', '11111111-1111-1111-1111-000000000003',
     'task', '00000000-0000-0000-0000-000000000010',
     NOW() - INTERVAL '1 day',   'Organiser session de formation équipe NovaSky'),

    ('66666666-6666-6666-6666-000000000007',
     '00000000-0000-0000-0000-000000000001', '11111111-1111-1111-1111-000000000004',
     'email', '00000000-0000-0000-0000-000000000010',
     NOW() - INTERVAL '20 days', 'Relance paiement — INV-2025-008 en retard'),

    ('66666666-6666-6666-6666-000000000008',
     '00000000-0000-0000-0000-000000000001', '11111111-1111-1111-1111-000000000004',
     'call', '00000000-0000-0000-0000-000000000010',
     NOW() - INTERVAL '10 days', 'Escalade compte at-risk — RetailEdge'),

    ('66666666-6666-6666-6666-000000000009',
     '00000000-0000-0000-0000-000000000001', '11111111-1111-1111-1111-000000000005',
     'email', '00000000-0000-0000-0000-000000000010',
     NOW() - INTERVAL '6 months','Campagne win-back MediCore — churn recovery'),

    ('66666666-6666-6666-6666-000000000010',
     '00000000-0000-0000-0000-000000000001', '22222222-2222-2222-2222-000000000001',
     'meeting', '00000000-0000-0000-0000-000000000010',
     NOW() - INTERVAL '2 days',  'QBR avec Alice Martin — expansion Datastream')
ON CONFLICT (id) DO NOTHING;


-- ============================================================
-- SECTION I — Quota commercial (rep performance analytics)
-- ============================================================
INSERT INTO quotas (id, tenant_id, user_id, amount, period_start, period_end)
VALUES (
    '77777777-7777-7777-7777-000000000001',
    '00000000-0000-0000-0000-000000000001',
    '00000000-0000-0000-0000-000000000010',
    120000.00,
    DATE_TRUNC('year', CURRENT_DATE)::date,
    (DATE_TRUNC('year', CURRENT_DATE) + INTERVAL '1 year' - INTERVAL '1 day')::date
)
ON CONFLICT (id) DO NOTHING;


-- ============================================================
-- SECTION J — Snapshots MRR (6 mois — tendance croissante)
-- ============================================================
INSERT INTO mrr_snapshots (
    id, tenant_id, snapshot_date,
    mrr, new_mrr, expansion_mrr, churned_mrr
)
VALUES
    ('88888888-8888-8888-8888-000000000001',
     '00000000-0000-0000-0000-000000000001',
     DATE_TRUNC('month', NOW() - INTERVAL '5 months')::date,
     11680.00, 3200.00, 0.00,    990.00),

    ('88888888-8888-8888-8888-000000000002',
     '00000000-0000-0000-0000-000000000001',
     DATE_TRUNC('month', NOW() - INTERVAL '4 months')::date,
     12690.00, 990.00,  1010.00, 0.00),

    ('88888888-8888-8888-8888-000000000003',
     '00000000-0000-0000-0000-000000000001',
     DATE_TRUNC('month', NOW() - INTERVAL '3 months')::date,
     13500.00, 0.00,    810.00,  0.00),

    ('88888888-8888-8888-8888-000000000004',
     '00000000-0000-0000-0000-000000000001',
     DATE_TRUNC('month', NOW() - INTERVAL '2 months')::date,
     14800.00, 1300.00, 0.00,    0.00),

    ('88888888-8888-8888-8888-000000000005',
     '00000000-0000-0000-0000-000000000001',
     DATE_TRUNC('month', NOW() - INTERVAL '1 month')::date,
     15690.00, 890.00,  0.00,    0.00),

    ('88888888-8888-8888-8888-000000000006',
     '00000000-0000-0000-0000-000000000001',
     DATE_TRUNC('month', NOW())::date,
     15690.00, 0.00,    0.00,    0.00)
ON CONFLICT (tenant_id, snapshot_date) DO NOTHING;


-- ============================================================
-- SECTION K — Séquences (2) + étapes
-- ============================================================
INSERT INTO sequences (
    id, tenant_id, name, description, status,
    exit_conditions, tags, created_by, created_at, updated_at
)
VALUES
    -- Séquence 1 : Onboarding Q2 2025 (active, 4 étapes)
    ('99999999-9999-9999-9999-000000000001',
     '00000000-0000-0000-0000-000000000001',
     'Onboarding Q2 2025',
     'Séquence d''accueil pour les nouveaux clients signés au Q2 2025',
     'active',
     '[{"condition_type":"replied","parameters":{}},{"condition_type":"meeting_booked","parameters":{}}]',
     ARRAY['onboarding','q2-2025'],
     '00000000-0000-0000-0000-000000000010',
     NOW() - INTERVAL '3 months', NOW()),

    -- Séquence 2 : Réactivation Churned (paused, 3 étapes)
    ('99999999-9999-9999-9999-000000000002',
     '00000000-0000-0000-0000-000000000001',
     'Réactivation Churned',
     'Campagne de réactivation pour les comptes churned depuis 3–6 mois',
     'paused',
     '[{"condition_type":"replied","parameters":{}},{"condition_type":"deal_stage_changed","parameters":{"target_stage":"qualification"}}]',
     ARRAY['win-back','churned'],
     '00000000-0000-0000-0000-000000000010',
     NOW() - INTERVAL '5 months', NOW() - INTERVAL '1 month')
ON CONFLICT (id) DO NOTHING;

-- Étapes — Onboarding Q2 (4 étapes)
INSERT INTO sequence_steps (
    id, sequence_id, tenant_id,
    position, step_type, delay_days, delay_hours,
    subject, body_template
)
VALUES
    ('aaaaaaaa-aaaa-aaaa-aaaa-000000000001',
     '99999999-9999-9999-9999-000000000001',
     '00000000-0000-0000-0000-000000000001',
     1, 'email', 0, 2,
     'Bienvenue chez RevOps IA !',
     'Bonjour {{first_name}}, bienvenue dans votre espace RevOps IA. Voici comment démarrer…'),

    ('aaaaaaaa-aaaa-aaaa-aaaa-000000000002',
     '99999999-9999-9999-9999-000000000001',
     '00000000-0000-0000-0000-000000000001',
     2, 'email', 3, 0,
     'Vos premières étapes avec RevOps IA',
     'Voici les 3 actions clés pour réussir votre intégration en semaine 1…'),

    ('aaaaaaaa-aaaa-aaaa-aaaa-000000000003',
     '99999999-9999-9999-9999-000000000001',
     '00000000-0000-0000-0000-000000000001',
     3, 'task', 5, 0,
     NULL,
     'Planifier un appel de suivi J+5 avec {{first_name}} pour valider l''avancement'),

    ('aaaaaaaa-aaaa-aaaa-aaaa-000000000004',
     '99999999-9999-9999-9999-000000000001',
     '00000000-0000-0000-0000-000000000001',
     4, 'email', 14, 0,
     'Comment se passe votre onboarding ?',
     'Bonjour {{first_name}}, 2 semaines déjà ! Partagez vos retours en 2 clics…')
ON CONFLICT (id) DO NOTHING;

-- Étapes — Réactivation Churned (3 étapes)
INSERT INTO sequence_steps (
    id, sequence_id, tenant_id,
    position, step_type, delay_days, delay_hours,
    subject, body_template
)
VALUES
    ('aaaaaaaa-aaaa-aaaa-aaaa-000000000005',
     '99999999-9999-9999-9999-000000000002',
     '00000000-0000-0000-0000-000000000001',
     1, 'email', 0, 0,
     'On pense à vous, {{first_name}}',
     'Depuis votre départ, nous avons lancé plusieurs nouvelles fonctionnalités qui vous auraient plu…'),

    ('aaaaaaaa-aaaa-aaaa-aaaa-000000000006',
     '99999999-9999-9999-9999-000000000002',
     '00000000-0000-0000-0000-000000000001',
     2, 'linkedin_message', 7, 0,
     NULL,
     'Bonjour {{first_name}}, avez-vous eu l''occasion de consulter notre nouvelle offre ?'),

    ('aaaaaaaa-aaaa-aaaa-aaaa-000000000007',
     '99999999-9999-9999-9999-000000000002',
     '00000000-0000-0000-0000-000000000001',
     3, 'call', 14, 0,
     NULL,
     'Appel de réactivation — proposer un essai gratuit 14 jours')
ON CONFLICT (id) DO NOTHING;


-- ============================================================
-- SECTION L — Résumé du seed
-- ============================================================
DO $$
DECLARE
    cnt_accounts  INT;
    cnt_contacts  INT;
    cnt_subs      INT;
    cnt_invoices  INT;
    cnt_deals     INT;
    cnt_sequences INT;
    cnt_steps     INT;
    cnt_activities INT;
BEGIN
    SELECT COUNT(*) INTO cnt_accounts   FROM accounts   WHERE tenant_id = '00000000-0000-0000-0000-000000000001';
    SELECT COUNT(*) INTO cnt_contacts   FROM contacts   WHERE org_id    = '00000000-0000-0000-0000-000000000001';
    SELECT COUNT(*) INTO cnt_subs       FROM subscriptions WHERE tenant_id = '00000000-0000-0000-0000-000000000001';
    SELECT COUNT(*) INTO cnt_invoices   FROM invoices   WHERE tenant_id = '00000000-0000-0000-0000-000000000001';
    SELECT COUNT(*) INTO cnt_deals      FROM deals      WHERE tenant_id = '00000000-0000-0000-0000-000000000001';
    SELECT COUNT(*) INTO cnt_sequences  FROM sequences  WHERE tenant_id = '00000000-0000-0000-0000-000000000001';
    SELECT COUNT(*) INTO cnt_steps      FROM sequence_steps WHERE tenant_id = '00000000-0000-0000-0000-000000000001';
    SELECT COUNT(*) INTO cnt_activities FROM activities WHERE tenant_id = '00000000-0000-0000-0000-000000000001';

    RAISE NOTICE '══════════════════════════════════════════════';
    RAISE NOTICE '  Seed demo — tenant 00000000-…-0001';
    RAISE NOTICE '  accounts     : %', cnt_accounts;
    RAISE NOTICE '  contacts     : %', cnt_contacts;
    RAISE NOTICE '  subscriptions: %', cnt_subs;
    RAISE NOTICE '  invoices     : %', cnt_invoices;
    RAISE NOTICE '  deals        : %', cnt_deals;
    RAISE NOTICE '  sequences    : %', cnt_sequences;
    RAISE NOTICE '  steps        : %', cnt_steps;
    RAISE NOTICE '  activities   : %', cnt_activities;
    RAISE NOTICE '══════════════════════════════════════════════';
END $$;
