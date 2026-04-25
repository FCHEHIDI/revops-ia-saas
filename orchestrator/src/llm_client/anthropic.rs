use anyhow::{anyhow, Result};
use async_trait::async_trait;
use serde::{Deserialize, Serialize};
use tracing::{debug, instrument};

use crate::models::{
    FinishReason, FunctionCall, LlmResponse, Message, Role, Tool, ToolCall, UsageStats,
};

use super::LlmProvider;

pub struct AnthropicProvider {
    client: reqwest::Client,
    api_key: String,
    model: String,
}

impl AnthropicProvider {
    pub fn new(client: reqwest::Client, api_key: String, model: String) -> Self {
        Self {
            client,
            api_key,
            model,
        }
    }
}

const ANTHROPIC_API_URL: &str = "https://api.anthropic.com/v1/messages";
const ANTHROPIC_VERSION: &str = "2023-06-01";
const MAX_TOKENS: u32 = 4096;

// ---------------------------------------------------------------------------
// Anthropic request types
// ---------------------------------------------------------------------------

#[derive(Serialize)]
struct AnthropicRequest {
    model: String,
    max_tokens: u32,
    #[serde(skip_serializing_if = "Option::is_none")]
    system: Option<String>,
    messages: Vec<AnthropicMessage>,
    #[serde(skip_serializing_if = "Vec::is_empty")]
    tools: Vec<AnthropicTool>,
}

#[derive(Serialize)]
struct AnthropicMessage {
    role: String,
    content: AnthropicContent,
}

#[derive(Serialize)]
#[serde(untagged)]
enum AnthropicContent {
    Text(String),
    Blocks(Vec<AnthropicBlock>),
}

#[derive(Serialize)]
#[serde(tag = "type", rename_all = "snake_case")]
enum AnthropicBlock {
    Text {
        text: String,
    },
    ToolUse {
        id: String,
        name: String,
        input: serde_json::Value,
    },
    ToolResult {
        tool_use_id: String,
        content: String,
    },
}

#[derive(Serialize)]
struct AnthropicTool {
    name: String,
    description: String,
    input_schema: serde_json::Value,
}

// ---------------------------------------------------------------------------
// Anthropic response types
// ---------------------------------------------------------------------------

#[derive(Deserialize)]
struct AnthropicResponse {
    content: Vec<AnthropicResponseBlock>,
    stop_reason: Option<String>,
    usage: AnthropicUsage,
}

#[derive(Deserialize)]
#[serde(tag = "type", rename_all = "snake_case")]
enum AnthropicResponseBlock {
    Text {
        text: String,
    },
    ToolUse {
        id: String,
        name: String,
        input: serde_json::Value,
    },
}

#[derive(Deserialize)]
struct AnthropicUsage {
    input_tokens: u32,
    output_tokens: u32,
}

#[derive(Deserialize)]
struct AnthropicErrorResponse {
    error: AnthropicError,
}

#[derive(Deserialize)]
struct AnthropicError {
    message: String,
}

// ---------------------------------------------------------------------------
// LlmProvider implementation
// ---------------------------------------------------------------------------

#[async_trait]
impl LlmProvider for AnthropicProvider {
    #[instrument(skip(self, messages, tools), fields(model = %self.model, messages_count = messages.len()))]
    async fn complete(&self, messages: &[Message], tools: &[Tool]) -> Result<LlmResponse> {
        // Anthropic separates the system prompt from the messages array
        let system_prompt = messages
            .iter()
            .find(|m| m.role == Role::System)
            .and_then(|m| m.content.clone());

        let anthropic_messages = build_anthropic_messages(messages);

        let anthropic_tools: Vec<AnthropicTool> = tools
            .iter()
            .map(|t| AnthropicTool {
                name: t.function.name.clone(),
                description: t.function.description.clone(),
                input_schema: t.function.parameters.clone(),
            })
            .collect();

        let request = AnthropicRequest {
            model: self.model.clone(),
            max_tokens: MAX_TOKENS,
            system: system_prompt,
            messages: anthropic_messages,
            tools: anthropic_tools,
        };

        debug!("Calling Anthropic Messages API");

        let http_response = self
            .client
            .post(ANTHROPIC_API_URL)
            .header("x-api-key", &self.api_key)
            .header("anthropic-version", ANTHROPIC_VERSION)
            .json(&request)
            .send()
            .await?;

        let status = http_response.status();

        if !status.is_success() {
            let body = http_response.text().await.unwrap_or_default();
            let message = serde_json::from_str::<AnthropicErrorResponse>(&body)
                .map(|e| e.error.message)
                .unwrap_or(body);
            return Err(anyhow!("Anthropic API error {}: {}", status, message));
        }

        let parsed: AnthropicResponse = http_response.json().await?;

        let finish_reason = match parsed.stop_reason.as_deref() {
            Some("tool_use") => FinishReason::ToolCalls,
            Some("max_tokens") => FinishReason::Length,
            _ => FinishReason::Stop,
        };

        let mut text_content = String::new();
        let mut tool_calls: Vec<ToolCall> = vec![];

        for block in parsed.content {
            match block {
                AnthropicResponseBlock::Text { text } => {
                    text_content.push_str(&text);
                }
                AnthropicResponseBlock::ToolUse { id, name, input } => {
                    let arguments = serde_json::to_string(&input).unwrap_or_default();
                    tool_calls.push(ToolCall {
                        id,
                        call_type: "function".to_string(),
                        function: FunctionCall { name, arguments },
                    });
                }
            }
        }

        let content = if text_content.is_empty() {
            None
        } else {
            Some(text_content)
        };

        Ok(LlmResponse {
            content,
            tool_calls,
            finish_reason,
            usage: UsageStats {
                prompt_tokens: parsed.usage.input_tokens,
                completion_tokens: parsed.usage.output_tokens,
                total_tokens: parsed.usage.input_tokens + parsed.usage.output_tokens,
            },
        })
    }
}

/// Convert our internal messages to Anthropic format.
///
/// Key differences from OpenAI:
/// - System messages are extracted and sent in a dedicated `system` field
/// - Tool results use `tool_result` content blocks (not a separate role)
/// - Assistant messages with tool calls use `tool_use` content blocks
fn build_anthropic_messages(messages: &[Message]) -> Vec<AnthropicMessage> {
    let mut result = vec![];

    for msg in messages {
        match msg.role {
            // System messages are handled separately; skip them here
            Role::System => continue,

            Role::User => {
                result.push(AnthropicMessage {
                    role: "user".to_string(),
                    content: AnthropicContent::Text(msg.content.clone().unwrap_or_default()),
                });
            }

            Role::Assistant => {
                // If the assistant message contains tool calls, encode as blocks
                if let Some(ref tool_calls) = msg.tool_calls {
                    let mut blocks = vec![];

                    if let Some(ref text) = msg.content {
                        if !text.is_empty() {
                            blocks.push(AnthropicBlock::Text { text: text.clone() });
                        }
                    }

                    for tc in tool_calls {
                        let input: serde_json::Value = serde_json::from_str(&tc.function.arguments)
                            .unwrap_or(serde_json::Value::Null);

                        blocks.push(AnthropicBlock::ToolUse {
                            id: tc.id.clone(),
                            name: tc.function.name.clone(),
                            input,
                        });
                    }

                    result.push(AnthropicMessage {
                        role: "assistant".to_string(),
                        content: AnthropicContent::Blocks(blocks),
                    });
                } else {
                    result.push(AnthropicMessage {
                        role: "assistant".to_string(),
                        content: AnthropicContent::Text(msg.content.clone().unwrap_or_default()),
                    });
                }
            }

            Role::Tool => {
                let tool_use_id = msg.tool_call_id.clone().unwrap_or_default();
                let content = msg.content.clone().unwrap_or_default();

                result.push(AnthropicMessage {
                    role: "user".to_string(),
                    content: AnthropicContent::Blocks(vec![AnthropicBlock::ToolResult {
                        tool_use_id,
                        content,
                    }]),
                });
            }
        }
    }

    result
}
