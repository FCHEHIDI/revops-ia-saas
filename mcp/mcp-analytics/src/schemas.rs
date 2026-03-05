use chrono::NaiveDate;
use rust_decimal::Decimal;
use serde::{Deserialize, Serialize};
use uuid::Uuid;

// ---------------------------------------------------------------------------
// Pipeline
// ---------------------------------------------------------------------------

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct StageConversionRate {
    pub stage: String,
    pub deal_count: i64,
    pub total_value: Decimal,
    pub avg_time_in_stage_days: f32,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GetPipelineMetricsOutput {
    pub conversion_rates: Vec<StageConversionRate>,
    pub avg_cycle_days: f32,
    pub win_rate: f32,
    pub avg_deal_size: Decimal,
    pub deals_created: i64,
    pub deals_won: i64,
    pub deals_lost: i64,
    pub revenue_generated: Decimal,
    pub period_start: NaiveDate,
    pub period_end: NaiveDate,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct VelocityBreakdownRow {
    pub dimension: String,
    pub velocity_score: f64,
    pub deals_count: i64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GetDealVelocityOutput {
    pub velocity_score: f64,
    pub deals_won: i64,
    pub win_rate: f32,
    pub avg_deal_value: Decimal,
    pub avg_cycle_days: f32,
    pub trend: String,
    pub breakdown: Vec<VelocityBreakdownRow>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FunnelStage {
    pub stage: String,
    pub entered: i64,
    pub exited: i64,
    pub converted: i64,
    pub conversion_rate: f32,
    pub avg_time_days: f32,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GetFunnelAnalysisOutput {
    pub stages: Vec<FunnelStage>,
    pub overall_conversion: f32,
    pub bottleneck_stage: Option<String>,
}

// ---------------------------------------------------------------------------
// Revenue
// ---------------------------------------------------------------------------

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MonthlyForecast {
    pub month: NaiveDate,
    pub new_revenue: Decimal,
    pub recurring_revenue: Decimal,
    pub total: Decimal,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ForecastRevenueOutput {
    pub monthly_forecast: Vec<MonthlyForecast>,
    pub total_forecast: Decimal,
    pub model_used: String,
    pub assumptions: Vec<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MrrDataPoint {
    pub month: NaiveDate,
    pub mrr: Decimal,
    pub new_mrr: Decimal,
    pub churned_mrr: Decimal,
    pub net_new_mrr: Decimal,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GetMrrTrendOutput {
    pub data_points: Vec<MrrDataPoint>,
    pub current_mrr: Decimal,
    pub mom_growth_rate: f32,
}

// ---------------------------------------------------------------------------
// Churn
// ---------------------------------------------------------------------------

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ComputeChurnRateOutput {
    pub churn_rate: f32,
    pub churned_count: i64,
    pub starting_count: i64,
    pub net_revenue_retention: f32,
    pub gross_revenue_retention: f32,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AtRiskAccount {
    pub account_id: Uuid,
    pub account_name: String,
    pub risk_score: f32,
    pub risk_signals: Vec<String>,
    pub mrr_at_risk: Decimal,
    pub last_activity_days_ago: Option<i64>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GetAtRiskAccountsOutput {
    pub accounts: Vec<AtRiskAccount>,
    pub total: i64,
}

// ---------------------------------------------------------------------------
// Performance
// ---------------------------------------------------------------------------

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GetRepPerformanceOutput {
    pub rep_id: Uuid,
    pub deals_won: i64,
    pub revenue_generated: Decimal,
    pub quota_attainment: f32,
    pub avg_deal_size: Decimal,
    pub avg_cycle_days: f32,
    pub activities_logged: i64,
    pub pipeline_coverage: f32,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RepRanking {
    pub rank: u32,
    pub rep_id: Uuid,
    pub rep_name: String,
    pub metric_value: f64,
    pub deals_won: i64,
    pub revenue: Decimal,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GetTeamLeaderboardOutput {
    pub rankings: Vec<RepRanking>,
    pub period_start: NaiveDate,
    pub period_end: NaiveDate,
}

// ---------------------------------------------------------------------------
// Activity
// ---------------------------------------------------------------------------

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ActivityTypeStat {
    pub activity_type: String,
    pub count: i64,
    pub percentage: f32,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DailyActivityCount {
    pub date: NaiveDate,
    pub count: i64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GetActivityMetricsOutput {
    pub total_activities: i64,
    pub breakdown_by_type: Vec<ActivityTypeStat>,
    pub trend: Vec<DailyActivityCount>,
}
