use std::sync::Arc;

use anyhow::{Context, Result};
use orchestrator::{
    api,
    config::Config,
    queue::{DlqDispatcher, LowPriorityWorker, QueueDispatcher},
    AppState,
};
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
            EnvFilter::try_from_default_env().unwrap_or_else(|_| EnvFilter::new(&config.rust_log)),
        )
        .with(tracing_subscriber::fmt::layer().json())
        .init();

    info!(
        host = %config.server_host,
        port = config.server_port,
        model = %config.default_model,
        "Starting RevOps orchestrator"
    );

    // ── HTTP client (shared across all internal service calls) ───────────────
    let http_client = reqwest::Client::builder()
        .timeout(std::time::Duration::from_secs(120))
        .connect_timeout(std::time::Duration::from_secs(10))
        .build()
        .context("Failed to build HTTP client")?;

    // ── MCP client — short connect timeout so offline servers fail fast ───────
    let mcp_client = reqwest::Client::builder()
        .timeout(std::time::Duration::from_secs(30))
        .connect_timeout(std::time::Duration::from_millis(800))
        .build()
        .context("Failed to build MCP HTTP client")?;

    // ── Redis — fail fast if unavailable at startup ───────────────────────────
    //
    // `QueueDispatcher::connect()` creates and owns the primary Redis connection.
    // `queue_dispatcher.connection()` exposes a cheap Arc clone for DlqDispatcher.
    //
    // A *separate* ConnectionManager is created for the LOW priority worker so
    // its blocking XREADGROUP calls never compete with the producer path.
    info!(redis_url = %config.redis_url, "Connecting to Redis");

    // Primary connection: QueueDispatcher creates + initialises consumer groups
    let queue_dispatcher = QueueDispatcher::connect(&config.redis_url)
        .await
        .context("Failed to initialise Redis Streams — is Redis reachable?")?;

    // DlqDispatcher shares the producer's ConnectionManager (Arc clone)
    let dlq_dispatcher = DlqDispatcher::new(
        queue_dispatcher.connection(),
        http_client.clone(),
        config.backend_api_url.clone(),
        config.inter_service_secret.clone(),
    );

    // Dedicated connection for the LOW priority worker (blocking reads)
    let redis_client = redis::Client::open(config.redis_url.as_str())
        .context("Failed to create Redis client for worker")?;
    let worker_conn = redis::aio::ConnectionManager::new(redis_client)
        .await
        .context("Failed to connect to Redis for LOW priority worker")?;

    info!("Redis connections established");

    // ── AppState ──────────────────────────────────────────────────────────────
    let state = Arc::new(AppState {
        config: Arc::new(config.clone()),
        http_client,
        mcp_client,
        queue: Some(Arc::new(queue_dispatcher)),
        dlq: Some(Arc::new(dlq_dispatcher.clone())),
    });

    // ── Spawn LOW priority background worker ─────────────────────────────────
    let worker = LowPriorityWorker::new(worker_conn, Arc::clone(&state), Arc::new(dlq_dispatcher));
    tokio::spawn(async move {
        worker.run().await;
    });

    // ── HTTP server ───────────────────────────────────────────────────────────
    let app = api::router(state);

    let addr = format!("{}:{}", config.server_host, config.server_port);
    let listener = tokio::net::TcpListener::bind(&addr)
        .await
        .with_context(|| format!("Failed to bind to {}", addr))?;

    info!(addr = %addr, "Orchestrator ready");

    axum::serve(listener, app).await?;

    Ok(())
}
