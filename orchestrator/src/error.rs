use axum::{
    http::StatusCode,
    response::{IntoResponse, Response},
    Json,
};
use serde_json::json;
use thiserror::Error;

#[derive(Debug, Error)]
pub enum AppError {
    #[error("Unauthorized: invalid or missing X-Internal-API-Key")]
    Unauthorized,

    #[error("Bad request: {0}")]
    BadRequest(String),

    #[error("LLM provider error: {0}")]
    LlmError(String),

    #[error("MCP server error [{server}]: {message}")]
    McpError { server: String, message: String },

    #[error("RAG service error: {0}")]
    RagError(String),

    #[error("Context build error: {0}")]
    ContextError(String),

    #[error("Backend API error: {0}")]
    BackendError(String),

    #[error("Configuration error: {0}")]
    ConfigError(String),

    #[error("Tenant validation failed: {0}")]
    TenantError(String),

    #[error("Queue error [{queue}]: {message}")]
    QueueError { queue: String, message: String },

    #[error("DLQ archive error: {0}")]
    DlqError(String),

    #[error("Internal error: {0}")]
    Internal(#[from] anyhow::Error),
}

impl IntoResponse for AppError {
    fn into_response(self) -> Response {
        let (status, code) = match &self {
            AppError::Unauthorized => (StatusCode::UNAUTHORIZED, "UNAUTHORIZED"),
            AppError::BadRequest(_) => (StatusCode::BAD_REQUEST, "BAD_REQUEST"),
            AppError::TenantError(_) => (StatusCode::BAD_REQUEST, "TENANT_ERROR"),
            AppError::ConfigError(_) => (StatusCode::INTERNAL_SERVER_ERROR, "CONFIG_ERROR"),
            AppError::LlmError(_) => (StatusCode::BAD_GATEWAY, "LLM_ERROR"),
            AppError::McpError { .. } => (StatusCode::BAD_GATEWAY, "MCP_ERROR"),
            AppError::RagError(_) => (StatusCode::BAD_GATEWAY, "RAG_ERROR"),
            AppError::QueueError { .. } => (StatusCode::SERVICE_UNAVAILABLE, "QUEUE_ERROR"),
            AppError::DlqError(_) => (StatusCode::INTERNAL_SERVER_ERROR, "DLQ_ERROR"),
            AppError::ContextError(_) | AppError::BackendError(_) | AppError::Internal(_) => {
                (StatusCode::INTERNAL_SERVER_ERROR, "INTERNAL_ERROR")
            }
        };

        let body = json!({
            "error": {
                "code": code,
                "message": self.to_string(),
            }
        });

        (status, Json(body)).into_response()
    }
}
