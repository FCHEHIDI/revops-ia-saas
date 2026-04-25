use axum::Json;
use serde_json::{json, Value};

/// GET /health — liveness probe, no authentication required.
pub async fn health_handler() -> Json<Value> {
    Json(json!({
        "status": "ok",
        "service": "orchestrator",
        "version": env!("CARGO_PKG_VERSION"),
    }))
}
