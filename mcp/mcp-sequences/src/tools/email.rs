use serde::{Deserialize, Serialize};
use serde_json::json;
use sqlx::PgPool;
use tracing::{error, instrument, warn};
use uuid::Uuid;

use crate::audit::{write_audit, AuditEntry};
use crate::db::validate_tenant;
use crate::errors::SequencesError;

// ---------------------------------------------------------------------------
// send_step_email
// ---------------------------------------------------------------------------

/// Input for the `send_step_email` MCP tool.
///
/// Fetches the email step at `step_index` from the sequence, renders the
/// template against the contact's variables, and enqueues the send via the
/// backend's internal email endpoint.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SendStepEmailInput {
    pub tenant_id: Uuid,
    pub user_id: Uuid,
    pub sequence_id: Uuid,
    pub contact_id: Uuid,
    pub step_index: i32,
    /// Override the backend URL (useful in tests / local dev).
    pub backend_url: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SendStepEmailOutput {
    pub email_send_id: String,
    pub to_email: String,
    pub subject: String,
    pub status: String,
}

#[instrument(skip(pool), fields(tool = "send_step_email"))]
pub async fn send_step_email(
    input: SendStepEmailInput,
    pool: &PgPool,
    inter_service_secret: &str,
    backend_base_url: &str,
) -> Result<SendStepEmailOutput, SequencesError> {
    let start = std::time::Instant::now();
    validate_tenant(input.tenant_id, pool).await?;

    // 1. Resolve the email step at position == step_index
    let step = sqlx::query!(
        r#"
        SELECT id, subject, body_template
        FROM sequence_steps
        WHERE sequence_id = $1
          AND tenant_id   = $2
          AND position    = $3
          AND step_type   = 'email'
        "#,
        input.sequence_id,
        input.tenant_id,
        input.step_index,
    )
    .fetch_optional(pool)
    .await
    .map_err(SequencesError::DatabaseError)?;

    let step = step.ok_or_else(|| {
        SequencesError::NotFound(format!(
            "email step at position {} in sequence {}",
            input.step_index, input.sequence_id
        ))
    })?;

    let subject = step.subject.unwrap_or_default();
    let body_template = step.body_template.unwrap_or_default();
    if subject.is_empty() {
        return Err(SequencesError::ValidationError(
            "step has no subject — cannot send".into(),
        ));
    }

    // 2. Resolve contact email
    let contact = sqlx::query!(
        "SELECT id, email, first_name, last_name FROM contacts WHERE id = $1 AND org_id = $2",
        input.contact_id,
        input.tenant_id,
    )
    .fetch_optional(pool)
    .await
    .map_err(SequencesError::DatabaseError)?
    .ok_or(SequencesError::ContactNotFound(input.contact_id))?;

    let to_email = contact.email.clone().unwrap_or_default();
    if to_email.is_empty() {
        return Err(SequencesError::ValidationError(format!(
            "contact {} has no email address",
            input.contact_id
        )));
    }

    // 3. Simple template variable substitution: {{first_name}}, {{last_name}}
    let first_name = contact.first_name.clone().unwrap_or_default();
    let last_name = contact.last_name.clone().unwrap_or_default();
    let body_html = body_template
        .replace("{{first_name}}", &first_name)
        .replace("{{last_name}}", &last_name)
        .replace("{{full_name}}", &format!("{first_name} {last_name}").trim().to_string());

    // 4. Call backend /internal/v1/email/enqueue
    let override_url = input.backend_url.as_deref().unwrap_or(backend_base_url);
    let enqueue_url = format!("{override_url}/internal/v1/email/enqueue");

    let payload = json!({
        "tenant_id":   input.tenant_id,
        "contact_id":  input.contact_id,
        "to_email":    to_email,
        "subject":     subject,
        "body_html":   body_html,
        "sequence_id": input.sequence_id,
        "step_index":  input.step_index,
    });

    let client = reqwest::Client::new();
    let resp = client
        .post(&enqueue_url)
        .header("x-inter-service-secret", inter_service_secret)
        .header("content-type", "application/json")
        .body(payload.to_string())
        .send()
        .await
        .map_err(|e| SequencesError::InternalError(anyhow::anyhow!("backend request failed: {e}")))?;

    if !resp.status().is_success() {
        let status_code = resp.status().as_u16();
        let body = resp.text().await.unwrap_or_default();
        error!(
            "send_step_email: backend returned {status_code}: {body}"
        );
        return Err(SequencesError::InternalError(anyhow::anyhow!(
            "email enqueue failed (HTTP {status_code}): {body}"
        )));
    }

    let resp_json: serde_json::Value = resp
        .json()
        .await
        .map_err(|e| SequencesError::InternalError(anyhow::anyhow!("invalid JSON from backend: {e}")))?;

    let email_send_id = resp_json["id"]
        .as_str()
        .unwrap_or("unknown")
        .to_string();

    let duration_ms = start.elapsed().as_millis() as i64;
    let _ = write_audit(
        AuditEntry::new(
            input.tenant_id,
            Some(input.user_id),
            "send_step_email",
            &json!({
                "sequence_id": input.sequence_id,
                "contact_id":  input.contact_id,
                "step_index":  input.step_index,
                "to_email":    to_email,
                "email_send_id": email_send_id,
            }),
            "ENQUEUED",
            duration_ms,
        ),
        pool,
    )
    .await;

    Ok(SendStepEmailOutput {
        email_send_id,
        to_email,
        subject,
        status: "pending".to_string(),
    })
}
