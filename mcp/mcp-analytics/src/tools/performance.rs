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
use crate::schemas::{GetRepPerformanceOutput, GetTeamLeaderboardOutput, RepRanking};

// ---------------------------------------------------------------------------
// get_rep_performance
// ---------------------------------------------------------------------------

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GetRepPerformanceInput {
    pub tenant_id: Uuid,
    pub user_id: Option<Uuid>,
    pub rep_id: Uuid,
    pub period_start: NaiveDate,
    pub period_end: NaiveDate,
}

struct RepStatsRow {
    deals_won: i64,
    revenue_generated: Decimal,
    avg_deal_size: Decimal,
    avg_cycle_days: f64,
}

struct RepActivityRow {
    activities_logged: i64,
}

struct PipelineValueRow {
    open_pipeline: Decimal,
}

struct QuotaRow {
    quota_amount: Decimal,
}

/// Default quota used when no quota is defined for the rep in the given period.
const DEFAULT_QUOTA: f64 = 100_000.0;

#[instrument(skip(pool), fields(tool = "get_rep_performance"))]
pub async fn get_rep_performance(
    input: GetRepPerformanceInput,
    pool: &PgPool,
) -> Result<GetRepPerformanceOutput, AnalyticsError> {
    let start = std::time::Instant::now();
    validate_tenant(input.tenant_id, pool).await?;

    let stats = sqlx::query_as!(
        RepStatsRow,
        r#"
        SELECT
            COUNT(*) FILTER (WHERE stage = 'closed_won')                                   AS "deals_won!: i64",
            COALESCE(SUM(value) FILTER (WHERE stage = 'closed_won'), 0)                    AS "revenue_generated!: Decimal",
            COALESCE(AVG(value) FILTER (WHERE stage = 'closed_won'), 0)                    AS "avg_deal_size!: Decimal",
            COALESCE(
                AVG(EXTRACT(EPOCH FROM (closed_at - created_at)) / 86400.0)
                FILTER (WHERE stage = 'closed_won' AND closed_at IS NOT NULL),
                0
            )                                                                              AS "avg_cycle_days!: f64"
        FROM deals
        WHERE tenant_id    = $1
          AND assigned_to  = $2
          AND created_at::date >= $3
          AND created_at::date <= $4
        "#,
        input.tenant_id,
        input.rep_id,
        input.period_start,
        input.period_end,
    )
    .fetch_one(pool)
    .await
    .map_err(AnalyticsError::DatabaseError)?;

    let activity_row = sqlx::query_as!(
        RepActivityRow,
        r#"
        SELECT COUNT(*) AS "activities_logged!: i64"
        FROM activities
        WHERE tenant_id    = $1
          AND performed_by = $2
          AND occurred_at::date >= $3
          AND occurred_at::date <= $4
        "#,
        input.tenant_id,
        input.rep_id,
        input.period_start,
        input.period_end,
    )
    .fetch_one(pool)
    .await
    .map_err(AnalyticsError::DatabaseError)?;

    let open_pipeline = sqlx::query_as!(
        PipelineValueRow,
        r#"
        SELECT COALESCE(SUM(value), 0) AS "open_pipeline!: Decimal"
        FROM deals
        WHERE tenant_id   = $1
          AND assigned_to = $2
          AND stage NOT IN ('closed_won', 'closed_lost')
        "#,
        input.tenant_id,
        input.rep_id,
    )
    .fetch_one(pool)
    .await
    .map_err(AnalyticsError::DatabaseError)?;

    let quota: Decimal = sqlx::query_as!(
        QuotaRow,
        r#"
        SELECT COALESCE(SUM(amount), 0) AS "quota_amount!: Decimal"
        FROM quotas
        WHERE tenant_id  = $1
          AND user_id    = $2
          AND period_start <= $3
          AND period_end   >= $4
        "#,
        input.tenant_id,
        input.rep_id,
        input.period_end,
        input.period_start,
    )
    .fetch_optional(pool)
    .await
    .map_err(AnalyticsError::DatabaseError)?
    .map(|r| r.quota_amount)
    .unwrap_or_else(|| {
        Decimal::try_from(DEFAULT_QUOTA).unwrap_or(Decimal::ZERO)
    });

    use rust_decimal::prelude::ToPrimitive;

    let revenue_f64 = stats.revenue_generated.to_f64().unwrap_or(0.0);
    let quota_f64 = quota.to_f64().unwrap_or(DEFAULT_QUOTA);

    let quota_attainment = if quota_f64 > 0.0 {
        (revenue_f64 / quota_f64) as f32
    } else {
        0.0
    };

    let open_pipeline_f64 = open_pipeline.open_pipeline.to_f64().unwrap_or(0.0);
    let remaining_quota = (quota_f64 - revenue_f64).max(0.0);
    let pipeline_coverage = if remaining_quota > 0.0 {
        (open_pipeline_f64 / remaining_quota) as f32
    } else {
        f32::INFINITY
    };

    let duration_ms = start.elapsed().as_millis() as i64;
    let audit_entry = AuditEntry::new(
        input.tenant_id,
        input.user_id,
        "get_rep_performance",
        &json!({
            "rep_id": input.rep_id,
            "period_start": input.period_start,
            "period_end": input.period_end,
        }),
        "OK",
        duration_ms,
    );
    if let Err(e) = write_audit(audit_entry, pool).await {
        error!("Audit write failed for get_rep_performance: {}", e);
    }

    Ok(GetRepPerformanceOutput {
        rep_id: input.rep_id,
        deals_won: stats.deals_won,
        revenue_generated: stats.revenue_generated,
        quota_attainment,
        avg_deal_size: stats.avg_deal_size,
        avg_cycle_days: stats.avg_cycle_days as f32,
        activities_logged: activity_row.activities_logged,
        pipeline_coverage,
    })
}

// ---------------------------------------------------------------------------
// get_team_leaderboard
// ---------------------------------------------------------------------------

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GetTeamLeaderboardInput {
    pub tenant_id: Uuid,
    pub user_id: Option<Uuid>,
    pub period_start: NaiveDate,
    pub period_end: NaiveDate,
    pub metric: String,
    pub limit: u32,
}

struct LeaderboardRow {
    rep_id: Uuid,
    rep_name: String,
    deals_won: i64,
    revenue: Decimal,
    activities: i64,
}

#[instrument(skip(pool), fields(tool = "get_team_leaderboard"))]
pub async fn get_team_leaderboard(
    input: GetTeamLeaderboardInput,
    pool: &PgPool,
) -> Result<GetTeamLeaderboardOutput, AnalyticsError> {
    let start = std::time::Instant::now();
    validate_tenant(input.tenant_id, pool).await?;

    if !["revenue", "deals_won", "activities"].contains(&input.metric.as_str()) {
        return Err(AnalyticsError::ValidationError(
            "metric must be 'revenue', 'deals_won', or 'activities'".to_string(),
        ));
    }

    let limit = (input.limit.min(100)) as i64;

    let rows = sqlx::query_as!(
        LeaderboardRow,
        r#"
        SELECT
            u.id                                                                             AS "rep_id!: Uuid",
            COALESCE(u.name, u.id::text)                                                    AS "rep_name!: String",
            COUNT(d.id) FILTER (WHERE d.stage = 'closed_won')                               AS "deals_won!: i64",
            COALESCE(SUM(d.value) FILTER (WHERE d.stage = 'closed_won'), 0)                 AS "revenue!: Decimal",
            COUNT(a.id)                                                                      AS "activities!: i64"
        FROM users u
        LEFT JOIN deals d
            ON d.assigned_to   = u.id
           AND d.tenant_id     = u.tenant_id
           AND d.created_at::date >= $2
           AND d.created_at::date <= $3
        LEFT JOIN activities a
            ON a.performed_by   = u.id
           AND a.tenant_id      = u.tenant_id
           AND a.occurred_at::date >= $2
           AND a.occurred_at::date <= $3
        WHERE u.tenant_id = $1
        GROUP BY u.id, u.name
        ORDER BY
            CASE $4
                WHEN 'revenue'    THEN COALESCE(SUM(d.value) FILTER (WHERE d.stage = 'closed_won'), 0)::float8
                WHEN 'deals_won'  THEN COUNT(d.id) FILTER (WHERE d.stage = 'closed_won')::float8
                WHEN 'activities' THEN COUNT(a.id)::float8
                ELSE COALESCE(SUM(d.value) FILTER (WHERE d.stage = 'closed_won'), 0)::float8
            END DESC
        LIMIT $5
        "#,
        input.tenant_id,
        input.period_start,
        input.period_end,
        input.metric,
        limit,
    )
    .fetch_all(pool)
    .await
    .map_err(AnalyticsError::DatabaseError)?;

    use rust_decimal::prelude::ToPrimitive;

    let rankings: Vec<RepRanking> = rows
        .into_iter()
        .enumerate()
        .map(|(i, r)| {
            let metric_value = match input.metric.as_str() {
                "revenue" => r.revenue.to_f64().unwrap_or(0.0),
                "deals_won" => r.deals_won as f64,
                "activities" => r.activities as f64,
                _ => r.revenue.to_f64().unwrap_or(0.0),
            };
            RepRanking {
                rank: (i + 1) as u32,
                rep_id: r.rep_id,
                rep_name: r.rep_name,
                metric_value,
                deals_won: r.deals_won,
                revenue: r.revenue,
            }
        })
        .collect();

    let duration_ms = start.elapsed().as_millis() as i64;
    let audit_entry = AuditEntry::new(
        input.tenant_id,
        input.user_id,
        "get_team_leaderboard",
        &json!({
            "period_start": input.period_start,
            "period_end": input.period_end,
            "metric": input.metric,
            "limit": input.limit,
        }),
        "OK",
        duration_ms,
    );
    if let Err(e) = write_audit(audit_entry, pool).await {
        error!("Audit write failed for get_team_leaderboard: {}", e);
    }

    Ok(GetTeamLeaderboardOutput {
        rankings,
        period_start: input.period_start,
        period_end: input.period_end,
    })
}
