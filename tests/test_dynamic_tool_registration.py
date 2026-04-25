"""Tests for dynamic tool registration with FastMCP.

Spike: Verify that dynamically-created functions (with __signature__ set at
runtime) integrate correctly with FastMCP's add_tool() and produce the
expected JSON schemas for LLM consumption.

Three test levels:
  1. Unit — Tool.from_function() schema verification
  2. In-memory MCP client — full protocol roundtrip
  3. Live prototype — manual (see examples/prototype_server.py)
"""

import inspect
from collections.abc import Callable
from typing import Annotated, Any, Optional

import pytest
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.tools.base import Tool
from pydantic import Field

from mcp_tools_sql.utils.data_type_utility.type_mapping import (
    TYPE_MAP,
    resolve_python_type,
)

# ---------------------------------------------------------------------------
# Helper: build a function with a dynamic signature
# ---------------------------------------------------------------------------


def _make_dynamic_tool_fn(
    name: str,
    description: str,
    params: list[dict[str, object]],
) -> Callable[..., Any]:
    """Build an async function with dynamically-typed parameters.

    Each entry in *params* is a dict with keys:
      name (str), type (str), description (str, optional),
      required (bool, default True).
    """

    async def _tool_fn(**kwargs: object) -> str:
        return f"Executed {name} with {kwargs}"

    sig_params: list[inspect.Parameter] = []
    for p in params:
        python_type = resolve_python_type(str(p["type"]))
        required = bool(p.get("required", True))
        desc = str(p.get("description", ""))

        if required:
            annotation: object = (
                Annotated[python_type, Field(description=desc)] if desc else python_type
            )
            default: object = inspect.Parameter.empty
        else:
            annotation = (
                Annotated[Optional[python_type], Field(description=desc)]  # noqa: UP007
                if desc
                else Optional[python_type]  # noqa: UP007
            )
            default = None

        sig_params.append(
            inspect.Parameter(
                str(p["name"]),
                kind=inspect.Parameter.POSITIONAL_OR_KEYWORD,
                default=default,
                annotation=annotation,
            )
        )

    _tool_fn.__signature__ = inspect.Signature(sig_params)  # type: ignore[attr-defined]
    _tool_fn.__name__ = name
    _tool_fn.__doc__ = description
    return _tool_fn


# ---------------------------------------------------------------------------
# Type mapping tests
# ---------------------------------------------------------------------------


class TestTypeMapping:
    """Verify resolve_python_type maps config strings correctly."""

    def test_known_types(self) -> None:
        """All entries in TYPE_MAP resolve correctly."""
        assert resolve_python_type("str") is str
        assert resolve_python_type("int") is int
        assert resolve_python_type("float") is float
        assert resolve_python_type("bool") is bool

    def test_unknown_type_raises(self) -> None:
        """Unknown type strings raise ValueError."""
        with pytest.raises(ValueError, match="Unknown type"):
            resolve_python_type("banana")

    def test_type_map_completeness(self) -> None:
        """TYPE_MAP contains the expected entries."""
        assert set(TYPE_MAP) == {"str", "int", "float", "bool", "datetime"}


# ---------------------------------------------------------------------------
# Level 1: Unit tests — Tool.from_function() schema verification
# ---------------------------------------------------------------------------


class TestLevel1SchemaGeneration:  # pylint: disable=no-member
    """Verify JSON schema generation from dynamically-typed functions."""

    def test_query_tool_single_required_param(self) -> None:
        """Query tool with a single required string filter."""
        fn = _make_dynamic_tool_fn(
            name="query_customers_by_country",
            description="Find customers in a specific country.",
            params=[
                {
                    "name": "country",
                    "type": "str",
                    "description": "Country code to filter by",
                },
            ],
        )
        tool = Tool.from_function(fn)

        assert tool.name == "query_customers_by_country"
        assert tool.description == "Find customers in a specific country."

        props = tool.parameters["properties"]
        assert "country" in props
        assert props["country"]["type"] == "string"
        assert props["country"].get("description") == "Country code to filter by"
        assert "country" in tool.parameters.get("required", [])

    def test_query_tool_multiple_types(self) -> None:
        """Query tool with str, int, and optional float params."""
        fn = _make_dynamic_tool_fn(
            name="query_orders",
            description="Search orders by multiple criteria.",
            params=[
                {
                    "name": "status",
                    "type": "str",
                    "description": "Order status filter",
                },
                {
                    "name": "customer_id",
                    "type": "int",
                    "description": "Customer ID",
                },
                {
                    "name": "min_total",
                    "type": "float",
                    "description": "Minimum order total",
                    "required": False,
                },
            ],
        )
        tool = Tool.from_function(fn)

        props = tool.parameters["properties"]
        assert props["status"]["type"] == "string"
        assert props["customer_id"]["type"] == "integer"
        # Optional float is present
        assert "min_total" in props

        required = tool.parameters.get("required", [])
        assert "status" in required
        assert "customer_id" in required
        assert "min_total" not in required

    def test_update_tool_key_and_fields(self) -> None:
        """Update tool with key param and settable fields."""
        fn = _make_dynamic_tool_fn(
            name="update_order_status",
            description="Update the status of an order.",
            params=[
                {
                    "name": "order_id",
                    "type": "int",
                    "description": "Order ID (primary key)",
                },
                {
                    "name": "status",
                    "type": "str",
                    "description": "New status value",
                },
                {
                    "name": "notes",
                    "type": "str",
                    "description": "Optional notes",
                    "required": False,
                },
            ],
        )
        tool = Tool.from_function(fn)

        props = tool.parameters["properties"]
        assert props["order_id"]["type"] == "integer"
        assert props["status"]["type"] == "string"

        required = tool.parameters.get("required", [])
        assert "order_id" in required
        assert "status" in required
        assert "notes" not in required

    def test_all_optional_params(self) -> None:
        """Edge case: tool where all params are optional."""
        fn = _make_dynamic_tool_fn(
            name="query_all_customers",
            description="List customers with optional filters.",
            params=[
                {
                    "name": "country",
                    "type": "str",
                    "description": "Country filter",
                    "required": False,
                },
                {
                    "name": "limit",
                    "type": "int",
                    "description": "Max results",
                    "required": False,
                },
            ],
        )
        tool = Tool.from_function(fn)

        props = tool.parameters["properties"]
        assert "country" in props
        assert "limit" in props
        # No required params
        required = tool.parameters.get("required", [])
        assert not required

    def test_no_params_tool(self) -> None:
        """Edge case: tool with no parameters."""
        fn = _make_dynamic_tool_fn(
            name="query_system_info",
            description="Return system information.",
            params=[],
        )
        tool = Tool.from_function(fn)

        assert tool.name == "query_system_info"
        assert tool.description == "Return system information."
        # No properties or empty properties
        props = tool.parameters.get("properties", {})
        assert not props


# ---------------------------------------------------------------------------
# Level 2: In-memory MCP client — full protocol roundtrip
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestLevel2McpProtocol:
    """Verify tools are discoverable and callable via MCP protocol."""

    async def test_dynamic_tools_discoverable(self) -> None:
        """All dynamic tools appear in list_tools() response."""
        from mcp.shared.memory import create_connected_server_and_client_session

        mcp = FastMCP("test-dynamic-tools")

        fn1 = _make_dynamic_tool_fn(
            name="query_customers_by_country",
            description="Find customers by country.",
            params=[
                {"name": "country", "type": "str", "description": "Country code"},
            ],
        )
        fn2 = _make_dynamic_tool_fn(
            name="query_orders",
            description="Search orders.",
            params=[
                {"name": "status", "type": "str", "description": "Status filter"},
                {
                    "name": "min_total",
                    "type": "float",
                    "description": "Min total",
                    "required": False,
                },
            ],
        )
        fn3 = _make_dynamic_tool_fn(
            name="update_order_status",
            description="Update order status.",
            params=[
                {"name": "order_id", "type": "int", "description": "Order ID"},
                {"name": "status", "type": "str", "description": "New status"},
            ],
        )

        mcp.add_tool(fn1)
        mcp.add_tool(fn2)
        mcp.add_tool(fn3)

        async with create_connected_server_and_client_session(
            mcp, raise_exceptions=True
        ) as client:
            result = await client.list_tools()
            tool_names = {t.name for t in result.tools}

            assert "query_customers_by_country" in tool_names
            assert "query_orders" in tool_names
            assert "update_order_status" in tool_names

    async def test_schema_correct_via_protocol(self) -> None:
        """Tool schema matches expectations when retrieved via MCP."""
        from mcp.shared.memory import create_connected_server_and_client_session

        mcp = FastMCP("test-schema")

        fn = _make_dynamic_tool_fn(
            name="query_customers_by_country",
            description="Find customers by country.",
            params=[
                {
                    "name": "country",
                    "type": "str",
                    "description": "Country code to filter by",
                },
            ],
        )
        mcp.add_tool(fn)

        async with create_connected_server_and_client_session(
            mcp, raise_exceptions=True
        ) as client:
            result = await client.list_tools()
            tool = result.tools[0]

            assert tool.name == "query_customers_by_country"
            assert tool.description == "Find customers by country."

            schema = tool.inputSchema
            props = schema["properties"]
            assert "country" in props
            assert props["country"]["type"] == "string"

    async def test_tool_callable_returns_result(self) -> None:
        """Dynamic tool can be called and returns a result."""
        from mcp.shared.memory import create_connected_server_and_client_session

        mcp = FastMCP("test-callable")

        fn = _make_dynamic_tool_fn(
            name="query_customers_by_country",
            description="Find customers by country.",
            params=[
                {"name": "country", "type": "str", "description": "Country code"},
            ],
        )
        mcp.add_tool(fn)

        async with create_connected_server_and_client_session(
            mcp, raise_exceptions=True
        ) as client:
            call_result = await client.call_tool(
                "query_customers_by_country", {"country": "DE"}
            )
            assert not call_result.isError
            text = call_result.content[0].text  # type: ignore[union-attr]
            assert "country" in text
            assert "DE" in text

    async def test_optional_param_omittable(self) -> None:
        """Optional parameters can be omitted from the call."""
        from mcp.shared.memory import create_connected_server_and_client_session

        mcp = FastMCP("test-optional")

        fn = _make_dynamic_tool_fn(
            name="query_orders",
            description="Search orders.",
            params=[
                {"name": "status", "type": "str", "description": "Status"},
                {
                    "name": "min_total",
                    "type": "float",
                    "description": "Min total",
                    "required": False,
                },
            ],
        )
        mcp.add_tool(fn)

        async with create_connected_server_and_client_session(
            mcp, raise_exceptions=True
        ) as client:
            # Call without optional param
            call_result = await client.call_tool("query_orders", {"status": "pending"})
            assert not call_result.isError

    async def test_no_params_tool_callable(self) -> None:
        """Tool with no parameters can be called."""
        from mcp.shared.memory import create_connected_server_and_client_session

        mcp = FastMCP("test-no-params")

        fn = _make_dynamic_tool_fn(
            name="query_system_info",
            description="Return system info.",
            params=[],
        )
        mcp.add_tool(fn)

        async with create_connected_server_and_client_session(
            mcp, raise_exceptions=True
        ) as client:
            call_result = await client.call_tool("query_system_info", {})
            assert not call_result.isError
