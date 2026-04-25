pub mod anthropic;
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
///
/// Returns an error if no API key is available for the required provider.
pub fn create_llm_provider(
    model: &str,
    config: &Arc<Config>,
) -> Result<Arc<dyn LlmProvider>, AppError> {
    let provider = Config::provider_for_model(model);

    match provider {
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
            )))
        }
    }
}
