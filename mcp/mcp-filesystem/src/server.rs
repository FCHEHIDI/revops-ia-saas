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

fn s(v: Value) -> std::sync::Arc<Map<String, Value>> {
    std::sync::Arc::new(v.as_object().cloned().unwrap_or_default())
}
use sqlx::PgPool;
use std::borrow::Cow;
use std::sync::Arc;
use tracing::{error, info, instrument};

use crate::errors::FilesystemError;
use crate::rag_client::RagClient;
use crate::storage::ObjectStorage;
use crate::tools::{
    documents::{
        delete_document, get_document_metadata, list_documents, read_document,
        DeleteDocumentInput, GetDocumentMetadataInput, ListDocumentsInput, ReadDocumentInput,
    },
    playbooks::{get_playbook, list_playbooks, GetPlaybookInput, ListPlaybooksInput},
    reports::{list_reports, upload_report, ListReportsInput, UploadReportInput},
    search::{search_documents, SearchDocumentsInput},
};

// ---------------------------------------------------------------------------
// FilesystemServer
// ---------------------------------------------------------------------------

#[derive(Clone)]
pub struct FilesystemServer {
    pool: Arc<PgPool>,
    storage: Arc<dyn ObjectStorage>,
    rag_client: Arc<RagClient>,
}

impl FilesystemServer {
    pub fn new(
        pool: PgPool,
        storage: Arc<dyn ObjectStorage>,
        rag_client: RagClient,
    ) -> Self {
        Self {
            pool: Arc::new(pool),
            storage,
            rag_client: Arc::new(rag_client),
        }
    }

    fn fs_error_to_mcp(err: FilesystemError) -> McpError {
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

    fn err_result(err: FilesystemError) -> CallToolResult {
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
// ServerHandler
// ---------------------------------------------------------------------------

impl ServerHandler for FilesystemServer {
    fn get_info(&self) -> ServerInfo {
        ServerInfo {
            capabilities: ServerCapabilities {
                tools: Some(rmcp::model::ToolsCapability { list_changed: None }),
                ..Default::default()
            },
            server_info: rmcp::model::Implementation {
                name: "mcp-filesystem".to_string(),
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
            // Documents
            // ----------------------------------------------------------------
            Tool {
                name: Cow::Borrowed("read_document"),
                description: Cow::Borrowed(
                    "Reads the text content of a document by ID. Returns up to max_chars characters (default 10 000, max 50 000). Never exposes storage paths.",
                ),
                input_schema: s(json!({
                    "type": "object",
                    "required": ["tenant_id", "document_id"],
                    "properties": {
                        "tenant_id":   { "type": "string", "format": "uuid" },
                        "user_id":     { "type": "string", "format": "uuid" },
                        "document_id": { "type": "string", "format": "uuid" },
                        "max_chars":   { "type": "integer", "minimum": 1, "maximum": 50000, "default": 10000 },
                        "page_range":  {
                            "type": "array",
                            "items": { "type": "integer", "minimum": 1 },
                            "minItems": 2,
                            "maxItems": 2
                        }
                    }
                })),
            },
            Tool {
                name: Cow::Borrowed("list_documents"),
                description: Cow::Borrowed(
                    "Lists documents for a tenant with optional filters on type, tags, filename search, and upload date. Never exposes storage paths.",
                ),
                input_schema: s(json!({
                    "type": "object",
                    "required": ["tenant_id"],
                    "properties": {
                        "tenant_id":      { "type": "string", "format": "uuid" },
                        "user_id":        { "type": "string", "format": "uuid" },
                        "document_type":  { "type": "string", "enum": ["playbook","report","contract","proposal","presentation","datasheet","internal","other"] },
                        "tags":           { "type": "array", "items": { "type": "string" } },
                        "search_query":   { "type": "string" },
                        "uploaded_after": { "type": "string", "format": "date-time" },
                        "limit":          { "type": "integer", "minimum": 1, "maximum": 200, "default": 50 },
                        "offset":         { "type": "integer", "minimum": 0, "default": 0 }
                    }
                })),
            },
            Tool {
                name: Cow::Borrowed("get_document_metadata"),
                description: Cow::Borrowed(
                    "Returns metadata for a single document (filename, type, MIME, size, tags, RAG index status). Never includes storage path.",
                ),
                input_schema: s(json!({
                    "type": "object",
                    "required": ["tenant_id", "document_id"],
                    "properties": {
                        "tenant_id":   { "type": "string", "format": "uuid" },
                        "user_id":     { "type": "string", "format": "uuid" },
                        "document_id": { "type": "string", "format": "uuid" }
                    }
                })),
            },
            Tool {
                name: Cow::Borrowed("delete_document"),
                description: Cow::Borrowed(
                    "Permanently deletes a document and its storage object. Requires confirm=true. Returns bytes freed.",
                ),
                input_schema: s(json!({
                    "type": "object",
                    "required": ["tenant_id", "document_id", "confirm"],
                    "properties": {
                        "tenant_id":   { "type": "string", "format": "uuid" },
                        "user_id":     { "type": "string", "format": "uuid" },
                        "document_id": { "type": "string", "format": "uuid" },
                        "confirm":     { "type": "boolean", "description": "Must be true to confirm permanent deletion" }
                    }
                })),
            },
            // ----------------------------------------------------------------
            // Playbooks
            // ----------------------------------------------------------------
            Tool {
                name: Cow::Borrowed("list_playbooks"),
                description: Cow::Borrowed(
                    "Lists active playbooks for a tenant, optionally filtered by category and tags.",
                ),
                input_schema: s(json!({
                    "type": "object",
                    "required": ["tenant_id"],
                    "properties": {
                        "tenant_id": { "type": "string", "format": "uuid" },
                        "user_id":   { "type": "string", "format": "uuid" },
                        "category":  { "type": "string", "enum": ["sales_process","objection_handling","battle_card","onboarding","competitive_analysis","pricing_guide"] },
                        "tags":      { "type": "array", "items": { "type": "string" } },
                        "limit":     { "type": "integer", "minimum": 1, "maximum": 200, "default": 50 },
                        "offset":    { "type": "integer", "minimum": 0, "default": 0 }
                    }
                })),
            },
            Tool {
                name: Cow::Borrowed("get_playbook"),
                description: Cow::Borrowed(
                    "Returns the full content (markdown) of an active playbook by ID.",
                ),
                input_schema: s(json!({
                    "type": "object",
                    "required": ["tenant_id", "playbook_id"],
                    "properties": {
                        "tenant_id":   { "type": "string", "format": "uuid" },
                        "user_id":     { "type": "string", "format": "uuid" },
                        "playbook_id": { "type": "string", "format": "uuid" }
                    }
                })),
            },
            // ----------------------------------------------------------------
            // Reports
            // ----------------------------------------------------------------
            Tool {
                name: Cow::Borrowed("upload_report"),
                description: Cow::Borrowed(
                    "Uploads a text/markdown/JSON/HTML report (max 5 MB). Optionally queues it for RAG ingestion. Returns document_id and ingestion job_id if queued.",
                ),
                input_schema: s(json!({
                    "type": "object",
                    "required": ["tenant_id", "filename", "content", "mime_type", "report_type", "tags", "ingest_to_rag", "metadata"],
                    "properties": {
                        "tenant_id":    { "type": "string", "format": "uuid" },
                        "user_id":      { "type": "string", "format": "uuid" },
                        "filename":     { "type": "string" },
                        "content":      { "type": "string", "description": "Raw text content (max 5 000 000 chars)" },
                        "mime_type":    { "type": "string", "enum": ["text/plain","text/markdown","application/json","text/html"] },
                        "report_type":  { "type": "string", "enum": ["pipeline_analysis","churn_report","forecast_report","performance_report","custom_report"] },
                        "tags":         { "type": "array", "items": { "type": "string" } },
                        "ingest_to_rag":{ "type": "boolean" },
                        "metadata":     { "type": "object" }
                    }
                })),
            },
            Tool {
                name: Cow::Borrowed("list_reports"),
                description: Cow::Borrowed(
                    "Lists uploaded reports for a tenant, optionally filtered by type and date range.",
                ),
                input_schema: s(json!({
                    "type": "object",
                    "required": ["tenant_id"],
                    "properties": {
                        "tenant_id":   { "type": "string", "format": "uuid" },
                        "user_id":     { "type": "string", "format": "uuid" },
                        "report_type": { "type": "string", "enum": ["pipeline_analysis","churn_report","forecast_report","performance_report","custom_report"] },
                        "from_date":   { "type": "string", "format": "date" },
                        "to_date":     { "type": "string", "format": "date" },
                        "limit":       { "type": "integer", "minimum": 1, "maximum": 200, "default": 50 },
                        "offset":      { "type": "integer", "minimum": 0, "default": 0 }
                    }
                })),
            },
            // ----------------------------------------------------------------
            // Search
            // ----------------------------------------------------------------
            Tool {
                name: Cow::Borrowed("search_documents"),
                description: Cow::Borrowed(
                    "Performs semantic search over tenant documents via the RAG service. Returns ranked chunks with similarity scores. top_k default=5 max=20.",
                ),
                input_schema: s(json!({
                    "type": "object",
                    "required": ["tenant_id", "query"],
                    "properties": {
                        "tenant_id":      { "type": "string", "format": "uuid" },
                        "user_id":        { "type": "string", "format": "uuid" },
                        "query":          { "type": "string", "minLength": 1 },
                        "document_types": { "type": "array", "items": { "type": "string", "enum": ["playbook","report","contract","proposal","presentation","datasheet","internal","other"] } },
                        "top_k":          { "type": "integer", "minimum": 1, "maximum": 20, "default": 5 },
                        "min_score":      { "type": "number", "minimum": 0.0, "maximum": 1.0, "default": 0.5 }
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
        let storage = self.storage.as_ref();
        let rag = self.rag_client.as_ref();

        info!("Dispatching tool: {}", name);

        match name {
            // Documents
            "read_document" => {
                let input: ReadDocumentInput = Self::parse_input(args, name)?;
                match read_document(input, pool, storage).await {
                    Ok(out) => Ok(Self::ok_result(out)),
                    Err(e) => Ok(Self::err_result(e)),
                }
            }
            "list_documents" => {
                let input: ListDocumentsInput = Self::parse_input(args, name)?;
                match list_documents(input, pool).await {
                    Ok(out) => Ok(Self::ok_result(out)),
                    Err(e) => Ok(Self::err_result(e)),
                }
            }
            "get_document_metadata" => {
                let input: GetDocumentMetadataInput = Self::parse_input(args, name)?;
                match get_document_metadata(input, pool).await {
                    Ok(out) => Ok(Self::ok_result(out)),
                    Err(e) => Ok(Self::err_result(e)),
                }
            }
            "delete_document" => {
                let input: DeleteDocumentInput = Self::parse_input(args, name)?;
                match delete_document(input, pool, storage).await {
                    Ok(out) => Ok(Self::ok_result(out)),
                    Err(e) => Ok(Self::err_result(e)),
                }
            }
            // Playbooks
            "list_playbooks" => {
                let input: ListPlaybooksInput = Self::parse_input(args, name)?;
                match list_playbooks(input, pool).await {
                    Ok(out) => Ok(Self::ok_result(out)),
                    Err(e) => Ok(Self::err_result(e)),
                }
            }
            "get_playbook" => {
                let input: GetPlaybookInput = Self::parse_input(args, name)?;
                match get_playbook(input, pool).await {
                    Ok(out) => Ok(Self::ok_result(out)),
                    Err(e) => Ok(Self::err_result(e)),
                }
            }
            // Reports
            "upload_report" => {
                let input: UploadReportInput = Self::parse_input(args, name)?;
                match upload_report(input, pool, storage, rag).await {
                    Ok(out) => Ok(Self::ok_result(out)),
                    Err(e) => Ok(Self::err_result(e)),
                }
            }
            "list_reports" => {
                let input: ListReportsInput = Self::parse_input(args, name)?;
                match list_reports(input, pool).await {
                    Ok(out) => Ok(Self::ok_result(out)),
                    Err(e) => Ok(Self::err_result(e)),
                }
            }
            // Search
            "search_documents" => {
                let input: SearchDocumentsInput = Self::parse_input(args, name)?;
                match search_documents(input, pool, rag).await {
                    Ok(out) => Ok(Self::ok_result(out)),
                    Err(e) => Ok(Self::err_result(e)),
                }
            }
            unknown => {
                error!("Unknown tool requested: {}", unknown);
                Err(McpError::internal_error(format!("Unknown tool: {unknown}"), None))
            }
        }
    }
}
