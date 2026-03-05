use chrono::{NaiveDate, Utc};
use rust_decimal::Decimal;
use serde::{Deserialize, Serialize};
use serde_json::json;
use sqlx::PgPool;
use tracing::{error, instrument};
use uuid::Uuid;

use crate::audit::{write_audit, AuditEntry};
use crate::db::validate_tenant;
use crate::errors::CrmError;
use crate::schemas::{Deal, DealStage, DealSummary, PaginationInput};

// ---------------------------------------------------------------------------
// get_deal
// ---------------------------------------------------------------------------

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GetDealInput {
    pub tenant_id: Uuid,
    pub user_id: Option<Uuid>,
    pub deal_id: Uuid,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GetDealOutput {
    pub deal: Deal,
}

#[instrument(skip(pool), fields(tool = "get_deal"))]
pub async fn get_deal(input: GetDealInput, pool: &PgPool) -> Result<GetDealOutput, CrmError> {
    let start = std::time::Instant::now();
    validate_tenant(input.tenant_id, pool).await?;

    let deal = sqlx::query_as!(
        Deal,
        r#"
        SELECT
            id, tenant_id, name, account_id, value, currency,
            stage AS "stage: DealStage",
            probability, close_date, assigned_to,
            custom_fields, created_at, updated_at, closed_at
        FROM deals
        WHERE id = $1 AND tenant_id = $2
        "#,
        input.deal_id,
        input.tenant_id,
    )
    .fetch_optional(pool)
    .await
    .map_err(CrmError::DatabaseError)?
    .ok_or_else(|| CrmError::NotFound(format!("deal {}", input.deal_id)))?;

    let duration_ms = start.elapsed().as_millis() as i64;
    let audit_entry = AuditEntry::new(
        input.tenant_id,
        input.user_id,
        "get_deal",
        &json!({ "deal_id": input.deal_id }),
        "OK",
        duration_ms,
    );
    if let Err(e) = write_audit(audit_entry, pool).await {
        error!("Audit write failed for get_deal: {}", e);
    }

    Ok(GetDealOutput { deal })
}

// ---------------------------------------------------------------------------
// search_deals
// ---------------------------------------------------------------------------

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SearchDealsInput {
    pub tenant_id: Uuid,
    pub user_id: Option<Uuid>,
    pub query: Option<String>,
    pub stage: Option<DealStage>,
    pub account_id: Option<Uuid>,
    pub assigned_to: Option<Uuid>,
    #[serde(flatten)]
    pub pagination: PaginationInput,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SearchDealsOutput {
    pub deals: Vec<DealSummary>,
    pub total: i64,
    pub page: i64,
    pub page_size: i64,
}

#[instrument(skip(pool), fields(tool = "search_deals"))]
pub async fn search_deals(
    input: SearchDealsInput,
    pool: &PgPool,
) -> Result<SearchDealsOutput, CrmError> {
    let start = std::time::Instant::now();
    validate_tenant(input.tenant_id, pool).await?;

    let search_pattern = input
        .query
        .as_deref()
        .map(|q| format!("%{}%", q.to_lowercase()));

    let deals = sqlx::query_as!(
        DealSummary,
        r#"
        SELECT
            id, name, account_id, value, currency,
            stage AS "stage: DealStage",
            close_date, assigned_to
        FROM deals
        WHERE tenant_id = $1
          AND ($2::text IS NULL OR LOWER(name) LIKE $2)
          AND ($3::deal_stage IS NULL OR stage = $3)
          AND ($4::uuid IS NULL OR account_id = $4)
          AND ($5::uuid IS NULL OR assigned_to = $5)
        ORDER BY close_date ASC, value DESC
        LIMIT $6 OFFSET $7
        "#,
        input.tenant_id,
        search_pattern,
        input.stage as Option<DealStage>,
        input.account_id,
        input.assigned_to,
        input.pagination.limit(),
        input.pagination.offset(),
    )
    .fetch_all(pool)
    .await
    .map_err(CrmError::DatabaseError)?;

    let total: i64 = sqlx::query_scalar!(
        r#"
        SELECT COUNT(*)
        FROM deals
        WHERE tenant_id = $1
          AND ($2::text IS NULL OR LOWER(name) LIKE $2)
          AND ($3::deal_stage IS NULL OR stage = $3)
          AND ($4::uuid IS NULL OR account_id = $4)
          AND ($5::uuid IS NULL OR assigned_to = $5)
        "#,
        input.tenant_id,
        search_pattern,
        input.stage as Option<DealStage>,
        input.account_id,
        input.assigned_to,
    )
    .fetch_one(pool)
    .await
    .map_err(CrmError::DatabaseError)?
    .unwrap_or(0);

    let duration_ms = start.elapsed().as_millis() as i64;
    let audit_entry = AuditEntry::new(
        input.tenant_id,
        input.user_id,
        "search_deals",
        &json!({ "query": input.query, "stage": input.stage }),
        "OK",
        duration_ms,
    );
    if let Err(e) = write_audit(audit_entry, pool).await {
        error!("Audit write failed for search_deals: {}", e);
    }

    Ok(SearchDealsOutput {
        deals,
        total,
        page: input.pagination.page,
        page_size: input.pagination.page_size,
    })
}

// ---------------------------------------------------------------------------
// create_deal
// ---------------------------------------------------------------------------

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CreateDealInput {
    pub tenant_id: Uuid,
    pub user_id: Option<Uuid>,
    pub name: String,
    pub account_id: Uuid,
    pub value: Decimal,
    pub currency: String,
    pub stage: Option<DealStage>,
    pub probability: Option<f32>,
    pub close_date: NaiveDate,
    pub assigned_to: Option<Uuid>,
    pub custom_fields: Option<serde_json::Value>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CreateDealOutput {
    pub deal: Deal,
}

#[instrument(skip(pool), fields(tool = "create_deal"))]
pub async fn create_deal(
    input: CreateDealInput,
    pool: &PgPool,
) -> Result<CreateDealOutput, CrmError> {
    let start = std::time::Instant::now();
    validate_tenant(input.tenant_id, pool).await?;

    if input.name.trim().is_empty() {
        return Err(CrmError::ValidationError(
            "deal name cannot be empty".to_string(),
        ));
    }
    if input.currency.len() != 3 {
        return Err(CrmError::ValidationError(
            "currency must be a 3-letter ISO 4217 code".to_string(),
        ));
    }
    if input.value < Decimal::ZERO {
        return Err(CrmError::ValidationError(
            "deal value cannot be negative".to_string(),
        ));
    }

    let account_exists: bool = sqlx::query_scalar!(
        "SELECT EXISTS(SELECT 1 FROM accounts WHERE id = $1 AND tenant_id = $2)",
        input.account_id,
        input.tenant_id,
    )
    .fetch_one(pool)
    .await
    .map_err(CrmError::DatabaseError)?
    .unwrap_or(false);

    if !account_exists {
        return Err(CrmError::NotFound(format!(
            "account {}",
            input.account_id
        )));
    }

    let stage = input.stage.unwrap_or(DealStage::Prospecting);
    let probability = input.probability.unwrap_or(0.0).clamp(0.0, 1.0);
    let custom_fields = input
        .custom_fields
        .unwrap_or_else(|| serde_json::Value::Object(serde_json::Map::new()));
    let now = Utc::now();
    let id = Uuid::new_v4();

    let deal = sqlx::query_as!(
        Deal,
        r#"
        INSERT INTO deals (
            id, tenant_id, name, account_id, value, currency,
            stage, probability, close_date, assigned_to,
            custom_fields, created_at, updated_at, closed_at
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, NULL)
        RETURNING
            id, tenant_id, name, account_id, value, currency,
            stage AS "stage: DealStage",
            probability, close_date, assigned_to,
            custom_fields, created_at, updated_at, closed_at
        "#,
        id,
        input.tenant_id,
        input.name.trim(),
        input.account_id,
        input.value,
        input.currency.to_uppercase(),
        stage as DealStage,
        probability as f64,
        input.close_date,
        input.assigned_to,
        custom_fields,
        now,
        now,
    )
    .fetch_one(pool)
    .await
    .map_err(CrmError::DatabaseError)?;

    let duration_ms = start.elapsed().as_millis() as i64;
    let audit_entry = AuditEntry::new(
        input.tenant_id,
        input.user_id,
        "create_deal",
        &json!({ "name": input.name, "account_id": input.account_id, "value": input.value }),
        "CREATED",
        duration_ms,
    );
    if let Err(e) = write_audit(audit_entry, pool).await {
        error!("Audit write failed for create_deal: {}", e);
    }

    Ok(CreateDealOutput { deal })
}

// ---------------------------------------------------------------------------
// update_deal_stage
// ---------------------------------------------------------------------------

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct UpdateDealStageInput {
    pub tenant_id: Uuid,
    pub user_id: Option<Uuid>,
    pub deal_id: Uuid,
    pub new_stage: DealStage,
    pub reason: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct UpdateDealStageOutput {
    pub deal: Deal,
    pub previous_stage: DealStage,
    pub new_stage: DealStage,
}

#[instrument(skip(pool), fields(tool = "update_deal_stage"))]
pub async fn update_deal_stage(
    input: UpdateDealStageInput,
    pool: &PgPool,
) -> Result<UpdateDealStageOutput, CrmError> {
    let start = std::time::Instant::now();
    validate_tenant(input.tenant_id, pool).await?;

    let current = sqlx::query!(
        r#"
        SELECT stage AS "stage: DealStage"
        FROM deals
        WHERE id = $1 AND tenant_id = $2
        "#,
        input.deal_id,
        input.tenant_id,
    )
    .fetch_optional(pool)
    .await
    .map_err(CrmError::DatabaseError)?
    .ok_or_else(|| CrmError::NotFound(format!("deal {}", input.deal_id)))?;

    let previous_stage = current.stage;

    if !previous_stage.can_transition_to(&input.new_stage) {
        return Err(CrmError::InvalidTransition {
            from: previous_stage.as_str().to_string(),
            to: input.new_stage.as_str().to_string(),
        });
    }

    let closed_at = match &input.new_stage {
        DealStage::ClosedWon | DealStage::ClosedLost => Some(Utc::now()),
        _ => None,
    };

    let deal = sqlx::query_as!(
        Deal,
        r#"
        UPDATE deals
        SET
            stage      = $3,
            closed_at  = CASE WHEN $4::timestamptz IS NOT NULL THEN $4 ELSE closed_at END,
            updated_at = NOW()
        WHERE id = $1 AND tenant_id = $2
        RETURNING
            id, tenant_id, name, account_id, value, currency,
            stage AS "stage: DealStage",
            probability, close_date, assigned_to,
            custom_fields, created_at, updated_at, closed_at
        "#,
        input.deal_id,
        input.tenant_id,
        input.new_stage as DealStage,
        closed_at,
    )
    .fetch_one(pool)
    .await
    .map_err(CrmError::DatabaseError)?;

    let duration_ms = start.elapsed().as_millis() as i64;
    let audit_entry = AuditEntry::new(
        input.tenant_id,
        input.user_id,
        "update_deal_stage",
        &json!({
            "deal_id": input.deal_id,
            "previous_stage": previous_stage,
            "new_stage": input.new_stage,
            "reason": input.reason,
        }),
        "UPDATED",
        duration_ms,
    );
    if let Err(e) = write_audit(audit_entry, pool).await {
        error!("Audit write failed for update_deal_stage: {}", e);
    }

    let new_stage = deal.stage.clone();
    Ok(UpdateDealStageOutput {
        deal,
        previous_stage,
        new_stage,
    })
}

// ---------------------------------------------------------------------------
// delete_deal
// ---------------------------------------------------------------------------

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DeleteDealInput {
    pub tenant_id: Uuid,
    pub user_id: Option<Uuid>,
    /// Must have permission `crm:deals:delete`
    pub permission: String,
    pub deal_id: Uuid,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DeleteDealOutput {
    pub deleted: bool,
    pub deal_id: Uuid,
}

#[instrument(skip(pool), fields(tool = "delete_deal"))]
pub async fn delete_deal(
    input: DeleteDealInput,
    pool: &PgPool,
) -> Result<DeleteDealOutput, CrmError> {
    let start = std::time::Instant::now();
    validate_tenant(input.tenant_id, pool).await?;

    if input.permission != "crm:deals:delete" {
        return Err(CrmError::PermissionDenied(
            "crm:deals:delete".to_string(),
        ));
    }

    let rows_affected = sqlx::query!(
        "DELETE FROM deals WHERE id = $1 AND tenant_id = $2",
        input.deal_id,
        input.tenant_id,
    )
    .execute(pool)
    .await
    .map_err(CrmError::DatabaseError)?
    .rows_affected();

    if rows_affected == 0 {
        return Err(CrmError::NotFound(format!("deal {}", input.deal_id)));
    }

    let duration_ms = start.elapsed().as_millis() as i64;
    let audit_entry = AuditEntry::new(
        input.tenant_id,
        input.user_id,
        "delete_deal",
        &json!({ "deal_id": input.deal_id }),
        "DELETED",
        duration_ms,
    );
    if let Err(e) = write_audit(audit_entry, pool).await {
        error!("Audit write failed for delete_deal: {}", e);
    }

    Ok(DeleteDealOutput {
        deleted: true,
        deal_id: input.deal_id,
    })
}
