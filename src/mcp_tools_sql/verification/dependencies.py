"""Dependencies section: per-connection backend and optional/extra deps check."""

from __future__ import annotations

from mcp_tools_sql.backends.connection_check import check_connections
from mcp_tools_sql.config.models import DatabaseConfig
from mcp_tools_sql.verification._helpers import CheckResult, make_entry


def verify_dependencies(db_config: DatabaseConfig | None) -> dict[str, CheckResult]:
    """Check the backend and its optional dependencies for every connection.

    Args:
        db_config: The loaded database config, or ``None`` when it is
            absent or failed to parse.

    Returns:
        Rows keyed ``<connection>.<key>``, or a single ``backend`` ERR row
        when there is no config or it defines no connections.
    """
    if db_config is None or not db_config.connections:
        return {
            "backend": make_entry(
                ok=False,
                error="cannot determine backend without valid config",
            ),
        }
    return {
        f"{row.connection}.{row.key}": make_entry(
            ok=row.ok, value=row.value, error=row.error, install_hint=row.hint
        )
        for row in check_connections(db_config.connections)
    }
