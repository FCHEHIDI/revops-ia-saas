use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use serde_json::json;
use sqlx::PgPool;
use tracing::{error, instrument, warn};
use uuid::Uuid;

use crate::audit::{write_audit, AuditEntry};
use crate::db::validate_tenant;
use crate::errors::FilesystemError;
use crate::schemas::{DocumentMetadata, DocumentType, DEFAULT_MAX_CHARS, MAX_READ_CHARS};
use crate::storage::ObjectStorage;

// ---------------------------------------------------------------------------
// read_document
// ---------------------------------------------------------------------------

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ReadDocumentInput {
    pub tenant_id: Uuid,
    pub user_id: Option<Uuid>,
    pub document_id: Uuid,
    pub max_chars: Option<usize>,
    pub page_range: Option<(u32, u32)>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ReadDocumentOutput {
    pub document_id: Uuid,
    pub filename: String,
    pub content: String,
    pub total_chars: usize,
    pub truncated: bool,
    pub mime_type: String,
    pub page_count: Option<i32>,
}

struct DocumentRow {
    id: Uuid,
    tenant_id: Uuid,
    filename: String,
    mime_type: String,
    storage_path: String,
    page_count: Option<i32>,
}

#[instrument(skip(pool, storage), fields(tool = "read_document"))]
pub async fn read_document(
    input: ReadDocumentInput,
    pool: &PgPool,
    storage: &dyn ObjectStorage,
) -> Result<ReadDocumentOutput, FilesystemError> {
    let start = std::time::Instant::now();
    validate_tenant(input.tenant_id, pool).await?;

    let max_chars = input
        .max_chars
        .unwrap_or(DEFAULT_MAX_CHARS)
        .min(MAX_READ_CHARS);

    let row = sqlx::query_as!(
        DocumentRow,
        r#"
        SELECT id, tenant_id, filename, mime_type, storage_path, page_count
        FROM fs_documents
        WHERE id = $1 AND tenant_id = $2
        "#,
        input.document_id,
        input.tenant_id,
    )
    .fetch_optional(pool)
    .await
    .map_err(FilesystemError::DatabaseError)?
    .ok_or_else(|| FilesystemError::NotFound(format!("document:{}", input.document_id)))?;

    let raw_bytes = storage.read_content(&row.storage_path).await?;

    let full_content = String::from_utf8_lossy(&raw_bytes).into_owned();
    let total_chars = full_content.chars().count();

    let (content, truncated) = if total_chars > max_chars {
        let truncated_content: String = full_content.chars().take(max_chars).collect();
        (truncated_content, true)
    } else {
        (full_content, false)
    };

    let duration_ms = start.elapsed().as_millis() as i64;
    let audit_entry = AuditEntry::new(
        input.tenant_id,
        input.user_id,
        "read_document",
        &json!({ "document_id": input.document_id, "max_chars": max_chars }),
        "OK",
        duration_ms,
    );
    if let Err(e) = write_audit(audit_entry, pool).await {
        error!("Audit write failed for read_document: {}", e);
    }

    Ok(ReadDocumentOutput {
        document_id: row.id,
        filename: row.filename,
        content,
        total_chars,
        truncated,
        mime_type: row.mime_type,
        page_count: row.page_count,
    })
}

// ---------------------------------------------------------------------------
// list_documents
// ---------------------------------------------------------------------------

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ListDocumentsInput {
    pub tenant_id: Uuid,
    pub user_id: Option<Uuid>,
    pub document_type: Option<DocumentType>,
    pub tags: Option<Vec<String>>,
    pub search_query: Option<String>,
    pub uploaded_after: Option<DateTime<Utc>>,
    pub limit: Option<u32>,
    pub offset: Option<u32>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ListDocumentsOutput {
    pub documents: Vec<DocumentMetadata>,
    pub total: i64,
}

struct DocumentMetaRow {
    id: Uuid,
    tenant_id: Uuid,
    filename: String,
    document_type: DocumentType,
    mime_type: String,
    size_bytes: i64,
    tags: Vec<String>,
    rag_indexed: bool,
    rag_indexed_at: Option<DateTime<Utc>>,
    uploaded_by: Uuid,
    created_at: DateTime<Utc>,
    updated_at: DateTime<Utc>,
}

#[instrument(skip(pool), fields(tool = "list_documents"))]
pub async fn list_documents(
    input: ListDocumentsInput,
    pool: &PgPool,
) -> Result<ListDocumentsOutput, FilesystemError> {
    let start = std::time::Instant::now();
    validate_tenant(input.tenant_id, pool).await?;

    let limit = input.limit.unwrap_or(50).min(200) as i64;
    let offset = input.offset.unwrap_or(0) as i64;
    let search_pattern = input
        .search_query
        .as_deref()
        .map(|q| format!("%{}%", q));
    let tags_filter = input.tags.clone();

    let rows = sqlx::query_as!(
        DocumentMetaRow,
        r#"
        SELECT
            id,
            tenant_id,
            filename,
            document_type AS "document_type: DocumentType",
            mime_type,
            size_bytes,
            tags,
            rag_indexed,
            rag_indexed_at,
            uploaded_by,
            created_at,
            updated_at
        FROM fs_documents
        WHERE tenant_id = $1
          AND ($2::document_type IS NULL OR document_type = $2)
          AND ($3::text IS NULL OR filename ILIKE $3)
          AND ($4::timestamptz IS NULL OR created_at >= $4)
          AND ($5::text[] IS NULL OR tags @> $5)
        ORDER BY created_at DESC
        LIMIT $6 OFFSET $7
        "#,
        input.tenant_id,
        input.document_type as Option<DocumentType>,
        search_pattern,
        input.uploaded_after,
        tags_filter.as_deref(),
        limit,
        offset,
    )
    .fetch_all(pool)
    .await
    .map_err(FilesystemError::DatabaseError)?;

    let total: i64 = sqlx::query_scalar!(
        r#"
        SELECT COUNT(*)
        FROM fs_documents
        WHERE tenant_id = $1
          AND ($2::document_type IS NULL OR document_type = $2)
          AND ($3::text IS NULL OR filename ILIKE $3)
          AND ($4::timestamptz IS NULL OR created_at >= $4)
          AND ($5::text[] IS NULL OR tags @> $5)
        "#,
        input.tenant_id,
        input.document_type as Option<DocumentType>,
        search_pattern,
        input.uploaded_after,
        tags_filter.as_deref(),
    )
    .fetch_one(pool)
    .await
    .map_err(FilesystemError::DatabaseError)?
    .unwrap_or(0);

    let documents = rows
        .into_iter()
        .map(|r| DocumentMetadata {
            id: r.id,
            tenant_id: r.tenant_id,
            filename: r.filename,
            document_type: r.document_type,
            mime_type: r.mime_type,
            size_bytes: r.size_bytes,
            tags: r.tags,
            rag_indexed: r.rag_indexed,
            rag_indexed_at: r.rag_indexed_at,
            uploaded_by: r.uploaded_by,
            created_at: r.created_at,
            updated_at: r.updated_at,
        })
        .collect();

    let duration_ms = start.elapsed().as_millis() as i64;
    let audit_entry = AuditEntry::new(
        input.tenant_id,
        input.user_id,
        "list_documents",
        &json!({ "document_type": input.document_type, "search_query": input.search_query }),
        "OK",
        duration_ms,
    );
    if let Err(e) = write_audit(audit_entry, pool).await {
        error!("Audit write failed for list_documents: {}", e);
    }

    Ok(ListDocumentsOutput { documents, total })
}

// ---------------------------------------------------------------------------
// get_document_metadata
// ---------------------------------------------------------------------------

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GetDocumentMetadataInput {
    pub tenant_id: Uuid,
    pub user_id: Option<Uuid>,
    pub document_id: Uuid,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GetDocumentMetadataOutput {
    pub metadata: DocumentMetadata,
}

#[instrument(skip(pool), fields(tool = "get_document_metadata"))]
pub async fn get_document_metadata(
    input: GetDocumentMetadataInput,
    pool: &PgPool,
) -> Result<GetDocumentMetadataOutput, FilesystemError> {
    let start = std::time::Instant::now();
    validate_tenant(input.tenant_id, pool).await?;

    let row = sqlx::query_as!(
        DocumentMetaRow,
        r#"
        SELECT
            id,
            tenant_id,
            filename,
            document_type AS "document_type: DocumentType",
            mime_type,
            size_bytes,
            tags,
            rag_indexed,
            rag_indexed_at,
            uploaded_by,
            created_at,
            updated_at
        FROM fs_documents
        WHERE id = $1 AND tenant_id = $2
        "#,
        input.document_id,
        input.tenant_id,
    )
    .fetch_optional(pool)
    .await
    .map_err(FilesystemError::DatabaseError)?
    .ok_or_else(|| FilesystemError::NotFound(format!("document:{}", input.document_id)))?;

    let duration_ms = start.elapsed().as_millis() as i64;
    let audit_entry = AuditEntry::new(
        input.tenant_id,
        input.user_id,
        "get_document_metadata",
        &json!({ "document_id": input.document_id }),
        "OK",
        duration_ms,
    );
    if let Err(e) = write_audit(audit_entry, pool).await {
        error!("Audit write failed for get_document_metadata: {}", e);
    }

    Ok(GetDocumentMetadataOutput {
        metadata: DocumentMetadata {
            id: row.id,
            tenant_id: row.tenant_id,
            filename: row.filename,
            document_type: row.document_type,
            mime_type: row.mime_type,
            size_bytes: row.size_bytes,
            tags: row.tags,
            rag_indexed: row.rag_indexed,
            rag_indexed_at: row.rag_indexed_at,
            uploaded_by: row.uploaded_by,
            created_at: row.created_at,
            updated_at: row.updated_at,
        },
    })
}

// ---------------------------------------------------------------------------
// delete_document
// ---------------------------------------------------------------------------

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DeleteDocumentInput {
    pub tenant_id: Uuid,
    pub user_id: Option<Uuid>,
    pub document_id: Uuid,
    pub confirm: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DeleteDocumentOutput {
    pub deleted_at: DateTime<Utc>,
    pub storage_bytes_freed: i64,
}

struct DeleteDocumentRow {
    storage_path: String,
    size_bytes: i64,
}

#[instrument(skip(pool, storage), fields(tool = "delete_document"))]
pub async fn delete_document(
    input: DeleteDocumentInput,
    pool: &PgPool,
    storage: &dyn ObjectStorage,
) -> Result<DeleteDocumentOutput, FilesystemError> {
    let start = std::time::Instant::now();
    validate_tenant(input.tenant_id, pool).await?;

    if !input.confirm {
        return Err(FilesystemError::ConfirmationRequired);
    }

    let row = sqlx::query_as!(
        DeleteDocumentRow,
        r#"
        SELECT storage_path, size_bytes
        FROM fs_documents
        WHERE id = $1 AND tenant_id = $2
        "#,
        input.document_id,
        input.tenant_id,
    )
    .fetch_optional(pool)
    .await
    .map_err(FilesystemError::DatabaseError)?
    .ok_or_else(|| FilesystemError::NotFound(format!("document:{}", input.document_id)))?;

    // Delete from DB first
    sqlx::query!(
        "DELETE FROM fs_documents WHERE id = $1 AND tenant_id = $2",
        input.document_id,
        input.tenant_id,
    )
    .execute(pool)
    .await
    .map_err(FilesystemError::DatabaseError)?;

    let deleted_at = Utc::now();

    // Delete from storage — log on failure, do not propagate
    match storage.delete(&row.storage_path).await {
        Ok(_) => {}
        Err(e) => {
            warn!(
                "Storage delete failed for orphaned path '{}' (document {}): {}",
                row.storage_path, input.document_id, e
            );
        }
    }

    let duration_ms = start.elapsed().as_millis() as i64;
    let audit_entry = AuditEntry::new(
        input.tenant_id,
        input.user_id,
        "delete_document",
        &json!({ "document_id": input.document_id }),
        "DELETED",
        duration_ms,
    );
    if let Err(e) = write_audit(audit_entry, pool).await {
        error!("Audit write failed for delete_document: {}", e);
    }

    Ok(DeleteDocumentOutput {
        deleted_at,
        storage_bytes_freed: row.size_bytes,
    })
}
