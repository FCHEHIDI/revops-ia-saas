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
