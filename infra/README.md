# infra — Infrastructure RevOps IA SaaS

Infrastructure as Code du projet RevOps IA SaaS.

## Structure

```
infra/
├── docker/                     # Orchestration locale (développement)
│   ├── docker-compose.yml      # Stack complète en local
│   └── docker-compose.dev.yml  # Overrides développement (hot reload, ports exposés)
├── kubernetes/                 # Manifests Kubernetes (production)
│   ├── base/                   # Manifests de base (Kustomize)
│   │   ├── backend/            # Deployment + Service + ConfigMap backend API
│   │   ├── orchestrator/       # Deployment + Service orchestrateur Rust
│   │   ├── mcp/                # Deployments + Services serveurs MCP (5 services)
│   │   ├── rag/                # Deployment + Service couche RAG
│   │   ├── frontend/           # Deployment + Service frontend Next.js
│   │   ├── redis/              # StatefulSet Redis
│   │   └── postgres/           # StatefulSet PostgreSQL + pgvector
│   └── overlays/
│       ├── dev/                # Kustomize overlay développement (minikube)
│       └── prod/               # Kustomize overlay production (ressources, replicas)
├── terraform/                  # Infrastructure cloud (Kubernetes cluster, DNS, etc.)
│   ├── main.tf                 # Ressources principales
│   ├── variables.tf            # Variables d'entrée
│   └── outputs.tf              # Sorties (endpoints, credentials)
├── helm/
│   └── revops-ia/              # Helm chart de l'application complète
│       └── templates/          # Templates Helm
├── monitoring/                 # Observabilité
│   ├── prometheus/             # Configuration Prometheus (scrape configs)
│   └── grafana/
│       └── dashboards/         # Dashboards JSON Grafana (latence, queue, GPU)
└── ci/
    └── github-actions/         # Workflows GitHub Actions (CI/CD)
```

## Développement local

```bash
# Lancer toute la stack
docker compose -f infra/docker/docker-compose.yml up

# Lancer uniquement les services tiers (postgres, redis)
docker compose -f infra/docker/docker-compose.yml up postgres redis
```

## Déploiement Kubernetes

```bash
# Appliquer les manifests de base
kubectl apply -k infra/kubernetes/base/

# Appliquer l'overlay de dev
kubectl apply -k infra/kubernetes/overlays/dev/
```

## Services et ports locaux

| Service | Port local | Description |
|---------|-----------|-------------|
| frontend | 3000 | UI Next.js |
| backend | 8000 | API FastAPI |
| orchestrator | 8001 | Orchestrateur Rust |
| rag | 8002 | Service RAG FastAPI |
| mcp-crm | 9001 | Serveur MCP CRM |
| mcp-billing | 9002 | Serveur MCP Billing |
| mcp-analytics | 9003 | Serveur MCP Analytics |
| mcp-sequences | 9004 | Serveur MCP Sequences |
| mcp-filesystem | 9005 | Serveur MCP Filesystem |
| postgres | 5432 | PostgreSQL + pgvector |
| redis | 6379 | Redis (queue + cache) |
| prometheus | 9090 | Métriques |
| grafana | 3001 | Dashboards |
