"""MCP tools for executing pre-approved queries."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from mcp_tools_sql.query_helpers import build_query_body, build_query_sig_params
from mcp_tools_sql.tool_builder import build_tool_fn

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP

    from mcp_tools_sql.backends.registry import BackendRegistry
    from mcp_tools_sql.config.models import QueryConfig, ResolvedTargets


class QueryTools:
    """Registers configured query tools on an MCP server."""

    _NAME_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")
    _TRUNCATION_HINT = "Refine your query parameters or increase max_rows."

    def __init__(
        self,
        registry: BackendRegistry,
        targets: ResolvedTargets,
        queries: dict[str, QueryConfig],
    ) -> None:
        self._registry = registry
        self._targets = targets
        self._queries = queries

    def register(self, mcp: FastMCP) -> None:
        """Register one MCP tool per configured query as ``query_<name>``.

        Each tool binds the backend for its pinned ``(connection, database)``
        target, resolved once from the registry at registration time.

        Raises:
            ValueError: If a configured query name does not match the allowed
                identifier pattern (``_NAME_RE``), or if a query pins a
                connection/database that is not configured.
        """
        for name, config in self._queries.items():
            if not self._NAME_RE.match(name):
                raise ValueError(
                    f"Invalid query name {name!r}: must match "
                    f"{self._NAME_RE.pattern}"
                )
            target = self._targets.resolve_pinned(
                config.connection or None, config.database or None
            )
            backend = self._registry.backend_for(target)
            sig_params = build_query_sig_params(config)
            body = build_query_body(
                name,
                config,
                backend,
                target.backend_name,
                self._TRUNCATION_HINT,
            )
            fn = build_tool_fn(name, sig_params, body, config.description)
            mcp.add_tool(
                fn,
                name=f"query_{name}",
                description=config.description,
            )
