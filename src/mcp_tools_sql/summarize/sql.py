"""SQL generation and data structures for the ``summarize_columns`` tool.

This module hosts the summarize package's data layer. It provides the pure,
dialect-aware type categoriser that every later summarize step dispatches on,
the front of the execution pipeline (the fail-closed ``where`` gate, the dialect
table reference, the static metadata query, and the filtered ``COUNT(*)``); the
scalar-aggregate / value-list SQL builders and the shared ``ColumnMeta``
dataclass land in subsequent steps.

The categoriser is prefix/affinity-based, not an exact-match lookup: SQLite's
declared type is an arbitrary affinity string (``VARCHAR(20)``, ``NUM``, or even
empty), so classification keys off substrings and a few dialect-specific guards.

All *executable* SQL is built as a sqlglot AST and rendered via
``.sql(dialect=...)`` -- never string-concatenated -- so dialect differences
(bracket vs double-quote identifier quoting) fall out of the renderer. The
metadata query is the sole exception: it injects only bound ``:schema``/
``:table`` values, so it is a per-dialect constant string.
"""

from __future__ import annotations

from typing import Any, Literal

import sqlglot
from sqlglot import exp

from mcp_tools_sql.utils.sql_placeholders import (
    basic_preflight,
    read_only_violation,
)

Category = Literal["numeric", "temporal", "string", "boolean", "other"]

# Exact declared types, matched before the generic token scans below.
_BOOLEAN_TYPES = frozenset({"bit", "bool", "boolean"})
# T-SQL large-object types: cannot appear in GROUP BY / DISTINCT / comparisons,
# so they are profiled as ``other`` (no distinct, no value list). The generic
# ``text`` string token would otherwise misclassify text/ntext as ``string``.
_TSQL_LOB_TYPES = frozenset({"text", "ntext", "image"})
# T-SQL ``timestamp``/``rowversion`` is a binary(8) row-version stamp, NOT a
# date/time. Guarded before the temporal token scan so step 3 never emits
# MIN/MAX on it (SQL Server Msg 8117 would break the shared scalar SELECT).
_TSQL_BINARY_TYPES = frozenset({"timestamp", "rowversion"})

# Substring tokens scanned (in order) once the exact/guard checks miss.
_NUMERIC_TOKENS = ("int", "decimal", "float", "num", "real", "money")
_TEMPORAL_TOKENS = ("date", "time", "timestamp")
_STRING_TOKENS = ("char", "text", "clob", "string")


def categorize_type(declared_type: str, dialect: str) -> Category:
    """Classify a declared column type into a coarse profiling category.

    Matching is case-insensitive and prefix/affinity-based (substring tokens),
    not exact lookup. Order is load-bearing: T-SQL LOB and row-version guards
    run before the generic token scans, and ``boolean`` before ``numeric`` so a
    ``bit`` column is never swept up by an integer token.

    Args:
        declared_type: Raw declared/reported type string (e.g. ``VARCHAR(20)``,
            ``NUM``, ``nvarchar(max)``); may be empty for a SQLite affinity.
        dialect: Backend dialect, ``"sqlite"`` or ``"tsql"``. Only the T-SQL
            LOB and ``timestamp``/``rowversion`` guards depend on it.

    Returns:
        One of the five :data:`Category` literal values.
    """
    t = declared_type.strip().lower()
    if dialect == "tsql" and t in _TSQL_LOB_TYPES:
        return "other"
    if dialect == "tsql" and t in _TSQL_BINARY_TYPES:
        return "other"
    if t in _BOOLEAN_TYPES:
        return "boolean"
    if any(token in t for token in _NUMERIC_TOKENS):
        return "numeric"
    if any(token in t for token in _TEMPORAL_TOKENS):
        return "temporal"
    if t == "" or any(token in t for token in _STRING_TOKENS):
        return "string"
    return "other"


# Static per-dialect metadata queries. These inject only bound ``:schema`` /
# ``:table`` values (never identifiers), so they need no AST -- a plain constant
# string per dialect. Aliased to the shared ``name`` / ``type`` / ``ordinal``
# result shape that step 3 consumes when building ``ColumnMeta``.
_METADATA_SQL: dict[str, str] = {
    "tsql": (
        "SELECT COLUMN_NAME AS name, DATA_TYPE AS type, "
        "ORDINAL_POSITION AS ordinal "
        "FROM INFORMATION_SCHEMA.COLUMNS "
        "WHERE TABLE_SCHEMA = :schema AND TABLE_NAME = :table "
        "ORDER BY ORDINAL_POSITION"
    ),
    "sqlite": (
        "SELECT name, type, cid AS ordinal "
        "FROM pragma_table_info(:table) ORDER BY cid"
    ),
}


def build_table_ref(schema: str, table: str, dialect: str) -> exp.Table:
    """Build the dialect table reference for the target table.

    Identifiers are always quoted (``exp.to_identifier(name, quoted=True)``) so
    names with spaces or reserved words (e.g. ``Order Details``) survive; the
    renderer picks the dialect quote style (``[dbo].[t]`` on T-SQL, ``"t"`` on
    SQLite). On T-SQL the ``schema`` becomes the table's ``db`` component; on
    SQLite there is no schema namespace, so ``schema`` is accepted and ignored
    (decision 20).

    Args:
        schema: Owning schema name (used on T-SQL, ignored on SQLite).
        table: Table name.
        dialect: Backend dialect, ``"sqlite"`` or ``"tsql"``.

    Returns:
        The :class:`exp.Table` node for the target, ready to render or to feed
        into a larger query.
    """
    this = exp.to_identifier(table, quoted=True)
    if dialect == "tsql":
        return exp.Table(this=this, db=exp.to_identifier(schema, quoted=True))
    return exp.Table(this=this)


def validate_where(
    where: str | None,
    schema: str,
    table: str,
    params: dict[str, Any] | None,
    dialect: str,
) -> tuple[exp.Expression | None, str | None]:
    """Validate an optional ``where`` predicate, fail-closed.

    Reuses the exact gate ``count_records`` applies: the predicate is wrapped in
    a synthetic ``SELECT 1 FROM <schema.table> WHERE <where>`` probe, run
    through :func:`basic_preflight` (empty / multi-statement / parse /
    unbound-``:name`` checks) and then :func:`read_only_violation`, and only on
    success re-extracted from the *re-parsed* statement -- the user's text is
    never echoed back into a later query.

    Args:
        where: Raw predicate text with optional ``:name`` placeholders, or
            ``None``/blank for no filter.
        schema: Owning schema name (for the probe's table reference).
        table: Table name (for the probe's table reference).
        params: Bound values for the predicate's ``:name`` placeholders.
        dialect: Backend dialect, ``"sqlite"`` or ``"tsql"``.

    Returns:
        ``(predicate_ast, None)`` on success, ``(None, error_message)`` on a
        failed check, and ``(None, None)`` when ``where`` is ``None`` or blank.
    """
    if not where or where.strip() == "":
        return (None, None)
    table_ref = build_table_ref(schema, table, dialect)
    probe = f"SELECT 1 FROM {table_ref.sql(dialect=dialect)} WHERE {where}"
    verdict = basic_preflight(probe, params, dialect)
    if verdict is not None:
        return (None, verdict)
    verdict = read_only_violation(probe, dialect)
    if verdict is not None:
        return (None, verdict)
    predicate = sqlglot.parse_one(probe, read=dialect).args["where"].this
    return (predicate, None)


def metadata_sql(dialect: str) -> str:
    """Return the static per-dialect column-metadata query.

    The query injects only bound ``:schema`` / ``:table`` values, so it is a
    constant string rather than an AST build. It returns one row per column
    aliased to the shared ``name`` / ``type`` / ``ordinal`` shape, ordered by
    ordinal position.

    Args:
        dialect: Backend dialect, ``"sqlite"`` or ``"tsql"``.

    Returns:
        The metadata SQL for ``dialect``.
    """
    return _METADATA_SQL[dialect]


def build_count_sql(
    table_ref: exp.Table,
    predicate: exp.Expression | None,
    dialect: str,
) -> str:
    """Build and render the filtered ``SELECT COUNT(*)`` for the target.

    Builds ``SELECT COUNT(*) AS row_count FROM <table_ref>`` as an AST, applying
    ``.where(predicate)`` when a validated predicate is supplied, and renders it
    for ``dialect``. The count short-circuits the pipeline on zero rows and
    feeds the distinct gate (summary § execution pipeline step 3).

    Args:
        table_ref: The target table reference from :func:`build_table_ref`.
        predicate: A validated predicate from :func:`validate_where`, or
            ``None`` for an unfiltered count.
        dialect: Backend dialect, ``"sqlite"`` or ``"tsql"``.

    Returns:
        The rendered count query, dialect-targeted.
    """
    query = exp.select(exp.alias_(exp.Count(this=exp.Star()), "row_count")).from_(
        table_ref
    )
    if predicate is not None:
        query = query.where(predicate)
    return query.sql(dialect=dialect)
