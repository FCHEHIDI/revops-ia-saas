//! Background worker — consumes `orchestrator:low` priority jobs.
//!
//! Runs as a `tokio::spawn`'d task in the same process as the HTTP server.
//! Processes jobs asynchronously: reconstruct context → call LLM → notify backend.
//!
//! ## Retry / DLQ flow
//!
//! - Job is delivered via XREADGROUP (delivery_count = 1)
//! - On failure, the job is NOT ACK'd → it stays in XPENDING
//! - `requeue_pending` runs on a configurable interval and claims messages
//!   idle longer than `pending_min_idle_ms` via XCLAIM
//! - After `max_attempts` deliveries (tracked by Redis XPENDING delivery_count),
//!   the job is archived to the DLQ and ACK'd to remove it from the stream
//!
//! ## Backend contract — POST /internal/jobs/{job_id}/completed
//!
//! Request (JSON):
//! ```json
//! {
//!   "tenant_id":        "<uuid>",
//!   "conversation_id":  "<uuid>",
//!   "response_content": "<LLM response text>",
//!   "tokens_used": {
//!     "prompt_tokens":     123,
//!     "completion_tokens": 456,
//!     "total_tokens":      579
//!   }
//! }
//! ```
//! Response: 200 OK.
//! The backend should append the assistant message to the conversation and
//! optionally deliver the result to the user (e.g., via email or push notification).

use std::sync::Arc;
use std::time::Duration;

use futures::future::join_all;
use redis::aio::ConnectionManager;
use tracing::{debug, error, info, instrument, warn};
use uuid::Uuid;

use crate::{
    context::builder::ContextBuilder,
    error::AppError,
    llm_client::create_llm_provider,
    mcp_client::McpDispatcher,
    models::{Message, ProcessRequest, Role, UsageStats},
    queue::{
        dispatcher::{
            parse_pending_entries, parse_stream_messages, parse_xclaim_messages, OrchestratorJob,
            CONSUMER_GROUP, STREAM_LOW,
        },
        dlq::{DlqDispatcher, DlqEntry},
    },
    rag_client::client::RagClient,
    routing::router::ModelRouter,
    AppState,
};

// ---------------------------------------------------------------------------
// WorkerConfig
// ---------------------------------------------------------------------------

pub struct WorkerConfig {
    /// Duration to block on XREADGROUP waiting for new messages.
    pub block_timeout_ms: u64,
    /// How often to scan XPENDING for stuck messages.
    pub pending_check_interval_secs: u64,
    /// Minimum idle time before a pending message is reclaimed (XCLAIM).
    pub pending_min_idle_ms: u64,
    /// Maximum delivery attempts before a job is sent to the DLQ.
    pub max_attempts: u32,
}

impl Default for WorkerConfig {
    fn default() -> Self {
        Self {
            block_timeout_ms: 2_000,
            pending_check_interval_secs: 60,
            pending_min_idle_ms: 30_000,
            max_attempts: 3,
        }
    }
}

// ---------------------------------------------------------------------------
// WorkerJobResult — internal result of processing one job
// ---------------------------------------------------------------------------

struct WorkerJobResult {
    content: String,
    usage: UsageStats,
}

// ---------------------------------------------------------------------------
// LowPriorityWorker
// ---------------------------------------------------------------------------

pub struct LowPriorityWorker {
    conn: ConnectionManager,
    state: Arc<AppState>,
    dlq: Arc<DlqDispatcher>,
    worker_config: WorkerConfig,
    consumer_id: String,
}

impl LowPriorityWorker {
    pub fn new(conn: ConnectionManager, state: Arc<AppState>, dlq: Arc<DlqDispatcher>) -> Self {
        let consumer_id = format!("worker-{}", Uuid::new_v4());

        info!(consumer_id = %consumer_id, "LOW priority worker initialized");

        Self {
            conn,
            state,
            dlq,
            worker_config: WorkerConfig::default(),
            consumer_id,
        }
    }

    /// Start the worker loop. Runs indefinitely.
    ///
    /// On transient errors (Redis I/O, LLM failures) it logs and continues.
    /// This function is designed to be called via `tokio::spawn`.
    pub async fn run(mut self) {
        let pending_interval = Duration::from_secs(self.worker_config.pending_check_interval_secs);
        let mut last_pending_check = tokio::time::Instant::now();

        info!(
            consumer_id = %self.consumer_id,
            stream = STREAM_LOW,
            "LOW priority worker started"
        );

        loop {
            // Periodic scan for stuck pending messages
            if last_pending_check.elapsed() >= pending_interval {
                self.requeue_pending().await;
                last_pending_check = tokio::time::Instant::now();
            }

            match self.poll_next_job().await {
                Ok(Some((msg_id, job, delivery_count))) => {
                    info!(
                        job_id = %job.job_id,
                        tenant_id = %job.tenant_id,
                        msg_id = %msg_id,
                        delivery_count,
                        "Dequeued LOW priority job"
                    );
                    self.handle_job(&msg_id, job, delivery_count).await;
                }
                Ok(None) => {
                    // Block timeout — no new messages, loop again
                    debug!("No new jobs (block timeout)");
                }
                Err(e) => {
                    error!(error = %e, "XREADGROUP failed — backing off 1s");
                    tokio::time::sleep(Duration::from_secs(1)).await;
                }
            }
        }
    }

    // ── Polling ──────────────────────────────────────────────────────────────

    /// Read one message from `orchestrator:low` via XREADGROUP BLOCK.
    ///
    /// Returns `Ok(None)` on block timeout (normal), `Ok(Some(...))` when a
    /// message arrives, `Err(...)` on Redis error.
    async fn poll_next_job(&mut self) -> Result<Option<(String, OrchestratorJob, u32)>, AppError> {
        let mut conn = self.conn.clone();

        let response: redis::Value = redis::cmd("XREADGROUP")
            .arg("GROUP")
            .arg(CONSUMER_GROUP)
            .arg(&self.consumer_id)
            .arg("COUNT")
            .arg(1u32)
            .arg("BLOCK")
            .arg(self.worker_config.block_timeout_ms)
            .arg("STREAMS")
            .arg(STREAM_LOW)
            .arg(">")
            .query_async(&mut conn)
            .await
            .map_err(|e| AppError::QueueError {
                queue: STREAM_LOW.to_string(),
                message: format!("XREADGROUP failed: {}", e),
            })?;

        // Nil = block timeout (no messages available)
        if matches!(response, redis::Value::Nil) {
            return Ok(None);
        }

        let messages = parse_stream_messages(response);
        let Some((msg_id, fields)) = messages.into_iter().next() else {
            return Ok(None);
        };

        let job = OrchestratorJob::from_fields(&fields)?;
        Ok(Some((msg_id, job, 1)))
    }

    // ── Job processing ────────────────────────────────────────────────────────

    /// Process a job: build context → run agentic loop → notify backend.
    ///
    /// On success: ACK the message.
    /// On failure: if delivery_count < max_attempts, do NOT ACK (stay in XPENDING).
    ///             if delivery_count >= max_attempts, archive to DLQ and ACK.
    #[instrument(skip(self, job), fields(job_id = %job.job_id, tenant_id = %job.tenant_id, delivery_count))]
    async fn handle_job(&mut self, msg_id: &str, job: OrchestratorJob, delivery_count: u32) {
        match self.process_job(&job).await {
            Ok(result) => {
                self.notify_backend_completed(&job, &result).await;
                self.ack(msg_id).await;
            }
            Err(e) => {
                error!(
                    job_id = %job.job_id,
                    error = %e,
                    delivery_count,
                    max_attempts = self.worker_config.max_attempts,
                    "Job processing failed"
                );

                if delivery_count >= self.worker_config.max_attempts {
                    warn!(job_id = %job.job_id, "Max attempts reached — archiving to DLQ");

                    let payload = serde_json::to_value(&job).unwrap_or_else(|_| {
                        serde_json::json!({
                            "job_id": job.job_id.to_string(),
                            "tenant_id": job.tenant_id.to_string(),
                        })
                    });

                    let entry = DlqEntry::new(
                        job.job_id,
                        job.tenant_id,
                        e.to_string(),
                        delivery_count,
                        payload,
                    );

                    if let Err(dlq_err) = self.dlq.archive(&entry).await {
                        error!(
                            job_id = %job.job_id,
                            error = %dlq_err,
                            "Failed to archive job to DLQ"
                        );
                    }

                    // ACK regardless — prevent the job from looping forever
                    self.ack(msg_id).await;
                }
                // else: do NOT ACK → job stays in XPENDING for retry via requeue_pending
            }
        }
    }

    /// Rebuild context and run the agentic loop for a LOW priority job.
    ///
    /// Mirrors the inline `orchestrate()` logic in `api/process.rs` but
    /// without SSE streaming — collects the full response instead.
    async fn process_job(&self, job: &OrchestratorJob) -> Result<WorkerJobResult, AppError> {
        const MAX_ITERATIONS: u32 = 10;

        let req = ProcessRequest {
            tenant_id: job.tenant_id,
            conversation_id: job.conversation_id,
            message: job.message.clone(),
            user_id: job.user_id,
            priority: job.priority.clone(),
        };

        let rag_client = RagClient::new(
            self.state.http_client.clone(),
            self.state.config.rag_api_url.clone(),
            self.state.config.inter_service_secret.clone(),
        );

        let mcp_dispatcher =
            McpDispatcher::new(self.state.http_client.clone(), self.state.config.clone());

        let context_builder =
            ContextBuilder::new(self.state.http_client.clone(), self.state.config.clone());

        let mut ctx = context_builder.build(&req, &rag_client).await?;

        let model_router = ModelRouter::new(self.state.config.clone());
        let model = model_router.select_model(&req);
        let llm = create_llm_provider(&model, &self.state.config)?;

        info!(
            job_id = %job.job_id,
            model = %model,
            "Starting agentic loop for LOW priority job"
        );

        let mut final_content = String::new();
        let mut final_usage = UsageStats::default();

        for iteration in 0..MAX_ITERATIONS {
            let llm_response = llm
                .complete(&ctx.messages, &ctx.tools)
                .await
                .map_err(|e| AppError::LlmError(e.to_string()))?;

            if let Some(ref content) = llm_response.content {
                final_content = content.clone();
            }
            final_usage = llm_response.usage.clone();

            if llm_response.tool_calls.is_empty() {
                debug!(iteration, "Agentic loop complete — no more tool calls");
                break;
            }

            // Persist assistant message + dispatch tool calls (same as inline handler)
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
                "Dispatching MCP tool calls (worker)"
            );

            let parsed_args: Vec<serde_json::Value> = llm_response
                .tool_calls
                .iter()
                .map(|tc| {
                    serde_json::from_str(&tc.function.arguments).unwrap_or_else(|e| {
                        warn!(
                            tool = %tc.function.name,
                            error = %e,
                            "Invalid tool args — falling back to empty object"
                        );
                        serde_json::Value::Object(Default::default())
                    })
                })
                .collect();

            let results = join_all(llm_response.tool_calls.iter().zip(parsed_args.iter()).map(
                |(tc, params)| {
                    let tool_name = tc.function.name.clone();
                    let tenant = job.tenant_id.to_string();
                    let params = params.clone();
                    // Clone before async move so the original stays accessible
                    // across closure calls (McpDispatcher is Arc-backed internally).
                    let dispatcher = mcp_dispatcher.clone();
                    async move { dispatcher.call(&tool_name, params, &tenant).await }
                },
            ))
            .await;

            for (tc, result) in llm_response.tool_calls.iter().zip(results) {
                let content = match result {
                    Ok(v) => serde_json::to_string(&v).unwrap_or_else(|e| {
                        warn!(tool = %tc.function.name, error = %e, "Failed to serialize MCP result");
                        String::new()
                    }),
                    Err(e) => {
                        error!(tool = %tc.function.name, error = %e, "MCP tool call failed (worker)");
                        format!("Tool call failed: {}", e)
                    }
                };
                ctx.messages
                    .push(Message::tool_result(tc.id.clone(), content));
            }
        }

        Ok(WorkerJobResult {
            content: final_content,
            usage: final_usage,
        })
    }

    // ── Backend notification ──────────────────────────────────────────────────

    /// Notify the backend that a LOW priority job completed successfully.
    ///
    /// Backend contract — POST /internal/jobs/{job_id}/completed
    /// Body: {
    ///   "tenant_id":        uuid,
    ///   "conversation_id":  uuid,
    ///   "response_content": string,
    ///   "tokens_used": { "prompt_tokens": u32, "completion_tokens": u32, "total_tokens": u32 }
    /// }
    /// The backend appends the assistant message to the conversation and
    /// delivers the result to the user (e.g. email or webhook).
    async fn notify_backend_completed(&self, job: &OrchestratorJob, result: &WorkerJobResult) {
        let url = format!(
            "{}/internal/jobs/{}/completed",
            self.state.config.backend_api_url, job.job_id
        );

        let body = serde_json::json!({
            "tenant_id":        job.tenant_id,
            "conversation_id":  job.conversation_id,
            "response_content": result.content,
            "tokens_used": {
                "prompt_tokens":     result.usage.prompt_tokens,
                "completion_tokens": result.usage.completion_tokens,
                "total_tokens":      result.usage.total_tokens,
            }
        });

        match self
            .state
            .http_client
            .post(&url)
            .header(
                "X-Internal-API-Key",
                &self.state.config.inter_service_secret,
            )
            .json(&body)
            .send()
            .await
        {
            Ok(resp) if resp.status().is_success() => {
                info!(job_id = %job.job_id, "Backend notified of job completion");
            }
            Ok(resp) => {
                warn!(
                    job_id = %job.job_id,
                    status = %resp.status(),
                    "Backend returned non-success for job completion notification"
                );
            }
            Err(e) => {
                warn!(
                    job_id = %job.job_id,
                    error = %e,
                    "Backend unreachable for job completion notification"
                );
            }
        }
    }

    // ── ACK ───────────────────────────────────────────────────────────────────

    async fn ack(&mut self, msg_id: &str) {
        let mut conn = self.conn.clone();

        match redis::cmd("XACK")
            .arg(STREAM_LOW)
            .arg(CONSUMER_GROUP)
            .arg(msg_id)
            .query_async::<_, i64>(&mut conn)
            .await
        {
            Ok(_) => debug!(msg_id, "Message ACK'd"),
            Err(e) => error!(msg_id, error = %e, "XACK failed"),
        }
    }

    // ── Pending scan + XCLAIM ─────────────────────────────────────────────────

    /// Scan XPENDING for messages idle longer than `pending_min_idle_ms`
    /// and re-deliver them to this consumer via XCLAIM.
    async fn requeue_pending(&mut self) {
        debug!("Scanning XPENDING for stuck messages");

        let mut conn = self.conn.clone();

        let response: redis::Value = match redis::cmd("XPENDING")
            .arg(STREAM_LOW)
            .arg(CONSUMER_GROUP)
            .arg("-")
            .arg("+")
            .arg(100u32)
            .query_async(&mut conn)
            .await
        {
            Ok(v) => v,
            Err(e) => {
                warn!(error = %e, "XPENDING failed");
                return;
            }
        };

        let entries = parse_pending_entries(response);
        let stale: Vec<_> = entries
            .iter()
            .filter(|(_, idle_ms, _)| *idle_ms >= self.worker_config.pending_min_idle_ms)
            .collect();

        if stale.is_empty() {
            return;
        }

        info!(count = stale.len(), "Reclaiming stale pending messages");

        for (msg_id, _idle_ms, delivery_count) in stale {
            let claim_result: Result<redis::Value, _> = redis::cmd("XCLAIM")
                .arg(STREAM_LOW)
                .arg(CONSUMER_GROUP)
                .arg(&self.consumer_id)
                .arg(self.worker_config.pending_min_idle_ms)
                .arg(msg_id.as_str())
                .query_async(&mut conn)
                .await;

            match claim_result {
                Ok(val) => {
                    let claimed = parse_xclaim_messages(val);
                    for (claimed_id, fields) in claimed {
                        match OrchestratorJob::from_fields(&fields) {
                            Ok(job) => {
                                info!(
                                    msg_id = %claimed_id,
                                    job_id = %job.job_id,
                                    delivery_count,
                                    "Retrying claimed job"
                                );
                                self.handle_job(&claimed_id, job, *delivery_count).await;
                            }
                            Err(e) => {
                                error!(msg_id = %claimed_id, error = %e, "Failed to parse claimed message — skipping");
                            }
                        }
                    }
                }
                Err(e) => {
                    warn!(msg_id, error = %e, "XCLAIM failed for pending message");
                }
            }
        }
    }
}
