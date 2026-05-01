use axum::{
    extract::State,
    http::{HeaderMap, StatusCode},
    response::Json,
    routing::{get, post},
    Router,
};
use chrono::{Datelike, Local, Months, NaiveDate};
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

// ---------------------------------------------------------------------------
// Period normalisation for billing tools
//
// `get_mrr` expects `from_date`/`to_date` (NaiveDate) but the orchestrator
// sends `period: "2025-01"` (YYYY-MM) or a natural-language range.
// ---------------------------------------------------------------------------

/// Resolve a `period` string to `(from_date, to_date)` for billing use.
///
/// Accepts:
/// - ISO month "YYYY-MM" → first and last day of that month
/// - Natural ranges "last_30_days", "current_quarter", etc.
fn resolve_billing_period(period: &str, today: NaiveDate) -> (NaiveDate, NaiveDate) {
    // Try "YYYY-MM" first
    if let Ok(month_date) = NaiveDate::parse_from_str(&format!("{}-01", period), "%Y-%m-%d") {
        let last_day = {
            let next = if month_date.month() == 12 {
                NaiveDate::from_ymd_opt(month_date.year() + 1, 1, 1)
            } else {
                NaiveDate::from_ymd_opt(month_date.year(), month_date.month() + 1, 1)
            };
            next.unwrap_or(month_date) - chrono::Duration::days(1)
        };
        return (month_date, last_day);
    }

    match period {
        "last_30_days" => (today - chrono::Duration::days(30), today),
        "last_90_days" => (today - chrono::Duration::days(90), today),
        "last_6_months" => {
            let start = today.checked_sub_months(Months::new(6)).unwrap_or(today);
            (start, today)
        }
        "last_12_months" | "last_year" => {
            let start = today.checked_sub_months(Months::new(12)).unwrap_or(today);
            (start, today)
        }
        "current_month" => {
            let start =
                NaiveDate::from_ymd_opt(today.year(), today.month(), 1).unwrap_or(today);
            (start, today)
        }
        "current_quarter" => {
            let q_month = ((today.month() - 1) / 3) * 3 + 1;
            let start = NaiveDate::from_ymd_opt(today.year(), q_month, 1).unwrap_or(today);
            (start, today)
        }
        "current_year" => {
            let start = NaiveDate::from_ymd_opt(today.year(), 1, 1).unwrap_or(today);
            (start, today)
        }
        _ => {
            // Fallback: last 30 days
            (today - chrono::Duration::days(30), today)
        }
    }
}

/// For `get_mrr`: translate `period` → `from_date` / `to_date`.
fn normalize_billing_params(tool: &str, params: &mut Value) {
    if tool != "get_mrr" {
        return;
    }
    let today = Local::now().date_naive();
    let map = match params.as_object_mut() {
        Some(m) => m,
        None => return,
    };
    if map.contains_key("period") && !map.contains_key("from_date") {
        if let Some(pv) = map.remove("period") {
            let (from, to) = resolve_billing_period(pv.as_str().unwrap_or("last_30_days"), today);
            map.insert("from_date".to_string(), Value::String(from.to_string()));
            map.insert("to_date".to_string(), Value::String(to.to_string()));
        }
    }
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

    // Translate period strings before deserialisation
    normalize_billing_params(&body.tool, &mut params);

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
