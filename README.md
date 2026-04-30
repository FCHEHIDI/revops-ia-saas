# ROI — RevOps Intelligence

> Plateforme RevOps **IA-native** propulsée par **Xenito**, le copilote IA dédié aux équipes Sales, Marketing et Customer Success.  
> Dark. Fast. Opinionated.

![Login](./docs/screenshots/00-login.png)

---

## Tour de l'interface

### Xenito — Copilote IA RevOps

Interface conversationnelle full-screen. Xenito orchestre vos données CRM, facturation et analytics en langage naturel. Chaque message déclenche une pipeline complète : `LLM → MCP tools → synthèse`.

![Xenito Chat](./docs/screenshots/01-xenito-chat.png)

> **Pipeline MCP** : le badge `mcp_crm__search_contacts` confirme que l'orchestrateur Rust appelle les outils métier avant de synthétiser la réponse via Groq `llama-3.3-70b-versatile`.

---

### Dashboard — Vue exécutive

KPIs temps réel : ARR, pipeline, deals actifs, win rate. Graphique revenue mensuel/trimestriel + fil d'activité récente.

![Dashboard](./docs/screenshots/02-dashboard.png)

| Métrique | Valeur | Tendance |
|---|---|---|
| ARR Total | $4.2M | +18.4% vs mois dernier |
| Pipeline | $1.8M | +7.2% cette semaine |
| Deals actifs | 25 | −2 cette semaine |
| Win Rate | 34% | +3 pts vs Q1 |

---

### CRM — Contacts & Deals

50 contacts seedés avec statut, poste, email. Recherche full-text. RLS PostgreSQL garantit l'isolation stricte par tenant.

![CRM](./docs/screenshots/03-crm.png)

---

### Analytics — Métriques RevOps

Vue consolidée des indicateurs clés : contacts actifs, MRR, taux de conversion, séquences actives.

![Analytics](./docs/screenshots/04-analytics.png)

---

### Facturation — Invoices

Pipeline de facturation avec statuts (Payée / En attente / En retard / Brouillon) et suivi des échéances par client.

![Facturation](./docs/screenshots/05-billing.png)

---

### Séquences — Outreach Cadences

Cadences d'outreach multi-canal (email, LinkedIn, appels). Statuts Active / En pause / Brouillon / Terminée avec métriques d'inscription.

![Séquences](./docs/screenshots/06-sequences.png)

---

### Documents — RAG

Ingestion documentaire multi-tenant. Drag & drop PDF/DOCX/TXT → indexation pgvector → accessible depuis Xenito en contexte conversationnel.

![Documents](./docs/screenshots/07-documents.png)

---

## Vision

Construire un SaaS RevOps moderne, **IA-native**, qui s'appuie sur :

- **LLM orchestrateur stateless** (Rust/Axum) — reconstruit le contexte à chaque requête, appelle RAG + MCP
- **Couche MCP** exposant les capacités métier (CRM, Billing, Analytics, Sequences, Filesystem)
- **RAG** pour la mémoire documentaire et le contexte long terme
- **Backend multi-tenant** sécurisé — RLS PostgreSQL, isolation stricte par tenant
- **UI conversationnelle** enrichie de vues structurées (tableaux, dashboards, formulaires)
- **Architecture scalable** (queue, batching, cluster LLM)

---

## Architecture

```
Client (Next.js 15)
    │
    ├── Auth — httpOnly cookies, JWT HS256, middleware RLS
    ├── API Backend (FastAPI 0.110 + asyncpg) ──── :18000
    │       ├── Sessions, CRM, Users, Documents
    │       └── PostgreSQL 16 (RLS multi-tenant) ── :5433
    │
    └── Chat SSE ──► Orchestrateur Rust (Axum) ──── :8003
                         ├── RAG (pgvector) ─────── :18500
                         ├── MCP CRM (Python) ───── :19001
                         ├── MCP Billing (Rust) ─── :19002
                         ├── MCP Analytics (Rust) ── :19003
                         ├── MCP Sequences (Rust) ── :19004
                         └── Groq LLM ─ llama-3.3-70b-versatile
```

---

## Stack technique

| Couche | Technologie | Port |
|---|---|---|
| Frontend | Next.js 15, TypeScript, Tailwind CSS | :3000 |
| Backend API | FastAPI, SQLAlchemy async, Alembic | :18000 |
| Orchestrateur LLM | Rust / Axum, SSE streaming | :8003 |
| RAG | FastAPI + pgvector | :18500 |
| MCP CRM | Python FastAPI | :19001 |
| MCP Billing/Analytics/Sequences/FS | Rust (Axum) | :19002–:19005 |
| Base de données | PostgreSQL 16 (RLS multi-tenant) | :5433 |
| Cache / Queue | Redis | :6380 |

**LLM** : Groq (`llama-3.3-70b-versatile`) — streaming SSE end-to-end.

---

## Structure du repo

```
backend/      API FastAPI — auth cookie, RLS, sessions, users, CRM
frontend/     UI Next.js — Xenito, Dashboard, CRM, Analytics, Billing, Sequences, Documents
orchestrator/ Rust/Axum — orchestration LLM, RAG, MCP, SSE streaming
mcp/          Microservices métier (CRM Python + Billing/Analytics/Sequences/FS Rust)
rag/          Ingestion et retrieval documentaire (pgvector)
infra/        Docker Compose, Kubernetes, Terraform, CI/CD, monitoring
docs/         ADRs, specs fonctionnelles, plan de dev, screenshots
```

---

## Démarrage local

```bash
# 1. Infra (Postgres + Redis)
docker compose -f infra/docker/docker-compose.dev.yml up -d

# 2. Migrations + seed démo
cd backend
python -m alembic upgrade head
python scripts/seed_demo.py

# 3. Backend API
uvicorn app.main:app --port 18000 --reload

# 4. Orchestrateur
cd orchestrator && cargo run

# 5. MCP CRM
cd mcp/mcp-crm && uvicorn src.main:app --port 19001 --reload

# 6. Frontend
cd frontend && npm install && npm run dev
```

**Credentials démo** : `admin@acme.io` / `acme1234` — org `acme-revops`

---

## Tests (backend)

```
28 passed   — auth, JWT, CRM permissions, tenant isolation, RLS, sessions
 3 xfailed  — RLS superuser, repository event loop (attendus)
 0 failures
```

```bash
cd backend && python -m pytest tests/ -q
```

---

## État du projet (29 avril 2026)

### Fonctionnalités livrées ✅

- **Auth** : login/logout cookie httpOnly, refresh token, middleware JWT pur ASGI, RLS multi-tenant
- **Chat IA** : interface Xenito, SSE streaming end-to-end, orchestrateur Rust stateless
- **MCP** : routing langage naturel → outils métier (`mcp_crm__search_contacts`, etc.)
- **CRM** : contacts, deals — RLS par tenant, permissions RBAC
- **Dashboard** : KPIs ARR, pipeline, win rate, activité récente
- **Analytics** : métriques consolidées MRR, conversion, séquences
- **Facturation** : invoices multi-statut avec échéances
- **Séquences** : cadences outreach multi-canal
- **Documents** : upload + indexation RAG multi-tenant
- **Seed data** : 50 contacts, 6 invoices, 6 séquences, 4 métriques

### Prochaines étapes

- [ ] MCP Billing + Analytics — connexion complète à l'orchestrateur
- [ ] RAG : pipeline d'ingestion PDF → pgvector opérationnel
- [ ] Observabilité : métriques LLM, coûts Groq, latences par tenant
- [ ] Upgrade Groq tier (rate limit 12K TPM en free tier)

---

## Standards & principes

- **Rust** idiomatique pour `mcp/` et `orchestrator/` (Axum, Tokio)
- **Python** pour backend et MCP CRM (FastAPI, SQLAlchemy async, Pydantic v2)
- **TypeScript strict** pour le frontend (Next.js 15 App Router)
- Services **stateless** -- l'orchestrateur reconstruit le contexte a chaque requete
- **RLS PostgreSQL** -- isolation tenant au niveau base de donnees (ADR-005)
- MCP = source de verite metier | RAG = memoire documentaire | LLM = cerveau orchestrateur
