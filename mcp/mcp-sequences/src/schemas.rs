use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use sqlx::Type;
use uuid::Uuid;

// ---------------------------------------------------------------------------
// Enums
// ---------------------------------------------------------------------------

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize, Type)]
#[sqlx(type_name = "sequence_status", rename_all = "lowercase")]
#[serde(rename_all = "lowercase")]
pub enum SequenceStatus {
    Active,
    Paused,
    Draft,
    Archived,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize, Type)]
#[sqlx(type_name = "step_type", rename_all = "lowercase")]
#[serde(rename_all = "lowercase")]
pub enum StepType {
    Email,
    #[sqlx(rename = "linkedin_message")]
    #[serde(rename = "linkedin_message")]
    LinkedInMessage,
    Task,
    Call,
    Wait,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize, Type)]
#[sqlx(type_name = "exit_condition_type", rename_all = "lowercase")]
#[serde(rename_all = "lowercase")]
pub enum ExitConditionType {
    Replied,
    Clicked,
    #[sqlx(rename = "meeting_booked")]
    #[serde(rename = "meeting_booked")]
    MeetingBooked,
    #[sqlx(rename = "manual_unenroll")]
    #[serde(rename = "manual_unenroll")]
    ManualUnenroll,
    #[sqlx(rename = "deal_stage_changed")]
    #[serde(rename = "deal_stage_changed")]
    DealStageChanged,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize, Type)]
#[sqlx(type_name = "enrollment_status", rename_all = "lowercase")]
#[serde(rename_all = "lowercase")]
pub enum EnrollmentStatus {
    Pending,
    Active,
    Paused,
    Completed,
    Unenrolled,
    Failed,
}

// ---------------------------------------------------------------------------
// Core structs
// ---------------------------------------------------------------------------

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SequenceStep {
    pub id: Uuid,
    pub sequence_id: Uuid,
    pub position: i32,
    pub step_type: StepType,
    pub delay_days: i32,
    pub delay_hours: i32,
    pub template_id: Option<Uuid>,
    pub subject: Option<String>,
    pub body_template: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ExitCondition {
    pub condition_type: ExitConditionType,
    pub parameters: serde_json::Value,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Sequence {
    pub id: Uuid,
    pub tenant_id: Uuid,
    pub name: String,
    pub description: Option<String>,
    pub status: SequenceStatus,
    pub steps: Vec<SequenceStep>,
    pub exit_conditions: Vec<ExitCondition>,
    pub tags: Vec<String>,
    pub created_by: Uuid,
    pub created_at: DateTime<Utc>,
    pub updated_at: DateTime<Utc>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SequenceSummary {
    pub id: Uuid,
    pub name: String,
    pub status: SequenceStatus,
    pub steps_count: i64,
    pub active_enrollments: i64,
    pub total_enrolled: i64,
    pub created_at: DateTime<Utc>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Enrollment {
    pub id: Uuid,
    pub tenant_id: Uuid,
    pub sequence_id: Uuid,
    pub contact_id: Uuid,
    pub status: EnrollmentStatus,
    pub current_step: i32,
    pub custom_variables: serde_json::Value,
    pub enrolled_at: DateTime<Utc>,
    pub next_step_at: Option<DateTime<Utc>>,
    pub completed_at: Option<DateTime<Utc>>,
    pub unenroll_reason: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct EnrollmentSummary {
    pub id: Uuid,
    pub contact_id: Uuid,
    pub status: EnrollmentStatus,
    pub current_step: i32,
    pub enrolled_at: DateTime<Utc>,
    pub next_step_at: Option<DateTime<Utc>>,
}

// ---------------------------------------------------------------------------
// Input helpers
// ---------------------------------------------------------------------------

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SequenceStepInput {
    pub step_type: StepType,
    pub delay_days: i32,
    pub delay_hours: i32,
    pub template_id: Option<Uuid>,
    pub subject: Option<String>,
    pub body_template: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ExitConditionInput {
    pub condition_type: ExitConditionType,
    pub parameters: Option<serde_json::Value>,
}
