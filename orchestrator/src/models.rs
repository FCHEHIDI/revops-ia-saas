use serde::{Deserialize, Serialize};
use uuid::Uuid;

// ---------------------------------------------------------------------------
// API Request / Response
// ---------------------------------------------------------------------------

#[derive(Debug, Clone, Deserialize)]
pub struct ProcessRequest {
    pub tenant_id: Uuid,
    pub conversation_id: Uuid,
    pub message: String,
    pub user_id: Uuid,
    #[serde(default)]
    pub priority: Priority,
}

#[derive(Debug, Clone, Deserialize, Serialize, PartialEq, Eq, Default)]
#[serde(rename_all = "SCREAMING_SNAKE_CASE")]
pub enum Priority {
    High,
    #[default]
    Normal,
    Low,
}

// ---------------------------------------------------------------------------
// SSE Event payloads — streamed back to the backend
// ---------------------------------------------------------------------------

#[derive(Debug, Clone, Serialize)]
#[serde(tag = "type", rename_all = "snake_case")]
pub enum SseEventPayload {
    Token {
        content: String,
    },
    ToolCall {
        tool: String,
        result: serde_json::Value,
    },
    Done {
        usage: UsageStats,
    },
    /// Emitted for LOW priority jobs — the request has been accepted and queued.
    /// The backend should poll `GET /internal/jobs/{job_id}` for the result.
    Accepted {
        job_id: uuid::Uuid,
        queue: String,
    },
    Error {
        message: String,
    },
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct UsageStats {
    pub prompt_tokens: u32,
    pub completion_tokens: u32,
    pub total_tokens: u32,
}

// ---------------------------------------------------------------------------
// LLM message types — shared across OpenAI and Anthropic adapters
// ---------------------------------------------------------------------------

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Message {
    pub role: Role,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub content: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub tool_calls: Option<Vec<ToolCall>>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub tool_call_id: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub name: Option<String>,
}

impl Message {
    pub fn system(content: impl Into<String>) -> Self {
        Self {
            role: Role::System,
            content: Some(content.into()),
            tool_calls: None,
            tool_call_id: None,
            name: None,
        }
    }

    pub fn user(content: impl Into<String>) -> Self {
        Self {
            role: Role::User,
            content: Some(content.into()),
            tool_calls: None,
            tool_call_id: None,
            name: None,
        }
    }

    pub fn tool_result(tool_call_id: impl Into<String>, content: impl Into<String>) -> Self {
        Self {
            role: Role::Tool,
            content: Some(content.into()),
            tool_calls: None,
            tool_call_id: Some(tool_call_id.into()),
            name: None,
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "lowercase")]
pub enum Role {
    System,
    User,
    Assistant,
    Tool,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ToolCall {
    pub id: String,
    #[serde(rename = "type")]
    pub call_type: String,
    pub function: FunctionCall,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FunctionCall {
    pub name: String,
    pub arguments: String,
}

// ---------------------------------------------------------------------------
// Tool definitions — sent to the LLM to describe available MCP tools
// ---------------------------------------------------------------------------

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Tool {
    #[serde(rename = "type")]
    pub tool_type: String,
    pub function: ToolFunction,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ToolFunction {
    pub name: String,
    pub description: String,
    pub parameters: serde_json::Value,
}

// ---------------------------------------------------------------------------
// LLM provider output
// ---------------------------------------------------------------------------

#[derive(Debug, Clone)]
pub struct LlmResponse {
    pub content: Option<String>,
    pub tool_calls: Vec<ToolCall>,
    pub finish_reason: FinishReason,
    pub usage: UsageStats,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum FinishReason {
    Stop,
    ToolCalls,
    Length,
    Other,
}

// ---------------------------------------------------------------------------
// RAG retrieval types — mirrors rag/app/models/schemas.py
// ---------------------------------------------------------------------------

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RagChunk {
    pub document_id: Uuid,
    pub filename: String,
    pub chunk_index: u32,
    pub content: String,
    pub similarity_score: f32,
    pub document_type: String,
    /// CRM-specific metadata injected by the RAG CRM worker.
    ///
    /// Present when `document_type` is `"crm"`. Contains fields such as
    /// `entity_type`, `entity_name`, `account_name`, `deal_stage`, `deal_id`,
    /// `account_id`, `contact_id`, etc.
    #[serde(default)]
    pub crm_metadata: Option<serde_json::Value>,
}

// ---------------------------------------------------------------------------
// MCP HTTP call types — POST /mcp/call on each MCP server
// ---------------------------------------------------------------------------

#[derive(Debug, Clone, Serialize)]
pub struct McpCallRequest {
    pub tool: String,
    pub params: serde_json::Value,
    pub tenant_id: String,
}

#[derive(Debug, Clone, Deserialize)]
pub struct McpCallResponse {
    pub result: Option<serde_json::Value>,
    pub error: Option<String>,
}

// ---------------------------------------------------------------------------
// Backend conversation history — GET /internal/conversations/{id}/messages
// ---------------------------------------------------------------------------

#[derive(Debug, Clone, Deserialize)]
pub struct ConversationMessage {
    pub role: String,
    pub content: String,
    #[serde(default)]
    pub tool_call_id: Option<String>,
    #[serde(default)]
    pub tool_calls: Option<serde_json::Value>,
}
