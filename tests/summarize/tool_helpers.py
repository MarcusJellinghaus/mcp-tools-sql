"""Shared end-to-end helpers for the ``summarize_columns`` tool tests.

Both summarize tool test modules -- the table path (``test_tools.py``) and the
``sql=`` source path (``test_tools_query_source.py``) -- drive the whole
pipeline through ``create_connected_server_and_client_session``, so the backend
factory, the client context manager, and the call wrapper live here rather than
being duplicated per module.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.shared.memory import create_connected_server_and_client_session

from mcp_tools_sql.backends.sqlite import SQLiteBackend
from mcp_tools_sql.config.models import ConnectionConfig
from mcp_tools_sql.summarize import SummarizeTools
from tests.target_helpers import single_target


def sqlite_backend(db_path: Path) -> SQLiteBackend:
    """Return a connected SQLite backend for the given database path.

    Returns:
        The connected :class:`SQLiteBackend`.
    """
    backend = SQLiteBackend(ConnectionConfig(backend="sqlite", path=str(db_path)))
    backend.connect()
    return backend


@asynccontextmanager
async def client_for(
    backend: Any, *, backend_name: str = "sqlite"
) -> AsyncIterator[Any]:
    """Yield an MCP client with ``summarize_columns`` bound to *backend*.

    Yields:
        A connected MCP client session exposing ``summarize_columns``.
    """
    mcp = FastMCP("test-summarize")
    SummarizeTools(*single_target(backend, backend_name=backend_name)).register(mcp)
    async with create_connected_server_and_client_session(
        mcp, raise_exceptions=True
    ) as client:
        yield client


async def call_summarize(
    client: Any,
    schema: str | None = None,
    table: str | None = None,
    *,
    sql: str | None = None,
    columns: list[str] | None = None,
    where: str | None = None,
    params: dict[str, Any] | None = None,
    n: int | None = None,
    connection: str | None = None,
    database: str | None = None,
) -> str:
    """Call ``summarize_columns`` via the MCP client and return the text.

    Only the arguments actually supplied are sent, so a call omitting both
    source arguments exercises the tool's own mutual-exclusivity check rather
    than a client-side schema error.

    Returns:
        The tool's single text result.
    """
    args: dict[str, Any] = {}
    for key, value in (
        ("schema", schema),
        ("table", table),
        ("sql", sql),
        ("columns", columns),
        ("where", where),
        ("params", params),
        ("n", n),
        ("connection", connection),
        ("database", database),
    ):
        if value is not None:
            args[key] = value
    result = await client.call_tool("summarize_columns", args)
    return result.content[0].text  # type: ignore[no-any-return]
