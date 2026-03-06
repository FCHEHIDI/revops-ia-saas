use std::sync::Arc;

use anyhow::Result;
use orchestrator::{api, config::Config, AppState};
use tracing::info;
use tracing_subscriber::{layer::SubscriberExt, util::SubscriberInitExt, EnvFilter};

#[tokio::main]
async fn main() -> Result<()> {
    // Load .env if present (no-op in production where env vars are injected)
    dotenvy::dotenv().ok();

    let config = Config::from_env()?;

    // Structured JSON logging — parseable by Grafana Loki
    tracing_subscriber::registry()
        .with(
            EnvFilter::try_from_default_env()
                .unwrap_or_else(|_| EnvFilter::new(&config.rust_log)),
        )
        .with(tracing_subscriber::fmt::layer().json())
        .init();

    info!(
        host = %config.server_host,
        port = config.server_port,
        model = %config.default_model,
        "Starting RevOps orchestrator"
    );

    let http_client = reqwest::Client::builder()
        .timeout(std::time::Duration::from_secs(120))
        .connect_timeout(std::time::Duration::from_secs(10))
        .build()?;

    let state = Arc::new(AppState {
        config: Arc::new(config.clone()),
        http_client,
    });

    let app = api::router(state);

    let addr = format!("{}:{}", config.server_host, config.server_port);
    let listener = tokio::net::TcpListener::bind(&addr).await?;

    info!(addr = %addr, "Orchestrator ready");

    axum::serve(listener, app).await?;

    Ok(())
}
