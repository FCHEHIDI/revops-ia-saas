use anyhow::{Context, Result};
use std::env;

/// Global configuration loaded from environment variables at startup.
///
/// All fields with sensible defaults fall back gracefully. Only
/// `INTER_SERVICE_SECRET` is strictly required.
#[derive(Debug, Clone)]
pub struct Config {
    pub server_host: String,
    pub server_port: u16,

    /// Shared secret between the backend and the orchestrator.
    /// Validated on every request via `X-Internal-API-Key`.
    pub inter_service_secret: String,

    // Internal service URLs
    pub backend_api_url: String,
    pub rag_api_url: String,
    pub mcp_crm_url: String,
    pub mcp_billing_url: String,
    pub mcp_analytics_url: String,
    pub mcp_sequences_url: String,
    pub mcp_filesystem_url: String,

    pub redis_url: String,

    // LLM provider credentials
    pub openai_api_key: Option<String>,
    pub anthropic_api_key: Option<String>,

    /// Default LLM model name. Provider is inferred from the prefix:
    /// `gpt-*` → OpenAI, `claude-*` → Anthropic.
    pub default_model: String,

    pub otel_exporter_otlp_endpoint: Option<String>,
    pub rust_log: String,
}

impl Config {
    pub fn from_env() -> Result<Self> {
        Ok(Config {
            server_host: env::var("SERVER_HOST").unwrap_or_else(|_| "0.0.0.0".to_string()),
            server_port: env::var("SERVER_PORT")
                .unwrap_or_else(|_| "8001".to_string())
                .parse()
                .context("SERVER_PORT must be a valid u16")?,

            inter_service_secret: env::var("INTER_SERVICE_SECRET")
                .context("INTER_SERVICE_SECRET is required")?,

            backend_api_url: env::var("BACKEND_API_URL")
                .unwrap_or_else(|_| "http://backend:8000".to_string()),
            rag_api_url: env::var("RAG_API_URL")
                .unwrap_or_else(|_| "http://rag:8002".to_string()),
            mcp_crm_url: env::var("MCP_CRM_URL")
                .unwrap_or_else(|_| "http://mcp-crm:9001".to_string()),
            mcp_billing_url: env::var("MCP_BILLING_URL")
                .unwrap_or_else(|_| "http://mcp-billing:9002".to_string()),
            mcp_analytics_url: env::var("MCP_ANALYTICS_URL")
                .unwrap_or_else(|_| "http://mcp-analytics:9003".to_string()),
            mcp_sequences_url: env::var("MCP_SEQUENCES_URL")
                .unwrap_or_else(|_| "http://mcp-sequences:9004".to_string()),
            mcp_filesystem_url: env::var("MCP_FILESYSTEM_URL")
                .unwrap_or_else(|_| "http://mcp-filesystem:9005".to_string()),

            redis_url: env::var("REDIS_URL")
                .unwrap_or_else(|_| "redis://redis:6379".to_string()),

            openai_api_key: env::var("OPENAI_API_KEY").ok(),
            anthropic_api_key: env::var("ANTHROPIC_API_KEY").ok(),
            default_model: env::var("DEFAULT_MODEL")
                .unwrap_or_else(|_| "gpt-4o".to_string()),

            otel_exporter_otlp_endpoint: env::var("OTEL_EXPORTER_OTLP_ENDPOINT").ok(),
            rust_log: env::var("RUST_LOG").unwrap_or_else(|_| "info".to_string()),
        })
    }

    /// Returns the provider inferred from the model name.
    pub fn provider_for_model(model: &str) -> &'static str {
        if model.starts_with("gpt-") || model.starts_with("o1") || model.starts_with("o3") {
            "openai"
        } else if model.starts_with("claude-") {
            "anthropic"
        } else {
            "openai"
        }
    }
}
