"""Connection section: backend instantiation, SELECT 1, Kerberos check."""

from __future__ import annotations

import logging
import socket
import subprocess
import sys
from typing import Any

from mcp_tools_sql.backends.base import DatabaseBackend, create_backend
from mcp_tools_sql.config.models import ConnectionConfig
from mcp_tools_sql.verification._helpers import make_entry

logger = logging.getLogger(__name__)

_CONTROL_CHAR_HINT = (
    "value contains control character(s) (e.g. newline) — most likely from a "
    "backslash escape (\\n, \\t) in a double-quoted TOML value. "
    "Use a single-quoted literal ('server\\name') or double the backslash "
    '("server\\\\name") to keep the literal backslash.'
)


def _has_control_chars(value: str) -> bool:
    """Return True if ``value`` contains any ASCII control character."""
    return any(ord(c) < 32 for c in value)


def _required_str_entry(value: str, *, required_error: str) -> dict[str, Any]:
    """Build a make_entry for a required string field, with control-char check.

    If ``value`` contains control characters, returns an ``ok=False`` entry
    whose ``value`` is ``repr(value)`` (so the offending character is visible)
    and ``error`` is :data:`_CONTROL_CHAR_HINT`. Otherwise behaves like the
    standard required-string check.

    Returns:
        A verifier entry dict.
    """
    if value and _has_control_chars(value):
        return make_entry(ok=False, value=repr(value), error=_CONTROL_CHAR_HINT)
    return make_entry(
        ok=bool(value),
        value=value or "(empty)",
        error="" if value else required_error,
    )


def _resolve_dns(host_with_instance: str) -> tuple[bool, str, str]:
    r"""Resolve the host portion of ``host_with_instance`` via DNS.

    Strips any ``\instance`` suffix before lookup — SQL Server named-instance
    syntax (``host\instance``) is not part of the hostname proper.

    Returns:
        Tuple ``(ok, value, error)`` suitable for :func:`make_entry`. On
        success ``value`` is the resolved IP; on failure ``value`` is the
        host that was tried and ``error`` carries the ``gaierror`` message.
    """
    host_only = host_with_instance.split("\\", 1)[0]
    try:
        ip = socket.gethostbyname(host_only)
        return True, ip, ""
    except socket.gaierror as exc:
        return False, host_only, f"DNS lookup failed: {exc}"


def _check_kerberos_ticket() -> tuple[bool, str, str]:
    """Run ``klist -s`` to check for a cached Kerberos ticket.

    Returns:
        Tuple ``(ok, value, error)``. ``ok`` is True when ``klist -s``
        exits zero. ``FileNotFoundError`` (no ``klist`` installed) and
        ``subprocess.TimeoutExpired`` map to ``ok=False`` with a hint.
    """
    try:
        proc = subprocess.run(
            ["klist", "-s"],
            check=False,
            capture_output=True,
            timeout=5,
        )
    except FileNotFoundError:
        logger.debug("klist not found on PATH")
        return (
            False,
            "klist not installed",
            "Install Kerberos client tools (krb5-user / krb5-workstation)",
        )
    except subprocess.TimeoutExpired as exc:
        logger.debug("klist -s timed out: %s", exc)
        return False, "klist timeout", str(exc)
    if proc.returncode == 0:
        logger.debug("klist -s exit 0: cached ticket present")
        return True, "cached ticket present", ""
    logger.debug("klist -s exit %d, stderr=%r", proc.returncode, proc.stderr)
    return False, "no cached ticket", "Run `kinit` to obtain a Kerberos ticket"


def verify_connection(
    connection: ConnectionConfig,
) -> tuple[dict[str, Any], DatabaseBackend | None]:
    """Verify connectivity to the configured database.

    Builds a backend via ``create_backend(connection)`` and runs ``SELECT 1``.
    On success the backend is left **open** and returned as the second tuple
    element so M2 sections can reuse it; the caller is responsible for
    closing it. On failure the second tuple element is ``None``.

    Returns:
        A 2-tuple of (result_dict, open_backend_or_None).
    """
    result: dict[str, Any] = {}
    result["backend"] = make_entry(ok=True, value=connection.backend)

    if connection.backend == "mssql":
        result["driver"] = make_entry(
            ok=bool(connection.driver),
            value=connection.driver or "(empty)",
            error="" if connection.driver else "driver must be set for mssql",
        )

    if connection.backend == "sqlite":
        result["path"] = _required_str_entry(
            connection.path, required_error="path must be set for sqlite"
        )
    else:
        if connection.host and _has_control_chars(connection.host):
            result["host_port"] = make_entry(
                ok=False,
                value=repr(connection.host),
                error=_CONTROL_CHAR_HINT,
            )
        else:
            if not connection.host:
                host_value = "(empty)"
            elif connection.port:
                host_value = f"{connection.host}:{connection.port}"
            else:
                host_value = connection.host
            result["host_port"] = make_entry(
                ok=bool(connection.host),
                value=host_value,
                error="" if connection.host else "host must be set",
            )
        result["database"] = _required_str_entry(
            connection.database, required_error="database must be set"
        )

    if connection.trusted_connection and connection.password:
        result["credentials"] = make_entry(
            ok=True, value="trusted_connection + password"
        )
    elif connection.trusted_connection:
        result["credentials"] = make_entry(ok=True, value="trusted_connection")
    elif connection.password:
        result["credentials"] = make_entry(ok=True, value="password")
    elif connection.backend == "sqlite":
        result["credentials"] = make_entry(ok=True, value="(not required for sqlite)")
    else:
        result["credentials"] = make_entry(
            ok=False,
            value="(none)",
            error="No credentials configured",
        )

    if (
        connection.backend == "mssql"
        and connection.host
        and not _has_control_chars(connection.host)
    ):
        ok, value, error = _resolve_dns(connection.host)
        result["dns_lookup"] = make_entry(ok=ok, value=value, error=error)

    if (
        connection.backend == "mssql"
        and connection.trusted_connection
        and sys.platform == "linux"
    ):
        ok, value, error = _check_kerberos_ticket()
        result["kerberos_ticket"] = make_entry(ok=ok, value=value, error=error)

    open_backend: DatabaseBackend | None = None
    backend: DatabaseBackend | None = None
    try:
        backend = create_backend(connection)
        backend.connect()
        backend.execute_query("SELECT 1")
        result["select_1"] = make_entry(ok=True, value="ok")
        open_backend = backend
    except Exception as exc:  # pylint: disable=broad-except
        result["select_1"] = make_entry(ok=False, value="failed", error=str(exc))
        if backend is not None:
            try:
                backend.close()
            except Exception:  # pylint: disable=broad-except
                pass
        open_backend = None

    result["overall_ok"] = all(
        entry["ok"] for key, entry in result.items() if key != "overall_ok"
    )
    return result, open_backend
