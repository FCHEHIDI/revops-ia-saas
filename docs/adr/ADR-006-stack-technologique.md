# ADR-006 : Stack technologique globale du projet

- **Date** : 2026-03-05
- **Statut** : Accepté
- **Décideurs** : Architecte Système

---

## Contexte

Le projet RevOps IA SaaS est un système distribué multi-couches. Chaque couche a des contraintes différentes (performance, productivité, maintenabilité, écosystème) qui justifient des choix technologiques distincts. Cette ADR consolide et justifie l'ensemble des choix de stack pour garantir la cohérence et servir de référence unique pour tous les agents développeurs.

Les critères de sélection sont :
- **Performance** adaptée aux besoins de la couche
- **Maintenabilité** : code lisible, communauté active, outillage mature
- **Cohérence** : minimiser le nombre de langages et frameworks différents sans sacrifier la performance
- **Écosystème IA/ML** : support natif des bibliothèques LLM, RAG, embeddings
- **Recrutement** : technologies reconnues avec un vivier de développeurs disponibles

---

## Décision

### Vue d'ensemble de la stack

| Couche | Technologie | Justification principale |
|--------|-------------|--------------------------|
| Frontend | TypeScript + React + Next.js (App Router) + Tailwind CSS | Standard industrie, SSR/SSG natif, écosystème riche |
| Backend API | Python 3.12 + FastAPI + SQLAlchemy + Alembic + PostgreSQL | Productivité, async natif, écosystème ML |
| Orchestrateur LLM | Rust (2021) + Tokio + rmcp | Performance, stateless, sécurité mémoire (voir ADR-001) |
| Serveurs MCP | Rust (2021) + Tokio + rmcp | Idem orchestrateur, protocole MCP natif |
| Couche RAG | Python 3.12 + LangChain/LlamaIndex + pgvector/Qdrant | Écosystème ML Python dominant |
| Queue | Redis 7 + BullMQ (ou Tokio channels en Rust) | Persistance, retry, monitoring natif |
| Infra (dev) | Docker + Docker Compose | Reproductibilité locale |
| Infra (prod) | Kubernetes + Helm | Scaling, résilience, standard cloud-native |
| CI/CD | GitHub Actions | Intégration native GitHub, gratuit pour les builds |
| Observabilité | OpenTelemetry + Prometheus + Grafana | Standard open-source, traces distribuées |
| Base de données | PostgreSQL 16 + pgvector (MVP) | OLTP + vector search dans une même instance |
| Data Warehouse | PostgreSQL (MVP) → DuckDB/BigQuery (scale) | Analytics BI et reporting |

---

### Détail par couche

#### 1. Frontend — TypeScript + React + Next.js + Tailwind CSS

**Choix retenu :**
- **TypeScript** : typage statique, refactoring sûr, meilleure DX en équipe
- **React 19** : modèle de composants mature, Server Components pour le SSR
- **Next.js 15 (App Router)** : routing, SSR/SSG, API routes, optimisations automatiques
- **Tailwind CSS** : styling utilitaire, cohérence UI rapide, pas de CSS global à maintenir

**Alternatives considérées :**
- *Vue.js / Nuxt* : bon framework, mais écosystème composants plus petit pour les UI complexes de type data dashboard
- *SvelteKit* : excellent pour les performances, mais communauté plus restreinte et moins de devs disponibles
- *Angular* : trop verbeux pour un MVP agile, overhead de configuration

---

#### 2. Backend API — Python 3.12 + FastAPI + SQLAlchemy + Alembic

**Choix retenu :**
- **Python 3.12** : performances améliorées (GIL optionnel en 3.13+), syntaxe mature
- **FastAPI** : async natif (ASGI/uvicorn), validation Pydantic v2, génération OpenAPI automatique
- **SQLAlchemy 2.0** : ORM async, support RLS PostgreSQL, migrations Alembic robustes
- **PostgreSQL 16** : OLTP principal, support `pgvector`, RLS, JSON natif

**Alternatives considérées :**
- *Go + Gin/Fiber* : performances supérieures, mais perd l'écosystème ML Python essentiel pour les intégrations LLM
- *Node.js + NestJS* : possible mais double stack TypeScript/Python complexifie la maintenance
- *Django* : trop opinioné et lourd pour une API microservice, ORM synchrone par défaut

---

#### 3. MCP + Orchestrateur — Rust (édition 2021) + Tokio + rmcp

Voir **ADR-001** pour la justification complète.

**Bibliothèques Rust sélectionnées :**
- `tokio` 1.x : runtime async, tasks, channels, timers
- `rmcp` : SDK MCP officiel en Rust
- `serde` + `serde_json` : sérialisation performante
- `reqwest` : HTTP client async
- `sqlx` : accès PostgreSQL async (pour les serveurs MCP qui lisent la DB directement)
- `tracing` + `tracing-opentelemetry` : observabilité distribuée
- `anyhow` + `thiserror` : gestion d'erreurs

---

#### 4. Couche RAG — Python + LangChain ou LlamaIndex + pgvector/Qdrant

**Choix retenu :**
- **Python** : l'écosystème ML/AI est dominé par Python (LangChain, LlamaIndex, sentence-transformers)
- **pgvector** (MVP) : extension PostgreSQL, zéro infrastructure supplémentaire
- **Qdrant** (scale) : vector database haute performance, support HNSW, filtres par metadata
- **LangChain ou LlamaIndex** : décision finale à l'implémentation selon benchmark

**Alternatives considérées :**
- *Pinecone* : SaaS managé performant, mais vendor lock-in et coût à l'échelle
- *Weaviate* : bonne solution, mais plus lourd opérationnellement que Qdrant
- *ChromaDB* : adapté aux prototypes, pas à la production multi-tenant à grande échelle
- *Rust pur pour le RAG* : possible à terme mais l'écosystème ML Rust est encore immature

---

#### 5. Queue — Redis 7 + BullMQ / Tokio channels

**Choix retenu :**
- **Redis 7** : persistance AOF/RDB, Pub/Sub, Streams, battle-tested en production
- **BullMQ** : file de jobs avec priorités, retry, dead letter queue, dashboard Bull Board
- **Tokio channels** (Rust) : pour la communication interne entre tâches au sein de l'orchestrateur

**Alternatives considérées :**
- *RabbitMQ* : plus puissant pour les workflows complexes, mais overhead opérationnel supérieur
- *Kafka* : adapté au streaming événementiel massif, sur-dimensionné pour une queue de jobs LLM
- *AWS SQS* : vendor lock-in AWS, latence réseau supplémentaire

---

#### 6. Infrastructure

**Développement local :**
- **Docker + Docker Compose** : tous les services (API, orchestrateur, MCP, RAG, Redis, PostgreSQL) définis dans `docker-compose.yml`
- Hot reload activé pour Frontend (Next.js) et Backend (uvicorn --reload)
- Volume mounts pour le code source

**Production :**
- **Kubernetes** (via Helm charts) : scaling horizontal des pods LLM workers, health checks, rolling updates
- **GitHub Actions** : CI/CD — tests, lint, build, push image Docker, deploy Helm

**Observabilité :**
- **OpenTelemetry** : SDK instrumenté dans tous les services (Python, Rust, TypeScript)
- **Prometheus** : scraping des métriques exposées par chaque service
- **Grafana** : dashboards (latence p99, queue length, GPU utilization, error rate par tenant)
- **Loki** : agrégation des logs structurés (JSON)

---

## Alternatives globales considérées

### Full TypeScript (Bun + Hono pour le backend)
- **Rejeté** : perd l'écosystème Python ML/AI pour le backend et le RAG. Les gains de performance ne compensent pas.

### Full Rust (backend inclus)
- **Rejeté** : la productivité de développement pour le backend API (auth, sessions, routing, migrations) est significativement inférieure à Python/FastAPI. Le gain de performance n'est pas nécessaire à ce niveau.

### Microservices séparés pour chaque tenant
- **Rejeté** : explosion du nombre de déploiements, complexité opérationnelle non justifiée. Le RLS + namespaces RAG suffisent pour l'isolation.

---

## Conséquences

### Positives
- **Cohérence** : les choix sont justifiés et documentés — chaque agent développeur sait quelle technologie utiliser pour quelle couche
- **Performances optimales par couche** : Rust là où la performance est critique, Python là où la productivité ML prime
- **Standard industrie** : toutes les technologies choisies sont largement adoptées et ont une communauté active
- **Observable dès le début** : OpenTelemetry instrumenté dès la phase MVP, pas de dette d'observabilité

### Négatives / Risques
- **Multi-langage** : l'équipe doit maîtriser Rust, Python et TypeScript. Risque de silos de compétences.
- **Complexité d'intégration** : les interfaces entre les couches (Rust ↔ Python ↔ TypeScript) nécessitent des contrats d'API clairs et versionnés
- **Docker Compose en dev** : la stack complète est lourde à lancer localement (8 services). Un script de démarrage sélectif est nécessaire.

### Neutres
- La séparation des technologies par couche facilite la migration future d'une couche sans impacter les autres (ex: remplacer le RAG Python par Rust si l'écosystème mûrit)
- Les choix cloud-agnostic (Kubernetes, OpenTelemetry, PostgreSQL) permettent un déploiement sur n'importe quel fournisseur cloud (AWS, GCP, Azure, self-hosted)
