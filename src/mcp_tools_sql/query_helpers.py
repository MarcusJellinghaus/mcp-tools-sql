"""Shared helpers for assembling query-style MCP tool signatures and bodies.

These building blocks are used by both ``query_tools`` (user-configured
queries) and ``schema_tools`` (built-in schema queries). They live one
layer below the tool modules so the two can share code without forming
a sibling-to-sibling dependency.
"""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from fnmatch import fnmatch
from typing import TYPE_CHECKING, Annotated, Any, Literal, Optional, cast

from pydantic import Field

from mcp_tools_sql.formatting import format_fanout_rows, format_rows
from mcp_tools_sql.tool_logging import log_tool_call
from mcp_tools_sql.utils.data_type_utility.type_mapping import resolve_python_type
from mcp_tools_sql.utils.sql_placeholders import ParseError, extract_param_names

if TYPE_CHECKING:
    from mcp_tools_sql.backends.base import DatabaseBackend
    from mcp_tools_sql.backends.registry import BackendRegistry
    from mcp_tools_sql.config.models import QueryConfig, ResolvedTargets


def extract_sql_params(sql: str) -> set[str]:
    """Scan SQL for :param_name references.

    Placeholders inside quoted strings and comments are ignored. SQL that
    cannot be parsed yields an empty set rather than raising: param discovery
    is best-effort, and the dedicated EXPLAIN check owns the "is this valid
    SQL" verdict during verification.

    Returns:
        Set of parameter names found in the SQL string, or an empty set when
        ``sql`` cannot be parsed.
    """
    try:
        return extract_param_names(sql)
    except ParseError:
        return set()


def apply_filter(
    rows: list[dict[str, Any]],
    column: str,
    pattern: str | None,
) -> list[dict[str, Any]]:
    """Apply fnmatch glob filter on ``column``.

    Returns:
        Filtered rows matching the glob pattern.
    """
    if not pattern:
        return rows
    return [r for r in rows if fnmatch(str(r.get(column, "")).lower(), pattern.lower())]


def build_query_sig_params(config: QueryConfig) -> list[inspect.Parameter]:
    """Build the public signature parameters for a query tool.

    Returns:
        User-declared params followed by an implicit ``max_rows`` parameter
        and, when ``config.filter_column`` is non-empty, a
        ``<filter_column>_filter`` parameter.
    """
    sig_params: list[inspect.Parameter] = []
    for param_cfg in config.params.values():
        python_type = resolve_python_type(param_cfg.type)
        desc = param_cfg.description

        if param_cfg.required:
            annotation: Any = (
                Annotated[python_type, Field(description=desc)] if desc else python_type
            )
            sig_params.append(
                inspect.Parameter(
                    param_cfg.name,
                    kind=inspect.Parameter.POSITIONAL_OR_KEYWORD,
                    default=inspect.Parameter.empty,
                    annotation=annotation,
                )
            )
        else:
            annotation = (
                Annotated[Optional[python_type], Field(description=desc)]  # noqa: UP007
                if desc
                else Optional[python_type]  # noqa: UP007
            )
            sig_params.append(
                inspect.Parameter(
                    param_cfg.name,
                    kind=inspect.Parameter.POSITIONAL_OR_KEYWORD,
                    default=None,
                    annotation=annotation,
                )
            )

    max_rows_desc = "Maximum rows to return"
    sig_params.append(
        inspect.Parameter(
            "max_rows",
            kind=inspect.Parameter.POSITIONAL_OR_KEYWORD,
            default=config.max_rows_default,
            annotation=Annotated[int, Field(description=max_rows_desc)],
        )
    )

    if config.filter_column:
        filter_kwarg = f"{config.filter_column}_filter"
        filter_desc = (
            f"Glob pattern (case-insensitive) on the {config.filter_column} column"
        )
        sig_params.append(
            inspect.Parameter(
                filter_kwarg,
                kind=inspect.Parameter.POSITIONAL_OR_KEYWORD,
                default=None,
                annotation=Annotated[
                    Optional[str], Field(description=filter_desc)
                ],  # noqa: UP007
            )
        )

    return sig_params


def _cap_max_rows(config: QueryConfig, requested: int) -> tuple[int, str]:
    """Clamp ``requested`` to ``config.max_rows_hard``.

    Returns:
        A ``(capped, note)`` pair. ``note`` is a human-readable explanation to
        append to output when the request exceeded the hard limit, else "".
    """
    hard: int = cast(int, config.max_rows_hard)
    if requested > hard:
        note = (
            f"\n\nRequested max_rows={requested} exceeds hard limit "
            f"{hard}; capped at {hard}."
        )
        return hard, note
    return requested, ""


async def execute_and_format(
    name: str,
    resolved_sql: str,
    sql_params: set[str],
    backend: DatabaseBackend,
    config: QueryConfig,
    filter_kwarg: str | None,
    truncation_hint: str,
    kwargs: dict[str, Any],
) -> str:
    """Shared execution+format tail for query-style tool bodies.

    Applies the ``max_rows`` hard-limit cap (appending a note when clamped),
    pops the filter kwarg, strips ``kwargs`` down to declared SQL params, logs
    the call, executes the query, applies the optional filter, and formats the
    rows. Used by both ``build_query_body`` (pinned) and the runtime schema
    bodies so the common tail has a single home.

    Returns:
        The formatted result text, with a max_rows cap note appended when the
        requested limit exceeded the hard limit.
    """
    requested, note = _cap_max_rows(
        config, kwargs.pop("max_rows", config.max_rows_default)
    )
    filter_pattern: str | None = (
        kwargs.pop(filter_kwarg, None) if filter_kwarg else None
    )

    stripped = {k: v for k, v in kwargs.items() if k in sql_params}

    async with log_tool_call(name, stripped, sql=resolved_sql) as rec:
        rows = backend.execute_query(resolved_sql, stripped or None)
        if filter_kwarg:
            rows = apply_filter(rows, config.filter_column, filter_pattern)
        rec.record(rows=len(rows), cols=len(rows[0]) if rows else 0)
        return format_rows(rows, requested, truncation_hint=truncation_hint) + note


def build_query_body(
    name: str,
    config: QueryConfig,
    backend: DatabaseBackend,
    backend_name: str,
    truncation_hint: str,
) -> Callable[..., Awaitable[str]]:
    """Build the async body closure that executes a query at tool call time.

    Returns:
        An async callable accepting the same kwargs as the tool's public
        signature, returning the formatted result text.
    """
    resolved_sql = config.resolve_sql(backend_name)
    sql_params = extract_sql_params(resolved_sql)
    filter_kwarg = f"{config.filter_column}_filter" if config.filter_column else None

    async def body(**kwargs: Any) -> str:
        return await execute_and_format(
            name,
            resolved_sql,
            sql_params,
            backend,
            config,
            filter_kwarg,
            truncation_hint,
            kwargs,
        )

    return body


def build_target_params(
    targets: ResolvedTargets,
    *,
    star: bool = False,
) -> list[inspect.Parameter]:
    """Build the keyword-only ``connection``/``database`` selector parameters.

    These runtime target-selection params are shown only for multi-target
    installs, so a single-target signature stays byte-identical to today:

    * Nothing is added unless ``targets.is_multi``.
    * A keyword-only ``connection`` param (``Literal`` enum of the connection
      names, defaulting to the file-default connection) is added only when more
      than one connection is configured.
    * A keyword-only ``database`` param (``Literal`` enum of the database names)
      is always added under multi. Its default is ``None`` so ``resolve_pinned``
      falls back to the *selected* connection's ``default_database`` rather than
      the file-default connection's catalog.

    Args:
        targets: The resolved targets to derive the enum members from.
        star: When True, append the ``"*"`` fan-out sentinel to the ``database``
            enum. Only the ``schema_tools`` fan-out caller passes ``star=True``;
            pinned callers take the default and never see ``"*"``.

    Returns:
        The keyword-only selector params, or an empty list when not multi.
    """
    if not targets.is_multi:
        return []

    params: list[inspect.Parameter] = []

    connection_names = targets.connection_names
    if len(connection_names) > 1:
        conn_enum: Any = Literal.__getitem__(tuple(connection_names))
        conn_desc = "Connection to run against (defaults to the file default)."
        params.append(
            inspect.Parameter(
                "connection",
                kind=inspect.Parameter.KEYWORD_ONLY,
                default=targets.file_default_connection,
                annotation=Annotated[conn_enum, Field(description=conn_desc)],
            )
        )

    db_names = list(targets.database_names)
    if star:
        db_names.append("*")
    db_enum: Any = Literal.__getitem__(tuple(db_names))
    db_desc = "Database (catalog) to run against; defaults to the connection default."
    if star:
        db_desc += " Use '*' to fan out across all databases of the connection."
    params.append(
        inspect.Parameter(
            "database",
            kind=inspect.Parameter.KEYWORD_ONLY,
            default=None,
            annotation=Annotated[Optional[db_enum], Field(description=db_desc)],
        )
    )

    return params


def build_schema_body(
    name: str,
    config: QueryConfig,
    registry: BackendRegistry,
    targets: ResolvedTargets,
    truncation_hint: str,
) -> Callable[..., Awaitable[str]]:
    """Build a runtime-resolving schema tool body over one or all targets.

    Unlike :func:`build_query_body` (which pins its backend at registration
    time), this body resolves its ``(connection, database)`` target from the
    call-time ``connection``/``database`` kwargs. For a pinned database it
    resolves exactly one target and delegates to the shared
    :func:`execute_and_format` core. For ``database="*"`` it fans out across
    **every** database of the resolved connection, tags each row with a
    ``_database`` column, merges in config order, caps the merged total at
    ``max_rows``, and renders a per-database footer plus inline per-target
    errors via :func:`format_fanout_rows`. The ``_database`` column appears
    only on the fan-out path — single-target output is unchanged.

    Returns:
        An async callable that resolves its target(s) then executes and formats
        the result, or returns a friendly verdict string when the pinned target
        pair is invalid.
    """
    filter_kwarg = f"{config.filter_column}_filter" if config.filter_column else None

    async def fanout(conn: str, kwargs: dict[str, Any]) -> str:
        """Execute against every database of ``conn`` and merge the rows.

        Returns:
            The merged, formatted rows, or a friendly verdict string when
            ``conn`` is not a known connection.
        """
        fan_targets = targets.for_connection(conn)
        if not fan_targets:
            return (
                f"Connection '{conn}' not found. "
                f"Available: {targets.connection_names}"
            )
        requested, note = _cap_max_rows(
            config, kwargs.pop("max_rows", config.max_rows_default)
        )
        filter_pattern: str | None = (
            kwargs.pop(filter_kwarg, None) if filter_kwarg else None
        )
        # All targets of one connection share a backend_name → resolve SQL once.
        resolved_sql = config.resolve_sql(fan_targets[0].backend_name)
        sql_params = extract_sql_params(resolved_sql)
        stripped = {k: v for k, v in kwargs.items() if k in sql_params}

        merged: list[dict[str, Any]] = []
        counts: dict[str, int] = {}
        errors: list[tuple[str, str]] = []
        async with log_tool_call(name, stripped, sql=resolved_sql) as rec:
            for target in fan_targets:
                try:
                    rows = registry.backend_for(target).execute_query(
                        resolved_sql, stripped or None
                    )
                    if filter_kwarg:
                        rows = apply_filter(rows, config.filter_column, filter_pattern)
                    for row in rows:
                        row["_database"] = target.database
                    counts[target.database] = len(rows)
                    merged.extend(rows)
                except Exception as exc:  # noqa: BLE001
                    errors.append((target.database, str(exc)))
            rec.record(rows=len(merged), cols=len(merged[0]) if merged else 0)
        formatted = format_fanout_rows(
            merged, counts, errors, requested, truncation_hint=truncation_hint
        )
        return formatted + note

    async def body(**kwargs: Any) -> str:
        conn = kwargs.pop("connection", None) or targets.file_default_connection
        db = kwargs.pop("database", None)
        if db == "*":
            return await fanout(conn, kwargs)
        try:
            target = targets.resolve_pinned(conn, db)
        except ValueError as exc:
            return str(exc)
        resolved_sql = config.resolve_sql(target.backend_name)
        sql_params = extract_sql_params(resolved_sql)
        backend = registry.backend_for(target)
        return await execute_and_format(
            name,
            resolved_sql,
            sql_params,
            backend,
            config,
            filter_kwarg,
            truncation_hint,
            kwargs,
        )

    return body
