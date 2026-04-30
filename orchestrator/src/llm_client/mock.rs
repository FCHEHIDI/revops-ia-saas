use anyhow::Result;
use async_trait::async_trait;
use uuid::Uuid;

use crate::models::{FinishReason, FunctionCall, LlmResponse, Message, Tool, ToolCall, UsageStats};

use super::LlmProvider;

/// Deterministic mock LLM provider for E2E tests without a real API key.
///
/// Multi-service scenario (3 turns):
///   Turn 1 — no tool results yet → calls `mcp_billing__list_overdue_payments`
///   Turn 2 — 1 tool result       → calls `mcp_analytics__get_mrr_trend`
///   Turn 3 — 2+ tool results     → returns a canned cross-service summary
pub struct MockProvider;

#[async_trait]
impl LlmProvider for MockProvider {
    async fn complete(&self, messages: &[Message], _tools: &[Tool]) -> Result<LlmResponse> {
        // Count how many tool results are already in the conversation
        let tool_result_count = messages
            .iter()
            .filter(|m| m.tool_call_id.is_some())
            .count();

        // Extract tenant_id from the system message context
        let tenant_id = messages
            .iter()
            .find(|m| m.content.as_deref().unwrap_or("").contains("tenant"))
            .and_then(|_| None::<String>)
            .unwrap_or_else(|| "00000000-0000-0000-0000-000000000001".to_string());

        match tool_result_count {
            0 => {
                // Turn 1 — ask for overdue payments from billing
                Ok(LlmResponse {
                    content: None,
                    tool_calls: vec![ToolCall {
                        id: Uuid::new_v4().to_string(),
                        call_type: "function".to_string(),
                        function: FunctionCall {
                            name: "mcp_billing__list_overdue_payments".to_string(),
                            arguments: format!(r#"{{"tenant_id": "{}"}}"#, tenant_id),
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
            1 => {
                // Turn 2 — now fetch MRR trend from analytics
                Ok(LlmResponse {
                    content: None,
                    tool_calls: vec![ToolCall {
                        id: Uuid::new_v4().to_string(),
                        call_type: "function".to_string(),
                        function: FunctionCall {
                            name: "mcp_analytics__get_mrr_trend".to_string(),
                            arguments: format!(
                                r#"{{"tenant_id": "{}", "months": 3}}"#,
                                tenant_id
                            ),
                        },
                    }],
                    finish_reason: FinishReason::ToolCalls,
                    usage: UsageStats {
                        prompt_tokens: 120,
                        completion_tokens: 22,
                        total_tokens: 142,
                    },
                })
            }
            _ => {
                // Turn 3+ — synthesise a cross-service summary
                Ok(LlmResponse {
                    content: Some(
                        "Synthèse RevOps : j'ai consulté les paiements en retard (billing) \
                         ainsi que la tendance MRR sur 3 mois (analytics). \
                         Les données confirment une croissance MRR stable malgré quelques \
                         factures impayées à relancer en priorité."
                            .to_string(),
                    ),
                    tool_calls: vec![],
                    finish_reason: FinishReason::Stop,
                    usage: UsageStats {
                        prompt_tokens: 200,
                        completion_tokens: 48,
                        total_tokens: 248,
                    },
                })
            }
        }
    }
}
