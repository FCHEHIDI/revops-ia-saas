use chrono::{DateTime, NaiveDate, Utc};
use rust_decimal::Decimal;
use serde::{Deserialize, Serialize};
use uuid::Uuid;

// ---------------------------------------------------------------------------
// Enums
// ---------------------------------------------------------------------------

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq, sqlx::Type)]
#[sqlx(type_name = "invoice_status", rename_all = "snake_case")]
#[serde(rename_all = "snake_case")]
pub enum InvoiceStatus {
    Draft,
    Pending,
    Paid,
    Overdue,
    Void,
    Refunded,
}

impl InvoiceStatus {
    pub fn as_str(&self) -> &'static str {
        match self {
            InvoiceStatus::Draft => "draft",
            InvoiceStatus::Pending => "pending",
            InvoiceStatus::Paid => "paid",
            InvoiceStatus::Overdue => "overdue",
            InvoiceStatus::Void => "void",
            InvoiceStatus::Refunded => "refunded",
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq, sqlx::Type)]
#[sqlx(type_name = "subscription_status", rename_all = "snake_case")]
#[serde(rename_all = "snake_case")]
pub enum SubscriptionStatus {
    Trialing,
    Active,
    PastDue,
    Canceled,
    Suspended,
    Paused,
}

impl SubscriptionStatus {
    pub fn as_str(&self) -> &'static str {
        match self {
            SubscriptionStatus::Trialing => "trialing",
            SubscriptionStatus::Active => "active",
            SubscriptionStatus::PastDue => "past_due",
            SubscriptionStatus::Canceled => "canceled",
            SubscriptionStatus::Suspended => "suspended",
            SubscriptionStatus::Paused => "paused",
        }
    }

    /// Returns the list of statuses this status can legally transition to.
    pub fn valid_transitions(&self) -> &[SubscriptionStatus] {
        match self {
            SubscriptionStatus::Active => &[SubscriptionStatus::PastDue, SubscriptionStatus::Suspended],
            SubscriptionStatus::Suspended => &[SubscriptionStatus::Active],
            SubscriptionStatus::PastDue => &[SubscriptionStatus::Active, SubscriptionStatus::Canceled],
            SubscriptionStatus::Trialing => &[SubscriptionStatus::Active, SubscriptionStatus::Canceled],
            SubscriptionStatus::Canceled => &[],
            SubscriptionStatus::Paused => &[SubscriptionStatus::Active],
        }
    }

    pub fn can_transition_to(&self, target: &SubscriptionStatus) -> bool {
        self.valid_transitions().contains(target)
    }

    /// Returns true if this status qualifies as "active" for subscription checks.
    pub fn is_active_for_service(&self) -> bool {
        matches!(
            self,
            SubscriptionStatus::Active | SubscriptionStatus::Trialing | SubscriptionStatus::PastDue
        )
    }
}

// ---------------------------------------------------------------------------
// Core entities
// ---------------------------------------------------------------------------

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Invoice {
    pub id: Uuid,
    pub tenant_id: Uuid,
    pub subscription_id: Uuid,
    pub invoice_number: String,
    pub status: InvoiceStatus,
    pub amount: Decimal,
    pub currency: String,
    pub due_date: NaiveDate,
    pub paid_at: Option<DateTime<Utc>>,
    pub line_items: Vec<InvoiceLineItem>,
    pub created_at: DateTime<Utc>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct InvoiceLineItem {
    pub description: String,
    pub quantity: i32,
    pub unit_price: Decimal,
    pub amount: Decimal,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct InvoiceSummary {
    pub id: Uuid,
    pub invoice_number: String,
    pub status: InvoiceStatus,
    pub amount: Decimal,
    pub currency: String,
    pub due_date: NaiveDate,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct OverdueInvoice {
    pub invoice: InvoiceSummary,
    pub overdue_days: i32,
    pub contact_email: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Subscription {
    pub id: Uuid,
    pub tenant_id: Uuid,
    pub plan_id: String,
    pub plan_name: String,
    pub status: SubscriptionStatus,
    pub seats: i32,
    pub mrr: Decimal,
    pub currency: String,
    pub current_period_start: DateTime<Utc>,
    pub current_period_end: DateTime<Utc>,
    pub cancel_at_period_end: bool,
    pub trial_end: Option<DateTime<Utc>>,
    pub features: Vec<String>,
    pub created_at: DateTime<Utc>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MrrDataPoint {
    pub date: NaiveDate,
    pub mrr: Decimal,
    pub new_mrr: Decimal,
    pub expansion_mrr: Decimal,
    pub churned_mrr: Decimal,
}
