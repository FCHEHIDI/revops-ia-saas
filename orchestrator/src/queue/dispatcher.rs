//! Queue dispatcher for async job management.
//!
//! Currently a placeholder — the orchestrator processes requests inline
//! (synchronous agentic loop within the SSE handler).
//!
//! This module is designed to support a future architecture where:
//! - `HIGH` priority requests are processed immediately (current behavior)
//! - `NORMAL` requests are enqueued in Redis and processed by workers
//! - `LOW` requests are batched for GPU-efficient processing
//!
//! See ADR-002 for the full queue architecture decision.

use anyhow::Result;
use serde::{Deserialize, Serialize};
use tracing::{debug, info};
use uuid::Uuid;

use crate::models::Priority;

/// A queued orchestration job.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct OrchestratorJob {
    pub job_id: Uuid,
    pub tenant_id: Uuid,
    pub conversation_id: Uuid,
    pub user_id: Uuid,
    pub message: String,
    pub priority: Priority,
    pub created_at: u64,
}

impl OrchestratorJob {
    pub fn new(
        tenant_id: Uuid,
        conversation_id: Uuid,
        user_id: Uuid,
        message: String,
        priority: Priority,
    ) -> Self {
        Self {
            job_id: Uuid::new_v4(),
            tenant_id,
            conversation_id,
            user_id,
            message,
            priority,
            created_at: std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap_or_default()
                .as_secs(),
        }
    }
}

/// Dispatches orchestration jobs to the appropriate queue.
///
/// Currently a no-op placeholder. When the queue architecture is activated,
/// this will push jobs to Redis Streams with TTL and priority metadata.
pub struct QueueDispatcher {
    redis_url: String,
}

impl QueueDispatcher {
    pub fn new(redis_url: String) -> Self {
        Self { redis_url }
    }

    /// Enqueue a job for async processing.
    ///
    /// Queue name convention: `orchestrator:{priority}` — consumers can
    /// subscribe to specific priority channels for autoscaling.
    pub async fn enqueue(&self, job: &OrchestratorJob) -> Result<()> {
        let queue_name = match job.priority {
            Priority::High => "orchestrator:high",
            Priority::Normal => "orchestrator:normal",
            Priority::Low => "orchestrator:low",
        };

        info!(
            job_id = %job.job_id,
            queue = %queue_name,
            tenant_id = %job.tenant_id,
            "Enqueueing orchestration job (placeholder — not yet persisted)"
        );

        debug!(redis_url = %self.redis_url, "Queue dispatcher initialized (placeholder)");

        Ok(())
    }
}
