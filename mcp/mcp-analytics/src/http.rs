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
    activity::{get_activity_metrics, GetActivityMetricsInput},
    churn::{compute_churn_rate, get_at_risk_accounts, ComputeChurnRateInput, GetAtRiskAccountsInput},
    performance::{
        get_rep_performance, get_team_leaderboard, GetRepPerformanceInput,
        GetTeamLeaderboardInput,
    },
    pipeline::{
        get_deal_velocity, get_funnel_analysis, get_pipeline_metrics, GetDealVelocityInput,
        GetFunnelAnalysisInput, GetPipelineMetricsInput,
    },
    revenue::{forecast_revenue, get_mrr_trend, ForecastRevenueInput, GetMrrTrendInput},
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
    Json(serde_json::json!({"status": "ok", "service": "mcp-analytics"}))
}

async fn list_tools_handler() -> Json<Value> {
    Json(serde_json::json!([
        "get_pipeline_metrics", "get_deal_velocity", "get_funnel_analysis",
        "forecast_revenue", "get_mrr_trend",
        "compute_churn_rate", "get_at_risk_accounts",
        "get_rep_performance", "get_team_leaderboard",
        "get_activity_metrics"
    ]))
}

// ---------------------------------------------------------------------------
// Period normalisation helpers
//
// The orchestrator sends a high-level `period` string (e.g. "last_30_days").
// Each tool input struct requires explicit ISO 8601 dates or a month count.
// These helpers translate the period before serde deserialisation.
// ---------------------------------------------------------------------------

/// Map a natural-language period to (period_start, period_end) dates.
fn resolve_period(period: &str, today: NaiveDate) -> (NaiveDate, NaiveDate) {
    match period {
        "last_7_days" => (today - chrono::Duration::days(7), today),
        "last_30_days" => (today - chrono::Duration::days(30), today),
        "last_90_days" => (today - chrono::Duration::days(90), today),
        "last_6_months" | "last_180_days" => {
            let start = today.checked_sub_months(Months::new(6)).unwrap_or(today);
            (start, today)
        }
        "last_12_months" => {
            let start = today.checked_sub_months(Months::new(12)).unwrap_or(today);
            (start, today)
        }
        "current_month" => {
            let start =
                NaiveDate::from_ymd_opt(today.year(), today.month(), 1).unwrap_or(today);
            (start, today)
        }
        "last_month" => {
            let first_of_current =
                NaiveDate::from_ymd_opt(today.year(), today.month(), 1).unwrap_or(today);
            let end = first_of_current - chrono::Duration::days(1);
            let start =
                NaiveDate::from_ymd_opt(end.year(), end.month(), 1).unwrap_or(end);
            (start, end)
        }
        "current_quarter" => {
            let q_month = ((today.month() - 1) / 3) * 3 + 1;
            let start = NaiveDate::from_ymd_opt(today.year(), q_month, 1).unwrap_or(today);
            (start, today)
        }
        "last_quarter" => {
            let q_month = ((today.month() - 1) / 3) * 3 + 1;
            let q_start = NaiveDate::from_ymd_opt(today.year(), q_month, 1).unwrap_or(today);
            let end = q_start - chrono::Duration::days(1);
            let prev_q_month = ((end.month() - 1) / 3) * 3 + 1;
            let start =
                NaiveDate::from_ymd_opt(end.year(), prev_q_month, 1).unwrap_or(end);
            (start, end)
        }
        "current_year" => {
            let start = NaiveDate::from_ymd_opt(today.year(), 1, 1).unwrap_or(today);
            (start, today)
        }
        "last_year" | "previous_year" => {
            let start = NaiveDate::from_ymd_opt(today.year() - 1, 1, 1).unwrap_or(today);
            let end = NaiveDate::from_ymd_opt(today.year() - 1, 12, 31).unwrap_or(today);
            (start, end)
        }
        _ => (today - chrono::Duration::days(30), today),
    }
}

/// Map a period string to a month count (for `get_mrr_trend` and `forecast_revenue`).
fn period_to_months(period: &str) -> u8 {
    match period {
        "last_month" | "current_month" | "next_month" => 1,
        "last_3_months" | "current_quarter" | "last_quarter" | "next_quarter" => 3,
        "last_6_months" | "next_6_months" => 6,
        "last_12_months" | "last_year" | "current_year" | "next_year" => 12,
        _ => 3,
    }
}

/// Translate LLM-friendly params into the exact fields expected by each input struct.
///
/// Runs in-place on the JSON params object before serde deserialisation.
fn normalize_period_params(tool: &str, params: &mut Value) {
    let today = Local::now().date_naive();
    let map = match params.as_object_mut() {
        Some(m) => m,
        None => return,
    };

    if tool == "forecast_revenue" {
        // period → forecast_months; inject defaults for model and include_existing_mrr
        if let Some(pv) = map.remove("period") {
            let months = period_to_months(pv.as_str().unwrap_or("next_quarter"));
            map.entry("forecast_months")
                .or_insert_with(|| Value::Number(months.into()));
        }
        map.entry("model")
            .or_insert_with(|| Value::String("weighted_pipeline".to_string()));
        map.entry("include_existing_mrr")
            .or_insert(Value::Bool(true));
        // confidence_level was in old defs — silently remove it
        map.remove("confidence_level");
        return;
    }

    if tool == "get_mrr_trend" {
        // period → months
        if let Some(pv) = map.remove("period") {
            let months = period_to_months(pv.as_str().unwrap_or("last_12_months"));
            map.entry("months")
                .or_insert_with(|| Value::Number(months.into()));
        }
        return;
    }

    // All other period-based analytics tools: period → period_start + period_end
    if map.contains_key("period") && !map.contains_key("period_start") {
        if let Some(pv) = map.remove("period") {
            let (start, end) = resolve_period(pv.as_str().unwrap_or("last_30_days"), today);
            map.insert("period_start".to_string(), Value::String(start.to_string()));
            map.insert("period_end".to_string(), Value::String(end.to_string()));
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

    // Translate period strings and inject defaults before deserialisation
    normalize_period_params(&body.tool, &mut params);

    match body.tool.as_str() {
        // ── Pipeline ──────────────────────────────────────────────────────────
        "get_pipeline_metrics" => match serde_json::from_value::<GetPipelineMetricsInput>(params) {
            Ok(input) => match get_pipeline_metrics(input, pool).await {
                Ok(out) => ok_resp(out),
                Err(e) => err_resp(e.error_code(), &e.to_string()),
            },
            Err(e) => bad_params(e, "get_pipeline_metrics"),
        },
        "get_deal_velocity" => match serde_json::from_value::<GetDealVelocityInput>(params) {
            Ok(input) => match get_deal_velocity(input, pool).await {
                Ok(out) => ok_resp(out),
                Err(e) => err_resp(e.error_code(), &e.to_string()),
            },
            Err(e) => bad_params(e, "get_deal_velocity"),
        },
        "get_funnel_analysis" => match serde_json::from_value::<GetFunnelAnalysisInput>(params) {
            Ok(input) => match get_funnel_analysis(input, pool).await {
                Ok(out) => ok_resp(out),
                Err(e) => err_resp(e.error_code(), &e.to_string()),
            },
            Err(e) => bad_params(e, "get_funnel_analysis"),
        },
        // ── Revenue ───────────────────────────────────────────────────────────
        "forecast_revenue" => match serde_json::from_value::<ForecastRevenueInput>(params) {
            Ok(input) => match forecast_revenue(input, pool).await {
                Ok(out) => ok_resp(out),
                Err(e) => err_resp(e.error_code(), &e.to_string()),
            },
            Err(e) => bad_params(e, "forecast_revenue"),
        },
        "get_mrr_trend" => match serde_json::from_value::<GetMrrTrendInput>(params) {
            Ok(input) => match get_mrr_trend(input, pool).await {
                Ok(out) => ok_resp(out),
                Err(e) => err_resp(e.error_code(), &e.to_string()),
            },
            Err(e) => bad_params(e, "get_mrr_trend"),
        },
        // ── Churn ─────────────────────────────────────────────────────────────
        "compute_churn_rate" => match serde_json::from_value::<ComputeChurnRateInput>(params) {
            Ok(input) => match compute_churn_rate(input, pool).await {
                Ok(out) => ok_resp(out),
                Err(e) => err_resp(e.error_code(), &e.to_string()),
            },
            Err(e) => bad_params(e, "compute_churn_rate"),
        },
        "get_at_risk_accounts" => match serde_json::from_value::<GetAtRiskAccountsInput>(params) {
            Ok(input) => match get_at_risk_accounts(input, pool).await {
                Ok(out) => ok_resp(out),
                Err(e) => err_resp(e.error_code(), &e.to_string()),
            },
            Err(e) => bad_params(e, "get_at_risk_accounts"),
        },
        // ── Performance ───────────────────────────────────────────────────────
        "get_rep_performance" => match serde_json::from_value::<GetRepPerformanceInput>(params) {
            Ok(input) => match get_rep_performance(input, pool).await {
                Ok(out) => ok_resp(out),
                Err(e) => err_resp(e.error_code(), &e.to_string()),
            },
            Err(e) => bad_params(e, "get_rep_performance"),
        },
        "get_team_leaderboard" => match serde_json::from_value::<GetTeamLeaderboardInput>(params) {
            Ok(input) => match get_team_leaderboard(input, pool).await {
                Ok(out) => ok_resp(out),
                Err(e) => err_resp(e.error_code(), &e.to_string()),
            },
            Err(e) => bad_params(e, "get_team_leaderboard"),
        },
        // ── Activity ──────────────────────────────────────────────────────────
        "get_activity_metrics" => match serde_json::from_value::<GetActivityMetricsInput>(params) {
            Ok(input) => match get_activity_metrics(input, pool).await {
                Ok(out) => ok_resp(out),
                Err(e) => err_resp(e.error_code(), &e.to_string()),
            },
            Err(e) => bad_params(e, "get_activity_metrics"),
        },
        unknown => {
            error!(tool = unknown, "Unknown analytics tool");
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
