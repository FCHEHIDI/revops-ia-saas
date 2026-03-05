mod audit;
mod config;
mod db;
mod errors;
mod rag_client;
mod schemas;
mod server;
mod storage;
mod tools;

use anyhow::{Context, Result};
use config::McpTransport;
use rmcp::transport::{SseServerTransport, StdioServerTransport};
use std::sync::Arc;
use tracing::info;
use tracing_subscriber::{fmt, EnvFilter};

use crate::config::Config;
use crate::db::create_pool;
use crate::rag_client::RagClient;
use crate::server::FilesystemServer;
use crate::storage::LocalStorage;

#[tokio::main]
async fn main() -> Result<()> {
    let cfg = Config::from_env().context("Failed to load configuration")?;

    let filter = EnvFilter::try_new(&cfg.log_level)
        .unwrap_or_else(|_| EnvFilter::new("info"));

    fmt()
        .with_env_filter(filter)
        .with_target(true)
        .init();

    info!(
        name = "mcp-filesystem",
        version = env!("CARGO_PKG_VERSION"),
        transport = ?cfg.transport,
        storage_backend = ?cfg.storage_backend,
        "Starting mcp-filesystem server"
    );

    let pool = create_pool(&cfg.database_url)
        .await
        .context("Failed to connect to PostgreSQL")?;

    info!("PostgreSQL connection pool established");

    let storage: Arc<dyn crate::storage::ObjectStorage> = Arc::new(
        LocalStorage::new(&cfg.storage_base_dir)
    );

    info!(base_dir = %cfg.storage_base_dir, "Local storage backend initialised");

    let rag_client = RagClient::new(cfg.rag_service_url.clone());

    info!(url = %cfg.rag_service_url, "RAG client initialised");

    let server = FilesystemServer::new(pool, storage, rag_client);

    match cfg.transport {
        McpTransport::Stdio => {
            info!("Using stdio transport");
            let transport = StdioServerTransport::new();
            rmcp::serve_server(server, transport)
                .await
                .context("mcp-filesystem server terminated with error")?;
        }
        McpTransport::Sse => {
            let bind_addr = std::env::var("SSE_BIND_ADDR")
                .unwrap_or_else(|_| "0.0.0.0:3005".to_string());
            info!(addr = %bind_addr, "Using SSE transport");
            let transport = SseServerTransport::new(&bind_addr)
                .context("Failed to bind SSE transport")?;
            rmcp::serve_server(server, transport)
                .await
                .context("mcp-filesystem server terminated with error")?;
        }
    }

    info!("mcp-filesystem server shut down");
    Ok(())
}
