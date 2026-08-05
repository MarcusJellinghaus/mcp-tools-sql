"""SQL generation and data structures for the ``summarize_columns`` tool.

This module hosts the summarize package's data layer. It provides the pure,
dialect-aware type categoriser that every later summarize step dispatches on,
the front of the execution pipeline (the fail-closed ``where`` gate, the dialect
table reference, the static metadata query, and the filtered ``COUNT(*)``), the
shared ``ColumnMeta`` dataclass, and the single-scan scalar-aggregate pass
(``build_scalar_sql`` and its per-category expression builders), and the
duplication-driven value-list SQL builders (``clamp_n`` and
``build_value_list_sql``).

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

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

import sqlglot
from sqlglot import exp

from mcp_tools_sql.utils.sql_placeholders import (
    basic_preflight,
    read_only_violation,
)

Category = Literal["numeric", "temporal", "string", "boolean", "other"]


@dataclass(frozen=True)
class ColumnMeta:
    """Per-column metadata carried through the whole summarize pipeline.

    Built once from the metadata query (declared casing / type / ordinal) and
    the :func:`categorize_type` verdict, then consumed by the scalar-aggregate
    pass (this step), the value-list pass, and both renderers.

    Attributes:
        name: Column name in its declared casing (echoed verbatim in output).
        declared_type: Raw declared/reported type string from the metadata
            query (e.g. ``int``, ``VARCHAR(20)``, ``nvarchar(max)``).
        category: The coarse profiling category dispatched on.
        ordinal: Zero-based-or-one-based ordinal position from the metadata
            query; used for the 50-column cap and triage ordering.
    """

    name: str
    declared_type: str
    category: Category
    ordinal: int


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


# --- Scalar-aggregate pass -------------------------------------------------
#
# One SELECT computes every statistic for every profiled column in a single
# table scan. Each aggregate is aliased ``c{idx}__{stat}`` so the single result
# row maps back per column in the assembler. Category dispatch keeps the SQL
# legal per type: T-SQL rejects MIN/MAX on ``bit`` and any aggregate/DISTINCT on
# LOB types, and silently truncates integer AVG/SUM -- both guarded here.


def _alias(expr: exp.Expression, idx: int, stat: str) -> exp.Alias:
    """Alias an aggregate expression as ``c{idx}__{stat}`` for the result row."""
    return exp.Alias(this=expr, alias=exp.to_identifier(f"c{idx}__{stat}"))


def _cast_float(expr: exp.Expression) -> exp.Cast:
    """Wrap ``expr`` in ``CAST(... AS FLOAT)`` to avoid integer truncation."""
    return exp.Cast(this=expr, to=exp.DataType.build("FLOAT"))


def _count_case(condition: exp.Expression) -> exp.Count:
    """Build ``COUNT(CASE WHEN <condition> THEN 1 END)`` -- a conditional tally."""
    case = exp.Case(ifs=[exp.If(this=condition, true=exp.Literal.number(1))])
    return exp.Count(this=case)


def _non_null(idx: int, ref: exp.Column) -> exp.Alias:
    """``COUNT(c)`` -- non-null tally, emitted for every category."""
    return _alias(exp.Count(this=ref.copy()), idx, "nonnull")


def _distinct(idx: int, ref: exp.Column) -> exp.Alias:
    """``COUNT(DISTINCT c)`` -- distinct tally (never emitted for ``other``)."""
    return _alias(
        exp.Count(this=exp.Distinct(expressions=[ref.copy()])), idx, "distinct"
    )


def _is_integer_type(declared_type: str) -> bool:
    """True for integer-like declared types (``int``/``bigint``/``smallint``…).

    Only these overflow T-SQL's 32-bit ``SUM`` accumulator, so only these get
    the ``CAST(... AS BIGINT)`` guard; decimal/money/float are left uncast.
    """
    return "int" in declared_type.lower()


def _numeric_exprs(
    idx: int,
    col_ref: exp.Column,
    decl_type: str,
    dialect: str,
    include_distinct: bool,
) -> list[exp.Alias]:
    """Aggregates for a numeric column: min/max/mean/sum plus zero/neg tallies."""
    out = [_non_null(idx, col_ref)]
    if include_distinct:
        out.append(_distinct(idx, col_ref))
    out.append(_alias(exp.Min(this=col_ref.copy()), idx, "min"))
    out.append(_alias(exp.Max(this=col_ref.copy()), idx, "max"))
    out.append(_alias(exp.Avg(this=_cast_float(col_ref.copy())), idx, "mean"))
    if dialect == "tsql" and _is_integer_type(decl_type):
        sum_arg: exp.Expression = exp.Cast(
            this=col_ref.copy(), to=exp.DataType.build("BIGINT")
        )
    else:
        sum_arg = col_ref.copy()
    out.append(_alias(exp.Sum(this=sum_arg), idx, "sum"))
    zero = exp.EQ(this=col_ref.copy(), expression=exp.Literal.number(0))
    neg = exp.LT(this=col_ref.copy(), expression=exp.Literal.number(0))
    out.append(_alias(_count_case(zero), idx, "zero"))
    out.append(_alias(_count_case(neg), idx, "neg"))
    return out


def _temporal_exprs(
    idx: int,
    col_ref: exp.Column,
    decl_type: str,
    dialect: str,
    include_distinct: bool,
) -> list[exp.Alias]:
    """Aggregates for a temporal column: non_null, distinct, min, max."""
    out = [_non_null(idx, col_ref)]
    if include_distinct:
        out.append(_distinct(idx, col_ref))
    out.append(_alias(exp.Min(this=col_ref.copy()), idx, "min"))
    out.append(_alias(exp.Max(this=col_ref.copy()), idx, "max"))
    return out


def _string_exprs(
    idx: int,
    col_ref: exp.Column,
    decl_type: str,
    dialect: str,
    include_distinct: bool,
) -> list[exp.Alias]:
    """Aggregates for a string column: value min/max, empty tally, char lengths.

    Value ``MIN``/``MAX`` feed the triage line (strings carry value min/max like
    numeric/temporal); lengths use :class:`exp.Length` (``LENGTH`` on SQLite,
    ``LEN`` on T-SQL) with the average FLOAT-cast to dodge integer truncation.
    """
    out = [_non_null(idx, col_ref)]
    if include_distinct:
        out.append(_distinct(idx, col_ref))
    out.append(_alias(exp.Min(this=col_ref.copy()), idx, "min"))
    out.append(_alias(exp.Max(this=col_ref.copy()), idx, "max"))
    trimmed = exp.Anonymous(
        this="LTRIM",
        expressions=[exp.Anonymous(this="RTRIM", expressions=[col_ref.copy()])],
    )
    empty = exp.EQ(this=trimmed, expression=exp.Literal.string(""))
    out.append(_alias(_count_case(empty), idx, "empty"))
    out.append(_alias(exp.Min(this=exp.Length(this=col_ref.copy())), idx, "len_min"))
    out.append(_alias(exp.Max(this=exp.Length(this=col_ref.copy())), idx, "len_max"))
    out.append(
        _alias(
            exp.Avg(this=_cast_float(exp.Length(this=col_ref.copy()))), idx, "len_avg"
        )
    )
    return out


def _boolean_exprs(
    idx: int,
    col_ref: exp.Column,
    decl_type: str,
    dialect: str,
    include_distinct: bool,
) -> list[exp.Alias]:
    """Aggregates for a boolean column: true/false tallies (no value min/max).

    T-SQL rejects ``MIN``/``MAX`` on ``bit``, so this category never emits them.
    """
    out = [_non_null(idx, col_ref)]
    if include_distinct:
        out.append(_distinct(idx, col_ref))
    true = exp.EQ(this=col_ref.copy(), expression=exp.Literal.number(1))
    false = exp.EQ(this=col_ref.copy(), expression=exp.Literal.number(0))
    out.append(_alias(_count_case(true), idx, "true"))
    out.append(_alias(_count_case(false), idx, "false"))
    return out


def _other_exprs(
    idx: int,
    col_ref: exp.Column,
    decl_type: str,
    dialect: str,
    include_distinct: bool,
) -> list[exp.Alias]:
    """Aggregates for an ``other``/LOB column: non_null plus T-SQL byte sizes.

    LOB types cannot appear in ``DISTINCT``/``GROUP BY``/comparisons, so no
    distinct and no value min/max are emitted (``decl_type`` and
    ``include_distinct`` are accepted only to share the dispatch signature). On
    T-SQL the byte size comes from ``DATALENGTH`` with the average FLOAT-cast;
    SQLite gets rows/nulls only.
    """
    out = [_non_null(idx, col_ref)]
    if dialect == "tsql":
        out.append(
            _alias(
                exp.Min(
                    this=exp.Anonymous(this="DATALENGTH", expressions=[col_ref.copy()])
                ),
                idx,
                "size_min",
            )
        )
        out.append(
            _alias(
                exp.Max(
                    this=exp.Anonymous(this="DATALENGTH", expressions=[col_ref.copy()])
                ),
                idx,
                "size_max",
            )
        )
        out.append(
            _alias(
                exp.Avg(
                    this=_cast_float(
                        exp.Anonymous(this="DATALENGTH", expressions=[col_ref.copy()])
                    )
                ),
                idx,
                "size_avg",
            )
        )
    return out


_ScalarBuilder = Callable[[int, exp.Column, str, str, bool], list[exp.Alias]]

_DISPATCH: dict[Category, _ScalarBuilder] = {
    "numeric": _numeric_exprs,
    "temporal": _temporal_exprs,
    "string": _string_exprs,
    "boolean": _boolean_exprs,
    "other": _other_exprs,
}


def build_scalar_sql(
    columns: list[ColumnMeta],
    table_ref: exp.Table,
    predicate: exp.Expression | None,
    dialect: str,
    *,
    include_distinct: bool,
) -> str:
    """Build the single scalar-aggregate ``SELECT`` for all profiled columns.

    Every statistic for every column is computed in one table scan. Each column
    is dispatched to its per-category builder (keyed on
    :attr:`ColumnMeta.category`), and the aliases are collected into one
    ``SELECT ... FROM <table_ref>`` with ``.where(predicate)`` applied when a
    validated predicate is supplied. The result is a single row whose columns
    are named ``c{idx}__{stat}`` for the assembler to map back per column.

    Args:
        columns: The profiled columns, in the order their ``c{idx}`` indices
            are assigned (index == list position).
        table_ref: The target table reference from :func:`build_table_ref`.
        predicate: A validated predicate from :func:`validate_where`, or
            ``None`` for an unfiltered scan.
        dialect: Backend dialect, ``"sqlite"`` or ``"tsql"``.
        include_distinct: When ``True``, emit ``COUNT(DISTINCT c)`` for every
            non-``other`` column; when ``False``, omit it everywhere.

    Returns:
        The rendered scalar-aggregate query, dialect-targeted, producing one
        result row.
    """
    aliases: list[exp.Alias] = []
    for idx, meta in enumerate(columns):
        col_ref = exp.Column(this=exp.to_identifier(meta.name, quoted=True))
        aliases += _DISPATCH[meta.category](
            idx, col_ref, meta.declared_type, dialect, include_distinct
        )
    query = exp.select(*aliases).from_(table_ref)
    if predicate is not None:
        query = query.where(predicate)
    return query.sql(dialect=dialect)


# --- Value-list pass -------------------------------------------------------
#
# One GROUP BY (deep view only) per profiled column. The *shape* is chosen by
# duplication: a ``top`` list ranks values by frequency (the caller passes this
# when distinct < non_null), a ``sample`` list emits distinct non-null values
# with no freq column (distinct == non_null, where every count is 1). Never
# built for ``other``-category columns -- LOB types cannot be grouped.

VALUE_LIST_HARD_CAP: int = 50
VALUE_LIST_MIN: int = 1


def clamp_n(n: int) -> tuple[int, str]:
    """Clamp the value-list length ``n`` into ``[VALUE_LIST_MIN, HARD_CAP]``.

    The clamp is two-sided and neither bound is cosmetic. Above
    :data:`VALUE_LIST_HARD_CAP` the per-column ``GROUP BY`` cost is bounded;
    below :data:`VALUE_LIST_MIN` an ``n`` of ``0`` would emit an empty list
    under a ``top values:`` header, and a negative ``n`` renders ``TOP -1``
    (which SQL Server rejects outright). A non-empty note is returned in
    *either* clamped direction so the caller can tell the user what was applied.

    Args:
        n: Requested value-list length.

    Returns:
        A ``(clamped, note)`` pair. ``note`` is ``""`` when ``n`` was already in
        range, else a human-readable explanation of the applied bound.
    """
    if n > VALUE_LIST_HARD_CAP:
        note = (
            f"Requested n={n} exceeds the maximum {VALUE_LIST_HARD_CAP}; "
            f"using {VALUE_LIST_HARD_CAP}."
        )
        return (VALUE_LIST_HARD_CAP, note)
    if n < VALUE_LIST_MIN:
        note = (
            f"Requested n={n} is below the minimum {VALUE_LIST_MIN}; "
            f"using {VALUE_LIST_MIN}."
        )
        return (VALUE_LIST_MIN, note)
    return (n, "")


def build_value_list_sql(
    col: ColumnMeta,
    table_ref: exp.Table,
    predicate: exp.Expression | None,
    n: int,
    dialect: str,
    *,
    kind: Literal["top", "sample"],
) -> str:
    """Build a single-column value-list query whose shape is set by ``kind``.

    The caller (step 7) picks ``kind`` from the column's scalar stats:
    ``"top"`` when the column has duplicates (``distinct < non_null``) and
    ``"sample"`` when every value is unique (``distinct == non_null``), where a
    frequency column would be uninformative. Never called for ``other``-category
    columns: LOB types cannot appear in ``GROUP BY`` / ``DISTINCT``.

    - ``kind == "top"``: ``SELECT c AS value, COUNT(*) AS freq ... GROUP BY c
      ORDER BY COUNT(*) DESC, c ASC LIMIT n``. ``NULL`` ranks as an ordinary
      group (no special handling); the ``c ASC`` tiebreak makes the ordering
      total, hence deterministic.
    - ``kind == "sample"``: ``SELECT DISTINCT c AS value ... WHERE c IS NOT NULL
      ORDER BY c ASC LIMIT n`` -- no ``freq`` column, and ``NULL`` is excluded.
      The sample header reads ``N of D distinct`` with ``D`` counting non-null
      distinct values, so a returned ``NULL`` row would make ``N`` exceed ``D``.

    The null test is built as ``exp.Is(this=ref, expression=exp.Null(),
    negate=True)`` so it renders the literal ``c IS NOT NULL`` on both dialects;
    ``ref.is_(exp.null()).not_()`` would instead render ``NOT c IS NULL``. The
    limit is applied via sqlglot ``.limit(n)`` so the renderer emits ``LIMIT n``
    (SQLite) / ``TOP n`` (T-SQL) automatically.

    Args:
        col: The profiled column (declared casing quoted into the query).
        table_ref: The target table reference from :func:`build_table_ref`.
        predicate: A validated predicate from :func:`validate_where`, AND-
            combined into the ``WHERE`` clause, or ``None`` for no filter.
        n: Value-list length; the caller should pass a :func:`clamp_n`-clamped
            value so the emitted ``LIMIT``/``TOP`` stays in ``[1, 50]``.
        dialect: Backend dialect, ``"sqlite"`` or ``"tsql"``.
        kind: ``"top"`` for a frequency-ranked list, ``"sample"`` for a distinct
            non-null sample.

    Returns:
        The rendered value-list query, dialect-targeted, returning
        ``(value, freq)`` rows for ``"top"`` and ``(value,)`` rows for
        ``"sample"``.
    """
    ref = exp.column(exp.to_identifier(col.name, quoted=True))
    if kind == "top":
        query = exp.select(
            exp.alias_(ref.copy(), "value"),
            exp.alias_(exp.Count(this=exp.Star()), "freq"),
        ).from_(table_ref.copy())
        query = query.group_by(ref.copy()).order_by(
            exp.Count(this=exp.Star()).desc(), ref.asc()
        )
    else:
        query = (
            exp.select(exp.alias_(ref.copy(), "value"))
            .distinct()
            .from_(table_ref.copy())
            .order_by(ref.asc())
        )
        query = query.where(exp.Is(this=ref.copy(), expression=exp.Null(), negate=True))
    if predicate is not None:
        query = query.where(predicate)
    return query.limit(n).sql(dialect=dialect)
