use std::convert::Infallible;
use std::sync::Arc;

use axum::{
    extract::{Json, State},
    http::HeaderMap,
    response::sse::{Event, KeepAlive, Sse},
};
use tokio::sync::mpsc;
use tokio_stream::wrappers::ReceiverStream;
use tracing::{error, info, instrument, warn};

use crate::{
    AppState,
    context::builder::ContextBuilder,
    error::AppError,
    llm_client::create_llm_provider,
    mcp_client::McpDispatcher,
    models::{Message, ProcessRequest, Role, SseEventPayload, ToolCall},
    rag_client::client::RagClient,
    routing::router::ModelRouter,
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
    )
)]
pub async fn process_handler(
    State(state): State<Arc<AppState>>,
    headers: HeaderMap,
    Json(req): Json<ProcessRequest>,
) -> Result<Sse<impl futures::Stream<Item = Result<Event, Infallible>>>, AppError> {
    validate_api_key(&headers, &state.config.inter_service_secret)?;

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
/// 1. Build context: fetch history + RAG retrieval
/// 2. Select LLM model
/// 3. Agentic loop: call LLM → dispatch tool calls → inject results → repeat
/// 4. Stream final response tokens as SSE events
async fn orchestrate(
    state: Arc<AppState>,
    req: ProcessRequest,
    tx: mpsc::Sender<Result<Event, Infallible>>,
) -> Result<(), AppError> {
    const MAX_ITERATIONS: u32 = 10;

    // Build context-scoped services
    let rag_client = RagClient::new(
        state.http_client.clone(),
        state.config.rag_api_url.clone(),
        state.config.inter_service_secret.clone(),
    );

    let mcp_dispatcher = McpDispatcher::new(
        state.http_client.clone(),
        state.config.clone(),
    );

    let model_router = ModelRouter::new(state.config.clone());
    let model = model_router.select_model(&req);
    let llm = create_llm_provider(&model, &state.config)?;

    // Build initial context
    let context_builder = ContextBuilder::new(
        state.http_client.clone(),
        state.config.clone(),
    );

    let mut ctx = context_builder.build(&req, &rag_client).await?;

    info!(model = %model, "Starting agentic loop");

    // Agentic loop: call LLM, dispatch tool calls, repeat until no tool calls
    for iteration in 0..MAX_ITERATIONS {
        let llm_response = llm
            .complete(&ctx.messages, &ctx.tools)
            .await
            .map_err(|e| AppError::LlmError(e.to_string()))?;

        // Stream content tokens to client (chunked to simulate token streaming)
        if let Some(ref content) = llm_response.content {
            stream_content_tokens(&tx, content).await;
        }

        if llm_response.tool_calls.is_empty() {
            // Final response — emit done event and exit loop
            send_event(&tx, &SseEventPayload::Done { usage: llm_response.usage }).await;
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
            "Dispatching MCP tool calls"
        );

        dispatch_tool_calls(
            &tx,
            &mcp_dispatcher,
            &mut ctx.messages,
            &llm_response.tool_calls,
            &req.tenant_id.to_string(),
        )
        .await;
    }

    Ok(())
}

/// Emit LLM content as individual token events in ~50-char chunks.
async fn stream_content_tokens(
    tx: &mpsc::Sender<Result<Event, Infallible>>,
    content: &str,
) {
    // Chunk by word boundary so tokens look natural
    let words: Vec<&str> = content.split_inclusive(' ').collect();
    let mut buffer = String::new();

    for word in words {
        buffer.push_str(word);
        if buffer.len() >= 10 {
            send_event(tx, &SseEventPayload::Token { content: buffer.clone() }).await;
            buffer.clear();
        }
    }

    if !buffer.is_empty() {
        send_event(tx, &SseEventPayload::Token { content: buffer }).await;
    }
}

/// Dispatch all tool calls to their respective MCP servers, injecting results
/// back into `messages` so the next LLM call has full context.
async fn dispatch_tool_calls(
    tx: &mpsc::Sender<Result<Event, Infallible>>,
    dispatcher: &McpDispatcher,
    messages: &mut Vec<Message>,
    tool_calls: &[ToolCall],
    tenant_id: &str,
) {
    for tool_call in tool_calls {
        let tool_name = &tool_call.function.name;
        let params: serde_json::Value =
            serde_json::from_str(&tool_call.function.arguments).unwrap_or(serde_json::Value::Null);

        info!(tool = %tool_name, "Calling MCP tool");

        let (result_value, result_content) = match dispatcher
            .call(tool_name, params, tenant_id)
            .await
        {
            Ok(v) => {
                let s = serde_json::to_string(&v).unwrap_or_default();
                (v, s)
            }
            Err(e) => {
                error!(tool = %tool_name, error = %e, "MCP tool call failed");
                let err_msg = format!("Tool call failed: {}", e);
                (
                    serde_json::json!({"error": err_msg}),
                    err_msg,
                )
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
        messages.push(Message::tool_result(tool_call.id.clone(), result_content));
    }
}
