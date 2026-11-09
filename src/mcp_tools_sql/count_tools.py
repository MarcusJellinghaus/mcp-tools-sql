"""MCP tool for counting the rows a read-only SELECT would return.

``count_records`` is a read-only sibling of ``validate_sql``: unlike
``validate_sql`` (which only EXPLAINs and never executes), this tool *runs* a
``SELECT COUNT(*)`` wrapper around the user's query and returns the row count as
a plain number string.

Security model (see ``pr_info/steps/summary.md``):

- **Layer 1 (primary) — sqlglot AST.** :func:`arbitrary_sql_violation` proves by
  AST inspection that the statement is read-only before anything executes, and
  rejects the T-SQL pass-through row-set functions (``OPENQUERY`` and friends)
  by name. Those are the limit of the proof, not part of it: the statement they
  carry runs on another server, so the AST cannot clear it.
- **Layer 2 (backstop) — DB-enforced read-only.** The wrapped count runs through
  :meth:`DatabaseBackend.execute_readonly_query` (SQLite: a fresh
  ``PRAGMA query_only=ON`` connection; MSSQL: a documented read-only login, so
  on MSSQL layer 1 is the only enforcement inside this process).
"""

from __future__ import annotations

import inspect
from typing import TYPE_CHECKING, Annotated, Any

from pydantic import Field

from mcp_tools_sql.backends.base import BackendError, QueryTimeoutError, to_dialect
from mcp_tools_sql.formatting import TIMEOUT_HINT_NARROWER
from mcp_tools_sql.query_helpers import build_target_params
from mcp_tools_sql.sql_ast.placeholders import (
    LEADING_CTE_REJECTION,
    arbitrary_sql_violation,
    basic_preflight,
    build_count_query,
    has_leading_cte,
)
from mcp_tools_sql.tool_builder import build_tool_fn
from mcp_tools_sql.tool_logging import log_tool_call
from mcp_tools_sql.utils.tool_spec import tool_spec

if TYPE_CHECKING:
    from mcp_tools_sql.backends.registry import BackendRegistry
    from mcp_tools_sql.config.models import ResolvedTargets
    from mcp_tools_sql.utils.tool_spec import ToolSink


_DESCRIPTION = (
    "Count the rows a read-only SELECT would return. Executes a "
    "SELECT COUNT(*) wrapper around your query (read-only); rejects any "
    "statement that is not read-only (no INSERT/UPDATE/DELETE/DDL/SELECT...INTO). "
    "Returns the count as a plain number. Supports :name placeholders via "
    "params. Unlike validate_sql, this tool executes the wrapped count query."
)


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
                dict[str, Any] | None,
                Field(description="Bound values for :name placeholders."),
            ],
        ),
    ]


class CountTools:
    """Builds the ``count_records`` tool spec."""

    def __init__(self, registry: BackendRegistry, targets: ResolvedTargets) -> None:
        self._registry = registry
        self._targets = targets

    def register(self, sink: ToolSink) -> None:
        """Add the ``count_records`` tool spec to ``sink``.

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
                violation = arbitrary_sql_violation(sql, dialect)
                if violation is not None:
                    return violation
                if dialect == "tsql" and has_leading_cte(sql, dialect):
                    return LEADING_CTE_REJECTION
                wrapped = build_count_query(sql, dialect)
                try:
                    rows = backend.execute_readonly_query(wrapped, params)
                except QueryTimeoutError as exc:
                    return f"{exc} {TIMEOUT_HINT_NARROWER}"
                except BackendError as exc:
                    name = getattr(exc, "original_class", type(exc).__name__)
                    return f"Invalid SQL. {name}: {exc}"
                except (KeyError, TypeError, ValueError) as exc:
                    return f"Invalid parameters. {type(exc).__name__}: {exc}"
                except RuntimeError as exc:
                    return f"Database connection error. {type(exc).__name__}: {exc}"
                except Exception as exc:
                    name = getattr(exc, "original_class", type(exc).__name__)
                    return f"Unexpected error. {name}: {exc}"
                return str(rows[0]["row_count"])

        sig_params = _base_count_params() + build_target_params(targets)
        fn = build_tool_fn("count_records", sig_params, core, _DESCRIPTION)
        sink.add(
            tool_spec(
                fn,
                group="sql.profiling",
                read_only=True,
                name="count_records",
                description=_DESCRIPTION,
            )
        )
