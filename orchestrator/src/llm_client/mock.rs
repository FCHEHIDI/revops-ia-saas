use anyhow::Result;
use async_trait::async_trait;
use uuid::Uuid;

use crate::models::{FinishReason, FunctionCall, LlmResponse, Message, Tool, ToolCall, UsageStats};

use super::LlmProvider;

/// Deterministic mock LLM provider for E2E tests without a real API key.
///
/// Turn 1 (no prior tool results in messages): returns a `tool_call` on
/// `mcp_crm__list_contacts` with `{"tenant_id":"<tenant>", "limit": 5}`.
///
/// Turn 2+ (tool results present): returns a canned text summary.
pub struct MockProvider;

#[async_trait]
impl LlmProvider for MockProvider {
    async fn complete(&self, messages: &[Message], _tools: &[Tool]) -> Result<LlmResponse> {
        // Check if we already have tool results in the conversation
        let has_tool_results = messages
            .iter()
            .any(|m| m.tool_call_id.is_some());

        if has_tool_results {
            // Final answer turn — return a canned summary
            Ok(LlmResponse {
                content: Some(
                    "Voici les contacts récupérés depuis le CRM. \
                     Le mock LLM a bien traité les résultats de l'outil mcp_crm__search_contacts."
                        .to_string(),
                ),
                tool_calls: vec![],
                finish_reason: FinishReason::Stop,
                usage: UsageStats {
                    prompt_tokens: 120,
                    completion_tokens: 32,
                    total_tokens: 152,
                },
            })
        } else {
            // First turn — simulate a tool_call on crm.list_contacts
            // Extract tenant_id from the last system message if possible
            let tenant_id = messages
                .iter()
                .find(|m| m.content.as_deref().unwrap_or("").contains("tenant"))
                .and_then(|_| None::<String>)
                .unwrap_or_else(|| "00000000-0000-0000-0000-000000000001".to_string());

            Ok(LlmResponse {
                content: None,
                tool_calls: vec![ToolCall {
                    id: Uuid::new_v4().to_string(),
                    call_type: "function".to_string(),
                    function: FunctionCall {
                        name: "mcp_crm__search_contacts".to_string(),
                        arguments: format!(
                            r#"{{"tenant_id": "{}", "limit": 5}}"#,
                            tenant_id
                        ),
                    },
                }],
                finish_reason: FinishReason::ToolCalls,
                usage: UsageStats {
                    prompt_tokens: 80,
                    completion_tokens: 20,
                    total_tokens: 100,
                },
            })
        }
    }
}
