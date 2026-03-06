use serde::{Deserialize, Serialize};
use tracing::{debug, instrument, warn};
use uuid::Uuid;

use crate::{error::AppError, models::RagChunk};

/// HTTP client for the RAG service.
///
/// Calls `POST {rag_url}/retrieve` with tenant-scoped queries.
/// The RAG layer enforces strict tenant isolation via per-tenant
/// Qdrant collections named `tenant_{tenant_id}`.
pub struct RagClient {
    http_client: reqwest::Client,
    base_url: String,
    api_key: String,
}

impl RagClient {
    pub fn new(http_client: reqwest::Client, base_url: String, api_key: String) -> Self {
        Self { http_client, base_url, api_key }
    }

    /// Retrieve the top-K most relevant document chunks for a query.
    ///
    /// Returns an empty vec on RAG errors rather than propagating them —
    /// the orchestrator continues without RAG context rather than failing.
    #[instrument(skip(self), fields(tenant_id = %tenant_id, top_k = top_k))]
    pub async fn retrieve(
        &self,
        tenant_id: &str,
        query: &str,
        top_k: u32,
    ) -> Result<Vec<RagChunk>, AppError> {
        let tenant_uuid: Uuid = tenant_id.parse().map_err(|_| {
            AppError::RagError(format!("Invalid tenant_id UUID: {}", tenant_id))
        })?;

        let request = RetrieveRequest {
            tenant_id: tenant_uuid,
            query: query.to_string(),
            top_k,
            min_score: 0.35,
            document_types: None,
        };

        let url = format!("{}/retrieve", self.base_url);
        debug!(url = %url, query = %query, "Calling RAG retrieve endpoint");

        let response = self
            .http_client
            .post(&url)
            .header("X-Internal-API-Key", &self.api_key)
            .json(&request)
            .send()
            .await
            .map_err(|e| AppError::RagError(format!("Failed to reach RAG service: {}", e)))?;

        if !response.status().is_success() {
            let status = response.status();
            let body = response.text().await.unwrap_or_default();
            warn!(status = %status, body = %body, "RAG service error");
            return Err(AppError::RagError(format!(
                "RAG service returned {}: {}",
                status, body
            )));
        }

        let parsed: RetrieveResponse = response.json().await.map_err(|e| {
            AppError::RagError(format!("Failed to parse RAG response: {}", e))
        })?;

        let chunks: Vec<RagChunk> = parsed
            .results
            .into_iter()
            .map(|r| RagChunk {
                document_id: r.document_id,
                filename: r.filename,
                chunk_index: r.chunk_index as u32,
                content: r.content,
                similarity_score: r.similarity_score as f32,
                document_type: r.document_type,
            })
            .collect();

        debug!(chunks_returned = chunks.len(), "RAG retrieval completed");

        Ok(chunks)
    }
}

// ---------------------------------------------------------------------------
// RAG API schemas — mirror rag/app/models/schemas.py
// ---------------------------------------------------------------------------

#[derive(Serialize)]
struct RetrieveRequest {
    tenant_id: Uuid,
    query: String,
    top_k: u32,
    min_score: f64,
    #[serde(skip_serializing_if = "Option::is_none")]
    document_types: Option<Vec<String>>,
}

#[derive(Deserialize)]
struct RetrieveResponse {
    results: Vec<ChunkResult>,
    #[allow(dead_code)]
    total_found: u32,
}

#[derive(Deserialize)]
struct ChunkResult {
    document_id: Uuid,
    filename: String,
    chunk_index: i64,
    content: String,
    similarity_score: f64,
    document_type: String,
}
