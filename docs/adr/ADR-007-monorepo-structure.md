# ADR-007 : Structure Monorepo du projet RevOps IA SaaS

- **Date** : 2026-03-06
- **Statut** : Accepté
- **Décideurs** : Architecte Système

---

## Contexte

Le projet RevOps IA SaaS est un système distribué composé de plusieurs services aux technologies hétérogènes (Python, Rust, TypeScript). La question de l'organisation du code source est structurante : un monorepo centralise tout dans un seul dépôt Git, tandis qu'une approche polyrepo dédie un dépôt par service.

Les contraintes du projet sont :
- **Multi-technologie** : Python (backend, RAG), Rust (orchestrateur, MCP), TypeScript (frontend)
- **Cohérence inter-services** : les contrats d'interface entre les couches (schémas, types) doivent rester alignés
- **Équipe réduite** : une équipe d'agents spécialisés coordonnée par un PM IA
- **CI/CD unifié** : les pipelines doivent pouvoir construire et tester l'ensemble du système de manière coordonnée
- **Visibilité** : tout le code doit être visible dans une seule vue pour faciliter les revues d'architecture et la cohérence des décisions

---

## Décision

**Le projet adopte une architecture monorepo avec services séparés dans des dossiers de premier niveau.**

### Arborescence racine

```
revops-ia-saas/
├── backend/           # API multi-tenant (Python 3.12 + FastAPI)
├── orchestrator/      # LLM Orchestrator stateless (Rust 2021 + Tokio)
├── mcp/               # Serveurs MCP métier (Rust 2021 + rmcp)
│   ├── mcp-crm/
│   ├── mcp-billing/
│   ├── mcp-analytics/
│   ├── mcp-sequences/
│   └── mcp-filesystem/
├── rag/               # Couche RAG documentaire (Python 3.12 + FastAPI)
├── frontend/          # UI (Next.js 15 + TypeScript + Tailwind CSS)
├── infra/             # Infrastructure as Code (Docker, K8s, Terraform)
│   ├── docker/        # docker-compose.yml (local)
│   ├── kubernetes/    # Manifests Kubernetes (production)
│   ├── terraform/     # Infrastructure cloud
│   ├── helm/          # Helm charts
│   ├── monitoring/    # Prometheus + Grafana
│   └── ci/            # GitHub Actions workflows
└── docs/              # Documentation et ADR
    ├── adr/           # Architecture Decision Records
    ├── ARCHITECTURE.md
    └── PROJECT_MANAGER_CHARTER.md
```

### Structure interne par service

#### `backend/` — Python / FastAPI

```
backend/
├── app/
│   ├── main.py
│   ├── config.py
│   ├── dependencies.py
│   ├── auth/          # Authentification JWT
│   ├── users/         # Gestion des utilisateurs
│   ├── sessions/      # Sessions de chat
│   ├── documents/     # Documents utilisateurs
│   ├── orchestrator/  # Proxy vers l'orchestrateur LLM
│   ├── audit/         # Logs d'audit
│   ├── middleware/    # Middleware d'isolation tenant
│   └── common/        # Utilitaires partagés (db, security)
├── alembic/           # Migrations de base de données
├── tests/
├── requirements.txt
├── Dockerfile
└── .env.example
```

#### `orchestrator/` — Rust / Tokio

```
orchestrator/
├── src/
│   ├── main.rs
│   ├── server.rs      # Routes HTTP (POST /process, GET /health)
│   ├── config.rs
│   ├── errors.rs
│   ├── schemas.rs
│   ├── context/       # Reconstruction du contexte LLM
│   ├── routing/       # Sélection du modèle
│   ├── mcp_client/    # Client MCP
│   ├── rag_client/    # Client RAG
│   ├── llm_client/    # Client LLM (OpenAI / Anthropic)
│   └── queue/         # Producteur Redis
├── tests/
├── Cargo.toml
├── Dockerfile
└── .env.example
```

#### `mcp/{server}/` — Rust / rmcp (structure commune)

```
mcp/mcp-{name}/
├── src/
│   ├── main.rs
│   ├── server.rs      # Serveur MCP (rmcp)
│   ├── config.rs
│   ├── errors.rs
│   ├── schemas.rs
│   ├── db.rs          # Accès PostgreSQL (sqlx)
│   ├── audit.rs       # Audit log des appels MCP
│   └── tools/         # Implémentation des tools MCP
├── Cargo.toml
├── Dockerfile
└── README.md
```

#### `rag/` — Python / FastAPI

```
rag/
├── app/
│   ├── main.py
│   ├── config.py
│   ├── dependencies.py
│   ├── schemas.py
│   ├── indexing/      # Chunking + embeddings + indexation
│   ├── retrieval/     # Retriever + reranker
│   ├── vector_store/  # pgvector + Qdrant
│   └── queue/         # Consumer Redis (jobs d'indexation)
├── tests/
├── requirements.txt
├── Dockerfile
└── .env.example
```

#### `frontend/` — TypeScript / Next.js 15

```
frontend/
├── src/
│   ├── app/           # App Router Next.js (pages, layouts)
│   │   ├── (auth)/    # Groupe de routes authentification
│   │   └── (dashboard)/ # Groupe de routes dashboard
│   │       ├── chat/
│   │       ├── crm/
│   │       ├── billing/
│   │       ├── analytics/
│   │       ├── sequences/
│   │       └── documents/
│   ├── components/    # Composants React (chat, crm, billing, ui…)
│   ├── hooks/         # Custom hooks (useSSE, useAuth, useTenant)
│   ├── lib/           # Clients API et SSE
│   └── types/         # Types TypeScript partagés
├── public/
├── package.json
├── tsconfig.json
├── tailwind.config.ts
├── next.config.ts
├── Dockerfile
└── .env.example
```

#### `infra/` — Docker + Kubernetes + Terraform

```
infra/
├── docker/
│   └── docker-compose.yml   # Stack complète locale
├── kubernetes/
│   ├── base/               # Manifests Kustomize de base
│   └── overlays/           # Surcharges par environnement (dev, prod)
├── terraform/              # IaC (variables, providers, outputs)
├── helm/revops-ia/         # Helm chart de l'application
├── monitoring/             # Prometheus + Grafana
└── ci/github-actions/      # Pipelines CI/CD
```

---

## Alternatives considérées

### Polyrepo (1 dépôt Git par service)

- **Avantages** : indépendance totale des équipes, cycles de release découplés, permissions Git granulaires par service
- **Rejeté** :
  - La coordination inter-services est difficile (les changements de contrat d'API nécessitent plusieurs PRs synchronisées)
  - L'outillage de revue globale est absent (un Reviewer ne peut pas avoir une vue unifiée)
  - La découverte du code est fragmentée pour les agents spécialisés
  - La charge opérationnelle (N dépôts, N CI, N secrets) est disproportionnée pour la taille de l'équipe

### Monorepo avec workspace unique (ex: Turborepo, Nx)

- **Avantages** : partage de code entre services TypeScript, build cache, graph de dépendances
- **Rejeté** : inapplicable à un projet multi-langage (Rust + Python + TypeScript). Les outils comme Turborepo sont TypeScript-centric. Un workspace Cargo ne peut pas inclure les projets Python. L'approche "dossiers de premier niveau" est plus universelle.

### Monorepo avec dossiers de premier niveau (retenu)

- **Avantages** :
  - Structure claire et navigable sans outillage spécifique
  - CI/CD par dossier (GitHub Actions `paths:` filter)
  - Chaque service garde son propre fichier de dépendances (`Cargo.toml`, `requirements.txt`, `package.json`)
  - Les agents spécialisés peuvent travailler sur leur périmètre sans conflit

---

## Conséquences

### Positives

- **Visibilité totale** : un `git clone` donne accès à l'ensemble du système
- **Cohérence des ADR** : les décisions d'architecture s'appliquent à tous les services depuis un seul endroit
- **CI/CD path-based** : GitHub Actions déclenche uniquement les jobs affectés par un changement (ex: modification dans `backend/` ne déclenche que `lint-backend`)
- **Refactoring transversal simplifié** : renommer une interface utilisée par plusieurs services est visible dans une seule PR
- **Onboarding** : un nouvel agent (ou développeur) comprend l'ensemble du système en explorant un seul dépôt

### Négatives / Risques

- **Taille du dépôt** : à terme, le monorepo grossira (Rust build artifacts, node_modules si non ignorés). Les fichiers binaires sont à exclure via `.gitignore`.
- **Permissions granulaires** : GitHub ne permet pas de restreindre l'accès en lecture/écriture à un sous-dossier. CODEOWNERS permet une revue obligatoire par responsable de dossier.
- **Conflits de merge** : peu probable avec des services technologiquement distincts, mais possible sur les fichiers partagés (`docs/`, `.github/`)

### Règles d'organisation

1. Chaque service est **autonome** : ses dépendances, son Dockerfile et son `.env.example` sont dans son dossier
2. Aucun code partagé entre services n'existe dans le monorepo — la communication se fait via les **APIs HTTP** (contrats documentés)
3. Les secrets ne sont **jamais** commités — uniquement des `.env.example` avec des valeurs fictives
4. Les **ADR** documentent toute décision structurante avant implémentation
