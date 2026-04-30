mod audit;
mod config;
mod db;
mod errors;
mod http;
mod rag_client;
mod schemas;
mod server;
mod storage;
mod tools;

use anyhow::{Context, Result};
use config::McpTransport;
use std::sync::Arc;
use tracing::info;
use tracing_subscriber::{fmt, EnvFilter};

use crate::config::Config;
use crate::db::create_pool;
use crate::http::HttpState;
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

    let rag_client = RagClient::new(cfg.rag_service_url.clone(), cfg.inter_service_secret.clone());

    info!(url = %cfg.rag_service_url, "RAG client initialised");

    match cfg.transport {
        McpTransport::Http => {
            let state = HttpState {
                pool: Arc::new(pool),
                storage,
                rag_client,
                inter_service_secret: cfg.inter_service_secret.clone(),
            };
            let app = http::router(state);
            let listener = tokio::net::TcpListener::bind(&cfg.http_bind)
                .await
                .with_context(|| format!("Failed to bind HTTP server to {}", cfg.http_bind))?;
            info!(addr = %cfg.http_bind, "mcp-filesystem HTTP server listening");
            axum::serve(listener, app)
                .await
                .context("mcp-filesystem HTTP server terminated with error")?;
        }
        McpTransport::Stdio => {
            info!("Using stdio transport");
            let server = FilesystemServer::new(pool, storage, rag_client);
            let transport = rmcp::transport::stdio();
            rmcp::serve_server(server, transport)
                .await
                .context("mcp-filesystem server terminated with error")?;
        }
        McpTransport::Sse => {
            let bind_addr = std::env::var("SSE_BIND_ADDR")
                .unwrap_or_else(|_| "0.0.0.0:3005".to_string());
            info!(addr = %bind_addr, "Using SSE transport");
            let bind: std::net::SocketAddr = bind_addr
                .parse()
                .context("Invalid SSE_BIND_ADDR")?;
            let mut sse = rmcp::transport::sse_server::SseServer::serve(bind)
                .await
                .context("Failed to bind SSE transport")?;
            while let Some(transport) = sse.next_transport().await {
                let server = FilesystemServer::new(pool.clone(), storage.clone(), rag_client.clone());
                tokio::spawn(async move {
                    if let Err(e) = rmcp::serve_server(server, transport).await {
                        tracing::error!("SSE session error: {e}");
                    }
                });
            }
        }
    }

    info!("mcp-filesystem server shut down");
    Ok(())
}
