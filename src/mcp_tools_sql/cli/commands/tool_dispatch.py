"""Exit-code classifier and dispatch wrapper for the `tool` CLI subcommand."""

from __future__ import annotations

import inspect
import sqlite3
from typing import TYPE_CHECKING, Any

from pydantic import ValidationError

if TYPE_CHECKING:
    from mcp_tools_sql.utils.tool_spec import ToolSpec

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


async def invoke_tool(spec: ToolSpec, kwargs: dict[str, Any]) -> tuple[int, str]:
    """Validate ``kwargs`` against ``spec.args_model``, then call ``spec.fn``.

    Every model field is passed to ``spec.fn``, so omitted optional
    arguments arrive as their defaults (including the ``_UNSET`` sentinel).

    Returns:
        An ``(exit_code, text)`` pair — the text to print on either success
        or failure.
    """
    try:
        validated = spec.args_model.model_validate(kwargs)
        call_kwargs = {
            field: getattr(validated, field) for field in spec.args_model.model_fields
        }
        result = spec.fn(**call_kwargs)
        if inspect.isawaitable(result):
            result = await result
        return EXIT_OK, str(result)
    except ValidationError as exc:
        return EXIT_REJECTED, str(exc)
    except Exception as exc:  # pylint: disable=broad-except
        name = getattr(exc, "original_class", type(exc).__name__)
        return classify_exception(exc), f"{name}: {exc}"
