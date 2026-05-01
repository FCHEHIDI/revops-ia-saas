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
        Self {
            http_client,
            config,
        }
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
        // Keep only the last 6 messages to stay within token limits
        let history: Vec<_> = history.into_iter().rev().take(6).rev().collect();
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

    /// GET {backend}/internal/sessions/{id}/history
    ///
    /// Returns an empty history on 404 (new conversation).
    async fn fetch_history(
        &self,
        req: &ProcessRequest,
    ) -> Result<Vec<ConversationMessage>, AppError> {
        let url = format!(
            "{}/internal/sessions/{}/history",
            self.config.backend_api_url, req.conversation_id
        );

        debug!(url = %url, "Fetching conversation history");

        let response = self
            .http_client
            .get(&url)
            // Backend checks X-Internal-Secret header (BACKEND_SECRET env)
            .header("X-Internal-Secret", &self.config.backend_secret)
            .header("X-Tenant-ID", req.tenant_id.to_string())
            .send()
            .await
            .map_err(|e| AppError::BackendError(format!("Failed to reach backend: {}", e)))?;

        match response.status().as_u16() {
            200 => {
                // Backend returns { session_id, messages: [{role, content, timestamp}] }
                #[derive(serde::Deserialize)]
                struct HistoryResponse {
                    messages: Vec<ConversationMessage>,
                }
                let body: HistoryResponse = response.json().await.map_err(|e| {
                    AppError::BackendError(format!("Invalid history response: {}", e))
                })?;
                Ok(body.messages)
            }
            // No history yet (new conversation) or auth not configured — continue without history
            401 | 403 | 404 => {
                warn!(status = %response.status(), "History endpoint returned non-200 — proceeding with empty history");
                Ok(vec![])
            }
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

/// Build the system prompt, separating CRM live-data chunks from static document chunks.
///
/// CRM chunks (identified by `crm_metadata.is_some()` or `document_type` containing `"crm"`)
/// are rendered under a dedicated `## CRM Context` section with structured entity headers.
/// All other chunks appear under `## Relevant Documentation`.
pub fn build_system_prompt(chunks: &[RagChunk]) -> String {
    let mut prompt = String::from(
        "You are Xenito, an AI assistant specialized in Revenue Operations (RevOps). \
         You support sales, marketing, and customer success teams by providing \
         data-driven insights and automating repetitive tasks.\n\n\
         You have access to real-time business data through specialized tools:\n\
         - CRM tools for contacts, accounts, and deals\n\
         - Billing tools for invoices and subscription status\n\
         - Analytics tools for pipeline metrics and KPIs\n\
         - Sequence tools for outreach automation\n\
         - Document tools for playbooks and reports\n\n\
         CRITICAL RULES:\n\
         1. NEVER invent, fabricate, or hallucinate data. If a tool fails or is unavailable, \
            say so clearly: \"I cannot access [service] right now.\" Do NOT make up names, emails, or numbers.\n\
         2. If a tool returns an error, acknowledge the failure and suggest the user try again later.\n\
         3. Only call tools when the user's request requires real data. For greetings or general questions, respond directly without calling tools.\n\
         4. Be concise, accurate, and actionable. Respond in the same language as the user.\n\
         5. NEVER use emojis. Your responses must be emoji-free at all times.\n\
         6. Format responses in clean Markdown: use **bold** for key terms and important values, \
            bullet lists for enumerations, and tables for structured data. \
            Keep a professional and direct tone.\n",
    );

    let (crm_chunks, doc_chunks): (Vec<&RagChunk>, Vec<&RagChunk>) = chunks
        .iter()
        .partition(|c| c.crm_metadata.is_some() || c.document_type.contains("crm"));

    if !doc_chunks.is_empty() {
        prompt.push_str("\n## Relevant Documentation\n\n");
        for chunk in &doc_chunks {
            prompt.push_str(&format!(
                "**Source: {} [score: {:.2}]**\n{}\n\n",
                chunk.filename, chunk.similarity_score, chunk.content
            ));
        }
    }

    if !crm_chunks.is_empty() {
        prompt.push_str("\n## CRM Context (from recent activity)\n\n");
        for chunk in &crm_chunks {
            let header = crm_chunk_header(chunk);
            prompt.push_str(&format!("**{}**\n{}\n\n", header, chunk.content));
        }
    }

    prompt
}

/// Format a CRM chunk header extracting entity name and stage from `crm_metadata`.
///
/// Falls back to `chunk.filename` when metadata fields are absent.
fn crm_chunk_header(chunk: &RagChunk) -> String {
    let meta = match &chunk.crm_metadata {
        Some(m) => m,
        None => {
            return format!(
                "[CRM] {} [score: {:.2}]",
                chunk.filename, chunk.similarity_score
            )
        }
    };

    let entity_type = meta
        .get("entity_type")
        .and_then(|v| v.as_str())
        .unwrap_or(chunk.document_type.as_str());

    let entity_name = meta
        .get("account_name")
        .or_else(|| meta.get("entity_name"))
        .or_else(|| meta.get("contact_name"))
        .and_then(|v| v.as_str())
        .unwrap_or(chunk.filename.as_str());

    let stage = meta
        .get("deal_stage")
        .or_else(|| meta.get("stage"))
        .and_then(|v| v.as_str());

    match stage {
        Some(s) => format!(
            "[CRM] {} — {} | {} [score: {:.2}]",
            entity_type, entity_name, s, chunk.similarity_score
        ),
        None => format!(
            "[CRM] {} — {} [score: {:.2}]",
            entity_type, entity_name, chunk.similarity_score
        ),
    }
}

/// Static tool definitions for all MCP servers.
///
/// In a future iteration these can be fetched dynamically from each MCP server
/// via a `GET /mcp/tools` discovery endpoint.
pub fn default_tool_definitions() -> Vec<Tool> {
    vec![
        // ── mcp-crm — contacts ────────────────────────────────────────────
        make_tool(
            "mcp_crm__get_contact",
            "Get full contact details by UUID (name, email, company, stage, notes)",
            &[("contact_id", "string", "UUID of the contact", true)],
        ),
        make_tool(
            "mcp_crm__search_contacts",
            "Search or list CRM contacts. Use query='' to list all. Supports status filter.",
            &[
                (
                    "query",
                    "string",
                    "Search query string — use empty string '' to list all contacts",
                    false,
                ),
                (
                    "status",
                    "string",
                    "Filter by contact status: 'active', 'inactive', 'prospect', 'customer', 'churned'",
                    false,
                ),
                (
                    "page_size",
                    "integer",
                    "Maximum number of results per page (default 20, max 100)",
                    false,
                ),
            ],
        ),
        make_tool(
            "mcp_crm__create_contact",
            "Create a new CRM contact with personal and professional details",
            &[
                ("first_name", "string", "Contact first name", true),
                ("last_name", "string", "Contact last name", true),
                ("email", "string", "Contact email address", true),
                ("created_by", "string", "UUID of the user creating the contact", true),
                ("phone", "string", "Contact phone number", false),
                ("job_title", "string", "Job title or role", false),
                ("account_id", "string", "UUID of the linked account", false),
                ("status", "string", "Contact status: 'active', 'inactive', 'prospect', 'customer', 'churned'", false),
            ],
        ),
        make_tool(
            "mcp_crm__update_contact",
            "Update an existing contact's details (only provided fields are changed)",
            &[
                (
                    "contact_id",
                    "string",
                    "UUID of the contact to update",
                    true,
                ),
                ("first_name", "string", "Updated first name", false),
                ("last_name", "string", "Updated last name", false),
                ("email", "string", "Updated email address", false),
                ("phone", "string", "Updated phone number", false),
                ("job_title", "string", "Updated job title", false),
                ("account_id", "string", "UUID of the linked account", false),
                ("stage", "string", "Contact lifecycle stage", false),
            ],
        ),
        // ── mcp-crm — accounts ───────────────────────────────────────────
        make_tool(
            "mcp_crm__get_account",
            "Get full account details by UUID (name, domain, industry, ARR, contacts)",
            &[("account_id", "string", "UUID of the account", true)],
        ),
        make_tool(
            "mcp_crm__search_accounts",
            "Search accounts by name or domain",
            &[
                ("query", "string", "Search query string", false),
                (
                    "page_size",
                    "integer",
                    "Maximum number of results per page (default 20, max 100)",
                    false,
                ),
            ],
        ),
        make_tool(
            "mcp_crm__create_account",
            "Create a new CRM account (company / organisation)",
            &[
                ("name", "string", "Account / company name", true),
                (
                    "domain",
                    "string",
                    "Company website domain (e.g. acme.com)",
                    false,
                ),
                (
                    "industry",
                    "string",
                    "Industry sector (e.g. SaaS, Fintech, Healthcare)",
                    false,
                ),
                (
                    "size",
                    "string",
                    "Company size bracket (e.g. '1-10', '11-50', '51-200')",
                    false,
                ),
                (
                    "annual_revenue",
                    "string",
                    "Estimated annual revenue in USD",
                    false,
                ),
                ("notes", "string", "Optional notes about the account", false),
            ],
        ),
        make_tool(
            "mcp_crm__update_account",
            "Update an existing account's details (only provided fields are changed)",
            &[
                (
                    "account_id",
                    "string",
                    "UUID of the account to update",
                    true,
                ),
                ("name", "string", "Updated account name", false),
                ("domain", "string", "Updated domain", false),
                ("industry", "string", "Updated industry", false),
                ("size", "string", "Updated company size", false),
                ("annual_revenue", "string", "Updated annual revenue", false),
                ("notes", "string", "Updated notes", false),
            ],
        ),
        // ── mcp-crm — deals ──────────────────────────────────────────────
        make_tool(
            "mcp_crm__get_deal",
            "Get full deal details by UUID (title, amount, stage, account, contacts, activity)",
            &[("deal_id", "string", "UUID of the deal", true)],
        ),
        make_tool(
            "mcp_crm__list_deals",
            "List deals with optional filters on stage or owner",
            &[
                ("stage", "string", "Filter by stage: 'prospecting', 'qualification', 'proposal', 'negotiation', 'closed_won', 'closed_lost'", false),
                ("owner_id", "string", "Filter by owner UUID", false),
                (
                    "page_size",
                    "integer",
                    "Maximum number of results per page (default 20, max 100)",
                    false,
                ),
            ],
        ),
        make_tool(
            "mcp_crm__update_deal_stage",
            "Move a deal to a different pipeline stage",
            &[
                ("deal_id", "string", "UUID of the deal", true),
                (
                    "new_stage",
                    "string",
                    "Target stage: 'prospecting', 'qualification', 'proposal', 'negotiation', 'closed_won', 'closed_lost'",
                    true,
                ),
                ("notes", "string", "Optional notes to attach to this stage transition", false),
            ],
        ),
        // mcp_crm__create_deal has a contact_ids array field — built manually
        Tool {
            tool_type: "function".to_string(),
            function: ToolFunction {
                name: "mcp_crm__create_deal".to_string(),
                description:
                    "Create a new deal linked to an account with optional contact associations"
                        .to_string(),
                parameters: serde_json::json!({
                    "type": "object",
                    "properties": {
                        "title": {
                            "type": "string",
                            "description": "Deal title"
                        },
                        "account_id": {
                            "type": "string",
                            "description": "UUID of the linked account"
                        },
                        "amount": {
                            "type": "number",
                            "description": "Deal amount in the account's currency"
                        },
                        "stage": {
                            "type": "string",
                            "description": "Pipeline stage name (e.g. 'prospecting', 'qualified', 'proposal')"
                        },
                        "owner_id": {
                            "type": "string",
                            "description": "UUID of the deal owner (sales rep)"
                        },
                        "expected_close_date": {
                            "type": "string",
                            "description": "Expected close date in ISO 8601 format (e.g. '2026-06-30')"
                        },
                        "contact_ids": {
                            "type": "array",
                            "items": { "type": "string" },
                            "description": "UUIDs of contacts associated with this deal"
                        },
                        "notes": {
                            "type": "string",
                            "description": "Optional deal notes"
                        }
                    },
                    "required": ["title", "account_id", "amount"]
                }),
            },
        },
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
            &[(
                "limit",
                "integer",
                "Maximum number of results (default 20)",
                false,
            )],
        ),
        // ── mcp-analytics ──────────────────────────────────────────────────
        make_tool(
            "mcp_analytics__get_pipeline_metrics",
            "Get pipeline KPIs: total value, deal count, win rate, average cycle time",
            &[(
                "period",
                "string",
                "Time period (e.g. 'last_30_days', 'current_quarter', 'last_year')",
                true,
            )],
        ),
        make_tool(
            "mcp_analytics__compute_churn_rate",
            "Compute monthly or quarterly churn rate as a percentage",
            &[(
                "period",
                "string",
                "Time period for churn computation",
                true,
            )],
        ),
        make_tool(
            "mcp_analytics__get_deal_velocity",
            "Get average time (in days) deals spend in each pipeline stage",
            &[("period", "string", "Time period to analyze", true)],
        ),
        make_tool(
            "mcp_billing__list_invoices",
            "List all invoices for an account with optional status filter",
            &[
                ("account_id", "string", "UUID of the account", true),
                (
                    "status",
                    "string",
                    "Filter by status: 'paid', 'pending', 'overdue' (optional)",
                    false,
                ),
            ],
        ),
        make_tool(
            "mcp_billing__get_subscription",
            "Fetch full subscription details for an account",
            &[("account_id", "string", "UUID of the account", true)],
        ),
        make_tool(
            "mcp_billing__update_subscription_status",
            "Update the status of an account subscription (e.g. cancel, reactivate)",
            &[
                ("account_id", "string", "UUID of the account", true),
                (
                    "status",
                    "string",
                    "New status: 'active', 'cancelled', 'suspended'",
                    true,
                ),
            ],
        ),
        make_tool(
            "mcp_billing__get_customer_billing_summary",
            "Get a full billing summary for a customer: MRR, invoices, subscription",
            &[("account_id", "string", "UUID of the account", true)],
        ),
        make_tool(
            "mcp_billing__get_mrr",
            "Compute total Monthly Recurring Revenue for the tenant",
            &[(
                "period",
                "string",
                "Month/year for MRR calculation (e.g. '2025-01')",
                true,
            )],
        ),
        make_tool(
            "mcp_analytics__get_funnel_analysis",
            "Get stage-by-stage conversion rates across the sales funnel",
            &[("period", "string", "Time period to analyze", true)],
        ),
        make_tool(
            "mcp_analytics__forecast_revenue",
            "Forecast future revenue based on current pipeline and historical close rates",
            &[
                (
                    "period",
                    "string",
                    "Forecast horizon (e.g. 'next_quarter')",
                    true,
                ),
                (
                    "confidence_level",
                    "string",
                    "Confidence band: 'low', 'mid', 'high' (default 'mid')",
                    false,
                ),
            ],
        ),
        make_tool(
            "mcp_analytics__get_mrr_trend",
            "Get the monthly MRR trend over a given period",
            &[(
                "period",
                "string",
                "Time range (e.g. 'last_12_months')",
                true,
            )],
        ),
        make_tool(
            "mcp_analytics__get_at_risk_accounts",
            "Identify accounts at high risk of churn based on activity and usage signals",
            &[(
                "limit",
                "integer",
                "Maximum number of at-risk accounts to return (default 10)",
                false,
            )],
        ),
        make_tool(
            "mcp_analytics__get_rep_performance",
            "Get individual sales rep KPIs: quota attainment, win rate, average deal size",
            &[
                ("rep_id", "string", "UUID of the sales rep", true),
                ("period", "string", "Time period to evaluate", true),
            ],
        ),
        make_tool(
            "mcp_analytics__get_team_leaderboard",
            "Get ranked leaderboard of all sales reps by quota attainment for the period",
            &[(
                "period",
                "string",
                "Time period to rank (e.g. 'current_quarter')",
                true,
            )],
        ),
        make_tool(
            "mcp_analytics__get_activity_metrics",
            "Get activity volume metrics: calls, emails, meetings per rep or team",
            &[("period", "string", "Time period to analyze", true)],
        ),
        // ── mcp-sequences ──────────────────────────────────────────────────
        make_tool(
            "mcp_sequences__create_sequence",
            "Create a new outreach sequence with specified steps",
            &[
                ("name", "string", "Sequence name", true),
                (
                    "description",
                    "string",
                    "Short description of the sequence goal",
                    false,
                ),
            ],
        ),
        make_tool(
            "mcp_sequences__enroll_contact",
            "Enroll a contact in an existing outreach sequence",
            &[
                ("sequence_id", "string", "UUID of the sequence", true),
                (
                    "contact_id",
                    "string",
                    "UUID of the contact to enroll",
                    true,
                ),
            ],
        ),
        make_tool(
            "mcp_sequences__get_sequence_performance",
            "Get open rates, reply rates, and conversion metrics for a sequence",
            &[("sequence_id", "string", "UUID of the sequence", true)],
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
            &[(
                "document_type",
                "string",
                "Filter by type: 'playbook', 'report', 'contract' (optional)",
                false,
            )],
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

// ─────────────────────────────────────────────────────────────────────────────
// Contract tests: validate default_tool_definitions() against mcp-crm schemas.
//
// These tests are the Rust side of the schema contract.  The Python side lives
// in mcp/mcp-crm/tests/test_contracts.py.
//
// Naming convention: every test function starts with `tool_schema_` so it can
// be run selectively with: cargo test tool_schema -- --nocapture
//
// REGRESSION GUARD for commit bc46965:
//   update_deal_stage param 'stage' → 'new_stage' mismatch caused every
//   deal-move tool call to fail silently with VALIDATION_ERROR.
// ─────────────────────────────────────────────────────────────────────────────
#[cfg(test)]
mod tool_schema_tests {
    use super::*;

    fn get_tool<'a>(tools: &'a [Tool], name: &str) -> &'a Tool {
        tools
            .iter()
            .find(|t| t.function.name == name)
            .unwrap_or_else(|| panic!("Tool '{name}' missing from default_tool_definitions()"))
    }

    fn required_params(tool: &Tool) -> Vec<String> {
        tool.function.parameters["required"]
            .as_array()
            .unwrap_or(&vec![])
            .iter()
            .filter_map(|v| v.as_str().map(String::from))
            .collect()
    }

    fn property_names(tool: &Tool) -> Vec<String> {
        tool.function.parameters["properties"]
            .as_object()
            .map(|o| o.keys().cloned().collect())
            .unwrap_or_default()
    }

    /// All 12 mcp-crm tools must be present in default_tool_definitions().
    #[test]
    fn tool_schema_all_mcp_crm_tools_present() {
        let tools = default_tool_definitions();
        let names: Vec<&str> = tools.iter().map(|t| t.function.name.as_str()).collect();

        for expected in &[
            "mcp_crm__get_contact",
            "mcp_crm__search_contacts",
            "mcp_crm__create_contact",
            "mcp_crm__update_contact",
            "mcp_crm__get_account",
            "mcp_crm__search_accounts",
            "mcp_crm__create_account",
            "mcp_crm__update_account",
            "mcp_crm__get_deal",
            "mcp_crm__list_deals",
            "mcp_crm__create_deal",
            "mcp_crm__update_deal_stage",
        ] {
            assert!(
                names.contains(expected),
                "Tool '{expected}' missing from default_tool_definitions()"
            );
        }
    }

    /// REGRESSION bc46965: update_deal_stage must use 'new_stage', not 'stage'.
    /// mcp-crm handler: validate_enum_field(params, "new_stage", DEAL_STAGE_VALUES, required=True)
    #[test]
    fn tool_schema_update_deal_stage_uses_new_stage() {
        let tools = default_tool_definitions();
        let tool = get_tool(&tools, "mcp_crm__update_deal_stage");
        let required = required_params(tool);

        assert!(
            required.contains(&"new_stage".to_string()),
            "update_deal_stage must require 'new_stage' (mcp-crm uses new_stage). Got: {required:?}"
        );
        assert!(
            !required.contains(&"stage".to_string()),
            "update_deal_stage must NOT use 'stage' as required param — use 'new_stage'. Got: {required:?}"
        );
    }

    /// search_contacts must expose page_size, not limit (mcp-crm ignores 'limit').
    #[test]
    fn tool_schema_search_contacts_uses_page_size() {
        let tools = default_tool_definitions();
        let tool = get_tool(&tools, "mcp_crm__search_contacts");
        let props = property_names(tool);

        assert!(
            props.contains(&"page_size".to_string()),
            "search_contacts must expose 'page_size'. Got: {props:?}"
        );
        assert!(
            !props.contains(&"limit".to_string()),
            "search_contacts must NOT use 'limit' — use 'page_size'. Got: {props:?}"
        );
    }

    /// list_deals and search_accounts must use page_size, not limit.
    #[test]
    fn tool_schema_pagination_uses_page_size() {
        let tools = default_tool_definitions();
        for name in &["mcp_crm__list_deals", "mcp_crm__search_accounts"] {
            let tool = get_tool(&tools, name);
            let props = property_names(tool);
            assert!(
                !props.contains(&"limit".to_string()),
                "'{name}' must NOT use 'limit' — use 'page_size'. Got: {props:?}"
            );
        }
    }

    /// create_contact must require 'created_by' (mcp-crm calls validate_uuid_field(params, "created_by")).
    #[test]
    fn tool_schema_create_contact_requires_created_by() {
        let tools = default_tool_definitions();
        let tool = get_tool(&tools, "mcp_crm__create_contact");
        let required = required_params(tool);

        assert!(
            required.contains(&"created_by".to_string()),
            "create_contact must require 'created_by'. Got: {required:?}"
        );
        // 'company' and 'notes' are not fields in the mcp-crm create_contact handler
        assert!(
            !required.contains(&"company".to_string()),
            "create_contact must NOT require 'company' (not a mcp-crm field). Got: {required:?}"
        );
    }

    /// search_contacts status enum must list 'prospect', not 'lead'.
    #[test]
    fn tool_schema_contact_status_uses_prospect_not_lead() {
        let tools = default_tool_definitions();
        let tool = get_tool(&tools, "mcp_crm__search_contacts");
        let props = &tool.function.parameters["properties"];

        if let Some(status) = props.get("status") {
            let desc = status["description"].as_str().unwrap_or("");
            assert!(
                desc.contains("prospect"),
                "search_contacts status description must mention 'prospect'. Got: {desc:?}"
            );
            assert!(
                !desc.contains("lead"),
                "search_contacts status must NOT mention 'lead' (valid value is 'prospect'). Got: {desc:?}"
            );
        }
    }
}
