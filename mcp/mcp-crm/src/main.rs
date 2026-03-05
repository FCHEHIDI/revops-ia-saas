mod audit;
mod config;
mod db;
mod errors;
mod schemas;
mod server;
mod tools;

use anyhow::{Context, Result};
use config::McpTransport;
use rmcp::transport::{SseServerTransport, StdioServerTransport};
use tracing::info;
use tracing_subscriber::{fmt, EnvFilter};

use crate::config::Config;
use crate::db::create_pool;
use crate::server::CrmServer;

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
        name = "mcp-crm",
        version = env!("CARGO_PKG_VERSION"),
        transport = ?cfg.transport,
        "Starting mcp-crm server"
    );

    let pool = create_pool(&cfg.database_url)
        .await
        .context("Failed to connect to PostgreSQL")?;

    info!("PostgreSQL connection pool established");

    let server = CrmServer::new(pool);

    match cfg.transport {
        McpTransport::Stdio => {
            info!("Using stdio transport");
            let transport = StdioServerTransport::new();
            rmcp::serve_server(server, transport)
                .await
                .context("mcp-crm server terminated with error")?;
        }
        McpTransport::Sse => {
            let bind_addr = std::env::var("SSE_BIND_ADDR")
                .unwrap_or_else(|_| "0.0.0.0:3001".to_string());
            info!(addr = %bind_addr, "Using SSE transport");
            let transport = SseServerTransport::new(&bind_addr)
                .context("Failed to bind SSE transport")?;
            rmcp::serve_server(server, transport)
                .await
                .context("mcp-crm server terminated with error")?;
        }
    }

    info!("mcp-crm server shut down");
    Ok(())
}
