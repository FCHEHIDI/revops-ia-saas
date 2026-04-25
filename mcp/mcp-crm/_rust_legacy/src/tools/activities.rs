use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use serde_json::json;
use sqlx::PgPool;
use tracing::{error, instrument};
use uuid::Uuid;

use crate::audit::{write_audit, AuditEntry};
use crate::db::validate_tenant;
use crate::errors::CrmError;
use crate::schemas::{Activity, ActivityType, EntityType, PaginationInput};

// ---------------------------------------------------------------------------
// list_activities
// ---------------------------------------------------------------------------

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ListActivitiesInput {
    pub tenant_id: Uuid,
    pub user_id: Option<Uuid>,
    pub entity_type: EntityType,
    pub entity_id: Uuid,
    pub activity_type: Option<ActivityType>,
    #[serde(flatten)]
    pub pagination: PaginationInput,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ListActivitiesOutput {
    pub activities: Vec<Activity>,
    pub total: i64,
    pub page: i64,
    pub page_size: i64,
}

#[instrument(skip(pool), fields(tool = "list_activities"))]
pub async fn list_activities(
    input: ListActivitiesInput,
    pool: &PgPool,
) -> Result<ListActivitiesOutput, CrmError> {
    let start = std::time::Instant::now();
    validate_tenant(input.tenant_id, pool).await?;

    let activities = sqlx::query_as!(
        Activity,
        r#"
        SELECT
            id, tenant_id,
            entity_type     AS "entity_type: EntityType",
            entity_id,
            activity_type   AS "activity_type: ActivityType",
            subject, notes, duration_minutes,
            performed_by, occurred_at
        FROM activities
        WHERE tenant_id    = $1
          AND entity_type  = $2
          AND entity_id    = $3
          AND ($4::activity_type IS NULL OR activity_type = $4)
        ORDER BY occurred_at DESC
        LIMIT $5 OFFSET $6
        "#,
        input.tenant_id,
        input.entity_type as EntityType,
        input.entity_id,
        input.activity_type as Option<ActivityType>,
        input.pagination.limit(),
        input.pagination.offset(),
    )
    .fetch_all(pool)
    .await
    .map_err(CrmError::DatabaseError)?;

    let total: i64 = sqlx::query_scalar!(
        r#"
        SELECT COUNT(*)
        FROM activities
        WHERE tenant_id   = $1
          AND entity_type = $2
          AND entity_id   = $3
          AND ($4::activity_type IS NULL OR activity_type = $4)
        "#,
        input.tenant_id,
        input.entity_type as EntityType,
        input.entity_id,
        input.activity_type as Option<ActivityType>,
    )
    .fetch_one(pool)
    .await
    .map_err(CrmError::DatabaseError)?
    .unwrap_or(0);

    let duration_ms = start.elapsed().as_millis() as i64;
    let audit_entry = AuditEntry::new(
        input.tenant_id,
        input.user_id,
        "list_activities",
        &json!({
            "entity_type": input.entity_type,
            "entity_id": input.entity_id,
        }),
        "OK",
        duration_ms,
    );
    if let Err(e) = write_audit(audit_entry, pool).await {
        error!("Audit write failed for list_activities: {}", e);
    }

    Ok(ListActivitiesOutput {
        activities,
        total,
        page: input.pagination.page,
        page_size: input.pagination.page_size,
    })
}

// ---------------------------------------------------------------------------
// log_activity
// ---------------------------------------------------------------------------

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct LogActivityInput {
    pub tenant_id: Uuid,
    pub user_id: Option<Uuid>,
    pub entity_type: EntityType,
    pub entity_id: Uuid,
    pub activity_type: ActivityType,
    pub subject: String,
    pub notes: Option<String>,
    pub duration_minutes: Option<i32>,
    pub performed_by: Uuid,
    pub occurred_at: Option<DateTime<Utc>>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct LogActivityOutput {
    pub activity: Activity,
}

#[instrument(skip(pool), fields(tool = "log_activity"))]
pub async fn log_activity(
    input: LogActivityInput,
    pool: &PgPool,
) -> Result<LogActivityOutput, CrmError> {
    let start = std::time::Instant::now();
    validate_tenant(input.tenant_id, pool).await?;

    if input.subject.trim().is_empty() {
        return Err(CrmError::ValidationError(
            "activity subject cannot be empty".to_string(),
        ));
    }
    if let Some(dur) = input.duration_minutes {
        if dur < 0 {
            return Err(CrmError::ValidationError(
                "duration_minutes cannot be negative".to_string(),
            ));
        }
    }

    let entity_exists = match input.entity_type {
        EntityType::Contact => sqlx::query_scalar!(
            "SELECT EXISTS(SELECT 1 FROM contacts WHERE id = $1 AND tenant_id = $2)",
            input.entity_id,
            input.tenant_id,
        )
        .fetch_one(pool)
        .await
        .map_err(CrmError::DatabaseError)?
        .unwrap_or(false),

        EntityType::Deal => sqlx::query_scalar!(
            "SELECT EXISTS(SELECT 1 FROM deals WHERE id = $1 AND tenant_id = $2)",
            input.entity_id,
            input.tenant_id,
        )
        .fetch_one(pool)
        .await
        .map_err(CrmError::DatabaseError)?
        .unwrap_or(false),

        EntityType::Account => sqlx::query_scalar!(
            "SELECT EXISTS(SELECT 1 FROM accounts WHERE id = $1 AND tenant_id = $2)",
            input.entity_id,
            input.tenant_id,
        )
        .fetch_one(pool)
        .await
        .map_err(CrmError::DatabaseError)?
        .unwrap_or(false),
    };

    if !entity_exists {
        return Err(CrmError::NotFound(format!(
            "{:?} {}",
            input.entity_type, input.entity_id
        )));
    }

    let occurred_at = input.occurred_at.unwrap_or_else(Utc::now);
    let id = Uuid::new_v4();

    let activity = sqlx::query_as!(
        Activity,
        r#"
        INSERT INTO activities (
            id, tenant_id, entity_type, entity_id,
            activity_type, subject, notes, duration_minutes,
            performed_by, occurred_at
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
        RETURNING
            id, tenant_id,
            entity_type   AS "entity_type: EntityType",
            entity_id,
            activity_type AS "activity_type: ActivityType",
            subject, notes, duration_minutes,
            performed_by, occurred_at
        "#,
        id,
        input.tenant_id,
        input.entity_type as EntityType,
        input.entity_id,
        input.activity_type as ActivityType,
        input.subject.trim(),
        input.notes,
        input.duration_minutes,
        input.performed_by,
        occurred_at,
    )
    .fetch_one(pool)
    .await
    .map_err(CrmError::DatabaseError)?;

    let duration_ms = start.elapsed().as_millis() as i64;
    let audit_entry = AuditEntry::new(
        input.tenant_id,
        input.user_id,
        "log_activity",
        &json!({
            "entity_type": input.entity_type,
            "entity_id": input.entity_id,
            "activity_type": input.activity_type,
        }),
        "CREATED",
        duration_ms,
    );
    if let Err(e) = write_audit(audit_entry, pool).await {
        error!("Audit write failed for log_activity: {}", e);
    }

    Ok(LogActivityOutput { activity })
}
