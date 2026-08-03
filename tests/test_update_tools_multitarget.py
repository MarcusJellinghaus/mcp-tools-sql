"""Multi-target tests for UpdateTools (pinned per-target backend selection)."""

from __future__ import annotations

from pathlib import Path

import pytest
from mcp.server.fastmcp import FastMCP

from mcp_tools_sql.backends.sqlite import SQLiteBackend
from mcp_tools_sql.config.models import (
    ConnectionConfig,
    ResolvedTargets,
    UpdateConfig,
    UpdateFieldConfig,
    UpdateKeyConfig,
)
from mcp_tools_sql.update_tools import UpdateTools
from tests.target_helpers import RecordingRegistry, make_target


def _sqlite_backend(db_path: Path) -> SQLiteBackend:
    """Return a connected SQLite backend for the given database path."""
    backend = SQLiteBackend(ConnectionConfig(backend="sqlite", path=str(db_path)))
    backend.connect()
    return backend


# ---------------------------------------------------------------------------
# Pinned per-target backend selection (multi-target)
# ---------------------------------------------------------------------------


def _multi_target_registry(
    backend: SQLiteBackend,
) -> tuple[RecordingRegistry, ResolvedTargets, dict[str, object]]:
    """Build a 3-target ``(registry, targets, by_key)`` for pinning tests.

    Connection ``default`` has databases ``sales`` (default) and ``hr``;
    connection ``second`` has a lone ``sales`` database. Every target maps to
    the same *backend* so registration succeeds without a real second DB.
    """
    t_default = make_target(
        "default",
        "sales",
        is_default=True,
        default_database="sales",
        backend_name="mssql",
    )
    t_hr = make_target("default", "hr", default_database="sales", backend_name="mssql")
    t_second = make_target(
        "second", "sales", default_database="sales", backend_name="mssql"
    )
    targets = ResolvedTargets(
        targets=[t_default, t_hr, t_second],
        default=t_default,
        file_default_connection="default",
    )
    registry = RecordingRegistry(
        {
            ("default", "sales"): backend,
            ("default", "hr"): backend,
            ("second", "sales"): backend,
        }
    )
    return registry, targets, {"default": t_default, "hr": t_hr, "second": t_second}


def _set_name_update(**pins: str) -> dict[str, UpdateConfig]:
    """Return a ``set_name`` update config with the given pinned fields."""
    return {
        "set_name": UpdateConfig(
            description="",
            table="customers",
            key=UpdateKeyConfig(field="id", type="int"),
            fields=[UpdateFieldConfig(field="name", type="str")],
            **pins,
        )
    }


def test_unpinned_update_binds_default_target(sqlite_db: Path) -> None:
    """An update with no pinned fields binds to the default target's backend."""
    backend = _sqlite_backend(sqlite_db)
    registry, targets, by_key = _multi_target_registry(backend)
    mcp = FastMCP("test-update-pin-default")

    UpdateTools(registry, targets, _set_name_update()).register(mcp)

    assert registry.calls == [by_key["default"]]


def test_update_pinned_to_connection_binds_that_backend(sqlite_db: Path) -> None:
    """An update pinned to a second connection binds to that connection's backend."""
    backend = _sqlite_backend(sqlite_db)
    registry, targets, by_key = _multi_target_registry(backend)
    mcp = FastMCP("test-update-pin-connection")

    UpdateTools(registry, targets, _set_name_update(connection="second")).register(mcp)

    assert registry.calls == [by_key["second"]]


def test_update_pinned_to_database_resolves_default_connection(
    sqlite_db: Path,
) -> None:
    """An update pinned to ``database='hr'`` resolves ``(default_conn, hr)``."""
    backend = _sqlite_backend(sqlite_db)
    registry, targets, by_key = _multi_target_registry(backend)
    mcp = FastMCP("test-update-pin-database")

    UpdateTools(registry, targets, _set_name_update(database="hr")).register(mcp)

    assert registry.calls == [by_key["hr"]]
    assert registry.calls[0].connection == "default"
    assert registry.calls[0].database == "hr"


def test_update_pinned_to_unknown_target_raises(sqlite_db: Path) -> None:
    """An invalid pinned target surfaces as ValueError at register()."""
    backend = _sqlite_backend(sqlite_db)
    registry, targets, _ = _multi_target_registry(backend)
    mcp = FastMCP("test-update-pin-invalid")

    with pytest.raises(ValueError, match="nope"):
        UpdateTools(registry, targets, _set_name_update(connection="nope")).register(
            mcp
        )
