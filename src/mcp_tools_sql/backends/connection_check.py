"""Per-connection dependency check: backend name, pyodbc, ODBC driver.

Produces neutral :class:`DependencyRow` values (``backends`` cannot import
``verification``); the DEPENDENCIES section and ``build_toolset`` map them.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import NamedTuple

from mcp_tools_sql.backends.base import SUPPORTED_BACKENDS, normalize_backend
from mcp_tools_sql.backends.mssql import odbc_drivers, pyodbc_version
from mcp_tools_sql.config.models import ConnectionConfig

MSSQL_INSTALL_HINT = "pip install mcp-tools-sql[mssql]"
ODBC_DRIVER_HINT = (
    "Install Microsoft ODBC Driver 18 for SQL Server "
    "(https://learn.microsoft.com/sql/connect/odbc/download-odbc-driver-for-sql-server)"
)


@dataclass(frozen=True)
class DependencyRow:
    """One dependency check result for one connection.

    Attributes:
        connection: The connection name from the database config.
        key: ``"info"``, ``"backend"``, ``"pyodbc"`` or ``"odbc_driver"``.
        ok: Whether the check passed.
        value: The observed value (version, driver name, placeholder).
        error: Why the check failed; empty when it passed.
        hint: How to fix the failure; empty when there is nothing to install.
    """

    connection: str
    key: str
    ok: bool
    value: str = ""
    error: str = ""
    hint: str = ""


class _PyodbcProbe(NamedTuple):
    """Outcome of probing pyodbc once: version and installed drivers."""

    version: str | None
    import_error: str
    drivers: list[str] | None
    drivers_error: str


def _probe_pyodbc() -> _PyodbcProbe:
    """Import pyodbc and list its drivers, capturing failures as text.

    Returns:
        ``version`` is ``None`` when pyodbc cannot be imported; ``drivers``
        is ``None`` when pyodbc is missing or ``drivers()`` raised.
    """
    try:
        version = pyodbc_version()
    except ImportError as exc:
        return _PyodbcProbe(None, str(exc), None, "")
    try:
        drivers = odbc_drivers()
    except Exception as exc:  # pylint: disable=broad-except
        return _PyodbcProbe(version, "", None, str(exc))
    return _PyodbcProbe(version, "", drivers, "")


def _pyodbc_row(name: str, probe: _PyodbcProbe) -> DependencyRow:
    """Build the ``pyodbc`` row for connection *name*.

    Returns:
        OK with the version, or ERR ``(not installed)`` with the install hint.
    """
    if probe.version is None:
        return DependencyRow(
            name,
            "pyodbc",
            ok=False,
            value="(not installed)",
            error=probe.import_error,
            hint=MSSQL_INSTALL_HINT,
        )
    return DependencyRow(name, "pyodbc", ok=True, value=probe.version)


def _driver_row(name: str, driver: str, probe: _PyodbcProbe) -> DependencyRow:
    """Build the ``odbc_driver`` row, comparing *driver* against installed ones.

    A non-empty *driver* must be installed by that exact name; an empty one
    accepts the first installed driver whose name contains ``SQL Server``.

    Returns:
        The ``odbc_driver`` row for connection *name*.
    """
    if probe.version is None:
        return DependencyRow(
            name,
            "odbc_driver",
            ok=False,
            value="(skipped)",
            error="pyodbc not available",
        )
    if probe.drivers is None:
        return DependencyRow(
            name, "odbc_driver", ok=False, value="(error)", error=probe.drivers_error
        )

    drivers = probe.drivers
    if driver:
        if driver in drivers:
            return DependencyRow(name, "odbc_driver", ok=True, value=driver)
        installed = ", ".join(drivers) if drivers else "(none)"
        return DependencyRow(
            name,
            "odbc_driver",
            ok=False,
            value=f"(not found: {driver!r})",
            error=f"configured driver {driver!r} not installed; installed: {installed}",
            hint=ODBC_DRIVER_HINT,
        )

    sql_server_driver = next((d for d in drivers if "SQL Server" in d), None)
    if sql_server_driver is None:
        return DependencyRow(
            name,
            "odbc_driver",
            ok=False,
            value="(none found)",
            error="No ODBC driver containing 'SQL Server' found",
            hint=ODBC_DRIVER_HINT,
        )
    return DependencyRow(name, "odbc_driver", ok=True, value=sql_server_driver)


def check_connections(
    connections: Mapping[str, ConnectionConfig],
) -> list[DependencyRow]:
    """Check the backend and its optional dependencies for every connection.

    pyodbc is probed at most once per call, however many connections use it.
    No connection is opened.

    Args:
        connections: Connection configs keyed by name.

    Returns:
        Rows in connection order: ``backend`` (unsupported name), ``info``
        (sqlite), or ``pyodbc`` then ``odbc_driver`` (mssql / pyodbc).
    """
    rows: list[DependencyRow] = []
    probe: _PyodbcProbe | None = None
    for name, cfg in connections.items():
        if cfg.backend not in SUPPORTED_BACKENDS:
            rows.append(
                DependencyRow(
                    name,
                    "backend",
                    ok=False,
                    value=cfg.backend,
                    error=f"unsupported backend {cfg.backend!r}; "
                    f"supported: {', '.join(sorted(SUPPORTED_BACKENDS))}",
                )
            )
        elif normalize_backend(cfg.backend) == "sqlite":
            rows.append(
                DependencyRow(
                    name, "info", ok=True, value="(no optional dependencies for sqlite)"
                )
            )
        else:
            if probe is None:
                probe = _probe_pyodbc()
            rows.append(_pyodbc_row(name, probe))
            rows.append(_driver_row(name, cfg.driver, probe))
    return rows
