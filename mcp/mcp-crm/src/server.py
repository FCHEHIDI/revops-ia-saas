from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from config import get_settings
from errors import error_response
from http_client import build_client
from schemas import TOOL_SCHEMAS
from tools import TOOL_REGISTRY

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    app.state.settings = settings
    app.state.http_client = build_client(settings)
    logger.info(
        "mcp-crm server started — backend=%s tools=%d",
        settings.BACKEND_URL,
        len(TOOL_REGISTRY),
    )
    yield
    await app.state.http_client.aclose()
    logger.info("mcp-crm server shutting down")


app = FastAPI(
    title="mcp-crm",
    description="MCP CRM server — proxy to backend /internal/v1/crm/*",
    version="1.0.0",
    lifespan=lifespan,
)


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------


@app.get("/health", tags=["internal"])
async def health() -> dict:
    return {"status": "ok", "service": "mcp-crm"}


# ---------------------------------------------------------------------------
# Tool discovery
# ---------------------------------------------------------------------------


@app.get("/tools", tags=["internal"])
async def list_tools() -> list[dict[str, Any]]:
    """Returns the list of available tools with their input schemas."""
    return TOOL_SCHEMAS


# ---------------------------------------------------------------------------
# Main MCP dispatch endpoint
# ---------------------------------------------------------------------------


@app.post("/mcp/call", tags=["mcp"])
async def mcp_call(request: Request) -> JSONResponse:
    """
    Dispatches a tool call from the Rust orchestrator.

    Expected request body:
      {
        "tool": "<tool_name>",
        "params": { "tenant_id": "...", ... },
        "tenant_id": "..."
      }

    Response:
      { "result": {...}, "error": null }    — success
      { "result": null, "error": "CODE: message" }  — error
    """
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(
            content=error_response(
                "INVALID_REQUEST", "Request body must be valid JSON"
            ),
            status_code=200,
        )

    tool_name: str | None = body.get("tool")
    params: dict = body.get("params") or {}

    if not tool_name:
        return JSONResponse(
            content=error_response("INVALID_REQUEST", "'tool' field is required"),
            status_code=200,
        )

    handler = TOOL_REGISTRY.get(tool_name)
    if handler is None:
        known = ", ".join(sorted(TOOL_REGISTRY.keys()))
        return JSONResponse(
            content=error_response(
                "UNKNOWN_TOOL",
                f"Unknown tool '{tool_name}'. Available: {known}",
            ),
            status_code=200,
        )

    try:
        # Tools are decorated with @tool — CrmMcpError is caught internally
        # and returned as {"result": null, "error": "CODE: message"}.
        # This outer try/except handles truly unexpected exceptions only.
        result = await handler(
            params,
            request.app.state.http_client,
            request.app.state.settings,
        )
        return JSONResponse(content=result, status_code=200)

    except Exception as exc:
        logger.exception("Unexpected error in tool '%s'", tool_name)
        return JSONResponse(
            content=error_response("INTERNAL_ERROR", str(exc)),
            status_code=200,
        )
