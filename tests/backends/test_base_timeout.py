"""Tests for the backend-neutral timeout primitives in ``backends/base.py``."""

from __future__ import annotations

import sqlite3

import pytest

from mcp_tools_sql.backends.base import (
    Deadline,
    QueryTimeoutError,
    translate_timeout,
)


def _exc(*args: object, sqlite_errorcode: int | None = None) -> Exception:
    """Build a plain exception, optionally carrying ``sqlite_errorcode``."""
    exc = Exception(*args)
    if sqlite_errorcode is not None:
        exc.sqlite_errorcode = sqlite_errorcode  # type: ignore[attr-defined]
    return exc


@pytest.mark.parametrize(
    "exc",
    [
        _exc("interrupted", sqlite_errorcode=9),
        _exc("HYT00", "[HYT00] Query timeout expired"),
    ],
    ids=["sqlite_interrupt", "sqlstate_hyt00"],
)
def test_translate_timeout_recognises_timeouts(exc: Exception) -> None:
    result = translate_timeout(exc, 7)
    assert isinstance(result, QueryTimeoutError)
    assert result.seconds == 7


@pytest.mark.parametrize(
    "exc",
    [
        _exc("database is locked", sqlite_errorcode=5),
        _exc("42S02", "[42S02] Invalid object name"),
        _exc("HYT01", "[HYT01] Connection timeout expired"),
        _exc(),
        _exc(9),
    ],
    ids=["other_sqlite_code", "other_sqlstate", "login_timeout", "no_args", "int"],
)
def test_translate_timeout_ignores_other_errors(exc: Exception) -> None:
    assert translate_timeout(exc, 7) is None


def test_query_timeout_error_message() -> None:
    exc = QueryTimeoutError(30)
    assert str(exc) == "Query aborted after 30 s (statement timeout)."
    assert exc.seconds == 30


def test_query_timeout_error_is_not_driver_error() -> None:
    assert not issubclass(QueryTimeoutError, sqlite3.Error)


def test_deadline_defaults_to_unarmed() -> None:
    assert Deadline().at is None
    assert Deadline(at=1.5).at == 1.5
