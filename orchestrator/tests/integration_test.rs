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
        groq_api_key: None,
        ollama_base_url: None,
        default_model: "gpt-4o".to_string(),
        otel_exporter_otlp_endpoint: None,
        rust_log: "error".to_string(),
        backend_secret: "test-backend-secret".to_string(),
        llm_mock: true,
    }
}

fn test_app() -> axum::Router {
    // queue and dlq are None — these tests never reach the queue path
    // (all requests fail at auth or body validation before orchestrate() is called).
    let state = Arc::new(AppState {
        config: Arc::new(test_config()),
        http_client: reqwest::Client::new(),
        mcp_client: reqwest::Client::new(),
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

// ─────────────────────────────────────────────────────────────────────────────
// Billing / Analytics / Sequences tool-name parsing
// ─────────────────────────────────────────────────────────────────────────────

/// Verify that all billing MCP tool names parse correctly via `parse_tool_name`.
#[test]
fn test_parse_billing_tool_names() {
    use orchestrator::mcp_client::parse_tool_name;

    let billing_tools = [
        ("mcp_billing__list_invoices", "mcp_billing", "list_invoices"),
        ("mcp_billing__get_invoice", "mcp_billing", "get_invoice"),
        (
            "mcp_billing__list_overdue_payments",
            "mcp_billing",
            "list_overdue_payments",
        ),
        (
            "mcp_billing__get_subscription",
            "mcp_billing",
            "get_subscription",
        ),
        (
            "mcp_billing__update_subscription_status",
            "mcp_billing",
            "update_subscription_status",
        ),
        (
            "mcp_billing__check_subscription_status",
            "mcp_billing",
            "check_subscription_status",
        ),
        (
            "mcp_billing__get_customer_billing_summary",
            "mcp_billing",
            "get_customer_billing_summary",
        ),
        ("mcp_billing__get_mrr", "mcp_billing", "get_mrr"),
    ];

    for (full_name, expected_prefix, expected_tool) in &billing_tools {
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

/// Verify that all analytics MCP tool names parse correctly via `parse_tool_name`.
#[test]
fn test_parse_analytics_tool_names() {
    use orchestrator::mcp_client::parse_tool_name;

    let analytics_tools = [
        (
            "mcp_analytics__get_mrr_trend",
            "mcp_analytics",
            "get_mrr_trend",
        ),
        (
            "mcp_analytics__get_pipeline_metrics",
            "mcp_analytics",
            "get_pipeline_metrics",
        ),
        (
            "mcp_analytics__compute_churn_rate",
            "mcp_analytics",
            "compute_churn_rate",
        ),
        (
            "mcp_analytics__get_at_risk_accounts",
            "mcp_analytics",
            "get_at_risk_accounts",
        ),
        (
            "mcp_analytics__get_rep_performance",
            "mcp_analytics",
            "get_rep_performance",
        ),
        (
            "mcp_analytics__get_team_leaderboard",
            "mcp_analytics",
            "get_team_leaderboard",
        ),
        (
            "mcp_analytics__get_deal_velocity",
            "mcp_analytics",
            "get_deal_velocity",
        ),
        (
            "mcp_analytics__get_funnel_analysis",
            "mcp_analytics",
            "get_funnel_analysis",
        ),
        (
            "mcp_analytics__forecast_revenue",
            "mcp_analytics",
            "forecast_revenue",
        ),
        (
            "mcp_analytics__get_activity_metrics",
            "mcp_analytics",
            "get_activity_metrics",
        ),
    ];

    for (full_name, expected_prefix, expected_tool) in &analytics_tools {
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

/// Verify that all sequences MCP tool names parse correctly via `parse_tool_name`.
#[test]
fn test_parse_sequences_tool_names() {
    use orchestrator::mcp_client::parse_tool_name;

    let sequences_tools = [
        (
            "mcp_sequences__list_sequences",
            "mcp_sequences",
            "list_sequences",
        ),
        (
            "mcp_sequences__create_sequence",
            "mcp_sequences",
            "create_sequence",
        ),
        (
            "mcp_sequences__update_sequence",
            "mcp_sequences",
            "update_sequence",
        ),
        (
            "mcp_sequences__delete_sequence",
            "mcp_sequences",
            "delete_sequence",
        ),
        (
            "mcp_sequences__get_sequence",
            "mcp_sequences",
            "get_sequence",
        ),
        (
            "mcp_sequences__enroll_contact",
            "mcp_sequences",
            "enroll_contact",
        ),
        (
            "mcp_sequences__unenroll_contact",
            "mcp_sequences",
            "unenroll_contact",
        ),
        (
            "mcp_sequences__list_enrollments",
            "mcp_sequences",
            "list_enrollments",
        ),
        (
            "mcp_sequences__pause_sequence",
            "mcp_sequences",
            "pause_sequence",
        ),
        (
            "mcp_sequences__resume_sequence",
            "mcp_sequences",
            "resume_sequence",
        ),
        (
            "mcp_sequences__get_sequence_performance",
            "mcp_sequences",
            "get_sequence_performance",
        ),
    ];

    for (full_name, expected_prefix, expected_tool) in &sequences_tools {
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

// ─────────────────────────────────────────────────────────────────────────────
// default_tool_definitions — multi-service coverage
// ─────────────────────────────────────────────────────────────────────────────

/// Verify that `default_tool_definitions()` includes tools for all five services.
#[test]
fn test_default_tool_definitions_covers_all_services() {
    use orchestrator::context::builder::default_tool_definitions;

    let tools = default_tool_definitions();
    let names: Vec<&str> = tools.iter().map(|t| t.function.name.as_str()).collect();

    // Billing
    for expected in &[
        "mcp_billing__list_invoices",
        "mcp_billing__get_invoice",
        "mcp_billing__list_overdue_payments",
        "mcp_billing__get_subscription",
    ] {
        assert!(
            names.contains(expected),
            "Missing billing tool: {}. Have: {:?}",
            expected,
            names
        );
    }

    // Analytics
    for expected in &[
        "mcp_analytics__get_mrr_trend",
        "mcp_analytics__get_pipeline_metrics",
        "mcp_analytics__compute_churn_rate",
        "mcp_analytics__forecast_revenue",
    ] {
        assert!(
            names.contains(expected),
            "Missing analytics tool: {}",
            expected
        );
    }

    // Sequences
    for expected in &[
        "mcp_sequences__list_sequences",
        "mcp_sequences__create_sequence",
        "mcp_sequences__enroll_contact",
        "mcp_sequences__get_sequence_performance",
    ] {
        assert!(
            names.contains(expected),
            "Missing sequences tool: {}",
            expected
        );
    }

    // Filesystem
    for expected in &[
        "mcp_filesystem__read_document",
        "mcp_filesystem__list_documents",
    ] {
        assert!(
            names.contains(expected),
            "Missing filesystem tool: {}",
            expected
        );
    }
}

/// Verify that the total number of tools covers all services (billing + analytics +
/// sequences + filesystem on top of the 12 CRM tools).
#[test]
fn test_default_tool_definitions_total_count() {
    use orchestrator::context::builder::default_tool_definitions;

    let tools = default_tool_definitions();

    let crm_count = tools
        .iter()
        .filter(|t| t.function.name.starts_with("mcp_crm__"))
        .count();
    let billing_count = tools
        .iter()
        .filter(|t| t.function.name.starts_with("mcp_billing__"))
        .count();
    let analytics_count = tools
        .iter()
        .filter(|t| t.function.name.starts_with("mcp_analytics__"))
        .count();
    let sequences_count = tools
        .iter()
        .filter(|t| t.function.name.starts_with("mcp_sequences__"))
        .count();
    let filesystem_count = tools
        .iter()
        .filter(|t| t.function.name.starts_with("mcp_filesystem__"))
        .count();

    assert_eq!(crm_count, 12, "Expected 12 CRM tools, got {}", crm_count);
    assert!(
        billing_count >= 4,
        "Expected at least 4 billing tools, got {}",
        billing_count
    );
    assert!(
        analytics_count >= 4,
        "Expected at least 4 analytics tools, got {}",
        analytics_count
    );
    assert!(
        sequences_count >= 4,
        "Expected at least 4 sequences tools, got {}",
        sequences_count
    );
    assert!(
        filesystem_count >= 2,
        "Expected at least 2 filesystem tools, got {}",
        filesystem_count
    );

    assert!(
        tools.len() > 12,
        "Total tools should exceed 12 (CRM only), got {}",
        tools.len()
    );
}
