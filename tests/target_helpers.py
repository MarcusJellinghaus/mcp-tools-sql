"""Shared helpers for building registries and resolved targets in tests."""

from __future__ import annotations

from typing import TYPE_CHECKING

from mcp_tools_sql.backends.registry import BackendRegistry
from mcp_tools_sql.config.models import (
    ConnectionConfig,
    ResolvedTarget,
    ResolvedTargets,
)

if TYPE_CHECKING:
    from mcp_tools_sql.backends.base import DatabaseBackend


class RecordingRegistry(BackendRegistry):
    """Registry that returns pre-seeded backends and records every lookup.

    Backends are keyed by ``(connection, database)``. ``backend_for`` appends
    each requested :class:`ResolvedTarget` to ``calls`` so tests can assert
    which target a tool bound to.
    """

    def __init__(self, backends: dict[tuple[str, str], DatabaseBackend]) -> None:
        super().__init__()
        self._seeded = backends
        self.calls: list[ResolvedTarget] = []

    def backend_for(self, target: ResolvedTarget) -> DatabaseBackend:
        """Record the lookup and return the seeded backend for *target*.

        Returns:
            The backend seeded for this target's ``(connection, database)`` key.
        """
        self.calls.append(target)
        return self._seeded[(target.connection, target.database)]


def make_target(
    connection: str,
    database: str,
    *,
    is_default: bool = False,
    default_database: str | None = None,
    backend_name: str = "sqlite",
) -> ResolvedTarget:
    """Build a ResolvedTarget for the given connection/database pair.

    Returns:
        A resolved target whose ``config.database`` is pinned to *database*.
    """
    default_db = default_database or database
    names = list(dict.fromkeys([default_db, database]))
    base = ConnectionConfig.model_validate(
        {"backend": backend_name, "databases": names, "default_database": default_db}
    )
    config = base.model_copy(update={"database": database})
    return ResolvedTarget(
        connection=connection,
        database=database,
        config=config,
        backend_name=backend_name,
        is_default=is_default,
    )


def single_target(
    backend: DatabaseBackend,
    *,
    connection: str = "default",
    database: str = "main",
) -> tuple[RecordingRegistry, ResolvedTargets]:
    """Build a one-target ``(registry, targets)`` bound to *backend*.

    Returns:
        A recording registry seeded with *backend* and a single-target
        ``ResolvedTargets`` whose default/file-default is that target.
    """
    target = make_target(
        connection, database, is_default=True, default_database=database
    )
    targets = ResolvedTargets(
        targets=[target], default=target, file_default_connection=connection
    )
    registry = RecordingRegistry({(connection, database): backend})
    return registry, targets
