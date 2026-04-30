//! Queue dispatcher — producer side of the Redis Streams job queue.
//!
//! Architecture (ADR-002):
//! - Three priority streams: `orchestrator:high`, `orchestrator:normal`, `orchestrator:low`
//! - Consumer group `orchestrator-workers` on each stream (MKSTREAM ensures streams exist)
//! - This module is the *producer*: it only enqueues jobs via XADD
//! - Consumers (workers) live in `queue::worker`
//!
//! Job fields are stored as flat key-value pairs in the stream entry —
//! not as a JSON blob — to make them inspectable via `redis-cli XRANGE`.

use std::collections::HashMap;

use redis::aio::ConnectionManager;
use serde::{Deserialize, Serialize};
use tracing::{debug, info, instrument};
use uuid::Uuid;

use crate::{error::AppError, models::Priority};

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

pub const CONSUMER_GROUP: &str = "orchestrator-workers";

pub const STREAM_HIGH: &str = "orchestrator:high";
pub const STREAM_NORMAL: &str = "orchestrator:normal";
pub const STREAM_LOW: &str = "orchestrator:low";

const MAXLEN_HIGH: u64 = 1_000;
const MAXLEN_NORMAL: u64 = 10_000;
const MAXLEN_LOW: u64 = 50_000;

// ---------------------------------------------------------------------------
// OrchestratorJob
// ---------------------------------------------------------------------------

/// A queued orchestration job stored in a Redis Stream.
///
/// Fields are serialized as flat strings in the stream entry (not JSON).
/// The `attempts` field is informational at enqueue time (always 0);
/// the actual retry count is tracked by Redis via XPENDING delivery_count.
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

    /// Deserialize an `OrchestratorJob` from a Redis Stream field map.
    pub fn from_fields(fields: &HashMap<String, String>) -> Result<Self, AppError> {
        macro_rules! require {
            ($key:expr) => {
                fields.get($key).ok_or_else(|| AppError::QueueError {
                    queue: STREAM_LOW.to_string(),
                    message: format!("Missing stream field '{}'", $key),
                })?
            };
        }

        let parse_uuid = |s: &str, field: &str| -> Result<Uuid, AppError> {
            s.parse::<Uuid>().map_err(|_| AppError::QueueError {
                queue: STREAM_LOW.to_string(),
                message: format!("Invalid UUID in field '{}'", field),
            })
        };

        Ok(Self {
            job_id: parse_uuid(require!("job_id"), "job_id")?,
            tenant_id: parse_uuid(require!("tenant_id"), "tenant_id")?,
            conversation_id: parse_uuid(require!("conversation_id"), "conversation_id")?,
            user_id: parse_uuid(require!("user_id"), "user_id")?,
            message: require!("message").clone(),
            priority: priority_from_str(require!("priority"))?,
            created_at: require!("created_at").parse::<u64>().unwrap_or(0),
        })
    }
}

// ---------------------------------------------------------------------------
// QueueDispatcher — producer
// ---------------------------------------------------------------------------

/// Enqueues orchestration jobs into the appropriate Redis Stream.
///
/// Internally wraps a `ConnectionManager` (Arc-backed, auto-reconnects).
/// `Clone` is cheap — it shares the underlying connection state.
#[derive(Clone)]
pub struct QueueDispatcher {
    conn: ConnectionManager,
}

impl QueueDispatcher {
    /// Connect to Redis, create consumer groups on all three streams (idempotent).
    ///
    /// Fails fast if Redis is unreachable — the orchestrator should not start
    /// without a working queue.
    pub async fn connect(redis_url: &str) -> Result<Self, AppError> {
        let client = redis::Client::open(redis_url).map_err(|e| AppError::QueueError {
            queue: "all".to_string(),
            message: format!("Invalid Redis URL: {}", e),
        })?;

        let conn = ConnectionManager::new(client)
            .await
            .map_err(|e| AppError::QueueError {
                queue: "all".to_string(),
                message: format!("Failed to connect to Redis: {}", e),
            })?;

        let dispatcher = Self { conn };

        for stream in [STREAM_HIGH, STREAM_NORMAL, STREAM_LOW] {
            dispatcher.ensure_consumer_group(stream).await?;
        }

        info!("QueueDispatcher connected — consumer groups initialized");
        Ok(dispatcher)
    }

    /// Create the consumer group for `stream` if it does not yet exist.
    ///
    /// Uses `MKSTREAM` so the stream is created atomically with the group.
    /// `BUSYGROUP` errors are silently ignored (idempotent).
    async fn ensure_consumer_group(&self, stream: &str) -> Result<(), AppError> {
        let mut conn = self.conn.clone();

        let result: Result<redis::Value, redis::RedisError> = redis::cmd("XGROUP")
            .arg("CREATE")
            .arg(stream)
            .arg(CONSUMER_GROUP)
            .arg("$")
            .arg("MKSTREAM")
            .query_async(&mut conn)
            .await;

        match result {
            Ok(_) => {
                info!(stream, "Consumer group '{}' created", CONSUMER_GROUP);
            }
            Err(ref e) if e.code() == Some("BUSYGROUP") => {
                debug!(stream, "Consumer group already exists — skipping");
            }
            Err(e) => {
                return Err(AppError::QueueError {
                    queue: stream.to_string(),
                    message: format!("XGROUP CREATE failed: {}", e),
                });
            }
        }

        Ok(())
    }

    /// Enqueue a job into the appropriate priority stream.
    ///
    /// Uses approximate MAXLEN trimming to bound memory usage.
    /// Returns the Redis-generated message ID (e.g. `"1234567890123-0"`).
    #[instrument(skip(self), fields(job_id = %job.job_id, tenant_id = %job.tenant_id, priority = ?job.priority))]
    pub async fn enqueue(&self, job: &OrchestratorJob) -> Result<String, AppError> {
        let stream = stream_for_priority(&job.priority);
        let maxlen = maxlen_for_priority(&job.priority);

        let mut conn = self.conn.clone();

        let msg_id: String = redis::cmd("XADD")
            .arg(stream)
            .arg("MAXLEN")
            .arg("~")
            .arg(maxlen)
            .arg("*")
            .arg("job_id")
            .arg(job.job_id.to_string())
            .arg("tenant_id")
            .arg(job.tenant_id.to_string())
            .arg("conversation_id")
            .arg(job.conversation_id.to_string())
            .arg("user_id")
            .arg(job.user_id.to_string())
            .arg("message")
            .arg(&job.message)
            .arg("priority")
            .arg(priority_to_str(&job.priority))
            .arg("created_at")
            .arg(job.created_at.to_string())
            .query_async(&mut conn)
            .await
            .map_err(|e| AppError::QueueError {
                queue: stream.to_string(),
                message: format!("XADD failed: {}", e),
            })?;

        info!(
            job_id = %job.job_id,
            stream,
            msg_id = %msg_id,
            tenant_id = %job.tenant_id,
            "Job enqueued"
        );

        Ok(msg_id)
    }

    /// Expose a clone of the internal connection for use by workers and DLQ.
    pub fn connection(&self) -> ConnectionManager {
        self.conn.clone()
    }
}

// ---------------------------------------------------------------------------
// Helpers — stream parsing
// ---------------------------------------------------------------------------

/// Parse the nested `redis::Value` returned by `XREADGROUP` into
/// `(message_id, field_map)` pairs.
///
/// Expected structure:
/// ```text
/// Bulk([
///   Bulk([Data(stream_name), Bulk([
///     Bulk([Data(msg_id), Bulk([Data(f1), Data(v1), ...])])
///   ])])
/// ])
/// ```
pub fn parse_stream_messages(response: redis::Value) -> Vec<(String, HashMap<String, String>)> {
    let mut result = Vec::new();

    let redis::Value::Bulk(streams) = response else {
        return result;
    };

    for stream_entry in streams {
        let redis::Value::Bulk(mut parts) = stream_entry else {
            continue;
        };
        if parts.len() < 2 {
            continue;
        }
        let messages_val = parts.remove(1);
        let redis::Value::Bulk(messages) = messages_val else {
            continue;
        };

        for msg in messages {
            let redis::Value::Bulk(mut msg_parts) = msg else {
                continue;
            };
            if msg_parts.len() < 2 {
                continue;
            }
            let id_val = msg_parts.remove(0);
            let fields_val = msg_parts.remove(0);

            let Some(msg_id) = redis_value_to_string(id_val) else {
                continue;
            };
            let redis::Value::Bulk(raw_fields) = fields_val else {
                continue;
            };

            let mut map = HashMap::new();
            let mut iter = raw_fields.into_iter();
            while let (Some(k), Some(v)) = (iter.next(), iter.next()) {
                if let (Some(key), Some(val)) = (redis_value_to_string(k), redis_value_to_string(v))
                {
                    map.insert(key, val);
                }
            }

            result.push((msg_id, map));
        }
    }

    result
}

/// Parse the response of `XPENDING stream group - + count` into pending entries.
///
/// Each entry is `(message_id, idle_ms, delivery_count)`.
/// This is the detailed form of XPENDING (Redis ≥ 5.0).
pub fn parse_pending_entries(response: redis::Value) -> Vec<(String, u64, u32)> {
    let mut result = Vec::new();

    let redis::Value::Bulk(entries) = response else {
        return result;
    };

    for entry in entries {
        let redis::Value::Bulk(parts) = entry else {
            continue;
        };
        if parts.len() < 4 {
            continue;
        }

        let Some(msg_id) = redis_value_to_string(parts[0].clone()) else {
            continue;
        };
        let idle_ms = match &parts[2] {
            redis::Value::Int(n) => *n as u64,
            _ => continue,
        };
        let delivery_count = match &parts[3] {
            redis::Value::Int(n) => *n as u32,
            _ => continue,
        };

        result.push((msg_id, idle_ms, delivery_count));
    }

    result
}

/// Parse the response of `XCLAIM` into `(message_id, field_map)` pairs.
///
/// XCLAIM returns messages in XRANGE format (no outer stream wrapper).
pub fn parse_xclaim_messages(response: redis::Value) -> Vec<(String, HashMap<String, String>)> {
    let mut result = Vec::new();

    let redis::Value::Bulk(messages) = response else {
        return result;
    };

    for msg in messages {
        let redis::Value::Bulk(mut msg_parts) = msg else {
            continue;
        };
        if msg_parts.len() < 2 {
            continue;
        }
        let id_val = msg_parts.remove(0);
        let fields_val = msg_parts.remove(0);

        let Some(msg_id) = redis_value_to_string(id_val) else {
            continue;
        };
        let redis::Value::Bulk(raw_fields) = fields_val else {
            continue;
        };

        let mut map = HashMap::new();
        let mut iter = raw_fields.into_iter();
        while let (Some(k), Some(v)) = (iter.next(), iter.next()) {
            if let (Some(key), Some(val)) = (redis_value_to_string(k), redis_value_to_string(v)) {
                map.insert(key, val);
            }
        }

        result.push((msg_id, map));
    }

    result
}

// ---------------------------------------------------------------------------
// Private helpers
// ---------------------------------------------------------------------------

fn redis_value_to_string(v: redis::Value) -> Option<String> {
    match v {
        redis::Value::Data(bytes) => String::from_utf8(bytes).ok(),
        redis::Value::Status(s) => Some(s),
        redis::Value::Int(n) => Some(n.to_string()),
        _ => None,
    }
}

pub fn stream_for_priority(p: &Priority) -> &'static str {
    match p {
        Priority::High => STREAM_HIGH,
        Priority::Normal => STREAM_NORMAL,
        Priority::Low => STREAM_LOW,
    }
}

fn maxlen_for_priority(p: &Priority) -> u64 {
    match p {
        Priority::High => MAXLEN_HIGH,
        Priority::Normal => MAXLEN_NORMAL,
        Priority::Low => MAXLEN_LOW,
    }
}

pub fn priority_to_str(p: &Priority) -> &'static str {
    match p {
        Priority::High => "HIGH",
        Priority::Normal => "NORMAL",
        Priority::Low => "LOW",
    }
}

pub fn priority_from_str(s: &str) -> Result<Priority, AppError> {
    match s {
        "HIGH" => Ok(Priority::High),
        "NORMAL" => Ok(Priority::Normal),
        "LOW" => Ok(Priority::Low),
        other => Err(AppError::QueueError {
            queue: "parse".to_string(),
            message: format!("Unknown priority value: '{}'", other),
        }),
    }
}
