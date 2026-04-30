# ADR-008 : Architecture du MCP CRM — Phase 2

- **Date** : 2026-03-17
- **Statut** : Accepté
- **Décideurs** : Architecte Système
- **Remplace partiellement** : ADR-001 (Rust pour MCP) — exception pour les serveurs MCP sans accès DB direct
- **Concerne** : ADR-003 (MCP couche métier), ADR-005 (isolation multi-tenant)

---

## Contexte

La Phase 2 du projet RevOps IA SaaS introduit le premier serveur MCP métier : `mcp-crm`. Ce serveur expose les capacités CRM (contacts, accounts, deals) au LLM orchestrateur.

Deux décisions architecturales structurantes doivent être prises :

1. **Pattern d'accès aux données** : le serveur MCP CRM doit-il accéder directement à PostgreSQL (via sqlx, comme prévu initialement dans ADR-001 et ADR-007), ou doit-il passer par le backend FastAPI ?

2. **Choix technologique** : Rust (rmcp) ou Python (mcp SDK officiel) pour implémenter le serveur MCP CRM ?

Ces deux décisions sont liées : le choix d'accès via le backend modifie fondamentalement le profil du serveur MCP (proxy HTTP vs service DB).

### Contrainte initiale (ADR-001)

ADR-001 a choisi Rust pour les serveurs MCP en raison de :
- L'accès DB direct via `sqlx` (type-safe, performant)
- La cohérence avec l'orchestrateur Rust
- Les garantees de mémoire et de concurrence Rust

Cette décision supposait que les MCPs avaient un accès direct à la base de données.

### Problème identifié

Un accès DB direct depuis les serveurs MCP crée les problèmes suivants :

- **Double implémentation RLS** : la logique d'isolation tenant doit être implémentée à la fois dans le backend (SQLAlchemy + middleware) et dans chaque serveur MCP (sqlx + logique de session Postgres). Toute évolution du schéma RLS doit être synchronisée dans N endroits.

- **Surface d'attaque élargie** : chaque serveur MCP ayant des credentials DB directes, une compromission d'un serveur MCP donne un accès direct à toutes les données du cluster Postgres (avec les droits de l'utilisateur DB configuré).

- **Duplication logique métier** : les validations (ex: vérification que `stage` appartient aux valeurs autorisées, que `owner_id` est un utilisateur valide du tenant) seraient dupliquées entre le backend et les MCPs.

- **Contournement du RBAC applicatif** : le RBAC est implémenté dans le backend (via les permissions stockées dans `users.permissions`). Un MCP avec accès DB direct contournerait structurellement cette couche.

---

## Décision

### Décision 1 : Les serveurs MCP n'ont pas d'accès direct à la base de données

**Les serveurs MCP appellent exclusivement le backend FastAPI via des endpoints internes HTTP.**

Ce pattern s'applique à `mcp-crm` en Phase 2 et établit le standard pour tous les futurs serveurs MCP (`mcp-billing`, `mcp-analytics`, `mcp-sequences`).

**Flux de données :**

```
Orchestrateur Rust
    │
    │  Protocole MCP (JSON-RPC 2.0 / HTTP+SSE)
    ▼
mcp-crm (Python)
    │
    │  HTTP interne (X-Internal-API-Key + X-Tenant-ID)
    ▼
Backend FastAPI /internal/v1/crm/*
    │
    │  SQLAlchemy + SET app.current_tenant_id
    ▼
PostgreSQL (RLS activé sur contacts, accounts, deals)
```

**Garanties apportées par ce pattern :**

1. **RLS implémenté une seule fois** dans le backend — les MCPs n'ont aucune logique de tenant
2. **RBAC applicatif respecté** — les MCPs passent les métadonnées utilisateur (`user_id`, `permissions`) dans les requêtes, le backend les applique
3. **Credentials DB centralisées** — seul le backend détient les credentials Postgres. Les MCPs n'ont accès qu'à une clé API interne
4. **Logique métier centralisée** — validations, audit logs et déclencheurs RAG sont dans le backend uniquement

### Décision 2 : Python (mcp SDK officiel) pour mcp-crm

**Le serveur `mcp-crm` est implémenté en Python avec le SDK MCP officiel d'Anthropic.**

**Justification :**

| Critère | Rust (rmcp) | Python (mcp SDK) | Décision |
|---------|------------|-----------------|----------|
| Accès DB direct (sqlx) | Requis | N/A | Plus requis → avantage Rust éliminé |
| Client HTTP (appels backend) | reqwest (verbose) | httpx async (naturel) | Python |
| Support protocole MCP | rmcp (crate communautaire) | SDK officiel Anthropic | Python |
| Cohérence avec backend | Non | Oui (Python) | Python |
| Temps d'implémentation | ~2x plus long | Référence | Python |
| Maintenabilité | Forte expertise Rust requise | Standard Python | Python |

Le principal avantage de Rust (sqlx + safety DB) disparaît dès lors que le MCP ne touche plus la DB directement. `mcp-crm` est fonctionnellement un **proxy HTTP typé** — un domaine où Python httpx + Pydantic est parfaitement adapté.

**Exception au ADR-001 :** ADR-001 a retenu Rust pour les MCPs ayant un accès DB direct. Cette décision est partiellement supersédée pour les MCPs sans accès DB. La règle devient :

> **MCP avec accès DB direct** (futur use case, si applicable) → Rust + rmcp + sqlx  
> **MCP sans accès DB** (pattern standard Phase 2+) → Python + mcp SDK + httpx

---

## Structure du backend CRM (`backend/app/crm/`)

```
backend/app/crm/
├── __init__.py
├── router.py           # Routes /internal/v1/crm/* (contacts, accounts, deals)
├── service.py          # Logique métier (orchestration repo + RBAC + RAG trigger)
├── repository.py       # Accès DB SQLAlchemy uniquement
├── schemas.py          # Pydantic v2 — DTOs request/response
├── models.py           # SQLAlchemy ORM (Contact, Account, Deal)
└── permissions.py      # Dépendances FastAPI RBAC CRM
```

### Endpoints internes exposés

**Préfixe** : `/internal/v1/crm` — bloqué au niveau réseau pour tout accès externe.

| Méthode | URL | Rôle |
|---------|-----|------|
| GET | `/internal/v1/crm/contacts/{id}` | Récupérer un contact |
| GET | `/internal/v1/crm/contacts` | Rechercher/lister des contacts |
| POST | `/internal/v1/crm/contacts` | Créer un contact |
| PUT | `/internal/v1/crm/contacts/{id}` | Mettre à jour un contact |
| GET | `/internal/v1/crm/accounts/{id}` | Récupérer un compte |
| GET | `/internal/v1/crm/accounts` | Rechercher/lister des comptes |
| POST | `/internal/v1/crm/accounts` | Créer un compte |
| PUT | `/internal/v1/crm/accounts/{id}` | Mettre à jour un compte |
| GET | `/internal/v1/crm/deals/{id}` | Récupérer un deal |
| GET | `/internal/v1/crm/deals` | Lister les deals |
| POST | `/internal/v1/crm/deals` | Créer un deal |
| PUT | `/internal/v1/crm/deals/{id}` | Mettre à jour un deal |

### Authentification inter-services

```
X-Internal-API-Key: {INTERNAL_API_KEY}   # validé par verify_internal_key()
X-Tenant-ID: {org_id}                    # injecté dans SET app.current_tenant_id
X-Request-ID: {trace_id}                 # propagé dans les logs
```

---

## Structure du serveur MCP CRM (`mcp/mcp-crm/`)

```
mcp/mcp-crm/
├── src/
│   ├── main.py             # Point d'entrée, initialise le serveur MCP
│   ├── server.py           # Définition du serveur MCP, registration des tools
│   ├── config.py           # Settings (BACKEND_URL, INTERNAL_API_KEY)
│   ├── http_client.py      # Client httpx vers backend /internal/v1/crm/*
│   ├── schemas.py          # Pydantic v2 — types partagés MCP ↔ backend
│   ├── errors.py           # McpError → JSON-RPC error codes
│   └── tools/
│       ├── contacts.py     # get_contact, search_contacts, create_contact, update_contact
│       ├── accounts.py     # get_account, search_accounts, create_account, update_account
│       └── deals.py        # get_deal, list_deals, create_deal, update_deal_stage
├── tests/
├── requirements.txt
├── Dockerfile
└── .env.example
```

### Tools MCP exposés

```
get_contact(contact_id, tenant_id)
search_contacts(query, account_id?, page?, limit?, tenant_id)
create_contact(first_name, last_name, email, phone?, job_title?, account_id?, tenant_id, created_by)
update_contact(contact_id, fields_to_update, tenant_id)
get_account(account_id, tenant_id)
search_accounts(query, industry?, page?, limit?, tenant_id)
create_account(name, domain?, industry?, size?, tenant_id, created_by)
update_account(account_id, fields_to_update, tenant_id)
get_deal(deal_id, tenant_id)
list_deals(stage?, owner_id?, page?, limit?, tenant_id)
create_deal(title, account_id, amount?, stage, close_date?, owner_id, tenant_id, created_by)
update_deal_stage(deal_id, new_stage, notes?, tenant_id)
```

---

## Schéma CRM

### Tables

**`accounts`** : `id`, `org_id`, `name`, `domain`, `industry`, `size`, `arr`, `status`, `created_by`, `created_at`, `updated_at`

**`contacts`** : `id`, `org_id`, `account_id`, `first_name`, `last_name`, `email`, `phone`, `job_title`, `status`, `created_by`, `created_at`, `updated_at`

**`deals`** : `id`, `org_id`, `account_id`, `contact_id`, `owner_id`, `title`, `stage`, `amount`, `currency`, `close_date`, `probability`, `notes`, `created_by`, `created_at`, `updated_at`

### Pattern RLS (identique aux tables existantes)

```sql
ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON {table}
    USING (org_id::text = current_setting('app.current_tenant_id', true))
    WITH CHECK (org_id::text = current_setting('app.current_tenant_id', true));
```

### Migration Alembic

Fichier : `backend/alembic/versions/0002_crm_schema.py`

---

## Permissions RBAC CRM

| Permission | viewer | sales_rep | manager | admin |
|-----------|--------|-----------|---------|-------|
| `crm:contacts:read` | ✅ | ✅ | ✅ | ✅ |
| `crm:contacts:write` | ❌ | ✅ (propres) | ✅ | ✅ |
| `crm:accounts:read` | ✅ | ✅ | ✅ | ✅ |
| `crm:accounts:write` | ❌ | ❌ | ✅ | ✅ |
| `crm:deals:read` | ✅ | ✅ (propres) | ✅ | ✅ |
| `crm:deals:write` | ❌ | ✅ (propres) | ✅ | ✅ |
| `crm:deals:delete` | ❌ | ❌ | ❌ | ✅ |

---

## Intégration RAG

Le backend CRM déclenche des jobs d'indexation RAG (stream Redis `rag:index:jobs`) après création ou mise à jour d'un deal avec des notes.

**Entités indexées** : `deals.notes`, résumés account, historique des changements de stage.

**Format du job** :

```json
{
  "job_id": "job_crm_...",
  "schema_version": "1.0",
  "type": "crm_entity_index",
  "priority": "low",
  "tenant_id": "{org_id}",
  "entity_type": "deal_note",
  "entity_id": "{deal_id}",
  "content": "...",
  "metadata": { "deal_id": "...", "account_name": "...", "stage": "..." }
}
```

---

## Alternatives considérées

### Accès DB direct depuis mcp-crm (pattern ADR-001)

- **Description** : `mcp-crm` utilise sqlx + Rust, accède directement à Postgres, gère sa propre logique RLS
- **Rejeté** :
  - Double implémentation du RLS et des validations métier
  - Surface d'attaque : credentials DB dans N serveurs MCP
  - Contournement structurel du RBAC applicatif (stocké dans `users.permissions`)
  - Couplage fort au schéma DB — toute migration doit être synchronisée dans le backend ET les MCPs

### Rust (rmcp) sans accès DB direct

- **Description** : Rust pour le protocole MCP, mais client HTTP reqwest vers le backend
- **Rejeté** :
  - Complexité Rust sans bénéfice (pas de sqlx, pas de concurrence critique)
  - reqwest + serde en Rust pour des appels HTTP CRUD est plus verbeux que httpx + Pydantic
  - Incohérence : on utiliserait Rust uniquement pour satisfaire ADR-001, sans bénéfice fonctionnel

---

## Conséquences

### Positives

- **RLS implémenté une seule fois** dans le backend — aucune duplication
- **RBAC respecté structurellement** — les MCPs ne peuvent pas contourner les permissions
- **Surface d'attaque réduite** — les credentials DB ne sont présentes que dans le backend
- **Logique métier centralisée** — validations, audit logs et triggers RAG dans un seul endroit
- **Testabilité** — les MCPs sont testés en mockant le backend HTTP, pas en mockant Postgres
- **Évolutivité** — ajouter une validation métier = modifier le backend uniquement, transparent pour le MCP

### Négatives / Risques

- **Saut réseau supplémentaire** : Orchestrateur → MCP → Backend → DB (3 sauts vs 2 avec accès DB direct). Latence estimée : +5 à +15ms par opération CRM.
- **Backend devient un SPOF critique** : si le backend est down, tous les MCPs sont inopérants. Mitigé par le déploiement multi-instance du backend.
- **Complexité de débogage** : une erreur CRM implique de tracer 3 services. Mitigé par le champ `X-Request-ID` propagé à toutes les couches.

### Impact sur ADR-001

ADR-001 reste valide pour les serveurs MCP avec accès DB direct (si ce pattern est nécessaire dans le futur). Pour la Phase 2, il est partiellement supersédé : les MCPs accèdent aux données **via le backend**, pas directement. Cette évolution est cohérente avec l'objectif de centralisation du RBAC et de l'isolation tenant dans le backend.

---

## Règles absolues découlant de cette décision

1. **Aucun serveur MCP ne contient de credentials Postgres** — jamais
2. **Aucun serveur MCP ne génère de requêtes SQL** — jamais
3. **Tout accès aux données tenant-scoped passe par `/internal/v1/`** du backend
4. **Les MCPs ne s'appellent jamais entre eux** — seul l'orchestrateur initie les appels MCP
5. **Le `tenant_id` (org_id) est un paramètre obligatoire** de chaque tool MCP — aucun tool sans tenant
