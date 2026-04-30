use std::sync::Arc;

use tracing::debug;

use crate::{config::Config, models::Priority, models::ProcessRequest};

/// Selects the LLM model for a given request based on priority and context.
///
/// Routing rules (ADR-002: prioritized queue):
/// - `HIGH`   → fastest available model for interactive latency (≤2s goal)
/// - `NORMAL` → default configured model (best balance quality/cost)
/// - `LOW`    → cheaper model for batch processing if available
pub struct ModelRouter {
    config: Arc<Config>,
}

impl ModelRouter {
    pub fn new(config: Arc<Config>) -> Self {
        Self { config }
    }

    pub fn select_model(&self, req: &ProcessRequest) -> String {
        let model = match req.priority {
            Priority::High => self.fast_model(),
            Priority::Normal => self.config.default_model.clone(),
            Priority::Low => self.economy_model(),
        };

        debug!(
            priority = ?req.priority,
            model = %model,
            "Model selected"
        );

        model
    }

    /// Fast model for interactive (HIGH priority) requests.
    ///
    /// Uses the default model but could be overridden to a faster variant
    /// (e.g. `gpt-4o-mini` or `claude-3-haiku`) based on latency requirements.
    fn fast_model(&self) -> String {
        let default = &self.config.default_model;

        // Map to the fastest variant of the same provider family
        if default.starts_with("claude-3-5-sonnet") {
            "claude-3-haiku-20240307".to_string()
        } else if default.starts_with("gpt-4") {
            "gpt-4o-mini".to_string()
        } else {
            default.clone()
        }
    }

    /// Economy model for LOW priority batch requests.
    ///
    /// Uses cheaper models to optimize cost for non-interactive workloads.
    fn economy_model(&self) -> String {
        let default = &self.config.default_model;

        if default.starts_with("claude-") {
            "claude-3-haiku-20240307".to_string()
        } else if default.starts_with("gpt-4") {
            "gpt-4o-mini".to_string()
        } else {
            default.clone()
        }
    }
}
