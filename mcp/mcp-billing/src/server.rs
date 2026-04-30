use rmcp::{
    model::{
        CallToolRequestParam, CallToolResult, Content, ListToolsResult, PaginatedRequestParam,
        ServerCapabilities, ServerInfo, Tool,
    },
    service::{RequestContext, RoleServer},
    Error as McpError,
    ServerHandler,
};
use serde_json::{json, Map, Value};
use sqlx::PgPool;
use std::borrow::Cow;
use std::sync::Arc;
use tracing::{error, info, instrument};

/// Convert a `serde_json::Value::Object` into `Arc<Map<String, Value>>` for Tool::input_schema.
fn s(v: Value) -> Arc<Map<String, Value>> {
    Arc::new(v.as_object().cloned().unwrap_or_default())
}

use crate::errors::BillingError;
use crate::tools::{
    invoices::{
        get_invoice, list_invoices, list_overdue_payments,
        GetInvoiceInput, ListInvoicesInput, ListOverduePaymentsInput,
    },
    subscriptions::{
        check_subscription_status, get_subscription, update_subscription_status,
        CheckSubscriptionStatusInput, GetSubscriptionInput, UpdateSubscriptionStatusInput,
    },
    summary::{
        get_customer_billing_summary, get_mrr,
        GetCustomerBillingSummaryInput, GetMrrInput,
    },
};

// ---------------------------------------------------------------------------
// BillingServer
// ---------------------------------------------------------------------------

#[derive(Clone)]
pub struct BillingServer {
    pool: Arc<PgPool>,
}

impl BillingServer {
    pub fn new(pool: PgPool) -> Self {
        Self {
            pool: Arc::new(pool),
        }
    }

    fn billing_error_to_mcp(err: BillingError) -> McpError {
        McpError::internal_error(err.to_string(), Some(err.to_mcp_error_content()))
    }

    fn parse_input<T: serde::de::DeserializeOwned>(
        arguments: Option<Value>,
        tool_name: &str,
    ) -> Result<T, McpError> {
        let args = arguments.unwrap_or(Value::Object(serde_json::Map::new()));
        serde_json::from_value(args)
            .map_err(|e| McpError::invalid_params(format!("{tool_name}: {e}"), None))
    }

    fn ok_result(data: impl serde::Serialize) -> CallToolResult {
        CallToolResult {
            content: vec![Content::text(
                serde_json::to_string_pretty(&data)
                    .unwrap_or_else(|_| "{}".to_string()),
            )],
            is_error: Some(false),
        }
    }

    fn err_result(err: BillingError) -> CallToolResult {
        CallToolResult {
            content: vec![Content::text(
                serde_json::to_string_pretty(&err.to_mcp_error_content())
                    .unwrap_or_else(|_| r#"{"error":"INTERNAL_ERROR"}"#.to_string()),
            )],
            is_error: Some(true),
        }
    }
}

// ---------------------------------------------------------------------------
// ServerHandler implementation
// ---------------------------------------------------------------------------

impl ServerHandler for BillingServer {
    fn get_info(&self) -> ServerInfo {
        ServerInfo {
            capabilities: ServerCapabilities {
                tools: Some(rmcp::model::ToolsCapability { list_changed: None }),
                ..Default::default()
            },
            server_info: rmcp::model::Implementation {
                name: "mcp-billing".to_string(),
                version: env!("CARGO_PKG_VERSION").to_string(),
            },
            ..Default::default()
        }
    }

    #[instrument(skip(self, _ctx), name = "list_tools")]
    async fn list_tools(
        &self,
        _request: PaginatedRequestParam,
        _ctx: RequestContext<RoleServer>,
    ) -> Result<ListToolsResult, McpError> {
        let tools = vec![
            // ----------------------------------------------------------------
            // Invoices
            // ----------------------------------------------------------------
            Tool {
                name: Cow::Borrowed("get_invoice"),
                description: Cow::Borrowed(
                    "Retrieves a single invoice by ID with all line items for the given tenant.",
                ),
                input_schema: s(json!({
                    "type": "object",
                    "required": ["tenant_id", "invoice_id"],
                    "properties": {
                        "tenant_id":  { "type": "string", "format": "uuid" },
                        "user_id":    { "type": "string", "format": "uuid" },
                        "invoice_id": { "type": "string", "format": "uuid" }
                    }
                })),
            },
            Tool {
                name: Cow::Borrowed("list_invoices"),
                description: Cow::Borrowed(
                    "Lists invoices for the tenant with optional status/date filters. Returns summaries with total count and total amount.",
                ),
                input_schema: s(json!({
                    "type": "object",
                    "required": ["tenant_id"],
                    "properties": {
                        "tenant_id": { "type": "string", "format": "uuid" },
                        "user_id":   { "type": "string", "format": "uuid" },
                        "status": {
                            "type": "string",
                            "enum": ["draft", "pending", "paid", "overdue", "void", "refunded"]
                        },
                        "from_date": { "type": "string", "format": "date", "description": "ISO 8601 date (YYYY-MM-DD)" },
                        "to_date":   { "type": "string", "format": "date", "description": "ISO 8601 date (YYYY-MM-DD)" },
                        "limit":  { "type": "integer", "minimum": 1, "maximum": 100, "default": 20 },
                        "offset": { "type": "integer", "minimum": 0, "default": 0 }
                    }
                })),
            },
            Tool {
                name: Cow::Borrowed("list_overdue_payments"),
                description: Cow::Borrowed(
                    "Lists overdue invoices with optional filter on number of overdue days. Returns total overdue amount and contact email.",
                ),
                input_schema: s(json!({
                    "type": "object",
                    "required": ["tenant_id"],
                    "properties": {
                        "tenant_id": { "type": "string", "format": "uuid" },
                        "user_id":   { "type": "string", "format": "uuid" },
                        "overdue_days_min": { "type": "integer", "minimum": 0, "description": "Only return invoices overdue by at least this many days" },
                        "overdue_days_max": { "type": "integer", "minimum": 0, "description": "Only return invoices overdue by at most this many days" },
                        "limit": { "type": "integer", "minimum": 1, "maximum": 100, "default": 20 }
                    }
                })),
            },
            // ----------------------------------------------------------------
            // Subscriptions
            // ----------------------------------------------------------------
            Tool {
                name: Cow::Borrowed("get_subscription"),
                description: Cow::Borrowed(
                    "Retrieves subscription details. If subscription_id is omitted, returns the most recent subscription for the tenant.",
                ),
                input_schema: s(json!({
                    "type": "object",
                    "required": ["tenant_id"],
                    "properties": {
                        "tenant_id":       { "type": "string", "format": "uuid" },
                        "user_id":         { "type": "string", "format": "uuid" },
                        "subscription_id": { "type": "string", "format": "uuid", "description": "Optional — omit to get the active subscription" }
                    }
                })),
            },
            Tool {
                name: Cow::Borrowed("check_subscription_status"),
                description: Cow::Borrowed(
                    "Returns the current subscription status, plan name, trial info, seat usage and enabled features. Returns NO_ACTIVE_SUBSCRIPTION if no active/trial/past_due subscription exists.",
                ),
                input_schema: s(json!({
                    "type": "object",
                    "required": ["tenant_id"],
                    "properties": {
                        "tenant_id": { "type": "string", "format": "uuid" },
                        "user_id":   { "type": "string", "format": "uuid" }
                    }
                })),
            },
            Tool {
                name: Cow::Borrowed("update_subscription_status"),
                description: Cow::Borrowed(
                    "Updates the status of a subscription. Requires billing:subscriptions:write permission. Only valid transitions are allowed: Active→PastDue, Active→Suspended, Suspended→Active, PastDue→Active, PastDue→Canceled.",
                ),
                input_schema: s(json!({
                    "type": "object",
                    "required": ["tenant_id", "subscription_id", "new_status", "reason"],
                    "properties": {
                        "tenant_id":       { "type": "string", "format": "uuid" },
                        "user_id":         { "type": "string", "format": "uuid" },
                        "subscription_id": { "type": "string", "format": "uuid" },
                        "new_status": {
                            "type": "string",
                            "enum": ["trialing", "active", "past_due", "canceled", "suspended", "paused"]
                        },
                        "reason": { "type": "string", "minLength": 1, "description": "Required justification for the status change" }
                    }
                })),
            },
            // ----------------------------------------------------------------
            // Summary / Analytics
            // ----------------------------------------------------------------
            Tool {
                name: Cow::Borrowed("get_customer_billing_summary"),
                description: Cow::Borrowed(
                    "Returns a high-level billing summary: MRR, ARR, pending invoices, lifetime value, next renewal date and payment method info.",
                ),
                input_schema: s(json!({
                    "type": "object",
                    "required": ["tenant_id"],
                    "properties": {
                        "tenant_id": { "type": "string", "format": "uuid" },
                        "user_id":   { "type": "string", "format": "uuid" }
                    }
                })),
            },
            Tool {
                name: Cow::Borrowed("get_mrr"),
                description: Cow::Borrowed(
                    "Returns monthly MRR data points for a date range, including new MRR, expansion MRR, churned MRR. Also returns current MRR and growth rate over the period.",
                ),
                input_schema: s(json!({
                    "type": "object",
                    "required": ["tenant_id", "from_date", "to_date"],
                    "properties": {
                        "tenant_id": { "type": "string", "format": "uuid" },
                        "user_id":   { "type": "string", "format": "uuid" },
                        "from_date": { "type": "string", "format": "date", "description": "Start of period (YYYY-MM-DD)" },
                        "to_date":   { "type": "string", "format": "date", "description": "End of period (YYYY-MM-DD)" }
                    }
                })),
            },
        ];

        Ok(ListToolsResult {
            tools,
            next_cursor: None,
        })
    }

    #[instrument(skip(self, _ctx), name = "call_tool", fields(tool = %request.name))]
    async fn call_tool(
        &self,
        request: CallToolRequestParam,
        _ctx: RequestContext<RoleServer>,
    ) -> Result<CallToolResult, McpError> {
        let name = request.name.as_ref();
        let args = request.arguments.map(Value::Object);
        let pool = self.pool.as_ref();

        info!("Dispatching tool: {}", name);

        match name {
            // ----------------------------------------------------------------
            // Invoices
            // ----------------------------------------------------------------
            "get_invoice" => {
                let input: GetInvoiceInput = Self::parse_input(args, name)?;
                match get_invoice(input, pool).await {
                    Ok(out) => Ok(Self::ok_result(out)),
                    Err(e) => Ok(Self::err_result(e)),
                }
            }
            "list_invoices" => {
                let input: ListInvoicesInput = Self::parse_input(args, name)?;
                match list_invoices(input, pool).await {
                    Ok(out) => Ok(Self::ok_result(out)),
                    Err(e) => Ok(Self::err_result(e)),
                }
            }
            "list_overdue_payments" => {
                let input: ListOverduePaymentsInput = Self::parse_input(args, name)?;
                match list_overdue_payments(input, pool).await {
                    Ok(out) => Ok(Self::ok_result(out)),
                    Err(e) => Ok(Self::err_result(e)),
                }
            }
            // ----------------------------------------------------------------
            // Subscriptions
            // ----------------------------------------------------------------
            "get_subscription" => {
                let input: GetSubscriptionInput = Self::parse_input(args, name)?;
                match get_subscription(input, pool).await {
                    Ok(out) => Ok(Self::ok_result(out)),
                    Err(e) => Ok(Self::err_result(e)),
                }
            }
            "check_subscription_status" => {
                let input: CheckSubscriptionStatusInput = Self::parse_input(args, name)?;
                match check_subscription_status(input, pool).await {
                    Ok(out) => Ok(Self::ok_result(out)),
                    Err(e) => Ok(Self::err_result(e)),
                }
            }
            "update_subscription_status" => {
                let input: UpdateSubscriptionStatusInput = Self::parse_input(args, name)?;
                match update_subscription_status(input, pool).await {
                    Ok(out) => Ok(Self::ok_result(out)),
                    Err(e) => Ok(Self::err_result(e)),
                }
            }
            // ----------------------------------------------------------------
            // Summary / Analytics
            // ----------------------------------------------------------------
            "get_customer_billing_summary" => {
                let input: GetCustomerBillingSummaryInput = Self::parse_input(args, name)?;
                match get_customer_billing_summary(input, pool).await {
                    Ok(out) => Ok(Self::ok_result(out)),
                    Err(e) => Ok(Self::err_result(e)),
                }
            }
            "get_mrr" => {
                let input: GetMrrInput = Self::parse_input(args, name)?;
                match get_mrr(input, pool).await {
                    Ok(out) => Ok(Self::ok_result(out)),
                    Err(e) => Ok(Self::err_result(e)),
                }
            }
            unknown => {
                error!("Unknown tool requested: {}", unknown);
                Err(McpError::internal_error(
                    format!("Unknown tool: {unknown}"),
                    None,
                ))
            }
        }
    }
}
