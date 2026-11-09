"""Shared helpers and result types for the verification subpackage."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Literal, NotRequired, TypedDict


class CheckResult(TypedDict):
    """One verifier result row.

    ``severity`` is ``"warning"`` for WARN rows (always ``ok=False``) and
    ``"error"`` for passing and ERR rows. ``error`` and ``install_hint`` are
    present only when non-empty.
    """

    ok: bool
    value: str
    severity: Literal["error", "warning"]
    error: NotRequired[str]
    install_hint: NotRequired[str]


class VerifySection(TypedDict):
    """One titled section of verifier rows, keyed (and ordered) by row label."""

    title: str
    ok: bool
    checks: dict[str, CheckResult]


class VerifyResult(TypedDict):
    """Full result of :func:`mcp_tools_sql.verification.verify_all`.

    ``skipped_queries`` / ``skipped_updates`` are ``None`` unless the
    QUERIES/UPDATES sections were skipped because the default connection
    failed; then they hold the number of entries that went unchecked.
    """

    sections: list[VerifySection]
    skipped_queries: int | None
    skipped_updates: int | None


def make_entry(
    *,
    ok: bool,
    value: str = "",
    error: str = "",
    install_hint: str = "",
    severity: Literal["error", "warning"] = "error",
) -> CheckResult:
    """Build a single verifier result entry with the standard shape.

    Not part of the public ``mcp_tools_sql.verification`` API — used only
    within the subpackage's submodules. The name deliberately lacks an
    underscore prefix to avoid pylint ``protected-access`` warnings on
    cross-module imports.

    Returns:
        A :class:`CheckResult`; ``error`` and ``install_hint`` are included
        only when non-empty.
    """
    entry: CheckResult = {"ok": ok, "value": value, "severity": severity}
    if error:
        entry["error"] = error
    if install_hint:
        entry["install_hint"] = install_hint
    return entry


def make_warn_entry(value: str, error: str = "") -> CheckResult:
    """Build a WARN entry that does not affect the exit code.

    Returns:
        A :class:`CheckResult` with ``ok=False`` and ``severity="warning"``.
    """
    return make_entry(ok=False, value=value, error=error, severity="warning")


def make_skipped_entry(connection: str) -> CheckResult:
    """Build a WARN entry for a check skipped because its connection is down.

    Emitted by the M2 (QUERIES/UPDATES) verifiers when an entry's resolved
    target belongs to an unreachable connection: instead of blanking the row,
    it names the offending connection. A warning, so it does not itself flip
    the exit code — the connection's own probe failure in the CONNECTION
    section already records the error.

    Returns:
        A warning :class:`CheckResult`.
    """
    return make_warn_entry(f"skipped (connection {connection} unreachable)")


def make_skipped_not_read_only_entry() -> CheckResult:
    """Build a WARN entry for an EXPLAIN skipped because the query is rejected.

    The ``<name>.sql`` EXPLAIN probe would otherwise send the database operator
    the very SQL the read-only gate is about to refuse, and report the
    database's complaint about it rather than the real reason the query is bad.
    A warning for the same reason as :func:`make_skipped_entry`: the query's
    own ``read_only`` row already records the error, so this row must not flip
    the exit code a second time.

    Returns:
        A warning :class:`CheckResult`.
    """
    return make_warn_entry("(skipped)", "not read-only; see the read_only row")


def is_passing(entry: CheckResult) -> bool:
    """Return True when ``entry`` passed or is only a warning."""
    return entry["ok"] or entry["severity"] == "warning"


def checks_ok(checks: Mapping[str, CheckResult]) -> bool:
    """Return True when every row in ``checks`` is passing (see :func:`is_passing`)."""
    return all(is_passing(entry) for entry in checks.values())
