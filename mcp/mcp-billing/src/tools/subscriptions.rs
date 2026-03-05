use chrono::{DateTime, Utc};
use rust_decimal::Decimal;
use serde::{Deserialize, Serialize};
use serde_json::json;
use sqlx::PgPool;
use tracing::{error, instrument};
use uuid::Uuid;

use crate::audit::{write_audit, AuditEntry};
use crate::db::validate_tenant;
use crate::errors::BillingError;
use crate::schemas::{Subscription, SubscriptionStatus};

// ---------------------------------------------------------------------------
// get_subscription
// ---------------------------------------------------------------------------

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GetSubscriptionInput {
    pub tenant_id: Uuid,
    pub user_id: Option<Uuid>,
    /// If None, fetches the most recent active subscription for the tenant.
    pub subscription_id: Option<Uuid>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GetSubscriptionOutput {
    pub subscription: Subscription,
}

struct SubscriptionRow {
    id: Uuid,
    tenant_id: Uuid,
    plan_id: String,
    plan_name: String,
    status: SubscriptionStatus,
    seats: i32,
    mrr: Decimal,
    currency: String,
    current_period_start: DateTime<Utc>,
    current_period_end: DateTime<Utc>,
    cancel_at_period_end: bool,
    trial_end: Option<DateTime<Utc>>,
    features: serde_json::Value,
    created_at: DateTime<Utc>,
}

impl SubscriptionRow {
    fn into_subscription(self) -> Subscription {
        let features: Vec<String> = self
            .features
            .as_array()
            .map(|arr| {
                arr.iter()
                    .filter_map(|v| v.as_str().map(|s| s.to_string()))
                    .collect()
            })
            .unwrap_or_default();

        Subscription {
            id: self.id,
            tenant_id: self.tenant_id,
            plan_id: self.plan_id,
            plan_name: self.plan_name,
            status: self.status,
            seats: self.seats,
            mrr: self.mrr,
            currency: self.currency,
            current_period_start: self.current_period_start,
            current_period_end: self.current_period_end,
            cancel_at_period_end: self.cancel_at_period_end,
            trial_end: self.trial_end,
            features,
            created_at: self.created_at,
        }
    }
}

#[instrument(skip(pool), fields(tool = "get_subscription"))]
pub async fn get_subscription(
    input: GetSubscriptionInput,
    pool: &PgPool,
) -> Result<GetSubscriptionOutput, BillingError> {
    let start = std::time::Instant::now();
    validate_tenant(input.tenant_id, pool).await?;

    let row = match input.subscription_id {
        Some(sub_id) => {
            sqlx::query_as!(
                SubscriptionRow,
                r#"
                SELECT
                    id, tenant_id, plan_id, plan_name,
                    status AS "status: SubscriptionStatus",
                    seats, mrr, currency,
                    current_period_start, current_period_end,
                    cancel_at_period_end, trial_end,
                    features, created_at
                FROM subscriptions
                WHERE id = $1 AND tenant_id = $2
                "#,
                sub_id,
                input.tenant_id,
            )
            .fetch_optional(pool)
            .await
            .map_err(BillingError::DatabaseError)?
            .ok_or_else(|| BillingError::NotFound(format!("subscription {}", sub_id)))?
        }
        None => {
            sqlx::query_as!(
                SubscriptionRow,
                r#"
                SELECT
                    id, tenant_id, plan_id, plan_name,
                    status AS "status: SubscriptionStatus",
                    seats, mrr, currency,
                    current_period_start, current_period_end,
                    cancel_at_period_end, trial_end,
                    features, created_at
                FROM subscriptions
                WHERE tenant_id = $1
                ORDER BY created_at DESC
                LIMIT 1
                "#,
                input.tenant_id,
            )
            .fetch_optional(pool)
            .await
            .map_err(BillingError::DatabaseError)?
            .ok_or_else(|| BillingError::NoActiveSubscription)?
        }
    };

    let subscription = row.into_subscription();

    let duration_ms = start.elapsed().as_millis() as i64;
    let audit_entry = AuditEntry::new(
        input.tenant_id,
        input.user_id,
        "get_subscription",
        &json!({ "subscription_id": input.subscription_id }),
        "OK",
        duration_ms,
    );
    if let Err(e) = write_audit(audit_entry, pool).await {
        error!("Audit write failed for get_subscription: {}", e);
    }

    Ok(GetSubscriptionOutput { subscription })
}

// ---------------------------------------------------------------------------
// check_subscription_status
// ---------------------------------------------------------------------------

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CheckSubscriptionStatusInput {
    pub tenant_id: Uuid,
    pub user_id: Option<Uuid>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CheckSubscriptionStatusOutput {
    pub status: SubscriptionStatus,
    pub plan_name: String,
    pub current_period_end: DateTime<Utc>,
    pub is_trial: bool,
    pub trial_ends_at: Option<DateTime<Utc>>,
    pub seats_used: i64,
    pub seats_total: i32,
    pub features: Vec<String>,
}

struct ActiveSubscriptionRow {
    status: SubscriptionStatus,
    plan_name: String,
    current_period_end: DateTime<Utc>,
    trial_end: Option<DateTime<Utc>>,
    seats: i32,
    features: serde_json::Value,
}

#[instrument(skip(pool), fields(tool = "check_subscription_status"))]
pub async fn check_subscription_status(
    input: CheckSubscriptionStatusInput,
    pool: &PgPool,
) -> Result<CheckSubscriptionStatusOutput, BillingError> {
    let start = std::time::Instant::now();
    validate_tenant(input.tenant_id, pool).await?;

    let sub = sqlx::query_as!(
        ActiveSubscriptionRow,
        r#"
        SELECT
            status AS "status: SubscriptionStatus",
            plan_name,
            current_period_end,
            trial_end,
            seats,
            features
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
    .map_err(BillingError::DatabaseError)?
    .ok_or(BillingError::NoActiveSubscription)?;

    let seats_used: i64 = sqlx::query_scalar!(
        r#"SELECT COUNT(*)::bigint FROM users WHERE tenant_id = $1 AND active = true"#,
        input.tenant_id,
    )
    .fetch_one(pool)
    .await
    .map_err(BillingError::DatabaseError)?
    .unwrap_or(0);

    let features: Vec<String> = sub
        .features
        .as_array()
        .map(|arr| {
            arr.iter()
                .filter_map(|v| v.as_str().map(|s| s.to_string()))
                .collect()
        })
        .unwrap_or_default();

    let is_trial = matches!(sub.status, SubscriptionStatus::Trialing);
    let trial_ends_at = if is_trial { sub.trial_end } else { None };

    let duration_ms = start.elapsed().as_millis() as i64;
    let audit_entry = AuditEntry::new(
        input.tenant_id,
        input.user_id,
        "check_subscription_status",
        &json!({}),
        "OK",
        duration_ms,
    );
    if let Err(e) = write_audit(audit_entry, pool).await {
        error!("Audit write failed for check_subscription_status: {}", e);
    }

    Ok(CheckSubscriptionStatusOutput {
        status: sub.status,
        plan_name: sub.plan_name,
        current_period_end: sub.current_period_end,
        is_trial,
        trial_ends_at,
        seats_used,
        seats_total: sub.seats,
        features,
    })
}

// ---------------------------------------------------------------------------
// update_subscription_status
// ---------------------------------------------------------------------------

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct UpdateSubscriptionStatusInput {
    pub tenant_id: Uuid,
    pub user_id: Option<Uuid>,
    pub subscription_id: Uuid,
    pub new_status: SubscriptionStatus,
    pub reason: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct UpdateSubscriptionStatusOutput {
    pub previous_status: SubscriptionStatus,
    pub new_status: SubscriptionStatus,
    pub updated_at: DateTime<Utc>,
}

struct CurrentStatusRow {
    status: SubscriptionStatus,
}

#[instrument(skip(pool), fields(tool = "update_subscription_status"))]
pub async fn update_subscription_status(
    input: UpdateSubscriptionStatusInput,
    pool: &PgPool,
) -> Result<UpdateSubscriptionStatusOutput, BillingError> {
    let start = std::time::Instant::now();

    // 1. Validate tenant first (always first per ADR-003)
    validate_tenant(input.tenant_id, pool).await?;

    // 2. Permission check — caller must hold billing:subscriptions:write
    //    In the MCP layer, permissions are passed as part of the input context.
    //    The orchestrator is responsible for injecting the user's permission set;
    //    here we validate the required permission exists on the user record.
    let has_permission: bool = sqlx::query_scalar!(
        r#"
        SELECT EXISTS(
            SELECT 1 FROM user_permissions
            WHERE user_id = $1
                AND tenant_id = $2
                AND permission = 'billing:subscriptions:write'
        )
        "#,
        input.user_id,
        input.tenant_id,
    )
    .fetch_one(pool)
    .await
    .map_err(BillingError::DatabaseError)?
    .unwrap_or(false);

    if !has_permission {
        return Err(BillingError::PermissionDenied(
            "billing:subscriptions:write".to_string(),
        ));
    }

    // 3. Fetch current status
    let current = sqlx::query_as!(
        CurrentStatusRow,
        r#"
        SELECT status AS "status: SubscriptionStatus"
        FROM subscriptions
        WHERE id = $1 AND tenant_id = $2
        "#,
        input.subscription_id,
        input.tenant_id,
    )
    .fetch_optional(pool)
    .await
    .map_err(BillingError::DatabaseError)?
    .ok_or_else(|| BillingError::NotFound(format!("subscription {}", input.subscription_id)))?;

    // 4. Validate transition
    if !current.status.can_transition_to(&input.new_status) {
        return Err(BillingError::InvalidTransition {
            from: current.status.as_str().to_string(),
            to: input.new_status.as_str().to_string(),
        });
    }

    let updated_at = Utc::now();

    // 5. Apply update
    sqlx::query!(
        r#"
        UPDATE subscriptions
        SET status = $1, updated_at = $2
        WHERE id = $3 AND tenant_id = $4
        "#,
        input.new_status as SubscriptionStatus,
        updated_at,
        input.subscription_id,
        input.tenant_id,
    )
    .execute(pool)
    .await
    .map_err(BillingError::DatabaseError)?;

    // 6. Write enriched audit log (reason is critical context for this write action)
    let duration_ms = start.elapsed().as_millis() as i64;
    let audit_entry = AuditEntry::new(
        input.tenant_id,
        input.user_id,
        "update_subscription_status",
        &json!({
            "subscription_id": input.subscription_id,
            "new_status": input.new_status.as_str(),
        }),
        "OK",
        duration_ms,
    )
    .with_metadata(json!({
        "previous_status": current.status.as_str(),
        "new_status": input.new_status.as_str(),
        "reason": input.reason,
    }));

    if let Err(e) = write_audit(audit_entry, pool).await {
        error!("Audit write failed for update_subscription_status: {}", e);
    }

    Ok(UpdateSubscriptionStatusOutput {
        previous_status: current.status,
        new_status: input.new_status,
        updated_at,
    })
}
