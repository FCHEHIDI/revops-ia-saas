# mcp-billing

Serveur MCP de facturation et gestion des abonnements pour RevOps IA SaaS.

Ce serveur expose 8 tools MCP couvrant les domaines **factures**, **abonnements** et **métriques financières** (MRR/ARR).

---

## Architecture

- **Runtime** : Tokio async (Rust édition 2021)
- **Protocole** : `rmcp` (Rust MCP SDK)
- **Base de données** : PostgreSQL via `sqlx` (async, RLS enforced)
- **Transport** : stdio (défaut) ou SSE

### Invariants de sécurité (ADR-003, ADR-005)

1. **`validate_tenant()` est toujours appelé en premier** dans chaque handler — aucune requête ne s'exécute sans validation préalable du tenant.
2. **RLS PostgreSQL** : `set_config('app.current_tenant_id', tenant_id, true)` est positionné systématiquement avant toute requête SQL.
3. **Defense-in-depth** : toutes les requêtes SQL incluent `WHERE tenant_id = $N` en plus du RLS.
4. **Audit log** : chaque tool écrit dans `audit_events`. Les erreurs d'audit ne bloquent jamais la logique métier.
5. **Tenant invalide** → `TenantForbidden` (HTTP 403), jamais 404.
6. **Stateless** : aucun état persistant dans le serveur.

---

## Variables d'environnement

| Variable               | Requis | Défaut           | Description                                                        |
|------------------------|--------|------------------|--------------------------------------------------------------------|
| `DATABASE_URL`         | ✅     | —                | URL PostgreSQL (ex: `postgres://user:pass@host/db`)                |
| `MCP_TRANSPORT`        | ❌     | `stdio`          | Transport : `stdio` ou `http`                                      |
| `HTTP_BIND`            | ❌     | `0.0.0.0:19002`  | Adresse d'écoute en mode HTTP                                      |
| `INTER_SERVICE_SECRET` | ✅*    | —                | Secret partagé avec l'orchestrator (header `X-Internal-API-Key`)   |
| `LOG_LEVEL`            | ❌     | `info`           | Niveau de log (`debug`, `info`, `warn`, `error`)                   |

> *Requis en mode HTTP. Créer un fichier `.env` à la racine du service (voir section Démarrage).

### Démarrage en mode HTTP (dev)

```bash
# Fichier .env (gitignored)
DATABASE_URL=postgresql://revops:revops@localhost:5433/revops
MCP_TRANSPORT=http
HTTP_BIND=0.0.0.0:19002
INTER_SERVICE_SECRET=dev-internal-key-change-me
LOG_LEVEL=info

# Build
SQLX_OFFLINE=true cargo build --release

# Run
./target/release/mcp-billing

# Health check
curl http://localhost:19002/health
# → {"service":"mcp-billing","status":"ok"}

# Liste des tools
curl http://localhost:19002/tools
# → ["get_invoice","list_invoices","list_overdue_payments",...]

# Appel d'outil
curl -X POST http://localhost:19002/mcp/call \
  -H "Content-Type: application/json" \
  -H "X-Internal-API-Key: dev-internal-key-change-me" \
  -d '{"tool":"list_invoices","tenant_id":"<uuid>","params":{"tenant_id":"<uuid>","limit":10}}'
```

---

## Schéma de base de données attendu

### Tables principales

```sql
-- Factures
CREATE TABLE invoices (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL REFERENCES organizations(id),
    subscription_id UUID NOT NULL,
    invoice_number  TEXT NOT NULL,
    status          invoice_status NOT NULL DEFAULT 'pending',
    amount          NUMERIC(15,2) NOT NULL,
    currency        TEXT NOT NULL DEFAULT 'USD',
    due_date        DATE NOT NULL,
    paid_at         TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Lignes de facture
CREATE TABLE invoice_line_items (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    invoice_id  UUID NOT NULL REFERENCES invoices(id),
    description TEXT NOT NULL,
    quantity    INTEGER NOT NULL DEFAULT 1,
    unit_price  NUMERIC(15,2) NOT NULL,
    amount      NUMERIC(15,2) NOT NULL
);

-- Abonnements
CREATE TABLE subscriptions (
    id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id             UUID NOT NULL REFERENCES organizations(id),
    plan_id               TEXT NOT NULL,
    plan_name             TEXT NOT NULL,
    status                subscription_status NOT NULL,
    seats                 INTEGER NOT NULL DEFAULT 1,
    mrr                   NUMERIC(15,2) NOT NULL DEFAULT 0,
    currency              TEXT NOT NULL DEFAULT 'USD',
    current_period_start  TIMESTAMPTZ NOT NULL,
    current_period_end    TIMESTAMPTZ NOT NULL,
    cancel_at_period_end  BOOLEAN NOT NULL DEFAULT FALSE,
    trial_end             TIMESTAMPTZ,
    features              JSONB NOT NULL DEFAULT '[]',
    created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at            TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Snapshots MRR mensuels
CREATE TABLE mrr_snapshots (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id      UUID NOT NULL REFERENCES organizations(id),
    snapshot_date  DATE NOT NULL,
    mrr            NUMERIC(15,2) NOT NULL DEFAULT 0,
    new_mrr        NUMERIC(15,2) NOT NULL DEFAULT 0,
    expansion_mrr  NUMERIC(15,2) NOT NULL DEFAULT 0,
    churned_mrr    NUMERIC(15,2) NOT NULL DEFAULT 0
);

-- Moyens de paiement
CREATE TABLE payment_methods (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id  UUID NOT NULL REFERENCES organizations(id),
    last4      TEXT,
    is_default BOOLEAN NOT NULL DEFAULT FALSE
);

-- Permissions utilisateurs
CREATE TABLE user_permissions (
    user_id    UUID NOT NULL,
    tenant_id  UUID NOT NULL,
    permission TEXT NOT NULL,
    PRIMARY KEY (user_id, tenant_id, permission)
);
```

### Types PostgreSQL requis

```sql
CREATE TYPE invoice_status AS ENUM ('draft', 'pending', 'paid', 'overdue', 'void', 'refunded');
CREATE TYPE subscription_status AS ENUM ('trialing', 'active', 'past_due', 'canceled', 'suspended', 'paused');
```

---

## Tools

### `get_invoice`

Récupère une facture complète avec ses lignes.

**Input**
```json
{
  "tenant_id": "uuid",
  "user_id": "uuid",
  "invoice_id": "uuid"
}
```

**Output**
```json
{
  "invoice": {
    "id": "uuid",
    "tenant_id": "uuid",
    "subscription_id": "uuid",
    "invoice_number": "INV-2026-001",
    "status": "paid",
    "amount": "1200.00",
    "currency": "USD",
    "due_date": "2026-01-31",
    "paid_at": "2026-01-28T14:00:00Z",
    "line_items": [
      { "description": "Pro Plan - Jan 2026", "quantity": 1, "unit_price": "1200.00", "amount": "1200.00" }
    ],
    "created_at": "2026-01-01T00:00:00Z"
  }
}
```

**Erreurs** : `TENANT_FORBIDDEN` (403), `NOT_FOUND` (404), `DATABASE_ERROR` (500)

---

### `list_invoices`

Liste les factures avec filtres optionnels et totaux agrégés.

**Input**
```json
{
  "tenant_id": "uuid",
  "user_id": "uuid",
  "status": "pending",
  "from_date": "2026-01-01",
  "to_date": "2026-03-31",
  "limit": 20,
  "offset": 0
}
```

**Output**
```json
{
  "invoices": [ /* Vec<InvoiceSummary> */ ],
  "total": 42,
  "total_amount": "50400.00"
}
```

**Erreurs** : `TENANT_FORBIDDEN` (403), `DATABASE_ERROR` (500)

---

### `list_overdue_payments`

Liste les factures en retard de paiement avec calcul du nombre de jours de retard.

**Input**
```json
{
  "tenant_id": "uuid",
  "overdue_days_min": 7,
  "overdue_days_max": 90,
  "limit": 20
}
```

**Output**
```json
{
  "overdue_invoices": [
    {
      "invoice": { "id": "...", "invoice_number": "INV-2026-010", "status": "overdue", "amount": "500.00", "currency": "USD", "due_date": "2026-02-01" },
      "overdue_days": 32,
      "contact_email": "billing@customer.com"
    }
  ],
  "total_overdue_amount": "1500.00",
  "currency": "USD",
  "count": 3
}
```

**Erreurs** : `TENANT_FORBIDDEN` (403), `DATABASE_ERROR` (500)

---

### `get_subscription`

Récupère les détails d'un abonnement. Si `subscription_id` est omis, retourne le plus récent.

**Input**
```json
{
  "tenant_id": "uuid",
  "subscription_id": "uuid"
}
```

**Output**
```json
{
  "subscription": {
    "id": "uuid",
    "tenant_id": "uuid",
    "plan_id": "pro_monthly",
    "plan_name": "Pro",
    "status": "active",
    "seats": 10,
    "mrr": "1200.00",
    "currency": "USD",
    "current_period_start": "2026-03-01T00:00:00Z",
    "current_period_end": "2026-04-01T00:00:00Z",
    "cancel_at_period_end": false,
    "trial_end": null,
    "features": ["analytics", "sequences", "api_access"],
    "created_at": "2025-06-01T00:00:00Z"
  }
}
```

**Erreurs** : `TENANT_FORBIDDEN` (403), `NOT_FOUND` (404), `NO_ACTIVE_SUBSCRIPTION` (404), `DATABASE_ERROR` (500)

---

### `check_subscription_status`

Vérifie si le tenant a un abonnement actif et retourne les informations de capacité.

**Input**
```json
{
  "tenant_id": "uuid",
  "user_id": "uuid"
}
```

**Output**
```json
{
  "status": "active",
  "plan_name": "Pro",
  "current_period_end": "2026-04-01T00:00:00Z",
  "is_trial": false,
  "trial_ends_at": null,
  "seats_used": 7,
  "seats_total": 10,
  "features": ["analytics", "sequences", "api_access"]
}
```

**Erreurs** : `TENANT_FORBIDDEN` (403), `NO_ACTIVE_SUBSCRIPTION` (404), `DATABASE_ERROR` (500)

---

### `update_subscription_status`

Met à jour le statut d'un abonnement. Requiert la permission `billing:subscriptions:write`.

**Transitions valides** :
- `active` → `past_due`, `suspended`
- `suspended` → `active`
- `past_due` → `active`, `canceled`
- `trialing` → `active`, `canceled`
- `paused` → `active`

**Input**
```json
{
  "tenant_id": "uuid",
  "user_id": "uuid",
  "subscription_id": "uuid",
  "new_status": "suspended",
  "reason": "Non-payment after 3 reminders"
}
```

**Output**
```json
{
  "previous_status": "past_due",
  "new_status": "suspended",
  "updated_at": "2026-03-05T18:00:00Z"
}
```

**Erreurs** : `TENANT_FORBIDDEN` (403), `PERMISSION_DENIED` (403), `NOT_FOUND` (404), `INVALID_TRANSITION` (422), `DATABASE_ERROR` (500)

---

### `get_customer_billing_summary`

Retourne un résumé financier complet du tenant.

**Input**
```json
{
  "tenant_id": "uuid",
  "user_id": "uuid"
}
```

**Output**
```json
{
  "mrr": "1200.00",
  "arr": "14400.00",
  "currency": "USD",
  "pending_invoices_count": 2,
  "pending_invoices_amount": "2400.00",
  "next_renewal_date": "2026-04-01T00:00:00Z",
  "lifetime_value": "18000.00",
  "payment_method_last4": "4242"
}
```

**Erreurs** : `TENANT_FORBIDDEN` (403), `DATABASE_ERROR` (500)

---

### `get_mrr`

Retourne les données MRR mensuelles pour une période donnée.

**Input**
```json
{
  "tenant_id": "uuid",
  "user_id": "uuid",
  "from_date": "2025-01-01",
  "to_date": "2026-03-31"
}
```

**Output**
```json
{
  "data_points": [
    {
      "date": "2025-01-01",
      "mrr": "800.00",
      "new_mrr": "800.00",
      "expansion_mrr": "0.00",
      "churned_mrr": "0.00"
    }
  ],
  "current_mrr": "1200.00",
  "growth_rate": 50.0
}
```

**Erreurs** : `TENANT_FORBIDDEN` (403), `VALIDATION_ERROR` (422), `DATABASE_ERROR` (500)

---

## Lancer en développement

```bash
export DATABASE_URL="postgres://user:password@localhost:5432/revops"
export MCP_TRANSPORT=stdio
export LOG_LEVEL=debug

cargo run
```

## Build de production

```bash
cargo build --release
# Binaire : ./target/release/mcp-billing
```
