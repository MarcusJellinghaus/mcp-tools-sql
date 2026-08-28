"""AST-aware extraction and translation of ``:name`` SQL placeholders.

Built on :mod:`sqlglot`: the SQL is parsed into an AST and ``:name``
placeholders are recognised as :class:`sqlglot.exp.Placeholder` nodes.
Because they are real AST nodes, occurrences inside quoted strings
(``'…'``, ``"…"``) and comments (``-- …``, ``/* … */``) are never treated
as placeholders -- sqlglot classifies those as literals/comments instead.

Exposes :func:`extract_param_names`, :func:`translate_named_to_qmark`, and
:func:`substitute_named_with_literals`. The last is used by the MSSQL
``explain`` path, where pyodbc's prepared-statement protocol does not
return result rows under ``SET SHOWPLAN_TEXT ON``.

It also hosts the shared, dialect-aware analysis helpers reused across the
SQL-consuming tools: :func:`count_statements`,
:func:`first_statement_kind`, :func:`has_leading_cte` (with its shared
:data:`LEADING_CTE_REJECTION` message), and the shared :func:`basic_preflight`.
sqlglot's :class:`~sqlglot.errors.ParseError` is re-exported so callers can
implement the fail-closed parse contract without importing sqlglot directly.

Note:
    Rendered SQL is produced by sqlglot's generator, not echoed verbatim
    from the input. Whitespace, keyword casing, and comments may be
    normalised -- this is a deliberate consequence of the AST migration.
"""

from __future__ import annotations

import math
from datetime import date, datetime
from decimal import Decimal
from typing import Any, cast

import sqlglot
from sqlglot import exp
from sqlglot.errors import ParseError

__all__ = [
    "LEADING_CTE_REJECTION",
    "ParseError",
    "basic_preflight",
    "build_count_query",
    "count_statements",
    "extract_param_names",
    "first_statement_kind",
    "has_leading_cte",
    "read_only_violation",
    "substitute_named_with_literals",
    "translate_named_to_qmark",
]

# Session-control statements rejected by callers that disallow session state.
_SESSION_STATEMENT_KEYWORDS = frozenset({"USE", "SET", "DECLARE"})

# Data-modifying / DDL node types rejected anywhere in the AST by the
# read-only gate. ``find`` walks the whole tree, so a write node buried in a
# CTE body (e.g. ``WITH x AS (DELETE ...) ...``) is still caught.
_WRITE_NODES = (
    exp.Insert,
    exp.Update,
    exp.Delete,
    exp.Merge,
    exp.Create,
    exp.Drop,
    exp.Alter,
    exp.TruncateTable,
)

# STRICT, fail-closed allow-list of read-only root node types. Confirmed
# empirically against sqlglot for both the ``sqlite`` and ``tsql`` dialects:
#   ``SELECT``                -> exp.Select
#   ``WITH ... SELECT``       -> exp.Select (carries a ``with`` arg)
#   ``SELECT ... INTO`` (tsql)-> exp.Select (carries an ``into`` arg; rejected
#                                separately below)
#   ``... UNION ...``         -> exp.Union
#   ``VALUES (...), (...)``   -> exp.Values
# Any root NOT in this tuple is rejected -- never widen this to a catch-all.
_READONLY_ROOTS = (exp.Select, exp.Union, exp.Values)

# Shared rejection message for leading-CTE (``WITH``) queries under T-SQL.
# Both consumers -- ``count_records`` and ``summarize_columns`` -- wrap the
# source in a derived table (``AS count_sub`` / ``AS src``), which SQL Server
# does not allow for a CTE query, so the message names that shared cause.
LEADING_CTE_REJECTION: str = (
    "CTE (WITH) queries aren't supported on SQL Server — "
    "the query can't be wrapped in a derived table."
)


def _statements(sql: str, dialect: str | None = None) -> list[exp.Expression]:
    """Parse ``sql`` into a list of top-level statement expressions.

    Args:
        sql: The SQL text to parse.
        dialect: The sqlglot dialect to parse under, or ``None`` for the
            dialect-neutral default parser.

    Returns:
        The non-empty parsed statements; trailing/empty fragments that
        sqlglot returns as ``None`` are dropped.
    """
    # ``parse`` with an explicit ``read`` is typed as returning the ``Expr``
    # trait rather than the concrete ``Expression``; they are the same objects
    # at runtime, so narrow back to ``Expression`` for downstream helpers.
    parsed = cast("list[exp.Expression | None]", sqlglot.parse(sql, read=dialect))
    return [stmt for stmt in parsed if stmt is not None]


def _named_placeholders(expr: exp.Expression) -> list[exp.Placeholder]:
    """Collect named ``:name`` placeholder nodes from ``expr`` in render order.

    Anonymous ``?`` placeholders are excluded. They carry no ``this`` arg, so
    they are filtered on ``text("this")`` rather than ``name``: sqlglot's
    :attr:`Placeholder.name` falls back to ``"?"`` for them (which is truthy),
    whereas ``text("this")`` is the empty string. ``find_all`` performs a
    depth-first pre-order walk, which matches the left-to-right order in which
    the generator renders the placeholders.

    Returns:
        Named placeholder nodes, in positional order.
    """
    return [node for node in expr.find_all(exp.Placeholder) if node.text("this")]


def extract_param_names(sql: str, dialect: str | None = None) -> set[str]:
    """Return the set of ``:name`` placeholder names in ``sql``.

    Args:
        sql: The SQL text to inspect.
        dialect: The sqlglot dialect to parse under, or ``None`` for the
            dialect-neutral default parser. Passing the backend dialect
            lets dialect-specific statements (e.g. T-SQL ``DECLARE``) parse
            without raising.

    Returns:
        Unordered, deduplicated set of placeholder names (without the
        leading ``:``). Placeholders inside quoted strings or comments
        are ignored because they are not placeholder nodes in the AST.
    """
    return {
        ph.name
        for stmt in _statements(sql, dialect)
        for ph in _named_placeholders(stmt)
    }


def translate_named_to_qmark(
    sql: str, dialect: str | None = None
) -> tuple[str, list[str]]:
    """Translate ``:name`` placeholders to ``?`` markers.

    Each named placeholder node is replaced by an anonymous placeholder and
    the statements are re-rendered through sqlglot.

    Args:
        sql: SQL with ``:name`` placeholders.
        dialect: The sqlglot dialect to parse and render under, or ``None``
            for the dialect-neutral default. Passing the backend dialect
            (e.g. ``"tsql"``) preserves dialect-specific quoting such as
            bracket-quoted T-SQL identifiers (``[id]``), which the neutral
            renderer would otherwise corrupt.

    Returns:
        Tuple ``(translated_sql, ordered_names)`` where every ``:name``
        placeholder has been rewritten as ``?`` and ``ordered_names[i]``
        is the name of the *i*-th ``?`` in ``translated_sql``. Order and
        duplicates are preserved.
    """
    names: list[str] = []
    rendered: list[str] = []
    for stmt in _statements(sql, dialect):
        for ph in _named_placeholders(stmt):
            names.append(ph.name)
            ph.replace(exp.Placeholder())
        rendered.append(stmt.sql(dialect=dialect))
    return "; ".join(rendered), names


def _sql_literal(value: Any) -> str:
    """Render a Python value as a SQL literal.

    Args:
        value: Python value to render as a SQL literal.

    Returns:
        SQL-literal text suitable for direct inclusion in a statement.

    Raises:
        ValueError: If ``value`` is a non-finite float (NaN or infinity);
            MSSQL has no literal form for these.
        TypeError: If the value type has no supported literal rendering.
    """
    if value is None:
        return "NULL"
    # bool before int: bool is a subclass of int.
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if not math.isfinite(value):
            msg = f"Cannot render non-finite float as SQL literal: {value!r}"
            raise ValueError(msg)
        return repr(value)
    if isinstance(value, str):
        escaped = value.replace("'", "''")
        return f"'{escaped}'"
    # datetime before date: datetime is a subclass of date.
    if isinstance(value, datetime):
        return f"'{value.isoformat(sep=' ')}'"
    if isinstance(value, date):
        return f"'{value.isoformat()}'"
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, bytes):
        return "0x" + value.hex()
    msg = f"Unsupported SQL literal type: {type(value).__name__}"
    raise TypeError(msg)


def substitute_named_with_literals(
    sql: str, params: dict[str, Any], dialect: str | None = None
) -> str:
    """Replace ``:name`` placeholders with rendered SQL literals.

    Used by the MSSQL ``explain`` path: pyodbc's prepared-statement
    protocol does not return result rows under ``SET SHOWPLAN_TEXT ON``,
    so the parameterised form must be expanded to literals before the
    showplan call.

    Each named placeholder node is replaced by the parsed literal of
    ``_sql_literal(params[name])`` and the statements are re-rendered
    through sqlglot. A missing placeholder key raises ``KeyError`` (via the
    ``params`` lookup); unsupported value types or non-finite floats
    propagate ``TypeError`` / ``ValueError`` from :func:`_sql_literal`.

    Args:
        sql: SQL with ``:name`` placeholders.
        params: Mapping of placeholder name to Python value.
        dialect: The sqlglot dialect to parse and render under, or ``None``
            for the dialect-neutral default. Passing the backend dialect
            (e.g. ``"tsql"``) preserves dialect-specific quoting such as
            bracket-quoted T-SQL identifiers (``[id]``), which the neutral
            renderer would otherwise corrupt.

    Returns:
        SQL with each placeholder replaced by ``_sql_literal(params[name])``.
    """
    rendered: list[str] = []
    for stmt in _statements(sql, dialect):
        for ph in _named_placeholders(stmt):
            literal = sqlglot.parse_one(_sql_literal(params[ph.name]))
            ph.replace(literal)
        rendered.append(stmt.sql(dialect=dialect))
    return "; ".join(rendered)


def count_statements(sql: str, dialect: str) -> int:
    """Return the number of non-empty parsed statements in ``sql``.

    Args:
        sql: The SQL text to parse.
        dialect: The sqlglot dialect to parse under.

    Returns:
        The count of top-level statements, ignoring empty fragments such as
        trailing semicolons.
    """
    return len(_statements(sql, dialect))


def first_statement_kind(sql: str, dialect: str) -> str | None:
    """Return the session-control kind of the first statement, or ``None``.

    Recognises ``USE`` / ``SET`` / ``DECLARE`` statements regardless of
    whether sqlglot models them as dedicated nodes (:class:`exp.Use`,
    :class:`exp.Set`, :class:`exp.Declare`) or as a generic
    :class:`exp.Command` (the form some dialects emit, e.g. ``SET`` under
    the ``sqlite`` dialect).

    Args:
        sql: The SQL text to parse.
        dialect: The sqlglot dialect to parse under.

    Returns:
        ``"USE"``, ``"SET"``, or ``"DECLARE"`` when the first statement is
        that session-control statement; ``None`` otherwise.
    """
    statements = _statements(sql, dialect)
    root = statements[0] if statements else None
    if root is None:
        return None
    if isinstance(root, exp.Use):
        return "USE"
    if isinstance(root, exp.Set):
        return "SET"
    if isinstance(root, exp.Declare):
        return "DECLARE"
    if isinstance(root, exp.Command):
        command = root.name.upper()
        if command in _SESSION_STATEMENT_KEYWORDS:
            return command
    return None


def basic_preflight(
    sql: str, params: dict[str, Any] | None, dialect: str
) -> str | None:
    """Run the shared, dialect-aware pre-flight checks on ``sql``.

    Applies the checks common to every SQL-consuming tool: empty SQL, the
    fail-closed parse contract, multiple statements, and missing ``:name``
    parameters. It deliberately does **not** apply any session-control
    (``USE``/``SET``/``DECLARE``) check -- callers that need that layer it on
    top (see :func:`mcp_tools_sql.validation_tools._preflight`).

    Args:
        sql: The SQL text to validate.
        params: Bound values for ``:name`` placeholders, or ``None``.
        dialect: The sqlglot dialect to parse under.

    Returns:
        An error verdict string when a check fails, or ``None`` when all
        checks pass.
    """
    if sql.strip() == "":
        return "Invalid SQL. ValidationError: empty SQL"
    try:
        statement_count = count_statements(sql, dialect)
    except ParseError as exc:
        return f"Invalid SQL. ParseError (SQL parsed as {dialect}): {exc}"
    if statement_count > 1:
        return "Invalid SQL. ValidationError: multiple statements not supported"
    missing = extract_param_names(sql, dialect) - (params or {}).keys()
    if missing:
        return f"Invalid parameters. ValidationError: missing parameter: {min(missing)}"
    return None


def read_only_violation(sql: str, dialect: str) -> str | None:
    """Return a rejection message if ``sql`` is not provably read-only.

    This is the primary security gate for :func:`count_records`. It positively
    proves a statement is read-only by AST inspection rather than blocklisting
    keywords:

    1. **No write nodes anywhere.** ``Insert``/``Update``/``Delete``/``Merge``/
       ``Create``/``Drop``/``Alter``/``TruncateTable`` are rejected wherever they
       appear in the tree -- including inside a CTE body -- because ``find``
       walks the whole AST.
    2. **No ``SELECT ... INTO``.** Under T-SQL this materialises a new table, so
       any ``Select`` carrying an ``into`` arg is rejected.
    3. **Fail-closed root allow-list.** The root node must itself be one of
       :data:`_READONLY_ROOTS`; any other (parseable) root -- e.g. ``PRAGMA``,
       ``EXPLAIN`` -- is rejected.

    Args:
        sql: The single SQL statement to inspect.
        dialect: The sqlglot dialect to parse under (``"sqlite"`` or ``"tsql"``).

    Returns:
        A concise rejection message (returned verbatim by the tool) when the
        statement is not provably read-only, or ``None`` when it is.
    """
    root = sqlglot.parse_one(sql, read=dialect)
    write_node = root.find(*_WRITE_NODES)
    if write_node is not None:
        kind = type(write_node).__name__.upper()
        return f"Not read-only. {kind} statements are not permitted."
    if any(select.args.get("into") for select in root.find_all(exp.Select)):
        return "Not read-only. SELECT ... INTO is not permitted."
    if not isinstance(root, _READONLY_ROOTS):
        return "Not read-only. Only SELECT/WITH/VALUES queries can be counted."
    return None


def has_leading_cte(sql: str, dialect: str) -> bool:
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


def build_count_query(sql: str, dialect: str) -> str:
    """Wrap ``sql`` in a ``SELECT COUNT(*)`` and render it for ``dialect``.

    Builds the AST ``SELECT COUNT(*) AS row_count FROM (<sql>) AS count_sub``
    and renders it through sqlglot's generator targeting ``dialect``. Any
    ``:name`` placeholders in ``sql`` survive into the rendered wrapper as
    bindable placeholders.

    The inner query's statement-level ``ORDER BY`` is dropped before wrapping:
    ``COUNT(*)`` is order-independent, so removing it is semantically free and
    avoids T-SQL error 1033 (``ORDER BY`` invalid in a derived table unless
    accompanied by ``TOP``/``OFFSET``/``FOR XML``).

    Args:
        sql: The (already read-only-verified) SQL to wrap.
        dialect: The sqlglot dialect to parse and render under.

    Returns:
        The rendered count query, dialect-targeted.
    """
    inner = sqlglot.parse_one(sql, read=dialect)
    # Drop the statement-level ORDER BY; it is meaningless once wrapped in
    # COUNT(*) and illegal inside a T-SQL derived table (error 1033).
    inner.set("order", None)
    # Build the derived table directly (rather than ``inner.subquery(...)``)
    # so every read-only root renders uniformly: ``subquery`` lives on
    # ``exp.Query`` (Select/Union) but not on ``exp.Values``, which the gate
    # also accepts as a root.
    count_sub = exp.Subquery(
        this=inner, alias=exp.TableAlias(this=exp.to_identifier("count_sub"))
    )
    wrapped = exp.select(exp.alias_(exp.Count(this=exp.Star()), "row_count")).from_(
        count_sub
    )
    return wrapped.sql(dialect=dialect)
