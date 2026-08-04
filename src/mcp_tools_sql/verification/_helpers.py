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


def make_skipped_entry(connection: str) -> dict[str, Any]:
    """Build a WARN entry for a check skipped because its connection is down.

    Emitted by the M2 (QUERIES/UPDATES) verifiers when an entry's resolved
    target belongs to an unreachable connection: instead of blanking the row,
    it names the offending connection. Rendered as ``[WARN]`` (``warn=True``)
    so it does not itself flip the exit code — the connection's own probe
    failure in the CONNECTION section already records the error.

    Returns:
        A verifier entry dict with ``warn`` set.
    """
    entry = make_entry(ok=True, value=f"skipped (connection {connection} unreachable)")
    entry["warn"] = True
    return entry
