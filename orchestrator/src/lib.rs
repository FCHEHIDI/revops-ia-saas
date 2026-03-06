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

/// Shared application state — cloned into every Axum handler via `Arc`.
///
/// `reqwest::Client` is internally Arc-backed and cheap to clone.
#[derive(Clone)]
pub struct AppState {
    pub config: Arc<Config>,
    pub http_client: reqwest::Client,
}
