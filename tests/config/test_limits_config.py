"""Tests for the timeout settings, ``[limits]`` and their validation."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from mcp_tools_sql.config.models import (
    BUILTIN_MAX_ROWS_HARD,
    ConnectionConfig,
    LimitsConfig,
    QueryConfig,
    QueryFileConfig,
    count_rows_violation,
)


def test_connection_timeout_defaults() -> None:
    """Both timeouts default to 30 s (statement) and 15 s (login)."""
    config = ConnectionConfig(backend="sqlite", path=":memory:")

    assert config.query_timeout_seconds == 30
    assert config.connect_timeout_seconds == 15


def test_limits_defaults() -> None:
    """``[limits]`` defaults apply when the table is absent."""
    limits = QueryFileConfig(connection="default").limits

    assert limits.max_output_chars == 80_000
    assert limits.max_cell_chars == 500
    assert limits.max_count_rows == 100_000


@pytest.mark.parametrize("value", [0, -1])
@pytest.mark.parametrize("field", ["query_timeout_seconds", "connect_timeout_seconds"])
def test_connection_timeout_rejects_non_positive(field: str, value: int) -> None:
    """``0`` and negative timeouts fail validation."""
    with pytest.raises(ValidationError):
        ConnectionConfig.model_validate(
            {"backend": "sqlite", "path": ":memory:", field: value}
        )


@pytest.mark.parametrize("value", [0, -1])
@pytest.mark.parametrize(
    "field", ["max_output_chars", "max_cell_chars", "max_count_rows"]
)
def test_limits_reject_non_positive(field: str, value: int) -> None:
    """``0`` and negative limits fail validation."""
    with pytest.raises(ValidationError):
        QueryFileConfig.model_validate({"limits": {field: value}})


def test_max_count_rows_below_builtin_hard_limit_rejected() -> None:
    """``max_count_rows`` below the built-ins' ``max_rows_hard`` is rejected."""
    with pytest.raises(ValidationError):
        LimitsConfig(max_count_rows=BUILTIN_MAX_ROWS_HARD - 1)


def test_max_count_rows_equal_to_builtin_hard_limit_accepted() -> None:
    """``max_count_rows`` equal to the built-ins' ``max_rows_hard`` is fine."""
    assert LimitsConfig(max_count_rows=BUILTIN_MAX_ROWS_HARD).max_count_rows == 100


@pytest.mark.parametrize(
    "query",
    [
        {"sql": "SELECT 1", "max_rows_hard": 500},
        {"sql": "SELECT 1", "max_rows_default": 500},
    ],
    ids=["max_rows_hard", "max_rows_default"],
)
def test_query_hard_limit_above_max_count_rows_rejected(query: dict[str, Any]) -> None:
    """A query whose effective ``max_rows_hard`` exceeds ``max_count_rows`` fails."""
    with pytest.raises(ValidationError, match="max_count_rows"):
        QueryFileConfig.model_validate(
            {"limits": {"max_count_rows": 200}, "queries": {"big": query}}
        )


def test_query_hard_limit_within_max_count_rows_accepted() -> None:
    """A query whose ``max_rows_hard`` fits under ``max_count_rows`` loads."""
    config = QueryFileConfig.model_validate(
        {
            "limits": {"max_count_rows": 200},
            "queries": {"ok": {"sql": "SELECT 1", "max_rows_hard": 200}},
        }
    )

    assert config.limits.max_count_rows == 200


def test_count_rows_violation_message() -> None:
    """The violation names the query, its hard limit and ``max_count_rows``."""
    queries = {"big": QueryConfig(sql="SELECT 1", max_rows_hard=500)}

    message = count_rows_violation(LimitsConfig(max_count_rows=200), queries)

    assert message == (
        "[queries.big] max_rows_hard 500 exceeds [limits] max_count_rows 200"
    )


def test_count_rows_violation_none_when_ok() -> None:
    """No violation when every query fits."""
    queries = {"ok": QueryConfig(sql="SELECT 1")}

    assert count_rows_violation(LimitsConfig(), queries) is None


def test_connect_timeout_accepted_on_sqlite() -> None:
    """``connect_timeout_seconds`` is accepted (and ignored) on SQLite."""
    config = ConnectionConfig(
        backend="sqlite", path=":memory:", connect_timeout_seconds=5
    )

    assert config.connect_timeout_seconds == 5
