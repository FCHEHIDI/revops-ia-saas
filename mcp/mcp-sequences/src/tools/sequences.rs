use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use serde_json::json;
use sqlx::PgPool;
use tracing::{error, instrument};
use uuid::Uuid;

use crate::audit::{write_audit, AuditEntry};
use crate::db::validate_tenant;
use crate::errors::SequencesError;
use crate::schemas::{
    ExitCondition, ExitConditionInput, Sequence, SequenceStatus, SequenceStep,
    SequenceStepInput, SequenceSummary, StepType,
};

// ---------------------------------------------------------------------------
// create_sequence
// ---------------------------------------------------------------------------

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CreateSequenceInput {
    pub tenant_id: Uuid,
    pub user_id: Uuid,
    pub name: String,
    pub description: Option<String>,
    pub steps: Vec<SequenceStepInput>,
    pub exit_conditions: Vec<ExitConditionInput>,
    pub tags: Vec<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CreateSequenceOutput {
    pub sequence_id: Uuid,
    pub steps_count: u32,
    pub created_at: DateTime<Utc>,
}

#[instrument(skip(pool), fields(tool = "create_sequence"))]
pub async fn create_sequence(
    input: CreateSequenceInput,
    pool: &PgPool,
) -> Result<CreateSequenceOutput, SequencesError> {
    let start = std::time::Instant::now();
    validate_tenant(input.tenant_id, pool).await?;

    if input.steps.is_empty() {
        return Err(SequencesError::ValidationError(
            "steps cannot be empty".to_string(),
        ));
    }
    for (i, step) in input.steps.iter().enumerate() {
        if step.delay_days < 0 {
            return Err(SequencesError::ValidationError(format!(
                "step[{i}].delay_days must be >= 0"
            )));
        }
        if !(0..=23).contains(&step.delay_hours) {
            return Err(SequencesError::ValidationError(format!(
                "step[{i}].delay_hours must be in [0, 23]"
            )));
        }
    }
    if input.name.trim().is_empty() {
        return Err(SequencesError::ValidationError(
            "name cannot be empty".to_string(),
        ));
    }

    let sequence_id = Uuid::new_v4();
    let now = Utc::now();
    let tags_arr: Vec<&str> = input.tags.iter().map(|s| s.as_str()).collect();

    sqlx::query!(
        r#"
        INSERT INTO sequences (
            id, tenant_id, name, description, status,
            exit_conditions, tags, created_by, created_at, updated_at
        )
        VALUES ($1, $2, $3, $4, 'draft', $5, $6, $7, $8, $9)
        "#,
        sequence_id,
        input.tenant_id,
        input.name.trim(),
        input.description.as_deref(),
        serde_json::to_value(&input.exit_conditions).unwrap_or_default(),
        &tags_arr as &[&str],
        input.user_id,
        now,
        now,
    )
    .execute(pool)
    .await
    .map_err(SequencesError::DatabaseError)?;

    for (idx, step) in input.steps.iter().enumerate() {
        let step_id = Uuid::new_v4();
        sqlx::query!(
            r#"
            INSERT INTO sequence_steps (
                id, sequence_id, tenant_id, position, step_type,
                delay_days, delay_hours, template_id, subject, body_template
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
            "#,
            step_id,
            sequence_id,
            input.tenant_id,
            (idx + 1) as i32,
            step.step_type.clone() as StepType,
            step.delay_days,
            step.delay_hours,
            step.template_id,
            step.subject.as_deref(),
            step.body_template.as_deref(),
        )
        .execute(pool)
        .await
        .map_err(SequencesError::DatabaseError)?;
    }

    let steps_count = input.steps.len() as u32;
    let duration_ms = start.elapsed().as_millis() as i64;
    let audit_entry = AuditEntry::new(
        input.tenant_id,
        Some(input.user_id),
        "create_sequence",
        &json!({ "name": input.name, "steps_count": steps_count }),
        "CREATED",
        duration_ms,
    );
    if let Err(e) = write_audit(audit_entry, pool).await {
        error!("Audit write failed for create_sequence: {}", e);
    }

    Ok(CreateSequenceOutput {
        sequence_id,
        steps_count,
        created_at: now,
    })
}

// ---------------------------------------------------------------------------
// update_sequence
// ---------------------------------------------------------------------------

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct UpdateSequenceInput {
    pub tenant_id: Uuid,
    pub user_id: Uuid,
    pub sequence_id: Uuid,
    pub name: Option<String>,
    pub description: Option<String>,
    pub tags: Option<Vec<String>>,
    #[serde(default)]
    pub force: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct UpdateSequenceOutput {
    pub updated_at: DateTime<Utc>,
    pub warning: Option<String>,
}

#[instrument(skip(pool), fields(tool = "update_sequence"))]
pub async fn update_sequence(
    input: UpdateSequenceInput,
    pool: &PgPool,
) -> Result<UpdateSequenceOutput, SequencesError> {
    let start = std::time::Instant::now();
    validate_tenant(input.tenant_id, pool).await?;

    let active_count: i64 = sqlx::query_scalar!(
        r#"
        SELECT COUNT(*) FROM enrollments
        WHERE sequence_id = $1 AND tenant_id = $2 AND status = 'active'
        "#,
        input.sequence_id,
        input.tenant_id,
    )
    .fetch_one(pool)
    .await
    .map_err(SequencesError::DatabaseError)?
    .unwrap_or(0);

    if active_count > 0 && !input.force {
        return Err(SequencesError::SequenceHasActiveEnrollments {
            count: active_count,
        });
    }

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

    let now = Utc::now();

    if let Some(ref name) = input.name {
        if name.trim().is_empty() {
            return Err(SequencesError::ValidationError(
                "name cannot be empty".to_string(),
            ));
        }
    }

    let tags_param: Option<Vec<String>> = input.tags.clone();

    sqlx::query!(
        r#"
        UPDATE sequences
        SET
            name        = COALESCE($3, name),
            description = COALESCE($4, description),
            tags        = COALESCE($5, tags),
            updated_at  = $6
        WHERE id = $1 AND tenant_id = $2
        "#,
        input.sequence_id,
        input.tenant_id,
        input.name.as_deref(),
        input.description.as_deref(),
        tags_param.as_deref(),
        now,
    )
    .execute(pool)
    .await
    .map_err(SequencesError::DatabaseError)?;

    let warning = if active_count > 0 {
        Some(format!(
            "Updated sequence with {} active enrollments (force=true)",
            active_count
        ))
    } else {
        None
    };

    let duration_ms = start.elapsed().as_millis() as i64;
    let audit_entry = AuditEntry::new(
        input.tenant_id,
        Some(input.user_id),
        "update_sequence",
        &json!({ "sequence_id": input.sequence_id, "force": input.force }),
        "UPDATED",
        duration_ms,
    );
    if let Err(e) = write_audit(audit_entry, pool).await {
        error!("Audit write failed for update_sequence: {}", e);
    }

    Ok(UpdateSequenceOutput {
        updated_at: now,
        warning,
    })
}

// ---------------------------------------------------------------------------
// delete_sequence
// ---------------------------------------------------------------------------

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DeleteSequenceInput {
    pub tenant_id: Uuid,
    pub user_id: Uuid,
    pub sequence_id: Uuid,
    #[serde(default)]
    pub force: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DeleteSequenceOutput {
    pub deleted_at: DateTime<Utc>,
    pub unenrolled_count: i64,
}

#[instrument(skip(pool), fields(tool = "delete_sequence"))]
pub async fn delete_sequence(
    input: DeleteSequenceInput,
    pool: &PgPool,
) -> Result<DeleteSequenceOutput, SequencesError> {
    let start = std::time::Instant::now();
    validate_tenant(input.tenant_id, pool).await?;

    let active_count: i64 = sqlx::query_scalar!(
        r#"
        SELECT COUNT(*) FROM enrollments
        WHERE sequence_id = $1 AND tenant_id = $2 AND status IN ('active', 'pending')
        "#,
        input.sequence_id,
        input.tenant_id,
    )
    .fetch_one(pool)
    .await
    .map_err(SequencesError::DatabaseError)?
    .unwrap_or(0);

    if active_count > 0 && !input.force {
        return Err(SequencesError::SequenceHasActiveEnrollments {
            count: active_count,
        });
    }

    let unenrolled_count = if input.force && active_count > 0 {
        let result = sqlx::query!(
            r#"
            UPDATE enrollments
            SET status = 'unenrolled', unenroll_reason = 'sequence_deleted', completed_at = NOW()
            WHERE sequence_id = $1 AND tenant_id = $2 AND status IN ('active', 'pending')
            "#,
            input.sequence_id,
            input.tenant_id,
        )
        .execute(pool)
        .await
        .map_err(SequencesError::DatabaseError)?;
        result.rows_affected() as i64
    } else {
        0
    };

    let rows = sqlx::query!(
        "DELETE FROM sequences WHERE id = $1 AND tenant_id = $2",
        input.sequence_id,
        input.tenant_id,
    )
    .execute(pool)
    .await
    .map_err(SequencesError::DatabaseError)?;

    if rows.rows_affected() == 0 {
        return Err(SequencesError::NotFound(format!(
            "sequence {}",
            input.sequence_id
        )));
    }

    let deleted_at = Utc::now();
    let duration_ms = start.elapsed().as_millis() as i64;
    let audit_entry = AuditEntry::new(
        input.tenant_id,
        Some(input.user_id),
        "delete_sequence",
        &json!({
            "sequence_id": input.sequence_id,
            "force": input.force,
            "unenrolled_count": unenrolled_count
        }),
        "DELETED",
        duration_ms,
    );
    if let Err(e) = write_audit(audit_entry, pool).await {
        error!("Audit write failed for delete_sequence: {}", e);
    }

    Ok(DeleteSequenceOutput {
        deleted_at,
        unenrolled_count,
    })
}

// ---------------------------------------------------------------------------
// get_sequence
// ---------------------------------------------------------------------------

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GetSequenceInput {
    pub tenant_id: Uuid,
    pub user_id: Option<Uuid>,
    pub sequence_id: Uuid,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GetSequenceOutput {
    pub sequence: Sequence,
}

#[instrument(skip(pool), fields(tool = "get_sequence"))]
pub async fn get_sequence(
    input: GetSequenceInput,
    pool: &PgPool,
) -> Result<GetSequenceOutput, SequencesError> {
    let start = std::time::Instant::now();
    validate_tenant(input.tenant_id, pool).await?;

    let row = sqlx::query!(
        r#"
        SELECT
            id, tenant_id, name, description,
            status AS "status: SequenceStatus",
            exit_conditions, tags, created_by, created_at, updated_at
        FROM sequences
        WHERE id = $1 AND tenant_id = $2
        "#,
        input.sequence_id,
        input.tenant_id,
    )
    .fetch_optional(pool)
    .await
    .map_err(SequencesError::DatabaseError)?
    .ok_or_else(|| SequencesError::NotFound(format!("sequence {}", input.sequence_id)))?;

    let steps = sqlx::query!(
        r#"
        SELECT
            id, sequence_id, position,
            step_type AS "step_type: StepType",
            delay_days, delay_hours, template_id, subject, body_template
        FROM sequence_steps
        WHERE sequence_id = $1 AND tenant_id = $2
        ORDER BY position ASC
        "#,
        input.sequence_id,
        input.tenant_id,
    )
    .fetch_all(pool)
    .await
    .map_err(SequencesError::DatabaseError)?;

    let sequence_steps: Vec<SequenceStep> = steps
        .into_iter()
        .map(|s| SequenceStep {
            id: s.id,
            sequence_id: s.sequence_id,
            position: s.position,
            step_type: s.step_type,
            delay_days: s.delay_days,
            delay_hours: s.delay_hours,
            template_id: s.template_id,
            subject: s.subject,
            body_template: s.body_template,
        })
        .collect();

    let exit_conditions: Vec<ExitCondition> =
        serde_json::from_value(row.exit_conditions).unwrap_or_default();

    let sequence = Sequence {
        id: row.id,
        tenant_id: row.tenant_id,
        name: row.name,
        description: row.description,
        status: row.status,
        steps: sequence_steps,
        exit_conditions,
        tags: row.tags,
        created_by: row.created_by,
        created_at: row.created_at,
        updated_at: row.updated_at,
    };

    let duration_ms = start.elapsed().as_millis() as i64;
    let audit_entry = AuditEntry::new(
        input.tenant_id,
        input.user_id,
        "get_sequence",
        &json!({ "sequence_id": input.sequence_id }),
        "OK",
        duration_ms,
    );
    if let Err(e) = write_audit(audit_entry, pool).await {
        error!("Audit write failed for get_sequence: {}", e);
    }

    Ok(GetSequenceOutput { sequence })
}

// ---------------------------------------------------------------------------
// list_sequences
// ---------------------------------------------------------------------------

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ListSequencesInput {
    pub tenant_id: Uuid,
    pub user_id: Option<Uuid>,
    pub status: Option<SequenceStatus>,
    pub tags: Option<Vec<String>>,
    pub limit: Option<u32>,
    pub offset: Option<u32>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ListSequencesOutput {
    pub sequences: Vec<SequenceSummary>,
    pub total: i64,
}

#[instrument(skip(pool), fields(tool = "list_sequences"))]
pub async fn list_sequences(
    input: ListSequencesInput,
    pool: &PgPool,
) -> Result<ListSequencesOutput, SequencesError> {
    let start = std::time::Instant::now();
    validate_tenant(input.tenant_id, pool).await?;

    let limit = input.limit.unwrap_or(50).min(200) as i64;
    let offset = input.offset.unwrap_or(0) as i64;
    let tags_filter = input.tags.as_deref().map(|t| t.to_vec());

    let sequences = sqlx::query!(
        r#"
        SELECT
            s.id,
            s.name,
            s.status AS "status: SequenceStatus",
            COUNT(DISTINCT ss.id) AS steps_count,
            COUNT(DISTINCT CASE WHEN e.status = 'active' THEN e.id END) AS active_enrollments,
            COUNT(DISTINCT e.id) AS total_enrolled,
            s.created_at
        FROM sequences s
        LEFT JOIN sequence_steps ss ON ss.sequence_id = s.id
        LEFT JOIN enrollments e ON e.sequence_id = s.id AND e.tenant_id = s.tenant_id
        WHERE s.tenant_id = $1
          AND ($2::text IS NULL OR s.status = $2::sequence_status)
          AND ($3::text[] IS NULL OR s.tags && $3::text[])
        GROUP BY s.id, s.name, s.status, s.created_at
        ORDER BY s.created_at DESC
        LIMIT $4 OFFSET $5
        "#,
        input.tenant_id,
        input.status.as_ref().map(|s| format!("{:?}", s).to_lowercase()),
        tags_filter.as_deref(),
        limit,
        offset,
    )
    .fetch_all(pool)
    .await
    .map_err(SequencesError::DatabaseError)?;

    let total: i64 = sqlx::query_scalar!(
        r#"
        SELECT COUNT(*) FROM sequences
        WHERE tenant_id = $1
          AND ($2::text IS NULL OR status = $2::sequence_status)
          AND ($3::text[] IS NULL OR tags && $3::text[])
        "#,
        input.tenant_id,
        input.status.as_ref().map(|s| format!("{:?}", s).to_lowercase()),
        tags_filter.as_deref(),
    )
    .fetch_one(pool)
    .await
    .map_err(SequencesError::DatabaseError)?
    .unwrap_or(0);

    let result: Vec<SequenceSummary> = sequences
        .into_iter()
        .map(|r| SequenceSummary {
            id: r.id,
            name: r.name,
            status: r.status,
            steps_count: r.steps_count.unwrap_or(0),
            active_enrollments: r.active_enrollments.unwrap_or(0),
            total_enrolled: r.total_enrolled.unwrap_or(0),
            created_at: r.created_at,
        })
        .collect();

    let duration_ms = start.elapsed().as_millis() as i64;
    let audit_entry = AuditEntry::new(
        input.tenant_id,
        input.user_id,
        "list_sequences",
        &json!({ "status": input.status, "tags": input.tags }),
        "OK",
        duration_ms,
    );
    if let Err(e) = write_audit(audit_entry, pool).await {
        error!("Audit write failed for list_sequences: {}", e);
    }

    Ok(ListSequencesOutput {
        sequences: result,
        total,
    })
}
