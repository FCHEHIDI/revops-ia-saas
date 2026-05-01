use std::convert::Infallible;
use std::sync::Arc;

use axum::{
    extract::{Json, State},
    http::HeaderMap,
    response::sse::{Event, KeepAlive, Sse},
};
use futures::future::join_all;
use opentelemetry_semantic_conventions::trace as semconv;
use tokio::sync::mpsc;
use tokio_stream::wrappers::ReceiverStream;
use tracing::{error, info, instrument, warn};

use crate::{
    context::builder::ContextBuilder,
    error::AppError,
    llm_client::create_llm_provider,
    mcp_client::{parse_tool_name, McpDispatcher},
    models::{Message, Priority, ProcessRequest, Role, SseEventPayload, ToolCall},
    queue::OrchestratorJob,
    rag_client::client::RagClient,
    routing::router::ModelRouter,
    AppState,
};

/// POST /process — main orchestration endpoint.
///
/// Requires `X-Internal-API-Key` header matching `INTER_SERVICE_SECRET`.
/// Returns an SSE stream of events:
/// - `{"type":"token","content":"..."}` — LLM output tokens
/// - `{"type":"tool_call","tool":"...","result":{...}}` — MCP tool results
/// - `{"type":"done","usage":{...}}` — terminal event with token usage
/// - `{"type":"error","message":"..."}` — error event (stream ends after this)
#[instrument(
    skip(state, headers, req),
    fields(
        tenant_id = tracing::field::Empty,
        conversation_id = tracing::field::Empty,
        // OTEL semantic conventions for HTTP server spans
        { semconv::HTTP_REQUEST_METHOD } = "POST",
        { semconv::URL_PATH } = "/process",
    )
)]
pub async fn process_handler(
    State(state): State<Arc<AppState>>,
    headers: HeaderMap,
    Json(req): Json<ProcessRequest>,
) -> Result<Sse<impl futures::Stream<Item = Result<Event, Infallible>>>, AppError> {
    validate_api_key(&headers, &state.config.inter_service_secret)?;
    validate_tenant(&req)?;

    tracing::Span::current()
        .record("tenant_id", req.tenant_id.to_string())
        .record("conversation_id", req.conversation_id.to_string());

    info!(
        tenant_id = %req.tenant_id,
        conversation_id = %req.conversation_id,
        user_id = %req.user_id,
        priority = ?req.priority,
        "Orchestration request received"
    );

    let (tx, rx) = mpsc::channel::<Result<Event, Infallible>>(128);
    let tx_err = tx.clone();

    tokio::spawn(async move {
        if let Err(e) = orchestrate(state, req, tx).await {
            error!(error = %e, "Orchestration failed");
            send_event(
                &tx_err,
                &SseEventPayload::Error {
                    message: e.to_string(),
                },
            )
            .await;
        }
    });

    Ok(Sse::new(ReceiverStream::new(rx)).keep_alive(KeepAlive::default()))
}

fn validate_api_key(headers: &HeaderMap, expected: &str) -> Result<(), AppError> {
    match headers.get("x-internal-api-key") {
        Some(val) => {
            let provided = val.to_str().map_err(|_| AppError::Unauthorized)?;
            if provided == expected {
                Ok(())
            } else {
                Err(AppError::Unauthorized)
            }
        }
        None => Err(AppError::Unauthorized),
    }
}

fn validate_tenant(req: &ProcessRequest) -> Result<(), AppError> {
    if req.tenant_id.is_nil() {
        return Err(AppError::TenantError(
            "tenant_id cannot be nil UUID".to_string(),
        ));
    }
    Ok(())
}

async fn send_event(tx: &mpsc::Sender<Result<Event, Infallible>>, payload: &SseEventPayload) {
    match serde_json::to_string(payload) {
        Ok(data) => {
            if tx.send(Ok(Event::default().data(data))).await.is_err() {
                warn!("SSE receiver dropped — client disconnected");
            }
        }
        Err(e) => error!(error = %e, "Failed to serialize SSE event"),
    }
}

/// Core orchestration loop (stateless):
///
/// 1. LOW priority → enqueue in Redis and return `Accepted` SSE event immediately.
/// 2. HIGH / NORMAL → Build context: fetch history + RAG retrieval
/// 3. Agentic loop: call LLM → dispatch tool calls → inject results → repeat
/// 4. Stream final response tokens as SSE events
#[instrument(
    skip(state, req, tx),
    fields(
        tenant_id = %req.tenant_id,
        priority = tracing::field::Empty,
        model    = tracing::field::Empty,
        iterations = tracing::field::Empty,
        // OTEL GenAI semantic conventions
        { semconv::GEN_AI_OPERATION_NAME } = "chat",
        { semconv::GEN_AI_SYSTEM } = tracing::field::Empty,
        gen_ai.request.model = tracing::field::Empty,
        gen_ai.usage.input_tokens = tracing::field::Empty,
        gen_ai.usage.output_tokens = tracing::field::Empty,
    )
)]
async fn orchestrate(
    state: Arc<AppState>,
    req: ProcessRequest,
    tx: mpsc::Sender<Result<Event, Infallible>>,
) -> Result<(), AppError> {
    let priority_label = match req.priority {
        Priority::High => "HIGH",
        Priority::Normal => "NORMAL",
        Priority::Low => "LOW",
    };
    tracing::Span::current().record("priority", priority_label);

    // LOW priority jobs are processed asynchronously by the background worker.
    // The caller receives an `Accepted` event with the job_id so it can poll
    // GET /internal/jobs/{job_id} for the result.
    if req.priority == Priority::Low {
        let job = OrchestratorJob::new(
            req.tenant_id,
            req.conversation_id,
            req.user_id,
            req.message.clone(),
            req.priority.clone(),
        );

        let queue = state.queue.as_ref().ok_or_else(|| AppError::QueueError {
            queue: "orchestrator:low".to_string(),
            message: "Queue dispatcher not initialized".to_string(),
        })?;

        let msg_id = queue.enqueue(&job).await?;

        info!(
            job_id = %job.job_id,
            queue = "orchestrator:low",
            msg_id = %msg_id,
            tenant_id = %req.tenant_id,
            "LOW priority job enqueued — returning Accepted"
        );

        send_event(
            &tx,
            &SseEventPayload::Accepted {
                job_id: job.job_id,
                queue: "orchestrator:low".to_string(),
            },
        )
        .await;

        return Ok(());
    }

    const MAX_ITERATIONS: u32 = 10;

    // Build context-scoped services
    let rag_client = RagClient::new(
        state.http_client.clone(),
        state.config.rag_api_url.clone(),
        state.config.inter_service_secret.clone(),
    );

    let mcp_dispatcher = McpDispatcher::new(state.mcp_client.clone(), state.config.clone());

    let model_router = ModelRouter::new(state.config.clone());
    let model = model_router.select_model(&req);
    tracing::Span::current().record("model", model.as_str());

    // Record GenAI semantic convention attributes for this span
    let gen_ai_system = if model.starts_with("claude-") {
        "anthropic"
    } else if model.starts_with("gpt-") || model.starts_with("o1") || model.starts_with("o3") {
        "openai"
    } else if model.starts_with("groq:") || model.starts_with("groq/") {
        "groq"
    } else {
        "ollama"
    };
    tracing::Span::current()
        .record(semconv::GEN_AI_SYSTEM, gen_ai_system)
        .record("gen_ai.request.model", model.as_str());

    let llm = create_llm_provider(&model, &state.config)?;

    // Build initial context
    let context_builder = ContextBuilder::new(state.http_client.clone(), state.config.clone());

    let mut ctx = context_builder.build(&req, &rag_client).await?;

    // If the message doesn't appear to require live data, strip tools so the
    // LLM responds directly in one pass instead of triggering a tool-call loop
    // (which costs an extra ~20s LLM call for nothing).
    if !needs_tools(&req.message) {
        ctx.tools.clear();
        info!("Message classified as conversational — skipping tool definitions");
    }

    info!(model = %model, "Starting agentic loop");

    // Agentic loop: call LLM, dispatch tool calls, repeat until no tool calls
    for iteration in 0..MAX_ITERATIONS {
        let llm_response = llm
            .complete(&ctx.messages, &ctx.tools)
            .await
            .map_err(|e| AppError::LlmError(e.to_string()))?;

        // Stream content tokens to client (chunked to simulate token streaming)
        // Only stream tokens for the FINAL response (no tool calls).
        // If the LLM returns both content and tool calls in the same turn
        // (Llama behaviour), suppress the text — the tool results will
        // produce a clean final answer on the next iteration.
        if llm_response.tool_calls.is_empty() {
            if let Some(ref content) = llm_response.content {
                stream_content_tokens(&tx, content).await;
            }
        }

        if llm_response.tool_calls.is_empty() {
            // Final response — emit done event and exit loop
            tracing::Span::current().record("iterations", iteration + 1);
            tracing::Span::current()
                .record("gen_ai.usage.input_tokens", llm_response.usage.prompt_tokens)
                .record("gen_ai.usage.output_tokens", llm_response.usage.completion_tokens);
            send_event(
                &tx,
                &SseEventPayload::Done {
                    usage: llm_response.usage,
                },
            )
            .await;
            break;
        }

        // LLM requested tool calls — persist assistant message then dispatch
        ctx.messages.push(Message {
            role: Role::Assistant,
            content: llm_response.content.clone(),
            tool_calls: Some(llm_response.tool_calls.clone()),
            tool_call_id: None,
            name: None,
        });

        info!(
            iteration,
            num_calls = llm_response.tool_calls.len(),
            "LLM requested tool calls"
        );

        dispatch_tool_calls(
            &tx,
            &mcp_dispatcher,
            &mut ctx.messages,
            &llm_response.tool_calls,
            &req.tenant_id.to_string(),
        )
        .await;

        // After dispatching tools, strip tool definitions from the context.
        // The next LLM call only needs to format the results — sending all
        // tool schemas again wastes ~4-5k tokens and can hit TPM rate limits.
        ctx.tools.clear();
    }

    Ok(())
}

/// Classify the CRM entity type from a tool name.
///
/// Used to enrich tracing spans with a high-level entity dimension so that
/// dashboards can aggregate CRM call durations per entity type.
fn crm_entity_type_from_tool(tool_name: &str) -> &'static str {
    if tool_name.contains("contact") {
        "contact"
    } else if tool_name.contains("account") {
        "account"
    } else if tool_name.contains("deal") {
        "deal"
    } else {
        "other"
    }
}

/// Emit LLM content as individual token events in ~50-char chunks.
async fn stream_content_tokens(tx: &mpsc::Sender<Result<Event, Infallible>>, content: &str) {
    // Chunk by word boundary so tokens look natural
    let words: Vec<&str> = content.split_inclusive(' ').collect();
    let mut buffer = String::new();

    for word in words {
        buffer.push_str(word);
        if buffer.len() >= 10 {
            send_event(
                tx,
                &SseEventPayload::Token {
                    content: buffer.clone(),
                },
            )
            .await;
            buffer.clear();
        }
    }

    if !buffer.is_empty() {
        send_event(tx, &SseEventPayload::Token { content: buffer }).await;
    }
}

/// Dispatch all tool calls to their respective MCP servers, injecting results
/// back into `messages` so the next LLM call has full context.
///
/// All calls within a single LLM iteration are dispatched concurrently via
/// `join_all`. Results are processed in the original input order so the
/// injected `messages` sequence is stable and deterministic.
async fn dispatch_tool_calls(
    tx: &mpsc::Sender<Result<Event, Infallible>>,
    dispatcher: &McpDispatcher,
    messages: &mut Vec<Message>,
    tool_calls: &[ToolCall],
    tenant_id: &str,
) {
    // Pre-parse all argument payloads. Invalid JSON falls back to an empty
    // object so the MCP server can apply its own parameter defaults rather
    // than aborting the entire agentic iteration.
    let parsed_args: Vec<serde_json::Value> = tool_calls
        .iter()
        .map(|tc| {
            serde_json::from_str(&tc.function.arguments).unwrap_or_else(|e| {
                warn!(
                    tool = %tc.function.name,
                    error = %e,
                    "Invalid tool arguments JSON — falling back to empty object"
                );
                serde_json::Value::Object(Default::default())
            })
        })
        .collect();

    info!(
        num_calls = tool_calls.len(),
        "Dispatching MCP tool calls in parallel"
    );

    // Dispatch concurrently; join_all preserves input order in the result vec.
    // Each future returns (result, duration_ms) so the results loop can log
    // per-call latency without a second clock read.
    let results = join_all(
        tool_calls
            .iter()
            .zip(parsed_args.iter())
            .map(|(tc, params)| {
                let tool_name = tc.function.name.clone();
                let tenant = tenant_id.to_string();
                let params = params.clone();
                async move {
                    let start = tokio::time::Instant::now();
                    let result = dispatcher.call(&tool_name, params, &tenant).await;
                    let duration_ms = start.elapsed().as_millis() as u64;
                    (result, duration_ms)
                }
            }),
    )
    .await;

    // Process results in original order for stable message injection.
    for (tc, (result, duration_ms)) in tool_calls.iter().zip(results) {
        let tool_name = &tc.function.name;
        let server_prefix = parse_tool_name(tool_name)
            .map(|(prefix, _)| prefix)
            .unwrap_or("unknown");
        let crm_entity = crm_entity_type_from_tool(tool_name);

        let (result_value, result_content) = match result {
            Ok(v) => {
                // Truncate large list results to avoid Groq TPM rate limits.
                let s = truncate_mcp_result(v.clone());
                info!(
                    tool = %tool_name,
                    server = %server_prefix,
                    crm_entity_type = %crm_entity,
                    duration_ms,
                    result_chars = s.len(),
                    success = true,
                    "MCP tool call completed"
                );
                (v, s)
            }
            Err(e) => {
                error!(
                    tool = %tool_name,
                    server = %server_prefix,
                    crm_entity_type = %crm_entity,
                    duration_ms,
                    success = false,
                    error = %e,
                    "MCP tool call failed"
                );
                let err_msg = format!("Tool call failed: {}", e);
                (serde_json::json!({"error": err_msg}), err_msg)
            }
        };

        // Notify client of the tool call result
        send_event(
            tx,
            &SseEventPayload::ToolCall {
                tool: tool_name.clone(),
                result: result_value,
            },
        )
        .await;

        // Inject tool result into conversation context
        messages.push(Message::tool_result(tc.id.clone(), result_content));
    }
}

/// Heuristic classifier: returns `true` if the message likely needs live MCP
/// tool data (CRM contacts, deals, billing, metrics, etc.).
///
/// When `false`, the tools list is cleared before sending to the LLM, saving
/// one full LLM inference round-trip (~20s on CPU) for conversational messages
/// like greetings, thanks, or general questions.
fn needs_tools(message: &str) -> bool {
    let msg = message.to_lowercase();

    // Data-oriented keywords that require tool calls
    const DATA_KEYWORDS: &[&str] = &[
        // CRM entities
        "contact",
        "client",
        "account",
        "deal",
        "lead",
        "prospect",
        "opportunit",
        "pipeline",
        "société",
        "societe",
        "entreprise",
        "company",
        // Billing / revenue
        "facture",
        "invoice",
        "billing",
        "paiement",
        "payment",
        "revenue",
        "chiffre",
        "mrr",
        "arr",
        "montant",
        "amount",
        "abonnement",
        "subscription",
        // Actions that imply data retrieval
        "liste",
        "montre",
        "affiche",
        "recherche",
        "trouve",
        "show",
        "list",
        "find",
        "search",
        "get",
        "fetch",
        "donne-moi",
        "donne moi",
        "combien",
        "quel",
        // Sequences / analytics
        "séquence",
        "sequence",
        "campagne",
        "campaign",
        "metric",
        "dashboard",
        "report",
        "rapport",
        "analyse",
        "analytics",
        "statistique",
    ];

    DATA_KEYWORDS.iter().any(|kw| msg.contains(kw))
}

/// Truncates a large MCP result to stay within Groq's TPM limits.
///
/// - If the result is an object with an `items` array, keeps the first
///   `MAX_ITEMS` elements and appends a `_truncated` note so the LLM
///   knows the list was shortened.
/// - Otherwise, truncates the JSON string to `MAX_CHARS` characters.
///
/// This prevents 429 rate-limit errors while still giving the LLM
/// enough representative data to answer.
fn truncate_mcp_result(value: serde_json::Value) -> String {
    const MAX_ITEMS: usize = 5;
    const MAX_CHARS: usize = 3000;

    if let serde_json::Value::Object(ref map) = value {
        if let Some(serde_json::Value::Array(items)) = map.get("items") {
            if items.len() > MAX_ITEMS {
                let mut truncated = map.clone();
                truncated.insert(
                    "items".to_string(),
                    serde_json::Value::Array(items[..MAX_ITEMS].to_vec()),
                );
                truncated.insert(
                    "_truncated".to_string(),
                    serde_json::json!(format!(
                        "Showing {}/{} items (list truncated for context size)",
                        MAX_ITEMS,
                        items.len()
                    )),
                );
                return serde_json::to_string(&truncated).unwrap_or_default();
            }
        }
    }

    let s = serde_json::to_string(&value).unwrap_or_default();
    if s.len() > MAX_CHARS {
        format!("{}… [truncated at {} chars]", &s[..MAX_CHARS], MAX_CHARS)
    } else {
        s
    }
}
