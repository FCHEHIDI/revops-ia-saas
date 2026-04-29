use rmcp::{
    model::{
        CallToolRequestParam, CallToolResult, Content, ListToolsResult, PaginatedRequestParam,
        ServerCapabilities, ServerInfo, Tool,
    },
    service::{RequestContext, RoleServer},
    Error as McpError,
    ServerHandler,
};
use serde_json::{json, Map, Value};

/// Convert a `serde_json::Value::Object` into `Arc<Map<String, Value>>` for Tool::input_schema.
fn s(v: Value) -> Arc<Map<String, Value>> {
    Arc::new(v.as_object().cloned().unwrap_or_default())
}
use sqlx::PgPool;
use std::borrow::Cow;
use std::sync::Arc;
use tracing::{error, info, instrument};

use crate::errors::AnalyticsError;
use crate::tools::{
    activity::{get_activity_metrics, GetActivityMetricsInput},
    churn::{compute_churn_rate, get_at_risk_accounts, ComputeChurnRateInput, GetAtRiskAccountsInput},
    performance::{get_rep_performance, get_team_leaderboard, GetRepPerformanceInput, GetTeamLeaderboardInput},
    pipeline::{get_deal_velocity, get_funnel_analysis, get_pipeline_metrics, GetDealVelocityInput, GetFunnelAnalysisInput, GetPipelineMetricsInput},
    revenue::{forecast_revenue, get_mrr_trend, ForecastRevenueInput, GetMrrTrendInput},
};

// ---------------------------------------------------------------------------
// AnalyticsServer
// ---------------------------------------------------------------------------

#[derive(Clone)]
pub struct AnalyticsServer {
    pool: Arc<PgPool>,
}

impl AnalyticsServer {
    pub fn new(pool: PgPool) -> Self {
        Self {
            pool: Arc::new(pool),
        }
    }

    fn analytics_error_to_mcp(err: AnalyticsError) -> McpError {
        McpError::internal_error(err.to_string(), Some(err.to_mcp_error_content()))
    }

    fn parse_input<T: serde::de::DeserializeOwned>(
        arguments: Option<Value>,
        tool_name: &str,
    ) -> Result<T, McpError> {
        let args = arguments.unwrap_or(Value::Object(serde_json::Map::new()));
        serde_json::from_value(args)
            .map_err(|e| McpError::invalid_params(format!("{tool_name}: {e}"), None))
    }

    fn ok_result(data: impl serde::Serialize) -> CallToolResult {
        CallToolResult {
            content: vec![Content::text(
                serde_json::to_string_pretty(&data).unwrap_or_else(|_| "{}".to_string()),
            )],
            is_error: Some(false),
        }
    }

    fn err_result(err: AnalyticsError) -> CallToolResult {
        CallToolResult {
            content: vec![Content::text(
                serde_json::to_string_pretty(&err.to_mcp_error_content())
                    .unwrap_or_else(|_| r#"{"error":"INTERNAL_ERROR"}"#.to_string()),
            )],
            is_error: Some(true),
        }
    }
}

// ---------------------------------------------------------------------------
// ServerHandler implementation
// ---------------------------------------------------------------------------

impl ServerHandler for AnalyticsServer {
    fn get_info(&self) -> ServerInfo {
        ServerInfo {
            capabilities: ServerCapabilities {
                tools: Some(rmcp::model::ToolsCapability { list_changed: None }),
                ..Default::default()
            },
            server_info: rmcp::model::Implementation {
                name: "mcp-analytics".to_string(),
                version: env!("CARGO_PKG_VERSION").to_string(),
            },
            ..Default::default()
        }
    }

    #[instrument(skip(self, _ctx), name = "list_tools")]
    async fn list_tools(
        &self,
        _request: PaginatedRequestParam,
        _ctx: RequestContext<RoleServer>,
    ) -> Result<ListToolsResult, McpError> {
        let tools = vec![
            // ----------------------------------------------------------------
            // Pipeline
            // ----------------------------------------------------------------
            Tool {
                name: Cow::Borrowed("get_pipeline_metrics"),
                description: Cow::Borrowed(
                    "Aggregated pipeline metrics over a date range: conversion rates per stage, win rate, avg cycle, revenue generated.",
                ),
                input_schema: s(json!({
                    "type": "object",
                    "required": ["tenant_id", "user_id", "period_start", "period_end"],
                    "properties": {
                        "tenant_id":      { "type": "string", "format": "uuid" },
                        "user_id":        { "type": "string", "format": "uuid" },
                        "period_start":   { "type": "string", "format": "date" },
                        "period_end":     { "type": "string", "format": "date" },
                        "assigned_to":    { "type": "string", "format": "uuid" },
                        "include_closed": { "type": "boolean" }
                    }
                })),
            },
            Tool {
                name: Cow::Borrowed("get_deal_velocity"),
                description: Cow::Borrowed(
                    "Deal velocity score for a period: deals_won × win_rate × avg_value / avg_cycle_days, with optional breakdown by stage, rep, or segment.",
                ),
                input_schema: s(json!({
                    "type": "object",
                    "required": ["tenant_id", "user_id", "period_start", "period_end"],
                    "properties": {
                        "tenant_id":     { "type": "string", "format": "uuid" },
                        "user_id":       { "type": "string", "format": "uuid" },
                        "period_start":  { "type": "string", "format": "date" },
                        "period_end":    { "type": "string", "format": "date" },
                        "breakdown_by":  { "type": "string", "enum": ["stage", "rep", "segment"] }
                    }
                })),
            },
            Tool {
                name: Cow::Borrowed("get_funnel_analysis"),
                description: Cow::Borrowed(
                    "Full funnel analysis across pipeline stages: entered, converted, conversion rate, avg time in stage, and bottleneck detection.",
                ),
                input_schema: s(json!({
                    "type": "object",
                    "required": ["tenant_id", "user_id", "period_start", "period_end"],
                    "properties": {
                        "tenant_id":    { "type": "string", "format": "uuid" },
                        "user_id":      { "type": "string", "format": "uuid" },
                        "period_start": { "type": "string", "format": "date" },
                        "period_end":   { "type": "string", "format": "date" }
                    }
                })),
            },
            // ----------------------------------------------------------------
            // Revenue
            // ----------------------------------------------------------------
            Tool {
                name: Cow::Borrowed("forecast_revenue"),
                description: Cow::Borrowed(
                    "Monthly revenue forecast for up to 12 months using weighted_pipeline, conservative (×0.7), or linear_trend model.",
                ),
                input_schema: s(json!({
                    "type": "object",
                    "required": ["tenant_id", "user_id", "forecast_months", "model", "include_existing_mrr"],
                    "properties": {
                        "tenant_id":           { "type": "string", "format": "uuid" },
                        "user_id":             { "type": "string", "format": "uuid" },
                        "forecast_months":     { "type": "integer", "minimum": 1, "maximum": 12 },
                        "model":               { "type": "string", "enum": ["weighted_pipeline", "linear_trend", "conservative"] },
                        "include_existing_mrr":{ "type": "boolean" },
                        "assigned_to":         { "type": "string", "format": "uuid" }
                    }
                })),
            },
            Tool {
                name: Cow::Borrowed("get_mrr_trend"),
                description: Cow::Borrowed(
                    "Monthly MRR trend for the past N months: MRR, new MRR, churned MRR, net new MRR, and month-over-month growth.",
                ),
                input_schema: s(json!({
                    "type": "object",
                    "required": ["tenant_id", "user_id"],
                    "properties": {
                        "tenant_id": { "type": "string", "format": "uuid" },
                        "user_id":   { "type": "string", "format": "uuid" },
                        "months":    { "type": "integer", "minimum": 1, "maximum": 24 }
                    }
                })),
            },
            // ----------------------------------------------------------------
            // Churn
            // ----------------------------------------------------------------
            Tool {
                name: Cow::Borrowed("compute_churn_rate"),
                description: Cow::Borrowed(
                    "Computes customer churn rate or revenue churn rate over a date range, including NRR and GRR.",
                ),
                input_schema: s(json!({
                    "type": "object",
                    "required": ["tenant_id", "user_id", "period_start", "period_end", "churn_type"],
                    "properties": {
                        "tenant_id":    { "type": "string", "format": "uuid" },
                        "user_id":      { "type": "string", "format": "uuid" },
                        "period_start": { "type": "string", "format": "date" },
                        "period_end":   { "type": "string", "format": "date" },
                        "churn_type":   { "type": "string", "enum": ["customer", "revenue"] }
                    }
                })),
            },
            Tool {
                name: Cow::Borrowed("get_at_risk_accounts"),
                description: Cow::Borrowed(
                    "Returns accounts at risk of churn using a composite score of inactivity, unpaid invoices and overdue invoices.",
                ),
                input_schema: s(json!({
                    "type": "object",
                    "required": ["tenant_id", "user_id"],
                    "properties": {
                        "tenant_id":      { "type": "string", "format": "uuid" },
                        "user_id":        { "type": "string", "format": "uuid" },
                        "risk_threshold": { "type": "number", "minimum": 0.0, "maximum": 1.0 },
                        "limit":          { "type": "integer", "minimum": 1, "maximum": 200 }
                    }
                })),
            },
            // ----------------------------------------------------------------
            // Performance
            // ----------------------------------------------------------------
            Tool {
                name: Cow::Borrowed("get_rep_performance"),
                description: Cow::Borrowed(
                    "Individual sales rep performance: deals won, revenue, quota attainment, avg deal size, cycle time, activities, pipeline coverage.",
                ),
                input_schema: s(json!({
                    "type": "object",
                    "required": ["tenant_id", "user_id", "rep_id", "period_start", "period_end"],
                    "properties": {
                        "tenant_id":    { "type": "string", "format": "uuid" },
                        "user_id":      { "type": "string", "format": "uuid" },
                        "rep_id":       { "type": "string", "format": "uuid" },
                        "period_start": { "type": "string", "format": "date" },
                        "period_end":   { "type": "string", "format": "date" }
                    }
                })),
            },
            Tool {
                name: Cow::Borrowed("get_team_leaderboard"),
                description: Cow::Borrowed(
                    "Team leaderboard ranked by revenue, deals_won, or activity count over a period.",
                ),
                input_schema: s(json!({
                    "type": "object",
                    "required": ["tenant_id", "user_id", "period_start", "period_end", "metric", "limit"],
                    "properties": {
                        "tenant_id":    { "type": "string", "format": "uuid" },
                        "user_id":      { "type": "string", "format": "uuid" },
                        "period_start": { "type": "string", "format": "date" },
                        "period_end":   { "type": "string", "format": "date" },
                        "metric":       { "type": "string", "enum": ["revenue", "deals_won", "activities"] },
                        "limit":        { "type": "integer", "minimum": 1, "maximum": 100 }
                    }
                })),
            },
            // ----------------------------------------------------------------
            // Activity
            // ----------------------------------------------------------------
            Tool {
                name: Cow::Borrowed("get_activity_metrics"),
                description: Cow::Borrowed(
                    "Activity metrics over a date range: total count, breakdown by type with percentages, daily trend.",
                ),
                input_schema: s(json!({
                    "type": "object",
                    "required": ["tenant_id", "user_id", "period_start", "period_end"],
                    "properties": {
                        "tenant_id":     { "type": "string", "format": "uuid" },
                        "user_id":       { "type": "string", "format": "uuid" },
                        "period_start":  { "type": "string", "format": "date" },
                        "period_end":    { "type": "string", "format": "date" },
                        "rep_id":        { "type": "string", "format": "uuid" },
                        "activity_type": { "type": "string", "enum": ["call", "email", "meeting", "note", "task"] }
                    }
                })),
            },
        ];

        Ok(ListToolsResult {
            tools,
            next_cursor: None,
        })
    }

    #[instrument(skip(self, _ctx), name = "call_tool", fields(tool = %request.name))]
    async fn call_tool(
        &self,
        request: CallToolRequestParam,
        _ctx: RequestContext<RoleServer>,
    ) -> Result<CallToolResult, McpError> {
        let name = request.name.as_ref();
        let args = request.arguments.map(Value::Object);
        let pool = self.pool.as_ref();

        info!("Dispatching tool: {}", name);

        match name {
            // ----------------------------------------------------------------
            // Pipeline
            // ----------------------------------------------------------------
            "get_pipeline_metrics" => {
                let input: GetPipelineMetricsInput = Self::parse_input(args, name)?;
                match get_pipeline_metrics(input, pool).await {
                    Ok(out) => Ok(Self::ok_result(out)),
                    Err(e) => Ok(Self::err_result(e)),
                }
            }
            "get_deal_velocity" => {
                let input: GetDealVelocityInput = Self::parse_input(args, name)?;
                match get_deal_velocity(input, pool).await {
                    Ok(out) => Ok(Self::ok_result(out)),
                    Err(e) => Ok(Self::err_result(e)),
                }
            }
            "get_funnel_analysis" => {
                let input: GetFunnelAnalysisInput = Self::parse_input(args, name)?;
                match get_funnel_analysis(input, pool).await {
                    Ok(out) => Ok(Self::ok_result(out)),
                    Err(e) => Ok(Self::err_result(e)),
                }
            }
            // ----------------------------------------------------------------
            // Revenue
            // ----------------------------------------------------------------
            "forecast_revenue" => {
                let input: ForecastRevenueInput = Self::parse_input(args, name)?;
                match forecast_revenue(input, pool).await {
                    Ok(out) => Ok(Self::ok_result(out)),
                    Err(e) => Ok(Self::err_result(e)),
                }
            }
            "get_mrr_trend" => {
                let input: GetMrrTrendInput = Self::parse_input(args, name)?;
                match get_mrr_trend(input, pool).await {
                    Ok(out) => Ok(Self::ok_result(out)),
                    Err(e) => Ok(Self::err_result(e)),
                }
            }
            // ----------------------------------------------------------------
            // Churn
            // ----------------------------------------------------------------
            "compute_churn_rate" => {
                let input: ComputeChurnRateInput = Self::parse_input(args, name)?;
                match compute_churn_rate(input, pool).await {
                    Ok(out) => Ok(Self::ok_result(out)),
                    Err(e) => Ok(Self::err_result(e)),
                }
            }
            "get_at_risk_accounts" => {
                let input: GetAtRiskAccountsInput = Self::parse_input(args, name)?;
                match get_at_risk_accounts(input, pool).await {
                    Ok(out) => Ok(Self::ok_result(out)),
                    Err(e) => Ok(Self::err_result(e)),
                }
            }
            // ----------------------------------------------------------------
            // Performance
            // ----------------------------------------------------------------
            "get_rep_performance" => {
                let input: GetRepPerformanceInput = Self::parse_input(args, name)?;
                match get_rep_performance(input, pool).await {
                    Ok(out) => Ok(Self::ok_result(out)),
                    Err(e) => Ok(Self::err_result(e)),
                }
            }
            "get_team_leaderboard" => {
                let input: GetTeamLeaderboardInput = Self::parse_input(args, name)?;
                match get_team_leaderboard(input, pool).await {
                    Ok(out) => Ok(Self::ok_result(out)),
                    Err(e) => Ok(Self::err_result(e)),
                }
            }
            // ----------------------------------------------------------------
            // Activity
            // ----------------------------------------------------------------
            "get_activity_metrics" => {
                let input: GetActivityMetricsInput = Self::parse_input(args, name)?;
                match get_activity_metrics(input, pool).await {
                    Ok(out) => Ok(Self::ok_result(out)),
                    Err(e) => Ok(Self::err_result(e)),
                }
            }
            unknown => {
                error!("Unknown tool requested: {}", unknown);
                Err(McpError::internal_error(format!("Unknown tool: {unknown}"), None))
            }
        }
    }
}
