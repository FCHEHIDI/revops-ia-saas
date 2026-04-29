use chrono::NaiveDate;
use rust_decimal::prelude::ToPrimitive;
use rust_decimal::Decimal;
use serde::{Deserialize, Serialize};
use serde_json::json;
use sqlx::PgPool;
use tracing::{error, instrument};
use uuid::Uuid;

use crate::audit::{write_audit, AuditEntry};
use crate::db::validate_tenant;
use crate::errors::AnalyticsError;
use crate::schemas::{AtRiskAccount, ComputeChurnRateOutput, GetAtRiskAccountsOutput};

// ---------------------------------------------------------------------------
// compute_churn_rate
// ---------------------------------------------------------------------------

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ComputeChurnRateInput {
    pub tenant_id: Uuid,
    pub user_id: Option<Uuid>,
    pub period_start: NaiveDate,
    pub period_end: NaiveDate,
    pub churn_type: String,
}

struct CustomerChurnRow {
    starting_count: i64,
    churned_count: i64,
    starting_mrr: Decimal,
    churned_mrr: Decimal,
    expansion_mrr: Decimal,
}

#[instrument(skip(pool), fields(tool = "compute_churn_rate"))]
pub async fn compute_churn_rate(
    input: ComputeChurnRateInput,
    pool: &PgPool,
) -> Result<ComputeChurnRateOutput, AnalyticsError> {
    let start = std::time::Instant::now();
    validate_tenant(input.tenant_id, pool).await?;

    if !["customer", "revenue"].contains(&input.churn_type.as_str()) {
        return Err(AnalyticsError::ValidationError(
            "churn_type must be 'customer' or 'revenue'".to_string(),
        ));
    }

    let row = sqlx::query_as!(
        CustomerChurnRow,
        r#"
        WITH starting AS (
            SELECT
                COUNT(*)          AS starting_count,
                COALESCE(SUM(mrr), 0) AS starting_mrr
            FROM subscriptions
            WHERE tenant_id = $1
              AND started_at < $2::date
              AND (churned_at IS NULL OR churned_at > $2::date)
        ),
        churned AS (
            SELECT
                COUNT(*)          AS churned_count,
                COALESCE(SUM(mrr), 0) AS churned_mrr
            FROM subscriptions
            WHERE tenant_id = $1
              AND churned_at >= $2::date
              AND churned_at <= $3::date
        ),
        expansion AS (
            SELECT COALESCE(SUM(s.mrr - s_prev.mrr), 0) AS expansion_mrr
            FROM subscriptions s
            JOIN subscriptions s_prev
              ON s.account_id = s_prev.account_id
             AND s.tenant_id  = s_prev.tenant_id
            WHERE s.tenant_id  = $1
              AND s.started_at >= $2::date
              AND s.started_at <= $3::date
              AND s.mrr > s_prev.mrr
        )
        SELECT
            starting.starting_count  AS "starting_count!: i64",
            churned.churned_count    AS "churned_count!: i64",
            starting.starting_mrr   AS "starting_mrr!: Decimal",
            churned.churned_mrr     AS "churned_mrr!: Decimal",
            expansion.expansion_mrr AS "expansion_mrr!: Decimal"
        FROM starting, churned, expansion
        "#,
        input.tenant_id,
        input.period_start,
        input.period_end,
    )
    .fetch_one(pool)
    .await
    .map_err(AnalyticsError::DatabaseError)?;

    let churn_rate = match input.churn_type.as_str() {
        "customer" => {
            if row.starting_count > 0 {
                row.churned_count as f32 / row.starting_count as f32
            } else {
                0.0
            }
        }
        _ => {
            // revenue churn
            let starting_mrr = row.starting_mrr.to_f64().unwrap_or(0.0);
            let churned_mrr = row.churned_mrr.to_f64().unwrap_or(0.0);
            if starting_mrr > 0.0 {
                (churned_mrr / starting_mrr) as f32
            } else {
                0.0
            }
        }
    };

    // Net Revenue Retention = (starting_mrr - churned_mrr + expansion_mrr) / starting_mrr
    let starting_mrr_f64 = row.starting_mrr.to_f64().unwrap_or(0.0);
    let churned_mrr_f64 = row.churned_mrr.to_f64().unwrap_or(0.0);
    let expansion_mrr_f64 = row.expansion_mrr.to_f64().unwrap_or(0.0);

    let net_revenue_retention = if starting_mrr_f64 > 0.0 {
        ((starting_mrr_f64 - churned_mrr_f64 + expansion_mrr_f64) / starting_mrr_f64) as f32
    } else {
        1.0
    };

    let gross_revenue_retention = if starting_mrr_f64 > 0.0 {
        ((starting_mrr_f64 - churned_mrr_f64) / starting_mrr_f64).min(1.0).max(0.0) as f32
    } else {
        1.0
    };

    let duration_ms = start.elapsed().as_millis() as i64;
    let audit_entry = AuditEntry::new(
        input.tenant_id,
        input.user_id,
        "compute_churn_rate",
        &json!({
            "period_start": input.period_start,
            "period_end": input.period_end,
            "churn_type": input.churn_type,
        }),
        "OK",
        duration_ms,
    );
    if let Err(e) = write_audit(audit_entry, pool).await {
        error!("Audit write failed for compute_churn_rate: {}", e);
    }

    Ok(ComputeChurnRateOutput {
        churn_rate,
        churned_count: row.churned_count,
        starting_count: row.starting_count,
        net_revenue_retention,
        gross_revenue_retention,
    })
}

// ---------------------------------------------------------------------------
// get_at_risk_accounts
// ---------------------------------------------------------------------------

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GetAtRiskAccountsInput {
    pub tenant_id: Uuid,
    pub user_id: Option<Uuid>,
    pub risk_threshold: Option<f32>,
    pub limit: Option<u32>,
}

struct AtRiskRow {
    account_id: Uuid,
    account_name: String,
    mrr: Decimal,
    last_activity_days_ago: Option<i64>,
    unpaid_invoices: i64,
    overdue_invoices: i64,
}

#[instrument(skip(pool), fields(tool = "get_at_risk_accounts"))]
pub async fn get_at_risk_accounts(
    input: GetAtRiskAccountsInput,
    pool: &PgPool,
) -> Result<GetAtRiskAccountsOutput, AnalyticsError> {
    let start = std::time::Instant::now();
    validate_tenant(input.tenant_id, pool).await?;

    let risk_threshold = input.risk_threshold.unwrap_or(0.6);
    if !(0.0..=1.0).contains(&risk_threshold) {
        return Err(AnalyticsError::ValidationError(
            "risk_threshold must be between 0.0 and 1.0".to_string(),
        ));
    }
    let limit = input.limit.unwrap_or(50).min(200) as i64;

    let rows = sqlx::query_as!(
        AtRiskRow,
        r#"
        SELECT
            a.id                                                                            AS "account_id!: Uuid",
            a.name                                                                          AS "account_name!: String",
            COALESCE(s.mrr, 0)                                                             AS "mrr!: Decimal",
            EXTRACT(DAY FROM NOW() - MAX(act.occurred_at))::bigint                         AS "last_activity_days_ago?: i64",
            COUNT(inv.id) FILTER (WHERE inv.status = 'pending')                             AS "unpaid_invoices!: i64",
            COUNT(inv.id) FILTER (WHERE inv.status = 'overdue')                            AS "overdue_invoices!: i64"
        FROM accounts a
        LEFT JOIN subscriptions s
            ON s.account_id = a.id AND s.tenant_id = a.tenant_id AND s.status = 'active'
        LEFT JOIN activities act
            ON act.entity_id = a.id AND act.tenant_id = a.tenant_id
        LEFT JOIN invoices inv
            ON inv.account_id = a.id AND inv.tenant_id = a.tenant_id
        WHERE a.tenant_id = $1
        GROUP BY a.id, a.name, s.mrr
        ORDER BY s.mrr DESC NULLS LAST
        LIMIT $2
        "#,
        input.tenant_id,
        limit,
    )
    .fetch_all(pool)
    .await
    .map_err(AnalyticsError::DatabaseError)?;

    let mut accounts: Vec<AtRiskAccount> = rows
        .into_iter()
        .filter_map(|r| {
            let risk_score = compute_risk_score(
                r.last_activity_days_ago,
                r.unpaid_invoices,
                r.overdue_invoices,
            );
            if risk_score < risk_threshold {
                return None;
            }
            let risk_signals = build_risk_signals(
                r.last_activity_days_ago,
                r.unpaid_invoices,
                r.overdue_invoices,
            );
            Some(AtRiskAccount {
                account_id: r.account_id,
                account_name: r.account_name,
                risk_score,
                risk_signals,
                mrr_at_risk: r.mrr,
                last_activity_days_ago: r.last_activity_days_ago,
            })
        })
        .collect();

    accounts.sort_by(|a, b| {
        b.risk_score
            .partial_cmp(&a.risk_score)
            .unwrap_or(std::cmp::Ordering::Equal)
    });

    let total = accounts.len() as i64;

    let duration_ms = start.elapsed().as_millis() as i64;
    let audit_entry = AuditEntry::new(
        input.tenant_id,
        input.user_id,
        "get_at_risk_accounts",
        &json!({
            "risk_threshold": risk_threshold,
            "limit": limit,
        }),
        "OK",
        duration_ms,
    );
    if let Err(e) = write_audit(audit_entry, pool).await {
        error!("Audit write failed for get_at_risk_accounts: {}", e);
    }

    Ok(GetAtRiskAccountsOutput { accounts, total })
}

/// Composite risk score in [0.0, 1.0] based on three signals:
/// - Inactivity (days since last activity, capped at 90 days for full score)
/// - Unpaid invoices (each adds 0.15, capped at 0.45)
/// - Overdue invoices (each adds 0.20, capped at 0.40)
fn compute_risk_score(
    last_activity_days_ago: Option<i64>,
    unpaid_invoices: i64,
    overdue_invoices: i64,
) -> f32 {
    let inactivity_score = last_activity_days_ago
        .map(|d| (d as f32 / 90.0).min(1.0) * 0.4)
        .unwrap_or(0.4_f32); // No activity at all → maximum inactivity score

    let unpaid_score = (unpaid_invoices as f32 * 0.15).min(0.45);
    let overdue_score = (overdue_invoices as f32 * 0.20).min(0.40);

    (inactivity_score + unpaid_score + overdue_score).min(1.0)
}

fn build_risk_signals(
    last_activity_days_ago: Option<i64>,
    unpaid_invoices: i64,
    overdue_invoices: i64,
) -> Vec<String> {
    let mut signals = Vec::new();

    match last_activity_days_ago {
        None => signals.push("Aucune activité enregistrée".to_string()),
        Some(d) if d > 60 => signals.push(format!("Pas d'activité depuis {} jours", d)),
        Some(d) if d > 30 => signals.push(format!("Faible engagement ({} jours sans activité)", d)),
        _ => {}
    }

    if overdue_invoices > 0 {
        signals.push(format!("{} facture(s) en retard de paiement", overdue_invoices));
    }
    if unpaid_invoices > 0 {
        signals.push(format!("{} facture(s) impayée(s)", unpaid_invoices));
    }

    signals
}
