use anyhow::{Context, Result};
use std::env;

#[derive(Debug, Clone)]
pub enum McpTransport {
    Stdio,
    Sse,
}

impl McpTransport {
    fn from_str(s: &str) -> Self {
        match s.to_lowercase().as_str() {
            "sse" => McpTransport::Sse,
            _ => McpTransport::Stdio,
        }
    }
}

#[derive(Debug, Clone)]
pub struct Config {
    pub database_url: String,
    pub transport: McpTransport,
    pub log_level: String,
}

impl Config {
    pub fn from_env() -> Result<Self> {
        let database_url = env::var("DATABASE_URL")
            .context("DATABASE_URL environment variable is required")?;

        let transport = env::var("MCP_TRANSPORT")
            .unwrap_or_else(|_| "stdio".to_string());

        let log_level = env::var("LOG_LEVEL")
            .unwrap_or_else(|_| "info".to_string());

        Ok(Config {
            database_url,
            transport: McpTransport::from_str(&transport),
            log_level,
        })
    }
}
