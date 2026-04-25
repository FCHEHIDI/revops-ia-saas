use std::sync::Arc;

use tracing::{debug, instrument, warn};

use crate::{
    config::Config,
    error::AppError,
    models::{McpCallRequest, McpCallResponse},
};

use super::{parse_tool_name, resolve_server_url};

/// Dispatches LLM tool calls to the appropriate MCP HTTP server.
///
/// Each MCP server exposes `POST /mcp/call` and accepts:
/// ```json
/// { "tool": "get_contact", "params": {...}, "tenant_id": "..." }
/// ```
///
/// The server validates `tenant_id` before executing any action.
/// This ensures the MCP layer enforces tenant isolation independently
/// of the orchestrator.
/// `reqwest::Client` and `Arc<Config>` are both cheap to clone (Arc-backed).
#[derive(Clone)]
pub struct McpDispatcher {
    http_client: reqwest::Client,
    config: Arc<Config>,
}

impl McpDispatcher {
    pub fn new(http_client: reqwest::Client, config: Arc<Config>) -> Self {
        Self {
            http_client,
            config,
        }
    }

    /// Dispatch a single tool call to its MCP server.
    ///
    /// Retries up to 3 times with exponential backoff on transient errors.
    #[instrument(skip(self, params), fields(tool = %tool_name, tenant_id = %tenant_id))]
    pub async fn call(
        &self,
        tool_name: &str,
        params: serde_json::Value,
        tenant_id: &str,
    ) -> Result<serde_json::Value, AppError> {
        let (prefix, tool) = parse_tool_name(tool_name)?;
        let server_url = resolve_server_url(&self.config, prefix)?;
        let endpoint = format!("{}/mcp/call", server_url);

        let request_body = McpCallRequest {
            tool: tool.to_string(),
            params,
            tenant_id: tenant_id.to_string(),
        };

        debug!(server = %prefix, tool = %tool, endpoint = %endpoint, "Dispatching MCP call");

        let result = retry_with_backoff(|| {
            let client = self.http_client.clone();
            let endpoint = endpoint.clone();
            let body = request_body.clone();
            let secret = self.config.inter_service_secret.clone();

            async move {
                client
                    .post(&endpoint)
                    .header("X-Internal-API-Key", &secret)
                    .json(&body)
                    .send()
                    .await
            }
        })
        .await
        .map_err(|e| AppError::McpError {
            server: prefix.to_string(),
            message: format!("HTTP request failed: {}", e),
        })?;

        let status = result.status();

        if !status.is_success() {
            let body = result.text().await.unwrap_or_default();
            return Err(AppError::McpError {
                server: prefix.to_string(),
                message: format!("Server returned {}: {}", status, body),
            });
        }

        let response: McpCallResponse = result.json().await.map_err(|e| AppError::McpError {
            server: prefix.to_string(),
            message: format!("Failed to parse MCP response: {}", e),
        })?;

        if let Some(err) = response.error {
            return Err(AppError::McpError {
                server: prefix.to_string(),
                message: err,
            });
        }

        Ok(response.result.unwrap_or(serde_json::Value::Null))
    }
}

/// Retry an async operation up to `MAX_RETRIES` times with exponential backoff.
///
/// Only retries on network/timeout errors (not 4xx/5xx HTTP errors).
async fn retry_with_backoff<F, Fut>(f: F) -> Result<reqwest::Response, reqwest::Error>
where
    F: Fn() -> Fut,
    Fut: std::future::Future<Output = Result<reqwest::Response, reqwest::Error>>,
{
    const MAX_RETRIES: u32 = 3;
    let mut delay_ms = 100u64;

    for attempt in 1..=MAX_RETRIES {
        match f().await {
            Ok(resp) => return Ok(resp),
            Err(e) if attempt < MAX_RETRIES && (e.is_timeout() || e.is_connect()) => {
                warn!(
                    attempt,
                    delay_ms,
                    error = %e,
                    "MCP call failed, retrying"
                );
                tokio::time::sleep(std::time::Duration::from_millis(delay_ms)).await;
                delay_ms *= 2;
            }
            Err(e) => return Err(e),
        }
    }

    unreachable!("Loop always returns")
}
