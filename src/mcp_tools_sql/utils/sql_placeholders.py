"""Tokenizer-aware extraction and translation of ``:name`` SQL placeholders.

Recognises ``:name`` placeholders while ignoring occurrences inside
quoted strings (``'…'``, ``"…"``) and comments (``-- …``, ``/* … */``)
via ``sqlparse``'s token classification.

Exposes :func:`extract_param_names`, :func:`translate_named_to_qmark`, and
:func:`substitute_named_with_literals`. The last is used by the MSSQL
``explain`` path, where pyodbc's prepared-statement protocol does not
return result rows under ``SET SHOWPLAN_TEXT ON``.
"""

from __future__ import annotations

import math
from collections.abc import Iterator
from datetime import date, datetime
from decimal import Decimal
from typing import Any

import sqlparse
from sqlparse import tokens as T
from sqlparse.sql import Token


def _iter_placeholders(sql: str) -> Iterator[Token]:
    """Yield ``:name`` placeholder tokens from ``sql``.

    Quoted strings and comments are skipped because ``sqlparse`` tags
    placeholders with ``Name.Placeholder`` distinctly from string and
    comment tokens.

    Yields:
        Each ``Name.Placeholder`` token whose value begins with ``:``.
    """
    for stmt in sqlparse.parse(sql):
        for tok in stmt.flatten():  # type: ignore[no-untyped-call]
            if tok.ttype is T.Name.Placeholder and tok.value.startswith(":"):
                yield tok


def extract_param_names(sql: str) -> set[str]:
    """Return the set of ``:name`` placeholder names in ``sql``.

    Returns:
        Unordered, deduplicated set of placeholder names (without the
        leading ``:``). Placeholders inside quoted strings or comments
        are ignored.
    """
    return {tok.value[1:] for tok in _iter_placeholders(sql)}


def translate_named_to_qmark(sql: str) -> tuple[str, list[str]]:
    """Translate ``:name`` placeholders to ``?`` markers.

    Returns:
        Tuple ``(translated_sql, ordered_names)`` where every
        ``:name`` placeholder has been rewritten as ``?`` and
        ``ordered_names[i]`` is the name of the *i*-th ``?`` in
        ``translated_sql``. Order and duplicates are preserved.
    """
    names: list[str] = []
    parts: list[str] = []
    for stmt in sqlparse.parse(sql):
        for tok in stmt.flatten():  # type: ignore[no-untyped-call]
            if tok.ttype is T.Name.Placeholder and tok.value.startswith(":"):
                names.append(tok.value[1:])
                parts.append("?")
            else:
                parts.append(tok.value)
    return "".join(parts), names


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

    A missing placeholder key raises ``KeyError`` (via the ``params``
    lookup); unsupported value types or non-finite floats propagate
    ``TypeError`` / ``ValueError`` from :func:`_sql_literal`.

    Args:
        sql: SQL with ``:name`` placeholders.
        params: Mapping of placeholder name to Python value.

    Returns:
        SQL with each placeholder replaced by ``_sql_literal(params[name])``.
    """
    parts: list[str] = []
    for stmt in sqlparse.parse(sql):
        for tok in stmt.flatten():  # type: ignore[no-untyped-call]
            if tok.ttype is T.Name.Placeholder and tok.value.startswith(":"):
                name = tok.value[1:]
                parts.append(_sql_literal(params[name]))
            else:
                parts.append(tok.value)
    return "".join(parts)
