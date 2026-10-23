"""Lazily-instantiated, cached database backends keyed by resolved target."""

from __future__ import annotations

import logging

from mcp_tools_sql.backends.base import _DIALECTS, DatabaseBackend
from mcp_tools_sql.config.models import ConnectionConfig, ResolvedTarget

logger = logging.getLogger(__name__)


def create_backend(config: ConnectionConfig) -> DatabaseBackend:
    """Factory: instantiate the appropriate backend for *config.backend*.

    Returns:
        A DatabaseBackend instance for the requested backend type.

    Raises:
        ValueError: If the backend type is not supported.
    """
    if config.backend == "sqlite":
        from mcp_tools_sql.backends.sqlite import SQLiteBackend

        return SQLiteBackend(config)
    if config.backend in ("mssql", "pyodbc"):
        from mcp_tools_sql.backends.mssql import MSSQLBackend

        return MSSQLBackend(config)
    msg = (
        f"Unsupported backend: {config.backend}. "
        f"Supported: {', '.join(sorted(_DIALECTS))}."
    )
    raise ValueError(msg)


class BackendRegistry:
    """Instantiate and cache one backend per ``(connection, database)`` target.

    Owns backend lifecycle for the server: ``backend_for`` creates a backend on
    first use (delegating concrete-backend selection to :func:`create_backend`)
    and returns the cached instance on repeat calls. ``close_all`` releases
    every instantiated backend.
    """

    def __init__(self) -> None:
        """Initialise an empty backend cache."""
        self._backends: dict[tuple[str, str], DatabaseBackend] = {}

    def backend_for(self, target: ResolvedTarget) -> DatabaseBackend:
        """Return the backend for *target*, creating and caching it on first use.

        Backends are keyed by ``(connection, database)``. The backend's own
        ``connect()`` stays lazy, so no connection is opened until a query runs.

        Returns:
            The cached (possibly freshly created) backend for this target.
        """
        key = (target.connection, target.database)
        backend = self._backends.get(key)
        if backend is None:
            backend = create_backend(target.config)
            self._backends[key] = backend
        return backend

    def close_all(self) -> None:
        """Close every instantiated backend, swallowing per-backend errors.

        A failure closing one backend is logged and does not prevent the rest
        from being closed.
        """
        for key, backend in self._backends.items():
            try:
                backend.close()
            except Exception:  # pylint: disable=broad-except
                logger.warning("Error closing backend %s", key, exc_info=True)
