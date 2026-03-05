use anyhow::Context;
use rmcp::{
    model::{
        CallToolRequest, CallToolResult, Content, ListToolsResult, ServerCapabilities,
        ServerInfo, Tool,
    },
    server::ServerHandler,
    service::RequestContext,
    Error as McpError,
};
use serde_json::{json, Value};
use sqlx::PgPool;
use std::borrow::Cow;
use std::sync::Arc;
use tracing::{error, info, instrument};

use crate::errors::CrmError;
use crate::tools::{
    accounts::{
        create_account, get_account, search_accounts, update_account, CreateAccountInput,
        GetAccountInput, SearchAccountsInput, UpdateAccountInput,
    },
    activities::{
        list_activities, log_activity, ListActivitiesInput, LogActivityInput,
    },
    contacts::{
        create_contact, get_contact, search_contacts, update_contact, CreateContactInput,
        GetContactInput, SearchContactsInput, UpdateContactInput,
    },
    deals::{
        create_deal, delete_deal, get_deal, search_deals, update_deal_stage, CreateDealInput,
        DeleteDealInput, GetDealInput, SearchDealsInput, UpdateDealStageInput,
    },
    pipeline::{get_pipeline_summary, GetPipelineSummaryInput},
};

// ---------------------------------------------------------------------------
// CrmServer
// ---------------------------------------------------------------------------

#[derive(Clone)]
pub struct CrmServer {
    pool: Arc<PgPool>,
}

impl CrmServer {
    pub fn new(pool: PgPool) -> Self {
        Self {
            pool: Arc::new(pool),
        }
    }

    fn crm_error_to_mcp(err: CrmError) -> McpError {
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

    fn err_result(err: CrmError) -> CallToolResult {
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

#[rmcp::async_trait]
impl ServerHandler for CrmServer {
    fn get_info(&self) -> ServerInfo {
        ServerInfo {
            name: Cow::Borrowed("mcp-crm"),
            version: Cow::Borrowed(env!("CARGO_PKG_VERSION")),
            ..Default::default()
        }
    }

    fn get_capabilities(&self) -> ServerCapabilities {
        ServerCapabilities {
            tools: Some(rmcp::model::ToolsCapability { list_changed: None }),
            ..Default::default()
        }
    }

    #[instrument(skip(self, _ctx), name = "list_tools")]
    async fn list_tools(
        &self,
        _cursor: Option<String>,
        _ctx: RequestContext,
    ) -> Result<ListToolsResult, McpError> {
        let tools = vec![
            // ----------------------------------------------------------------
            // Contacts
            // ----------------------------------------------------------------
            Tool {
                name: Cow::Borrowed("get_contact"),
                description: Some(Cow::Borrowed(
                    "Retrieves a single CRM contact by ID for the given tenant.",
                )),
                input_schema: json!({
                    "type": "object",
                    "required": ["tenant_id", "contact_id"],
                    "properties": {
                        "tenant_id": { "type": "string", "format": "uuid" },
                        "user_id":   { "type": "string", "format": "uuid" },
                        "contact_id":{ "type": "string", "format": "uuid" }
                    }
                }),
            },
            Tool {
                name: Cow::Borrowed("search_contacts"),
                description: Some(Cow::Borrowed(
                    "Searches contacts by name/email with optional status and account filters.",
                )),
                input_schema: json!({
                    "type": "object",
                    "required": ["tenant_id"],
                    "properties": {
                        "tenant_id":  { "type": "string", "format": "uuid" },
                        "user_id":    { "type": "string", "format": "uuid" },
                        "query":      { "type": "string" },
                        "status":     { "type": "string", "enum": ["active","inactive","prospect","customer","churned"] },
                        "account_id": { "type": "string", "format": "uuid" },
                        "page":       { "type": "integer", "minimum": 1 },
                        "page_size":  { "type": "integer", "minimum": 1, "maximum": 100 }
                    }
                }),
            },
            Tool {
                name: Cow::Borrowed("create_contact"),
                description: Some(Cow::Borrowed(
                    "Creates a new contact in the CRM for the given tenant.",
                )),
                input_schema: json!({
                    "type": "object",
                    "required": ["tenant_id", "first_name", "last_name", "email"],
                    "properties": {
                        "tenant_id":     { "type": "string", "format": "uuid" },
                        "user_id":       { "type": "string", "format": "uuid" },
                        "first_name":    { "type": "string" },
                        "last_name":     { "type": "string" },
                        "email":         { "type": "string", "format": "email" },
                        "phone":         { "type": "string" },
                        "title":         { "type": "string" },
                        "account_id":    { "type": "string", "format": "uuid" },
                        "status":        { "type": "string", "enum": ["active","inactive","prospect","customer","churned"] },
                        "custom_fields": { "type": "object" }
                    }
                }),
            },
            Tool {
                name: Cow::Borrowed("update_contact"),
                description: Some(Cow::Borrowed(
                    "Partially updates an existing contact (PATCH semantics).",
                )),
                input_schema: json!({
                    "type": "object",
                    "required": ["tenant_id", "contact_id"],
                    "properties": {
                        "tenant_id":     { "type": "string", "format": "uuid" },
                        "user_id":       { "type": "string", "format": "uuid" },
                        "contact_id":    { "type": "string", "format": "uuid" },
                        "first_name":    { "type": "string" },
                        "last_name":     { "type": "string" },
                        "email":         { "type": "string", "format": "email" },
                        "phone":         { "type": "string" },
                        "title":         { "type": "string" },
                        "account_id":    { "type": "string", "format": "uuid" },
                        "status":        { "type": "string", "enum": ["active","inactive","prospect","customer","churned"] },
                        "custom_fields": { "type": "object" }
                    }
                }),
            },
            // ----------------------------------------------------------------
            // Accounts
            // ----------------------------------------------------------------
            Tool {
                name: Cow::Borrowed("get_account"),
                description: Some(Cow::Borrowed(
                    "Retrieves a single CRM account by ID.",
                )),
                input_schema: json!({
                    "type": "object",
                    "required": ["tenant_id", "account_id"],
                    "properties": {
                        "tenant_id":  { "type": "string", "format": "uuid" },
                        "user_id":    { "type": "string", "format": "uuid" },
                        "account_id": { "type": "string", "format": "uuid" }
                    }
                }),
            },
            Tool {
                name: Cow::Borrowed("search_accounts"),
                description: Some(Cow::Borrowed(
                    "Searches accounts by name/domain with optional industry filter.",
                )),
                input_schema: json!({
                    "type": "object",
                    "required": ["tenant_id"],
                    "properties": {
                        "tenant_id": { "type": "string", "format": "uuid" },
                        "user_id":   { "type": "string", "format": "uuid" },
                        "query":     { "type": "string" },
                        "industry":  { "type": "string" },
                        "page":      { "type": "integer", "minimum": 1 },
                        "page_size": { "type": "integer", "minimum": 1, "maximum": 100 }
                    }
                }),
            },
            Tool {
                name: Cow::Borrowed("create_account"),
                description: Some(Cow::Borrowed(
                    "Creates a new account/company in the CRM.",
                )),
                input_schema: json!({
                    "type": "object",
                    "required": ["tenant_id", "name"],
                    "properties": {
                        "tenant_id":      { "type": "string", "format": "uuid" },
                        "user_id":        { "type": "string", "format": "uuid" },
                        "name":           { "type": "string" },
                        "domain":         { "type": "string" },
                        "industry":       { "type": "string" },
                        "employee_count": { "type": "integer", "minimum": 0 },
                        "annual_revenue": { "type": "string" },
                        "custom_fields":  { "type": "object" }
                    }
                }),
            },
            Tool {
                name: Cow::Borrowed("update_account"),
                description: Some(Cow::Borrowed(
                    "Partially updates an existing account (PATCH semantics).",
                )),
                input_schema: json!({
                    "type": "object",
                    "required": ["tenant_id", "account_id"],
                    "properties": {
                        "tenant_id":      { "type": "string", "format": "uuid" },
                        "user_id":        { "type": "string", "format": "uuid" },
                        "account_id":     { "type": "string", "format": "uuid" },
                        "name":           { "type": "string" },
                        "domain":         { "type": "string" },
                        "industry":       { "type": "string" },
                        "employee_count": { "type": "integer", "minimum": 0 },
                        "annual_revenue": { "type": "string" },
                        "custom_fields":  { "type": "object" }
                    }
                }),
            },
            // ----------------------------------------------------------------
            // Deals
            // ----------------------------------------------------------------
            Tool {
                name: Cow::Borrowed("get_deal"),
                description: Some(Cow::Borrowed("Retrieves a single deal by ID.")),
                input_schema: json!({
                    "type": "object",
                    "required": ["tenant_id", "deal_id"],
                    "properties": {
                        "tenant_id": { "type": "string", "format": "uuid" },
                        "user_id":   { "type": "string", "format": "uuid" },
                        "deal_id":   { "type": "string", "format": "uuid" }
                    }
                }),
            },
            Tool {
                name: Cow::Borrowed("search_deals"),
                description: Some(Cow::Borrowed(
                    "Searches deals with optional stage, account and assignee filters.",
                )),
                input_schema: json!({
                    "type": "object",
                    "required": ["tenant_id"],
                    "properties": {
                        "tenant_id":   { "type": "string", "format": "uuid" },
                        "user_id":     { "type": "string", "format": "uuid" },
                        "query":       { "type": "string" },
                        "stage":       { "type": "string", "enum": ["prospecting","qualification","proposal","negotiation","closed_won","closed_lost"] },
                        "account_id":  { "type": "string", "format": "uuid" },
                        "assigned_to": { "type": "string", "format": "uuid" },
                        "page":        { "type": "integer", "minimum": 1 },
                        "page_size":   { "type": "integer", "minimum": 1, "maximum": 100 }
                    }
                }),
            },
            Tool {
                name: Cow::Borrowed("create_deal"),
                description: Some(Cow::Borrowed(
                    "Creates a new deal in the pipeline for the given account.",
                )),
                input_schema: json!({
                    "type": "object",
                    "required": ["tenant_id", "name", "account_id", "value", "currency", "close_date"],
                    "properties": {
                        "tenant_id":     { "type": "string", "format": "uuid" },
                        "user_id":       { "type": "string", "format": "uuid" },
                        "name":          { "type": "string" },
                        "account_id":    { "type": "string", "format": "uuid" },
                        "value":         { "type": "string", "description": "Decimal amount" },
                        "currency":      { "type": "string", "minLength": 3, "maxLength": 3 },
                        "stage":         { "type": "string", "enum": ["prospecting","qualification","proposal","negotiation","closed_won","closed_lost"] },
                        "probability":   { "type": "number", "minimum": 0, "maximum": 1 },
                        "close_date":    { "type": "string", "format": "date" },
                        "assigned_to":   { "type": "string", "format": "uuid" },
                        "custom_fields": { "type": "object" }
                    }
                }),
            },
            Tool {
                name: Cow::Borrowed("update_deal_stage"),
                description: Some(Cow::Borrowed(
                    "Transitions a deal to a new pipeline stage. Validates allowed transitions.",
                )),
                input_schema: json!({
                    "type": "object",
                    "required": ["tenant_id", "deal_id", "new_stage"],
                    "properties": {
                        "tenant_id": { "type": "string", "format": "uuid" },
                        "user_id":   { "type": "string", "format": "uuid" },
                        "deal_id":   { "type": "string", "format": "uuid" },
                        "new_stage": { "type": "string", "enum": ["prospecting","qualification","proposal","negotiation","closed_won","closed_lost"] },
                        "reason":    { "type": "string" }
                    }
                }),
            },
            Tool {
                name: Cow::Borrowed("delete_deal"),
                description: Some(Cow::Borrowed(
                    "Permanently deletes a deal. Requires permission 'crm:deals:delete'.",
                )),
                input_schema: json!({
                    "type": "object",
                    "required": ["tenant_id", "deal_id", "permission"],
                    "properties": {
                        "tenant_id":  { "type": "string", "format": "uuid" },
                        "user_id":    { "type": "string", "format": "uuid" },
                        "deal_id":    { "type": "string", "format": "uuid" },
                        "permission": { "type": "string", "const": "crm:deals:delete" }
                    }
                }),
            },
            // ----------------------------------------------------------------
            // Pipeline
            // ----------------------------------------------------------------
            Tool {
                name: Cow::Borrowed("get_pipeline_summary"),
                description: Some(Cow::Borrowed(
                    "Returns aggregated pipeline stats per stage: deal count, total value, avg value, avg age.",
                )),
                input_schema: json!({
                    "type": "object",
                    "required": ["tenant_id"],
                    "properties": {
                        "tenant_id":   { "type": "string", "format": "uuid" },
                        "user_id":     { "type": "string", "format": "uuid" },
                        "assigned_to": { "type": "string", "format": "uuid" }
                    }
                }),
            },
            // ----------------------------------------------------------------
            // Activities
            // ----------------------------------------------------------------
            Tool {
                name: Cow::Borrowed("list_activities"),
                description: Some(Cow::Borrowed(
                    "Lists activities for a given entity (contact, deal, or account).",
                )),
                input_schema: json!({
                    "type": "object",
                    "required": ["tenant_id", "entity_type", "entity_id"],
                    "properties": {
                        "tenant_id":     { "type": "string", "format": "uuid" },
                        "user_id":       { "type": "string", "format": "uuid" },
                        "entity_type":   { "type": "string", "enum": ["contact","deal","account"] },
                        "entity_id":     { "type": "string", "format": "uuid" },
                        "activity_type": { "type": "string", "enum": ["call","email","meeting","note","task"] },
                        "page":          { "type": "integer", "minimum": 1 },
                        "page_size":     { "type": "integer", "minimum": 1, "maximum": 100 }
                    }
                }),
            },
            Tool {
                name: Cow::Borrowed("log_activity"),
                description: Some(Cow::Borrowed(
                    "Logs a new activity (call, email, meeting, note, task) against an entity.",
                )),
                input_schema: json!({
                    "type": "object",
                    "required": ["tenant_id", "entity_type", "entity_id", "activity_type", "subject", "performed_by"],
                    "properties": {
                        "tenant_id":        { "type": "string", "format": "uuid" },
                        "user_id":          { "type": "string", "format": "uuid" },
                        "entity_type":      { "type": "string", "enum": ["contact","deal","account"] },
                        "entity_id":        { "type": "string", "format": "uuid" },
                        "activity_type":    { "type": "string", "enum": ["call","email","meeting","note","task"] },
                        "subject":          { "type": "string" },
                        "notes":            { "type": "string" },
                        "duration_minutes": { "type": "integer", "minimum": 0 },
                        "performed_by":     { "type": "string", "format": "uuid" },
                        "occurred_at":      { "type": "string", "format": "date-time" }
                    }
                }),
            },
        ];

        Ok(ListToolsResult {
            tools,
            next_cursor: None,
        })
    }

    #[instrument(skip(self, _ctx), name = "call_tool", fields(tool = %request.params.name))]
    async fn call_tool(
        &self,
        request: CallToolRequest,
        _ctx: RequestContext,
    ) -> Result<CallToolResult, McpError> {
        let name = request.params.name.as_ref();
        let args = request.params.arguments.clone();
        let pool = self.pool.as_ref();

        info!("Dispatching tool: {}", name);

        match name {
            "get_contact" => {
                let input: GetContactInput = Self::parse_input(args, name)?;
                match get_contact(input, pool).await {
                    Ok(out) => Ok(Self::ok_result(out)),
                    Err(e) => Ok(Self::err_result(e)),
                }
            }
            "search_contacts" => {
                let input: SearchContactsInput = Self::parse_input(args, name)?;
                match search_contacts(input, pool).await {
                    Ok(out) => Ok(Self::ok_result(out)),
                    Err(e) => Ok(Self::err_result(e)),
                }
            }
            "create_contact" => {
                let input: CreateContactInput = Self::parse_input(args, name)?;
                match create_contact(input, pool).await {
                    Ok(out) => Ok(Self::ok_result(out)),
                    Err(e) => Ok(Self::err_result(e)),
                }
            }
            "update_contact" => {
                let input: UpdateContactInput = Self::parse_input(args, name)?;
                match update_contact(input, pool).await {
                    Ok(out) => Ok(Self::ok_result(out)),
                    Err(e) => Ok(Self::err_result(e)),
                }
            }
            "get_account" => {
                let input: GetAccountInput = Self::parse_input(args, name)?;
                match get_account(input, pool).await {
                    Ok(out) => Ok(Self::ok_result(out)),
                    Err(e) => Ok(Self::err_result(e)),
                }
            }
            "search_accounts" => {
                let input: SearchAccountsInput = Self::parse_input(args, name)?;
                match search_accounts(input, pool).await {
                    Ok(out) => Ok(Self::ok_result(out)),
                    Err(e) => Ok(Self::err_result(e)),
                }
            }
            "create_account" => {
                let input: CreateAccountInput = Self::parse_input(args, name)?;
                match create_account(input, pool).await {
                    Ok(out) => Ok(Self::ok_result(out)),
                    Err(e) => Ok(Self::err_result(e)),
                }
            }
            "update_account" => {
                let input: UpdateAccountInput = Self::parse_input(args, name)?;
                match update_account(input, pool).await {
                    Ok(out) => Ok(Self::ok_result(out)),
                    Err(e) => Ok(Self::err_result(e)),
                }
            }
            "get_deal" => {
                let input: GetDealInput = Self::parse_input(args, name)?;
                match get_deal(input, pool).await {
                    Ok(out) => Ok(Self::ok_result(out)),
                    Err(e) => Ok(Self::err_result(e)),
                }
            }
            "search_deals" => {
                let input: SearchDealsInput = Self::parse_input(args, name)?;
                match search_deals(input, pool).await {
                    Ok(out) => Ok(Self::ok_result(out)),
                    Err(e) => Ok(Self::err_result(e)),
                }
            }
            "create_deal" => {
                let input: CreateDealInput = Self::parse_input(args, name)?;
                match create_deal(input, pool).await {
                    Ok(out) => Ok(Self::ok_result(out)),
                    Err(e) => Ok(Self::err_result(e)),
                }
            }
            "update_deal_stage" => {
                let input: UpdateDealStageInput = Self::parse_input(args, name)?;
                match update_deal_stage(input, pool).await {
                    Ok(out) => Ok(Self::ok_result(out)),
                    Err(e) => Ok(Self::err_result(e)),
                }
            }
            "delete_deal" => {
                let input: DeleteDealInput = Self::parse_input(args, name)?;
                match delete_deal(input, pool).await {
                    Ok(out) => Ok(Self::ok_result(out)),
                    Err(e) => Ok(Self::err_result(e)),
                }
            }
            "get_pipeline_summary" => {
                let input: GetPipelineSummaryInput = Self::parse_input(args, name)?;
                match get_pipeline_summary(input, pool).await {
                    Ok(out) => Ok(Self::ok_result(out)),
                    Err(e) => Ok(Self::err_result(e)),
                }
            }
            "list_activities" => {
                let input: ListActivitiesInput = Self::parse_input(args, name)?;
                match list_activities(input, pool).await {
                    Ok(out) => Ok(Self::ok_result(out)),
                    Err(e) => Ok(Self::err_result(e)),
                }
            }
            "log_activity" => {
                let input: LogActivityInput = Self::parse_input(args, name)?;
                match log_activity(input, pool).await {
                    Ok(out) => Ok(Self::ok_result(out)),
                    Err(e) => Ok(Self::err_result(e)),
                }
            }
            unknown => {
                error!("Unknown tool requested: {}", unknown);
                Err(McpError::method_not_found(
                    format!("Unknown tool: {unknown}"),
                ))
            }
        }
    }
}
