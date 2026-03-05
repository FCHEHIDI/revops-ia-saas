# Charte du Project Manager IA — Projet RevOps IA SaaS

Document de référence pour le Project Manager IA : rôles, responsabilités, architecture et standards de développement.

---

## 1. Vision du projet

Construire un **SaaS RevOps moderne, 100% IA-native**, basé sur :

- Un **LLM orchestrateur stateless**
- Une couche **MCP** exposant les capacités métier (CRM, Billing, Analytics, Sequences, Filesystem)
- Un **RAG** pour la mémoire documentaire
- Un **backend multi-tenant**
- Une **UI conversationnelle** + vues structurées
- Une **architecture scalable** (queue, batching, cluster LLM)

Le système doit être **modulaire**, **robuste**, **souverain** et **maintenable**.

---

## 2. Architecture cible

### 2.1 Vue d'ensemble

| Couche | Rôle |
|--------|------|
| **Frontend** | UI + chat IA |
| **Backend API** | Auth, sessions, routing |
| **LLM Orchestrator** | Reconstruit le contexte, appelle RAG + MCP |
| **RAG Layer** | Vector store, embeddings, retrievers |
| **Queue** | Priorités, batching, retry |
| **LLM Cluster** | Workers stateless |
| **MCP Layer** | Microservices métier |
| **Data Layer** | Postgres + Data Warehouse |

### 2.2 Diagramme d'architecture (LLM + MCP + RAG)

```
                    ┌───────────────────────────┐
                    │         Frontend          │
                    │  (UI RevOps + Chat IA)    │
                    └─────────────┬─────────────┘
                                  │
                                  ▼
                    ┌───────────────────────────┐
                    │        Backend API        │
                    │ Auth, sessions, routing   │
                    └─────────────┬─────────────┘
                                  │
                                  ▼
                    ┌───────────────────────────┐
                    │     LLM Orchestrator      │
                    │ - reconstruit le contexte │
                    │ - appelle RAG + MCP       │
                    │ - choisit le modèle       │
                    └───────┬─────────┬─────────┘
                            │         │
                     ┌──────▼──────┐  │
                     │  RAG Layer  │  │
                     │ Vector Store│  │
                     │ Embeddings  │  │
                     │ Retrievers  │  │
                     └──────┬──────┘  │
                            │         │
                            ▼         ▼
                    ┌──────────────────────────┐
                    │     Queue (LLM jobs)     │
                    │  Priorités, batching     │
                    └──────────────┬───────────┘
                                   │
                                   ▼
                    ┌──────────────────────────┐
                    │      LLM Cluster         │
                    │  (self-host, N instances)│
                    └──────────────┬───────────┘
                                   │
                                   ▼
                    ┌──────────────────────────┐
                    │       MCP Layer          │
                    │  mcp-crm  mcp-billing    │
                    │  mcp-analytics           │
                    │  mcp-sequences           │
                    │  mcp-filesystem          │
                    └──────────────┬───────────┘
                                   │
                                   ▼
                    ┌──────────────────────────┐
                    │      Data Layer          │
                    │  Postgres, DW, logs      │
                    └──────────────────────────┘
```

### 2.3 Principes architecturaux

- **LLM stateless** : le contexte est reconstruit à chaque requête à partir de la session, des extraits RAG et des données MCP
- **RAG = mémoire longue durée** : documents, playbooks, QBR, notes, emails, historiques
- **MCP = couche métier** : chaque domaine RevOps est un serveur MCP
- **Scalabilité** : queue devant le LLM, batching, load balancing

---

## 3. Rôles des agents

### 3.1 Catalogue des agents

| Agent | Responsable de | Livrables | Modèle recommandé |
|-------|----------------|-----------|-------------------|
| **Architecte Système** | Architecture globale, cohérence, ADR | Schémas, ADR, conventions | Claude Sonnet 4.6 |
| **Développeur Backend** | API multi-tenant, sessions, queue | Code, tests, doc API | GPT-4.1 ou Sonnet 4.6 |
| **Développeur MCP** | Serveurs MCP (CRM, Billing, etc.) | Serveurs, schémas tools, tests | Claude Sonnet 4.6 |
| **Développeur RAG** | Vector store, embeddings, retrievers | Code RAG, schémas, tests | Claude Sonnet 4.6 |
| **Développeur LLM Orchestrator** | Logique d'orchestration, contexte, prompts | Orchestrateur, prompts, tests | Claude Sonnet 4.6 |
| **Développeur Frontend** | UI conversationnelle, vues RevOps | UI, composants, tests | GPT-4.1 |
| **DevOps / Infra** | Docker, K8s, CI/CD, monitoring | Pipelines, manifests, dashboards | GPT-4.1 |
| **Reviewer** | Revue des PR, cohérence, sécurité | Revue, feedback | Claude Sonnet 4.6 |

### 3.2 Profil de l'agent idéal (orchestrateur)

- **Stateless** : pas d'état interne, backend reconstruit le contexte
- **Tool-first** : privilégie les tools MCP plutôt que le raisonnement interne
- **RAG-aware** : sait quand aller chercher des extraits pertinents
- **Planificateur** : découpe les tâches en étapes
- **Déterministe** : suit des règles, pas des improvisations
- **Sécurisé** : n'agit que via les tools autorisés

---

## 4. Standards de développement

### 4.1 Code

- **Rust** idiomatique pour MCP + orchestrateur
- **TypeScript / Go / Python** pour le backend selon besoin
- **Tests obligatoires** pour chaque module
- **Documentation** intégrée

### 4.2 Architecture

- **Stateless** partout
- **Découplage strict** entre les couches
- **MCP** = source de vérité métier
- **RAG** = mémoire documentaire
- **LLM** = cerveau orchestrateur

### 4.3 Sécurité

- Aucun accès direct du LLM aux données brutes
- MCP encapsule toutes les actions sensibles
- Logs anonymisés
- Multi-tenant strict

---

## 5. Workflow de collaboration

1. L'**Architecte** définit la feature et rédige un ADR si nécessaire
2. Le **PM IA** crée les tâches et assigne les agents
3. Chaque agent :
   - lit la charte
   - lit les fichiers concernés
   - propose un plan
   - implémente
   - ouvre une PR
4. L'**Agent Reviewer** valide la PR
5. L'**Architecte** valide la cohérence globale

---

## 6. Structure du repo

```
backend/        # API multi-tenant
mcp/            # Serveurs MCP (crm, billing, analytics, sequences, filesystem)
rag/            # Vector store, retrievers, embeddings
orchestrator/   # LLM orchestrator, prompts, context builder
frontend/       # UI, composants, pages
infra/          # Docker, K8s, CI/CD
docs/           # Architecture, ADR, spécifications MCP
```

---

## 7. Instructions types pour les agents

### Architecte

> "Définis la structure du module X selon la charte. Rédige un ADR."

### Développeur MCP

> "Implémente le serveur mcp-X selon la charte opérationnelle. Respecte les conventions, la structure du repo et les standards de sécurité. Propose un plan, puis implémente."

### Développeur RAG

> "Implémente le vector store multi-tenant avec embeddings et retrievers. Respecte la charte. Documente ton design."

### Développeur Backend

> "Implémente les endpoints nécessaires à X. Respecte la charte."

### Développeur Orchestrateur

> "Implémente la logique d'orchestration pour X. Gère le contexte et le routage vers MCP + RAG."

### Reviewer

> "Analyse la PR, vérifie la cohérence, la sécurité et les tests."

---

## 8. Références techniques

### 8.1 Scalabilité LLM (10 000 utilisateurs concurrents)

- LLM traité comme un **service stateless**
- Contexte externalisé dans l'infra (sessions, RAG)
- **MCP** pour réduire la charge cognitive du modèle
- **Queue / scheduling** devant le LLM
- **Batching** pour optimiser l'utilisation GPU

### 8.2 Stack recommandée

- **Agent principal** : Claude Sonnet 4.6
- **Agent secondaire** : GPT-4.1 (vitesse, boilerplate)
- **Environnement** : Cursor avec agents spécialisés
