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

Note:
    Rendered SQL is produced by sqlglot's generator, not echoed verbatim
    from the input. Whitespace, keyword casing, and comments may be
    normalised -- this is a deliberate consequence of the AST migration.
"""

from __future__ import annotations

import math
from datetime import date, datetime
from decimal import Decimal
from typing import Any

import sqlglot
from sqlglot import exp


def _statements(sql: str) -> list[exp.Expression]:
    """Parse ``sql`` into a list of top-level statement expressions.

    Returns:
        The non-empty parsed statements; trailing/empty fragments that
        sqlglot returns as ``None`` are dropped.
    """
    return [stmt for stmt in sqlglot.parse(sql) if stmt is not None]


def _named_placeholders(expr: exp.Expression) -> list[exp.Placeholder]:
    """Collect named ``:name`` placeholder nodes from ``expr`` in render order.

    Anonymous ``?`` placeholders (whose ``name`` is empty) are excluded.
    ``find_all`` performs a depth-first pre-order walk, which matches the
    left-to-right order in which the generator renders the placeholders.

    Returns:
        Named placeholder nodes, in positional order.
    """
    return [node for node in expr.find_all(exp.Placeholder) if node.name]


def extract_param_names(sql: str) -> set[str]:
    """Return the set of ``:name`` placeholder names in ``sql``.

    Returns:
        Unordered, deduplicated set of placeholder names (without the
        leading ``:``). Placeholders inside quoted strings or comments
        are ignored because they are not placeholder nodes in the AST.
    """
    return {ph.name for stmt in _statements(sql) for ph in _named_placeholders(stmt)}


def translate_named_to_qmark(sql: str) -> tuple[str, list[str]]:
    """Translate ``:name`` placeholders to ``?`` markers.

    Each named placeholder node is replaced by an anonymous placeholder and
    the statements are re-rendered through sqlglot.

    Returns:
        Tuple ``(translated_sql, ordered_names)`` where every ``:name``
        placeholder has been rewritten as ``?`` and ``ordered_names[i]``
        is the name of the *i*-th ``?`` in ``translated_sql``. Order and
        duplicates are preserved.
    """
    names: list[str] = []
    rendered: list[str] = []
    for stmt in _statements(sql):
        for ph in _named_placeholders(stmt):
            names.append(ph.name)
            ph.replace(exp.Placeholder())
        rendered.append(stmt.sql())
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


def substitute_named_with_literals(sql: str, params: dict[str, Any]) -> str:
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

    Returns:
        SQL with each placeholder replaced by ``_sql_literal(params[name])``.
    """
    rendered: list[str] = []
    for stmt in _statements(sql):
        for ph in _named_placeholders(stmt):
            literal = sqlglot.parse_one(_sql_literal(params[ph.name]))
            ph.replace(literal)
        rendered.append(stmt.sql())
    return "; ".join(rendered)
