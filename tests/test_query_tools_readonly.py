"""Tests for the read-only registration gate on configured queries."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import pytest
from mcp.server.fastmcp import FastMCP
from mcp.shared.memory import create_connected_server_and_client_session

from mcp_tools_sql.config.models import QueryConfig
from mcp_tools_sql.query_helpers import read_only_rejection
from mcp_tools_sql.query_tools import QueryTools
from mcp_tools_sql.utils.sql_placeholders import ParseError, read_only_violation
from tests.target_helpers import single_target, sqlite_backend

if TYPE_CHECKING:
    from pathlib import Path


async def _registered_names(mcp: FastMCP) -> set[str]:
    """Return the names of every tool registered on ``mcp``.

    Returns:
        The set of registered tool names.
    """
    async with create_connected_server_and_client_session(
        mcp, raise_exceptions=True
    ) as client:
        result = await client.list_tools()
        return {t.name for t in result.tools}


@pytest.mark.asyncio
async def test_write_query_is_skipped_with_warning(
    sqlite_db: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """A DELETE query registers no tool and logs a warning naming the query."""
    backend = sqlite_backend(sqlite_db)
    queries = {"purge": QueryConfig(description="", sql="DELETE FROM orders")}
    mcp = FastMCP("test-gate-delete")

    with caplog.at_level(logging.WARNING, logger="mcp_tools_sql.query_tools"):
        QueryTools(*single_target(backend), queries).register(mcp)

    assert await _registered_names(mcp) == set()
    assert any("purge" in rec.getMessage() for rec in caplog.records)


@pytest.mark.asyncio
async def test_sibling_queries_still_register(sqlite_db: Path) -> None:
    """A violating query is dropped; its valid siblings register normally."""
    backend = sqlite_backend(sqlite_db)
    queries = {
        "purge": QueryConfig(description="", sql="DELETE FROM orders"),
        "listing": QueryConfig(description="", sql="SELECT id FROM orders"),
    }
    mcp = FastMCP("test-gate-siblings")

    QueryTools(*single_target(backend), queries).register(mcp)

    assert await _registered_names(mcp) == {"query_listing"}


@pytest.mark.asyncio
async def test_exec_procedure_is_rejected(sqlite_db: Path) -> None:
    """EXEC of a stored procedure is rejected -- the gate cannot see its body."""
    backend = sqlite_backend(sqlite_db)
    queries = {"proc": QueryConfig(description="", sql="EXEC dbo.usp_x :p")}
    mcp = FastMCP("test-gate-exec")

    QueryTools(*single_target(backend, backend_name="mssql"), queries).register(mcp)

    assert await _registered_names(mcp) == set()


@pytest.mark.asyncio
async def test_separator_less_batch_is_rejected(sqlite_db: Path) -> None:
    """The absorption guard is composed into the gate, not just into utils."""
    backend = sqlite_backend(sqlite_db)
    queries = {"sneaky": QueryConfig(description="", sql="SELECT 1\nDELETE FROM t")}
    mcp = FastMCP("test-gate-batch")

    QueryTools(*single_target(backend, backend_name="mssql"), queries).register(mcp)

    assert await _registered_names(mcp) == set()


@pytest.mark.asyncio
async def test_unparseable_sql_is_rejected_not_raised(
    sqlite_db: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Unparseable SQL is a warned-and-skipped rejection, not an escaping error."""
    backend = sqlite_backend(sqlite_db)
    queries = {"broken": QueryConfig(description="", sql="SELECT FROM WHERE )(")}
    mcp = FastMCP("test-gate-unparseable")

    with caplog.at_level(logging.WARNING, logger="mcp_tools_sql.query_tools"):
        QueryTools(*single_target(backend), queries).register(mcp)

    assert await _registered_names(mcp) == set()
    assert any("broken" in rec.getMessage() for rec in caplog.records)


@pytest.mark.asyncio
async def test_valid_query_registers_and_bad_name_still_raises(
    sqlite_db: Path,
) -> None:
    """The two failure modes stay separate: bad name raises, bad SQL is skipped."""
    backend = sqlite_backend(sqlite_db)
    mcp = FastMCP("test-gate-valid")
    QueryTools(
        *single_target(backend),
        {"listing": QueryConfig(description="", sql="SELECT id FROM orders")},
    ).register(mcp)
    assert await _registered_names(mcp) == {"query_listing"}

    with pytest.raises(ValueError, match="123-bad"):
        QueryTools(
            *single_target(backend),
            {"123-bad": QueryConfig(description="", sql="DELETE FROM orders")},
        ).register(FastMCP("test-gate-bad-name"))


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "sql",
    [
        "SELECT * FROM OPENQUERY(srv, 'DELETE FROM t')",
        "SELECT * FROM OPENROWSET('SQLNCLI', 'srv', 'DELETE FROM t')",
    ],
)
@pytest.mark.parametrize("backend_name", ["sqlite", "mssql"])
async def test_passthrough_source_is_rejected(
    sqlite_db: Path, sql: str, backend_name: str
) -> None:
    """A linked-server pass-through registers no tool -- the far end is opaque."""
    backend = sqlite_backend(sqlite_db)
    queries = {"remote": QueryConfig(description="", sql=sql)}
    mcp = FastMCP("test-gate-passthrough")

    QueryTools(*single_target(backend, backend_name=backend_name), queries).register(
        mcp
    )

    assert await _registered_names(mcp) == set()


def test_read_only_rejection_accepts_clean_select() -> None:
    """A plain SELECT yields no rejection."""
    assert read_only_rejection("SELECT id FROM orders", "sqlite") is None


def test_read_only_rejection_reports_unparseable_sql() -> None:
    """Unparseable SQL yields a rejection message naming the dialect."""
    message = read_only_rejection("SELECT FROM WHERE )(", "tsql")
    assert message is not None
    assert "tsql" in message


def test_parse_error_message_is_one_line_without_escapes() -> None:
    """sqlglot's multi-line, ANSI-underlined ParseError text is flattened.

    A rejection message is rendered as a single ``verify`` row and logged as a
    single warning line, so a newline or a terminal escape would corrupt both.
    """
    sql = "SELECT * FROMX badtable"
    with pytest.raises(ParseError) as excinfo:
        read_only_violation(sql, "sqlite")
    raw = str(excinfo.value)
    assert "\n" in raw  # the premise: sqlglot's own text is multi-line
    assert "\x1b[" in raw  # ... and carries ANSI escapes

    message = read_only_rejection(sql, "sqlite")

    assert message is not None
    assert "\n" not in message
    assert "\x1b" not in message
    assert "badtable" in message
