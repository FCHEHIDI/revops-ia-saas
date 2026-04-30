use axum::{
    extract::State,
    http::{HeaderMap, StatusCode},
    response::Json,
    routing::{get, post},
    Router,
};
use serde::{Deserialize, Serialize};
use serde_json::Value;
use sqlx::PgPool;
use std::sync::Arc;
use tracing::{info, instrument, warn};

use crate::rag_client::RagClient;
use crate::storage::ObjectStorage;
use crate::tools::{
    documents::{
        delete_document, get_document_metadata, list_documents, read_document,
        DeleteDocumentInput, GetDocumentMetadataInput, ListDocumentsInput, ReadDocumentInput,
    },
    playbooks::{get_playbook, list_playbooks, GetPlaybookInput, ListPlaybooksInput},
    reports::{list_reports, upload_report, ListReportsInput, UploadReportInput},
    search::{search_documents, SearchDocumentsInput},
};

// ---------------------------------------------------------------------------
// Shared Axum state
// ---------------------------------------------------------------------------

#[derive(Clone)]
pub struct HttpState {
    pub pool: Arc<PgPool>,
    pub storage: Arc<dyn ObjectStorage + Send + Sync>,
    pub rag_client: RagClient,
    pub inter_service_secret: String,
}

// ---------------------------------------------------------------------------
// Request / response DTOs
// ---------------------------------------------------------------------------

#[derive(Debug, Deserialize)]
pub struct McpCallRequest {
    pub tool: String,
    #[serde(default)]
    pub params: Option<Value>,
    #[serde(default)]
    pub tenant_id: Option<String>,
}

#[derive(Debug, Serialize)]
pub struct McpCallResponse {
    pub result: Option<Value>,
    pub error: Option<String>,
}

// ---------------------------------------------------------------------------
// Router
// ---------------------------------------------------------------------------

pub fn router(state: HttpState) -> Router {
    Router::new()
        .route("/health", get(health))
        .route("/tools", get(list_tools_handler))
        .route("/mcp/call", post(mcp_call))
        .with_state(state)
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

fn unauthorized() -> (StatusCode, Json<McpCallResponse>) {
    (
        StatusCode::UNAUTHORIZED,
        Json(McpCallResponse {
            result: None,
            error: Some("UNAUTHORIZED: missing or invalid X-Internal-API-Key".to_string()),
        }),
    )
}

fn ok_resp(data: impl serde::Serialize) -> (StatusCode, Json<McpCallResponse>) {
    (
        StatusCode::OK,
        Json(McpCallResponse {
            result: Some(serde_json::to_value(data).unwrap_or(Value::Null)),
            error: None,
        }),
    )
}

fn err_resp(code: &str, msg: &str) -> (StatusCode, Json<McpCallResponse>) {
    (
        StatusCode::OK,
        Json(McpCallResponse {
            result: None,
            error: Some(format!("{}: {}", code, msg)),
        }),
    )
}

fn bad_params(e: serde_json::Error, tool: &str) -> (StatusCode, Json<McpCallResponse>) {
    (
        StatusCode::UNPROCESSABLE_ENTITY,
        Json(McpCallResponse {
            result: None,
            error: Some(format!("INVALID_PARAMS: {tool}: {e}")),
        }),
    )
}

// ---------------------------------------------------------------------------
// Handlers
// ---------------------------------------------------------------------------

async fn health() -> Json<Value> {
    Json(serde_json::json!({"status": "ok", "service": "mcp-filesystem"}))
}

async fn list_tools_handler() -> Json<Value> {
    Json(serde_json::json!([
        "read_document",
        "list_documents",
        "get_document_metadata",
        "delete_document",
        "list_playbooks",
        "get_playbook",
        "upload_report",
        "list_reports",
        "search_documents"
    ]))
}

#[instrument(skip(state, headers, body), fields(tool = %body.tool))]
async fn mcp_call(
    State(state): State<HttpState>,
    headers: HeaderMap,
    Json(body): Json<McpCallRequest>,
) -> (StatusCode, Json<McpCallResponse>) {
    // ── Auth ──────────────────────────────────────────────────────────────────
    let provided = headers
        .get("x-internal-api-key")
        .and_then(|v| v.to_str().ok())
        .unwrap_or("");
    if provided != state.inter_service_secret {
        warn!("Unauthorized call — invalid X-Internal-API-Key");
        return unauthorized();
    }

    // ── Merge top-level tenant_id into params ─────────────────────────────────
    let mut params = body.params.unwrap_or(Value::Object(serde_json::Map::new()));
    if let Some(tid) = &body.tenant_id {
        if let Value::Object(ref mut map) = params {
            map.entry("tenant_id")
                .or_insert_with(|| Value::String(tid.clone()));
        }
    }

    let pool = state.pool.as_ref();
    let storage = state.storage.as_ref();
    let rag_client = &state.rag_client;
    info!(tool = %body.tool, "MCP HTTP dispatch");

    match body.tool.as_str() {
        // ── Documents ─────────────────────────────────────────────────────────
        "read_document" => match serde_json::from_value::<ReadDocumentInput>(params) {
            Ok(input) => match read_document(input, pool, storage).await {
                Ok(out) => ok_resp(out),
                Err(e) => err_resp(e.error_code(), &e.to_string()),
            },
            Err(e) => bad_params(e, "read_document"),
        },
        "list_documents" => match serde_json::from_value::<ListDocumentsInput>(params) {
            Ok(input) => match list_documents(input, pool).await {
                Ok(out) => ok_resp(out),
                Err(e) => err_resp(e.error_code(), &e.to_string()),
            },
            Err(e) => bad_params(e, "list_documents"),
        },
        "get_document_metadata" => match serde_json::from_value::<GetDocumentMetadataInput>(params) {
            Ok(input) => match get_document_metadata(input, pool).await {
                Ok(out) => ok_resp(out),
                Err(e) => err_resp(e.error_code(), &e.to_string()),
            },
            Err(e) => bad_params(e, "get_document_metadata"),
        },
        "delete_document" => match serde_json::from_value::<DeleteDocumentInput>(params) {
            Ok(input) => match delete_document(input, pool, storage).await {
                Ok(out) => ok_resp(out),
                Err(e) => err_resp(e.error_code(), &e.to_string()),
            },
            Err(e) => bad_params(e, "delete_document"),
        },
        // ── Playbooks ─────────────────────────────────────────────────────────
        "list_playbooks" => match serde_json::from_value::<ListPlaybooksInput>(params) {
            Ok(input) => match list_playbooks(input, pool).await {
                Ok(out) => ok_resp(out),
                Err(e) => err_resp(e.error_code(), &e.to_string()),
            },
            Err(e) => bad_params(e, "list_playbooks"),
        },
        "get_playbook" => match serde_json::from_value::<GetPlaybookInput>(params) {
            Ok(input) => match get_playbook(input, pool).await {
                Ok(out) => ok_resp(out),
                Err(e) => err_resp(e.error_code(), &e.to_string()),
            },
            Err(e) => bad_params(e, "get_playbook"),
        },
        // ── Reports ───────────────────────────────────────────────────────────
        "upload_report" => match serde_json::from_value::<UploadReportInput>(params) {
            Ok(input) => match upload_report(input, pool, storage, rag_client).await {
                Ok(out) => ok_resp(out),
                Err(e) => err_resp(e.error_code(), &e.to_string()),
            },
            Err(e) => bad_params(e, "upload_report"),
        },
        "list_reports" => match serde_json::from_value::<ListReportsInput>(params) {
            Ok(input) => match list_reports(input, pool).await {
                Ok(out) => ok_resp(out),
                Err(e) => err_resp(e.error_code(), &e.to_string()),
            },
            Err(e) => bad_params(e, "list_reports"),
        },
        // ── Search ────────────────────────────────────────────────────────────
        "search_documents" => match serde_json::from_value::<SearchDocumentsInput>(params) {
            Ok(input) => match search_documents(input, pool, rag_client).await {
                Ok(out) => ok_resp(out),
                Err(e) => err_resp(e.error_code(), &e.to_string()),
            },
            Err(e) => bad_params(e, "search_documents"),
        },
        other => (
            StatusCode::NOT_FOUND,
            Json(McpCallResponse {
                result: None,
                error: Some(format!("UNKNOWN_TOOL: {other}")),
            }),
        ),
    }
}
