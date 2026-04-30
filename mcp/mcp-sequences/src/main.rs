mod audit;
mod config;
mod db;
mod errors;
mod http;
mod schemas;
mod server;
mod tools;

use anyhow::{Context, Result};
use config::McpTransport;
use std::sync::Arc;
use tracing::info;
use tracing_subscriber::{fmt, EnvFilter};

use crate::config::Config;
use crate::db::create_pool;
use crate::http::HttpState;
use crate::server::SequencesServer;

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
        name = "mcp-sequences",
        version = env!("CARGO_PKG_VERSION"),
        transport = ?cfg.transport,
        "Starting mcp-sequences server"
    );

    let pool = create_pool(&cfg.database_url)
        .await
        .context("Failed to connect to PostgreSQL")?;

    info!("PostgreSQL connection pool established");

    match cfg.transport {
        McpTransport::Http => {
            let state = HttpState {
                pool: Arc::new(pool),
                inter_service_secret: cfg.inter_service_secret.clone(),
            };
            let app = http::router(state);
            let listener = tokio::net::TcpListener::bind(&cfg.http_bind)
                .await
                .with_context(|| format!("Failed to bind HTTP server to {}", cfg.http_bind))?;
            info!(addr = %cfg.http_bind, "mcp-sequences HTTP server listening");
            axum::serve(listener, app)
                .await
                .context("mcp-sequences HTTP server terminated with error")?;
        }
        McpTransport::Stdio => {
            info!("Using stdio transport");
            let server = SequencesServer::new(pool);
            let transport = rmcp::transport::stdio();
            rmcp::serve_server(server, transport)
                .await
                .context("mcp-sequences server terminated with error")?;
        }
        McpTransport::Sse => {
            let bind_addr = std::env::var("SSE_BIND_ADDR")
                .unwrap_or_else(|_| "0.0.0.0:3004".to_string());
            info!(addr = %bind_addr, "Using SSE transport");
            let server = SequencesServer::new(pool);
            let bind: std::net::SocketAddr = bind_addr
                .parse()
                .context("Invalid SSE_BIND_ADDR")?;
            let mut sse = rmcp::transport::sse_server::SseServer::serve(bind)
                .await
                .context("Failed to bind SSE transport")?;
            while let Some(transport) = sse.next_transport().await {
                let s = server.clone();
                tokio::spawn(async move {
                    if let Err(e) = rmcp::serve_server(s, transport).await {
                        tracing::error!("SSE session error: {e}");
                    }
                });
            }
        }
    }

    info!("mcp-sequences server shut down");
    Ok(())
}
