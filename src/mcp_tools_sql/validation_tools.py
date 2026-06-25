"""MCP tools for SQL validation via the database's EXPLAIN mechanism."""

from __future__ import annotations

import sqlite3
from typing import TYPE_CHECKING, Annotated, Any

from pydantic import Field

from mcp_tools_sql.tool_logging import log_tool_call
from mcp_tools_sql.utils.sql_placeholders import (
    basic_preflight,
    first_statement_kind,
    substitute_named_with_literals,
    to_dialect,
)

try:
    import pyodbc  # pylint: disable=import-error

    _PYODBC_ERROR: tuple[type[Exception], ...] = (pyodbc.Error,)
except ImportError:
    _PYODBC_ERROR = ()

_INVALID_SQL_EXC: tuple[type[BaseException], ...] = (sqlite3.Error, *_PYODBC_ERROR)

_SESSION_KEYWORDS = frozenset({"USE", "SET", "DECLARE"})

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP

    from mcp_tools_sql.backends.base import DatabaseBackend


_DESCRIPTION = (
    "Validate a SQL string via the database's EXPLAIN mechanism. "
    "Returns 'Valid.' or a labelled error verdict. "
    "Setting return_plan=True appends the execution plan on success. "
    "validate_sql does NOT execute the statement — safe for SELECT, "
    "UPDATE, INSERT, DELETE, and DDL (CREATE/DROP/ALTER)."
)


def _preflight(sql: str, params: dict[str, Any] | None, dialect: str) -> str | None:
    """Run pre-flight checks on ``sql`` and its bound ``params``.

    Delegates the shared checks (empty / fail-closed parse / multiple
    statements / missing parameters) to :func:`basic_preflight`, then layers
    the ``validate_sql``-specific session-keyword rejection on top.

    Args:
        sql: The SQL text to validate.
        params: Bound values for ``:name`` placeholders, or ``None``.
        dialect: The sqlglot dialect to parse under.

    Returns:
        Error verdict string when a pre-flight check fails, or ``None``
        when all checks pass.
    """
    verdict = basic_preflight(sql, params, dialect)
    if verdict is not None:
        return verdict
    keyword = first_statement_kind(sql, dialect)
    if keyword in _SESSION_KEYWORDS:
        return f"Invalid SQL. ValidationError: {keyword} statements not supported"
    return None


def _explain(
    backend: DatabaseBackend,
    backend_name: str,
    sql: str,
    params: dict[str, Any] | None,
) -> str:
    """Return the execution plan, dispatching on backend type."""
    if backend_name == "sqlite":
        return backend.explain(sql, params)
    explain_sql = substitute_named_with_literals(sql, params or {})
    with backend.get_isolated_connection() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute("SET SHOWPLAN_TEXT ON")
            try:
                cursor.execute(explain_sql)
                rows = cursor.fetchall()
            finally:
                cursor.execute("SET SHOWPLAN_TEXT OFF")
            return "\n".join(r[0] for r in rows if r and r[0])
        finally:
            cursor.close()


class ValidationTools:
    """Registers the ``validate_sql`` tool on an MCP server."""

    def __init__(self, backend: DatabaseBackend, backend_name: str) -> None:
        self._backend = backend
        self._backend_name = backend_name

    def register(self, mcp: FastMCP) -> None:
        """Register the ``validate_sql`` tool on ``mcp``."""
        backend = self._backend
        backend_name = self._backend_name

        async def validate_sql(
            sql: Annotated[str, Field(description="The SQL to validate.")],
            params: Annotated[
                dict[str, Any] | None,
                Field(description="Bound values for :name placeholders."),
            ] = None,
            return_plan: Annotated[
                bool,
                Field(description="Append the execution plan on success."),
            ] = False,
        ) -> str:
            async with log_tool_call("validate_sql", params or {}, sql=sql) as rec:
                rec.record(rows=0, cols=0)
                verdict = _preflight(sql, params, to_dialect(backend_name))
                if verdict is not None:
                    return verdict
                try:
                    plan = _explain(backend, backend_name, sql, params)
                except _INVALID_SQL_EXC as exc:
                    return f"Invalid SQL. {type(exc).__name__}: {exc}"
                except (KeyError, TypeError, ValueError) as exc:
                    return f"Invalid parameters. {type(exc).__name__}: {exc}"
                except RuntimeError as exc:
                    return f"Database connection error. {type(exc).__name__}: {exc}"
                except Exception as exc:  # noqa: BLE001
                    return f"Unexpected error. {type(exc).__name__}: {exc}"
                if return_plan:
                    return f"Valid.\nExecution plan:\n{plan}"
                return "Valid."

        mcp.add_tool(validate_sql, name="validate_sql", description=_DESCRIPTION)
