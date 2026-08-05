"""``SummarizeTools``: orchestration and registration for ``summarize_columns``.

This module assembles the summarize package's SQL (``summarize/sql.py``) and
rendering (``summarize/render.py``) layers into the single ``summarize_columns``
MCP tool. It mirrors ``count_tools.CountTools``: a :func:`build_tool_fn`-assembled
tool that resolves its ``(connection, database)`` target per call via
:func:`build_target_params` (pinned -- no ``"*"`` fan-out), executes every query
through :meth:`DatabaseBackend.execute_readonly_query`, and returns a plain
string.

The per-call ``core`` runs the profiling pipeline: metadata query -> column
narrow/cap -> filtered ``COUNT(*)`` short-circuit -> single scalar-aggregate
pass -> per-column value lists (deep view only) -> :func:`render_summary`. The
user's ``where`` predicate is validated fail-closed and its ``params`` are
threaded into *every* predicate-bearing query so ``:name`` placeholders bind.
"""

from __future__ import annotations

import inspect
import sqlite3
from typing import TYPE_CHECKING, Annotated, Any, Literal, Optional

from pydantic import Field

from mcp_tools_sql.query_helpers import build_target_params
from mcp_tools_sql.summarize.render import (
    COLUMN_CAP,
    DISTINCT_GATE_ROWS,
    TRIAGE_THRESHOLD,
    ColumnProfile,
    empty_columns_message,
    empty_filter_message,
    empty_table_message,
    render_summary,
    table_not_found_message,
    unknown_columns_message,
)
from mcp_tools_sql.summarize.sql import (
    ColumnMeta,
    build_count_sql,
    build_scalar_sql,
    build_table_ref,
    build_value_list_sql,
    categorize_type,
    clamp_n,
    metadata_sql,
    validate_where,
)
from mcp_tools_sql.tool_builder import build_tool_fn
from mcp_tools_sql.tool_logging import log_tool_call
from mcp_tools_sql.utils.sql_placeholders import to_dialect

try:
    import pyodbc  # pylint: disable=import-error

    _PYODBC_ERROR: tuple[type[Exception], ...] = (pyodbc.Error,)
except ImportError:
    _PYODBC_ERROR = ()

_INVALID_SQL_EXC: tuple[type[BaseException], ...] = (sqlite3.Error, *_PYODBC_ERROR)

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP

    from mcp_tools_sql.backends.base import DatabaseBackend
    from mcp_tools_sql.backends.registry import BackendRegistry
    from mcp_tools_sql.config.models import ResolvedTargets


_DESCRIPTION = (
    "Profile the data in a table's columns: row/null/distinct counts, "
    "category-appropriate statistics (min/max/mean/sum for numeric, date "
    "bounds for temporal, length stats for string, true/false counts for "
    "boolean, byte sizes for binary), and duplication-driven value lists "
    "(top values with frequencies when values repeat, a sample when every "
    "value is unique). Read-only. Narrow with columns= and filter with a "
    "read-only where predicate; the predicate must use :name placeholders "
    "for values, bound via params (never inline literals). Returns a "
    "formatted text block; tables wider than 15 profiled columns render a "
    "compact one-line-per-column triage instead. n sets the value-list "
    "length (default 20, clamped to 1..50)."
)


def _base_summarize_params() -> list[inspect.Parameter]:
    """Return the fixed base signature params for ``summarize_columns``.

    The runtime ``connection``/``database`` selector params (added only for
    multi-target installs) are appended separately via
    :func:`build_target_params`, so a single-target signature is exactly these
    six parameters, all ``POSITIONAL_OR_KEYWORD``.

    Returns:
        The ``schema`` / ``table`` / ``columns`` / ``where`` / ``params`` / ``n``
        parameters in order.
    """
    return [
        inspect.Parameter(
            "schema",
            kind=inspect.Parameter.POSITIONAL_OR_KEYWORD,
            annotation=Annotated[
                str, Field(description="Owning schema (ignored on SQLite).")
            ],
        ),
        inspect.Parameter(
            "table",
            kind=inspect.Parameter.POSITIONAL_OR_KEYWORD,
            annotation=Annotated[str, Field(description="Table to profile.")],
        ),
        inspect.Parameter(
            "columns",
            kind=inspect.Parameter.POSITIONAL_OR_KEYWORD,
            default=None,
            annotation=Annotated[
                Optional[list[str]],  # noqa: UP007
                Field(description="Columns to profile; omit for all."),
            ],
        ),
        inspect.Parameter(
            "where",
            kind=inspect.Parameter.POSITIONAL_OR_KEYWORD,
            default=None,
            annotation=Annotated[
                Optional[str],  # noqa: UP007
                Field(description="Read-only predicate; :name placeholders only."),
            ],
        ),
        inspect.Parameter(
            "params",
            kind=inspect.Parameter.POSITIONAL_OR_KEYWORD,
            default=None,
            annotation=Annotated[
                Optional[dict[str, Any]],  # noqa: UP007
                Field(description="Bound values for the where :name placeholders."),
            ],
        ),
        inspect.Parameter(
            "n",
            kind=inspect.Parameter.POSITIONAL_OR_KEYWORD,
            default=20,
            annotation=Annotated[
                int, Field(description="Value-list length (clamped to 1..50).")
            ],
        ),
    ]


def _narrow_columns(
    metas: list[ColumnMeta], columns: list[str] | None
) -> str | tuple[int, list[ColumnMeta]]:
    """Narrow the metadata columns to the requested set, before any data query.

    Matching is case-insensitive against the declared names; unknown names fail
    the whole call, an explicitly empty ``columns=[]`` fails (rather than
    silently profiling nothing), and repeats are de-duplicated case-insensitively
    in first-seen order. The chosen columns are sorted by ordinal and capped to
    the first :data:`COLUMN_CAP`.

    Args:
        metas: The full column metadata list from the metadata query.
        columns: Requested column names, ``None`` for all, ``[]`` an error.

    Returns:
        A ``(total_columns, profiled)`` pair on success, or an error message
        string (empty-``columns=[]`` / unknown-column) to return to the caller.
    """
    by_lower = {m.name.lower(): m for m in metas}
    available = [m.name for m in metas]
    if columns is None:
        chosen: list[ColumnMeta] = list(metas)
    else:
        if not columns:
            return empty_columns_message(available)
        bad = [c for c in columns if c.lower() not in by_lower]
        if bad:
            return unknown_columns_message(bad, available)
        seen: set[str] = set()
        chosen = []
        for c in columns:
            key = c.lower()
            if key in seen:
                continue
            seen.add(key)
            chosen.append(by_lower[key])
    total_columns = len(chosen)
    profiled = sorted(chosen, key=lambda m: m.ordinal)[:COLUMN_CAP]
    return (total_columns, profiled)


def _split_stats(
    row: dict[str, Any], idx: int
) -> tuple[int, int | None, dict[str, Any]]:
    """Split one scalar-pass result row into a column's non_null/distinct/stats.

    The scalar pass aliases every aggregate ``c{idx}__{stat}``; this reads back
    the slice for column ``idx``, pulls ``nonnull`` (always present) and
    ``distinct`` (``None`` when the alias was gated out or never emitted) into
    their own fields, and returns the remaining aggregates as the ``stats`` dict.

    Args:
        row: The single scalar-aggregate result row.
        idx: The column's position index (its ``c{idx}`` alias prefix).

    Returns:
        A ``(non_null, distinct, stats)`` triple for :class:`ColumnProfile`.
    """
    prefix = f"c{idx}__"
    col_stats = {
        key[len(prefix) :]: value
        for key, value in row.items()
        if key.startswith(prefix)
    }
    non_null = int(col_stats.pop("nonnull"))
    distinct = col_stats.pop("distinct", None)
    return (non_null, distinct, col_stats)


class SummarizeTools:
    """Registers the ``summarize_columns`` tool on an MCP server."""

    def __init__(self, registry: BackendRegistry, targets: ResolvedTargets) -> None:
        self._registry = registry
        self._targets = targets

    def register(self, mcp: FastMCP) -> None:
        """Register the ``summarize_columns`` tool on ``mcp``.

        The ``(connection, database)`` target -- and therefore the backend and
        sqlglot dialect -- is resolved per call from optional keyword-only
        ``connection``/``database`` selector params (present only for
        multi-target installs). Single-target installs keep an identical
        signature and behaviour.
        """
        registry = self._registry
        targets = self._targets

        async def core(
            schema: str,
            table: str,
            columns: list[str] | None = None,
            where: str | None = None,
            params: dict[str, Any] | None = None,
            n: int = 20,
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
            async with log_tool_call(
                "summarize_columns", params or {}, sql=where or ""
            ) as rec:
                predicate, where_error = validate_where(
                    where, schema, table, params, dialect
                )
                if where_error is not None:
                    return where_error
                table_ref = build_table_ref(schema, table, dialect)
                try:
                    return _run(
                        backend,
                        rec,
                        schema,
                        table,
                        table_ref,
                        predicate,
                        params,
                        columns,
                        n,
                        dialect,
                    )
                except _INVALID_SQL_EXC as exc:
                    return f"Invalid SQL. {type(exc).__name__}: {exc}"
                except (KeyError, TypeError, ValueError) as exc:
                    return f"Invalid parameters. {type(exc).__name__}: {exc}"
                except RuntimeError as exc:
                    return f"Database connection error. {type(exc).__name__}: {exc}"
                except Exception as exc:  # noqa: BLE001
                    return f"Unexpected error. {type(exc).__name__}: {exc}"

        sig_params = _base_summarize_params() + build_target_params(targets, star=False)
        fn = build_tool_fn("summarize_columns", sig_params, core, _DESCRIPTION)
        mcp.add_tool(fn, name="summarize_columns", description=_DESCRIPTION)


def _run(  # noqa: PLR0913
    backend: DatabaseBackend,
    rec: Any,
    schema: str,
    table: str,
    table_ref: Any,
    predicate: Any,
    params: dict[str, Any] | None,
    columns: list[str] | None,
    n: int,
    dialect: str,
) -> str:
    """Execute the metadata -> count -> scalar -> value-list profiling pipeline.

    Split out of ``core`` so the ``count_tools`` exception tail wraps a single
    call. Every predicate-bearing query is passed ``params`` so the validated
    ``where`` predicate's ``:name`` placeholders bind; the metadata query takes
    its own ``{schema, table}`` dict and the unfiltered zero-match count carries
    no predicate.

    Args:
        backend: The resolved backend to execute read-only queries on.
        rec: The open :class:`ToolCallRecord` to record the profiled shape on.
        schema: Owning schema (for the metadata query and messages).
        table: Table name (for the metadata query and messages).
        table_ref: The dialect table reference from :func:`build_table_ref`.
        predicate: The validated ``where`` predicate AST, or ``None``.
        params: Bound values for the predicate's ``:name`` placeholders.
        columns: Requested column names, ``None`` for all, ``[]`` an error.
        n: Requested value-list length (clamped in-pipeline).
        dialect: Backend dialect, ``"sqlite"`` or ``"tsql"``.

    Returns:
        The rendered profiling block / triage table / status message.
    """
    meta_rows = backend.execute_readonly_query(
        metadata_sql(dialect), {"schema": schema, "table": table}
    )
    if not meta_rows:
        return table_not_found_message(schema, table)
    metas = [
        ColumnMeta(
            name=r["name"],
            declared_type=r["type"],
            category=categorize_type(r["type"], dialect),
            ordinal=r["ordinal"],
        )
        for r in meta_rows
    ]
    narrowed = _narrow_columns(metas, columns)
    if isinstance(narrowed, str):
        return narrowed
    total_columns, profiled = narrowed
    rec.record(rows=len(profiled), cols=1)

    rows = backend.execute_readonly_query(
        build_count_sql(table_ref, predicate, dialect), params
    )[0]["row_count"]
    if rows == 0:
        if predicate is not None:
            total_rows = backend.execute_readonly_query(
                build_count_sql(table_ref, None, dialect), params
            )[0]["row_count"]
            return empty_filter_message(total_rows)
        return empty_table_message(schema, table)

    view = "triage" if len(profiled) > TRIAGE_THRESHOLD else "deep"
    include_distinct = view == "deep" or rows <= DISTINCT_GATE_ROWS
    scalar_row = backend.execute_readonly_query(
        build_scalar_sql(
            profiled, table_ref, predicate, dialect, include_distinct=include_distinct
        ),
        params,
    )[0]

    clamped_n, clamp_note = clamp_n(n)
    profiles: list[ColumnProfile] = []
    for idx, meta in enumerate(profiled):
        non_null, distinct, col_stats = _split_stats(scalar_row, idx)
        value_kind: Literal["top", "sample", "none"] = "none"
        values: list[tuple[Any, ...]] | None = None
        if view == "deep" and meta.category != "other" and non_null > 0:
            value_kind = (
                "top" if distinct is not None and distinct < non_null else "sample"
            )
            vl_rows = backend.execute_readonly_query(
                build_value_list_sql(
                    meta, table_ref, predicate, clamped_n, dialect, kind=value_kind
                ),
                params,
            )
            if value_kind == "top":
                values = [(r["value"], r["freq"]) for r in vl_rows]
            else:
                values = [(r["value"],) for r in vl_rows]
        profiles.append(
            ColumnProfile(
                meta=meta,
                rows=rows,
                non_null=non_null,
                distinct=distinct,
                stats=col_stats,
                values=values,
                value_kind=value_kind,
            )
        )
    return (
        render_summary(profiles, total_columns, distinct_gated=not include_distinct)
        + clamp_note
    )
