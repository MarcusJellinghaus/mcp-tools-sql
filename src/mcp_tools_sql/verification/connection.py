"""Connection section: backend instantiation, SELECT 1, Kerberos check."""

from __future__ import annotations

import subprocess
import sys
from typing import Any

from mcp_tools_sql.backends.base import DatabaseBackend, create_backend
from mcp_tools_sql.config.models import ConnectionConfig
from mcp_tools_sql.verification._helpers import make_entry


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
        return (
            False,
            "klist not installed",
            "Install Kerberos client tools (krb5-user / krb5-workstation)",
        )
    except subprocess.TimeoutExpired as exc:
        return False, "klist timeout", str(exc)
    if proc.returncode == 0:
        return True, "cached ticket present", ""
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
        result["path"] = make_entry(
            ok=bool(connection.path),
            value=connection.path or "(empty)",
            error="" if connection.path else "path must be set for sqlite",
        )
    else:
        host_value = (
            f"{connection.host}:{connection.port}" if connection.host else "(empty)"
        )
        result["host_port"] = make_entry(
            ok=bool(connection.host),
            value=host_value,
            error="" if connection.host else "host must be set",
        )
        result["database"] = make_entry(
            ok=bool(connection.database),
            value=connection.database or "(empty)",
            error="" if connection.database else "database must be set",
        )

    if connection.password or connection.trusted_connection:
        result["credentials"] = make_entry(ok=True, value="configured")
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
