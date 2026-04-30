# mcp-crm

MCP CRM server for the RevOps IA SaaS platform.

Exposes 12 CRM tools (contacts, accounts, deals) to the Rust LLM orchestrator via a custom HTTP transport. Acts exclusively as a **stateless HTTP proxy** — no database access, no persistent state.

Implements [ADR-008](../../docs/adr/ADR-008-mcp-crm-architecture.md).

---

## Architecture

```
Orchestrator (Rust)
      │
      │  POST /mcp/call
      │  { "tool": "get_contact", "params": {...}, "tenant_id": "..." }
      ▼
mcp-crm (Python · FastAPI · port 9001)
      │
      │  GET/POST/PUT /internal/v1/crm/*
      │  X-Internal-API-Key + X-Tenant-ID
      ▼
Backend (FastAPI · port 8000)
      │
      │  SQLAlchemy + SET app.current_tenant_id
      ▼
PostgreSQL (RLS enabled)
```

---

## Tools exposés

| Tool | Description | Backend endpoint |
|------|-------------|-----------------|
| `get_contact` | Retrieve a contact by ID | `GET /internal/v1/crm/contacts/{id}` |
| `search_contacts` | Search contacts with filters | `GET /internal/v1/crm/contacts` |
| `create_contact` | Create a new contact | `POST /internal/v1/crm/contacts` |
| `update_contact` | Partially update a contact | `PUT /internal/v1/crm/contacts/{id}` |
| `get_account` | Retrieve an account by ID | `GET /internal/v1/crm/accounts/{id}` |
| `search_accounts` | Search accounts with filters | `GET /internal/v1/crm/accounts` |
| `create_account` | Create a new account | `POST /internal/v1/crm/accounts` |
| `update_account` | Partially update an account | `PUT /internal/v1/crm/accounts/{id}` |
| `get_deal` | Retrieve a deal by ID | `GET /internal/v1/crm/deals/{id}` |
| `list_deals` | List deals with filters | `GET /internal/v1/crm/deals` |
| `create_deal` | Create a new deal | `POST /internal/v1/crm/deals` |
| `update_deal_stage` | Transition a deal to a new stage | `PUT /internal/v1/crm/deals/{id}` |

The orchestrator calls tools using the prefixed name `mcp_crm__<tool>` (e.g. `mcp_crm__get_contact`). The prefix is stripped before forwarding to this server.

---

## Variables d'environnement

| Variable | Requis | Défaut | Description |
|----------|--------|--------|-------------|
| `BACKEND_URL` | **Oui** | — | Base URL of the internal FastAPI backend |
| `INTERNAL_API_KEY` | **Oui** | — | Shared secret for inter-service authentication |
| `PORT` | Non | `9001` | HTTP server port |
| `LOG_LEVEL` | Non | `INFO` | Log level (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |
| `HTTP_TIMEOUT` | Non | `10.0` | httpx read timeout (seconds) |

---

## Lancer localement

```bash
cd mcp/mcp-crm

python -m venv .venv
# Windows
.venv\Scripts\activate
# Linux/macOS
source .venv/bin/activate

pip install -r requirements-dev.txt

cp .env.example .env
# Edit .env with your BACKEND_URL and INTERNAL_API_KEY

python src/main.py
```

Server starts at `http://localhost:9001`.

---

## Lancer avec Docker

```bash
docker build -t mcp-crm .

docker run -p 9001:9001 \
  -e BACKEND_URL=http://host.docker.internal:8000 \
  -e INTERNAL_API_KEY=your-secret \
  mcp-crm
```

---

## Tester

```bash
cd mcp/mcp-crm
pip install -r requirements-dev.txt

pytest tests/ -v
```

All tests are fully isolated — no real backend required. HTTP calls are mocked with `respx`.

---

## Contrat HTTP `/mcp/call`

### Request

```http
POST /mcp/call
Content-Type: application/json

{
  "tool": "get_contact",
  "params": {
    "tenant_id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
    "contact_id": "a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d"
  },
  "tenant_id": "f47ac10b-58cc-4372-a567-0e02b2c3d479"
}
```

### Response — success

```json
{
  "result": {
    "contact": {
      "id": "a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d",
      "first_name": "Alice",
      "last_name": "Dupont",
      "email": "alice@example.com",
      ...
    }
  },
  "error": null
}
```

### Response — error

```json
{
  "result": null,
  "error": "NOT_FOUND: Resource not found: Contact not found"
}
```

### Error codes

| Code | Meaning |
|------|---------|
| `INVALID_TENANT` | `tenant_id` absent or not a valid UUID |
| `VALIDATION_ERROR` | Missing required field or invalid value |
| `NOT_FOUND` | Resource does not exist for this tenant |
| `UNAUTHORIZED` | Invalid internal API key |
| `FORBIDDEN` | Insufficient RBAC permissions |
| `CONFLICT` | Duplicate resource (e.g. email already exists) |
| `BACKEND_UNAVAILABLE` | Backend returned 5xx or connection failed |
| `UNKNOWN_TOOL` | Tool name not registered |
| `INTERNAL_ERROR` | Unexpected server error |

---

## Other endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /health` | Health check — returns `{"status": "ok"}` |
| `GET /tools` | Lists all 12 tools with their input schemas |
