use reqwest::Client;
use serde::{Deserialize, Serialize};
use std::time::Duration;
use tracing::{error, instrument};
use uuid::Uuid;

use crate::errors::FilesystemError;
use crate::schemas::DocumentChunk;

// ---------------------------------------------------------------------------
// RagClient
// ---------------------------------------------------------------------------

#[derive(Debug, Clone)]
pub struct RagClient {
    pub base_url: String,
    pub client: Client,
    api_key: String,
}

impl RagClient {
    pub fn new(base_url: String, api_key: String) -> Self {
        let client = Client::builder()
            .timeout(Duration::from_secs(5))
            .build()
            .expect("Failed to build reqwest client");

        RagClient { base_url, client, api_key }
    }
}

// ---------------------------------------------------------------------------
// Search
// ---------------------------------------------------------------------------

#[derive(Debug, Serialize)]
struct SearchRequest {
    namespace: String,
    query: String,
    top_k: u32,
    min_score: f32,
    #[serde(skip_serializing_if = "Option::is_none")]
    filters: Option<SearchFilters>,
}

#[derive(Debug, Serialize)]
struct SearchFilters {
    document_types: Vec<String>,
}

#[derive(Debug, Deserialize)]
struct SearchResponse {
    results: Vec<RagChunk>,
    total_found: i64,
}

#[derive(Debug, Deserialize)]
struct RagChunk {
    document_id: Uuid,
    filename: String,
    chunk_index: i32,
    content: String,
    similarity_score: f32,
    document_type: String,
    page_number: Option<i32>,
}

impl RagClient {
    #[instrument(skip(self), fields(tenant_id = %tenant_id, query = %query))]
    pub async fn search(
        &self,
        tenant_id: Uuid,
        query: &str,
        top_k: u32,
        min_score: f32,
        document_types: Option<Vec<String>>,
    ) -> Result<(Vec<DocumentChunk>, i64), FilesystemError> {
        let namespace = format!("tenant_{}", tenant_id);

        let filters = document_types.map(|dt| SearchFilters { document_types: dt });

        let body = SearchRequest {
            namespace,
            query: query.to_string(),
            top_k,
            min_score,
            filters,
        };

        let url = format!("{}/search", self.base_url);

        let response = self
            .client
            .post(&url)
            .header("X-Internal-Api-Key", &self.api_key)
            .json(&body)
            .send()
            .await
            .map_err(|e| {
                if e.is_timeout() {
                    error!("RAG service timeout on /search");
                    FilesystemError::RagServiceUnavailable
                } else {
                    error!("RAG service error on /search: {}", e);
                    FilesystemError::RagServiceUnavailable
                }
            })?;

        if !response.status().is_success() {
            error!("RAG /search returned HTTP {}", response.status());
            return Err(FilesystemError::RagServiceUnavailable);
        }

        let data: SearchResponse = response.json().await.map_err(|e| {
            error!("Failed to deserialize RAG /search response: {}", e);
            FilesystemError::RagServiceUnavailable
        })?;

        let chunks = data
            .results
            .into_iter()
            .map(|r| DocumentChunk {
                document_id: r.document_id,
                filename: r.filename,
                chunk_index: r.chunk_index,
                content: r.content,
                similarity_score: r.similarity_score,
                document_type: r.document_type,
                page_number: r.page_number,
            })
            .collect();

        Ok((chunks, data.total_found))
    }
}

// ---------------------------------------------------------------------------
// Ingest
// ---------------------------------------------------------------------------

#[derive(Debug, Serialize)]
struct IngestRequest {
    namespace: String,
    document_id: Uuid,
    storage_path: String,
}

#[derive(Debug, Deserialize)]
struct IngestResponse {
    job_id: Uuid,
}

impl RagClient {
    #[instrument(skip(self), fields(tenant_id = %tenant_id, document_id = %document_id))]
    pub async fn enqueue_ingestion(
        &self,
        tenant_id: Uuid,
        document_id: Uuid,
        storage_path: &str,
    ) -> Result<Uuid, FilesystemError> {
        let namespace = format!("tenant_{}", tenant_id);

        let body = IngestRequest {
            namespace,
            document_id,
            storage_path: storage_path.to_string(),
        };

        let url = format!("{}/ingest", self.base_url);

        let response = self
            .client
            .post(&url)
            .header("X-Internal-Api-Key", &self.api_key)
            .json(&body)
            .send()
            .await
            .map_err(|e| {
                if e.is_timeout() {
                    error!("RAG service timeout on /ingest");
                    FilesystemError::RagServiceUnavailable
                } else {
                    error!("RAG service error on /ingest: {}", e);
                    FilesystemError::RagServiceUnavailable
                }
            })?;

        if !response.status().is_success() {
            error!("RAG /ingest returned HTTP {}", response.status());
            return Err(FilesystemError::RagServiceUnavailable);
        }

        let data: IngestResponse = response.json().await.map_err(|e| {
            error!("Failed to deserialize RAG /ingest response: {}", e);
            FilesystemError::RagServiceUnavailable
        })?;

        Ok(data.job_id)
    }
}
