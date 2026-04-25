//! Dead Letter Queue — archives definitively failed jobs.
//!
//! When an orchestration job exceeds `max_attempts`, it is:
//! 1. Archived in the Redis stream `orchestrator:dlq` (durable, inspectable)
//! 2. Notified to the backend via `POST /internal/jobs/{job_id}/failed`
//!    (best-effort — backend unavailability is logged, not propagated)
//!
//! ## Backend contract — POST /internal/jobs/{job_id}/failed
//!
//! Request (JSON):
//! ```json
//! {
//!   "tenant_id":   "<uuid>",
//!   "error":       "<human-readable error message>",
//!   "attempts":    3,
//!   "failed_at":   1700000000
//! }
//! ```
//! Response: 200 OK (no body required).
//! The backend should update the job status to `failed` and optionally notify
//! the user. If the endpoint is unavailable, the orchestrator does NOT retry —
//! the backend can query `orchestrator:dlq` directly for reconciliation.

use redis::aio::ConnectionManager;
use serde::{Deserialize, Serialize};
use tracing::{info, instrument, warn};
use uuid::Uuid;

use crate::error::AppError;

// ---------------------------------------------------------------------------
// DLQ stream name
// ---------------------------------------------------------------------------

const DLQ_STREAM: &str = "orchestrator:dlq";
const DLQ_MAXLEN: u64 = 10_000;

// ---------------------------------------------------------------------------
// DlqEntry
// ---------------------------------------------------------------------------

/// A definitively failed job archived in the DLQ stream.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DlqEntry {
    pub job_id: Uuid,
    pub tenant_id: Uuid,
    /// Human-readable description of the final failure.
    pub error: String,
    /// Number of delivery attempts before archival.
    pub attempts: u32,
    /// Unix timestamp (seconds) when the job was archived.
    pub failed_at: u64,
    /// Full job payload for potential reprocessing.
    pub original_payload: serde_json::Value,
}

impl DlqEntry {
    pub fn new(
        job_id: Uuid,
        tenant_id: Uuid,
        error: String,
        attempts: u32,
        original_payload: serde_json::Value,
    ) -> Self {
        Self {
            job_id,
            tenant_id,
            error,
            attempts,
            failed_at: std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap_or_default()
                .as_secs(),
            original_payload,
        }
    }
}

// ---------------------------------------------------------------------------
// DlqDispatcher
// ---------------------------------------------------------------------------

/// Archives failed jobs to the DLQ stream and notifies the backend.
///
/// Uses the same `ConnectionManager` pool as the `QueueDispatcher`
/// (passed in via `QueueDispatcher::connection()`).
#[derive(Clone)]
pub struct DlqDispatcher {
    conn: ConnectionManager,
    http_client: reqwest::Client,
    backend_url: String,
    inter_service_secret: String,
}

impl DlqDispatcher {
    pub fn new(
        conn: ConnectionManager,
        http_client: reqwest::Client,
        backend_url: String,
        inter_service_secret: String,
    ) -> Self {
        Self {
            conn,
            http_client,
            backend_url,
            inter_service_secret,
        }
    }

    /// Archive a failed job to the DLQ stream and notify the backend.
    ///
    /// Step 1 (Redis) is critical — if it fails, the error is propagated.
    /// Step 2 (backend HTTP notification) is best-effort — failure is logged
    /// but does not cause this function to return an error.
    #[instrument(
        skip(self),
        fields(job_id = %entry.job_id, tenant_id = %entry.tenant_id, attempts = entry.attempts)
    )]
    pub async fn archive(&self, entry: &DlqEntry) -> Result<(), AppError> {
        // ── Step 1: XADD to DLQ stream ────────────────────────────────────────
        let payload_str = serde_json::to_string(&entry.original_payload).unwrap_or_else(|e| {
            warn!(error = %e, "Failed to serialize DLQ original_payload — using empty object");
            "{}".to_string()
        });

        let mut conn = self.conn.clone();

        let _msg_id: String = redis::cmd("XADD")
            .arg(DLQ_STREAM)
            .arg("MAXLEN")
            .arg("~")
            .arg(DLQ_MAXLEN)
            .arg("*")
            .arg("job_id")
            .arg(entry.job_id.to_string())
            .arg("tenant_id")
            .arg(entry.tenant_id.to_string())
            .arg("error")
            .arg(&entry.error)
            .arg("attempts")
            .arg(entry.attempts.to_string())
            .arg("failed_at")
            .arg(entry.failed_at.to_string())
            .arg("original_payload")
            .arg(&payload_str)
            .query_async(&mut conn)
            .await
            .map_err(|e| AppError::DlqError(format!("XADD to DLQ failed: {}", e)))?;

        info!(
            job_id = %entry.job_id,
            tenant_id = %entry.tenant_id,
            stream = DLQ_STREAM,
            "Job archived to DLQ"
        );

        // ── Step 2: Notify backend (best-effort) ──────────────────────────────
        //
        // Backend contract — POST /internal/jobs/{job_id}/failed
        // Body: { "tenant_id": uuid, "error": str, "attempts": u32, "failed_at": u64 }
        // The backend updates the job record and may notify the user.
        self.notify_backend_failed(entry).await;

        Ok(())
    }

    async fn notify_backend_failed(&self, entry: &DlqEntry) {
        let url = format!("{}/internal/jobs/{}/failed", self.backend_url, entry.job_id);

        let body = serde_json::json!({
            "tenant_id": entry.tenant_id,
            "error":     entry.error,
            "attempts":  entry.attempts,
            "failed_at": entry.failed_at,
        });

        match self
            .http_client
            .post(&url)
            .header("X-Internal-API-Key", &self.inter_service_secret)
            .json(&body)
            .send()
            .await
        {
            Ok(resp) if resp.status().is_success() => {
                info!(job_id = %entry.job_id, "Backend notified of job failure");
            }
            Ok(resp) => {
                warn!(
                    job_id = %entry.job_id,
                    status = %resp.status(),
                    "Backend returned non-success for job failure notification"
                );
            }
            Err(e) => {
                warn!(
                    job_id = %entry.job_id,
                    error = %e,
                    "Backend unreachable for job failure notification — DLQ entry persisted in Redis"
                );
            }
        }
    }
}
