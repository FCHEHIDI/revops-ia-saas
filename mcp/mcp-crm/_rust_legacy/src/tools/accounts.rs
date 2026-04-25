use chrono::Utc;
use rust_decimal::Decimal;
use serde::{Deserialize, Serialize};
use serde_json::json;
use sqlx::PgPool;
use tracing::{error, instrument};
use uuid::Uuid;

use crate::audit::{write_audit, AuditEntry};
use crate::db::validate_tenant;
use crate::errors::CrmError;
use crate::schemas::{Account, AccountSummary, PaginationInput};

// ---------------------------------------------------------------------------
// get_account
// ---------------------------------------------------------------------------

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GetAccountInput {
    pub tenant_id: Uuid,
    pub user_id: Option<Uuid>,
    pub account_id: Uuid,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GetAccountOutput {
    pub account: Account,
}

#[instrument(skip(pool), fields(tool = "get_account"))]
pub async fn get_account(
    input: GetAccountInput,
    pool: &PgPool,
) -> Result<GetAccountOutput, CrmError> {
    let start = std::time::Instant::now();
    validate_tenant(input.tenant_id, pool).await?;

    let account = sqlx::query_as!(
        Account,
        r#"
        SELECT
            id, tenant_id, name, domain, industry,
            employee_count, annual_revenue,
            custom_fields, created_at, updated_at
        FROM accounts
        WHERE id = $1 AND tenant_id = $2
        "#,
        input.account_id,
        input.tenant_id,
    )
    .fetch_optional(pool)
    .await
    .map_err(CrmError::DatabaseError)?
    .ok_or_else(|| CrmError::NotFound(format!("account {}", input.account_id)))?;

    let duration_ms = start.elapsed().as_millis() as i64;
    let audit_entry = AuditEntry::new(
        input.tenant_id,
        input.user_id,
        "get_account",
        &json!({ "account_id": input.account_id }),
        "OK",
        duration_ms,
    );
    if let Err(e) = write_audit(audit_entry, pool).await {
        error!("Audit write failed for get_account: {}", e);
    }

    Ok(GetAccountOutput { account })
}

// ---------------------------------------------------------------------------
// search_accounts
// ---------------------------------------------------------------------------

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SearchAccountsInput {
    pub tenant_id: Uuid,
    pub user_id: Option<Uuid>,
    pub query: Option<String>,
    pub industry: Option<String>,
    #[serde(flatten)]
    pub pagination: PaginationInput,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SearchAccountsOutput {
    pub accounts: Vec<AccountSummary>,
    pub total: i64,
    pub page: i64,
    pub page_size: i64,
}

#[instrument(skip(pool), fields(tool = "search_accounts"))]
pub async fn search_accounts(
    input: SearchAccountsInput,
    pool: &PgPool,
) -> Result<SearchAccountsOutput, CrmError> {
    let start = std::time::Instant::now();
    validate_tenant(input.tenant_id, pool).await?;

    let search_pattern = input
        .query
        .as_deref()
        .map(|q| format!("%{}%", q.to_lowercase()));

    let accounts = sqlx::query_as!(
        AccountSummary,
        r#"
        SELECT id, name, domain, industry
        FROM accounts
        WHERE tenant_id = $1
          AND ($2::text IS NULL OR (
              LOWER(name)   LIKE $2 OR
              LOWER(domain) LIKE $2
          ))
          AND ($3::text IS NULL OR LOWER(industry) = LOWER($3))
        ORDER BY name ASC
        LIMIT $4 OFFSET $5
        "#,
        input.tenant_id,
        search_pattern,
        input.industry,
        input.pagination.limit(),
        input.pagination.offset(),
    )
    .fetch_all(pool)
    .await
    .map_err(CrmError::DatabaseError)?;

    let total: i64 = sqlx::query_scalar!(
        r#"
        SELECT COUNT(*)
        FROM accounts
        WHERE tenant_id = $1
          AND ($2::text IS NULL OR (
              LOWER(name)   LIKE $2 OR
              LOWER(domain) LIKE $2
          ))
          AND ($3::text IS NULL OR LOWER(industry) = LOWER($3))
        "#,
        input.tenant_id,
        search_pattern,
        input.industry,
    )
    .fetch_one(pool)
    .await
    .map_err(CrmError::DatabaseError)?
    .unwrap_or(0);

    let duration_ms = start.elapsed().as_millis() as i64;
    let audit_entry = AuditEntry::new(
        input.tenant_id,
        input.user_id,
        "search_accounts",
        &json!({ "query": input.query, "industry": input.industry }),
        "OK",
        duration_ms,
    );
    if let Err(e) = write_audit(audit_entry, pool).await {
        error!("Audit write failed for search_accounts: {}", e);
    }

    Ok(SearchAccountsOutput {
        accounts,
        total,
        page: input.pagination.page,
        page_size: input.pagination.page_size,
    })
}

// ---------------------------------------------------------------------------
// create_account
// ---------------------------------------------------------------------------

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CreateAccountInput {
    pub tenant_id: Uuid,
    pub user_id: Option<Uuid>,
    pub name: String,
    pub domain: Option<String>,
    pub industry: Option<String>,
    pub employee_count: Option<i32>,
    pub annual_revenue: Option<Decimal>,
    pub custom_fields: Option<serde_json::Value>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CreateAccountOutput {
    pub account: Account,
}

#[instrument(skip(pool), fields(tool = "create_account"))]
pub async fn create_account(
    input: CreateAccountInput,
    pool: &PgPool,
) -> Result<CreateAccountOutput, CrmError> {
    let start = std::time::Instant::now();
    validate_tenant(input.tenant_id, pool).await?;

    if input.name.trim().is_empty() {
        return Err(CrmError::ValidationError(
            "account name cannot be empty".to_string(),
        ));
    }

    if let Some(ref domain) = input.domain {
        let existing: Option<Uuid> = sqlx::query_scalar!(
            "SELECT id FROM accounts WHERE tenant_id = $1 AND domain = $2",
            input.tenant_id,
            domain,
        )
        .fetch_optional(pool)
        .await
        .map_err(CrmError::DatabaseError)?;

        if existing.is_some() {
            return Err(CrmError::ConflictError(format!(
                "an account with domain '{}' already exists",
                domain
            )));
        }
    }

    let custom_fields = input
        .custom_fields
        .unwrap_or_else(|| serde_json::Value::Object(serde_json::Map::new()));
    let now = Utc::now();
    let id = Uuid::new_v4();

    let account = sqlx::query_as!(
        Account,
        r#"
        INSERT INTO accounts (
            id, tenant_id, name, domain, industry,
            employee_count, annual_revenue, custom_fields, created_at, updated_at
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
        RETURNING
            id, tenant_id, name, domain, industry,
            employee_count, annual_revenue, custom_fields, created_at, updated_at
        "#,
        id,
        input.tenant_id,
        input.name.trim(),
        input.domain,
        input.industry,
        input.employee_count,
        input.annual_revenue,
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
        "create_account",
        &json!({ "name": input.name, "domain": input.domain }),
        "CREATED",
        duration_ms,
    );
    if let Err(e) = write_audit(audit_entry, pool).await {
        error!("Audit write failed for create_account: {}", e);
    }

    Ok(CreateAccountOutput { account })
}

// ---------------------------------------------------------------------------
// update_account
// ---------------------------------------------------------------------------

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct UpdateAccountInput {
    pub tenant_id: Uuid,
    pub user_id: Option<Uuid>,
    pub account_id: Uuid,
    pub name: Option<String>,
    pub domain: Option<String>,
    pub industry: Option<String>,
    pub employee_count: Option<i32>,
    pub annual_revenue: Option<Decimal>,
    pub custom_fields: Option<serde_json::Value>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct UpdateAccountOutput {
    pub account: Account,
}

#[instrument(skip(pool), fields(tool = "update_account"))]
pub async fn update_account(
    input: UpdateAccountInput,
    pool: &PgPool,
) -> Result<UpdateAccountOutput, CrmError> {
    let start = std::time::Instant::now();
    validate_tenant(input.tenant_id, pool).await?;

    let account = sqlx::query_as!(
        Account,
        r#"
        UPDATE accounts
        SET
            name            = COALESCE($3, name),
            domain          = COALESCE($4, domain),
            industry        = COALESCE($5, industry),
            employee_count  = COALESCE($6, employee_count),
            annual_revenue  = COALESCE($7, annual_revenue),
            custom_fields   = COALESCE($8, custom_fields),
            updated_at      = NOW()
        WHERE id = $1 AND tenant_id = $2
        RETURNING
            id, tenant_id, name, domain, industry,
            employee_count, annual_revenue, custom_fields, created_at, updated_at
        "#,
        input.account_id,
        input.tenant_id,
        input.name.as_deref().map(str::trim),
        input.domain,
        input.industry,
        input.employee_count,
        input.annual_revenue,
        input.custom_fields,
    )
    .fetch_optional(pool)
    .await
    .map_err(CrmError::DatabaseError)?
    .ok_or_else(|| CrmError::NotFound(format!("account {}", input.account_id)))?;

    let duration_ms = start.elapsed().as_millis() as i64;
    let audit_entry = AuditEntry::new(
        input.tenant_id,
        input.user_id,
        "update_account",
        &json!({ "account_id": input.account_id }),
        "UPDATED",
        duration_ms,
    );
    if let Err(e) = write_audit(audit_entry, pool).await {
        error!("Audit write failed for update_account: {}", e);
    }

    Ok(UpdateAccountOutput { account })
}
