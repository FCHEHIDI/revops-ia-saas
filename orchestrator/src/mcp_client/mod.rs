pub mod http_client;

use std::sync::Arc;

use crate::config::Config;
use crate::error::AppError;
pub use http_client::McpDispatcher;

/// Resolves the base URL for a given MCP server prefix.
///
/// Tool names follow the convention: `mcp_{server}__{tool_name}`
/// e.g. `mcp_crm__get_contact` → server prefix `mcp_crm` → `http://mcp-crm:9001`
pub fn resolve_server_url<'a>(config: &'a Arc<Config>, prefix: &str) -> Result<&'a str, AppError> {
    match prefix {
        "mcp_crm" => Ok(config.mcp_crm_url.as_str()),
        "mcp_billing" => Ok(config.mcp_billing_url.as_str()),
        "mcp_analytics" => Ok(config.mcp_analytics_url.as_str()),
        "mcp_sequences" => Ok(config.mcp_sequences_url.as_str()),
        "mcp_filesystem" => Ok(config.mcp_filesystem_url.as_str()),
        other => Err(AppError::McpError {
            server: other.to_string(),
            message: format!(
                "Unknown MCP server prefix '{}'. \
                 Valid prefixes: mcp_crm, mcp_billing, mcp_analytics, mcp_sequences, mcp_filesystem",
                other
            ),
        }),
    }
}

/// Parses a tool name in the form `mcp_{server}__{tool}` into `(prefix, tool)`.
pub fn parse_tool_name(tool_name: &str) -> Result<(&str, &str), AppError> {
    match tool_name.find("__") {
        Some(idx) => Ok((&tool_name[..idx], &tool_name[idx + 2..])),
        None => Err(AppError::McpError {
            server: "unknown".to_string(),
            message: format!(
                "Invalid tool name '{}'. Expected format: mcp_{{server}}__{{tool_name}}",
                tool_name
            ),
        }),
    }
}
