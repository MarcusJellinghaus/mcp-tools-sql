"""Tool-type-agnostic assembler for dynamic MCP tool registration."""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from typing import Any

_UNSET: Any = object()


def build_tool_fn(
    name: str,
    sig_params: list[inspect.Parameter],
    body: Callable[..., Awaitable[str]],
    doc: str,
) -> Callable[..., Any]:
    """Assemble an async MCP tool function from a signature and body.

    Args:
        name: Tool function name (sets ``__name__``).
        sig_params: Ordered list of parameters forming the public signature.
        body: Async callable that implements the tool — receives the same
            keyword arguments as the public signature describes.
        doc: Docstring for the assembled function (sets ``__doc__``).

    Returns:
        An ``async def`` function whose ``__signature__`` matches
        ``sig_params`` and that awaits ``body(**kwargs)`` when called.
    """

    async def _tool_fn(**kwargs: Any) -> str:
        return await body(**kwargs)

    _tool_fn.__signature__ = inspect.Signature(sig_params)  # type: ignore[attr-defined]
    _tool_fn.__name__ = name
    _tool_fn.__doc__ = doc
    return _tool_fn
