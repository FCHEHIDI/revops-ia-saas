use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use serde_json::json;
use sqlx::PgPool;
use tracing::{error, instrument};
use uuid::Uuid;

use crate::audit::{write_audit, AuditEntry};
use crate::db::validate_tenant;
use crate::errors::SequencesError;

// ---------------------------------------------------------------------------
// pause_sequence
// ---------------------------------------------------------------------------

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PauseSequenceInput {
    pub tenant_id: Uuid,
    pub user_id: Uuid,
    pub sequence_id: Uuid,
    pub reason: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PauseSequenceOutput {
    pub paused_at: DateTime<Utc>,
    pub active_enrollments_affected: i64,
}

#[instrument(skip(pool), fields(tool = "pause_sequence"))]
pub async fn pause_sequence(
    input: PauseSequenceInput,
    pool: &PgPool,
) -> Result<PauseSequenceOutput, SequencesError> {
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

    sqlx::query!(
        r#"
        UPDATE sequences
        SET status = 'paused', updated_at = NOW()
        WHERE id = $1 AND tenant_id = $2
        "#,
        input.sequence_id,
        input.tenant_id,
    )
    .execute(pool)
    .await
    .map_err(SequencesError::DatabaseError)?;

    let affected = sqlx::query!(
        r#"
        UPDATE enrollments
        SET status = 'paused'
        WHERE sequence_id = $1 AND tenant_id = $2 AND status = 'active'
        "#,
        input.sequence_id,
        input.tenant_id,
    )
    .execute(pool)
    .await
    .map_err(SequencesError::DatabaseError)?;

    let active_enrollments_affected = affected.rows_affected() as i64;
    let paused_at = Utc::now();

    let duration_ms = start.elapsed().as_millis() as i64;
    let audit_entry = AuditEntry::new(
        input.tenant_id,
        Some(input.user_id),
        "pause_sequence",
        &json!({
            "sequence_id": input.sequence_id,
            "reason": input.reason,
            "affected_enrollments": active_enrollments_affected
        }),
        "PAUSED",
        duration_ms,
    );
    if let Err(e) = write_audit(audit_entry, pool).await {
        error!("Audit write failed for pause_sequence: {}", e);
    }

    Ok(PauseSequenceOutput {
        paused_at,
        active_enrollments_affected,
    })
}

// ---------------------------------------------------------------------------
// resume_sequence
// ---------------------------------------------------------------------------

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ResumeSequenceInput {
    pub tenant_id: Uuid,
    pub user_id: Uuid,
    pub sequence_id: Uuid,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ResumeSequenceOutput {
    pub resumed_at: DateTime<Utc>,
    pub enrollments_reactivated: i64,
}

#[instrument(skip(pool), fields(tool = "resume_sequence"))]
pub async fn resume_sequence(
    input: ResumeSequenceInput,
    pool: &PgPool,
) -> Result<ResumeSequenceOutput, SequencesError> {
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

    sqlx::query!(
        r#"
        UPDATE sequences
        SET status = 'active', updated_at = NOW()
        WHERE id = $1 AND tenant_id = $2
        "#,
        input.sequence_id,
        input.tenant_id,
    )
    .execute(pool)
    .await
    .map_err(SequencesError::DatabaseError)?;

    let reactivated = sqlx::query!(
        r#"
        UPDATE enrollments
        SET status = 'active'
        WHERE sequence_id = $1 AND tenant_id = $2 AND status = 'paused'
        "#,
        input.sequence_id,
        input.tenant_id,
    )
    .execute(pool)
    .await
    .map_err(SequencesError::DatabaseError)?;

    let enrollments_reactivated = reactivated.rows_affected() as i64;
    let resumed_at = Utc::now();

    let duration_ms = start.elapsed().as_millis() as i64;
    let audit_entry = AuditEntry::new(
        input.tenant_id,
        Some(input.user_id),
        "resume_sequence",
        &json!({
            "sequence_id": input.sequence_id,
            "enrollments_reactivated": enrollments_reactivated
        }),
        "RESUMED",
        duration_ms,
    );
    if let Err(e) = write_audit(audit_entry, pool).await {
        error!("Audit write failed for resume_sequence: {}", e);
    }

    Ok(ResumeSequenceOutput {
        resumed_at,
        enrollments_reactivated,
    })
}
