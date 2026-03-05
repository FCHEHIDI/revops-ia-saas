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

use crate::errors::SequencesError;
use crate::tools::{
    analytics::{get_sequence_performance, GetSequencePerformanceInput},
    enrollment::{
        enroll_contact, list_enrollments, unenroll_contact, EnrollContactInput,
        ListEnrollmentsInput, UnenrollContactInput,
    },
    execution::{pause_sequence, resume_sequence, PauseSequenceInput, ResumeSequenceInput},
    sequences::{
        create_sequence, delete_sequence, get_sequence, list_sequences, update_sequence,
        CreateSequenceInput, DeleteSequenceInput, GetSequenceInput, ListSequencesInput,
        UpdateSequenceInput,
    },
};

// ---------------------------------------------------------------------------
// SequencesServer
// ---------------------------------------------------------------------------

#[derive(Clone)]
pub struct SequencesServer {
    pool: Arc<PgPool>,
}

impl SequencesServer {
    pub fn new(pool: PgPool) -> Self {
        Self {
            pool: Arc::new(pool),
        }
    }

    fn seq_error_to_mcp(err: SequencesError) -> McpError {
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

    fn err_result(err: SequencesError) -> CallToolResult {
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
impl ServerHandler for SequencesServer {
    fn get_info(&self) -> ServerInfo {
        ServerInfo {
            name: Cow::Borrowed("mcp-sequences"),
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
            // Sequences CRUD
            // ----------------------------------------------------------------
            Tool {
                name: Cow::Borrowed("create_sequence"),
                description: Some(Cow::Borrowed(
                    "Creates a new outreach sequence with steps and exit conditions. Permission: sequences:write.",
                )),
                input_schema: json!({
                    "type": "object",
                    "required": ["tenant_id", "user_id", "name", "steps"],
                    "properties": {
                        "tenant_id":       { "type": "string", "format": "uuid" },
                        "user_id":         { "type": "string", "format": "uuid" },
                        "name":            { "type": "string" },
                        "description":     { "type": "string" },
                        "steps": {
                            "type": "array",
                            "minItems": 1,
                            "items": {
                                "type": "object",
                                "required": ["step_type", "delay_days", "delay_hours"],
                                "properties": {
                                    "step_type":      { "type": "string", "enum": ["email","linkedin_message","task","call","wait"] },
                                    "delay_days":     { "type": "integer", "minimum": 0 },
                                    "delay_hours":    { "type": "integer", "minimum": 0, "maximum": 23 },
                                    "template_id":    { "type": "string", "format": "uuid" },
                                    "subject":        { "type": "string" },
                                    "body_template":  { "type": "string" }
                                }
                            }
                        },
                        "exit_conditions": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "required": ["condition_type"],
                                "properties": {
                                    "condition_type": { "type": "string", "enum": ["replied","clicked","meeting_booked","manual_unenroll","deal_stage_changed"] },
                                    "parameters":     { "type": "object" }
                                }
                            }
                        },
                        "tags": { "type": "array", "items": { "type": "string" } }
                    }
                }),
            },
            Tool {
                name: Cow::Borrowed("update_sequence"),
                description: Some(Cow::Borrowed(
                    "Updates sequence metadata. Blocked by active enrollments unless force=true. Permission: sequences:write.",
                )),
                input_schema: json!({
                    "type": "object",
                    "required": ["tenant_id", "user_id", "sequence_id"],
                    "properties": {
                        "tenant_id":   { "type": "string", "format": "uuid" },
                        "user_id":     { "type": "string", "format": "uuid" },
                        "sequence_id": { "type": "string", "format": "uuid" },
                        "name":        { "type": "string" },
                        "description": { "type": "string" },
                        "tags":        { "type": "array", "items": { "type": "string" } },
                        "force":       { "type": "boolean", "default": false }
                    }
                }),
            },
            Tool {
                name: Cow::Borrowed("delete_sequence"),
                description: Some(Cow::Borrowed(
                    "Deletes a sequence. With force=true, unenrolls active contacts first. Permission: sequences:delete.",
                )),
                input_schema: json!({
                    "type": "object",
                    "required": ["tenant_id", "user_id", "sequence_id"],
                    "properties": {
                        "tenant_id":   { "type": "string", "format": "uuid" },
                        "user_id":     { "type": "string", "format": "uuid" },
                        "sequence_id": { "type": "string", "format": "uuid" },
                        "force":       { "type": "boolean", "default": false }
                    }
                }),
            },
            Tool {
                name: Cow::Borrowed("get_sequence"),
                description: Some(Cow::Borrowed(
                    "Retrieves a sequence by ID with all its steps. Permission: sequences:read.",
                )),
                input_schema: json!({
                    "type": "object",
                    "required": ["tenant_id", "sequence_id"],
                    "properties": {
                        "tenant_id":   { "type": "string", "format": "uuid" },
                        "user_id":     { "type": "string", "format": "uuid" },
                        "sequence_id": { "type": "string", "format": "uuid" }
                    }
                }),
            },
            Tool {
                name: Cow::Borrowed("list_sequences"),
                description: Some(Cow::Borrowed(
                    "Lists sequences with optional status and tag filters. Permission: sequences:read.",
                )),
                input_schema: json!({
                    "type": "object",
                    "required": ["tenant_id"],
                    "properties": {
                        "tenant_id": { "type": "string", "format": "uuid" },
                        "user_id":   { "type": "string", "format": "uuid" },
                        "status":    { "type": "string", "enum": ["active","paused","draft","archived"] },
                        "tags":      { "type": "array", "items": { "type": "string" } },
                        "limit":     { "type": "integer", "minimum": 1, "maximum": 200 },
                        "offset":    { "type": "integer", "minimum": 0 }
                    }
                }),
            },
            // ----------------------------------------------------------------
            // Enrollment
            // ----------------------------------------------------------------
            Tool {
                name: Cow::Borrowed("enroll_contact"),
                description: Some(Cow::Borrowed(
                    "Enrolls a contact into an active sequence. Permission: sequences:write.",
                )),
                input_schema: json!({
                    "type": "object",
                    "required": ["tenant_id", "user_id", "sequence_id", "contact_id"],
                    "properties": {
                        "tenant_id":           { "type": "string", "format": "uuid" },
                        "user_id":             { "type": "string", "format": "uuid" },
                        "sequence_id":         { "type": "string", "format": "uuid" },
                        "contact_id":          { "type": "string", "format": "uuid" },
                        "start_at":            { "type": "string", "format": "date-time" },
                        "custom_variables":    { "type": "object" },
                        "override_if_enrolled":{ "type": "boolean", "default": false }
                    }
                }),
            },
            Tool {
                name: Cow::Borrowed("unenroll_contact"),
                description: Some(Cow::Borrowed(
                    "Unenrolls a contact from a sequence by enrollment ID. Permission: sequences:write.",
                )),
                input_schema: json!({
                    "type": "object",
                    "required": ["tenant_id", "user_id", "enrollment_id", "reason"],
                    "properties": {
                        "tenant_id":     { "type": "string", "format": "uuid" },
                        "user_id":       { "type": "string", "format": "uuid" },
                        "enrollment_id": { "type": "string", "format": "uuid" },
                        "reason":        { "type": "string", "enum": ["replied","converted","manual","bounced"] }
                    }
                }),
            },
            Tool {
                name: Cow::Borrowed("list_enrollments"),
                description: Some(Cow::Borrowed(
                    "Lists enrollments for a sequence with optional status filter. Permission: sequences:read.",
                )),
                input_schema: json!({
                    "type": "object",
                    "required": ["tenant_id", "sequence_id"],
                    "properties": {
                        "tenant_id":   { "type": "string", "format": "uuid" },
                        "user_id":     { "type": "string", "format": "uuid" },
                        "sequence_id": { "type": "string", "format": "uuid" },
                        "status":      { "type": "string", "enum": ["pending","active","paused","completed","unenrolled","failed"] },
                        "limit":       { "type": "integer", "minimum": 1, "maximum": 200 },
                        "offset":      { "type": "integer", "minimum": 0 }
                    }
                }),
            },
            // ----------------------------------------------------------------
            // Execution
            // ----------------------------------------------------------------
            Tool {
                name: Cow::Borrowed("pause_sequence"),
                description: Some(Cow::Borrowed(
                    "Pauses a sequence and all its active enrollments. Permission: sequences:write.",
                )),
                input_schema: json!({
                    "type": "object",
                    "required": ["tenant_id", "user_id", "sequence_id"],
                    "properties": {
                        "tenant_id":   { "type": "string", "format": "uuid" },
                        "user_id":     { "type": "string", "format": "uuid" },
                        "sequence_id": { "type": "string", "format": "uuid" },
                        "reason":      { "type": "string" }
                    }
                }),
            },
            Tool {
                name: Cow::Borrowed("resume_sequence"),
                description: Some(Cow::Borrowed(
                    "Resumes a paused sequence and reactivates paused enrollments. Permission: sequences:write.",
                )),
                input_schema: json!({
                    "type": "object",
                    "required": ["tenant_id", "user_id", "sequence_id"],
                    "properties": {
                        "tenant_id":   { "type": "string", "format": "uuid" },
                        "user_id":     { "type": "string", "format": "uuid" },
                        "sequence_id": { "type": "string", "format": "uuid" }
                    }
                }),
            },
            // ----------------------------------------------------------------
            // Analytics
            // ----------------------------------------------------------------
            Tool {
                name: Cow::Borrowed("get_sequence_performance"),
                description: Some(Cow::Borrowed(
                    "Returns performance metrics for a sequence: enrollment stats, email rates per step. Permission: sequences:read.",
                )),
                input_schema: json!({
                    "type": "object",
                    "required": ["tenant_id", "sequence_id"],
                    "properties": {
                        "tenant_id":    { "type": "string", "format": "uuid" },
                        "user_id":      { "type": "string", "format": "uuid" },
                        "sequence_id":  { "type": "string", "format": "uuid" },
                        "period_start": { "type": "string", "format": "date" },
                        "period_end":   { "type": "string", "format": "date" }
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
            "create_sequence" => {
                let input: CreateSequenceInput = Self::parse_input(args, name)?;
                match create_sequence(input, pool).await {
                    Ok(out) => Ok(Self::ok_result(out)),
                    Err(e) => Ok(Self::err_result(e)),
                }
            }
            "update_sequence" => {
                let input: UpdateSequenceInput = Self::parse_input(args, name)?;
                match update_sequence(input, pool).await {
                    Ok(out) => Ok(Self::ok_result(out)),
                    Err(e) => Ok(Self::err_result(e)),
                }
            }
            "delete_sequence" => {
                let input: DeleteSequenceInput = Self::parse_input(args, name)?;
                match delete_sequence(input, pool).await {
                    Ok(out) => Ok(Self::ok_result(out)),
                    Err(e) => Ok(Self::err_result(e)),
                }
            }
            "get_sequence" => {
                let input: GetSequenceInput = Self::parse_input(args, name)?;
                match get_sequence(input, pool).await {
                    Ok(out) => Ok(Self::ok_result(out)),
                    Err(e) => Ok(Self::err_result(e)),
                }
            }
            "list_sequences" => {
                let input: ListSequencesInput = Self::parse_input(args, name)?;
                match list_sequences(input, pool).await {
                    Ok(out) => Ok(Self::ok_result(out)),
                    Err(e) => Ok(Self::err_result(e)),
                }
            }
            "enroll_contact" => {
                let input: EnrollContactInput = Self::parse_input(args, name)?;
                match enroll_contact(input, pool).await {
                    Ok(out) => Ok(Self::ok_result(out)),
                    Err(e) => Ok(Self::err_result(e)),
                }
            }
            "unenroll_contact" => {
                let input: UnenrollContactInput = Self::parse_input(args, name)?;
                match unenroll_contact(input, pool).await {
                    Ok(out) => Ok(Self::ok_result(out)),
                    Err(e) => Ok(Self::err_result(e)),
                }
            }
            "list_enrollments" => {
                let input: ListEnrollmentsInput = Self::parse_input(args, name)?;
                match list_enrollments(input, pool).await {
                    Ok(out) => Ok(Self::ok_result(out)),
                    Err(e) => Ok(Self::err_result(e)),
                }
            }
            "pause_sequence" => {
                let input: PauseSequenceInput = Self::parse_input(args, name)?;
                match pause_sequence(input, pool).await {
                    Ok(out) => Ok(Self::ok_result(out)),
                    Err(e) => Ok(Self::err_result(e)),
                }
            }
            "resume_sequence" => {
                let input: ResumeSequenceInput = Self::parse_input(args, name)?;
                match resume_sequence(input, pool).await {
                    Ok(out) => Ok(Self::ok_result(out)),
                    Err(e) => Ok(Self::err_result(e)),
                }
            }
            "get_sequence_performance" => {
                let input: GetSequencePerformanceInput = Self::parse_input(args, name)?;
                match get_sequence_performance(input, pool).await {
                    Ok(out) => Ok(Self::ok_result(out)),
                    Err(e) => Ok(Self::err_result(e)),
                }
            }
            unknown => {
                error!("Unknown tool requested: {}", unknown);
                Err(McpError::method_not_found(format!(
                    "Unknown tool: {unknown}"
                )))
            }
        }
    }
}
