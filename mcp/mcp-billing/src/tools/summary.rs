use chrono::{DateTime, Datelike, NaiveDate, Utc};
use rust_decimal::Decimal;
use serde::{Deserialize, Serialize};
use serde_json::json;
use sqlx::PgPool;
use tracing::{error, instrument};
use uuid::Uuid;

use crate::audit::{write_audit, AuditEntry};
use crate::db::validate_tenant;
use crate::errors::BillingError;
use crate::schemas::MrrDataPoint;

// ---------------------------------------------------------------------------
// get_customer_billing_summary
// ---------------------------------------------------------------------------

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GetCustomerBillingSummaryInput {
    pub tenant_id: Uuid,
    pub user_id: Option<Uuid>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GetCustomerBillingSummaryOutput {
    pub mrr: Decimal,
    pub arr: Decimal,
    pub currency: String,
    pub pending_invoices_count: i64,
    pub pending_invoices_amount: Decimal,
    pub next_renewal_date: Option<DateTime<Utc>>,
    pub lifetime_value: Decimal,
    pub payment_method_last4: Option<String>,
}

struct ActiveSubRow {
    mrr: Decimal,
    currency: String,
    current_period_end: DateTime<Utc>,
}

struct InvoiceStatsRow {
    pending_count: Option<i64>,
    pending_amount: Option<Decimal>,
    lifetime_value: Option<Decimal>,
}

#[instrument(skip(pool), fields(tool = "get_customer_billing_summary"))]
pub async fn get_customer_billing_summary(
    input: GetCustomerBillingSummaryInput,
    pool: &PgPool,
) -> Result<GetCustomerBillingSummaryOutput, BillingError> {
    let start = std::time::Instant::now();
    validate_tenant(input.tenant_id, pool).await?;

    // Fetch active subscription for MRR, ARR, currency, next renewal
    let active_sub = sqlx::query_as!(
        ActiveSubRow,
        r#"
        SELECT mrr, currency, current_period_end
        FROM subscriptions
        WHERE tenant_id = $1
            AND status IN ('active', 'trialing', 'past_due')
        ORDER BY created_at DESC
        LIMIT 1
        "#,
        input.tenant_id,
    )
    .fetch_optional(pool)
    .await
    .map_err(BillingError::DatabaseError)?;

    let (mrr, currency, next_renewal_date) = match active_sub {
        Some(sub) => (sub.mrr, sub.currency, Some(sub.current_period_end)),
        None => (Decimal::ZERO, "USD".to_string(), None),
    };

    let arr = mrr * Decimal::from(12);

    // Fetch invoice statistics in a single query
    let stats = sqlx::query_as!(
        InvoiceStatsRow,
        r#"
        SELECT
            SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END)::bigint AS "pending_count: i64",
            SUM(CASE WHEN status = 'pending' THEN amount ELSE 0 END) AS "pending_amount: Decimal",
            SUM(CASE WHEN status = 'paid' THEN amount ELSE 0 END) AS "lifetime_value: Decimal"
        FROM invoices
        WHERE tenant_id = $1
        "#,
        input.tenant_id,
    )
    .fetch_one(pool)
    .await
    .map_err(BillingError::DatabaseError)?;

    // Fetch default payment method last 4 digits
    let payment_method_last4: Option<String> = sqlx::query_scalar!(
        r#"
        SELECT last4
        FROM payment_methods
        WHERE tenant_id = $1 AND is_default = true
        LIMIT 1
        "#,
        input.tenant_id,
    )
    .fetch_optional(pool)
    .await
    .map_err(BillingError::DatabaseError)?;

    let duration_ms = start.elapsed().as_millis() as i64;
    let audit_entry = AuditEntry::new(
        input.tenant_id,
        input.user_id,
        "get_customer_billing_summary",
        &json!({}),
        "OK",
        duration_ms,
    );
    if let Err(e) = write_audit(audit_entry, pool).await {
        error!("Audit write failed for get_customer_billing_summary: {}", e);
    }

    Ok(GetCustomerBillingSummaryOutput {
        mrr,
        arr,
        currency,
        pending_invoices_count: stats.pending_count.unwrap_or(0),
        pending_invoices_amount: stats.pending_amount.unwrap_or(Decimal::ZERO),
        next_renewal_date,
        lifetime_value: stats.lifetime_value.unwrap_or(Decimal::ZERO),
        payment_method_last4,
    })
}

// ---------------------------------------------------------------------------
// get_mrr
// ---------------------------------------------------------------------------

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GetMrrInput {
    pub tenant_id: Uuid,
    pub user_id: Option<Uuid>,
    pub from_date: NaiveDate,
    pub to_date: NaiveDate,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GetMrrOutput {
    pub data_points: Vec<MrrDataPoint>,
    pub current_mrr: Decimal,
    pub growth_rate: f64,
}

struct MrrSnapshotRow {
    month_date: Option<NaiveDate>,
    mrr: Option<Decimal>,
    new_mrr: Option<Decimal>,
    expansion_mrr: Option<Decimal>,
    churned_mrr: Option<Decimal>,
}

struct CurrentMrrRow {
    mrr: Option<Decimal>,
}

#[instrument(skip(pool), fields(tool = "get_mrr"))]
pub async fn get_mrr(input: GetMrrInput, pool: &PgPool) -> Result<GetMrrOutput, BillingError> {
    let start = std::time::Instant::now();

    if input.from_date > input.to_date {
        return Err(BillingError::ValidationError(
            "from_date must be before or equal to to_date".to_string(),
        ));
    }

    validate_tenant(input.tenant_id, pool).await?;

    // Aggregate monthly MRR snapshots for the requested range.
    // One data point per calendar month within [from_date, to_date].
    let rows = sqlx::query_as!(
        MrrSnapshotRow,
        r#"
        SELECT
            DATE_TRUNC('month', snapshot_date)::date AS "month_date: NaiveDate",
            AVG(mrr) AS "mrr: Decimal",
            SUM(new_mrr) AS "new_mrr: Decimal",
            SUM(expansion_mrr) AS "expansion_mrr: Decimal",
            SUM(churned_mrr) AS "churned_mrr: Decimal"
        FROM mrr_snapshots
        WHERE tenant_id = $1
            AND snapshot_date >= $2
            AND snapshot_date <= $3
        GROUP BY DATE_TRUNC('month', snapshot_date)
        ORDER BY DATE_TRUNC('month', snapshot_date) ASC
        "#,
        input.tenant_id,
        input.from_date,
        input.to_date,
    )
    .fetch_all(pool)
    .await
    .map_err(BillingError::DatabaseError)?;

    // Build one data point per month in the requested range, filling gaps with zeros.
    let data_points = build_monthly_data_points(input.from_date, input.to_date, rows);

    // Current MRR from the active subscription
    let current_row = sqlx::query_as!(
        CurrentMrrRow,
        r#"
        SELECT mrr AS "mrr: Decimal"
        FROM subscriptions
        WHERE tenant_id = $1
            AND status IN ('active', 'trialing', 'past_due')
        ORDER BY created_at DESC
        LIMIT 1
        "#,
        input.tenant_id,
    )
    .fetch_optional(pool)
    .await
    .map_err(BillingError::DatabaseError)?;

    let current_mrr = current_row
        .and_then(|r| r.mrr)
        .unwrap_or(Decimal::ZERO);

    // Growth rate: ((last_month_mrr - first_month_mrr) / first_month_mrr) * 100
    let growth_rate = compute_growth_rate(&data_points);

    let duration_ms = start.elapsed().as_millis() as i64;
    let audit_entry = AuditEntry::new(
        input.tenant_id,
        input.user_id,
        "get_mrr",
        &json!({ "from_date": input.from_date, "to_date": input.to_date }),
        "OK",
        duration_ms,
    );
    if let Err(e) = write_audit(audit_entry, pool).await {
        error!("Audit write failed for get_mrr: {}", e);
    }

    Ok(GetMrrOutput {
        data_points,
        current_mrr,
        growth_rate,
    })
}

/// Fills in every calendar month between from_date and to_date (inclusive),
/// merging query results. Months with no snapshot data get zero values.
fn build_monthly_data_points(
    from_date: NaiveDate,
    to_date: NaiveDate,
    rows: Vec<MrrSnapshotRow>,
) -> Vec<MrrDataPoint> {
    use std::collections::HashMap;

    let snapshot_map: HashMap<NaiveDate, &MrrSnapshotRow> = rows
        .iter()
        .filter_map(|r| r.month_date.map(|d| (d, r)))
        .collect();

    let mut points = Vec::new();
    let mut current = NaiveDate::from_ymd_opt(from_date.year(), from_date.month(), 1)
        .unwrap_or(from_date);
    let last = NaiveDate::from_ymd_opt(to_date.year(), to_date.month(), 1)
        .unwrap_or(to_date);

    while current <= last {
        let (mrr, new_mrr, expansion_mrr, churned_mrr) = if let Some(row) = snapshot_map.get(&current) {
            (
                row.mrr.unwrap_or(Decimal::ZERO),
                row.new_mrr.unwrap_or(Decimal::ZERO),
                row.expansion_mrr.unwrap_or(Decimal::ZERO),
                row.churned_mrr.unwrap_or(Decimal::ZERO),
            )
        } else {
            (Decimal::ZERO, Decimal::ZERO, Decimal::ZERO, Decimal::ZERO)
        };

        points.push(MrrDataPoint {
            date: current,
            mrr,
            new_mrr,
            expansion_mrr,
            churned_mrr,
        });

        // Advance to next month
        let (year, month) = if current.month() == 12 {
            (current.year() + 1, 1)
        } else {
            (current.year(), current.month() + 1)
        };
        match NaiveDate::from_ymd_opt(year, month, 1) {
            Some(next) => current = next,
            None => break,
        }
    }

    points
}

fn compute_growth_rate(points: &[MrrDataPoint]) -> f64 {
    if points.len() < 2 {
        return 0.0;
    }
    let first = points.first().map(|p| p.mrr).unwrap_or(Decimal::ZERO);
    let last = points.last().map(|p| p.mrr).unwrap_or(Decimal::ZERO);

    if first.is_zero() {
        return 0.0;
    }

    let first_f: f64 = first.try_into().unwrap_or(0.0);
    let last_f: f64 = last.try_into().unwrap_or(0.0);

    ((last_f - first_f) / first_f) * 100.0
}
