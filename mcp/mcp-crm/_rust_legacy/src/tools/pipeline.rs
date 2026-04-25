use rust_decimal::Decimal;
use serde::{Deserialize, Serialize};
use serde_json::json;
use sqlx::PgPool;
use tracing::{error, instrument};
use uuid::Uuid;

use crate::audit::{write_audit, AuditEntry};
use crate::db::validate_tenant;
use crate::errors::CrmError;
use crate::schemas::{DealStage, PipelineStageStats};

// ---------------------------------------------------------------------------
// get_pipeline_summary
// ---------------------------------------------------------------------------

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GetPipelineSummaryInput {
    pub tenant_id: Uuid,
    pub user_id: Option<Uuid>,
    pub assigned_to: Option<Uuid>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GetPipelineSummaryOutput {
    pub stages: Vec<PipelineStageStats>,
    pub total_pipeline_value: Decimal,
    pub total_open_deals: i64,
    pub weighted_pipeline_value: Decimal,
}

/// Row returned by the pipeline aggregation query
struct PipelineRow {
    stage: DealStage,
    deal_count: i64,
    total_value: Decimal,
    avg_value: Decimal,
    avg_age_days: f64,
}

#[instrument(skip(pool), fields(tool = "get_pipeline_summary"))]
pub async fn get_pipeline_summary(
    input: GetPipelineSummaryInput,
    pool: &PgPool,
) -> Result<GetPipelineSummaryOutput, CrmError> {
    let start = std::time::Instant::now();
    validate_tenant(input.tenant_id, pool).await?;

    let rows = sqlx::query_as!(
        PipelineRow,
        r#"
        SELECT
            stage                               AS "stage: DealStage",
            COUNT(*)                            AS "deal_count!: i64",
            COALESCE(SUM(value), 0)             AS "total_value!: Decimal",
            COALESCE(AVG(value), 0)             AS "avg_value!: Decimal",
            COALESCE(
                AVG(EXTRACT(EPOCH FROM (NOW() - created_at)) / 86400.0),
                0
            )                                   AS "avg_age_days!: f64"
        FROM deals
        WHERE tenant_id = $1
          AND ($2::uuid IS NULL OR assigned_to = $2)
          AND stage NOT IN ('closed_won', 'closed_lost')
        GROUP BY stage
        ORDER BY
            CASE stage
                WHEN 'prospecting'   THEN 1
                WHEN 'qualification' THEN 2
                WHEN 'proposal'      THEN 3
                WHEN 'negotiation'   THEN 4
                ELSE 99
            END
        "#,
        input.tenant_id,
        input.assigned_to,
    )
    .fetch_all(pool)
    .await
    .map_err(CrmError::DatabaseError)?;

    let stages: Vec<PipelineStageStats> = rows
        .into_iter()
        .map(|r| PipelineStageStats {
            stage: r.stage,
            deal_count: r.deal_count,
            total_value: r.total_value,
            avg_value: r.avg_value,
            avg_age_days: r.avg_age_days as f32,
        })
        .collect();

    let total_pipeline_value: Decimal = stages.iter().map(|s| s.total_value).sum();
    let total_open_deals: i64 = stages.iter().map(|s| s.deal_count).sum();

    let weighted_pipeline_value: Decimal = sqlx::query_scalar!(
        r#"
        SELECT COALESCE(SUM(value * probability), 0) AS "weighted!: Decimal"
        FROM deals
        WHERE tenant_id = $1
          AND ($2::uuid IS NULL OR assigned_to = $2)
          AND stage NOT IN ('closed_won', 'closed_lost')
        "#,
        input.tenant_id,
        input.assigned_to,
    )
    .fetch_one(pool)
    .await
    .map_err(CrmError::DatabaseError)?;

    let duration_ms = start.elapsed().as_millis() as i64;
    let audit_entry = AuditEntry::new(
        input.tenant_id,
        input.user_id,
        "get_pipeline_summary",
        &json!({ "assigned_to": input.assigned_to }),
        "OK",
        duration_ms,
    );
    if let Err(e) = write_audit(audit_entry, pool).await {
        error!("Audit write failed for get_pipeline_summary: {}", e);
    }

    Ok(GetPipelineSummaryOutput {
        stages,
        total_pipeline_value,
        total_open_deals,
        weighted_pipeline_value,
    })
}
