use chrono::{Datelike, NaiveDate};
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
use crate::schemas::{ForecastRevenueOutput, GetMrrTrendOutput, MrrDataPoint, MonthlyForecast};

// ---------------------------------------------------------------------------
// forecast_revenue
// ---------------------------------------------------------------------------

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ForecastRevenueInput {
    pub tenant_id: Uuid,
    pub user_id: Option<Uuid>,
    pub forecast_months: u8,
    pub model: String,
    pub include_existing_mrr: bool,
    pub assigned_to: Option<Uuid>,
}

struct DealForecastRow {
    close_month: NaiveDate,
    weighted_revenue: Decimal,
}

struct MonthlyRevenueRow {
    month: NaiveDate,
    total_revenue: Decimal,
}

/// Fits a simple linear regression and returns (slope, intercept).
/// Returns (0, 0) when there are fewer than 2 data points or variance is zero.
fn linear_regression(points: &[(f64, f64)]) -> (f64, f64) {
    let n = points.len() as f64;
    if n < 2.0 {
        return (0.0, 0.0);
    }
    let sum_x: f64 = points.iter().map(|(x, _)| x).sum();
    let sum_y: f64 = points.iter().map(|(_, y)| y).sum();
    let sum_xy: f64 = points.iter().map(|(x, y)| x * y).sum();
    let sum_xx: f64 = points.iter().map(|(x, _)| x * x).sum();
    let denom = n * sum_xx - sum_x * sum_x;
    if denom.abs() < f64::EPSILON {
        return (0.0, sum_y / n);
    }
    let slope = (n * sum_xy - sum_x * sum_y) / denom;
    let intercept = (sum_y - slope * sum_x) / n;
    (slope, intercept)
}

/// Returns the first day of the month following `date`.
fn next_month_start(date: NaiveDate) -> NaiveDate {
    let (year, month) = if date.month() == 12 {
        (date.year() + 1, 1)
    } else {
        (date.year(), date.month() + 1)
    };
    NaiveDate::from_ymd_opt(year, month, 1).unwrap_or(date)
}

#[instrument(skip(pool), fields(tool = "forecast_revenue"))]
pub async fn forecast_revenue(
    input: ForecastRevenueInput,
    pool: &PgPool,
) -> Result<ForecastRevenueOutput, AnalyticsError> {
    let start = std::time::Instant::now();
    validate_tenant(input.tenant_id, pool).await?;

    if input.forecast_months > 12 {
        return Err(AnalyticsError::ValidationError(
            "forecast_months must not exceed 12".to_string(),
        ));
    }

    if !["weighted_pipeline", "linear_trend", "conservative"].contains(&input.model.as_str()) {
        return Err(AnalyticsError::ValidationError(
            "model must be 'weighted_pipeline', 'linear_trend', or 'conservative'".to_string(),
        ));
    }

    let today = chrono::Local::now().date_naive();
    let forecast_start = NaiveDate::from_ymd_opt(today.year(), today.month(), 1)
        .unwrap_or(today);

    let monthly_forecast = match input.model.as_str() {
        "weighted_pipeline" | "conservative" => {
            let multiplier = if input.model == "conservative" { 0.7_f64 } else { 1.0 };

            let rows = sqlx::query_as!(
                DealForecastRow,
                r#"
                SELECT
                    DATE_TRUNC('month', close_date)::date                AS "close_month!: NaiveDate",
                    COALESCE(SUM(value * probability), 0)                AS "weighted_revenue!: Decimal"
                FROM deals
                WHERE tenant_id = $1
                  AND stage NOT IN ('closed_won', 'closed_lost')
                  AND close_date >= $2
                  AND close_date < $2 + ($3::int * INTERVAL '1 month')
                  AND ($4::uuid IS NULL OR assigned_to = $4)
                GROUP BY DATE_TRUNC('month', close_date)
                ORDER BY DATE_TRUNC('month', close_date)
                "#,
                input.tenant_id,
                forecast_start,
                input.forecast_months as i32,
                input.assigned_to,
            )
            .fetch_all(pool)
            .await
            .map_err(AnalyticsError::DatabaseError)?;

            // Fetch current MRR if requested
            let mrr = if input.include_existing_mrr {
                sqlx::query_scalar!(
                    r#"
                    SELECT COALESCE(SUM(mrr), 0) AS "mrr!: Decimal"
                    FROM subscriptions
                    WHERE tenant_id = $1 AND status = 'active'
                    "#,
                    input.tenant_id,
                )
                .fetch_one(pool)
                .await
                .unwrap_or(Decimal::ZERO)
            } else {
                Decimal::ZERO
            };

            (0..input.forecast_months)
                .map(|i| {
                    let month = {
                        let mut m = forecast_start;
                        for _ in 0..i {
                            m = next_month_start(m);
                        }
                        m
                    };
                    let new_rev = rows
                        .iter()
                        .find(|r| r.close_month == month)
                        .map(|r| {
                            let v: f64 = r.weighted_revenue.to_f64().unwrap_or(0.0) * multiplier;
                            Decimal::try_from(v).unwrap_or(Decimal::ZERO)
                        })
                        .unwrap_or(Decimal::ZERO);
                    let total = new_rev + mrr;
                    MonthlyForecast {
                        month,
                        new_revenue: new_rev,
                        recurring_revenue: mrr,
                        total,
                    }
                })
                .collect::<Vec<_>>()
        }
        _ => {
            // linear_trend: regression on last 6 months of actual revenue
            let six_months_ago = {
                let mut d = forecast_start;
                for _ in 0..6 {
                    d = d
                        .with_day(1)
                        .unwrap_or(d)
                        .checked_sub_months(chrono::Months::new(1))
                        .unwrap_or(d);
                }
                d
            };

            let historical = sqlx::query_as!(
                MonthlyRevenueRow,
                r#"
                SELECT
                    DATE_TRUNC('month', closed_at)::date                  AS "month!: NaiveDate",
                    COALESCE(SUM(value), 0)                               AS "total_revenue!: Decimal"
                FROM deals
                WHERE tenant_id = $1
                  AND stage = 'closed_won'
                  AND closed_at IS NOT NULL
                  AND closed_at::date >= $2
                  AND closed_at::date < $3
                GROUP BY DATE_TRUNC('month', closed_at)
                ORDER BY DATE_TRUNC('month', closed_at)
                "#,
                input.tenant_id,
                six_months_ago,
                forecast_start,
            )
            .fetch_all(pool)
            .await
            .map_err(AnalyticsError::DatabaseError)?;

            let points: Vec<(f64, f64)> = historical
                .iter()
                .enumerate()
                .map(|(i, r)| {
                    let y: f64 = r.total_revenue.to_f64().unwrap_or(0.0);
                    (i as f64, y)
                })
                .collect();

            let (slope, intercept) = linear_regression(&points);
            let base_x = points.len() as f64;

            (0..input.forecast_months)
                .map(|i| {
                    let month = {
                        let mut m = forecast_start;
                        for _ in 0..i {
                            m = next_month_start(m);
                        }
                        m
                    };
                    let predicted = (slope * (base_x + i as f64) + intercept).max(0.0);
                    let new_rev = Decimal::try_from(predicted).unwrap_or(Decimal::ZERO);
                    MonthlyForecast {
                        month,
                        new_revenue: new_rev,
                        recurring_revenue: Decimal::ZERO,
                        total: new_rev,
                    }
                })
                .collect::<Vec<_>>()
        }
    };

    let total_forecast: Decimal = monthly_forecast.iter().map(|m| m.total).sum();

    let assumptions = match input.model.as_str() {
        "weighted_pipeline" => vec![
            "Revenue = SUM(deal.value × deal.probability) ventilé par mois de close_date".to_string(),
            "Seuls les deals en cours (non fermés) sont inclus".to_string(),
        ],
        "conservative" => vec![
            "Revenue = weighted_pipeline × 0.7".to_string(),
            "Facteur de conservation 30% appliqué sur le pipeline pondéré".to_string(),
        ],
        _ => vec![
            "Régression linéaire sur les 6 derniers mois de revenue réel".to_string(),
            "Extrapolation de la tendance observée sur la période de forecast".to_string(),
        ],
    };

    let duration_ms = start.elapsed().as_millis() as i64;
    let audit_entry = AuditEntry::new(
        input.tenant_id,
        input.user_id,
        "forecast_revenue",
        &json!({
            "forecast_months": input.forecast_months,
            "model": input.model,
            "include_existing_mrr": input.include_existing_mrr,
            "assigned_to": input.assigned_to,
        }),
        "OK",
        duration_ms,
    );
    if let Err(e) = write_audit(audit_entry, pool).await {
        error!("Audit write failed for forecast_revenue: {}", e);
    }

    Ok(ForecastRevenueOutput {
        monthly_forecast,
        total_forecast,
        model_used: input.model,
        assumptions,
    })
}

// ---------------------------------------------------------------------------
// get_mrr_trend
// ---------------------------------------------------------------------------

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GetMrrTrendInput {
    pub tenant_id: Uuid,
    pub user_id: Option<Uuid>,
    pub months: Option<u8>,
}

struct MrrRow {
    month: NaiveDate,
    mrr: Decimal,
    new_mrr: Decimal,
    churned_mrr: Decimal,
}

#[instrument(skip(pool), fields(tool = "get_mrr_trend"))]
pub async fn get_mrr_trend(
    input: GetMrrTrendInput,
    pool: &PgPool,
) -> Result<GetMrrTrendOutput, AnalyticsError> {
    let start_fn = std::time::Instant::now();
    validate_tenant(input.tenant_id, pool).await?;

    let months = input.months.unwrap_or(12).min(24);

    let today = chrono::Local::now().date_naive();
    let period_start = {
        let mut d = NaiveDate::from_ymd_opt(today.year(), today.month(), 1).unwrap_or(today);
        for _ in 0..months {
            d = d
                .checked_sub_months(chrono::Months::new(1))
                .unwrap_or(d);
        }
        d
    };

    let rows = sqlx::query_as!(
        MrrRow,
        r#"
        SELECT
            DATE_TRUNC('month', started_at)::date                            AS "month!: NaiveDate",
            COALESCE(SUM(mrr) FILTER (WHERE status = 'active'), 0)           AS "mrr!: Decimal",
            COALESCE(SUM(mrr) FILTER (WHERE status = 'active'
                AND started_at >= DATE_TRUNC('month', started_at)), 0)        AS "new_mrr!: Decimal",
            COALESCE(SUM(mrr) FILTER (WHERE status = 'churned'
                AND churned_at >= DATE_TRUNC('month', churned_at)), 0)        AS "churned_mrr!: Decimal"
        FROM subscriptions
        WHERE tenant_id = $1
          AND started_at::date >= $2
        GROUP BY DATE_TRUNC('month', started_at)
        ORDER BY DATE_TRUNC('month', started_at)
        "#,
        input.tenant_id,
        period_start,
    )
    .fetch_all(pool)
    .await
    .map_err(AnalyticsError::DatabaseError)?;

    let current_mrr = rows.last().map(|r| r.mrr).unwrap_or(Decimal::ZERO);

    let mom_growth_rate = if rows.len() >= 2 {
        let prev = rows[rows.len() - 2].mrr;
        let curr = rows[rows.len() - 1].mrr;
        if prev > Decimal::ZERO {
            let growth: f64 = ((curr - prev).to_f64().unwrap_or(0.0))
                / prev.to_f64().unwrap_or(1.0);
            growth as f32
        } else {
            0.0
        }
    } else {
        0.0
    };

    let data_points = rows
        .into_iter()
        .map(|r| MrrDataPoint {
            month: r.month,
            mrr: r.mrr,
            new_mrr: r.new_mrr,
            churned_mrr: r.churned_mrr,
            net_new_mrr: r.new_mrr - r.churned_mrr,
        })
        .collect();

    let duration_ms = start_fn.elapsed().as_millis() as i64;
    let audit_entry = AuditEntry::new(
        input.tenant_id,
        input.user_id,
        "get_mrr_trend",
        &json!({ "months": months }),
        "OK",
        duration_ms,
    );
    if let Err(e) = write_audit(audit_entry, pool).await {
        error!("Audit write failed for get_mrr_trend: {}", e);
    }

    Ok(GetMrrTrendOutput {
        data_points,
        current_mrr,
        mom_growth_rate,
    })
}
