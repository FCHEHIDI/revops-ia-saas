"""Contract tests: orchestrator tool definitions ↔ mcp-crm handlers.

Validates that the parameter names declared in TOOL_SCHEMAS (what the
orchestrator receives via ``GET /tools``) match the contract expected by
``orchestrator/src/context/builder.rs`` (``default_tool_definitions``).

REGRESSION TEST for commit bc46965:
  ``update_deal_stage`` param ``stage`` → ``new_stage`` mismatch caused
  every deal-move tool call to fail silently with VALIDATION_ERROR.
  Both TOOL_SCHEMAS and the Rust orchestrator must stay in sync.

How to update the contract:
  1. Edit ``CONTRACT`` in this file.
  2. Update ``mcp/mcp-crm/src/schemas.py``   (TOOL_SCHEMAS).
  3. Update ``mcp/mcp-crm/src/tools/*.py``   (handler validation calls).
  4. Update ``orchestrator/src/context/builder.rs`` (default_tool_definitions).

Run:
  cd mcp/mcp-crm && pytest tests/test_contracts.py -v
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from schemas import TOOL_SCHEMAS  # type: ignore[import-not-found]
from tools import TOOL_REGISTRY  # type: ignore[import-not-found]


# ── Canonical contract ────────────────────────────────────────────────────────
# Required params expected by each tool (tenant_id excluded — it is always
# injected at the server level and is not an LLM-visible parameter).
#
# These must match BOTH:
#   - TOOL_SCHEMAS  (mcp-crm/src/schemas.py)        ← Python side
#   - default_tool_definitions  (orchestrator/src/context/builder.rs) ← Rust side
# ─────────────────────────────────────────────────────────────────────────────
CONTRACT: dict[str, frozenset[str]] = {
    # Contacts
    "get_contact":    frozenset({"contact_id"}),
    "search_contacts": frozenset(),
    "create_contact": frozenset({"first_name", "last_name", "email", "created_by"}),
    "update_contact": frozenset({"contact_id"}),
    # Accounts
    "get_account":    frozenset({"account_id"}),
    "search_accounts": frozenset(),
    "create_account": frozenset({"name", "created_by"}),
    "update_account": frozenset({"account_id"}),
    # Deals
    "get_deal":          frozenset({"deal_id"}),
    "list_deals":        frozenset(),
    "create_deal":       frozenset({"title", "account_id", "stage", "owner_id", "created_by"}),
    "update_deal_stage": frozenset({"deal_id", "new_stage"}),  # ← was 'stage' before bc46965
}

_SCHEMA_MAP: dict[str, dict] = {s["name"]: s for s in TOOL_SCHEMAS}


# ── TOOL_REGISTRY tests ───────────────────────────────────────────────────────

class TestToolRegistry:
    """Validate TOOL_REGISTRY is fully aligned with the contract."""

    def test_all_contract_tools_registered(self) -> None:
        """Every contract tool must have a callable handler."""
        missing = [name for name in CONTRACT if name not in TOOL_REGISTRY]
        assert not missing, (
            f"Tools in contract but missing from TOOL_REGISTRY: {missing}\n"
            "Add them to mcp/mcp-crm/src/tools/__init__.py"
        )

    def test_no_unregistered_handlers(self) -> None:
        """Every handler in TOOL_REGISTRY must appear in the contract (no orphan tools)."""
        orphans = [name for name in TOOL_REGISTRY if name not in CONTRACT]
        assert not orphans, (
            f"Tools in TOOL_REGISTRY but missing from contract: {orphans}\n"
            "Add them to CONTRACT in this file and to orchestrator/src/context/builder.rs"
        )


# ── TOOL_SCHEMAS tests ────────────────────────────────────────────────────────

class TestToolSchemas:
    """Validate TOOL_SCHEMAS (the ``GET /tools`` response) matches the contract.

    TOOL_SCHEMAS is what the orchestrator fetches to build its system prompt
    and inform the LLM about available tools.  Required param names MUST
    match what the Rust orchestrator sends — any mismatch results in a silent
    VALIDATION_ERROR inside mcp-crm.
    """

    def test_all_contract_tools_in_schemas(self) -> None:
        """TOOL_SCHEMAS must expose every tool listed in the contract."""
        missing = [name for name in CONTRACT if name not in _SCHEMA_MAP]
        assert not missing, (
            f"Contract tools missing from TOOL_SCHEMAS: {missing}\n"
            "Add them to mcp/mcp-crm/src/schemas.py"
        )

    def test_required_params_match_contract(self) -> None:
        """Required params in TOOL_SCHEMAS must exactly match the contract.

        This is the primary regression guard for the stage/new_stage mismatch
        (bc46965).  Any divergence means the LLM will send a wrong param name
        and receive a VALIDATION_ERROR instead of a useful tool result.
        """
        failures: list[str] = []

        for tool_name, expected_required in CONTRACT.items():
            if tool_name not in _SCHEMA_MAP:
                continue  # missing tool is caught by test_all_contract_tools_in_schemas

            schema = _SCHEMA_MAP[tool_name]
            actual_required = (
                frozenset(schema["input_schema"].get("required", [])) - {"tenant_id"}
            )

            if actual_required != expected_required:
                failures.append(
                    f"  {tool_name!r}:\n"
                    f"    contract = {sorted(expected_required)}\n"
                    f"    actual   = {sorted(actual_required)}"
                )

        assert not failures, (
            "Required param mismatches detected — the orchestrator will send wrong "
            "param names, causing silent VALIDATION_ERRORs:\n"
            + "\n".join(failures)
            + "\n\nFix BOTH:\n"
            "  mcp/mcp-crm/src/schemas.py           (TOOL_SCHEMAS)\n"
            "  orchestrator/src/context/builder.rs   (default_tool_definitions)"
        )

    @pytest.mark.parametrize("tool_name", list(CONTRACT))
    def test_tool_has_tenant_id_property(self, tool_name: str) -> None:
        """Every tool schema must declare tenant_id as a property (server-level injection)."""
        if tool_name not in _SCHEMA_MAP:
            pytest.skip(f"Tool '{tool_name}' not in TOOL_SCHEMAS")

        schema = _SCHEMA_MAP[tool_name]
        props = schema["input_schema"].get("properties", {})
        assert "tenant_id" in props, (
            f"Tool '{tool_name}' missing tenant_id property in TOOL_SCHEMAS"
        )
