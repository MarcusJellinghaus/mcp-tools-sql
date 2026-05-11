"""MCP tools for executing pre-approved queries."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from mcp_tools_sql.tool_builder import build_tool_fn

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP

    from mcp_tools_sql.backends.base import DatabaseBackend
    from mcp_tools_sql.config.models import QueryConfig


class QueryTools:
    """Registers configured query tools on an MCP server."""

    _NAME_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")
    _TRUNCATION_HINT = "Refine your query parameters or increase max_rows."

    def __init__(
        self,
        backend: DatabaseBackend,
        queries: dict[str, QueryConfig],
        backend_name: str,
    ) -> None:
        self._backend = backend
        self._queries = queries
        self._backend_name = backend_name

    def register(self, mcp: FastMCP) -> None:
        """Register one MCP tool per configured query as ``query_<name>``."""
        for name, config in self._queries.items():
            if not self._NAME_RE.match(name):
                raise ValueError(
                    f"Invalid query name {name!r}: must match "
                    f"{self._NAME_RE.pattern}"
                )
            fn = build_tool_fn(
                name,
                config,
                self._backend,
                self._backend_name,
                truncation_hint=self._TRUNCATION_HINT,
            )
            mcp.add_tool(
                fn,
                name=f"query_{name}",
                description=config.description,
            )
