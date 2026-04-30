use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use serde_json::json;
use sqlx::PgPool;
use tracing::{error, instrument};
use uuid::Uuid;

use crate::audit::{write_audit, AuditEntry};
use crate::db::validate_tenant;
use crate::errors::SequencesError;
use crate::schemas::{EnrollmentStatus, EnrollmentSummary};

// ---------------------------------------------------------------------------
// enroll_contact
// ---------------------------------------------------------------------------

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct EnrollContactInput {
    pub tenant_id: Uuid,
    pub user_id: Uuid,
    pub sequence_id: Uuid,
    pub contact_id: Uuid,
    pub start_at: Option<DateTime<Utc>>,
    pub custom_variables: Option<serde_json::Value>,
    #[serde(default)]
    pub override_if_enrolled: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct EnrollContactOutput {
    pub enrollment_id: Uuid,
    pub starts_at: DateTime<Utc>,
    pub first_step_at: DateTime<Utc>,
}

#[instrument(skip(pool), fields(tool = "enroll_contact"))]
pub async fn enroll_contact(
    input: EnrollContactInput,
    pool: &PgPool,
) -> Result<EnrollContactOutput, SequencesError> {
    let start = std::time::Instant::now();
    validate_tenant(input.tenant_id, pool).await?;

    // 1. Verify sequence is active
    let seq_status: Option<String> = sqlx::query_scalar!(
        "SELECT status::text FROM sequences WHERE id = $1 AND tenant_id = $2",
        input.sequence_id,
        input.tenant_id,
    )
    .fetch_optional(pool)
    .await
    .map_err(SequencesError::DatabaseError)?
    .flatten();

    match seq_status.as_deref() {
        Some("active") => {}
        Some(_) => return Err(SequencesError::SequenceNotActive),
        None => {
            return Err(SequencesError::NotFound(format!(
                "sequence {}",
                input.sequence_id
            )))
        }
    }

    // 2. Verify contact exists (contacts table uses org_id as tenant identifier)
    let contact_exists: bool = sqlx::query_scalar!(
        "SELECT EXISTS(SELECT 1 FROM contacts WHERE id = $1 AND org_id = $2)",
        input.contact_id,
        input.tenant_id,
    )
    .fetch_one(pool)
    .await
    .map_err(SequencesError::DatabaseError)?
    .unwrap_or(false);

    if !contact_exists {
        return Err(SequencesError::ContactNotFound(input.contact_id));
    }

    // 3. Check existing active enrollment
    let existing_row = sqlx::query!(
        r#"
        SELECT id, status::text AS status
        FROM enrollments
        WHERE sequence_id = $1 AND contact_id = $2 AND tenant_id = $3
          AND status IN ('active', 'pending', 'paused')
        LIMIT 1
        "#,
        input.sequence_id,
        input.contact_id,
        input.tenant_id,
    )
    .fetch_optional(pool)
    .await
    .map_err(SequencesError::DatabaseError)?;

    if let Some(existing) = existing_row {
        if !input.override_if_enrolled {
            return Err(SequencesError::AlreadyEnrolled {
                enrollment_id: existing.id,
            });
        }
        // override: unenroll existing
        sqlx::query!(
            r#"
            UPDATE enrollments
            SET status = 'unenrolled', unenroll_reason = 'override_enrollment', completed_at = NOW()
            WHERE id = $1 AND tenant_id = $2
            "#,
            existing.id,
            input.tenant_id,
        )
        .execute(pool)
        .await
        .map_err(SequencesError::DatabaseError)?;
    }

    let now = Utc::now();
    let starts_at = input.start_at.unwrap_or(now);
    let enrollment_id = Uuid::new_v4();
    let custom_variables = input
        .custom_variables
        .unwrap_or_else(|| serde_json::Value::Object(serde_json::Map::new()));

    sqlx::query!(
        r#"
        INSERT INTO enrollments (
            id, tenant_id, sequence_id, contact_id, status,
            current_step, custom_variables, enrolled_at, next_step_at
        )
        VALUES ($1, $2, $3, $4, 'pending', 0, $5, $6, $7)
        "#,
        enrollment_id,
        input.tenant_id,
        input.sequence_id,
        input.contact_id,
        custom_variables,
        now,
        starts_at,
    )
    .execute(pool)
    .await
    .map_err(SequencesError::DatabaseError)?;

    let duration_ms = start.elapsed().as_millis() as i64;
    let audit_entry = AuditEntry::new(
        input.tenant_id,
        Some(input.user_id),
        "enroll_contact",
        &json!({
            "sequence_id": input.sequence_id,
            "contact_id": input.contact_id,
            "override": input.override_if_enrolled
        }),
        "ENROLLED",
        duration_ms,
    );
    if let Err(e) = write_audit(audit_entry, pool).await {
        error!("Audit write failed for enroll_contact: {}", e);
    }

    Ok(EnrollContactOutput {
        enrollment_id,
        starts_at,
        first_step_at: starts_at,
    })
}

// ---------------------------------------------------------------------------
// unenroll_contact
// ---------------------------------------------------------------------------

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct UnenrollContactInput {
    pub tenant_id: Uuid,
    pub user_id: Uuid,
    pub enrollment_id: Uuid,
    pub reason: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct UnenrollContactOutput {
    pub unenrolled_at: DateTime<Utc>,
    pub steps_completed: i32,
    pub steps_remaining: i32,
}

#[instrument(skip(pool), fields(tool = "unenroll_contact"))]
pub async fn unenroll_contact(
    input: UnenrollContactInput,
    pool: &PgPool,
) -> Result<UnenrollContactOutput, SequencesError> {
    let start = std::time::Instant::now();
    validate_tenant(input.tenant_id, pool).await?;

    let valid_reasons = ["replied", "converted", "manual", "bounced"];
    if !valid_reasons.contains(&input.reason.as_str()) {
        return Err(SequencesError::ValidationError(format!(
            "reason must be one of: {:?}",
            valid_reasons
        )));
    }

    let enrollment = sqlx::query!(
        r#"
        SELECT id, sequence_id, current_step
        FROM enrollments
        WHERE id = $1 AND tenant_id = $2
          AND status NOT IN ('unenrolled', 'completed')
        "#,
        input.enrollment_id,
        input.tenant_id,
    )
    .fetch_optional(pool)
    .await
    .map_err(SequencesError::DatabaseError)?
    .ok_or_else(|| SequencesError::NotFound(format!("enrollment {}", input.enrollment_id)))?;

    // Count total steps in this sequence
    let total_steps: i64 = sqlx::query_scalar!(
        "SELECT COUNT(*) FROM sequence_steps WHERE sequence_id = $1 AND tenant_id = $2",
        enrollment.sequence_id,
        input.tenant_id,
    )
    .fetch_one(pool)
    .await
    .map_err(SequencesError::DatabaseError)?
    .unwrap_or(0);

    let steps_completed = enrollment.current_step;
    let steps_remaining = (total_steps - steps_completed as i64).max(0) as i32;

    sqlx::query!(
        r#"
        UPDATE enrollments
        SET status = 'unenrolled', unenroll_reason = $3, completed_at = NOW()
        WHERE id = $1 AND tenant_id = $2
        "#,
        input.enrollment_id,
        input.tenant_id,
        input.reason,
    )
    .execute(pool)
    .await
    .map_err(SequencesError::DatabaseError)?;

    let unenrolled_at = Utc::now();
    let duration_ms = start.elapsed().as_millis() as i64;
    let audit_entry = AuditEntry::new(
        input.tenant_id,
        Some(input.user_id),
        "unenroll_contact",
        &json!({
            "enrollment_id": input.enrollment_id,
            "reason": input.reason,
            "steps_completed": steps_completed
        }),
        "UNENROLLED",
        duration_ms,
    );
    if let Err(e) = write_audit(audit_entry, pool).await {
        error!("Audit write failed for unenroll_contact: {}", e);
    }

    Ok(UnenrollContactOutput {
        unenrolled_at,
        steps_completed,
        steps_remaining,
    })
}

// ---------------------------------------------------------------------------
// list_enrollments
// ---------------------------------------------------------------------------

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ListEnrollmentsInput {
    pub tenant_id: Uuid,
    pub user_id: Option<Uuid>,
    pub sequence_id: Uuid,
    pub status: Option<EnrollmentStatus>,
    pub limit: Option<u32>,
    pub offset: Option<u32>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ListEnrollmentsOutput {
    pub enrollments: Vec<EnrollmentSummary>,
    pub total: i64,
}

#[instrument(skip(pool), fields(tool = "list_enrollments"))]
pub async fn list_enrollments(
    input: ListEnrollmentsInput,
    pool: &PgPool,
) -> Result<ListEnrollmentsOutput, SequencesError> {
    let start = std::time::Instant::now();
    validate_tenant(input.tenant_id, pool).await?;

    let limit = input.limit.unwrap_or(50).min(200) as i64;
    let offset = input.offset.unwrap_or(0) as i64;

    let enrollments = sqlx::query!(
        r#"
        SELECT
            id, contact_id,
            status AS "status: EnrollmentStatus",
            current_step, enrolled_at, next_step_at
        FROM enrollments
        WHERE sequence_id = $1 AND tenant_id = $2
          AND ($3::text IS NULL OR status = $3::enrollment_status)
        ORDER BY enrolled_at DESC
        LIMIT $4 OFFSET $5
        "#,
        input.sequence_id,
        input.tenant_id,
        input.status.as_ref().map(|s| format!("{:?}", s).to_lowercase()),
        limit,
        offset,
    )
    .fetch_all(pool)
    .await
    .map_err(SequencesError::DatabaseError)?;

    let total: i64 = sqlx::query_scalar!(
        r#"
        SELECT COUNT(*) FROM enrollments
        WHERE sequence_id = $1 AND tenant_id = $2
          AND ($3::text IS NULL OR status = $3::enrollment_status)
        "#,
        input.sequence_id,
        input.tenant_id,
        input.status.as_ref().map(|s| format!("{:?}", s).to_lowercase()),
    )
    .fetch_one(pool)
    .await
    .map_err(SequencesError::DatabaseError)?
    .unwrap_or(0);

    let result: Vec<EnrollmentSummary> = enrollments
        .into_iter()
        .map(|r| EnrollmentSummary {
            id: r.id,
            contact_id: r.contact_id,
            status: r.status,
            current_step: r.current_step,
            enrolled_at: r.enrolled_at,
            next_step_at: r.next_step_at,
        })
        .collect();

    let duration_ms = start.elapsed().as_millis() as i64;
    let audit_entry = AuditEntry::new(
        input.tenant_id,
        input.user_id,
        "list_enrollments",
        &json!({ "sequence_id": input.sequence_id, "status": input.status }),
        "OK",
        duration_ms,
    );
    if let Err(e) = write_audit(audit_entry, pool).await {
        error!("Audit write failed for list_enrollments: {}", e);
    }

    Ok(ListEnrollmentsOutput {
        enrollments: result,
        total,
    })
}
