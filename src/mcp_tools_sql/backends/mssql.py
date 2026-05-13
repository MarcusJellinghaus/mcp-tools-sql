"""Microsoft SQL Server database backend."""

from __future__ import annotations

from typing import Any

from mcp_tools_sql.backends.base import DatabaseBackend
from mcp_tools_sql.config.models import ConnectionConfig

_NEEDS_BRACES = set(";={}")
_DEFAULT_MSSQL_PORT = 1433


def _odbc_escape(value: str) -> str:
    """Escape an ODBC connection-string value per the ODBC spec.

    Wraps the value in ``{...}`` if it contains ``;``, ``=``, ``{``, ``}``,
    or has surrounding whitespace; embedded ``}`` characters are doubled.
    """
    if not value:
        return value
    if any(c in _NEEDS_BRACES for c in value) or value != value.strip():
        return "{" + value.replace("}", "}}") + "}"
    return value


def _build_connection_string(config: ConnectionConfig) -> str:
    """Build a pyodbc connection string from a ``ConnectionConfig``.

    Returns a semicolon-joined ``key=value`` string with deterministic
    ordering. ``port`` of 0 maps to the SQL Server default 1433.
    """
    port = config.port or _DEFAULT_MSSQL_PORT
    parts = [
        f"Driver={{{config.driver}}}",
        f"Server={config.host},{port}",
        f"Database={_odbc_escape(config.database)}",
    ]
    if config.trusted_connection:
        parts.append("Trusted_Connection=yes")
    else:
        parts.append(f"UID={_odbc_escape(config.username)}")
        parts.append(f"PWD={_odbc_escape(config.password)}")
    parts.append(f"Encrypt={'yes' if config.encrypt else 'no'}")
    parts.append(
        f"TrustServerCertificate={'yes' if config.trust_server_certificate else 'no'}"
    )
    return ";".join(parts)


class MSSQLBackend(DatabaseBackend):
    """Backend for Microsoft SQL Server via pyodbc."""

    def __init__(self, config: ConnectionConfig) -> None:
        self._config = config

    def connect(self) -> None:
        """Open a connection to SQL Server."""
        raise NotImplementedError

    def close(self) -> None:
        """Close the SQL Server connection."""
        raise NotImplementedError

    def execute_query(
        self, sql: str, params: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        """Execute a SELECT query."""
        raise NotImplementedError

    def execute_update(self, sql: str, params: dict[str, Any] | None = None) -> int:
        """Execute an UPDATE/INSERT."""
        raise NotImplementedError

    def explain(self, sql: str, params: dict[str, Any] | None = None) -> str:
        """Return the query execution plan."""
        raise NotImplementedError
