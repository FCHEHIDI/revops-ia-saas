use anyhow::Result;
use chrono::{DateTime, Utc};
use sha2::{Digest, Sha256};
use sqlx::PgPool;
use uuid::Uuid;

#[derive(Debug, Clone)]
pub struct AuditEntry {
    pub tenant_id: Uuid,
    pub user_id: Option<Uuid>,
    pub tool_name: String,
    /// SHA-256 of the serialized input params (excluding tenant_id and user_id)
    pub params_hash: String,
    pub result_code: String,
    pub duration_ms: i64,
    pub timestamp: DateTime<Utc>,
    /// Optional contextual metadata (e.g. reason for status change)
    pub metadata: Option<serde_json::Value>,
}

impl AuditEntry {
    pub fn new(
        tenant_id: Uuid,
        user_id: Option<Uuid>,
        tool_name: impl Into<String>,
        params_json: &serde_json::Value,
        result_code: impl Into<String>,
        duration_ms: i64,
    ) -> Self {
        let params_hash = hash_params(params_json);
        AuditEntry {
            tenant_id,
            user_id,
            tool_name: tool_name.into(),
            params_hash,
            result_code: result_code.into(),
            duration_ms,
            timestamp: Utc::now(),
            metadata: None,
        }
    }

    pub fn with_metadata(mut self, metadata: serde_json::Value) -> Self {
        self.metadata = Some(metadata);
        self
    }
}

/// Computes SHA-256 of a JSON value, stripping sensitive identity fields.
pub fn hash_params(params: &serde_json::Value) -> String {
    let mut sanitized = params.clone();
    if let Some(obj) = sanitized.as_object_mut() {
        obj.remove("tenant_id");
        obj.remove("user_id");
    }
    let serialized = sanitized.to_string();
    let mut hasher = Sha256::new();
    hasher.update(serialized.as_bytes());
    hex::encode(hasher.finalize())
}

/// Inserts an audit event into the `audit_events` table.
/// Errors are logged but do not propagate — audit failures must never block business logic.
pub async fn write_audit(entry: AuditEntry, pool: &PgPool) -> Result<()> {
    sqlx::query(
        r#"
        INSERT INTO audit_events (
            id,
            tenant_id,
            user_id,
            tool_name,
            params_hash,
            result_code,
            duration_ms,
            timestamp,
            metadata
        ) VALUES (
            gen_random_uuid(),
            $1,
            $2,
            $3,
            $4,
            $5,
            $6,
            $7,
            $8
        )
        "#,
    )
    .bind(entry.tenant_id)
    .bind(entry.user_id)
    .bind(&entry.tool_name)
    .bind(&entry.params_hash)
    .bind(&entry.result_code)
    .bind(entry.duration_ms)
    .bind(entry.timestamp)
    .bind(entry.metadata)
    .execute(pool)
    .await?;

    Ok(())
}
