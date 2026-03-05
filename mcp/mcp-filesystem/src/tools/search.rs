use serde::{Deserialize, Serialize};
use serde_json::json;
use sqlx::PgPool;
use tracing::{error, instrument};
use uuid::Uuid;

use crate::audit::{write_audit, AuditEntry};
use crate::db::validate_tenant;
use crate::errors::FilesystemError;
use crate::rag_client::RagClient;
use crate::schemas::{DocumentChunk, DocumentType, DEFAULT_MIN_SCORE, DEFAULT_TOP_K, MAX_TOP_K};

// ---------------------------------------------------------------------------
// search_documents
// ---------------------------------------------------------------------------

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SearchDocumentsInput {
    pub tenant_id: Uuid,
    pub user_id: Option<Uuid>,
    pub query: String,
    pub document_types: Option<Vec<DocumentType>>,
    pub top_k: Option<u32>,
    pub min_score: Option<f32>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SearchDocumentsOutput {
    pub results: Vec<DocumentChunk>,
    pub query_used: String,
    pub total_found: i64,
}

#[instrument(skip(pool, rag_client), fields(tool = "search_documents", tenant_id = %input.tenant_id))]
pub async fn search_documents(
    input: SearchDocumentsInput,
    pool: &PgPool,
    rag_client: &RagClient,
) -> Result<SearchDocumentsOutput, FilesystemError> {
    let start = std::time::Instant::now();
    validate_tenant(input.tenant_id, pool).await?;

    // Validate query is non-empty
    let query = input.query.trim().to_string();
    if query.is_empty() {
        return Err(FilesystemError::ValidationError(
            "query cannot be empty".to_string(),
        ));
    }

    let top_k = input.top_k.unwrap_or(DEFAULT_TOP_K).min(MAX_TOP_K);

    let min_score = input
        .min_score
        .unwrap_or(DEFAULT_MIN_SCORE)
        .clamp(0.0, 1.0);

    let document_type_strings = input.document_types.as_ref().map(|types| {
        types
            .iter()
            .map(|t| t.as_str().to_string())
            .collect::<Vec<_>>()
    });

    let (results, total_found) = rag_client
        .search(
            input.tenant_id,
            &query,
            top_k,
            min_score,
            document_type_strings,
        )
        .await?;

    let duration_ms = start.elapsed().as_millis() as i64;
    let audit_entry = AuditEntry::new(
        input.tenant_id,
        input.user_id,
        "search_documents",
        &json!({
            "query_len": query.len(),
            "top_k": top_k,
            "min_score": min_score,
            "document_types": input.document_types,
            "results_count": results.len(),
        }),
        "OK",
        duration_ms,
    );
    if let Err(e) = write_audit(audit_entry, pool).await {
        error!("Audit write failed for search_documents: {}", e);
    }

    Ok(SearchDocumentsOutput {
        results,
        query_used: query,
        total_found,
    })
}
