"""Tool-level statement-timeout handling (count, validate, summarize, update)."""

from __future__ import annotations

from typing import Any

import pytest
from mcp.server.fastmcp import FastMCP
from mcp.shared.memory import create_connected_server_and_client_session

from mcp_tools_sql.backends.base import DatabaseBackend, QueryTimeoutError
from mcp_tools_sql.config.models import (
    UpdateConfig,
    UpdateFieldConfig,
    UpdateKeyConfig,
)
from mcp_tools_sql.count_tools import CountTools
from mcp_tools_sql.server import FastMCPSink
from mcp_tools_sql.summarize.tools import SummarizeTools
from mcp_tools_sql.update_tools import UpdateTools
from mcp_tools_sql.validation_tools import ValidationTools
from tests.target_helpers import single_target

_NARROWER = "Query aborted after 30 s (statement timeout). Use a narrower query."
_BARE = "Query aborted after 30 s (statement timeout)."


class _TimeoutBackend(DatabaseBackend):
    """Backend whose every statement times out after 30 s."""

    def connect(self) -> None:
        """No-op."""

    def close(self) -> None:
        """No-op."""

    def execute_query(
        self, sql: str, params: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        raise QueryTimeoutError(30)

    def execute_readonly_query(
        self, sql: str, params: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        raise QueryTimeoutError(30)

    def execute_readonly_query_with_columns(
        self, sql: str, params: dict[str, Any] | None = None
    ) -> tuple[list[str], list[tuple[Any, ...]]]:
        raise QueryTimeoutError(30)

    def execute_update(self, sql: str, params: dict[str, Any] | None = None) -> int:
        raise QueryTimeoutError(30)

    def explain(
        self, sql: str, params: dict[str, Any] | None = None, *, isolated: bool = False
    ) -> str:
        raise QueryTimeoutError(30)


async def _call(mcp: FastMCP, tool: str, args: dict[str, Any]) -> str:
    """Call ``tool`` via an in-memory MCP client and return the text content."""
    async with create_connected_server_and_client_session(
        mcp, raise_exceptions=True
    ) as client:
        result = await client.call_tool(tool, args)
    return result.content[0].text  # type: ignore[union-attr]


@pytest.mark.asyncio
async def test_count_records_timeout() -> None:
    """``count_records`` reports the timeout with the narrower-query hint."""
    mcp = FastMCP("test-count-timeout")
    CountTools(*single_target(_TimeoutBackend())).register(FastMCPSink(mcp))
    text = await _call(mcp, "count_records", {"sql": "SELECT 1 AS x"})
    assert text == _NARROWER
    assert "Invalid SQL" not in text


@pytest.mark.asyncio
async def test_validate_sql_timeout() -> None:
    """``validate_sql`` reports the timeout with the narrower-query hint."""
    mcp = FastMCP("test-validate-timeout")
    ValidationTools(*single_target(_TimeoutBackend())).register(FastMCPSink(mcp))
    text = await _call(mcp, "validate_sql", {"sql": "SELECT 1"})
    assert text == _NARROWER
    assert "Invalid SQL" not in text


@pytest.mark.asyncio
async def test_summarize_columns_timeout() -> None:
    """``summarize_columns`` on a table source reports the timeout + hint."""
    mcp = FastMCP("test-summarize-timeout")
    SummarizeTools(*single_target(_TimeoutBackend())).register(FastMCPSink(mcp))
    text = await _call(
        mcp, "summarize_columns", {"schema": "main", "table": "customers"}
    )
    assert text == _NARROWER
    assert "Invalid SQL" not in text


@pytest.mark.asyncio
async def test_update_tool_timeout() -> None:
    """An update tool returns the bare timeout message, no hint."""
    updates = {
        "set_name": UpdateConfig(
            description="Set customer name",
            table="customers",
            key=UpdateKeyConfig(field="id", type="int"),
            fields=[UpdateFieldConfig(field="name", type="str")],
        )
    }
    mcp = FastMCP("test-update-timeout")
    UpdateTools(*single_target(_TimeoutBackend()), updates).register(FastMCPSink(mcp))
    text = await _call(mcp, "update_set_name", {"id": 1, "name": "x"})
    assert text == _BARE
