pub mod api;
pub mod config;
pub mod context;
pub mod error;
pub mod llm_client;
pub mod mcp_client;
pub mod models;
pub mod queue;
pub mod rag_client;
pub mod routing;

use std::sync::Arc;

use config::Config;
use queue::{DlqDispatcher, QueueDispatcher};

/// Shared application state — cloned into every Axum handler via `Arc`.
///
/// All fields are either `Arc`-wrapped or internally Arc-backed (e.g. `reqwest::Client`),
/// making clones cheap reference-count increments.
///
/// `queue` and `dlq` are `Option` so that integration tests and minimal
/// environments can construct an `AppState` without a live Redis connection.
/// In production both fields are always `Some(...)` after `main()` initialization.
#[derive(Clone)]
pub struct AppState {
    pub config: Arc<Config>,
    pub http_client: reqwest::Client,
    /// Producer for the Redis Streams job queue (HIGH / NORMAL / LOW).
    /// `None` only in test contexts; always `Some` in production.
    pub queue: Option<Arc<QueueDispatcher>>,
    /// Archive for definitively failed jobs.
    /// `None` only in test contexts; always `Some` in production.
    pub dlq: Option<Arc<DlqDispatcher>>,
}
