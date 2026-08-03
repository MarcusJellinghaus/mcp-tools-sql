"""Tests for BackendRegistry: lazy per-target backend caching + close_all."""

from __future__ import annotations

from contextlib import AbstractContextManager, nullcontext
from typing import Any

import pytest

from mcp_tools_sql.backends.base import DatabaseBackend
from mcp_tools_sql.backends.registry import BackendRegistry
from mcp_tools_sql.config.models import ConnectionConfig, ResolvedTarget


def _sqlite_target(connection: str, *, path: str = "") -> ResolvedTarget:
    """Build a sqlite ResolvedTarget keyed by the given connection name."""
    config = ConnectionConfig(backend="sqlite", path=path)
    return ResolvedTarget(
        connection=connection,
        database="main",
        config=config,
        backend_name="sqlite",
        is_default=False,
    )


class _FakeBackend(DatabaseBackend):
    """Minimal in-memory backend that records connect/close activity."""

    def __init__(self, *, close_raises: bool = False) -> None:
        self.connected = False
        self.close_calls = 0
        self._close_raises = close_raises

    def connect(self) -> None:
        self.connected = True

    def close(self) -> None:
        self.close_calls += 1
        if self._close_raises:
            raise RuntimeError("boom")

    def execute_query(
        self, sql: str, params: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        return []

    def execute_readonly_query(
        self, sql: str, params: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        return []

    def execute_update(self, sql: str, params: dict[str, Any] | None = None) -> int:
        return 0

    def explain(self, sql: str, params: dict[str, Any] | None = None) -> str:
        return ""

    def get_isolated_connection(self) -> AbstractContextManager[Any]:
        return nullcontext()


def _install_fake_create(
    monkeypatch: pytest.MonkeyPatch,
    factory: Any,
) -> None:
    """Replace ``create_backend`` in the registry module with *factory*."""
    monkeypatch.setattr("mcp_tools_sql.backends.registry.create_backend", factory)


# ---------------------------------------------------------------------------
# Caching identity
# ---------------------------------------------------------------------------


class TestCaching:
    """backend_for caches one backend per (connection, database) key."""

    def test_same_target_returns_same_instance(self) -> None:
        registry = BackendRegistry()
        target = _sqlite_target("conn")
        assert registry.backend_for(target) is registry.backend_for(target)

    def test_equal_targets_share_backend(self) -> None:
        """Two distinct-but-equal targets map to the same cached backend."""
        registry = BackendRegistry()
        first = registry.backend_for(_sqlite_target("conn"))
        second = registry.backend_for(_sqlite_target("conn"))
        assert first is second

    def test_distinct_targets_get_distinct_backends(self) -> None:
        registry = BackendRegistry()
        a = registry.backend_for(_sqlite_target("a"))
        b = registry.backend_for(_sqlite_target("b"))
        assert a is not b

    def test_returns_database_backend(self) -> None:
        registry = BackendRegistry()
        backend = registry.backend_for(_sqlite_target("conn"))
        assert isinstance(backend, DatabaseBackend)


# ---------------------------------------------------------------------------
# Lazy connection
# ---------------------------------------------------------------------------


class TestLazyConnect:
    """backend_for creates but never eagerly connects the backend."""

    def test_does_not_connect_eagerly(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _install_fake_create(monkeypatch, lambda config: _FakeBackend())
        registry = BackendRegistry()
        backend = registry.backend_for(_sqlite_target("conn"))
        assert isinstance(backend, _FakeBackend)
        assert backend.connected is False

    def test_real_backend_not_connected(self) -> None:
        """A real sqlite backend opens no connection until a query runs."""
        registry = BackendRegistry()
        backend = registry.backend_for(_sqlite_target("conn"))
        # SQLiteBackend keeps its connection lazily on ``_connection``.
        assert getattr(backend, "_connection") is None


# ---------------------------------------------------------------------------
# close_all
# ---------------------------------------------------------------------------


class TestCloseAll:
    """close_all closes every backend and survives per-backend errors."""

    def test_closes_every_backend(self, monkeypatch: pytest.MonkeyPatch) -> None:
        created: list[_FakeBackend] = []

        def factory(config: ConnectionConfig) -> _FakeBackend:
            backend = _FakeBackend()
            created.append(backend)
            return backend

        _install_fake_create(monkeypatch, factory)
        registry = BackendRegistry()
        registry.backend_for(_sqlite_target("a"))
        registry.backend_for(_sqlite_target("b"))

        registry.close_all()

        assert len(created) == 2
        assert all(backend.close_calls == 1 for backend in created)

    def test_continues_past_backend_that_raises(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        created: list[_FakeBackend] = []

        def factory(config: ConnectionConfig) -> _FakeBackend:
            backend = _FakeBackend(close_raises=len(created) == 0)
            created.append(backend)
            return backend

        _install_fake_create(monkeypatch, factory)
        registry = BackendRegistry()
        registry.backend_for(_sqlite_target("a"))
        registry.backend_for(_sqlite_target("b"))

        registry.close_all()  # must not propagate the first backend's error

        assert created[0].close_calls == 1
        assert created[1].close_calls == 1

    def test_close_all_when_empty_is_noop(self) -> None:
        registry = BackendRegistry()
        registry.close_all()  # no backends created; must not raise
