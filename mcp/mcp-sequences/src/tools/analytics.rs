use chrono::NaiveDate;
use serde::{Deserialize, Serialize};
use serde_json::json;
use sqlx::PgPool;
use tracing::{error, instrument};
use uuid::Uuid;

use crate::audit::{write_audit, AuditEntry};
use crate::db::validate_tenant;
use crate::errors::SequencesError;

// ---------------------------------------------------------------------------
// get_sequence_performance
// ---------------------------------------------------------------------------

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct StepMetrics {
    pub step_position: i32,
    pub step_type: String,
    pub sent: i64,
    pub opened: i64,
    pub clicked: i64,
    pub replied: i64,
    pub open_rate: f32,
    pub click_rate: f32,
    pub reply_rate: f32,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GetSequencePerformanceOutput {
    pub sequence_id: Uuid,
    pub total_enrolled: i64,
    pub total_completed: i64,
    pub total_unenrolled: i64,
    pub total_active: i64,
    pub open_rate: f32,
    pub click_rate: f32,
    pub reply_rate: f32,
    pub conversion_rate: f32,
    pub bounce_rate: f32,
    pub unsubscribe_rate: f32,
    pub step_metrics: Vec<StepMetrics>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GetSequencePerformanceInput {
    pub tenant_id: Uuid,
    pub user_id: Option<Uuid>,
    pub sequence_id: Uuid,
    pub period_start: Option<NaiveDate>,
    pub period_end: Option<NaiveDate>,
}

#[instrument(skip(pool), fields(tool = "get_sequence_performance"))]
pub async fn get_sequence_performance(
    input: GetSequencePerformanceInput,
    pool: &PgPool,
) -> Result<GetSequencePerformanceOutput, SequencesError> {
    let start = std::time::Instant::now();
    validate_tenant(input.tenant_id, pool).await?;

    let exists: bool = sqlx::query_scalar!(
        "SELECT EXISTS(SELECT 1 FROM sequences WHERE id = $1 AND tenant_id = $2)",
        input.sequence_id,
        input.tenant_id,
    )
    .fetch_one(pool)
    .await
    .map_err(SequencesError::DatabaseError)?
    .unwrap_or(false);

    if !exists {
        return Err(SequencesError::NotFound(format!(
            "sequence {}",
            input.sequence_id
        )));
    }

    // Enrollment aggregations
    let enrollment_stats = sqlx::query!(
        r#"
        SELECT
            COUNT(*) FILTER (WHERE TRUE) AS total_enrolled,
            COUNT(*) FILTER (WHERE status = 'completed') AS total_completed,
            COUNT(*) FILTER (WHERE status = 'unenrolled') AS total_unenrolled,
            COUNT(*) FILTER (WHERE status = 'active') AS total_active
        FROM enrollments
        WHERE sequence_id = $1 AND tenant_id = $2
          AND ($3::date IS NULL OR enrolled_at::date >= $3)
          AND ($4::date IS NULL OR enrolled_at::date <= $4)
        "#,
        input.sequence_id,
        input.tenant_id,
        input.period_start,
        input.period_end,
    )
    .fetch_one(pool)
    .await
    .map_err(SequencesError::DatabaseError)?;

    // Global email event rates
    let email_stats = sqlx::query!(
        r#"
        SELECT
            COUNT(*) FILTER (WHERE event_type = 'sent') AS sent,
            COUNT(*) FILTER (WHERE event_type = 'opened') AS opened,
            COUNT(*) FILTER (WHERE event_type = 'clicked') AS clicked,
            COUNT(*) FILTER (WHERE event_type = 'replied') AS replied,
            COUNT(*) FILTER (WHERE event_type = 'bounced') AS bounced,
            COUNT(*) FILTER (WHERE event_type = 'unsubscribed') AS unsubscribed,
            COUNT(*) FILTER (WHERE event_type = 'converted') AS converted
        FROM email_events ee
        JOIN enrollments e ON e.id = ee.enrollment_id
        WHERE e.sequence_id = $1 AND e.tenant_id = $2
          AND ($3::date IS NULL OR ee.occurred_at::date >= $3)
          AND ($4::date IS NULL OR ee.occurred_at::date <= $4)
        "#,
        input.sequence_id,
        input.tenant_id,
        input.period_start,
        input.period_end,
    )
    .fetch_one(pool)
    .await
    .map_err(SequencesError::DatabaseError)?;

    let sent = email_stats.sent.unwrap_or(0);
    let safe_sent = sent.max(1) as f32;

    let open_rate = (email_stats.opened.unwrap_or(0) as f32 / safe_sent) * 100.0;
    let click_rate = (email_stats.clicked.unwrap_or(0) as f32 / safe_sent) * 100.0;
    let reply_rate = (email_stats.replied.unwrap_or(0) as f32 / safe_sent) * 100.0;
    let conversion_rate = (email_stats.converted.unwrap_or(0) as f32 / safe_sent) * 100.0;
    let bounce_rate = (email_stats.bounced.unwrap_or(0) as f32 / safe_sent) * 100.0;
    let unsubscribe_rate = (email_stats.unsubscribed.unwrap_or(0) as f32 / safe_sent) * 100.0;

    // Per-step metrics
    let step_rows = sqlx::query!(
        r#"
        SELECT
            ss.position AS step_position,
            ss.step_type::text AS step_type,
            COUNT(*) FILTER (WHERE ee.event_type = 'sent') AS sent,
            COUNT(*) FILTER (WHERE ee.event_type = 'opened') AS opened,
            COUNT(*) FILTER (WHERE ee.event_type = 'clicked') AS clicked,
            COUNT(*) FILTER (WHERE ee.event_type = 'replied') AS replied
        FROM sequence_steps ss
        LEFT JOIN email_events ee ON ee.step_id = ss.id
            AND ($3::date IS NULL OR ee.occurred_at::date >= $3)
            AND ($4::date IS NULL OR ee.occurred_at::date <= $4)
        WHERE ss.sequence_id = $1 AND ss.tenant_id = $2
        GROUP BY ss.position, ss.step_type
        ORDER BY ss.position ASC
        "#,
        input.sequence_id,
        input.tenant_id,
        input.period_start,
        input.period_end,
    )
    .fetch_all(pool)
    .await
    .map_err(SequencesError::DatabaseError)?;

    let step_metrics: Vec<StepMetrics> = step_rows
        .into_iter()
        .map(|r| {
            let s_sent = r.sent.unwrap_or(0);
            let s_safe = s_sent.max(1) as f32;
            StepMetrics {
                step_position: r.step_position,
                step_type: r.step_type.unwrap_or_default(),
                sent: s_sent,
                opened: r.opened.unwrap_or(0),
                clicked: r.clicked.unwrap_or(0),
                replied: r.replied.unwrap_or(0),
                open_rate: (r.opened.unwrap_or(0) as f32 / s_safe) * 100.0,
                click_rate: (r.clicked.unwrap_or(0) as f32 / s_safe) * 100.0,
                reply_rate: (r.replied.unwrap_or(0) as f32 / s_safe) * 100.0,
            }
        })
        .collect();

    let duration_ms = start.elapsed().as_millis() as i64;
    let audit_entry = AuditEntry::new(
        input.tenant_id,
        input.user_id,
        "get_sequence_performance",
        &json!({
            "sequence_id": input.sequence_id,
            "period_start": input.period_start,
            "period_end": input.period_end
        }),
        "OK",
        duration_ms,
    );
    if let Err(e) = write_audit(audit_entry, pool).await {
        error!("Audit write failed for get_sequence_performance: {}", e);
    }

    Ok(GetSequencePerformanceOutput {
        sequence_id: input.sequence_id,
        total_enrolled: enrollment_stats.total_enrolled.unwrap_or(0),
        total_completed: enrollment_stats.total_completed.unwrap_or(0),
        total_unenrolled: enrollment_stats.total_unenrolled.unwrap_or(0),
        total_active: enrollment_stats.total_active.unwrap_or(0),
        open_rate,
        click_rate,
        reply_rate,
        conversion_rate,
        bounce_rate,
        unsubscribe_rate,
        step_metrics,
    })
}
