use std::sync::Arc;

use anyhow::{Context, Result};
use opentelemetry::trace::TracerProvider as OtelTracerProvider;
use opentelemetry_otlp::WithExportConfig;
// In SDK 0.26 the concrete struct is `TracerProvider` (no `Sdk` prefix)
use opentelemetry_sdk::trace::TracerProvider as SdkTracerProvider;
use orchestrator::{
    api,
    config::Config,
    queue::{DlqDispatcher, LowPriorityWorker, QueueDispatcher},
    AppState,
};
use tracing::info;
use tracing_opentelemetry::OpenTelemetryLayer;
use tracing_subscriber::{layer::SubscriberExt, util::SubscriberInitExt, EnvFilter};

/// Initialise the OTLP tracer and return the provider so it can be shut down
/// gracefully. Called only when `OTEL_EXPORTER_OTLP_ENDPOINT` is set.
fn init_tracer(endpoint: &str) -> Result<SdkTracerProvider> {
    let exporter = opentelemetry_otlp::new_exporter()
        .tonic()
        .with_endpoint(endpoint)
        .build_span_exporter()
        .context("Failed to build OTLP span exporter")?;

    let provider = SdkTracerProvider::builder()
        .with_batch_exporter(exporter, opentelemetry_sdk::runtime::Tokio)
        .with_config(
            opentelemetry_sdk::trace::Config::default().with_resource(
                opentelemetry_sdk::Resource::new(vec![
                    opentelemetry::KeyValue::new(
                        opentelemetry_semantic_conventions::resource::SERVICE_NAME,
                        "revops-orchestrator",
                    ),
                    opentelemetry::KeyValue::new(
                        opentelemetry_semantic_conventions::resource::SERVICE_VERSION,
                        env!("CARGO_PKG_VERSION"),
                    ),
                ]),
            ),
        )
        .build();

    Ok(provider)
}

#[tokio::main]
async fn main() -> Result<()> {
    // Load .env if present (no-op in production where env vars are injected)
    dotenvy::dotenv().ok();

    let config = Config::from_env()?;

    // ── Observability: tracing-subscriber + optional OTEL layer ──────────────
    //
    // When OTEL_EXPORTER_OTLP_ENDPOINT is set we add a tracing-opentelemetry
    // layer that bridges `#[instrument]` spans to the OTLP collector.
    // Without it we fall back to JSON stdout only (no-op for tests / local dev).
    let tracer_provider: Option<SdkTracerProvider> = match &config.otel_exporter_otlp_endpoint {
        Some(endpoint) => match init_tracer(endpoint) {
            Ok(provider) => {
                eprintln!(
                    "[otel] OTLP traces enabled → {}",
                    endpoint
                );
                Some(provider)
            }
            Err(e) => {
                eprintln!("[otel] Failed to init tracer, falling back to logs only: {e}");
                None
            }
        },
        None => None,
    };

    let env_filter =
        EnvFilter::try_from_default_env().unwrap_or_else(|_| EnvFilter::new(&config.rust_log));

    let registry = tracing_subscriber::registry()
        .with(env_filter)
        .with(tracing_subscriber::fmt::layer().json());

    if let Some(ref provider) = tracer_provider {
        // UFCS removes ambiguity between trait method and any direct impl method
        let tracer = OtelTracerProvider::tracer(provider, "revops-orchestrator");
        let otel_layer = OpenTelemetryLayer::new(tracer);
        registry.with(otel_layer).init();
    } else {
        registry.init();
    }

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

    // Flush and shutdown OTEL tracer so in-flight spans are exported before exit
    if let Some(provider) = tracer_provider {
        if let Err(e) = provider.shutdown() {
            eprintln!("[otel] tracer shutdown error: {e}");
        }
    }

    Ok(())
}
