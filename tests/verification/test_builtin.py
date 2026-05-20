"""Tests for `verify_builtin`."""

from __future__ import annotations

import re

from mcp_tools_sql.verification import verify_builtin


def test_verify_builtin_returns_query_count() -> None:
    """`default_queries_loaded` and `tools_registered_count` report >0 entries."""
    result = verify_builtin()

    assert result["default_queries_loaded"]["ok"] is True
    match = re.match(r"(\d+) queries", result["default_queries_loaded"]["value"])
    assert match is not None
    assert int(match.group(1)) > 0
    assert result["tools_registered_count"]["ok"] is True
    assert result["overall_ok"] is True


def test_verify_reports_default_queries_count() -> None:
    """Issue test (x): BUILTIN section shows ``{N} queries`` text."""
    result = verify_builtin()

    assert "queries" in result["default_queries_loaded"]["value"]
