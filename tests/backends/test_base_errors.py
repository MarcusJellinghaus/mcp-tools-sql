"""Tests for the neutral backend exceptions and `wrap_driver_error`."""

from __future__ import annotations

import sqlite3

from mcp_tools_sql.backends.base import (
    BackendConnectionError,
    BackendError,
    QueryTimeoutError,
    wrap_driver_error,
)

_SQLITE_CONNECTION = (sqlite3.OperationalError, sqlite3.InterfaceError)


class _MultiArgError(Exception):
    """Stand-in for a pyodbc-style `(sqlstate, message)` driver error."""


def test_operational_error_becomes_connection_error() -> None:
    """A connection-shaped driver error maps to `BackendConnectionError`."""
    wrapped = wrap_driver_error(
        sqlite3.OperationalError("no such table: t"), _SQLITE_CONNECTION
    )
    assert type(wrapped) is BackendConnectionError
    assert str(wrapped) == "no such table: t"
    assert wrapped.original_class == "OperationalError"


def test_programming_error_becomes_plain_backend_error() -> None:
    """A non-connection driver error maps to plain `BackendError`."""
    wrapped = wrap_driver_error(sqlite3.ProgrammingError("bad"), _SQLITE_CONNECTION)
    assert type(wrapped) is BackendError
    assert wrapped.original_class == "ProgrammingError"


def test_multi_arg_error_keeps_str_and_args() -> None:
    """`str()` and `.args` survive the translation for multi-arg drivers."""
    original = _MultiArgError("42S02", "[42S02] msg")
    wrapped = wrap_driver_error(original, ())
    assert str(wrapped) == str(original)
    assert wrapped.args == original.args
    assert wrapped.original_class == "_MultiArgError"


def test_empty_connection_types_gives_plain_backend_error() -> None:
    """No connection types: every error is a plain `BackendError`."""
    wrapped = wrap_driver_error(sqlite3.OperationalError("x"), ())
    assert type(wrapped) is BackendError


def test_exception_hierarchy_is_isolated() -> None:
    """`BackendError` does not join builtin buckets; timeouts stay outside it."""
    for builtin in (RuntimeError, ValueError, KeyError, TypeError):
        assert not issubclass(BackendError, builtin)
    assert issubclass(BackendConnectionError, BackendError)
    assert not issubclass(QueryTimeoutError, BackendError)
