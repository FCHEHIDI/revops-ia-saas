use chrono::NaiveDate;
use serde::{Deserialize, Serialize};
use serde_json::json;
use sqlx::PgPool;
use tracing::{error, instrument};
use uuid::Uuid;

use crate::audit::{write_audit, AuditEntry};
use crate::db::validate_tenant;
use crate::errors::AnalyticsError;
use crate::schemas::{ActivityTypeStat, DailyActivityCount, GetActivityMetricsOutput};

// ---------------------------------------------------------------------------
// get_activity_metrics
// ---------------------------------------------------------------------------

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GetActivityMetricsInput {
    pub tenant_id: Uuid,
    pub user_id: Option<Uuid>,
    pub period_start: NaiveDate,
    pub period_end: NaiveDate,
    pub rep_id: Option<Uuid>,
    pub activity_type: Option<String>,
}

struct ActivityTypeRow {
    activity_type: String,
    count: i64,
}

struct DailyRow {
    date: NaiveDate,
    count: i64,
}

#[instrument(skip(pool), fields(tool = "get_activity_metrics"))]
pub async fn get_activity_metrics(
    input: GetActivityMetricsInput,
    pool: &PgPool,
) -> Result<GetActivityMetricsOutput, AnalyticsError> {
    let start = std::time::Instant::now();
    validate_tenant(input.tenant_id, pool).await?;

    let type_rows = sqlx::query_as!(
        ActivityTypeRow,
        r#"
        SELECT
            activity_type::text         AS "activity_type!: String",
            COUNT(*)                    AS "count!: i64"
        FROM activities
        WHERE tenant_id          = $1
          AND occurred_at::date >= $2
          AND occurred_at::date <= $3
          AND ($4::uuid IS NULL OR performed_by = $4)
          AND ($5::text IS NULL OR activity_type::text = $5)
        GROUP BY activity_type
        ORDER BY COUNT(*) DESC
        "#,
        input.tenant_id,
        input.period_start,
        input.period_end,
        input.rep_id,
        input.activity_type,
    )
    .fetch_all(pool)
    .await
    .map_err(AnalyticsError::DatabaseError)?;

    let total_activities: i64 = type_rows.iter().map(|r| r.count).sum();

    let breakdown_by_type: Vec<ActivityTypeStat> = type_rows
        .iter()
        .map(|r| {
            let percentage = if total_activities > 0 {
                r.count as f32 / total_activities as f32 * 100.0
            } else {
                0.0
            };
            ActivityTypeStat {
                activity_type: r.activity_type.clone(),
                count: r.count,
                percentage,
            }
        })
        .collect();

    let daily_rows = sqlx::query_as!(
        DailyRow,
        r#"
        SELECT
            occurred_at::date           AS "date!: NaiveDate",
            COUNT(*)                    AS "count!: i64"
        FROM activities
        WHERE tenant_id          = $1
          AND occurred_at::date >= $2
          AND occurred_at::date <= $3
          AND ($4::uuid IS NULL OR performed_by = $4)
          AND ($5::text IS NULL OR activity_type::text = $5)
        GROUP BY occurred_at::date
        ORDER BY occurred_at::date
        "#,
        input.tenant_id,
        input.period_start,
        input.period_end,
        input.rep_id,
        input.activity_type,
    )
    .fetch_all(pool)
    .await
    .map_err(AnalyticsError::DatabaseError)?;

    let trend: Vec<DailyActivityCount> = daily_rows
        .into_iter()
        .map(|r| DailyActivityCount { date: r.date, count: r.count })
        .collect();

    let duration_ms = start.elapsed().as_millis() as i64;
    let audit_entry = AuditEntry::new(
        input.tenant_id,
        input.user_id,
        "get_activity_metrics",
        &json!({
            "period_start": input.period_start,
            "period_end": input.period_end,
            "rep_id": input.rep_id,
            "activity_type": input.activity_type,
        }),
        "OK",
        duration_ms,
    );
    if let Err(e) = write_audit(audit_entry, pool).await {
        error!("Audit write failed for get_activity_metrics: {}", e);
    }

    Ok(GetActivityMetricsOutput {
        total_activities,
        breakdown_by_type,
        trend,
    })
}
