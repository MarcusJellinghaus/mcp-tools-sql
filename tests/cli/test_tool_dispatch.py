"""Tests for the exit-code classifier and dispatch wrapper (`tool_dispatch.py`)."""

from __future__ import annotations

import asyncio
import sqlite3
from typing import Annotated

import pytest
from mcp.server.fastmcp.tools.base import Tool
from pydantic import Field

from mcp_tools_sql.cli.commands.tool_dispatch import (
    EXIT_BACKEND,
    EXIT_CONFIG,
    EXIT_OK,
    EXIT_REJECTED,
    classify_exception,
    invoke_tool,
)

try:
    import pyodbc  # pylint: disable=import-error

    _HAS_PYODBC = True
except ImportError:
    _HAS_PYODBC = False


async def _returns_string() -> str:
    return "the string"


async def _constrained(count: Annotated[int, Field(ge=1)]) -> str:
    return str(count)


async def _raises_runtime_error() -> str:
    raise RuntimeError("boom")


async def _raises_sqlite_operational_error() -> str:
    raise sqlite3.OperationalError("unable to open database file")


async def _raises_value_error() -> str:
    raise ValueError("at least one field value required")


async def _raises_sqlite_programming_error() -> str:
    raise sqlite3.ProgrammingError("bad SQL")


async def _raises_generic_exception() -> str:
    raise Exception("weird")  # pylint: disable=broad-exception-raised


def test_success_returns_exit_ok_and_result() -> None:
    """A function that returns a plain string: `(0, "the string")`."""
    tool = Tool.from_function(_returns_string)
    assert asyncio.run(invoke_tool(tool, {})) == (EXIT_OK, "the string")


def test_pydantic_validation_error_is_exit_rejected() -> None:
    """A violated `Field(ge=1)` constraint: exit 3, message mentions the constraint."""
    tool = Tool.from_function(_constrained)
    code, message = asyncio.run(invoke_tool(tool, {"count": 0}))
    assert code == EXIT_REJECTED
    assert "greater than or equal to 1" in message


def test_runtime_error_is_exit_config() -> None:
    """`RuntimeError("boom")`: exit 1."""
    tool = Tool.from_function(_raises_runtime_error)
    code, _message = asyncio.run(invoke_tool(tool, {}))
    assert code == EXIT_CONFIG


def test_sqlite_operational_error_is_exit_config() -> None:
    """`sqlite3.OperationalError`: exit 1."""
    tool = Tool.from_function(_raises_sqlite_operational_error)
    code, _message = asyncio.run(invoke_tool(tool, {}))
    assert code == EXIT_CONFIG


def test_value_error_is_exit_rejected() -> None:
    """`ValueError` with the exact `update_tools.py` wording: exit 3."""
    tool = Tool.from_function(_raises_value_error)
    code, message = asyncio.run(invoke_tool(tool, {}))
    assert code == EXIT_REJECTED
    assert "at least one field value required" in message


def test_sqlite_programming_error_is_exit_backend() -> None:
    """`sqlite3.ProgrammingError`: exit 4."""
    tool = Tool.from_function(_raises_sqlite_programming_error)
    code, _message = asyncio.run(invoke_tool(tool, {}))
    assert code == EXIT_BACKEND


def test_generic_exception_is_exit_backend() -> None:
    """A generic `Exception("weird")`: exit 4 (default fallback)."""
    tool = Tool.from_function(_raises_generic_exception)
    code, message = asyncio.run(invoke_tool(tool, {}))
    assert code == EXIT_BACKEND
    assert "weird" in message


def test_classify_exception_connection_bucket() -> None:
    """`classify_exception` buckets connection-shaped exceptions as `EXIT_CONFIG`."""
    assert classify_exception(RuntimeError("x")) == EXIT_CONFIG
    assert classify_exception(sqlite3.OperationalError("x")) == EXIT_CONFIG
    assert classify_exception(sqlite3.InterfaceError("x")) == EXIT_CONFIG


def test_classify_exception_rejected_bucket() -> None:
    """`classify_exception` buckets `KeyError`/`TypeError`/`ValueError` as `EXIT_REJECTED`."""
    assert classify_exception(KeyError("x")) == EXIT_REJECTED
    assert classify_exception(TypeError("x")) == EXIT_REJECTED
    assert classify_exception(ValueError("x")) == EXIT_REJECTED


def test_classify_exception_backend_default() -> None:
    """`classify_exception` falls back to `EXIT_BACKEND` for anything else."""
    assert classify_exception(sqlite3.ProgrammingError("x")) == EXIT_BACKEND
    assert (
        classify_exception(Exception("x")) == EXIT_BACKEND
    )  # pylint: disable=broad-exception-raised


@pytest.mark.skipif(
    not _HAS_PYODBC, reason="pyodbc not installed in this dev environment"
)
def test_classify_exception_pyodbc_buckets() -> None:
    """`classify_exception` buckets pyodbc connection errors as `EXIT_CONFIG`, others as `EXIT_BACKEND`."""
    assert classify_exception(pyodbc.OperationalError("x", "y")) == EXIT_CONFIG
    assert classify_exception(pyodbc.ProgrammingError("x", "y")) == EXIT_BACKEND
