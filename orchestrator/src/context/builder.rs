use std::sync::Arc;

use tracing::{debug, info, warn};

use crate::{
    config::Config,
    error::AppError,
    models::{ConversationMessage, Message, ProcessRequest, RagChunk, Role, Tool, ToolFunction},
    rag_client::client::RagClient,
};

/// Assembled LLM context ready for the first provider call.
pub struct ConversationContext {
    pub messages: Vec<Message>,
    pub tools: Vec<Tool>,
}

/// Builds the full stateless context for one orchestrator request:
///
/// 1. Fetches conversation history from the Backend API
/// 2. Retrieves relevant document chunks from the RAG layer
/// 3. Assembles the system prompt (role + RAG excerpts)
/// 4. Produces the ordered `messages` array and the `tools` list
pub struct ContextBuilder {
    http_client: reqwest::Client,
    config: Arc<Config>,
}

impl ContextBuilder {
    pub fn new(http_client: reqwest::Client, config: Arc<Config>) -> Self {
        Self { http_client, config }
    }

    pub async fn build(
        &self,
        req: &ProcessRequest,
        rag_client: &RagClient,
    ) -> Result<ConversationContext, AppError> {
        // Fetch history and RAG in parallel for lower latency
        let tenant_id_str = req.tenant_id.to_string();
        let (history_result, rag_result) = tokio::join!(
            self.fetch_history(req),
            rag_client.retrieve(&tenant_id_str, &req.message, 5),
        );

        let history = history_result?;
        let chunks = rag_result.unwrap_or_else(|e| {
            warn!(error = %e, "RAG retrieval failed — continuing without context");
            vec![]
        });

        info!(
            history_len = history.len(),
            rag_chunks = chunks.len(),
            "Context assembled"
        );

        let system_prompt = build_system_prompt(&chunks);

        let mut messages: Vec<Message> = Vec::with_capacity(history.len() + 2);
        messages.push(Message::system(system_prompt));

        for msg in history {
            messages.push(history_to_message(msg));
        }

        messages.push(Message::user(req.message.clone()));

        let tools = default_tool_definitions();

        Ok(ConversationContext { messages, tools })
    }

    /// GET {backend}/internal/conversations/{id}/messages
    ///
    /// Returns an empty history on 404 (new conversation).
    async fn fetch_history(
        &self,
        req: &ProcessRequest,
    ) -> Result<Vec<ConversationMessage>, AppError> {
        let url = format!(
            "{}/internal/conversations/{}/messages",
            self.config.backend_api_url, req.conversation_id
        );

        debug!(url = %url, "Fetching conversation history");

        let response = self
            .http_client
            .get(&url)
            .header("X-Internal-API-Key", &self.config.inter_service_secret)
            .header("X-Tenant-ID", req.tenant_id.to_string())
            .send()
            .await
            .map_err(|e| AppError::BackendError(format!("Failed to reach backend: {}", e)))?;

        match response.status().as_u16() {
            200 => {
                let messages: Vec<ConversationMessage> = response
                    .json()
                    .await
                    .map_err(|e| AppError::BackendError(format!("Invalid history response: {}", e)))?;
                Ok(messages)
            }
            404 => Ok(vec![]),
            status => Err(AppError::BackendError(format!(
                "Backend returned unexpected status {}",
                status
            ))),
        }
    }
}

fn history_to_message(msg: ConversationMessage) -> Message {
    let role = match msg.role.as_str() {
        "assistant" => Role::Assistant,
        "tool" => Role::Tool,
        _ => Role::User,
    };

    Message {
        role,
        content: Some(msg.content),
        tool_calls: None,
        tool_call_id: msg.tool_call_id,
        name: None,
    }
}

fn build_system_prompt(chunks: &[RagChunk]) -> String {
    let mut prompt = String::from(
        "You are an AI assistant specialized in Revenue Operations (RevOps). \
         You support sales, marketing, and customer success teams by providing \
         data-driven insights and automating repetitive tasks.\n\n\
         You have access to real-time business data through specialized tools:\n\
         - CRM tools for contacts, accounts, and deals\n\
         - Billing tools for invoices and subscription status\n\
         - Analytics tools for pipeline metrics and KPIs\n\
         - Sequence tools for outreach automation\n\
         - Document tools for playbooks and reports\n\n\
         Always call the appropriate tools to fetch current data before answering. \
         Cite your sources when referencing documents. \
         Be concise, accurate, and actionable.\n",
    );

    if !chunks.is_empty() {
        prompt.push_str("\n## Relevant Documentation\n\n");
        for chunk in chunks {
            prompt.push_str(&format!(
                "**Source: {} [score: {:.2}]**\n{}\n\n",
                chunk.filename, chunk.similarity_score, chunk.content
            ));
        }
    }

    prompt
}

/// Static tool definitions for all MCP servers.
///
/// In a future iteration these can be fetched dynamically from each MCP server
/// via a `GET /mcp/tools` discovery endpoint.
fn default_tool_definitions() -> Vec<Tool> {
    vec![
        // ── mcp-crm ────────────────────────────────────────────────────────
        make_tool(
            "mcp_crm__get_contact",
            "Get full contact details by UUID (name, email, company, stage, notes)",
            &[("contact_id", "string", "UUID of the contact", true)],
        ),
        make_tool(
            "mcp_crm__search_contacts",
            "Search contacts by name, email, or company",
            &[
                ("query", "string", "Search query string", true),
                ("limit", "integer", "Maximum number of results (default 10)", false),
            ],
        ),
        make_tool(
            "mcp_crm__update_deal_stage",
            "Move a deal to a different pipeline stage",
            &[
                ("deal_id", "string", "UUID of the deal", true),
                ("stage", "string", "Target stage name (e.g. 'qualified', 'proposal', 'closed_won')", true),
            ],
        ),
        make_tool(
            "mcp_crm__list_deals",
            "List deals with optional filters on stage or owner",
            &[
                ("stage", "string", "Filter by stage name", false),
                ("owner_id", "string", "Filter by owner UUID", false),
                ("limit", "integer", "Maximum number of results (default 20)", false),
            ],
        ),
        // ── mcp-billing ────────────────────────────────────────────────────
        make_tool(
            "mcp_billing__get_invoice",
            "Fetch invoice details including amount, status, and line items",
            &[("invoice_id", "string", "UUID of the invoice", true)],
        ),
        make_tool(
            "mcp_billing__check_subscription_status",
            "Check the current subscription plan and status for an account",
            &[("account_id", "string", "UUID of the account", true)],
        ),
        make_tool(
            "mcp_billing__list_overdue_payments",
            "List all accounts with overdue invoices for this tenant",
            &[("limit", "integer", "Maximum number of results (default 20)", false)],
        ),
        // ── mcp-analytics ──────────────────────────────────────────────────
        make_tool(
            "mcp_analytics__get_pipeline_metrics",
            "Get pipeline KPIs: total value, deal count, win rate, average cycle time",
            &[
                ("period", "string", "Time period (e.g. 'last_30_days', 'current_quarter', 'last_year')", true),
            ],
        ),
        make_tool(
            "mcp_analytics__compute_churn_rate",
            "Compute monthly or quarterly churn rate as a percentage",
            &[
                ("period", "string", "Time period for churn computation", true),
            ],
        ),
        make_tool(
            "mcp_analytics__get_deal_velocity",
            "Get average time (in days) deals spend in each pipeline stage",
            &[
                ("period", "string", "Time period to analyze", true),
            ],
        ),
        // ── mcp-sequences ──────────────────────────────────────────────────
        make_tool(
            "mcp_sequences__create_sequence",
            "Create a new outreach sequence with specified steps",
            &[
                ("name", "string", "Sequence name", true),
                ("description", "string", "Short description of the sequence goal", false),
            ],
        ),
        make_tool(
            "mcp_sequences__enroll_contact",
            "Enroll a contact in an existing outreach sequence",
            &[
                ("sequence_id", "string", "UUID of the sequence", true),
                ("contact_id", "string", "UUID of the contact to enroll", true),
            ],
        ),
        make_tool(
            "mcp_sequences__get_sequence_performance",
            "Get open rates, reply rates, and conversion metrics for a sequence",
            &[
                ("sequence_id", "string", "UUID of the sequence", true),
            ],
        ),
        // ── mcp-filesystem ─────────────────────────────────────────────────
        make_tool(
            "mcp_filesystem__read_document",
            "Read the content of a document by its storage path",
            &[("path", "string", "Relative path to the document", true)],
        ),
        make_tool(
            "mcp_filesystem__list_playbooks",
            "List all available sales and RevOps playbooks",
            &[("document_type", "string", "Filter by type: 'playbook', 'report', 'contract' (optional)", false)],
        ),
    ]
}

fn make_tool(name: &str, description: &str, params: &[(&str, &str, &str, bool)]) -> Tool {
    let mut properties = serde_json::Map::new();
    let mut required: Vec<serde_json::Value> = vec![];

    for (param_name, param_type, param_desc, is_required) in params {
        properties.insert(
            param_name.to_string(),
            serde_json::json!({ "type": param_type, "description": param_desc }),
        );
        if *is_required {
            required.push(serde_json::Value::String(param_name.to_string()));
        }
    }

    Tool {
        tool_type: "function".to_string(),
        function: ToolFunction {
            name: name.to_string(),
            description: description.to_string(),
            parameters: serde_json::json!({
                "type": "object",
                "properties": properties,
                "required": required,
            }),
        },
    }
}
