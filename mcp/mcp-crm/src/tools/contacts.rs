use chrono::Utc;
use serde::{Deserialize, Serialize};
use serde_json::json;
use sqlx::PgPool;
use tracing::{error, instrument};
use uuid::Uuid;

use crate::audit::{write_audit, AuditEntry};
use crate::db::validate_tenant;
use crate::errors::CrmError;
use crate::schemas::{Contact, ContactStatus, ContactSummary, PaginationInput};

// ---------------------------------------------------------------------------
// get_contact
// ---------------------------------------------------------------------------

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GetContactInput {
    pub tenant_id: Uuid,
    pub user_id: Option<Uuid>,
    pub contact_id: Uuid,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GetContactOutput {
    pub contact: Contact,
}

#[instrument(skip(pool), fields(tool = "get_contact"))]
pub async fn get_contact(
    input: GetContactInput,
    pool: &PgPool,
) -> Result<GetContactOutput, CrmError> {
    let start = std::time::Instant::now();
    validate_tenant(input.tenant_id, pool).await?;

    let contact = sqlx::query_as!(
        Contact,
        r#"
        SELECT
            id, tenant_id, first_name, last_name, email, phone, title,
            account_id, status AS "status: ContactStatus",
            custom_fields, created_at, updated_at
        FROM contacts
        WHERE id = $1 AND tenant_id = $2
        "#,
        input.contact_id,
        input.tenant_id,
    )
    .fetch_optional(pool)
    .await
    .map_err(CrmError::DatabaseError)?
    .ok_or_else(|| CrmError::NotFound(format!("contact {}", input.contact_id)))?;

    let duration_ms = start.elapsed().as_millis() as i64;
    let audit_entry = AuditEntry::new(
        input.tenant_id,
        input.user_id,
        "get_contact",
        &json!({ "contact_id": input.contact_id }),
        "OK",
        duration_ms,
    );
    if let Err(e) = write_audit(audit_entry, pool).await {
        error!("Audit write failed for get_contact: {}", e);
    }

    Ok(GetContactOutput { contact })
}

// ---------------------------------------------------------------------------
// search_contacts
// ---------------------------------------------------------------------------

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SearchContactsInput {
    pub tenant_id: Uuid,
    pub user_id: Option<Uuid>,
    pub query: Option<String>,
    pub status: Option<ContactStatus>,
    pub account_id: Option<Uuid>,
    #[serde(flatten)]
    pub pagination: PaginationInput,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SearchContactsOutput {
    pub contacts: Vec<ContactSummary>,
    pub total: i64,
    pub page: i64,
    pub page_size: i64,
}

#[instrument(skip(pool), fields(tool = "search_contacts"))]
pub async fn search_contacts(
    input: SearchContactsInput,
    pool: &PgPool,
) -> Result<SearchContactsOutput, CrmError> {
    let start = std::time::Instant::now();
    validate_tenant(input.tenant_id, pool).await?;

    let search_pattern = input
        .query
        .as_deref()
        .map(|q| format!("%{}%", q.to_lowercase()));

    let contacts = sqlx::query_as!(
        ContactSummary,
        r#"
        SELECT
            id, first_name, last_name, email,
            status AS "status: ContactStatus",
            account_id
        FROM contacts
        WHERE tenant_id = $1
          AND ($2::text IS NULL OR (
              LOWER(first_name) LIKE $2 OR
              LOWER(last_name)  LIKE $2 OR
              LOWER(email)      LIKE $2
          ))
          AND ($3::contact_status IS NULL OR status = $3)
          AND ($4::uuid IS NULL OR account_id = $4)
        ORDER BY last_name ASC, first_name ASC
        LIMIT $5 OFFSET $6
        "#,
        input.tenant_id,
        search_pattern,
        input.status as Option<ContactStatus>,
        input.account_id,
        input.pagination.limit(),
        input.pagination.offset(),
    )
    .fetch_all(pool)
    .await
    .map_err(CrmError::DatabaseError)?;

    let total: i64 = sqlx::query_scalar!(
        r#"
        SELECT COUNT(*)
        FROM contacts
        WHERE tenant_id = $1
          AND ($2::text IS NULL OR (
              LOWER(first_name) LIKE $2 OR
              LOWER(last_name)  LIKE $2 OR
              LOWER(email)      LIKE $2
          ))
          AND ($3::contact_status IS NULL OR status = $3)
          AND ($4::uuid IS NULL OR account_id = $4)
        "#,
        input.tenant_id,
        search_pattern,
        input.status as Option<ContactStatus>,
        input.account_id,
    )
    .fetch_one(pool)
    .await
    .map_err(CrmError::DatabaseError)?
    .unwrap_or(0);

    let duration_ms = start.elapsed().as_millis() as i64;
    let audit_entry = AuditEntry::new(
        input.tenant_id,
        input.user_id,
        "search_contacts",
        &json!({ "query": input.query, "status": input.status }),
        "OK",
        duration_ms,
    );
    if let Err(e) = write_audit(audit_entry, pool).await {
        error!("Audit write failed for search_contacts: {}", e);
    }

    Ok(SearchContactsOutput {
        contacts,
        total,
        page: input.pagination.page,
        page_size: input.pagination.page_size,
    })
}

// ---------------------------------------------------------------------------
// create_contact
// ---------------------------------------------------------------------------

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CreateContactInput {
    pub tenant_id: Uuid,
    pub user_id: Option<Uuid>,
    pub first_name: String,
    pub last_name: String,
    pub email: String,
    pub phone: Option<String>,
    pub title: Option<String>,
    pub account_id: Option<Uuid>,
    pub status: Option<ContactStatus>,
    pub custom_fields: Option<serde_json::Value>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CreateContactOutput {
    pub contact: Contact,
}

#[instrument(skip(pool), fields(tool = "create_contact"))]
pub async fn create_contact(
    input: CreateContactInput,
    pool: &PgPool,
) -> Result<CreateContactOutput, CrmError> {
    let start = std::time::Instant::now();
    validate_tenant(input.tenant_id, pool).await?;

    if input.email.is_empty() || !input.email.contains('@') {
        return Err(CrmError::ValidationError(
            "email must be a valid email address".to_string(),
        ));
    }
    if input.first_name.trim().is_empty() {
        return Err(CrmError::ValidationError(
            "first_name cannot be empty".to_string(),
        ));
    }
    if input.last_name.trim().is_empty() {
        return Err(CrmError::ValidationError(
            "last_name cannot be empty".to_string(),
        ));
    }

    let existing: Option<Uuid> = sqlx::query_scalar!(
        "SELECT id FROM contacts WHERE tenant_id = $1 AND email = $2",
        input.tenant_id,
        input.email,
    )
    .fetch_optional(pool)
    .await
    .map_err(CrmError::DatabaseError)?;

    if existing.is_some() {
        return Err(CrmError::ConflictError(format!(
            "a contact with email '{}' already exists",
            input.email
        )));
    }

    let status = input.status.unwrap_or(ContactStatus::Prospect);
    let custom_fields = input
        .custom_fields
        .unwrap_or_else(|| serde_json::Value::Object(serde_json::Map::new()));
    let now = Utc::now();
    let id = Uuid::new_v4();

    let contact = sqlx::query_as!(
        Contact,
        r#"
        INSERT INTO contacts (
            id, tenant_id, first_name, last_name, email, phone, title,
            account_id, status, custom_fields, created_at, updated_at
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
        RETURNING
            id, tenant_id, first_name, last_name, email, phone, title,
            account_id, status AS "status: ContactStatus",
            custom_fields, created_at, updated_at
        "#,
        id,
        input.tenant_id,
        input.first_name.trim(),
        input.last_name.trim(),
        input.email.trim().to_lowercase(),
        input.phone,
        input.title,
        input.account_id,
        status as ContactStatus,
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
        "create_contact",
        &json!({ "email": input.email, "first_name": input.first_name, "last_name": input.last_name }),
        "CREATED",
        duration_ms,
    );
    if let Err(e) = write_audit(audit_entry, pool).await {
        error!("Audit write failed for create_contact: {}", e);
    }

    Ok(CreateContactOutput { contact })
}

// ---------------------------------------------------------------------------
// update_contact
// ---------------------------------------------------------------------------

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct UpdateContactInput {
    pub tenant_id: Uuid,
    pub user_id: Option<Uuid>,
    pub contact_id: Uuid,
    pub first_name: Option<String>,
    pub last_name: Option<String>,
    pub email: Option<String>,
    pub phone: Option<String>,
    pub title: Option<String>,
    pub account_id: Option<Uuid>,
    pub status: Option<ContactStatus>,
    pub custom_fields: Option<serde_json::Value>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct UpdateContactOutput {
    pub contact: Contact,
}

#[instrument(skip(pool), fields(tool = "update_contact"))]
pub async fn update_contact(
    input: UpdateContactInput,
    pool: &PgPool,
) -> Result<UpdateContactOutput, CrmError> {
    let start = std::time::Instant::now();
    validate_tenant(input.tenant_id, pool).await?;

    if let Some(ref email) = input.email {
        if email.is_empty() || !email.contains('@') {
            return Err(CrmError::ValidationError(
                "email must be a valid email address".to_string(),
            ));
        }
    }

    let contact = sqlx::query_as!(
        Contact,
        r#"
        UPDATE contacts
        SET
            first_name    = COALESCE($3, first_name),
            last_name     = COALESCE($4, last_name),
            email         = COALESCE($5, email),
            phone         = COALESCE($6, phone),
            title         = COALESCE($7, title),
            account_id    = COALESCE($8, account_id),
            status        = COALESCE($9, status),
            custom_fields = COALESCE($10, custom_fields),
            updated_at    = NOW()
        WHERE id = $1 AND tenant_id = $2
        RETURNING
            id, tenant_id, first_name, last_name, email, phone, title,
            account_id, status AS "status: ContactStatus",
            custom_fields, created_at, updated_at
        "#,
        input.contact_id,
        input.tenant_id,
        input.first_name.as_deref().map(str::trim),
        input.last_name.as_deref().map(str::trim),
        input.email.as_deref().map(|e| e.trim().to_lowercase()),
        input.phone,
        input.title,
        input.account_id,
        input.status as Option<ContactStatus>,
        input.custom_fields,
    )
    .fetch_optional(pool)
    .await
    .map_err(CrmError::DatabaseError)?
    .ok_or_else(|| CrmError::NotFound(format!("contact {}", input.contact_id)))?;

    let duration_ms = start.elapsed().as_millis() as i64;
    let audit_entry = AuditEntry::new(
        input.tenant_id,
        input.user_id,
        "update_contact",
        &json!({ "contact_id": input.contact_id }),
        "UPDATED",
        duration_ms,
    );
    if let Err(e) = write_audit(audit_entry, pool).await {
        error!("Audit write failed for update_contact: {}", e);
    }

    Ok(UpdateContactOutput { contact })
}
