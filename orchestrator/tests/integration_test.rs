use axum::{
    body::Body,
    http::{Request, StatusCode},
};
use std::sync::Arc;
use tower::ServiceExt;

// Re-use the orchestrator crate internals for tests
use orchestrator::{api, AppState, config::Config};

fn test_config() -> Config {
    // Minimal config for unit tests — no external services required
    Config {
        server_host: "127.0.0.1".to_string(),
        server_port: 8001,
        inter_service_secret: "test-secret".to_string(),
        backend_api_url: "http://localhost:8000".to_string(),
        rag_api_url: "http://localhost:8002".to_string(),
        mcp_crm_url: "http://localhost:9001".to_string(),
        mcp_billing_url: "http://localhost:9002".to_string(),
        mcp_analytics_url: "http://localhost:9003".to_string(),
        mcp_sequences_url: "http://localhost:9004".to_string(),
        mcp_filesystem_url: "http://localhost:9005".to_string(),
        redis_url: "redis://localhost:6379".to_string(),
        openai_api_key: Some("test-key".to_string()),
        anthropic_api_key: None,
        default_model: "gpt-4o".to_string(),
        otel_exporter_otlp_endpoint: None,
        rust_log: "error".to_string(),
    }
}

fn test_app() -> axum::Router {
    let state = Arc::new(AppState {
        config: Arc::new(test_config()),
        http_client: reqwest::Client::new(),
    });
    api::router(state)
}

#[tokio::test]
async fn health_returns_200() {
    let app = test_app();

    let request = Request::builder()
        .uri("/health")
        .body(Body::empty())
        .unwrap();

    let response = app.oneshot(request).await.unwrap();

    assert_eq!(response.status(), StatusCode::OK);
}

#[tokio::test]
async fn health_body_contains_ok_status() {
    let app = test_app();

    let request = Request::builder()
        .uri("/health")
        .body(Body::empty())
        .unwrap();

    let response = app.oneshot(request).await.unwrap();
    let body = axum::body::to_bytes(response.into_body(), usize::MAX)
        .await
        .unwrap();
    let json: serde_json::Value = serde_json::from_slice(&body).unwrap();

    assert_eq!(json["status"], "ok");
    assert_eq!(json["service"], "orchestrator");
}

#[tokio::test]
async fn process_without_api_key_returns_401() {
    let app = test_app();

    let request = Request::builder()
        .method("POST")
        .uri("/process")
        .header("content-type", "application/json")
        .body(Body::from(
            r#"{
                "tenant_id": "00000000-0000-0000-0000-000000000001",
                "conversation_id": "00000000-0000-0000-0000-000000000002",
                "message": "Hello",
                "user_id": "00000000-0000-0000-0000-000000000003"
            }"#,
        ))
        .unwrap();

    let response = app.oneshot(request).await.unwrap();

    assert_eq!(response.status(), StatusCode::UNAUTHORIZED);
}

#[tokio::test]
async fn process_with_wrong_api_key_returns_401() {
    let app = test_app();

    let request = Request::builder()
        .method("POST")
        .uri("/process")
        .header("content-type", "application/json")
        .header("x-internal-api-key", "wrong-secret")
        .body(Body::from(
            r#"{
                "tenant_id": "00000000-0000-0000-0000-000000000001",
                "conversation_id": "00000000-0000-0000-0000-000000000002",
                "message": "Hello",
                "user_id": "00000000-0000-0000-0000-000000000003"
            }"#,
        ))
        .unwrap();

    let response = app.oneshot(request).await.unwrap();

    assert_eq!(response.status(), StatusCode::UNAUTHORIZED);
}

#[tokio::test]
async fn process_with_invalid_body_returns_422() {
    let app = test_app();

    let request = Request::builder()
        .method("POST")
        .uri("/process")
        .header("content-type", "application/json")
        .header("x-internal-api-key", "test-secret")
        .body(Body::from(r#"{"invalid": "payload"}"#))
        .unwrap();

    let response = app.oneshot(request).await.unwrap();

    assert_eq!(response.status(), StatusCode::UNPROCESSABLE_ENTITY);
}
