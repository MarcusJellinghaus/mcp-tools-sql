"""Source resolution for the ``summarize_columns`` tool.

This module owns everything that turns a profiling *source* -- a persisted
table or a user-supplied SELECT -- into the single :class:`Source` value object
the rest of the pipeline profiles. Three concerns live here:

:func:`build_table_source`
    Resolves the ``schema=``/``table=`` path from the catalog: the metadata
    query, the ``ColumnMeta`` assembly, and the table reference, or the
    not-found message when the table has no columns. Nothing about this path
    changed when it moved here; it simply produces a :class:`Source` like the
    query path does.

:func:`validate_source`
    Applies the shared security gates (``basic_preflight`` ->
    ``read_only_violation`` -> a narrower ``Select``/``Union`` root allow-list
    -> the T-SQL leading-CTE reject), handles the source's own ``ORDER BY`` /
    row limit, and returns the query as an aliased derived-table reference
    (``(<source>) AS src``) built from the **re-parsed** statement -- the user's
    raw text is never concatenated into a later query.

:func:`probe_columns`
    Resolves that reference's output columns from a :data:`PROBE_ROWS`-row
    value probe: ordered names from the backend's read-only describe method
    (which, unlike the dict form, preserves duplicate column names) and a
    declared *type string* inferred from the first non-``NULL`` value of each
    column. Emitting a declared-type string rather than a category keeps
    ``categorize_type`` (and the T-SQL ``BIGINT`` SUM guard that reads the same
    string) the single source of truth for categories.

The value -> type mapping is dialect-dependent: a probed ``str`` types as
``nvarchar`` on T-SQL, never ``TEXT``, because ``categorize_type``'s LOB guard
would otherwise sweep every string column into ``other``. On SQLite the probe
cannot see declared types at all -- ``backends/sqlite.py`` connects without
``detect_types``, so DATE/DATETIME columns arrive as ``str`` and BOOLEAN
columns as ``int``. That divergence from the table path is deliberate and
surfaced through :data:`SQLITE_PROBE_TYPE_LIMITS_NOTE` rather than worked
around.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

import sqlglot
from sqlglot import exp

from mcp_tools_sql.summarize.render import table_not_found_message
from mcp_tools_sql.summarize.sql import (
    ColumnMeta,
    SourceRef,
    build_table_ref,
    categorize_type,
    metadata_sql,
)
from mcp_tools_sql.utils.sql_placeholders import (
    LEADING_CTE_REJECTION,
    basic_preflight,
    has_leading_cte,
    read_only_violation,
)

if TYPE_CHECKING:
    from mcp_tools_sql.backends.base import DatabaseBackend

# Rows sampled by the value probe. Small on purpose: the probe only has to see
# one non-NULL value per column to decide its type, and it runs before the
# (potentially expensive) profiling passes.
PROBE_ROWS: int = 5

# Alias given to the derived table wrapping the user's source. Mirrors
# ``count_records``' ``AS count_sub``.
_SOURCE_ALIAS: str = "src"

# Declared type recorded when no sampled value could decide one.
UNKNOWN_TYPE: str = "unknown"

# Root allow-list rejection. Narrower than ``read_only_violation``, which also
# accepts ``VALUES`` as a countable root: a profiling source must be a query.
ROOT_REJECTION: str = (
    "The source must be a SELECT (or UNION of SELECTs) query. "
    "Wrap other read-only forms in a SELECT."
)

# Call-level notes. Plain footer sentences, printed in the order returned.
ORDER_BY_STRIPPED_NOTE: str = (
    "ORDER BY was removed from the source: without a row limit it does not "
    "change which rows are profiled, and SQL Server rejects it inside a "
    "derived table."
)

ROW_LIMITED_NOTE: str = (
    "The source is row-limited (TOP/LIMIT/OFFSET), so the statistics describe "
    "only the rows it returns, not the full result set."
)

TYPES_PROBED_NOTE: str = (
    "Column types were inferred from the first few sampled values, not read "
    "from a catalog: a column whose sampled values are all NULL reports an "
    "unknown type."
)

SQLITE_PROBE_TYPE_LIMITS_NOTE: str = (
    "On SQLite a sampled source cannot see declared types: DATE/DATETIME "
    "columns profile as string (length stats, not date bounds) and BOOLEAN "
    "columns as numeric. Profile the underlying table with schema=/table= for "
    "catalog types."
)

# Inline mark on a column whose type no sampled value could decide.
UNKNOWN_TYPE_NOTE: str = "type not determined: all sampled values were NULL"

# Rejection for output names the pipeline cannot address per column: the
# scalar pass and every value list quote the name, so duplicates (SQLite
# repeats a joined name verbatim) and unnamed expression columns are ambiguous.
_NAME_REJECTION: str = (
    "The source query has duplicate or unnamed output columns: {names}. "
    "Alias each output column (e.g. SELECT a.id AS a_id, b.id AS b_id) so "
    "every name is unique."
)

# Placeholder printed for an empty/missing name in the rejection message.
_UNNAMED_LABEL: str = "(unnamed)"


@dataclass(frozen=True)
class Source:
    """A resolved profiling source: what to profile and what to say about it.

    Built once per call -- by :func:`build_table_source` for the
    ``schema=``/``table=`` path, by the query path for ``sql=`` -- and consumed
    by the rest of the pipeline, which never branches on which path produced
    it.

    Attributes:
        ref: What every query builder does ``.from_()`` on: an ``exp.Table``
            for a persisted table, an aliased ``exp.Subquery`` for a query.
        label: The source descriptor used in status messages
            (``dbo.orders`` / ``main.orders`` -- always ``schema.table``, on
            both dialects, because the messages print the schema on both), or
            ``None`` for a query source. It is *not* a SQL reference:
            :func:`build_table_ref` keeps its own dialect rule.
        metas: The resolved per-column metadata, in output order.
        notes: Call-level footer sentences, in print order. Empty for a table
            source, whose types come from the catalog with nothing to qualify.
        types_probed: Whether the types in ``metas`` were inferred from sampled
            values rather than read from a catalog.
    """

    ref: SourceRef
    label: str | None
    metas: list[ColumnMeta]
    notes: list[str]
    types_probed: bool


def build_table_source(
    backend: DatabaseBackend, schema: str, table: str, dialect: str
) -> Source | str:
    """Resolve a persisted table into a :class:`Source` from the catalog.

    Runs the per-dialect metadata query with bound ``:schema`` / ``:table``
    values and assembles one :class:`ColumnMeta` per returned row, carrying the
    catalog's declared casing, type and ordinal through unchanged. A table with
    no metadata rows does not exist (or has no columns), which is a message to
    the caller rather than an empty profile.

    Args:
        backend: The resolved backend to run the read-only metadata query on.
        schema: Owning schema (bound into the metadata query and the label).
        table: Table name (bound into the metadata query and the label).
        dialect: Backend dialect, ``sqlite`` or ``tsql``.

    Returns:
        The resolved :class:`Source`, or the ``table_not_found`` message string
        to return to the caller when the metadata query came back empty.
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
    return Source(
        ref=build_table_ref(schema, table, dialect),
        label=f"{schema}.{table}",
        metas=metas,
        notes=[],
        types_probed=False,
    )


def validate_source(
    sql: str, params: dict[str, Any] | None, dialect: str
) -> tuple[exp.Subquery | None, list[str], str | None]:
    """Validate a user SELECT and return it as an aliased derived table.

    Gates, in order: :func:`basic_preflight` (empty / parse / multi-statement /
    unbound ``:name``), :func:`read_only_violation`, a narrower root allow-list
    accepting only ``Select`` / ``Union`` (``read_only_violation`` also passes
    ``VALUES``), and -- on T-SQL only -- :func:`has_leading_cte`, because SQL
    Server cannot wrap a CTE query in a derived table.

    A statement-level ``ORDER BY`` is stripped when the source carries no row
    limit: it cannot change *which* rows are profiled there, and T-SQL rejects
    it inside a derived table (error 1033). With a ``TOP`` / ``LIMIT`` /
    ``OFFSET`` present the clause decides which rows survive, so it is kept and
    the row-limited note is returned instead.

    Args:
        sql: The user's read-only SELECT, with optional ``:name`` placeholders.
        params: Bound values for the source's ``:name`` placeholders.
        dialect: Backend dialect, ``"sqlite"`` or ``"tsql"``.

    Returns:
        ``(ref, notes, None)`` on success, where ``ref`` is the source parsed,
        re-rendered and wrapped as ``(<source>) AS src`` and ``notes`` are
        call-level footer sentences in print order; ``(None, [], error)`` when
        any gate rejects the source. Exactly one of ``ref`` / ``error`` is set.
    """
    verdict = basic_preflight(sql, params, dialect)
    if verdict is None:
        verdict = read_only_violation(sql, dialect)
    if verdict is not None:
        return (None, [], verdict)
    parsed = sqlglot.parse_one(sql, read=dialect)
    if not isinstance(parsed, (exp.Select, exp.Union)):
        return (None, [], ROOT_REJECTION)
    if dialect == "tsql" and has_leading_cte(sql, dialect):
        return (None, [], LEADING_CTE_REJECTION)

    notes: list[str] = []
    # T-SQL ``TOP``, SQLite ``LIMIT`` and ``OFFSET ... FETCH`` all land in the
    # statement's ``limit`` / ``offset`` args, so one check covers all three.
    row_limited = bool(parsed.args.get("limit") or parsed.args.get("offset"))
    if not row_limited and parsed.args.get("order"):
        parsed.set("order", None)
        notes.append(ORDER_BY_STRIPPED_NOTE)
    if row_limited:
        notes.append(ROW_LIMITED_NOTE)

    ref = exp.Subquery(
        this=parsed, alias=exp.TableAlias(this=exp.to_identifier(_SOURCE_ALIAS))
    )
    return (ref, notes, None)


def _declared_type_for(value: Any, dialect: str) -> str:
    """Map a sampled Python value to a declared-type string for ``dialect``.

    Order is load-bearing: ``bool`` before ``int`` and ``datetime`` before
    ``date``, since each is a subclass of the next. The fallback row is
    dialect-dependent because :func:`categorize_type` is -- ``TEXT`` categorises
    as ``string`` on SQLite but hits the T-SQL LOB guard and would categorise as
    ``other``, so T-SQL gets ``nvarchar`` (which carries the ``char`` token and
    categorises as ``string`` on both dialects).

    Args:
        value: A non-``NULL`` sampled value from the probe.
        dialect: Backend dialect, ``"sqlite"`` or ``"tsql"``.

    Returns:
        A declared-type string suitable for :func:`categorize_type` and for
        display beside the column name.
    """
    if isinstance(value, bool):
        return "bit"
    if isinstance(value, int):
        return "INTEGER"
    if isinstance(value, float):
        return "REAL"
    if isinstance(value, Decimal):
        return "decimal"
    # ``datetime`` before ``date``: the former subclasses the latter. Note the
    # T-SQL ``timestamp`` type is a row-version stamp, so never use that name.
    if isinstance(value, datetime):
        return "datetime"
    if isinstance(value, date):
        return "date"
    if isinstance(value, (bytes, bytearray)):
        return "BLOB"
    return "TEXT" if dialect == "sqlite" else "nvarchar"


def _first_non_null(rows: list[tuple[Any, ...]], idx: int) -> Any:
    """Return the first non-``NULL`` value in column ``idx``, or ``None``.

    Args:
        rows: The probe's sampled rows.
        idx: The column's zero-based output ordinal.

    Returns:
        The first non-``NULL`` sampled value, or ``None`` when the column is
        all-``NULL`` across the sample (or no rows came back).
    """
    for row in rows:
        if idx < len(row) and row[idx] is not None:
            return row[idx]
    return None


def _name_rejection(names: list[str]) -> str | None:
    """Reject output names the per-column pipeline cannot address.

    A name is bad when it is empty/``None`` (an unnamed expression column),
    when it collides case-insensitively with an earlier name (SQLite repeats a
    joined column's name verbatim), or when it carries a ``":"`` disambiguation
    suffix.

    Args:
        names: The probe's ordered output column names.

    Returns:
        A rejection message naming the offending columns and the aliasing
        recovery, or ``None`` when every name is usable.
    """
    bad: list[str] = []
    seen: set[str] = set()
    for name in names:
        if not name or not name.strip():
            bad.append(_UNNAMED_LABEL)
            continue
        if ":" in name or name.lower() in seen:
            bad.append(name)
        seen.add(name.lower())
    if not bad:
        return None
    unique = list(dict.fromkeys(bad))
    return _NAME_REJECTION.format(names=", ".join(unique))


def probe_columns(
    backend: DatabaseBackend,
    ref: exp.Subquery,
    params: dict[str, Any] | None,
    dialect: str,
) -> tuple[list[ColumnMeta] | None, str | None]:
    """Resolve a source's output columns from a few-row value probe.

    Runs ``SELECT * FROM <ref> LIMIT PROBE_ROWS`` (``TOP`` on T-SQL), built from
    the reference rather than by string concatenation and passed ``params`` so
    the source's own ``:name`` placeholders bind. Names and ordinals come from
    the result's projection; the declared type of each column is inferred from
    its first non-``NULL`` sampled value. A column with no such value resolves
    :data:`UNKNOWN_TYPE`, is profiled as ``string`` (the only category whose
    aggregates are legal for any value), and carries
    :data:`UNKNOWN_TYPE_NOTE` as its inline mark.

    Args:
        backend: The resolved backend to run the read-only probe on.
        ref: The validated source reference from :func:`validate_source`.
        params: Bound values for the source's ``:name`` placeholders.
        dialect: Backend dialect, ``"sqlite"`` or ``"tsql"``.

    Returns:
        ``(metas, None)`` with one :class:`ColumnMeta` per output column
        ordered by (and carrying) its zero-based output ordinal, or
        ``(None, error_message)`` when the projection has duplicate or unnamed
        columns.
    """
    probe_sql = (
        exp.select(exp.Star()).from_(ref.copy()).limit(PROBE_ROWS).sql(dialect=dialect)
    )
    names, rows = backend.execute_readonly_query_with_columns(probe_sql, params)
    rejection = _name_rejection(names)
    if rejection is not None:
        return (None, rejection)
    metas: list[ColumnMeta] = []
    for idx, name in enumerate(names):
        value = _first_non_null(rows, idx)
        if value is None:
            metas.append(
                ColumnMeta(
                    name=name,
                    declared_type=UNKNOWN_TYPE,
                    category="string",
                    ordinal=idx,
                    note=UNKNOWN_TYPE_NOTE,
                )
            )
            continue
        declared_type = _declared_type_for(value, dialect)
        metas.append(
            ColumnMeta(
                name=name,
                declared_type=declared_type,
                category=categorize_type(declared_type, dialect),
                ordinal=idx,
            )
        )
    return (metas, None)
