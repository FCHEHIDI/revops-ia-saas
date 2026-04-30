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
    invoices::{
        get_invoice, list_invoices, list_overdue_payments, GetInvoiceInput, ListInvoicesInput,
        ListOverduePaymentsInput,
    },
    subscriptions::{
        check_subscription_status, get_subscription, update_subscription_status,
        CheckSubscriptionStatusInput, GetSubscriptionInput, UpdateSubscriptionStatusInput,
    },
    summary::{
        get_customer_billing_summary, get_mrr, GetCustomerBillingSummaryInput, GetMrrInput,
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
    Json(serde_json::json!({"status": "ok", "service": "mcp-billing"}))
}

async fn list_tools_handler() -> Json<Value> {
    Json(serde_json::json!([
        "get_invoice", "list_invoices", "list_overdue_payments",
        "get_subscription", "check_subscription_status", "update_subscription_status",
        "get_customer_billing_summary", "get_mrr"
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
        // ── Invoices ──────────────────────────────────────────────────────────
        "get_invoice" => match serde_json::from_value::<GetInvoiceInput>(params) {
            Ok(input) => match get_invoice(input, pool).await {
                Ok(out) => ok_resp(out),
                Err(e) => err_resp(e.error_code(), &e.to_string()),
            },
            Err(e) => bad_params(e, "get_invoice"),
        },
        "list_invoices" => match serde_json::from_value::<ListInvoicesInput>(params) {
            Ok(input) => match list_invoices(input, pool).await {
                Ok(out) => ok_resp(out),
                Err(e) => err_resp(e.error_code(), &e.to_string()),
            },
            Err(e) => bad_params(e, "list_invoices"),
        },
        "list_overdue_payments" => match serde_json::from_value::<ListOverduePaymentsInput>(params) {
            Ok(input) => match list_overdue_payments(input, pool).await {
                Ok(out) => ok_resp(out),
                Err(e) => err_resp(e.error_code(), &e.to_string()),
            },
            Err(e) => bad_params(e, "list_overdue_payments"),
        },
        // ── Subscriptions ─────────────────────────────────────────────────────
        "get_subscription" => match serde_json::from_value::<GetSubscriptionInput>(params) {
            Ok(input) => match get_subscription(input, pool).await {
                Ok(out) => ok_resp(out),
                Err(e) => err_resp(e.error_code(), &e.to_string()),
            },
            Err(e) => bad_params(e, "get_subscription"),
        },
        "check_subscription_status" => {
            match serde_json::from_value::<CheckSubscriptionStatusInput>(params) {
                Ok(input) => match check_subscription_status(input, pool).await {
                    Ok(out) => ok_resp(out),
                    Err(e) => err_resp(e.error_code(), &e.to_string()),
                },
                Err(e) => bad_params(e, "check_subscription_status"),
            }
        }
        "update_subscription_status" => {
            match serde_json::from_value::<UpdateSubscriptionStatusInput>(params) {
                Ok(input) => match update_subscription_status(input, pool).await {
                    Ok(out) => ok_resp(out),
                    Err(e) => err_resp(e.error_code(), &e.to_string()),
                },
                Err(e) => bad_params(e, "update_subscription_status"),
            }
        }
        // ── Summary ───────────────────────────────────────────────────────────
        "get_customer_billing_summary" => {
            match serde_json::from_value::<GetCustomerBillingSummaryInput>(params) {
                Ok(input) => match get_customer_billing_summary(input, pool).await {
                    Ok(out) => ok_resp(out),
                    Err(e) => err_resp(e.error_code(), &e.to_string()),
                },
                Err(e) => bad_params(e, "get_customer_billing_summary"),
            }
        }
        "get_mrr" => match serde_json::from_value::<GetMrrInput>(params) {
            Ok(input) => match get_mrr(input, pool).await {
                Ok(out) => ok_resp(out),
                Err(e) => err_resp(e.error_code(), &e.to_string()),
            },
            Err(e) => bad_params(e, "get_mrr"),
        },
        unknown => {
            error!(tool = unknown, "Unknown billing tool");
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
