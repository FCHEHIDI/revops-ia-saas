use anyhow::{anyhow, Result};
use async_trait::async_trait;
use serde::{Deserialize, Serialize};
use tracing::{debug, instrument};

use crate::models::{FinishReason, FunctionCall, LlmResponse, Message, Role, Tool, ToolCall, UsageStats};

use super::LlmProvider;

pub struct OpenAiProvider {
    client: reqwest::Client,
    api_key: String,
    model: String,
}

impl OpenAiProvider {
    pub fn new(client: reqwest::Client, api_key: String, model: String) -> Self {
        Self { client, api_key, model }
    }
}

// ---------------------------------------------------------------------------
// OpenAI request types
// ---------------------------------------------------------------------------

#[derive(Serialize)]
struct OpenAiRequest<'a> {
    model: &'a str,
    messages: Vec<OpenAiMessage>,
    #[serde(skip_serializing_if = "Vec::is_empty")]
    tools: Vec<OpenAiTool<'a>>,
    max_tokens: u32,
    temperature: f32,
}

#[derive(Serialize, Deserialize, Clone)]
struct OpenAiMessage {
    role: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    content: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    tool_calls: Option<Vec<OpenAiToolCall>>,
    #[serde(skip_serializing_if = "Option::is_none")]
    tool_call_id: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    name: Option<String>,
}

#[derive(Serialize)]
struct OpenAiTool<'a> {
    #[serde(rename = "type")]
    tool_type: &'static str,
    function: OpenAiFunction<'a>,
}

#[derive(Serialize)]
struct OpenAiFunction<'a> {
    name: &'a str,
    description: &'a str,
    parameters: &'a serde_json::Value,
}

#[derive(Serialize, Deserialize, Clone)]
struct OpenAiToolCall {
    id: String,
    #[serde(rename = "type")]
    call_type: String,
    function: OpenAiFunctionData,
}

#[derive(Serialize, Deserialize, Clone)]
struct OpenAiFunctionData {
    name: String,
    arguments: String,
}

// ---------------------------------------------------------------------------
// OpenAI response types
// ---------------------------------------------------------------------------

#[derive(Deserialize)]
struct OpenAiResponse {
    choices: Vec<OpenAiChoice>,
    usage: OpenAiUsage,
}

#[derive(Deserialize)]
struct OpenAiChoice {
    message: OpenAiMessage,
    finish_reason: Option<String>,
}

#[derive(Deserialize)]
struct OpenAiUsage {
    prompt_tokens: u32,
    completion_tokens: u32,
    total_tokens: u32,
}

// ---------------------------------------------------------------------------
// OpenAI error response
// ---------------------------------------------------------------------------

#[derive(Deserialize)]
struct OpenAiErrorResponse {
    error: OpenAiError,
}

#[derive(Deserialize)]
struct OpenAiError {
    message: String,
}

// ---------------------------------------------------------------------------
// LlmProvider implementation
// ---------------------------------------------------------------------------

#[async_trait]
impl LlmProvider for OpenAiProvider {
    #[instrument(skip(self, messages, tools), fields(model = %self.model, messages_count = messages.len()))]
    async fn complete(&self, messages: &[Message], tools: &[Tool]) -> Result<LlmResponse> {
        let openai_messages: Vec<OpenAiMessage> = messages
            .iter()
            .map(|m| OpenAiMessage {
                role: role_to_openai(&m.role),
                content: m.content.clone(),
                tool_calls: m.tool_calls.as_ref().map(|tcs| {
                    tcs.iter()
                        .map(|tc| OpenAiToolCall {
                            id: tc.id.clone(),
                            call_type: tc.call_type.clone(),
                            function: OpenAiFunctionData {
                                name: tc.function.name.clone(),
                                arguments: tc.function.arguments.clone(),
                            },
                        })
                        .collect()
                }),
                tool_call_id: m.tool_call_id.clone(),
                name: m.name.clone(),
            })
            .collect();

        let openai_tools: Vec<OpenAiTool> = tools
            .iter()
            .map(|t| OpenAiTool {
                tool_type: "function",
                function: OpenAiFunction {
                    name: &t.function.name,
                    description: &t.function.description,
                    parameters: &t.function.parameters,
                },
            })
            .collect();

        let request = OpenAiRequest {
            model: &self.model,
            messages: openai_messages,
            tools: openai_tools,
            max_tokens: 4096,
            temperature: 0.7,
        };

        debug!("Calling OpenAI chat completions API");

        let http_response = self
            .client
            .post("https://api.openai.com/v1/chat/completions")
            .bearer_auth(&self.api_key)
            .json(&request)
            .send()
            .await?;

        let status = http_response.status();

        if !status.is_success() {
            let body = http_response.text().await.unwrap_or_default();
            let message = serde_json::from_str::<OpenAiErrorResponse>(&body)
                .map(|e| e.error.message)
                .unwrap_or(body);
            return Err(anyhow!("OpenAI API error {}: {}", status, message));
        }

        let parsed: OpenAiResponse = http_response.json().await?;

        let choice = parsed
            .choices
            .into_iter()
            .next()
            .ok_or_else(|| anyhow!("Empty choices in OpenAI response"))?;

        let finish_reason = match choice.finish_reason.as_deref() {
            Some("tool_calls") => FinishReason::ToolCalls,
            Some("length") => FinishReason::Length,
            _ => FinishReason::Stop,
        };

        let tool_calls: Vec<ToolCall> = choice
            .message
            .tool_calls
            .unwrap_or_default()
            .into_iter()
            .map(|tc| ToolCall {
                id: tc.id,
                call_type: tc.call_type,
                function: FunctionCall {
                    name: tc.function.name,
                    arguments: tc.function.arguments,
                },
            })
            .collect();

        Ok(LlmResponse {
            content: choice.message.content,
            tool_calls,
            finish_reason,
            usage: UsageStats {
                prompt_tokens: parsed.usage.prompt_tokens,
                completion_tokens: parsed.usage.completion_tokens,
                total_tokens: parsed.usage.total_tokens,
            },
        })
    }
}

fn role_to_openai(role: &Role) -> String {
    match role {
        Role::System => "system",
        Role::User => "user",
        Role::Assistant => "assistant",
        Role::Tool => "tool",
    }
    .to_string()
}
