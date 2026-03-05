# mcp-filesystem

MCP server for document storage, playbook management, report upload, and RAG-powered semantic search — part of the RevOps IA SaaS platform.

## Architecture

- **Stateless** microservice, no in-memory state between calls
- **Multi-tenant** via Row-Level Security (`app.current_tenant_id`)
- `storage_path` is an **internal field only** — never exposed in tool outputs
- Every tool call emits a non-blocking audit log entry
- Storage abstracted behind `ObjectStorage` trait (LocalStorage MVP, S3 ready)
- RAG calls go through `RagClient` HTTP client with 5 s timeout

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `DATABASE_URL` | _required_ | PostgreSQL connection string |
| `MCP_TRANSPORT` | `stdio` | `stdio` or `sse` |
| `STORAGE_BACKEND` | `local` | `local` or `s3` |
| `STORAGE_BASE_DIR` | `/data/storage` | Base path for LocalStorage |
| `RAG_SERVICE_URL` | `http://rag-service:8000` | RAG HTTP service base URL |
| `LOG_LEVEL` | `info` | tracing log level |
| `SSE_BIND_ADDR` | `0.0.0.0:3005` | Bind address when `MCP_TRANSPORT=sse` |

## Tools

### Documents

#### `read_document`
Reads text content of a document by ID.

**Permission**: `filesystem:documents:read`

**Input**:
```json
{
  "tenant_id": "uuid",
  "user_id": "uuid (optional)",
  "document_id": "uuid",
  "max_chars": 10000,
  "page_range": [1, 5]
}
```

**Output**:
```json
{
  "document_id": "uuid",
  "filename": "string",
  "content": "string",
  "total_chars": 12345,
  "truncated": false,
  "mime_type": "text/markdown",
  "page_count": 5
}
```

**Errors**: `TENANT_FORBIDDEN`, `NOT_FOUND`, `STORAGE_ERROR`

---

#### `list_documents`
Lists documents with optional filters.

**Permission**: `filesystem:documents:read`

**Input**:
```json
{
  "tenant_id": "uuid",
  "document_type": "report",
  "tags": ["q4", "finance"],
  "search_query": "pipeline",
  "uploaded_after": "2025-01-01T00:00:00Z",
  "limit": 50,
  "offset": 0
}
```

**Output**:
```json
{
  "documents": [ { "id": "...", "filename": "...", "document_type": "...", ... } ],
  "total": 123
}
```

**Note**: `storage_path` is never included in output.

---

#### `get_document_metadata`
Returns metadata for a single document.

**Permission**: `filesystem:documents:read`

**Output**: `{ "metadata": { ...DocumentMetadata... } }`

---

#### `delete_document`
Permanently deletes a document. Requires `confirm: true`.

**Permission**: `filesystem:documents:delete`

**Logic**: DB deleted first; storage delete on failure is logged but does not block the response.

**Output**:
```json
{
  "deleted_at": "2025-03-01T12:00:00Z",
  "storage_bytes_freed": 204800
}
```

**Errors**: `CONFIRMATION_REQUIRED`, `NOT_FOUND`, `TENANT_FORBIDDEN`

---

### Playbooks

#### `list_playbooks`
Lists active playbooks, optionally filtered by category and tags.

**Permission**: `filesystem:playbooks:read`

**Output**:
```json
{
  "playbooks": [ { "id": "...", "title": "...", "category": "battle_card", ... } ],
  "total": 12
}
```

---

#### `get_playbook`
Returns the full markdown content of an active playbook.

**Permission**: `filesystem:playbooks:read`

**Output**: `{ "playbook": { ...Playbook including content... } }`

---

### Reports

#### `upload_report`
Uploads a text/markdown/JSON/HTML report (max 5 MB text). Optionally queues for RAG ingestion.

**Permission**: `filesystem:reports:write`

**Accepted MIME types**: `text/plain`, `text/markdown`, `application/json`, `text/html`

**Logic**:
1. Validate MIME type and content size
2. Write to storage first
3. Insert into DB (orphan logged if DB fails)
4. Optionally enqueue RAG ingestion (failure is logged, not propagated)

**Output**:
```json
{
  "document_id": "uuid",
  "uploaded_at": "2025-03-01T12:00:00Z",
  "rag_ingestion_queued": true,
  "rag_job_id": "uuid"
}
```

---

#### `list_reports`
Lists reports with optional type and date range filters.

**Permission**: `filesystem:reports:read`

**Output**: `{ "reports": [...DocumentMetadata...], "total": 45 }`

---

### Search

#### `search_documents`
Semantic search over tenant documents via the RAG service.

**Permission**: `filesystem:documents:read`

**Input**:
```json
{
  "tenant_id": "uuid",
  "query": "objection handling pricing",
  "document_types": ["playbook", "report"],
  "top_k": 5,
  "min_score": 0.5
}
```

**Output**:
```json
{
  "results": [
    {
      "document_id": "uuid",
      "filename": "pricing-guide-v3.md",
      "chunk_index": 2,
      "content": "...",
      "similarity_score": 0.87,
      "document_type": "playbook",
      "page_number": 4
    }
  ],
  "query_used": "objection handling pricing",
  "total_found": 12
}
```

**Errors**: `RAG_SERVICE_UNAVAILABLE` (5 s timeout), `VALIDATION_ERROR` (empty query)

---

## Storage Abstraction

```
ObjectStorage (trait)
  └── LocalStorage      — tokio::fs, base_dir configurable (MVP / dev / tests)
  └── S3Storage         — to be implemented (production)
```

`storage_path` format: `tenants/{tenant_id}/reports/{document_id}/{filename}`

## Security Rules

1. `validate_tenant()` is the **first** call in every handler
2. All SQL queries include `WHERE tenant_id = $N`
3. `storage_path` is **never** serialised into tool output structs
4. `delete_document` requires explicit `confirm: true`
5. Audit log is fire-and-forget — failures are logged, never propagated
6. No inter-MCP calls — RAG is accessed via HTTP only

## Database Tables Required

```sql
-- documents
CREATE TABLE documents (
    id             UUID PRIMARY KEY,
    tenant_id      UUID NOT NULL REFERENCES organizations(id),
    filename       TEXT NOT NULL,
    document_type  document_type NOT NULL,
    mime_type      TEXT NOT NULL,
    size_bytes     BIGINT NOT NULL,
    storage_path   TEXT NOT NULL,  -- internal only, never in API output
    tags           TEXT[] NOT NULL DEFAULT '{}',
    rag_indexed    BOOLEAN NOT NULL DEFAULT false,
    rag_indexed_at TIMESTAMPTZ,
    uploaded_by    UUID NOT NULL,
    page_count     INT,
    created_at     TIMESTAMPTZ NOT NULL,
    updated_at     TIMESTAMPTZ NOT NULL
);

-- playbooks
CREATE TABLE playbooks (
    id          UUID PRIMARY KEY,
    tenant_id   UUID NOT NULL REFERENCES organizations(id),
    title       TEXT NOT NULL,
    description TEXT,
    category    playbook_category NOT NULL,
    content     TEXT NOT NULL,
    tags        TEXT[] NOT NULL DEFAULT '{}',
    version     TEXT NOT NULL DEFAULT '1.0',
    is_active   BOOLEAN NOT NULL DEFAULT true,
    created_by  UUID NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL,
    updated_at  TIMESTAMPTZ NOT NULL
);
```
