"""Tests for the summarize SQL type categoriser."""

from __future__ import annotations

from typing import get_args

import pytest

from mcp_tools_sql.summarize.sql import Category, categorize_type

# (declared_type, dialect, expected_category)
_CASES = [
    # --- SQLite affinities (arbitrary declared-type strings) ---
    ("INTEGER", "sqlite", "numeric"),
    ("INT", "sqlite", "numeric"),
    ("BIGINT", "sqlite", "numeric"),
    ("REAL", "sqlite", "numeric"),
    ("NUMERIC", "sqlite", "numeric"),
    ("NUM", "sqlite", "numeric"),  # bare NUMERIC affinity — must NOT fall to other
    ("DECIMAL(10,2)", "sqlite", "numeric"),
    ("VARCHAR(20)", "sqlite", "string"),
    ("TEXT", "sqlite", "string"),
    ("", "sqlite", "string"),  # empty affinity → string
    ("BLOB", "sqlite", "other"),
    ("BOOLEAN", "sqlite", "boolean"),
    ("DATE", "sqlite", "temporal"),
    ("DATETIME", "sqlite", "temporal"),
    # --- T-SQL DATA_TYPE strings ---
    ("int", "tsql", "numeric"),
    ("bigint", "tsql", "numeric"),
    ("decimal", "tsql", "numeric"),
    ("money", "tsql", "numeric"),
    ("float", "tsql", "numeric"),
    ("bit", "tsql", "boolean"),
    ("nvarchar", "tsql", "string"),
    ("varchar", "tsql", "string"),
    ("nvarchar(max)", "tsql", "string"),  # LOB-ish but still string, NOT other
    ("datetime2", "tsql", "temporal"),
    ("date", "tsql", "temporal"),
    ("varbinary", "tsql", "other"),
    ("uniqueidentifier", "tsql", "other"),
    # LOB trio — cannot appear in GROUP BY / DISTINCT / comparisons
    ("text", "tsql", "other"),
    ("ntext", "tsql", "other"),
    ("image", "tsql", "other"),
    # --- timestamp is dialect-dependent ---
    ("timestamp", "tsql", "other"),  # rowversion = binary(8), NOT date/time
    ("TIMESTAMP", "sqlite", "temporal"),  # genuine date/time affinity
    ("rowversion", "tsql", "other"),
    # --- case-insensitivity ---
    ("Int", "tsql", "numeric"),
    ("VarChar", "sqlite", "string"),
]


@pytest.mark.parametrize(("declared_type", "dialect", "expected"), _CASES)
def test_categorize_type(declared_type: str, dialect: str, expected: str) -> None:
    """categorize_type maps declared types to the expected coarse category."""
    assert categorize_type(declared_type, dialect) == expected


def test_categorize_type_returns_a_category_literal() -> None:
    """Every result is one of the five declared Category literal values."""
    valid = set(get_args(Category))
    for declared_type, dialect, _ in _CASES:
        assert categorize_type(declared_type, dialect) in valid
