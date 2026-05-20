"""Shared helpers for the verification subpackage."""

from __future__ import annotations

from typing import Any, TypedDict


class VerifierEntry(TypedDict):
    """Standard shape of a single verifier result row."""

    ok: bool
    value: str
    error: str
    install_hint: str


def make_entry(
    *,
    ok: bool,
    value: str = "",
    error: str = "",
    install_hint: str = "",
) -> dict[str, Any]:
    """Build a single verifier result entry with the standard shape.

    Not part of the public ``mcp_tools_sql.verification`` API — used only
    within the subpackage's submodules and (during the extraction) the CLI
    shim. Intentionally NOT re-exported from ``__init__.py``. The name
    deliberately lacks an underscore prefix to avoid pylint
    ``protected-access`` warnings on cross-module imports.

    Returns:
        Dict containing ``ok``, ``value``, ``error`` and ``install_hint`` keys.
    """
    return {"ok": ok, "value": value, "error": error, "install_hint": install_hint}
