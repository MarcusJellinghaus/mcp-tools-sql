"""Tokenizer-aware extraction and translation of ``:name`` SQL placeholders.

Recognises ``:name`` placeholders while ignoring occurrences inside
quoted strings (``'…'``, ``"…"``) and comments (``-- …``, ``/* … */``)
via ``sqlparse``'s token classification.
"""

from __future__ import annotations

from collections.abc import Iterator

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
