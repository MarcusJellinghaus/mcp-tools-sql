"""Tests for the exit-code classifier and dispatch wrapper (`tool_dispatch.py`)."""

from __future__ import annotations

import asyncio
import inspect
import warnings
from collections.abc import Callable
from typing import Annotated, Any

from pydantic import Field

from mcp_tools_sql.backends.base import BackendConnectionError, BackendError
from mcp_tools_sql.cli.commands.tool_dispatch import (
    EXIT_BACKEND,
    EXIT_CONFIG,
    EXIT_OK,
    EXIT_REJECTED,
    classify_exception,
    invoke_tool,
)
from mcp_tools_sql.cli.commands.tool_help import render_tool_detail
from mcp_tools_sql.tool_builder import _UNSET, build_tool_fn
from mcp_tools_sql.utils.tool_spec import ToolSpec, tool_spec


def _spec(fn: Callable[..., Any]) -> ToolSpec:
    """Wrap a test function as a `ToolSpec`."""
    return tool_spec(fn, group="t", read_only=True, description="Test tool.")


def _update_style_spec(received: dict[str, Any]) -> ToolSpec:
    """Build an `update_*`-shaped spec whose `notes` field defaults to `_UNSET`."""

    async def _body(**kwargs: Any) -> str:
        received.update(kwargs)
        return "ok"

    fn = build_tool_fn(
        "update_t",
        [
            inspect.Parameter(
                "id", kind=inspect.Parameter.KEYWORD_ONLY, annotation=int
            ),
            inspect.Parameter(
                "notes",
                kind=inspect.Parameter.KEYWORD_ONLY,
                default=_UNSET,
                annotation=Annotated[str | None, Field(description="Notes")],
            ),
        ],
        _body,
        "Update tool.",
    )
    return tool_spec(fn, group="t", read_only=False)


async def _returns_string() -> str:
    return "the string"


async def _constrained(count: Annotated[int, Field(ge=1)]) -> str:
    return str(count)


async def _raises_runtime_error() -> str:
    raise RuntimeError("boom")


async def _raises_backend_connection_error() -> str:
    raise BackendConnectionError(
        "unable to open database file", original_class="OperationalError"
    )


async def _raises_value_error() -> str:
    raise ValueError("at least one field value required")


async def _raises_generic_exception() -> str:
    raise Exception("weird")  # pylint: disable=broad-exception-raised


def test_success_returns_exit_ok_and_result() -> None:
    """A function that returns a plain string: `(0, "the string")`."""
    tool = _spec(_returns_string)
    assert asyncio.run(invoke_tool(tool, {})) == (EXIT_OK, "the string")


def test_pydantic_validation_error_is_exit_rejected() -> None:
    """A violated `Field(ge=1)` constraint: exit 3, message mentions the constraint."""
    tool = _spec(_constrained)
    code, message = asyncio.run(invoke_tool(tool, {"count": 0}))
    assert code == EXIT_REJECTED
    assert "greater than or equal to 1" in message


def test_runtime_error_is_exit_config() -> None:
    """`RuntimeError("boom")`: exit 1."""
    tool = _spec(_raises_runtime_error)
    code, _message = asyncio.run(invoke_tool(tool, {}))
    assert code == EXIT_CONFIG


def test_backend_connection_error_is_exit_config() -> None:
    """`BackendConnectionError`: exit 1, message names the driver class."""
    tool = _spec(_raises_backend_connection_error)
    code, message = asyncio.run(invoke_tool(tool, {}))
    assert code == EXIT_CONFIG
    assert message == "OperationalError: unable to open database file"


def test_value_error_is_exit_rejected() -> None:
    """`ValueError` with the exact `update_tools.py` wording: exit 3."""
    tool = _spec(_raises_value_error)
    code, message = asyncio.run(invoke_tool(tool, {}))
    assert code == EXIT_REJECTED
    assert "at least one field value required" in message


def test_generic_exception_is_exit_backend() -> None:
    """A generic `Exception("weird")`: exit 4 (default fallback)."""
    tool = _spec(_raises_generic_exception)
    code, message = asyncio.run(invoke_tool(tool, {}))
    assert code == EXIT_BACKEND
    assert "weird" in message


def test_omitted_unset_default_reaches_body_without_warnings() -> None:
    """An omitted `_UNSET`-defaulted field arrives as `_UNSET`; no warning is raised."""
    received: dict[str, Any] = {}
    spec = _update_style_spec(received)

    with warnings.catch_warnings():
        warnings.simplefilter("error")
        result = asyncio.run(invoke_tool(spec, {"id": 1}))

    assert result == (EXIT_OK, "ok")
    assert received["id"] == 1
    assert received["notes"] is _UNSET


def test_render_tool_detail_with_unset_default_emits_no_warning() -> None:
    """`render_tool_detail` on an `_UNSET`-defaulted field raises no schema warning."""
    spec = _update_style_spec({})

    with warnings.catch_warnings():
        warnings.simplefilter("error")
        detail = render_tool_detail(spec)

    assert "--notes" in detail
    assert "--id  (required" in detail


def test_classify_exception_connection_bucket() -> None:
    """`classify_exception` buckets connection-shaped exceptions as `EXIT_CONFIG`."""
    assert classify_exception(RuntimeError("x")) == EXIT_CONFIG
    operational = BackendConnectionError("x", original_class="OperationalError")
    assert classify_exception(operational) == EXIT_CONFIG
    interface = BackendConnectionError("x", original_class="InterfaceError")
    assert classify_exception(interface) == EXIT_CONFIG


def test_classify_exception_rejected_bucket() -> None:
    """`classify_exception` buckets `KeyError`/`TypeError`/`ValueError` as `EXIT_REJECTED`."""
    assert classify_exception(KeyError("x")) == EXIT_REJECTED
    assert classify_exception(TypeError("x")) == EXIT_REJECTED
    assert classify_exception(ValueError("x")) == EXIT_REJECTED


def test_classify_exception_backend_default() -> None:
    """`classify_exception` falls back to `EXIT_BACKEND` for anything else."""
    programming = BackendError("x", original_class="ProgrammingError")
    assert classify_exception(programming) == EXIT_BACKEND
    assert classify_exception(Exception("x")) == EXIT_BACKEND  # pylint: disable=broad-exception-raised


def test_classify_exception_backend_errors() -> None:
    """Neutral backend errors bucket like the driver errors they translate."""
    connection = BackendConnectionError("x", original_class="OperationalError")
    assert classify_exception(connection) == EXIT_CONFIG
    other = BackendError("x", original_class="ProgrammingError")
    assert classify_exception(other) == EXIT_BACKEND


async def _raises_backend_error() -> str:
    raise BackendError("bad SQL", original_class="ProgrammingError")


def test_backend_error_message_uses_original_class() -> None:
    """`invoke_tool` names the driver class, not `BackendError`."""
    tool = _spec(_raises_backend_error)
    code, message = asyncio.run(invoke_tool(tool, {}))
    assert code == EXIT_BACKEND
    assert message == "ProgrammingError: bad SQL"
