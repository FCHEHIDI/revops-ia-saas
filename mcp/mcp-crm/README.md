# mcp-crm

MCP server for CRM domain: contacts, accounts, deals, pipeline analytics, and activities.

Built in Rust (edition 2021) with Tokio async, `rmcp` SDK, and `sqlx` PostgreSQL.

---

## Architecture

`mcp-crm` is a **stateless**, **isolated** microservice. It:

- Validates the `tenant_id` on every call before any business logic
- Sets PostgreSQL Row-Level Security via `set_config('app.current_tenant_id', ...)`
- Appends all calls to the `audit_events` table with a SHA-256 params hash
- Returns structured errors with consistent error codes and HTTP-equivalent status codes
- Exposes 15 MCP tools across 5 domains

```
src/
├── main.rs          — entry point: tracing init, config, pool, transport start
├── server.rs        — ServerHandler impl, tool dispatch
├── config.rs        — env var loading (DATABASE_URL, MCP_TRANSPORT, LOG_LEVEL)
├── db.rs            — PgPool creation, validate_tenant()
├── audit.rs         — AuditEntry, write_audit(), hash_params()
├── errors.rs        — CrmError enum with error codes and MCP serialization
├── schemas.rs       — core entities, enums, summary structs, pagination
└── tools/
    ├── contacts.rs  — get_contact, search_contacts, create_contact, update_contact
    ├── accounts.rs  — get_account, search_accounts, create_account, update_account
    ├── deals.rs     — get_deal, search_deals, create_deal, update_deal_stage, delete_deal
    ├── pipeline.rs  — get_pipeline_summary
    └── activities.rs— list_activities, log_activity
```

---

## Environment Variables

| Variable       | Required | Default | Description                          |
|----------------|----------|---------|--------------------------------------|
| `DATABASE_URL` | Yes      | —       | PostgreSQL connection string         |
| `MCP_TRANSPORT`| No       | `stdio` | Transport: `stdio` or `sse`          |
| `LOG_LEVEL`    | No       | `info`  | Tracing filter (e.g. `debug`, `info`)|
| `SSE_BIND_ADDR`| No       | `0.0.0.0:3001` | Bind address for SSE transport |

---

## Tools

### Contacts

#### `get_contact`
Retrieves a single contact by ID.

**Input:**
```json
{
  "tenant_id": "uuid",
  "user_id": "uuid (optional)",
  "contact_id": "uuid"
}
```
**Output:** `{ "contact": Contact }`

**Errors:** `TENANT_FORBIDDEN` (403), `NOT_FOUND` (404), `DATABASE_ERROR` (500)

---

#### `search_contacts`
Full-text search across first_name, last_name, email with optional status/account filters.

**Input:**
```json
{
  "tenant_id": "uuid",
  "query": "string (optional)",
  "status": "active|inactive|prospect|customer|churned (optional)",
  "account_id": "uuid (optional)",
  "page": 1,
  "page_size": 20
}
```
**Output:** `{ "contacts": [ContactSummary], "total": int, "page": int, "page_size": int }`

---

#### `create_contact`
Creates a new contact. Email must be unique per tenant.

**Input:**
```json
{
  "tenant_id": "uuid",
  "first_name": "string",
  "last_name": "string",
  "email": "string",
  "phone": "string (optional)",
  "title": "string (optional)",
  "account_id": "uuid (optional)",
  "status": "prospect (default)",
  "custom_fields": {}
}
```
**Output:** `{ "contact": Contact }`

**Errors:** `VALIDATION_ERROR` (422), `CONFLICT` (409), `TENANT_FORBIDDEN` (403)

---

#### `update_contact`
PATCH semantics — only provided fields are updated; omitted fields retain their current values.

**Input:**
```json
{
  "tenant_id": "uuid",
  "contact_id": "uuid",
  "first_name": "string (optional)",
  "last_name": "string (optional)",
  "email": "string (optional)",
  ...
}
```
**Output:** `{ "contact": Contact }`

---

### Accounts

#### `get_account` / `search_accounts` / `create_account` / `update_account`
Same pattern as contacts. Domain: accounts/companies.

`create_account` enforces unique domain per tenant if `domain` is provided.

---

### Deals

#### `get_deal`
**Input:** `{ "tenant_id", "deal_id" }`
**Output:** `{ "deal": Deal }`

---

#### `search_deals`
**Input:** `{ "tenant_id", "query?", "stage?", "account_id?", "assigned_to?", "page", "page_size" }`
**Output:** `{ "deals": [DealSummary], "total", "page", "page_size" }`

---

#### `create_deal`
Creates a deal with a required linked account.

**Input:**
```json
{
  "tenant_id": "uuid",
  "name": "Enterprise License Q2",
  "account_id": "uuid",
  "value": "50000.00",
  "currency": "EUR",
  "close_date": "2026-06-30",
  "stage": "prospecting (default)",
  "probability": 0.3,
  "assigned_to": "uuid (optional)"
}
```

---

#### `update_deal_stage`
Transitions a deal stage with validation of allowed transitions.

**Allowed transitions:**
- `prospecting` → `qualification`, `closed_lost`
- `qualification` → `proposal`, `closed_lost`
- `proposal` → `negotiation`, `closed_lost`
- `negotiation` → `closed_won`, `closed_lost`
- `closed_lost` → `prospecting` (re-open)

**Input:**
```json
{
  "tenant_id": "uuid",
  "deal_id": "uuid",
  "new_stage": "proposal",
  "reason": "string (optional)"
}
```
**Output:** `{ "deal": Deal, "previous_stage": "qualification", "new_stage": "proposal" }`

**Errors:** `INVALID_TRANSITION` (422), `NOT_FOUND` (404)

---

#### `delete_deal`
Permanently deletes a deal. Requires the caller to explicitly pass `"permission": "crm:deals:delete"`.

**Input:**
```json
{
  "tenant_id": "uuid",
  "deal_id": "uuid",
  "permission": "crm:deals:delete"
}
```
**Output:** `{ "deleted": true, "deal_id": "uuid" }`

**Errors:** `PERMISSION_DENIED` (403), `NOT_FOUND` (404)

---

### Pipeline

#### `get_pipeline_summary`
Returns aggregated stats for all open pipeline stages.

**Input:**
```json
{
  "tenant_id": "uuid",
  "assigned_to": "uuid (optional)"
}
```
**Output:**
```json
{
  "stages": [
    {
      "stage": "qualification",
      "deal_count": 12,
      "total_value": "840000.00",
      "avg_value": "70000.00",
      "avg_age_days": 23.4
    }
  ],
  "total_pipeline_value": "2100000.00",
  "total_open_deals": 45,
  "weighted_pipeline_value": "630000.00"
}
```

---

### Activities

#### `list_activities`
Lists activities for any entity (contact, deal, account) sorted by `occurred_at` DESC.

**Input:**
```json
{
  "tenant_id": "uuid",
  "entity_type": "contact|deal|account",
  "entity_id": "uuid",
  "activity_type": "call|email|meeting|note|task (optional)",
  "page": 1,
  "page_size": 20
}
```

---

#### `log_activity`
Records a new activity against an entity.

**Input:**
```json
{
  "tenant_id": "uuid",
  "entity_type": "deal",
  "entity_id": "uuid",
  "activity_type": "call",
  "subject": "Discovery call Q1",
  "notes": "Discussed budget constraints",
  "duration_minutes": 45,
  "performed_by": "uuid",
  "occurred_at": "2026-03-05T14:30:00Z (optional, defaults to now)"
}
```
**Output:** `{ "activity": Activity }`

---

## Security Model

1. **Tenant validation first** — every tool starts with `validate_tenant()`, returning `403 TENANT_FORBIDDEN` before any other logic runs
2. **Defense in depth** — all SQL queries include `WHERE tenant_id = $N` even though RLS is set at the connection level
3. **Audit trail** — every call writes to `audit_events` with a SHA-256 hash of the parameters (tenant_id/user_id stripped from hash for privacy)
4. **No state in memory** — `CrmServer` holds only an `Arc<PgPool>`; no caches, no sessions
5. **No inter-MCP calls** — the orchestrator coordinates between MCP servers; mcp-crm only talks to PostgreSQL

---

## Error Codes

| Code                | HTTP | Meaning                                           |
|---------------------|------|---------------------------------------------------|
| `TENANT_FORBIDDEN`  | 403  | Tenant does not exist or is inactive              |
| `PERMISSION_DENIED` | 403  | Caller lacks required permission                  |
| `NOT_FOUND`         | 404  | Resource not found within the tenant scope        |
| `VALIDATION_ERROR`  | 422  | Input failed validation                           |
| `CONFLICT`          | 409  | Unique constraint violated (email, domain, etc.)  |
| `INVALID_TRANSITION`| 422  | Deal stage transition not allowed                 |
| `DATABASE_ERROR`    | 500  | Unexpected PostgreSQL error                       |
| `INTERNAL_ERROR`    | 500  | Unexpected internal error                         |

---

## JSON-RPC Examples

### Initialize
```json
{ "jsonrpc": "2.0", "method": "initialize", "id": 1, "params": { "protocolVersion": "2024-11-05", "clientInfo": { "name": "orchestrator", "version": "1.0" }, "capabilities": {} } }
```

### List tools
```json
{ "jsonrpc": "2.0", "method": "tools/list", "id": 2, "params": {} }
```

### Call get_contact
```json
{
  "jsonrpc": "2.0",
  "method": "tools/call",
  "id": 3,
  "params": {
    "name": "get_contact",
    "arguments": {
      "tenant_id": "550e8400-e29b-41d4-a716-446655440000",
      "user_id": "6ba7b810-9dad-11d1-80b4-00c04fd430c8",
      "contact_id": "6ba7b811-9dad-11d1-80b4-00c04fd430c8"
    }
  }
}
```

### Call update_deal_stage
```json
{
  "jsonrpc": "2.0",
  "method": "tools/call",
  "id": 4,
  "params": {
    "name": "update_deal_stage",
    "arguments": {
      "tenant_id": "550e8400-e29b-41d4-a716-446655440000",
      "deal_id": "7c9e6679-7425-40de-944b-e07fc1f90ae7",
      "new_stage": "proposal",
      "reason": "Proposal document sent"
    }
  }
}
```
