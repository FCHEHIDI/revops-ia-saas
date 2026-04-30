use chrono::{DateTime, NaiveDate, Utc};
use serde::{Deserialize, Serialize};
use serde_json::json;
use sqlx::PgPool;
use tracing::{error, instrument, warn};
use uuid::Uuid;

use crate::audit::{write_audit, AuditEntry};
use crate::db::validate_tenant;
use crate::errors::FilesystemError;
use crate::rag_client::RagClient;
use crate::schemas::{
    DocumentMetadata, DocumentType, ReportType, ACCEPTED_MIME_TYPES, MAX_UPLOAD_CHARS,
};
use crate::storage::ObjectStorage;

// ---------------------------------------------------------------------------
// upload_report
// ---------------------------------------------------------------------------

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct UploadReportInput {
    pub tenant_id: Uuid,
    pub user_id: Option<Uuid>,
    pub filename: String,
    pub content: String,
    pub mime_type: String,
    pub report_type: ReportType,
    pub tags: Vec<String>,
    pub ingest_to_rag: bool,
    pub metadata: serde_json::Value,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct UploadReportOutput {
    pub document_id: Uuid,
    pub uploaded_at: DateTime<Utc>,
    pub rag_ingestion_queued: bool,
    pub rag_job_id: Option<Uuid>,
}

#[instrument(skip(pool, storage, rag_client, input), fields(tool = "upload_report", tenant_id = %input.tenant_id))]
pub async fn upload_report(
    input: UploadReportInput,
    pool: &PgPool,
    storage: &dyn ObjectStorage,
    rag_client: &RagClient,
) -> Result<UploadReportOutput, FilesystemError> {
    let start = std::time::Instant::now();
    validate_tenant(input.tenant_id, pool).await?;

    // Validate MIME type
    if !ACCEPTED_MIME_TYPES.contains(&input.mime_type.as_str()) {
        return Err(FilesystemError::UnsupportedMimeType(input.mime_type.clone()));
    }

    // Validate content size
    let content_len = input.content.len();
    if content_len > MAX_UPLOAD_CHARS {
        return Err(FilesystemError::FileTooLarge {
            size: content_len,
            max: MAX_UPLOAD_CHARS,
        });
    }

    if input.filename.trim().is_empty() {
        return Err(FilesystemError::ValidationError(
            "filename cannot be empty".to_string(),
        ));
    }

    let document_id = Uuid::new_v4();
    let storage_path = format!(
        "tenants/{}/reports/{}/{}",
        input.tenant_id, document_id, input.filename
    );
    let size_bytes = content_len as i64;
    let uploaded_by = input.user_id.unwrap_or(Uuid::nil());
    let now = Utc::now();

    // Store in storage first
    storage
        .write(&storage_path, input.content.as_bytes())
        .await?;

    // Insert into DB
    let db_result = sqlx::query!(
        r#"
        INSERT INTO fs_documents (
            id, tenant_id, filename, document_type, mime_type,
            size_bytes, storage_path, tags, rag_indexed,
            uploaded_by, created_at, updated_at
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, false, $9, $10, $11)
        "#,
        document_id,
        input.tenant_id,
        input.filename.trim(),
        DocumentType::Report as DocumentType,
        input.mime_type,
        size_bytes,
        storage_path,
        &input.tags,
        uploaded_by,
        now,
        now,
    )
    .execute(pool)
    .await;

    if let Err(e) = db_result {
        // DB failed after storage write — log the orphaned path
        warn!(
            "DB insert failed after storage write for orphaned path '{}': {}",
            storage_path, e
        );
        return Err(FilesystemError::DatabaseError(e));
    }

    // Optionally enqueue RAG ingestion
    let (rag_ingestion_queued, rag_job_id) = if input.ingest_to_rag {
        match rag_client
            .enqueue_ingestion(input.tenant_id, document_id, &storage_path)
            .await
        {
            Ok(job_id) => (true, Some(job_id)),
            Err(e) => {
                warn!(
                    "RAG ingestion enqueue failed for document {}: {}",
                    document_id, e
                );
                (false, None)
            }
        }
    } else {
        (false, None)
    };

    let duration_ms = start.elapsed().as_millis() as i64;
    let audit_entry = AuditEntry::new(
        input.tenant_id,
        input.user_id,
        "upload_report",
        &json!({
            "document_id": document_id,
            "filename": input.filename,
            "report_type": input.report_type,
            "size_bytes": size_bytes,
            "ingest_to_rag": input.ingest_to_rag,
        }),
        "CREATED",
        duration_ms,
    );
    if let Err(e) = write_audit(audit_entry, pool).await {
        error!("Audit write failed for upload_report: {}", e);
    }

    Ok(UploadReportOutput {
        document_id,
        uploaded_at: now,
        rag_ingestion_queued,
        rag_job_id,
    })
}

// ---------------------------------------------------------------------------
// list_reports
// ---------------------------------------------------------------------------

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ListReportsInput {
    pub tenant_id: Uuid,
    pub user_id: Option<Uuid>,
    pub report_type: Option<ReportType>,
    pub from_date: Option<NaiveDate>,
    pub to_date: Option<NaiveDate>,
    pub limit: Option<u32>,
    pub offset: Option<u32>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ListReportsOutput {
    pub reports: Vec<DocumentMetadata>,
    pub total: i64,
}

struct ReportRow {
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

#[instrument(skip(pool), fields(tool = "list_reports"))]
pub async fn list_reports(
    input: ListReportsInput,
    pool: &PgPool,
) -> Result<ListReportsOutput, FilesystemError> {
    let start = std::time::Instant::now();
    validate_tenant(input.tenant_id, pool).await?;

    let limit = input.limit.unwrap_or(50).min(200) as i64;
    let offset = input.offset.unwrap_or(0) as i64;

    let from_dt = input
        .from_date
        .map(|d| d.and_hms_opt(0, 0, 0).unwrap().and_utc());
    let to_dt = input
        .to_date
        .map(|d| d.and_hms_opt(23, 59, 59).unwrap().and_utc());

    // report_type is stored in a tags-like metadata column or as a sub-type;
    // for MVP we store it as a tag: "report_type:{value}"
    let report_type_tag = input
        .report_type
        .as_ref()
        .map(|rt| format!("report_type:{}", serde_json::to_string(rt).unwrap_or_default().trim_matches('"')));

    let rows = sqlx::query_as!(
        ReportRow,
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
          AND document_type = 'report'
          AND ($2::timestamptz IS NULL OR created_at >= $2)
          AND ($3::timestamptz IS NULL OR created_at <= $3)
          AND ($4::text IS NULL OR $4 = ANY(tags))
        ORDER BY created_at DESC
        LIMIT $5 OFFSET $6
        "#,
        input.tenant_id,
        from_dt,
        to_dt,
        report_type_tag,
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
          AND document_type = 'report'
          AND ($2::timestamptz IS NULL OR created_at >= $2)
          AND ($3::timestamptz IS NULL OR created_at <= $3)
          AND ($4::text IS NULL OR $4 = ANY(tags))
        "#,
        input.tenant_id,
        from_dt,
        to_dt,
        report_type_tag,
    )
    .fetch_one(pool)
    .await
    .map_err(FilesystemError::DatabaseError)?
    .unwrap_or(0);

    let reports = rows
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
        "list_reports",
        &json!({ "report_type": input.report_type, "from_date": input.from_date, "to_date": input.to_date }),
        "OK",
        duration_ms,
    );
    if let Err(e) = write_audit(audit_entry, pool).await {
        error!("Audit write failed for list_reports: {}", e);
    }

    Ok(ListReportsOutput { reports, total })
}
