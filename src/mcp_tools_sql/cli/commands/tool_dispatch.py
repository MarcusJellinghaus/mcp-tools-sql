"""Exit-code classifier and dispatch wrapper for the `tool` CLI subcommand."""

from __future__ import annotations

import sqlite3
from typing import TYPE_CHECKING, Any

from pydantic import ValidationError

if TYPE_CHECKING:
    from mcp.server.fastmcp.tools.base import Tool

try:
    import pyodbc  # pylint: disable=import-error

    _CONNECTION_EXC: tuple[type[BaseException], ...] = (
        RuntimeError,
        sqlite3.OperationalError,
        sqlite3.InterfaceError,
        pyodbc.OperationalError,
        pyodbc.InterfaceError,
    )
except ImportError:
    _CONNECTION_EXC = (RuntimeError, sqlite3.OperationalError, sqlite3.InterfaceError)

_REJECTED_EXC: tuple[type[BaseException], ...] = (KeyError, TypeError, ValueError)

EXIT_OK = 0
EXIT_CONFIG = 1
EXIT_REJECTED = 3
EXIT_BACKEND = 4


def classify_exception(exc: BaseException) -> int:
    """Map a raised exception to one of the dispatch exit codes.

    Returns:
        `EXIT_CONFIG` for connection-shaped exceptions, `EXIT_REJECTED` for
        rejected-call exceptions, `EXIT_BACKEND` otherwise.
    """
    if isinstance(exc, _CONNECTION_EXC):
        return EXIT_CONFIG
    if isinstance(exc, _REJECTED_EXC):
        return EXIT_REJECTED
    return EXIT_BACKEND


async def invoke_tool(tool: Tool, kwargs: dict[str, Any]) -> tuple[int, str]:
    """Call ``tool.fn`` with the same validation path the MCP server uses.

    Returns:
        An ``(exit_code, text)`` pair — the text to print on either success
        or failure.
    """
    try:
        result = await tool.fn_metadata.call_fn_with_arg_validation(
            tool.fn, tool.is_async, kwargs, None
        )
        return EXIT_OK, str(result)
    except ValidationError as exc:
        return EXIT_REJECTED, str(exc)
    except Exception as exc:  # pylint: disable=broad-except
        return classify_exception(exc), f"{type(exc).__name__}: {exc}"
