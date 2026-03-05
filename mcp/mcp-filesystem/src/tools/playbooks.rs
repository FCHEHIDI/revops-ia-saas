use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use serde_json::json;
use sqlx::PgPool;
use tracing::{error, instrument};
use uuid::Uuid;

use crate::audit::{write_audit, AuditEntry};
use crate::db::validate_tenant;
use crate::errors::FilesystemError;
use crate::schemas::{Playbook, PlaybookCategory, PlaybookSummary};

// ---------------------------------------------------------------------------
// list_playbooks
// ---------------------------------------------------------------------------

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ListPlaybooksInput {
    pub tenant_id: Uuid,
    pub user_id: Option<Uuid>,
    pub category: Option<PlaybookCategory>,
    pub tags: Option<Vec<String>>,
    pub limit: Option<u32>,
    pub offset: Option<u32>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ListPlaybooksOutput {
    pub playbooks: Vec<PlaybookSummary>,
    pub total: i64,
}

struct PlaybookSummaryRow {
    id: Uuid,
    title: String,
    category: PlaybookCategory,
    description: Option<String>,
    tags: Vec<String>,
    version: String,
}

#[instrument(skip(pool), fields(tool = "list_playbooks"))]
pub async fn list_playbooks(
    input: ListPlaybooksInput,
    pool: &PgPool,
) -> Result<ListPlaybooksOutput, FilesystemError> {
    let start = std::time::Instant::now();
    validate_tenant(input.tenant_id, pool).await?;

    let limit = input.limit.unwrap_or(50).min(200) as i64;
    let offset = input.offset.unwrap_or(0) as i64;
    let tags_filter = input.tags.clone();

    let rows = sqlx::query_as!(
        PlaybookSummaryRow,
        r#"
        SELECT
            id,
            title,
            category AS "category: PlaybookCategory",
            description,
            tags,
            version
        FROM playbooks
        WHERE tenant_id = $1
          AND is_active = true
          AND ($2::playbook_category IS NULL OR category = $2)
          AND ($3::text[] IS NULL OR tags @> $3)
        ORDER BY title ASC
        LIMIT $4 OFFSET $5
        "#,
        input.tenant_id,
        input.category as Option<PlaybookCategory>,
        tags_filter.as_deref(),
        limit,
        offset,
    )
    .fetch_all(pool)
    .await
    .map_err(FilesystemError::DatabaseError)?;

    let total: i64 = sqlx::query_scalar!(
        r#"
        SELECT COUNT(*)
        FROM playbooks
        WHERE tenant_id = $1
          AND is_active = true
          AND ($2::playbook_category IS NULL OR category = $2)
          AND ($3::text[] IS NULL OR tags @> $3)
        "#,
        input.tenant_id,
        input.category as Option<PlaybookCategory>,
        tags_filter.as_deref(),
    )
    .fetch_one(pool)
    .await
    .map_err(FilesystemError::DatabaseError)?
    .unwrap_or(0);

    let playbooks = rows
        .into_iter()
        .map(|r| PlaybookSummary {
            id: r.id,
            title: r.title,
            category: r.category,
            description: r.description,
            tags: r.tags,
            version: r.version,
        })
        .collect();

    let duration_ms = start.elapsed().as_millis() as i64;
    let audit_entry = AuditEntry::new(
        input.tenant_id,
        input.user_id,
        "list_playbooks",
        &json!({ "category": input.category }),
        "OK",
        duration_ms,
    );
    if let Err(e) = write_audit(audit_entry, pool).await {
        error!("Audit write failed for list_playbooks: {}", e);
    }

    Ok(ListPlaybooksOutput { playbooks, total })
}

// ---------------------------------------------------------------------------
// get_playbook
// ---------------------------------------------------------------------------

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GetPlaybookInput {
    pub tenant_id: Uuid,
    pub user_id: Option<Uuid>,
    pub playbook_id: Uuid,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GetPlaybookOutput {
    pub playbook: Playbook,
}

struct PlaybookRow {
    id: Uuid,
    tenant_id: Uuid,
    title: String,
    description: Option<String>,
    category: PlaybookCategory,
    content: String,
    tags: Vec<String>,
    version: String,
    is_active: bool,
    created_by: Uuid,
    created_at: DateTime<Utc>,
    updated_at: DateTime<Utc>,
}

#[instrument(skip(pool), fields(tool = "get_playbook"))]
pub async fn get_playbook(
    input: GetPlaybookInput,
    pool: &PgPool,
) -> Result<GetPlaybookOutput, FilesystemError> {
    let start = std::time::Instant::now();
    validate_tenant(input.tenant_id, pool).await?;

    let row = sqlx::query_as!(
        PlaybookRow,
        r#"
        SELECT
            id,
            tenant_id,
            title,
            description,
            category AS "category: PlaybookCategory",
            content,
            tags,
            version,
            is_active,
            created_by,
            created_at,
            updated_at
        FROM playbooks
        WHERE id = $1 AND tenant_id = $2 AND is_active = true
        "#,
        input.playbook_id,
        input.tenant_id,
    )
    .fetch_optional(pool)
    .await
    .map_err(FilesystemError::DatabaseError)?
    .ok_or_else(|| FilesystemError::NotFound(format!("playbook:{}", input.playbook_id)))?;

    let duration_ms = start.elapsed().as_millis() as i64;
    let audit_entry = AuditEntry::new(
        input.tenant_id,
        input.user_id,
        "get_playbook",
        &json!({ "playbook_id": input.playbook_id }),
        "OK",
        duration_ms,
    );
    if let Err(e) = write_audit(audit_entry, pool).await {
        error!("Audit write failed for get_playbook: {}", e);
    }

    Ok(GetPlaybookOutput {
        playbook: Playbook {
            id: row.id,
            tenant_id: row.tenant_id,
            title: row.title,
            description: row.description,
            category: row.category,
            content: row.content,
            tags: row.tags,
            version: row.version,
            is_active: row.is_active,
            created_by: row.created_by,
            created_at: row.created_at,
            updated_at: row.updated_at,
        },
    })
}
