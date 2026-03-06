COMPOSE := docker compose -f infra/docker/docker-compose.yml
BACKEND_CONTAINER := revops-ia-saas-backend-1
# NOTE Windows: ce Makefile requiert bash (Git Bash / WSL) ou GNU Make.
# Sur PowerShell, utiliser directement les commandes docker compose.

.PHONY: up down build logs ps migrate migrate-down \
        test-backend test-rag test-rust test-mcp \
        lint lint-backend lint-rag lint-rust lint-frontend \
        clean help

# ── Cluster Docker Compose ────────────────────────────────────────────────────

up: ## Démarrer tous les services en arrière-plan
	$(COMPOSE) up -d

down: ## Arrêter tous les services
	$(COMPOSE) down

build: ## Reconstruire toutes les images
	$(COMPOSE) build

build-no-cache: ## Reconstruire sans cache
	$(COMPOSE) build --no-cache

logs: ## Suivre les logs de tous les services
	$(COMPOSE) logs -f

logs-%: ## Suivre les logs d'un service (ex: make logs-backend)
	$(COMPOSE) logs -f $*

ps: ## État des containers
	$(COMPOSE) ps

restart-%: ## Redémarrer un service (ex: make restart-backend)
	$(COMPOSE) restart $*

# ── Migrations Alembic ────────────────────────────────────────────────────────

migrate: ## Appliquer les migrations (alembic upgrade head)
	$(COMPOSE) exec backend alembic upgrade head

migrate-down: ## Rétrograder d'une révision
	$(COMPOSE) exec backend alembic downgrade -1

migrate-status: ## Afficher le statut des migrations
	$(COMPOSE) exec backend alembic current

# ── Tests ─────────────────────────────────────────────────────────────────────

test-backend: ## Tests du backend FastAPI
	cd backend && pytest tests/ -v --asyncio-mode=auto

test-rag: ## Tests du service RAG
	cd rag && pytest tests/ -v --asyncio-mode=auto

test-orchestrator: ## Tests de l'orchestrateur Rust
	cd orchestrator && cargo test

test-mcp: ## Tests de tous les MCP (séquentiel - compatible tous OS)
	for svc in mcp-crm mcp-billing mcp-analytics mcp-sequences mcp-filesystem; do \
	  echo "=== Testing $$svc ==="; \
	  (cd mcp/$$svc && cargo test) || exit 1; \
	done

test-rust: test-orchestrator test-mcp ## Tests de toutes les crates Rust

# ── Linting ───────────────────────────────────────────────────────────────────

lint-backend: ## Lint backend Python
	cd backend && ruff check .

lint-rag: ## Lint RAG Python
	cd rag && ruff check .

lint-orchestrator: ## Lint orchestrateur Rust
	cd orchestrator && cargo fmt --check && cargo clippy -- -D warnings

lint-mcp: ## Lint tous les MCP Rust
	for svc in mcp-crm mcp-billing mcp-analytics mcp-sequences mcp-filesystem; do \
	  echo "--- $$svc ---"; \
	  (cd mcp/$$svc && cargo fmt --check && cargo clippy -- -D warnings); \
	done

lint-frontend: ## Lint frontend Next.js
	cd frontend && npm run lint && npm run type-check

lint: lint-backend lint-rag lint-orchestrator lint-mcp lint-frontend ## Lint tout le projet

# ── Utilitaires ───────────────────────────────────────────────────────────────

clean: ## Supprimer les containers, volumes et images du projet
	$(COMPOSE) down -v --rmi local

psql: ## Ouvrir psql dans le container postgres
	$(COMPOSE) exec postgres psql -U postgres -d revops_db

redis-cli: ## Ouvrir redis-cli dans le container redis
	$(COMPOSE) exec redis redis-cli

help: ## Afficher cette aide
	@grep -E '^[a-zA-Z_%-]+:.*##' $(MAKEFILE_LIST) | \
	  awk 'BEGIN {FS = ":.*##"}; {printf "  \033[36m%-22s\033[0m %s\n", $$1, $$2}'
