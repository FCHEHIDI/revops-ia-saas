# Docker Compose — Environnement de développement local

> **Stack complète RevOps IA SaaS** en local pour la Phase 2 (Backend + MCP CRM + Orchestrateur + RAG)

---

## Prérequis

- **Docker Desktop** (Windows/Mac) ou Docker Engine + Docker Compose v2 (Linux)
- **Git Bash** ou WSL sur Windows (pour les commandes Makefile optionnelles)
- **Ports disponibles** : 3000, 5432, 6379, 8000, 8080, 8500, 9001

---

## Démarrage rapide

```bash
# À la racine du projet
make dev-up

# Ou directement avec Docker Compose
docker compose -f infra/docker/docker-compose.dev.yml up -d
```

**Attendre que les health checks soient verts** (30-60 secondes) :

```bash
docker compose -f infra/docker/docker-compose.dev.yml ps
```

### Appliquer les migrations Alembic (première fois uniquement)

```bash
docker compose -f infra/docker/docker-compose.dev.yml exec backend alembic upgrade head
```

---

## Ports exposés

| Service        | Port interne | Port host | URL locale                     |
|----------------|--------------|-----------|--------------------------------|
| **Backend**    | 8000         | 8000      | http://localhost:8000          |
| **Orchestrator** | 8080       | 8080      | http://localhost:8080          |
| **MCP CRM**    | 9001         | 9001      | http://localhost:9001/health   |
| **RAG**        | 8002         | 8500      | http://localhost:8500          |
| **Postgres**   | 5432         | 5432      | `postgresql://revops:revops@localhost:5432/revops` |
| **Redis**      | 6379         | 6379      | `redis://localhost:6379/0`     |
| **Frontend**   | 3000         | 3000      | http://localhost:3000 (commenté par défaut) |

---

## Commandes utiles

### Makefile (racine du projet)

```bash
make dev-up        # Démarrer tous les services
make dev-down      # Arrêter tous les services
make dev-logs      # Suivre les logs en temps réel
make dev-ps        # État des containers
make dev-rebuild   # Reconstruire les images (après modif Dockerfile)
```

### Docker Compose direct

```bash
# Démarrer (avec build si nécessaire)
docker compose -f infra/docker/docker-compose.dev.yml up -d --build

# Arrêter
docker compose -f infra/docker/docker-compose.dev.yml down

# Logs d'un service spécifique
docker compose -f infra/docker/docker-compose.dev.yml logs -f backend

# Redémarrer un service
docker compose -f infra/docker/docker-compose.dev.yml restart orchestrator

# Shell dans un container
docker compose -f infra/docker/docker-compose.dev.yml exec backend bash
docker compose -f infra/docker/docker-compose.dev.yml exec postgres psql -U revops -d revops
```

---

## Migrations Alembic

### Appliquer les migrations

```bash
docker compose -f infra/docker/docker-compose.dev.yml exec backend alembic upgrade head
```

### Créer une nouvelle migration

```bash
docker compose -f infra/docker/docker-compose.dev.yml exec backend alembic revision --autogenerate -m "description"
```

### Rétrograder d'une révision

```bash
docker compose -f infra/docker/docker-compose.dev.yml exec backend alembic downgrade -1
```

### Afficher l'état des migrations

```bash
docker compose -f infra/docker/docker-compose.dev.yml exec backend alembic current
```

---

## Réinitialiser la stack (⚠️ supprime les données)

```bash
# Arrêter et supprimer les containers + volumes
docker compose -f infra/docker/docker-compose.dev.yml down -v

# Ou via make
make dev-down && docker volume rm revops-dev_pgdata

# Redémarrer proprement
make dev-up
docker compose -f infra/docker/docker-compose.dev.yml exec backend alembic upgrade head
```

---

## Variables d'environnement

Les secrets de développement sont définis directement dans le `docker-compose.dev.yml`. **Ne jamais** commiter de secrets réels.

| Variable             | Valeur dev                      | Service(s)               |
|----------------------|---------------------------------|--------------------------|
| `DATABASE_URL`       | `postgresql+asyncpg://revops:revops@postgres:5432/revops` | backend, rag |
| `REDIS_URL`          | `redis://redis:6379/0`          | backend, orchestrator, rag |
| `INTERNAL_API_KEY`   | `dev-internal-key-change-me`    | backend, orchestrator, mcp-crm |
| `JWT_SECRET`         | `dev-jwt-secret-change-me`      | backend |
| `ENVIRONMENT`        | `development`                   | backend |

Pour la production, ces variables sont injectées via **HashiCorp Vault** ou **GitHub Secrets** (cf. ADR-005).

---

## Troubleshooting

### Les health checks échouent

```bash
# Vérifier les logs d'un service
docker compose -f infra/docker/docker-compose.dev.yml logs postgres
docker compose -f infra/docker/docker-compose.dev.yml logs redis
```

### Erreur "extension vector does not exist"

L'image `postgres:16-alpine` standard ne contient pas pgvector. Deux solutions :

1. **Commenter `CREATE EXTENSION "vector"` dans `initdb/01-extensions.sql`** (si pas besoin du RAG en local)
2. **Utiliser une image avec pgvector préinstallé** : modifier `docker-compose.dev.yml` pour utiliser `pgvector/pgvector:pg16` ou `timescale/timescaledb-ha:pg16`

### Port déjà utilisé

```bash
# Identifier le processus utilisant le port (ex: 5432)
# Windows (PowerShell)
netstat -ano | findstr :5432

# Linux/macOS
lsof -i :5432

# Stopper le service conflictuel ou changer le port dans docker-compose.dev.yml
```

### Le backend ne se connecte pas à Postgres

Vérifier que le health check de Postgres est vert avant que le backend ne démarre :

```bash
docker compose -f infra/docker/docker-compose.dev.yml ps
```

Si le backend démarre trop tôt, le redémarrer :

```bash
docker compose -f infra/docker/docker-compose.dev.yml restart backend
```

---

## Architecture des dépendances

```
postgres (healthy) ──┬─→ backend ──→ orchestrator ──→ (mcp-crm, rag)
redis (healthy)      ┴─→ rag
```

Les services attendent les health checks `service_healthy` de Postgres et Redis grâce à `depends_on.condition`.

---

## Frontend (optionnel)

Le service `frontend` est **commenté par défaut** dans le compose car il complique le démarrage initial et n'est pas requis pour le développement backend/MCP.

Pour l'activer :
1. Décommenter la section `frontend` dans `docker-compose.dev.yml`
2. S'assurer que le Dockerfile frontend est configuré avec `output: standalone` dans `next.config.js`
3. Rebuilder : `make dev-rebuild`

---

## Bonnes pratiques

- **Ne jamais commit** de secrets réels dans `docker-compose.dev.yml`
- **Appliquer les migrations** après chaque pull contenant de nouvelles migrations Alembic
- **Rebuild les images** après modification d'un `requirements.txt` ou `Cargo.toml` : `make dev-rebuild`
- **Utiliser les logs** pour déboguer : `make dev-logs` ou `docker compose ... logs -f <service>`

---

**ADR de référence** : ADR-005 (multi-tenant RLS), ADR-008 (MCP CRM via backend)

Pour toute question, consulter `docs/ARCHITECTURE.md` et `docs/AUTOPILOT.md`.
