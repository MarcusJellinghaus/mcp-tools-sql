"""MCP tools for SQL validation via the database's EXPLAIN mechanism."""

from __future__ import annotations

import inspect
import sqlite3
from typing import TYPE_CHECKING, Annotated, Any

from pydantic import Field

from mcp_tools_sql.backends.base import (
    QueryTimeoutError,
    to_dialect,
    translate_timeout,
)
from mcp_tools_sql.formatting import TIMEOUT_HINT_NARROWER
from mcp_tools_sql.query_helpers import build_target_params
from mcp_tools_sql.tool_builder import build_tool_fn
from mcp_tools_sql.tool_logging import log_tool_call
from mcp_tools_sql.utils.sql_placeholders import (
    basic_preflight,
    first_statement_kind,
    substitute_named_with_literals,
)
from mcp_tools_sql.utils.tool_spec import tool_spec

try:
    import pyodbc  # pylint: disable=import-error

    _PYODBC_ERROR: tuple[type[Exception], ...] = (pyodbc.Error,)
except ImportError:
    _PYODBC_ERROR = ()

_INVALID_SQL_EXC: tuple[type[BaseException], ...] = (sqlite3.Error, *_PYODBC_ERROR)

_SESSION_KEYWORDS = frozenset({"USE", "SET", "DECLARE"})

if TYPE_CHECKING:
    from mcp_tools_sql.backends.base import DatabaseBackend
    from mcp_tools_sql.backends.registry import BackendRegistry
    from mcp_tools_sql.config.models import ResolvedTargets
    from mcp_tools_sql.utils.tool_spec import ToolSink


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
    timeout_seconds: int,
) -> str:
    """Return the execution plan, dispatching on backend type.

    The T-SQL path works on a raw SHOWPLAN cursor, so a driver statement
    timeout (``HYT00``) is translated here into :class:`QueryTimeoutError`.

    Raises:
        QueryTimeoutError: If the SHOWPLAN statement hit the statement timeout.
    """
    if backend_name == "sqlite":
        return backend.explain(sql, params)
    explain_sql = substitute_named_with_literals(sql, params or {}, "tsql")
    with backend.get_isolated_connection() as conn:
        try:
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
        except Exception as exc:
            if translate_timeout(exc, timeout_seconds) is not None:
                raise QueryTimeoutError(timeout_seconds) from exc
            raise


def _base_validate_params() -> list[inspect.Parameter]:
    """Return the fixed base signature params for ``validate_sql``.

    The runtime ``connection``/``database`` selector params (added only for
    multi-target installs) are appended separately via
    :func:`build_target_params`, so a single-target signature is exactly these
    three parameters.

    Returns:
        The ``sql`` / ``params`` / ``return_plan`` parameters in order.
    """
    return [
        inspect.Parameter(
            "sql",
            kind=inspect.Parameter.POSITIONAL_OR_KEYWORD,
            annotation=Annotated[str, Field(description="The SQL to validate.")],
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
        inspect.Parameter(
            "return_plan",
            kind=inspect.Parameter.POSITIONAL_OR_KEYWORD,
            default=False,
            annotation=Annotated[
                bool,
                Field(description="Append the execution plan on success."),
            ],
        ),
    ]


class ValidationTools:
    """Builds the ``validate_sql`` tool spec."""

    def __init__(self, registry: BackendRegistry, targets: ResolvedTargets) -> None:
        self._registry = registry
        self._targets = targets

    def register(self, sink: ToolSink) -> None:
        """Add the ``validate_sql`` tool spec to ``sink``.

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
            return_plan: bool = False,
            *,
            connection: str | None = None,
            database: str | None = None,
        ) -> str:
            try:
                target = targets.resolve_pinned(connection, database)
            except ValueError as exc:
                return str(exc)
            backend = registry.backend_for(target)
            backend_name = target.backend_name
            async with log_tool_call("validate_sql", params or {}, sql=sql) as rec:
                rec.record(rows=0, cols=0)
                verdict = _preflight(sql, params, to_dialect(backend_name))
                if verdict is not None:
                    return verdict
                try:
                    plan = _explain(
                        backend,
                        backend_name,
                        sql,
                        params,
                        target.config.query_timeout_seconds,
                    )
                except QueryTimeoutError as exc:
                    return f"{exc} {TIMEOUT_HINT_NARROWER}"
                except _INVALID_SQL_EXC as exc:
                    return f"Invalid SQL. {type(exc).__name__}: {exc}"
                except (KeyError, TypeError, ValueError) as exc:
                    return f"Invalid parameters. {type(exc).__name__}: {exc}"
                except RuntimeError as exc:
                    return f"Database connection error. {type(exc).__name__}: {exc}"
                except Exception as exc:
                    return f"Unexpected error. {type(exc).__name__}: {exc}"
                if return_plan:
                    return f"Valid.\nExecution plan:\n{plan}"
                return "Valid."

        sig_params = _base_validate_params() + build_target_params(targets)
        fn = build_tool_fn("validate_sql", sig_params, core, _DESCRIPTION)
        sink.add(
            tool_spec(
                fn,
                group="sql.validation",
                read_only=True,
                name="validate_sql",
                description=_DESCRIPTION,
            )
        )
