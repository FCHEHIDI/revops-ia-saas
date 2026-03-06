## RevOps IA SaaS — Architecture & Vision
![revops-ia-saas](./criqueauxpythons.png)
### Vision

Construire un SaaS RevOps moderne, **IA-native**, qui s’appuie sur :

- **LLM orchestrateur stateless**
- **Couche MCP** exposant les capacités métier (CRM, Billing, Analytics, Sequences, Filesystem)
- **RAG** pour la mémoire documentaire et le contexte long terme
- **Backend multi-tenant** sécurisé
- **UI conversationnelle** enrichie de vues structurées (tableaux, dashboards, formulaires)
- **Architecture scalable** (queue, batching, cluster LLM)

Objectif : fournir un copilote RevOps fiable qui devient la **source d’orchestration** entre CRM, facturation, analytics et exécution commerciale.

### Architecture globale

- **Frontend** : UI + chat IA, vues analytics, configuration.
- **Backend API** : auth, sessions, routing, gestion multi-tenant.
- **LLM Orchestrator** : reconstruit le contexte, appelle RAG + MCP, gère les plans d’actions.
- **RAG Layer** : vector store, embeddings, retrievers, gestion des collections par tenant.
- **Queue** : priorités, batching, retry, gestion de la charge des workers.
- **LLM Cluster** : workers stateless, scaling horizontal, observabilité.
- **MCP Layer** : microservices métier (CRM, Billing, Analytics, Sequences, Filesystem).
- **Data Layer** : Postgres (OLTP) + Data Warehouse (BI, reporting).

### Structure du repo

- **Code**
  - `backend/` : API, auth, sessions, routing, multi-tenant.
  - `mcp/` : services métier connectés aux outils RevOps.
  - `rag/` : ingestion, indexation, requêtage documentaire.
  - `orchestrator/` : logique d’orchestration LLM + agents.
  - `frontend/` : UI web, chat, vues structurées.
  - `infra/` : IaC, déploiement, observabilité.
  - `docs/` : spécs fonctionnelles et techniques détaillées.

### Standards & principes

- **Langages**
  - Rust idiomatique pour `mcp/` et `orchestrator/`.

- **Qualité**
  - Tests obligatoires sur les chemins critiques.
  - Linting et formatters automatiques.

- **Architecture**
  - Services **stateless** autant que possible (orchestrateur, workers).
  - MCP = **source de vérité métier**.
  - RAG = **mémoire documentaire**.
  - LLM = **cerveau orchestrateur**.

### Roadmap (high-level)

- **MVP**
  - Intégration CRM + Billing de base via MCP.
  - Orchestrateur LLM stateless avec RAG minimal.
  - UI de chat + 1–2 vues structurées clés.

- **v1**
  - Multi-tenant complet (scopes, permissions).
  - Séquences, playbooks, reporting avancé.
  - Monitoring, métriques et coûts LLM.
