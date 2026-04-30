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
use tracing::{error, info, instrument, warn};

use crate::tools::{
    analytics::{get_sequence_performance, GetSequencePerformanceInput},
    enrollment::{enroll_contact, unenroll_contact, list_enrollments, EnrollContactInput, UnenrollContactInput, ListEnrollmentsInput},
    execution::{pause_sequence, resume_sequence, PauseSequenceInput, ResumeSequenceInput},
    sequences::{
        create_sequence, update_sequence, delete_sequence, get_sequence, list_sequences,
        CreateSequenceInput, UpdateSequenceInput, DeleteSequenceInput, GetSequenceInput, ListSequencesInput,
    },
};

// ---------------------------------------------------------------------------
// Shared Axum state
// ---------------------------------------------------------------------------

#[derive(Clone)]
pub struct HttpState {
    pub pool: Arc<PgPool>,
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
// Handlers
// ---------------------------------------------------------------------------

async fn health() -> Json<Value> {
    Json(serde_json::json!({"status": "ok", "service": "mcp-sequences"}))
}

async fn list_tools_handler() -> Json<Value> {
    Json(serde_json::json!([
        "create_sequence", "update_sequence", "delete_sequence", "get_sequence", "list_sequences",
        "enroll_contact", "unenroll_contact", "list_enrollments",
        "pause_sequence", "resume_sequence",
        "get_sequence_performance"
    ]))
}

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
    info!(tool = %body.tool, "MCP HTTP dispatch");

    match body.tool.as_str() {
        // ── Sequences CRUD ────────────────────────────────────────────────────
        "create_sequence" => match serde_json::from_value::<CreateSequenceInput>(params) {
            Ok(input) => match create_sequence(input, pool).await {
                Ok(out) => ok_resp(out),
                Err(e) => err_resp(e.error_code(), &e.to_string()),
            },
            Err(e) => bad_params(e, "create_sequence"),
        },
        "update_sequence" => match serde_json::from_value::<UpdateSequenceInput>(params) {
            Ok(input) => match update_sequence(input, pool).await {
                Ok(out) => ok_resp(out),
                Err(e) => err_resp(e.error_code(), &e.to_string()),
            },
            Err(e) => bad_params(e, "update_sequence"),
        },
        "delete_sequence" => match serde_json::from_value::<DeleteSequenceInput>(params) {
            Ok(input) => match delete_sequence(input, pool).await {
                Ok(out) => ok_resp(out),
                Err(e) => err_resp(e.error_code(), &e.to_string()),
            },
            Err(e) => bad_params(e, "delete_sequence"),
        },
        "get_sequence" => match serde_json::from_value::<GetSequenceInput>(params) {
            Ok(input) => match get_sequence(input, pool).await {
                Ok(out) => ok_resp(out),
                Err(e) => err_resp(e.error_code(), &e.to_string()),
            },
            Err(e) => bad_params(e, "get_sequence"),
        },
        "list_sequences" => match serde_json::from_value::<ListSequencesInput>(params) {
            Ok(input) => match list_sequences(input, pool).await {
                Ok(out) => ok_resp(out),
                Err(e) => err_resp(e.error_code(), &e.to_string()),
            },
            Err(e) => bad_params(e, "list_sequences"),
        },
        // ── Enrollment ────────────────────────────────────────────────────────
        "enroll_contact" => match serde_json::from_value::<EnrollContactInput>(params) {
            Ok(input) => match enroll_contact(input, pool).await {
                Ok(out) => ok_resp(out),
                Err(e) => err_resp(e.error_code(), &e.to_string()),
            },
            Err(e) => bad_params(e, "enroll_contact"),
        },
        "unenroll_contact" => match serde_json::from_value::<UnenrollContactInput>(params) {
            Ok(input) => match unenroll_contact(input, pool).await {
                Ok(out) => ok_resp(out),
                Err(e) => err_resp(e.error_code(), &e.to_string()),
            },
            Err(e) => bad_params(e, "unenroll_contact"),
        },
        "list_enrollments" => match serde_json::from_value::<ListEnrollmentsInput>(params) {
            Ok(input) => match list_enrollments(input, pool).await {
                Ok(out) => ok_resp(out),
                Err(e) => err_resp(e.error_code(), &e.to_string()),
            },
            Err(e) => bad_params(e, "list_enrollments"),
        },
        // ── Execution ─────────────────────────────────────────────────────────
        "pause_sequence" => match serde_json::from_value::<PauseSequenceInput>(params) {
            Ok(input) => match pause_sequence(input, pool).await {
                Ok(out) => ok_resp(out),
                Err(e) => err_resp(e.error_code(), &e.to_string()),
            },
            Err(e) => bad_params(e, "pause_sequence"),
        },
        "resume_sequence" => match serde_json::from_value::<ResumeSequenceInput>(params) {
            Ok(input) => match resume_sequence(input, pool).await {
                Ok(out) => ok_resp(out),
                Err(e) => err_resp(e.error_code(), &e.to_string()),
            },
            Err(e) => bad_params(e, "resume_sequence"),
        },
        // ── Analytics ─────────────────────────────────────────────────────────
        "get_sequence_performance" => match serde_json::from_value::<GetSequencePerformanceInput>(params) {
            Ok(input) => match get_sequence_performance(input, pool).await {
                Ok(out) => ok_resp(out),
                Err(e) => err_resp(e.error_code(), &e.to_string()),
            },
            Err(e) => bad_params(e, "get_sequence_performance"),
        },
        unknown => {
            error!(tool = unknown, "Unknown sequences tool");
            (
                StatusCode::NOT_FOUND,
                Json(McpCallResponse {
                    result: None,
                    error: Some(format!("UNKNOWN_TOOL: {}", unknown)),
                }),
            )
        }
    }
}
