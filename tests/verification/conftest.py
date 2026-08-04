"""Shared fixtures for verification tests."""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

import pytest

from mcp_tools_sql.backends.base import DatabaseBackend
from mcp_tools_sql.backends.registry import BackendRegistry
from mcp_tools_sql.backends.sqlite import SQLiteBackend
from mcp_tools_sql.config.models import (
    ConnectionConfig,
    ResolvedTarget,
    ResolvedTargets,
)


@pytest.fixture
def sqlite_backend(sqlite_db: Path) -> Generator[SQLiteBackend, None, None]:
    """Open a connected SQLiteBackend on the shared `sqlite_db` fixture."""
    backend = SQLiteBackend(ConnectionConfig(backend="sqlite", path=str(sqlite_db)))
    backend.connect()
    yield backend
    backend.close()


class StubRegistry(BackendRegistry):
    """A registry that returns one fixed backend for every target.

    Lets the M2 (QUERIES/UPDATES) verifiers be exercised against a single
    already-connected test backend without going through ``create_backend``.
    """

    def __init__(self, backend: DatabaseBackend) -> None:
        """Store the backend returned by every ``backend_for`` call."""
        super().__init__()
        self._stub = backend

    def backend_for(self, target: ResolvedTarget) -> DatabaseBackend:
        """Return the fixed stub backend regardless of *target*."""
        del target
        return self._stub


def make_targets(
    *,
    backend_name: str = "sqlite",
    connection: str = "default",
    config: ConnectionConfig | None = None,
) -> ResolvedTargets:
    """Build a single-target :class:`ResolvedTargets` for the M2 verifiers.

    Returns:
        A ``ResolvedTargets`` whose sole target is the file default.
    """
    if config is None:
        config = ConnectionConfig(backend=backend_name, path=":memory:")
    database = config.default_database
    target = ResolvedTarget(
        connection=connection,
        database=database,
        config=config,
        backend_name=backend_name,
        is_default=True,
    )
    return ResolvedTargets(
        targets=[target],
        default=target,
        file_default_connection=connection,
    )


def all_reachable_map(targets: ResolvedTargets) -> dict[tuple[str, str], bool]:
    """Return a reachability map marking every target reachable."""
    return {(t.connection, t.database): True for t in targets.targets}


@pytest.fixture
def sqlite_targets() -> ResolvedTargets:
    """Single sqlite ``default/main`` target for the M2 verifiers."""
    return make_targets(backend_name="sqlite")


@pytest.fixture
def sqlite_registry(sqlite_backend: SQLiteBackend) -> BackendRegistry:
    """A registry returning the connected `sqlite_backend` for any target."""
    return StubRegistry(sqlite_backend)


@pytest.fixture
def all_reachable(sqlite_targets: ResolvedTargets) -> dict[tuple[str, str], bool]:
    """Reachability map marking the single sqlite target reachable."""
    return all_reachable_map(sqlite_targets)
