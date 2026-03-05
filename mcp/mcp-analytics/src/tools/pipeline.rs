use chrono::NaiveDate;
use rust_decimal::Decimal;
use serde::{Deserialize, Serialize};
use serde_json::json;
use sqlx::PgPool;
use tracing::{error, instrument};
use uuid::Uuid;

use crate::audit::{write_audit, AuditEntry};
use crate::db::validate_tenant;
use crate::errors::AnalyticsError;
use crate::schemas::{
    FunnelStage, GetDealVelocityOutput, GetFunnelAnalysisOutput, GetPipelineMetricsOutput,
    StageConversionRate, VelocityBreakdownRow,
};

// ---------------------------------------------------------------------------
// get_pipeline_metrics
// ---------------------------------------------------------------------------

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GetPipelineMetricsInput {
    pub tenant_id: Uuid,
    pub user_id: Option<Uuid>,
    pub period_start: NaiveDate,
    pub period_end: NaiveDate,
    pub assigned_to: Option<Uuid>,
    pub include_closed: Option<bool>,
}

struct StageRow {
    stage: String,
    deal_count: i64,
    total_value: Decimal,
    avg_time_in_stage_days: f64,
}

struct PeriodSummaryRow {
    deals_created: i64,
    deals_won: i64,
    deals_lost: i64,
    revenue_generated: Decimal,
    avg_cycle_days: f64,
    avg_deal_size: Decimal,
}

#[instrument(skip(pool), fields(tool = "get_pipeline_metrics"))]
pub async fn get_pipeline_metrics(
    input: GetPipelineMetricsInput,
    pool: &PgPool,
) -> Result<GetPipelineMetricsOutput, AnalyticsError> {
    let start = std::time::Instant::now();
    validate_tenant(input.tenant_id, pool).await?;

    let stage_rows: Vec<StageRow> = sqlx::query_as!(
        StageRow,
        r#"
        SELECT
            stage::text                                                          AS "stage!: String",
            COUNT(*)                                                             AS "deal_count!: i64",
            COALESCE(SUM(value), 0)                                             AS "total_value!: Decimal",
            COALESCE(
                AVG(EXTRACT(EPOCH FROM (
                    COALESCE(closed_at, NOW()) - created_at
                )) / 86400.0),
                0
            )                                                                    AS "avg_time_in_stage_days!: f64"
        FROM deals
        WHERE tenant_id = $1
          AND created_at::date >= $2
          AND created_at::date <= $3
          AND ($4::uuid IS NULL OR assigned_to = $4)
        GROUP BY stage
        ORDER BY
            CASE stage::text
                WHEN 'prospecting'   THEN 1
                WHEN 'qualification' THEN 2
                WHEN 'proposal'      THEN 3
                WHEN 'negotiation'   THEN 4
                WHEN 'closed_won'    THEN 5
                WHEN 'closed_lost'   THEN 6
                ELSE 99
            END
        "#,
        input.tenant_id,
        input.period_start,
        input.period_end,
        input.assigned_to,
    )
    .fetch_all(pool)
    .await
    .map_err(AnalyticsError::DatabaseError)?;

    let summary: PeriodSummaryRow = sqlx::query_as!(
        PeriodSummaryRow,
        r#"
        SELECT
            COUNT(*)                                                                          AS "deals_created!: i64",
            COUNT(*) FILTER (WHERE stage = 'closed_won')                                     AS "deals_won!: i64",
            COUNT(*) FILTER (WHERE stage = 'closed_lost')                                    AS "deals_lost!: i64",
            COALESCE(SUM(value) FILTER (WHERE stage = 'closed_won'), 0)                      AS "revenue_generated!: Decimal",
            COALESCE(
                AVG(
                    EXTRACT(EPOCH FROM (closed_at - created_at)) / 86400.0
                ) FILTER (WHERE stage IN ('closed_won', 'closed_lost') AND closed_at IS NOT NULL),
                0
            )                                                                                 AS "avg_cycle_days!: f64",
            COALESCE(
                AVG(value) FILTER (WHERE stage = 'closed_won'),
                0
            )                                                                                 AS "avg_deal_size!: Decimal"
        FROM deals
        WHERE tenant_id = $1
          AND created_at::date >= $2
          AND created_at::date <= $3
          AND ($4::uuid IS NULL OR assigned_to = $4)
        "#,
        input.tenant_id,
        input.period_start,
        input.period_end,
        input.assigned_to,
    )
    .fetch_one(pool)
    .await
    .map_err(AnalyticsError::DatabaseError)?;

    let win_rate = if summary.deals_won + summary.deals_lost > 0 {
        summary.deals_won as f32 / (summary.deals_won + summary.deals_lost) as f32
    } else {
        0.0
    };

    let conversion_rates = stage_rows
        .into_iter()
        .map(|r| StageConversionRate {
            stage: r.stage,
            deal_count: r.deal_count,
            total_value: r.total_value,
            avg_time_in_stage_days: r.avg_time_in_stage_days as f32,
        })
        .collect();

    let duration_ms = start.elapsed().as_millis() as i64;
    let audit_entry = AuditEntry::new(
        input.tenant_id,
        input.user_id,
        "get_pipeline_metrics",
        &json!({
            "period_start": input.period_start,
            "period_end": input.period_end,
            "assigned_to": input.assigned_to,
        }),
        "OK",
        duration_ms,
    );
    if let Err(e) = write_audit(audit_entry, pool).await {
        error!("Audit write failed for get_pipeline_metrics: {}", e);
    }

    Ok(GetPipelineMetricsOutput {
        conversion_rates,
        avg_cycle_days: summary.avg_cycle_days as f32,
        win_rate,
        avg_deal_size: summary.avg_deal_size,
        deals_created: summary.deals_created,
        deals_won: summary.deals_won,
        deals_lost: summary.deals_lost,
        revenue_generated: summary.revenue_generated,
        period_start: input.period_start,
        period_end: input.period_end,
    })
}

// ---------------------------------------------------------------------------
// get_deal_velocity
// ---------------------------------------------------------------------------

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GetDealVelocityInput {
    pub tenant_id: Uuid,
    pub user_id: Option<Uuid>,
    pub period_start: NaiveDate,
    pub period_end: NaiveDate,
    pub breakdown_by: Option<String>,
}

struct VelocityRow {
    deals_won: i64,
    avg_deal_value: Decimal,
    avg_cycle_days: f64,
    deals_total: i64,
}

struct BreakdownRow {
    dimension: String,
    deals_won: i64,
    avg_deal_value: Decimal,
    avg_cycle_days: f64,
}

/// Computes trend by comparing current period velocity to previous period.
async fn compute_trend(
    tenant_id: Uuid,
    period_start: NaiveDate,
    period_end: NaiveDate,
    current_velocity: f64,
    pool: &PgPool,
) -> Result<String, AnalyticsError> {
    let period_len = (period_end - period_start).num_days();
    let prev_end = period_start.pred_opt().unwrap_or(period_start);
    let prev_start = prev_end - chrono::Duration::days(period_len);

    let prev: Option<VelocityRow> = sqlx::query_as!(
        VelocityRow,
        r#"
        SELECT
            COUNT(*) FILTER (WHERE stage = 'closed_won')                                  AS "deals_won!: i64",
            COALESCE(AVG(value) FILTER (WHERE stage = 'closed_won'), 0)                   AS "avg_deal_value!: Decimal",
            COALESCE(
                AVG(EXTRACT(EPOCH FROM (closed_at - created_at)) / 86400.0)
                FILTER (WHERE stage = 'closed_won' AND closed_at IS NOT NULL),
                1
            )                                                                             AS "avg_cycle_days!: f64",
            COUNT(*)                                                                       AS "deals_total!: i64"
        FROM deals
        WHERE tenant_id = $1
          AND created_at::date >= $2
          AND created_at::date <= $3
        "#,
        tenant_id,
        prev_start,
        prev_end,
    )
    .fetch_optional(pool)
    .await
    .map_err(AnalyticsError::DatabaseError)?;

    let prev_velocity = prev.map(|r| {
        let total = r.deals_won + r.deals_total;
        let win_rate = if total > 0 { r.deals_won as f64 / total as f64 } else { 0.0 };
        let cycle = if r.avg_cycle_days < 1.0 { 1.0 } else { r.avg_cycle_days };
        let avg_val: f64 = r.avg_deal_value.to_string().parse().unwrap_or(0.0);
        r.deals_won as f64 * win_rate * avg_val / cycle
    }).unwrap_or(0.0);

    let threshold = 0.05 * prev_velocity.abs().max(1.0);
    let trend = if current_velocity > prev_velocity + threshold {
        "increasing"
    } else if current_velocity < prev_velocity - threshold {
        "decreasing"
    } else {
        "stable"
    };

    Ok(trend.to_string())
}

#[instrument(skip(pool), fields(tool = "get_deal_velocity"))]
pub async fn get_deal_velocity(
    input: GetDealVelocityInput,
    pool: &PgPool,
) -> Result<GetDealVelocityOutput, AnalyticsError> {
    let start = std::time::Instant::now();
    validate_tenant(input.tenant_id, pool).await?;

    let breakdown_by = input.breakdown_by.as_deref().unwrap_or("stage");
    if !["stage", "rep", "segment"].contains(&breakdown_by) {
        return Err(AnalyticsError::ValidationError(
            "breakdown_by must be 'stage', 'rep', or 'segment'".to_string(),
        ));
    }

    let row = sqlx::query_as!(
        VelocityRow,
        r#"
        SELECT
            COUNT(*) FILTER (WHERE stage = 'closed_won')                                  AS "deals_won!: i64",
            COALESCE(AVG(value) FILTER (WHERE stage = 'closed_won'), 0)                   AS "avg_deal_value!: Decimal",
            COALESCE(
                AVG(EXTRACT(EPOCH FROM (closed_at - created_at)) / 86400.0)
                FILTER (WHERE stage = 'closed_won' AND closed_at IS NOT NULL),
                1
            )                                                                             AS "avg_cycle_days!: f64",
            COUNT(*)                                                                       AS "deals_total!: i64"
        FROM deals
        WHERE tenant_id = $1
          AND created_at::date >= $2
          AND created_at::date <= $3
        "#,
        input.tenant_id,
        input.period_start,
        input.period_end,
    )
    .fetch_one(pool)
    .await
    .map_err(AnalyticsError::DatabaseError)?;

    let win_rate = if row.deals_won + row.deals_total > 0 {
        row.deals_won as f32 / (row.deals_won + row.deals_total) as f32
    } else {
        0.0
    };

    let avg_cycle = if row.avg_cycle_days < 1.0 { 1.0 } else { row.avg_cycle_days };
    let avg_val: f64 = row.avg_deal_value.to_string().parse().unwrap_or(0.0);
    let velocity_score = row.deals_won as f64 * win_rate as f64 * avg_val / avg_cycle;

    let trend = compute_trend(
        input.tenant_id,
        input.period_start,
        input.period_end,
        velocity_score,
        pool,
    )
    .await?;

    let breakdown = match breakdown_by {
        "rep" => {
            let rows = sqlx::query_as!(
                BreakdownRow,
                r#"
                SELECT
                    COALESCE(u.name, assigned_to::text)                                   AS "dimension!: String",
                    COUNT(*) FILTER (WHERE d.stage = 'closed_won')                        AS "deals_won!: i64",
                    COALESCE(AVG(d.value) FILTER (WHERE d.stage = 'closed_won'), 0)       AS "avg_deal_value!: Decimal",
                    COALESCE(
                        AVG(EXTRACT(EPOCH FROM (d.closed_at - d.created_at)) / 86400.0)
                        FILTER (WHERE d.stage = 'closed_won' AND d.closed_at IS NOT NULL),
                        1
                    )                                                                     AS "avg_cycle_days!: f64"
                FROM deals d
                LEFT JOIN users u ON u.id = d.assigned_to AND u.tenant_id = d.tenant_id
                WHERE d.tenant_id = $1
                  AND d.created_at::date >= $2
                  AND d.created_at::date <= $3
                  AND d.assigned_to IS NOT NULL
                GROUP BY d.assigned_to, u.name
                ORDER BY COUNT(*) FILTER (WHERE d.stage = 'closed_won') DESC
                "#,
                input.tenant_id,
                input.period_start,
                input.period_end,
            )
            .fetch_all(pool)
            .await
            .map_err(AnalyticsError::DatabaseError)?;

            rows.into_iter()
                .map(|r| {
                    let total = r.deals_won;
                    let wr = if total > 0 { total as f64 / (total + 1) as f64 } else { 0.0 };
                    let cycle = if r.avg_cycle_days < 1.0 { 1.0 } else { r.avg_cycle_days };
                    let av: f64 = r.avg_deal_value.to_string().parse().unwrap_or(0.0);
                    VelocityBreakdownRow {
                        dimension: r.dimension,
                        velocity_score: r.deals_won as f64 * wr * av / cycle,
                        deals_count: r.deals_won,
                    }
                })
                .collect()
        }
        _ => {
            // breakdown by stage (default)
            let rows = sqlx::query_as!(
                BreakdownRow,
                r#"
                SELECT
                    stage::text                                                            AS "dimension!: String",
                    COUNT(*) FILTER (WHERE stage = 'closed_won')                          AS "deals_won!: i64",
                    COALESCE(AVG(value) FILTER (WHERE stage = 'closed_won'), 0)           AS "avg_deal_value!: Decimal",
                    COALESCE(
                        AVG(EXTRACT(EPOCH FROM (closed_at - created_at)) / 86400.0)
                        FILTER (WHERE stage = 'closed_won' AND closed_at IS NOT NULL),
                        1
                    )                                                                     AS "avg_cycle_days!: f64"
                FROM deals
                WHERE tenant_id = $1
                  AND created_at::date >= $2
                  AND created_at::date <= $3
                GROUP BY stage
                ORDER BY
                    CASE stage::text
                        WHEN 'prospecting'   THEN 1
                        WHEN 'qualification' THEN 2
                        WHEN 'proposal'      THEN 3
                        WHEN 'negotiation'   THEN 4
                        ELSE 5
                    END
                "#,
                input.tenant_id,
                input.period_start,
                input.period_end,
            )
            .fetch_all(pool)
            .await
            .map_err(AnalyticsError::DatabaseError)?;

            rows.into_iter()
                .map(|r| {
                    let wr = if r.deals_won > 0 { 1.0_f64 } else { 0.0 };
                    let cycle = if r.avg_cycle_days < 1.0 { 1.0 } else { r.avg_cycle_days };
                    let av: f64 = r.avg_deal_value.to_string().parse().unwrap_or(0.0);
                    VelocityBreakdownRow {
                        dimension: r.dimension,
                        velocity_score: r.deals_won as f64 * wr * av / cycle,
                        deals_count: r.deals_won,
                    }
                })
                .collect()
        }
    };

    let duration_ms = start.elapsed().as_millis() as i64;
    let audit_entry = AuditEntry::new(
        input.tenant_id,
        input.user_id,
        "get_deal_velocity",
        &json!({
            "period_start": input.period_start,
            "period_end": input.period_end,
            "breakdown_by": input.breakdown_by,
        }),
        "OK",
        duration_ms,
    );
    if let Err(e) = write_audit(audit_entry, pool).await {
        error!("Audit write failed for get_deal_velocity: {}", e);
    }

    Ok(GetDealVelocityOutput {
        velocity_score,
        deals_won: row.deals_won,
        win_rate,
        avg_deal_value: row.avg_deal_value,
        avg_cycle_days: row.avg_cycle_days as f32,
        trend,
        breakdown,
    })
}

// ---------------------------------------------------------------------------
// get_funnel_analysis
// ---------------------------------------------------------------------------

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GetFunnelAnalysisInput {
    pub tenant_id: Uuid,
    pub user_id: Option<Uuid>,
    pub period_start: NaiveDate,
    pub period_end: NaiveDate,
}

struct FunnelRow {
    stage: String,
    entered: i64,
    converted: i64,
    avg_time_days: f64,
}

const STAGE_ORDER: &[&str] = &[
    "prospecting",
    "qualification",
    "proposal",
    "negotiation",
    "closed_won",
];

#[instrument(skip(pool), fields(tool = "get_funnel_analysis"))]
pub async fn get_funnel_analysis(
    input: GetFunnelAnalysisInput,
    pool: &PgPool,
) -> Result<GetFunnelAnalysisOutput, AnalyticsError> {
    let start = std::time::Instant::now();
    validate_tenant(input.tenant_id, pool).await?;

    let rows = sqlx::query_as!(
        FunnelRow,
        r#"
        SELECT
            stage::text                                                           AS "stage!: String",
            COUNT(*)                                                              AS "entered!: i64",
            COUNT(*) FILTER (WHERE stage != 'closed_lost')                       AS "converted!: i64",
            COALESCE(
                AVG(EXTRACT(EPOCH FROM (
                    COALESCE(closed_at, NOW()) - created_at
                )) / 86400.0),
                0
            )                                                                     AS "avg_time_days!: f64"
        FROM deals
        WHERE tenant_id = $1
          AND created_at::date >= $2
          AND created_at::date <= $3
        GROUP BY stage
        "#,
        input.tenant_id,
        input.period_start,
        input.period_end,
    )
    .fetch_all(pool)
    .await
    .map_err(AnalyticsError::DatabaseError)?;

    let total_entered: i64 = rows.iter().map(|r| r.entered).sum();

    let mut stages: Vec<FunnelStage> = STAGE_ORDER
        .iter()
        .filter_map(|&stage_name| {
            rows.iter().find(|r| r.stage == stage_name).map(|r| {
                let exited = r.entered - r.converted;
                let conversion_rate = if r.entered > 0 {
                    r.converted as f32 / r.entered as f32
                } else {
                    0.0
                };
                FunnelStage {
                    stage: r.stage.clone(),
                    entered: r.entered,
                    exited,
                    converted: r.converted,
                    conversion_rate,
                    avg_time_days: r.avg_time_days as f32,
                }
            })
        })
        .collect();

    // Append closed_lost as final funnel stage for completeness
    if let Some(lost_row) = rows.iter().find(|r| r.stage == "closed_lost") {
        stages.push(FunnelStage {
            stage: "closed_lost".to_string(),
            entered: lost_row.entered,
            exited: lost_row.entered,
            converted: 0,
            conversion_rate: 0.0,
            avg_time_days: lost_row.avg_time_days as f32,
        });
    }

    let overall_conversion = if total_entered > 0 {
        let won = rows.iter().find(|r| r.stage == "closed_won").map(|r| r.entered).unwrap_or(0);
        won as f32 / total_entered as f32
    } else {
        0.0
    };

    let bottleneck_stage = stages
        .iter()
        .filter(|s| s.stage != "closed_won" && s.stage != "closed_lost")
        .min_by(|a, b| {
            a.conversion_rate
                .partial_cmp(&b.conversion_rate)
                .unwrap_or(std::cmp::Ordering::Equal)
        })
        .map(|s| s.stage.clone());

    let duration_ms = start.elapsed().as_millis() as i64;
    let audit_entry = AuditEntry::new(
        input.tenant_id,
        input.user_id,
        "get_funnel_analysis",
        &json!({
            "period_start": input.period_start,
            "period_end": input.period_end,
        }),
        "OK",
        duration_ms,
    );
    if let Err(e) = write_audit(audit_entry, pool).await {
        error!("Audit write failed for get_funnel_analysis: {}", e);
    }

    Ok(GetFunnelAnalysisOutput {
        stages,
        overall_conversion,
        bottleneck_stage,
    })
}
