"""MCP tool for counting the rows a read-only SELECT would return.

``count_records`` is a read-only sibling of ``validate_sql``: unlike
``validate_sql`` (which only EXPLAINs and never executes), this tool *runs* a
``SELECT COUNT(*)`` wrapper around the user's query and returns the row count as
a plain number string.

Security model (see ``pr_info/steps/summary.md``):

- **Layer 1 (primary) — sqlglot AST.** :func:`read_only_violation` positively
  proves the statement is read-only before anything executes.
- **Layer 2 (backstop) — DB-enforced read-only.** The wrapped count runs through
  :meth:`DatabaseBackend.execute_readonly_query` (SQLite: a fresh
  ``PRAGMA query_only=ON`` connection; MSSQL: a documented read-only login).
"""

from __future__ import annotations

import inspect
import sqlite3
from typing import TYPE_CHECKING, Annotated, Any, Optional

import sqlglot
from pydantic import Field
from sqlglot import exp

from mcp_tools_sql.backends.base import to_dialect
from mcp_tools_sql.query_helpers import build_target_params
from mcp_tools_sql.tool_builder import build_tool_fn
from mcp_tools_sql.tool_logging import log_tool_call
from mcp_tools_sql.utils.sql_placeholders import (
    basic_preflight,
    build_count_query,
    read_only_violation,
)

try:
    import pyodbc  # pylint: disable=import-error

    _PYODBC_ERROR: tuple[type[Exception], ...] = (pyodbc.Error,)
except ImportError:
    _PYODBC_ERROR = ()

_INVALID_SQL_EXC: tuple[type[BaseException], ...] = (sqlite3.Error, *_PYODBC_ERROR)

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP

    from mcp_tools_sql.backends.registry import BackendRegistry
    from mcp_tools_sql.config.models import ResolvedTargets


_DESCRIPTION = (
    "Count the rows a read-only SELECT would return. Executes a "
    "SELECT COUNT(*) wrapper around your query (read-only); rejects any "
    "statement that is not read-only (no INSERT/UPDATE/DELETE/DDL/SELECT...INTO). "
    "Returns the count as a plain number. Supports :name placeholders via "
    "params. Unlike validate_sql, this tool executes the wrapped count query."
)

_LEADING_CTE_REJECTION = (
    "CTE (WITH) queries can't be counted on SQL Server — "
    "the count wrapper doesn't support them."
)


def _has_leading_cte(sql: str, dialect: str) -> bool:
    """Return ``True`` when ``sql``'s root statement carries a CTE (``WITH``).

    The check is keyed precisely on the *statement-level* ``with`` arg
    (an :class:`exp.With` node), so a T-SQL table hint such as
    ``WITH (NOLOCK)`` -- which sqlglot models on the *table* node, not the
    statement -- does not false-positive.

    Args:
        sql: The single SQL statement to inspect.
        dialect: The sqlglot dialect to parse under.

    Returns:
        ``True`` if the root statement is a leading CTE query, else ``False``.
    """
    parsed = sqlglot.parse_one(sql, read=dialect)
    # sqlglot keys the statement-level CTE arg as ``with_`` in current
    # versions (trailing underscore for the reserved word); older versions
    # used ``with``. Check both so the precise gate is version-robust.
    with_arg = parsed.args.get("with_") or parsed.args.get("with")
    return isinstance(with_arg, exp.With)


def _base_count_params() -> list[inspect.Parameter]:
    """Return the fixed base signature params for ``count_records``.

    The runtime ``connection``/``database`` selector params (added only for
    multi-target installs) are appended separately via
    :func:`build_target_params`, so a single-target signature is exactly these
    two parameters.

    Returns:
        The ``sql`` / ``params`` parameters in order.
    """
    return [
        inspect.Parameter(
            "sql",
            kind=inspect.Parameter.POSITIONAL_OR_KEYWORD,
            annotation=Annotated[
                str, Field(description="The read-only SELECT to count.")
            ],
        ),
        inspect.Parameter(
            "params",
            kind=inspect.Parameter.POSITIONAL_OR_KEYWORD,
            default=None,
            annotation=Annotated[
                Optional[dict[str, Any]],  # noqa: UP007
                Field(description="Bound values for :name placeholders."),
            ],
        ),
    ]


class CountTools:
    """Registers the ``count_records`` tool on an MCP server."""

    def __init__(self, registry: BackendRegistry, targets: ResolvedTargets) -> None:
        self._registry = registry
        self._targets = targets

    def register(self, mcp: FastMCP) -> None:
        """Register the ``count_records`` tool on ``mcp``.

        The ``(connection, database)`` target — and therefore the backend and
        sqlglot dialect — is resolved per call from optional keyword-only
        ``connection``/``database`` selector params (present only for
        multi-target installs). Single-target installs keep a byte-identical
        signature and behaviour.
        """
        registry = self._registry
        targets = self._targets

        async def core(
            sql: str,
            params: dict[str, Any] | None = None,
            *,
            connection: str | None = None,
            database: str | None = None,
        ) -> str:
            try:
                target = targets.resolve_pinned(connection, database)
            except ValueError as exc:
                return str(exc)
            backend = registry.backend_for(target)
            dialect = to_dialect(target.backend_name)
            async with log_tool_call("count_records", params or {}, sql=sql) as rec:
                rec.record(rows=1, cols=1)
                verdict = basic_preflight(sql, params, dialect)
                if verdict is not None:
                    return verdict
                violation = read_only_violation(sql, dialect)
                if violation is not None:
                    return violation
                if dialect == "tsql" and _has_leading_cte(sql, dialect):
                    return _LEADING_CTE_REJECTION
                wrapped = build_count_query(sql, dialect)
                try:
                    rows = backend.execute_readonly_query(wrapped, params)
                except _INVALID_SQL_EXC as exc:
                    return f"Invalid SQL. {type(exc).__name__}: {exc}"
                except (KeyError, TypeError, ValueError) as exc:
                    return f"Invalid parameters. {type(exc).__name__}: {exc}"
                except RuntimeError as exc:
                    return f"Database connection error. {type(exc).__name__}: {exc}"
                except Exception as exc:  # noqa: BLE001
                    return f"Unexpected error. {type(exc).__name__}: {exc}"
                return str(rows[0]["row_count"])

        sig_params = _base_count_params() + build_target_params(targets)
        fn = build_tool_fn("count_records", sig_params, core, _DESCRIPTION)
        mcp.add_tool(fn, name="count_records", description=_DESCRIPTION)
