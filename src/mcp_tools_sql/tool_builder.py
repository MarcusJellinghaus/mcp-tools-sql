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
        ``sig_params``. When called it binds the kwargs to that signature,
        fills omitted parameters from their defaults, and awaits ``body``
        with every parameter. Callers that pass only the keys they set
        (e.g. LangChain) thus see the same body arguments as FastMCP, which
        passes every field. Unknown or missing required kwargs raise
        ``TypeError``.
    """
    sig = inspect.Signature(sig_params)

    async def _tool_fn(**kwargs: Any) -> str:
        bound = sig.bind(**kwargs)
        bound.apply_defaults()
        return await body(**bound.arguments)

    _tool_fn.__signature__ = sig  # type: ignore[attr-defined]
    _tool_fn.__name__ = name
    _tool_fn.__doc__ = doc
    return _tool_fn
