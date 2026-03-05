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
pub enum StorageBackend {
    Local,
    S3,
}

impl StorageBackend {
    fn from_str(s: &str) -> Self {
        match s.to_lowercase().as_str() {
            "s3" => StorageBackend::S3,
            _ => StorageBackend::Local,
        }
    }
}

#[derive(Debug, Clone)]
pub struct Config {
    pub database_url: String,
    pub transport: McpTransport,
    pub storage_backend: StorageBackend,
    pub storage_base_dir: String,
    pub rag_service_url: String,
    pub log_level: String,
}

impl Config {
    pub fn from_env() -> Result<Self> {
        let database_url = env::var("DATABASE_URL")
            .context("DATABASE_URL environment variable is required")?;

        let transport = env::var("MCP_TRANSPORT")
            .unwrap_or_else(|_| "stdio".to_string());

        let storage_backend = env::var("STORAGE_BACKEND")
            .unwrap_or_else(|_| "local".to_string());

        let storage_base_dir = env::var("STORAGE_BASE_DIR")
            .unwrap_or_else(|_| "/data/storage".to_string());

        let rag_service_url = env::var("RAG_SERVICE_URL")
            .unwrap_or_else(|_| "http://rag-service:8000".to_string());

        let log_level = env::var("LOG_LEVEL")
            .unwrap_or_else(|_| "info".to_string());

        Ok(Config {
            database_url,
            transport: McpTransport::from_str(&transport),
            storage_backend: StorageBackend::from_str(&storage_backend),
            storage_base_dir,
            rag_service_url,
            log_level,
        })
    }
}
