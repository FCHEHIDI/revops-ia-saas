use axum::{
    body::Body,
    http::{Request, StatusCode},
};
use std::sync::Arc;
use tower::ServiceExt;

// Re-use the orchestrator crate internals for tests
use orchestrator::{api, config::Config, AppState};

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
    // queue and dlq are None — these tests never reach the queue path
    // (all requests fail at auth or body validation before orchestrate() is called).
    let state = Arc::new(AppState {
        config: Arc::new(test_config()),
        http_client: reqwest::Client::new(),
        queue: None,
        dlq: None,
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

// ─────────────────────────────────────────────────────────────────────────────
// CRM integration tests
// ─────────────────────────────────────────────────────────────────────────────

/// Verify that all 12 MCP CRM tool names parse correctly via `parse_tool_name`.
#[test]
fn test_parse_crm_tool_names() {
    use orchestrator::mcp_client::parse_tool_name;

    let crm_tools = [
        ("mcp_crm__get_contact", "mcp_crm", "get_contact"),
        ("mcp_crm__search_contacts", "mcp_crm", "search_contacts"),
        ("mcp_crm__create_contact", "mcp_crm", "create_contact"),
        ("mcp_crm__update_contact", "mcp_crm", "update_contact"),
        ("mcp_crm__get_account", "mcp_crm", "get_account"),
        ("mcp_crm__search_accounts", "mcp_crm", "search_accounts"),
        ("mcp_crm__create_account", "mcp_crm", "create_account"),
        ("mcp_crm__update_account", "mcp_crm", "update_account"),
        ("mcp_crm__get_deal", "mcp_crm", "get_deal"),
        ("mcp_crm__list_deals", "mcp_crm", "list_deals"),
        ("mcp_crm__update_deal_stage", "mcp_crm", "update_deal_stage"),
        ("mcp_crm__create_deal", "mcp_crm", "create_deal"),
    ];

    for (full_name, expected_prefix, expected_tool) in &crm_tools {
        let result = parse_tool_name(full_name)
            .unwrap_or_else(|_| panic!("parse_tool_name failed for '{}'", full_name));
        assert_eq!(
            result.0, *expected_prefix,
            "prefix mismatch for {}",
            full_name
        );
        assert_eq!(result.1, *expected_tool, "tool mismatch for {}", full_name);
    }
}

/// Verify that `default_tool_definitions()` exposes exactly 12 CRM tools.
#[test]
fn test_default_tool_definitions_contains_crm_tools() {
    use orchestrator::context::builder::default_tool_definitions;

    let tools = default_tool_definitions();
    let crm_tools: Vec<&str> = tools
        .iter()
        .filter(|t| t.function.name.starts_with("mcp_crm__"))
        .map(|t| t.function.name.as_str())
        .collect();

    let expected_crm_tools = [
        "mcp_crm__get_contact",
        "mcp_crm__search_contacts",
        "mcp_crm__create_contact",
        "mcp_crm__update_contact",
        "mcp_crm__get_account",
        "mcp_crm__search_accounts",
        "mcp_crm__create_account",
        "mcp_crm__update_account",
        "mcp_crm__get_deal",
        "mcp_crm__list_deals",
        "mcp_crm__update_deal_stage",
        "mcp_crm__create_deal",
    ];

    assert_eq!(
        crm_tools.len(),
        expected_crm_tools.len(),
        "Expected {} CRM tools, found {}: {:?}",
        expected_crm_tools.len(),
        crm_tools.len(),
        crm_tools
    );

    for expected in &expected_crm_tools {
        assert!(
            crm_tools.contains(expected),
            "Missing CRM tool: {}",
            expected
        );
    }
}

/// Verify that `McpDispatcher::call` propagates `tenant_id` in the request body
/// sent to the MCP server.
#[tokio::test]
async fn test_mcp_dispatcher_propagates_tenant_id() {
    use axum::{routing::post, Router};
    use std::sync::{Arc, Mutex};
    use tokio::net::TcpListener;

    use orchestrator::mcp_client::McpDispatcher;

    // Shared state to capture the body the dispatcher sends
    let captured: Arc<Mutex<Option<serde_json::Value>>> = Arc::new(Mutex::new(None));
    let captured_clone = Arc::clone(&captured);

    // Minimal mock MCP server — records the body and returns a valid response
    let mock_app = Router::new().route(
        "/mcp/call",
        post(move |axum::Json(body): axum::Json<serde_json::Value>| {
            let cap = Arc::clone(&captured_clone);
            async move {
                *cap.lock().unwrap() = Some(body);
                axum::Json(serde_json::json!({"result": {"dispatched": true}, "error": null}))
            }
        }),
    );

    let listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
    let addr = listener.local_addr().unwrap();

    tokio::spawn(async move {
        axum::serve(listener, mock_app).await.unwrap();
    });

    // Give the mock server a moment to start accepting connections
    tokio::time::sleep(std::time::Duration::from_millis(10)).await;

    // Build dispatcher pointing at the mock
    let mut cfg = test_config();
    cfg.mcp_crm_url = format!("http://{}", addr);
    let dispatcher = McpDispatcher::new(reqwest::Client::new(), Arc::new(cfg));

    let result = dispatcher
        .call(
            "mcp_crm__get_deal",
            serde_json::json!({"deal_id": "00000000-0000-0000-0000-000000000099"}),
            "tenant-test-42",
        )
        .await;

    assert!(result.is_ok(), "Expected Ok result, got: {:?}", result);

    let body = captured
        .lock()
        .unwrap()
        .clone()
        .expect("No request body captured");
    assert_eq!(
        body["tenant_id"], "tenant-test-42",
        "tenant_id not propagated in MCP request body"
    );
    assert_eq!(
        body["tool"], "get_deal",
        "Tool name (prefix stripped) should be 'get_deal'"
    );
}

/// Verify that a `RagChunk` JSON payload with `crm_metadata` deserialises correctly,
/// and that a payload without `crm_metadata` defaults to `None`.
#[test]
fn test_rag_chunk_crm_metadata_deserialization() {
    use orchestrator::models::RagChunk;

    // Chunk with CRM metadata
    let json_with_meta = r#"{
        "document_id": "00000000-0000-0000-0000-000000000001",
        "filename": "deal_notes.txt",
        "chunk_index": 0,
        "content": "Le prospect a mentionné une contrainte budgétaire pour Q3.",
        "similarity_score": 0.81,
        "document_type": "crm",
        "crm_metadata": {
            "deal_id": "00000000-0000-0000-0000-000000000002",
            "account_id": "00000000-0000-0000-0000-000000000003",
            "deal_stage": "proposal"
        }
    }"#;

    let chunk: RagChunk =
        serde_json::from_str(json_with_meta).expect("Should deserialise chunk with crm_metadata");

    assert!(chunk.crm_metadata.is_some(), "crm_metadata should be Some");
    let meta = chunk.crm_metadata.as_ref().unwrap();
    assert_eq!(meta["deal_stage"], "proposal");
    assert_eq!(meta["deal_id"], "00000000-0000-0000-0000-000000000002");

    // Chunk without CRM metadata — field absent → default None
    let json_without_meta = r#"{
        "document_id": "00000000-0000-0000-0000-000000000004",
        "filename": "playbook.pdf",
        "chunk_index": 1,
        "content": "Qualification criteria for enterprise deals.",
        "similarity_score": 0.74,
        "document_type": "pdf"
    }"#;

    let chunk_pdf: RagChunk = serde_json::from_str(json_without_meta)
        .expect("Should deserialise chunk without crm_metadata");

    assert!(
        chunk_pdf.crm_metadata.is_none(),
        "crm_metadata should be None when absent from JSON"
    );
}

/// Verify that `build_system_prompt` generates distinct `## CRM Context` and
/// `## Relevant Documentation` sections when chunks of both types are present.
#[test]
fn test_build_system_prompt_crm_section() {
    use orchestrator::context::builder::build_system_prompt;
    use orchestrator::models::RagChunk;
    use uuid::Uuid;

    let crm_chunk = RagChunk {
        document_id: Uuid::new_v4(),
        filename: "deal_notes.txt".to_string(),
        chunk_index: 0,
        content: "Budget constraint mentioned for Q3.".to_string(),
        similarity_score: 0.81,
        document_type: "crm".to_string(),
        crm_metadata: Some(serde_json::json!({
            "entity_type": "deal",
            "account_name": "Acme Corp",
            "deal_stage": "qualified"
        })),
    };

    let pdf_chunk = RagChunk {
        document_id: Uuid::new_v4(),
        filename: "playbook_commercial.pdf".to_string(),
        chunk_index: 3,
        content: "For deals in proposal stage, send the ROI calculator.".to_string(),
        similarity_score: 0.74,
        document_type: "pdf".to_string(),
        crm_metadata: None,
    };

    let prompt = build_system_prompt(&[crm_chunk, pdf_chunk]);

    assert!(
        prompt.contains("## CRM Context"),
        "System prompt should contain '## CRM Context' section"
    );
    assert!(
        prompt.contains("## Relevant Documentation"),
        "System prompt should contain '## Relevant Documentation' section"
    );
    assert!(
        prompt.contains("[CRM] deal — Acme Corp | qualified"),
        "CRM chunk header should include entity type, name and stage"
    );
    assert!(
        prompt.contains("playbook_commercial.pdf"),
        "PDF chunk should appear in the documentation section"
    );
}
