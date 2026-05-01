/// Ollama provider — uses the OpenAI-compatible `/v1/chat/completions` API
/// exposed by Ollama at http://localhost:11434 (or OLLAMA_BASE_URL).
///
/// No API key required. Tool calling is supported from Ollama 0.3+ with
/// models that expose the `tools` capability (llama3.1, llama3.2, deepseek-r1, etc.)
use anyhow::{anyhow, Result};
use async_trait::async_trait;
use serde::{Deserialize, Serialize};
use tracing::{debug, instrument};

use crate::models::{
    FinishReason, FunctionCall, LlmResponse, Message, Role, Tool, ToolCall, UsageStats,
};

use super::LlmProvider;

pub struct OllamaProvider {
    client: reqwest::Client,
    base_url: String,
    model: String,
}

impl OllamaProvider {
    pub fn new(client: reqwest::Client, base_url: String, model: String) -> Self {
        Self {
            client,
            base_url,
            model,
        }
    }
}

// ---------------------------------------------------------------------------
// Request / response shapes (OpenAI-compatible subset)
// ---------------------------------------------------------------------------

#[derive(Serialize)]
struct OllamaRequest<'a> {
    model: &'a str,
    messages: Vec<OllamaMessage>,
    #[serde(skip_serializing_if = "Vec::is_empty")]
    tools: Vec<OllamaTool<'a>>,
    stream: bool,
    options: OllamaOptions,
}

#[derive(Serialize)]
struct OllamaOptions {
    temperature: f32,
    num_predict: u32,
    /// Context window size — smaller = faster KV cache, lower memory
    num_ctx: u32,
}

#[derive(Serialize, Deserialize, Clone)]
struct OllamaMessage {
    role: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    content: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    tool_calls: Option<Vec<OllamaToolCall>>,
    #[serde(skip_serializing_if = "Option::is_none")]
    tool_call_id: Option<String>,
}

#[derive(Serialize)]
struct OllamaTool<'a> {
    #[serde(rename = "type")]
    tool_type: &'static str,
    function: OllamaFunction<'a>,
}

#[derive(Serialize)]
struct OllamaFunction<'a> {
    name: &'a str,
    description: &'a str,
    parameters: &'a serde_json::Value,
}

#[derive(Serialize, Deserialize, Clone)]
struct OllamaToolCall {
    #[serde(default)]
    id: String,
    #[serde(rename = "type", default)]
    call_type: String,
    function: OllamaFunctionData,
}

#[derive(Serialize, Deserialize, Clone)]
struct OllamaFunctionData {
    name: String,
    /// Ollama may return arguments as a JSON Value directly instead of a string.
    #[serde(default)]
    arguments: serde_json::Value,
}

// Ollama non-streaming response (uses /api/chat)
#[derive(Deserialize)]
struct OllamaChatResponse {
    message: OllamaMessage,
    done: bool,
    #[serde(default)]
    prompt_eval_count: u32,
    #[serde(default)]
    eval_count: u32,
}

#[derive(Deserialize)]
struct OllamaErrorResponse {
    error: String,
}

// ---------------------------------------------------------------------------
// LlmProvider implementation
// ---------------------------------------------------------------------------

#[async_trait]
impl LlmProvider for OllamaProvider {
    #[instrument(skip(self, messages, tools), fields(model = %self.model, messages_count = messages.len()))]
    async fn complete(&self, messages: &[Message], tools: &[Tool]) -> Result<LlmResponse> {
        let ollama_messages: Vec<OllamaMessage> = messages
            .iter()
            .map(|m| OllamaMessage {
                role: role_to_ollama(&m.role),
                content: m.content.clone(),
                tool_calls: m.tool_calls.as_ref().map(|tcs| {
                    tcs.iter()
                        .map(|tc| OllamaToolCall {
                            id: tc.id.clone(),
                            call_type: tc.call_type.clone(),
                            function: OllamaFunctionData {
                                name: tc.function.name.clone(),
                                // Re-parse arguments string to Value for Ollama
                                arguments: serde_json::from_str(&tc.function.arguments)
                                    .unwrap_or(serde_json::Value::Object(Default::default())),
                            },
                        })
                        .collect()
                }),
                tool_call_id: m.tool_call_id.clone(),
            })
            .collect();

        let ollama_tools: Vec<OllamaTool> = tools
            .iter()
            .map(|t| OllamaTool {
                tool_type: "function",
                function: OllamaFunction {
                    name: &t.function.name,
                    description: &t.function.description,
                    parameters: &t.function.parameters,
                },
            })
            .collect();

        let endpoint = format!("{}/api/chat", self.base_url.trim_end_matches('/'));

        let request = OllamaRequest {
            model: &self.model,
            messages: ollama_messages,
            tools: ollama_tools,
            stream: false,
            options: OllamaOptions {
                temperature: 0.7,
                num_predict: 512,
                num_ctx: 4096,
            },
        };

        debug!(endpoint = %endpoint, "Calling Ollama /api/chat");

        let http_response = self.client.post(&endpoint).json(&request).send().await?;

        let status = http_response.status();

        if !status.is_success() {
            let body = http_response.text().await.unwrap_or_default();
            let message = serde_json::from_str::<OllamaErrorResponse>(&body)
                .map(|e| e.error)
                .unwrap_or(body);
            return Err(anyhow!("Ollama API error {}: {}", status, message));
        }

        let parsed: OllamaChatResponse = http_response.json().await?;

        if !parsed.done {
            return Err(anyhow!("Ollama returned done=false unexpectedly"));
        }

        // Normalise tool calls: Ollama arguments are JSON Value, not string
        let tool_calls: Vec<ToolCall> = parsed
            .message
            .tool_calls
            .unwrap_or_default()
            .into_iter()
            .enumerate()
            .map(|(i, tc)| {
                let args_str = match &tc.function.arguments {
                    serde_json::Value::String(s) => s.clone(),
                    v => v.to_string(),
                };
                ToolCall {
                    id: if tc.id.is_empty() {
                        format!("call_{i}")
                    } else {
                        tc.id
                    },
                    call_type: if tc.call_type.is_empty() {
                        "function".to_string()
                    } else {
                        tc.call_type
                    },
                    function: FunctionCall {
                        name: tc.function.name,
                        arguments: args_str,
                    },
                }
            })
            .collect();

        let finish_reason = if tool_calls.is_empty() {
            FinishReason::Stop
        } else {
            FinishReason::ToolCalls
        };

        let total = parsed.prompt_eval_count + parsed.eval_count;

        Ok(LlmResponse {
            content: parsed.message.content,
            tool_calls,
            finish_reason,
            usage: UsageStats {
                prompt_tokens: parsed.prompt_eval_count,
                completion_tokens: parsed.eval_count,
                total_tokens: total,
            },
        })
    }
}

fn role_to_ollama(role: &Role) -> String {
    match role {
        Role::System => "system",
        Role::User => "user",
        Role::Assistant => "assistant",
        Role::Tool => "tool",
    }
    .to_string()
}
