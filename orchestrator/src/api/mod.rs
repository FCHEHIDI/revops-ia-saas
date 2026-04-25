pub mod health;
pub mod process;

use std::sync::Arc;

use axum::{
    routing::{get, post},
    Router,
};

use crate::AppState;

pub fn router(state: Arc<AppState>) -> Router {
    Router::new()
        .route("/health", get(health::health_handler))
        .route("/process", post(process::process_handler))
        .with_state(state)
}
