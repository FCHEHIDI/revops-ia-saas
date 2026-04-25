from __future__ import annotations

import functools
import logging
import uuid

import httpx

logger = logging.getLogger(__name__)


class CrmMcpError(Exception):
    """Structured error raised by tools and caught by the server dispatcher."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message

    def __repr__(self) -> str:
        return f"CrmMcpError(code={self.code!r}, message={self.message!r})"


# ---------------------------------------------------------------------------
# Validation helpers — called as first line in every tool
# ---------------------------------------------------------------------------


def validate_tenant_id(tenant_id: str | None) -> str:
    """
    Validates that tenant_id is present and a valid UUID4.
    Returns the canonical lowercase UUID string on success.
    Raises CrmMcpError(INVALID_TENANT) otherwise.
    """
    if not tenant_id or not str(tenant_id).strip():
        raise CrmMcpError("INVALID_TENANT", "tenant_id is required")
    try:
        val = uuid.UUID(str(tenant_id))
    except ValueError:
        raise CrmMcpError(
            "INVALID_TENANT",
            f"tenant_id '{tenant_id}' is not a valid UUID",
        )
    return str(val)


def validate_uuid_field(params: dict, field: str) -> str:
    """
    Validates that params[field] is present and a valid UUID.
    Returns the canonical lowercase UUID string on success.
    Raises CrmMcpError(VALIDATION_ERROR) otherwise.
    """
    value = params.get(field)
    if not value or not str(value).strip():
        raise CrmMcpError("VALIDATION_ERROR", f"'{field}' is required")
    try:
        val = uuid.UUID(str(value))
    except ValueError:
        raise CrmMcpError(
            "VALIDATION_ERROR",
            f"'{field}' value '{value}' is not a valid UUID",
        )
    return str(val)


def validate_required_str(params: dict, field: str) -> str:
    """Validates that params[field] is a non-empty string."""
    value = params.get(field)
    if not value or not str(value).strip():
        raise CrmMcpError(
            "VALIDATION_ERROR", f"'{field}' is required and must be a non-empty string"
        )
    return str(value).strip()


def validate_enum_field(
    params: dict, field: str, allowed: set[str], required: bool = False
) -> str | None:
    """Validates that params[field] belongs to the allowed enum set."""
    value = params.get(field)
    if value is None:
        if required:
            raise CrmMcpError("VALIDATION_ERROR", f"'{field}' is required")
        return None
    if str(value) not in allowed:
        raise CrmMcpError(
            "VALIDATION_ERROR",
            f"'{field}' must be one of {sorted(allowed)}, got '{value}'",
        )
    return str(value)


def validate_positive_int(
    params: dict, field: str, default: int, min_val: int = 1, max_val: int | None = None
) -> int:
    """Validates an optional integer field with min/max bounds."""
    value = params.get(field, default)
    try:
        int_val = int(value)
    except (TypeError, ValueError):
        raise CrmMcpError(
            "VALIDATION_ERROR", f"'{field}' must be an integer, got '{value}'"
        )
    if int_val < min_val:
        raise CrmMcpError(
            "VALIDATION_ERROR", f"'{field}' must be >= {min_val}, got {int_val}"
        )
    if max_val is not None and int_val > max_val:
        raise CrmMcpError(
            "VALIDATION_ERROR", f"'{field}' must be <= {max_val}, got {int_val}"
        )
    return int_val


# ---------------------------------------------------------------------------
# Response helpers
# ---------------------------------------------------------------------------


def error_response(code: str, message: str) -> dict:
    """Builds the McpCallResponse error payload expected by the orchestrator."""
    return {"result": None, "error": f"{code}: {message}"}


def success_response(data: dict) -> dict:
    """Builds the McpCallResponse success payload."""
    return {"result": data, "error": None}


# ---------------------------------------------------------------------------
# Tool decorator — wraps async tool functions to catch CrmMcpError
# ---------------------------------------------------------------------------


def tool(fn):
    """
    Decorator for MCP tool functions.

    Catches CrmMcpError raised anywhere in the tool (validation helpers,
    http_client mapping) and converts to an error_response dict.
    Unexpected exceptions are re-raised so server.py can log them.

    This allows tests to call tools directly and receive structured dicts
    without needing an intermediate try/except.
    """

    @functools.wraps(fn)
    async def wrapper(*args, **kwargs):
        try:
            return await fn(*args, **kwargs)
        except CrmMcpError as exc:
            logger.warning("Tool %s: %s: %s", fn.__name__, exc.code, exc.message)
            return error_response(exc.code, exc.message)
        except httpx.RequestError as exc:
            logger.warning("Tool %s: httpx.RequestError: %s", fn.__name__, exc)
            return error_response(
                "BACKEND_UNAVAILABLE", f"Backend request failed: {exc}"
            )

    return wrapper
