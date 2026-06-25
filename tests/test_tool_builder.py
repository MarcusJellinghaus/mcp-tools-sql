"""Tests for the tool_type-agnostic assembler in tool_builder."""

from __future__ import annotations

import asyncio
import inspect
from typing import Any

from mcp_tools_sql.query_helpers import apply_filter, extract_sql_params
from mcp_tools_sql.tool_builder import _UNSET, build_tool_fn


class TestExtractSqlParams:
    """Tests for extract_sql_params (now lives in query_helpers)."""

    def test_single_param(self) -> None:
        assert extract_sql_params("SELECT * WHERE x = :id") == {"id"}

    def test_multiple_params(self) -> None:
        assert extract_sql_params("SELECT * FROM t WHERE a = :x AND b = :y") == {
            "x",
            "y",
        }

    def test_no_params(self) -> None:
        assert extract_sql_params("SELECT 'main' AS name") == set()

    def test_duplicate_param(self) -> None:
        assert extract_sql_params("SELECT * FROM t WHERE a = :x OR b = :x") == {"x"}

    def test_unparseable_sql_yields_no_params(self) -> None:
        # Best-effort scan: invalid SQL returns an empty set rather than raising.
        assert extract_sql_params("SELECT * FROMX badtable") == set()


class TestApplyFilter:
    """Tests for apply_filter (now lives in query_helpers)."""

    def test_no_filter(self) -> None:
        """None filter returns all rows."""
        rows = [{"name": "a"}, {"name": "b"}]
        assert apply_filter(rows, "name", None) == rows

    def test_glob_match(self) -> None:
        """Glob pattern filters rows by the given column."""
        rows = [
            {"name": "user_id"},
            {"name": "user_name"},
            {"name": "order_id"},
        ]
        result = apply_filter(rows, "name", "user_*")
        assert result == [{"name": "user_id"}, {"name": "user_name"}]

    def test_case_insensitive(self) -> None:
        """Filter is case-insensitive."""
        rows = [{"name": "User_ID"}, {"name": "order_id"}]
        result = apply_filter(rows, "name", "user_*")
        assert result == [{"name": "User_ID"}]

    def test_no_match(self) -> None:
        """No matching rows returns empty list."""
        rows = [{"name": "a"}, {"name": "b"}]
        assert apply_filter(rows, "name", "z*") == []

    def test_apply_filter_column_absent_from_rows_returns_empty(self) -> None:
        """A filter_column missing from row keys yields empty list (no KeyError)."""
        rows = [{"other": "a"}, {"other": "b"}]
        assert apply_filter(rows, "missing", "a*") == []


class TestBuildToolFnAssembler:
    """build_tool_fn wires name, doc, signature, and body together."""

    def test_sets_name_doc_signature(self) -> None:
        """__name__, __doc__, and __signature__ reflect the inputs."""

        async def body(**_: Any) -> str:
            return "ok"

        sig_params = [
            inspect.Parameter(
                "x",
                kind=inspect.Parameter.POSITIONAL_OR_KEYWORD,
                annotation=int,
            )
        ]
        fn = build_tool_fn("my_tool", sig_params, body, "tool docstring")
        assert fn.__name__ == "my_tool"
        assert fn.__doc__ == "tool docstring"
        sig = inspect.signature(fn)
        assert list(sig.parameters) == ["x"]
        assert sig.parameters["x"].annotation is int

    def test_body_round_trip(self) -> None:
        """Calling the assembled fn awaits the body with the same kwargs."""
        seen: dict[str, Any] = {}

        async def body(**kwargs: Any) -> str:
            seen.update(kwargs)
            return "result-text"

        sig_params = [
            inspect.Parameter(
                "name",
                kind=inspect.Parameter.POSITIONAL_OR_KEYWORD,
                annotation=str,
            ),
            inspect.Parameter(
                "count",
                kind=inspect.Parameter.POSITIONAL_OR_KEYWORD,
                annotation=int,
                default=1,
            ),
        ]
        fn = build_tool_fn("echo", sig_params, body, "doc")
        result = asyncio.run(fn(name="alice", count=2))
        assert result == "result-text"
        assert seen == {"name": "alice", "count": 2}

    def test_empty_signature(self) -> None:
        """build_tool_fn works with no parameters."""

        async def body(**_: Any) -> str:
            return "fixed"

        fn = build_tool_fn("noop", [], body, "")
        assert inspect.signature(fn).parameters == {}
        assert asyncio.run(fn()) == "fixed"


class TestUnsetSentinel:
    """_UNSET is identity-comparable and distinct from None."""

    def test_unset_is_not_none(self) -> None:
        assert _UNSET is not None

    def test_unset_identity(self) -> None:
        from mcp_tools_sql.tool_builder import _UNSET as _UNSET_AGAIN

        assert _UNSET is _UNSET_AGAIN

    def test_unset_distinguishable_from_none_via_is(self) -> None:
        """_UNSET can be used as a sentinel: ``value is _UNSET`` works."""
        value: Any = _UNSET
        assert value is _UNSET
        value = None
        assert value is not _UNSET
