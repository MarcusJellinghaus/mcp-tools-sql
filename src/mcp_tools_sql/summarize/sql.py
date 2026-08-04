"""SQL generation and data structures for the ``summarize_columns`` tool.

This module hosts the summarize package's data layer. For now it provides the
pure, dialect-aware type categoriser that every later summarize step dispatches
on; the metadata / scalar-aggregate / value-list SQL builders and the shared
``ColumnMeta`` dataclass land in subsequent steps.

The categoriser is prefix/affinity-based, not an exact-match lookup: SQLite's
declared type is an arbitrary affinity string (``VARCHAR(20)``, ``NUM``, or even
empty), so classification keys off substrings and a few dialect-specific guards.
"""

from __future__ import annotations

from typing import Literal

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
