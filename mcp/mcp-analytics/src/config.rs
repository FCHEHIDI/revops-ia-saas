use anyhow::{Context, Result};
use std::env;

#[derive(Debug, Clone)]
pub enum McpTransport {
    Stdio,
    Sse,
    Http,
}

impl McpTransport {
    fn from_str(s: &str) -> Self {
        match s.to_lowercase().as_str() {
            "sse" => McpTransport::Sse,
            "http" => McpTransport::Http,
            _ => McpTransport::Stdio,
        }
    }
}

#[derive(Debug, Clone)]
pub struct Config {
    pub database_url: String,
    pub transport: McpTransport,
    pub log_level: String,
    /// Bind address for HTTP transport (e.g. "0.0.0.0:19003")
    pub http_bind: String,
    /// Shared secret validated on incoming X-Internal-API-Key header
    pub inter_service_secret: String,
}

impl Config {
    pub fn from_env() -> Result<Self> {
        let database_url = env::var("DATABASE_URL")
            .context("DATABASE_URL environment variable is required")?;

        let transport = env::var("MCP_TRANSPORT")
            .unwrap_or_else(|_| "http".to_string());

        let log_level = env::var("LOG_LEVEL")
            .unwrap_or_else(|_| "info".to_string());

        let http_bind = env::var("HTTP_BIND")
            .unwrap_or_else(|_| "0.0.0.0:19003".to_string());

        let inter_service_secret = env::var("INTER_SERVICE_SECRET")
            .unwrap_or_else(|_| "dev-internal-key-change-me".to_string());

        Ok(Config {
            database_url,
            transport: McpTransport::from_str(&transport),
            log_level,
            http_bind,
            inter_service_secret,
        })
    }
}
