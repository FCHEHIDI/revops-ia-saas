pub mod anthropic;
pub mod ollama;
pub mod openai;

use anyhow::Result;
use async_trait::async_trait;
use std::sync::Arc;

use crate::{
    config::Config,
    error::AppError,
    models::{LlmResponse, Message, Tool},
};

/// Unified interface for LLM providers.
///
/// Both OpenAI and Anthropic implement this trait. The orchestrator calls
/// `complete` in the agentic loop — no streaming at the LLM-client level;
/// token streaming is handled above this layer by chunking the full response.
#[async_trait]
pub trait LlmProvider: Send + Sync {
    /// Send messages to the LLM and return a complete response.
    ///
    /// If the response contains `tool_calls`, the caller is expected to
    /// dispatch them and invoke `complete` again with the results appended.
    async fn complete(&self, messages: &[Message], tools: &[Tool]) -> Result<LlmResponse>;
}

/// Factory function — selects the appropriate provider based on model name prefix.
///
/// - `gpt-*` / `o1*` / `o3*` → OpenAI
/// - `claude-*`               → Anthropic
/// - `groq:*`                 → Groq (OpenAI-compatible, cloud, fast)
/// - `ollama:*`               → Ollama (OpenAI-compatible, local)
///
/// Returns an error if no API key is available for the required provider.
pub fn create_llm_provider(
    model: &str,
    config: &Arc<Config>,
) -> Result<Arc<dyn LlmProvider>, AppError> {
    let provider = Config::provider_for_model(model);

    match provider {
        "groq" => {
            let api_key = config
                .groq_api_key
                .clone()
                .ok_or_else(|| AppError::ConfigError("GROQ_API_KEY is not set".to_string()))?;

            // Strip prefix to get bare model name, e.g. "groq:llama-3.1-70b-versatile"
            let bare_model = model.strip_prefix("groq:").unwrap_or(model);

            Ok(Arc::new(openai::OpenAiProvider::new(
                reqwest::Client::builder()
                    .timeout(std::time::Duration::from_secs(30))
                    .build()
                    .map_err(|e| AppError::Internal(e.into()))?,
                api_key,
                bare_model.to_string(),
                "https://api.groq.com/openai/v1".to_string(),
            )))
        }
        "anthropic" => {
            let api_key = config
                .anthropic_api_key
                .clone()
                .ok_or_else(|| AppError::ConfigError("ANTHROPIC_API_KEY is not set".to_string()))?;

            Ok(Arc::new(anthropic::AnthropicProvider::new(
                reqwest::Client::builder()
                    .timeout(std::time::Duration::from_secs(120))
                    .build()
                    .map_err(|e| AppError::Internal(e.into()))?,
                api_key,
                model.to_string(),
            )))
        }
        "ollama" => {
            // Strip the "ollama:" prefix if present to get the bare model name
            let bare_model = model.strip_prefix("ollama:").unwrap_or(model);
            let base_url = config
                .ollama_base_url
                .clone()
                .unwrap_or_else(|| "http://localhost:11434".to_string());

            Ok(Arc::new(ollama::OllamaProvider::new(
                reqwest::Client::builder()
                    .timeout(std::time::Duration::from_secs(180))
                    .build()
                    .map_err(|e| AppError::Internal(e.into()))?,
                base_url,
                bare_model.to_string(),
            )))
        }
        _ => {
            let api_key = config
                .openai_api_key
                .clone()
                .ok_or_else(|| AppError::ConfigError("OPENAI_API_KEY is not set".to_string()))?;

            Ok(Arc::new(openai::OpenAiProvider::new(
                reqwest::Client::builder()
                    .timeout(std::time::Duration::from_secs(120))
                    .build()
                    .map_err(|e| AppError::Internal(e.into()))?,
                api_key,
                model.to_string(),
                "https://api.openai.com/v1".to_string(),
            )))
        }
    }
}
