use chrono::{DateTime, NaiveDate, Utc};
use serde::{Deserialize, Serialize};
use uuid::Uuid;

// ---------------------------------------------------------------------------
// DocumentType
// ---------------------------------------------------------------------------

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize, sqlx::Type)]
#[sqlx(type_name = "document_type", rename_all = "snake_case")]
#[serde(rename_all = "snake_case")]
pub enum DocumentType {
    Playbook,
    Report,
    Contract,
    Proposal,
    Presentation,
    Datasheet,
    Internal,
    Other,
}

impl DocumentType {
    pub fn as_str(&self) -> &'static str {
        match self {
            DocumentType::Playbook => "playbook",
            DocumentType::Report => "report",
            DocumentType::Contract => "contract",
            DocumentType::Proposal => "proposal",
            DocumentType::Presentation => "presentation",
            DocumentType::Datasheet => "datasheet",
            DocumentType::Internal => "internal",
            DocumentType::Other => "other",
        }
    }
}

// ---------------------------------------------------------------------------
// PlaybookCategory
// ---------------------------------------------------------------------------

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize, sqlx::Type)]
#[sqlx(type_name = "playbook_category", rename_all = "snake_case")]
#[serde(rename_all = "snake_case")]
pub enum PlaybookCategory {
    SalesProcess,
    ObjectionHandling,
    BattleCard,
    Onboarding,
    CompetitiveAnalysis,
    PricingGuide,
}

// ---------------------------------------------------------------------------
// ReportType
// ---------------------------------------------------------------------------

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize, sqlx::Type)]
#[sqlx(type_name = "report_type", rename_all = "snake_case")]
#[serde(rename_all = "snake_case")]
pub enum ReportType {
    PipelineAnalysis,
    ChurnReport,
    ForecastReport,
    PerformanceReport,
    CustomReport,
}

// ---------------------------------------------------------------------------
// DocumentMetadata — storage_path intentionally excluded from this struct
// ---------------------------------------------------------------------------

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DocumentMetadata {
    pub id: Uuid,
    pub tenant_id: Uuid,
    pub filename: String,
    pub document_type: DocumentType,
    pub mime_type: String,
    pub size_bytes: i64,
    pub tags: Vec<String>,
    pub rag_indexed: bool,
    pub rag_indexed_at: Option<DateTime<Utc>>,
    pub uploaded_by: Uuid,
    pub created_at: DateTime<Utc>,
    pub updated_at: DateTime<Utc>,
}

// ---------------------------------------------------------------------------
// Playbook
// ---------------------------------------------------------------------------

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Playbook {
    pub id: Uuid,
    pub tenant_id: Uuid,
    pub title: String,
    pub description: Option<String>,
    pub category: PlaybookCategory,
    pub content: String,
    pub tags: Vec<String>,
    pub version: String,
    pub is_active: bool,
    pub created_by: Uuid,
    pub created_at: DateTime<Utc>,
    pub updated_at: DateTime<Utc>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PlaybookSummary {
    pub id: Uuid,
    pub title: String,
    pub category: PlaybookCategory,
    pub description: Option<String>,
    pub tags: Vec<String>,
    pub version: String,
}

// ---------------------------------------------------------------------------
// DocumentChunk (RAG search result)
// ---------------------------------------------------------------------------

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DocumentChunk {
    pub document_id: Uuid,
    pub filename: String,
    pub chunk_index: i32,
    pub content: String,
    pub similarity_score: f32,
    pub document_type: String,
    pub page_number: Option<i32>,
}

// ---------------------------------------------------------------------------
// Pagination helpers
// ---------------------------------------------------------------------------

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ListInput {
    pub limit: Option<u32>,
    pub offset: Option<u32>,
}

impl ListInput {
    pub fn limit(&self) -> i64 {
        self.limit.unwrap_or(50).min(200) as i64
    }

    pub fn offset(&self) -> i64 {
        self.offset.unwrap_or(0) as i64
    }
}

// ---------------------------------------------------------------------------
// Accepted MIME types for uploads
// ---------------------------------------------------------------------------

pub const ACCEPTED_MIME_TYPES: &[&str] = &[
    "text/plain",
    "text/markdown",
    "application/json",
    "text/html",
];

pub const MAX_UPLOAD_CHARS: usize = 5_000_000;
pub const DEFAULT_MAX_CHARS: usize = 10_000;
pub const MAX_READ_CHARS: usize = 50_000;
pub const DEFAULT_TOP_K: u32 = 5;
pub const MAX_TOP_K: u32 = 20;
pub const DEFAULT_MIN_SCORE: f32 = 0.5;
