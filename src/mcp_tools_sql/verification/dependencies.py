"""Dependencies section: backend-conditional optional/extra deps check."""

from __future__ import annotations

from typing import Any

from mcp_tools_sql.verification._helpers import make_entry


def verify_dependencies(
    backend: str,
    configured_driver: str = "",
) -> dict[str, Any]:
    """Backend-conditional check of optional/extra dependencies.

    Args:
        backend: Backend name (``sqlite``, ``mssql``, ``postgresql``)
            or ``"unknown"`` when the backend cannot be resolved.
        configured_driver: For ``mssql``, the driver name from the
            resolved ``ConnectionConfig``. When provided and not found in
            ``pyodbc.drivers()``, the ``odbc_driver`` row fails and lists
            what *is* installed. When empty, falls back to the legacy
            behavior of accepting any driver whose name contains
            ``"SQL Server"``.

    Returns:
        Standard verifier result dict with backend-specific entries
        and an ``overall_ok`` flag.
    """
    if backend == "unknown":
        return {
            "backend": make_entry(
                ok=False,
                error="cannot determine backend without valid config",
            ),
            "overall_ok": False,
        }

    if backend == "sqlite":
        return {
            "info": make_entry(ok=True, value="(no optional dependencies for sqlite)"),
            "overall_ok": True,
        }

    if backend == "mssql":
        return _verify_dependencies_mssql(configured_driver)

    if backend == "postgresql":
        return _verify_dependencies_postgresql()

    return {
        "backend": make_entry(
            ok=False,
            value=backend,
            error=f"unknown backend {backend!r}",
        ),
        "overall_ok": False,
    }


def _verify_dependencies_mssql(configured_driver: str) -> dict[str, Any]:
    """Check for ``pyodbc`` and the configured (or any) ``SQL Server`` driver.

    Returns:
        Verifier result dict for the mssql backend.
    """
    result: dict[str, Any] = {}
    pyodbc_module: Any = None
    try:
        import pyodbc  # pylint: disable=import-outside-toplevel

        pyodbc_module = pyodbc
        version = getattr(pyodbc, "version", "")
        result["pyodbc"] = make_entry(ok=True, value=version)
    except ImportError as exc:
        result["pyodbc"] = make_entry(
            ok=False,
            value="(not installed)",
            error=str(exc),
            install_hint="pip install mcp-tools-sql[mssql]",
        )

    if pyodbc_module is None:
        result["odbc_driver"] = make_entry(
            ok=False,
            value="(skipped)",
            error="pyodbc not available",
        )
    else:
        result["odbc_driver"] = _check_odbc_driver(pyodbc_module, configured_driver)

    result["overall_ok"] = all(
        entry["ok"] for key, entry in result.items() if key != "overall_ok"
    )
    return result


def _check_odbc_driver(pyodbc_module: Any, configured_driver: str) -> dict[str, Any]:
    """Build the ``odbc_driver`` row, comparing config against installed drivers.

    When ``configured_driver`` is non-empty, the row fails if that exact name
    is not present in ``pyodbc.drivers()`` and the error lists what is.

    Returns:
        A verifier entry dict.
    """
    install_hint = (
        "Install Microsoft ODBC Driver 18 for SQL Server "
        "(https://learn.microsoft.com/sql/connect/odbc/"
        "download-odbc-driver-for-sql-server)"
    )
    try:
        drivers = list(pyodbc_module.drivers())
    except Exception as exc:  # pylint: disable=broad-except
        return make_entry(ok=False, value="(error)", error=str(exc))

    if configured_driver:
        if configured_driver in drivers:
            return make_entry(ok=True, value=configured_driver)
        installed_str = ", ".join(drivers) if drivers else "(none)"
        return make_entry(
            ok=False,
            value=f"(not found: {configured_driver!r})",
            error=f"configured driver not installed; installed: {installed_str}",
            install_hint=install_hint,
        )

    sql_server_driver = next((d for d in drivers if "SQL Server" in d), None)
    if sql_server_driver is None:
        return make_entry(
            ok=False,
            value="(none found)",
            error="No ODBC driver containing 'SQL Server' found",
            install_hint=install_hint,
        )
    return make_entry(ok=True, value=sql_server_driver)


def _verify_dependencies_postgresql() -> dict[str, Any]:
    """Check for the ``psycopg`` package.

    Returns:
        Verifier result dict for the postgresql backend.
    """
    result: dict[str, Any] = {}
    try:
        import psycopg  # type: ignore[import-not-found]  # pylint: disable=import-outside-toplevel

        version = getattr(psycopg, "__version__", "")
        result["psycopg"] = make_entry(ok=True, value=version)
    except ImportError as exc:
        result["psycopg"] = make_entry(
            ok=False,
            value="(not installed)",
            error=str(exc),
            install_hint="pip install mcp-tools-sql[postgresql]",
        )

    result["overall_ok"] = all(
        entry["ok"] for key, entry in result.items() if key != "overall_ok"
    )
    return result
