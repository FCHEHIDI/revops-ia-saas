use chrono::{DateTime, NaiveDate, Utc};
use rust_decimal::Decimal;
use serde::{Deserialize, Serialize};
use uuid::Uuid;

// ---------------------------------------------------------------------------
// Enums
// ---------------------------------------------------------------------------

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq, sqlx::Type)]
#[sqlx(type_name = "contact_status", rename_all = "snake_case")]
#[serde(rename_all = "snake_case")]
pub enum ContactStatus {
    Active,
    Inactive,
    Prospect,
    Customer,
    Churned,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq, sqlx::Type)]
#[sqlx(type_name = "deal_stage", rename_all = "snake_case")]
#[serde(rename_all = "snake_case")]
pub enum DealStage {
    Prospecting,
    Qualification,
    Proposal,
    Negotiation,
    ClosedWon,
    ClosedLost,
}

impl DealStage {
    pub fn valid_transitions(&self) -> &[DealStage] {
        match self {
            DealStage::Prospecting => &[DealStage::Qualification, DealStage::ClosedLost],
            DealStage::Qualification => &[DealStage::Proposal, DealStage::ClosedLost],
            DealStage::Proposal => &[DealStage::Negotiation, DealStage::ClosedLost],
            DealStage::Negotiation => &[DealStage::ClosedWon, DealStage::ClosedLost],
            DealStage::ClosedWon => &[],
            DealStage::ClosedLost => &[DealStage::Prospecting],
        }
    }

    pub fn can_transition_to(&self, target: &DealStage) -> bool {
        self.valid_transitions().contains(target)
    }

    pub fn as_str(&self) -> &'static str {
        match self {
            DealStage::Prospecting => "prospecting",
            DealStage::Qualification => "qualification",
            DealStage::Proposal => "proposal",
            DealStage::Negotiation => "negotiation",
            DealStage::ClosedWon => "closed_won",
            DealStage::ClosedLost => "closed_lost",
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq, sqlx::Type)]
#[sqlx(type_name = "activity_type", rename_all = "snake_case")]
#[serde(rename_all = "snake_case")]
pub enum ActivityType {
    Call,
    Email,
    Meeting,
    Note,
    Task,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq, sqlx::Type)]
#[sqlx(type_name = "entity_type", rename_all = "snake_case")]
#[serde(rename_all = "snake_case")]
pub enum EntityType {
    Contact,
    Deal,
    Account,
}

// ---------------------------------------------------------------------------
// Core entities
// ---------------------------------------------------------------------------

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Contact {
    pub id: Uuid,
    pub tenant_id: Uuid,
    pub first_name: String,
    pub last_name: String,
    pub email: String,
    pub phone: Option<String>,
    pub title: Option<String>,
    pub account_id: Option<Uuid>,
    pub status: ContactStatus,
    pub custom_fields: serde_json::Value,
    pub created_at: DateTime<Utc>,
    pub updated_at: DateTime<Utc>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Account {
    pub id: Uuid,
    pub tenant_id: Uuid,
    pub name: String,
    pub domain: Option<String>,
    pub industry: Option<String>,
    pub employee_count: Option<i32>,
    pub annual_revenue: Option<Decimal>,
    pub custom_fields: serde_json::Value,
    pub created_at: DateTime<Utc>,
    pub updated_at: DateTime<Utc>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Deal {
    pub id: Uuid,
    pub tenant_id: Uuid,
    pub name: String,
    pub account_id: Uuid,
    pub value: Decimal,
    pub currency: String,
    pub stage: DealStage,
    pub probability: f32,
    pub close_date: NaiveDate,
    pub assigned_to: Option<Uuid>,
    pub custom_fields: serde_json::Value,
    pub created_at: DateTime<Utc>,
    pub updated_at: DateTime<Utc>,
    pub closed_at: Option<DateTime<Utc>>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Activity {
    pub id: Uuid,
    pub tenant_id: Uuid,
    pub entity_type: EntityType,
    pub entity_id: Uuid,
    pub activity_type: ActivityType,
    pub subject: String,
    pub notes: Option<String>,
    pub duration_minutes: Option<i32>,
    pub performed_by: Uuid,
    pub occurred_at: DateTime<Utc>,
}

// ---------------------------------------------------------------------------
// Summary structs (used in list responses)
// ---------------------------------------------------------------------------

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ContactSummary {
    pub id: Uuid,
    pub first_name: String,
    pub last_name: String,
    pub email: String,
    pub status: ContactStatus,
    pub account_id: Option<Uuid>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AccountSummary {
    pub id: Uuid,
    pub name: String,
    pub domain: Option<String>,
    pub industry: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DealSummary {
    pub id: Uuid,
    pub name: String,
    pub account_id: Uuid,
    pub value: Decimal,
    pub currency: String,
    pub stage: DealStage,
    pub close_date: NaiveDate,
    pub assigned_to: Option<Uuid>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PipelineStageStats {
    pub stage: DealStage,
    pub deal_count: i64,
    pub total_value: Decimal,
    pub avg_value: Decimal,
    pub avg_age_days: f64,
}

// ---------------------------------------------------------------------------
// Pagination
// ---------------------------------------------------------------------------

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PaginationInput {
    #[serde(default = "default_page")]
    pub page: i64,
    #[serde(default = "default_page_size")]
    pub page_size: i64,
}

fn default_page() -> i64 {
    1
}

fn default_page_size() -> i64 {
    20
}

impl PaginationInput {
    pub fn offset(&self) -> i64 {
        (self.page.max(1) - 1) * self.page_size.min(100).max(1)
    }

    pub fn limit(&self) -> i64 {
        self.page_size.min(100).max(1)
    }
}
