use chrono::{NaiveDate, Utc};
use rust_decimal::Decimal;
use serde::{Deserialize, Serialize};
use serde_json::json;
use sqlx::PgPool;
use tracing::{error, instrument};
use uuid::Uuid;

use crate::audit::{write_audit, AuditEntry};
use crate::db::validate_tenant;
use crate::errors::BillingError;
use crate::schemas::{Invoice, InvoiceLineItem, InvoiceStatus, InvoiceSummary, OverdueInvoice};

// ---------------------------------------------------------------------------
// get_invoice
// ---------------------------------------------------------------------------

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GetInvoiceInput {
    pub tenant_id: Uuid,
    pub user_id: Option<Uuid>,
    pub invoice_id: Uuid,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GetInvoiceOutput {
    pub invoice: Invoice,
}

struct InvoiceRow {
    id: Uuid,
    tenant_id: Uuid,
    subscription_id: Uuid,
    invoice_number: String,
    status: InvoiceStatus,
    amount: Decimal,
    currency: String,
    due_date: NaiveDate,
    paid_at: Option<chrono::DateTime<Utc>>,
    created_at: chrono::DateTime<Utc>,
}

struct LineItemRow {
    description: String,
    quantity: i32,
    unit_price: Decimal,
    amount: Decimal,
}

#[instrument(skip(pool), fields(tool = "get_invoice"))]
pub async fn get_invoice(input: GetInvoiceInput, pool: &PgPool) -> Result<GetInvoiceOutput, BillingError> {
    let start = std::time::Instant::now();
    validate_tenant(input.tenant_id, pool).await?;

    let row = sqlx::query_as!(
        InvoiceRow,
        r#"
        SELECT
            id, tenant_id, subscription_id, invoice_number,
            status AS "status: InvoiceStatus",
            amount, currency, due_date, paid_at, created_at
        FROM invoices
        WHERE id = $1 AND tenant_id = $2
        "#,
        input.invoice_id,
        input.tenant_id,
    )
    .fetch_optional(pool)
    .await
    .map_err(BillingError::DatabaseError)?
    .ok_or_else(|| BillingError::NotFound(format!("invoice {}", input.invoice_id)))?;

    let line_items = fetch_line_items(row.id, pool).await?;

    let invoice = Invoice {
        id: row.id,
        tenant_id: row.tenant_id,
        subscription_id: row.subscription_id,
        invoice_number: row.invoice_number,
        status: row.status,
        amount: row.amount,
        currency: row.currency,
        due_date: row.due_date,
        paid_at: row.paid_at,
        line_items,
        created_at: row.created_at,
    };

    let duration_ms = start.elapsed().as_millis() as i64;
    let audit_entry = AuditEntry::new(
        input.tenant_id,
        input.user_id,
        "get_invoice",
        &json!({ "invoice_id": input.invoice_id }),
        "OK",
        duration_ms,
    );
    if let Err(e) = write_audit(audit_entry, pool).await {
        error!("Audit write failed for get_invoice: {}", e);
    }

    Ok(GetInvoiceOutput { invoice })
}

async fn fetch_line_items(invoice_id: Uuid, pool: &PgPool) -> Result<Vec<InvoiceLineItem>, BillingError> {
    let rows = sqlx::query_as!(
        LineItemRow,
        r#"
        SELECT description, quantity, unit_price, amount
        FROM invoice_line_items
        WHERE invoice_id = $1
        ORDER BY id ASC
        "#,
        invoice_id,
    )
    .fetch_all(pool)
    .await
    .map_err(BillingError::DatabaseError)?;

    Ok(rows
        .into_iter()
        .map(|r| InvoiceLineItem {
            description: r.description,
            quantity: r.quantity,
            unit_price: r.unit_price,
            amount: r.amount,
        })
        .collect())
}

// ---------------------------------------------------------------------------
// list_invoices
// ---------------------------------------------------------------------------

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ListInvoicesInput {
    pub tenant_id: Uuid,
    pub user_id: Option<Uuid>,
    pub status: Option<InvoiceStatus>,
    pub from_date: Option<NaiveDate>,
    pub to_date: Option<NaiveDate>,
    #[serde(default = "default_limit")]
    pub limit: i64,
    #[serde(default)]
    pub offset: i64,
}

fn default_limit() -> i64 {
    20
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ListInvoicesOutput {
    pub invoices: Vec<InvoiceSummary>,
    pub total: i64,
    pub total_amount: Decimal,
}

struct InvoiceSummaryRow {
    id: Uuid,
    invoice_number: String,
    status: InvoiceStatus,
    amount: Decimal,
    currency: String,
    due_date: NaiveDate,
}

struct InvoiceAggRow {
    total: Option<i64>,
    total_amount: Option<Decimal>,
}

#[instrument(skip(pool), fields(tool = "list_invoices"))]
pub async fn list_invoices(input: ListInvoicesInput, pool: &PgPool) -> Result<ListInvoicesOutput, BillingError> {
    let start = std::time::Instant::now();
    validate_tenant(input.tenant_id, pool).await?;

    let limit = input.limit.min(100).max(1);
    let offset = input.offset.max(0);

    let agg_row = sqlx::query_as!(
        InvoiceAggRow,
        r#"
        SELECT
            COUNT(*)::bigint AS "total: i64",
            SUM(amount) AS "total_amount: Decimal"
        FROM invoices
        WHERE tenant_id = $1
            AND ($2::invoice_status IS NULL OR status = $2)
            AND ($3::date IS NULL OR due_date >= $3)
            AND ($4::date IS NULL OR due_date <= $4)
        "#,
        input.tenant_id,
        input.status as Option<InvoiceStatus>,
        input.from_date,
        input.to_date,
    )
    .fetch_one(pool)
    .await
    .map_err(BillingError::DatabaseError)?;

    let rows = sqlx::query_as!(
        InvoiceSummaryRow,
        r#"
        SELECT
            id, invoice_number,
            status AS "status: InvoiceStatus",
            amount, currency, due_date
        FROM invoices
        WHERE tenant_id = $1
            AND ($2::invoice_status IS NULL OR status = $2)
            AND ($3::date IS NULL OR due_date >= $3)
            AND ($4::date IS NULL OR due_date <= $4)
        ORDER BY created_at DESC
        LIMIT $5 OFFSET $6
        "#,
        input.tenant_id,
        input.status as Option<InvoiceStatus>,
        input.from_date,
        input.to_date,
        limit,
        offset,
    )
    .fetch_all(pool)
    .await
    .map_err(BillingError::DatabaseError)?;

    let invoices = rows
        .into_iter()
        .map(|r| InvoiceSummary {
            id: r.id,
            invoice_number: r.invoice_number,
            status: r.status,
            amount: r.amount,
            currency: r.currency,
            due_date: r.due_date,
        })
        .collect();

    let duration_ms = start.elapsed().as_millis() as i64;
    let audit_entry = AuditEntry::new(
        input.tenant_id,
        input.user_id,
        "list_invoices",
        &json!({ "status": input.status, "limit": limit, "offset": offset }),
        "OK",
        duration_ms,
    );
    if let Err(e) = write_audit(audit_entry, pool).await {
        error!("Audit write failed for list_invoices: {}", e);
    }

    Ok(ListInvoicesOutput {
        invoices,
        total: agg_row.total.unwrap_or(0),
        total_amount: agg_row.total_amount.unwrap_or(Decimal::ZERO),
    })
}

// ---------------------------------------------------------------------------
// list_overdue_payments
// ---------------------------------------------------------------------------

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ListOverduePaymentsInput {
    pub tenant_id: Uuid,
    pub user_id: Option<Uuid>,
    pub overdue_days_min: Option<i32>,
    pub overdue_days_max: Option<i32>,
    #[serde(default = "default_limit")]
    pub limit: i64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ListOverduePaymentsOutput {
    pub overdue_invoices: Vec<OverdueInvoice>,
    pub total_overdue_amount: Decimal,
    pub currency: String,
    pub count: i64,
}

struct OverdueRow {
    id: Uuid,
    invoice_number: String,
    status: InvoiceStatus,
    amount: Decimal,
    currency: String,
    due_date: NaiveDate,
    overdue_days: Option<i32>,
    contact_email: Option<String>,
}

struct OverdueAggRow {
    total_overdue_amount: Option<Decimal>,
    count: Option<i64>,
    currency: Option<String>,
}

#[instrument(skip(pool), fields(tool = "list_overdue_payments"))]
pub async fn list_overdue_payments(
    input: ListOverduePaymentsInput,
    pool: &PgPool,
) -> Result<ListOverduePaymentsOutput, BillingError> {
    let start = std::time::Instant::now();
    validate_tenant(input.tenant_id, pool).await?;

    let limit = input.limit.min(100).max(1);

    let agg = sqlx::query_as!(
        OverdueAggRow,
        r#"
        SELECT
            SUM(amount) AS "total_overdue_amount: Decimal",
            COUNT(*)::bigint AS "count: i64",
            MIN(currency) AS "currency: String"
        FROM invoices
        WHERE tenant_id = $1
            AND status = 'overdue'
            AND due_date < NOW()
            AND ($2::integer IS NULL OR EXTRACT(DAY FROM NOW() - due_date)::integer >= $2)
            AND ($3::integer IS NULL OR EXTRACT(DAY FROM NOW() - due_date)::integer <= $3)
        "#,
        input.tenant_id,
        input.overdue_days_min,
        input.overdue_days_max,
    )
    .fetch_one(pool)
    .await
    .map_err(BillingError::DatabaseError)?;

    let rows = sqlx::query_as!(
        OverdueRow,
        r#"
        SELECT
            i.id,
            i.invoice_number,
            i.status AS "status: InvoiceStatus",
            i.amount,
            i.currency,
            i.due_date,
            EXTRACT(DAY FROM NOW() - i.due_date)::integer AS "overdue_days: i32",
            o.billing_email AS "contact_email: String"
        FROM invoices i
        LEFT JOIN organizations o ON o.id = i.tenant_id
        WHERE i.tenant_id = $1
            AND i.status = 'overdue'
            AND i.due_date < NOW()
            AND ($2::integer IS NULL OR EXTRACT(DAY FROM NOW() - i.due_date)::integer >= $2)
            AND ($3::integer IS NULL OR EXTRACT(DAY FROM NOW() - i.due_date)::integer <= $3)
        ORDER BY i.due_date ASC
        LIMIT $4
        "#,
        input.tenant_id,
        input.overdue_days_min,
        input.overdue_days_max,
        limit,
    )
    .fetch_all(pool)
    .await
    .map_err(BillingError::DatabaseError)?;

    let overdue_invoices = rows
        .into_iter()
        .map(|r| OverdueInvoice {
            invoice: InvoiceSummary {
                id: r.id,
                invoice_number: r.invoice_number,
                status: r.status,
                amount: r.amount,
                currency: r.currency,
                due_date: r.due_date,
            },
            overdue_days: r.overdue_days.unwrap_or(0),
            contact_email: r.contact_email,
        })
        .collect();

    let duration_ms = start.elapsed().as_millis() as i64;
    let audit_entry = AuditEntry::new(
        input.tenant_id,
        input.user_id,
        "list_overdue_payments",
        &json!({
            "overdue_days_min": input.overdue_days_min,
            "overdue_days_max": input.overdue_days_max,
            "limit": limit
        }),
        "OK",
        duration_ms,
    );
    if let Err(e) = write_audit(audit_entry, pool).await {
        error!("Audit write failed for list_overdue_payments: {}", e);
    }

    Ok(ListOverduePaymentsOutput {
        overdue_invoices,
        total_overdue_amount: agg.total_overdue_amount.unwrap_or(Decimal::ZERO),
        currency: agg.currency.unwrap_or_else(|| "USD".to_string()),
        count: agg.count.unwrap_or(0),
    })
}
