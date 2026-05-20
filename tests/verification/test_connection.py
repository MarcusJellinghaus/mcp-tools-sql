"""Tests for ``mcp_tools_sql.verification.connection``."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from mcp_tools_sql.backends.base import DatabaseBackend
from mcp_tools_sql.backends.sqlite import SQLiteBackend
from mcp_tools_sql.config.models import ConnectionConfig
from mcp_tools_sql.verification import verify_connection


def _sqlite_connection(path: Path) -> ConnectionConfig:
    """Build a ConnectionConfig pointing at the given sqlite file."""
    return ConnectionConfig(backend="sqlite", path=str(path))


def test_verify_connection_sqlite_select_1_ok(tmp_path: Path) -> None:
    """Real sqlite tmp file → all rows ok=True, select_1 value 'ok'."""
    db_path = tmp_path / "real.sqlite"
    db_path.write_bytes(b"")
    result, open_backend = verify_connection(_sqlite_connection(db_path))
    try:
        assert result["backend"]["ok"] is True
        assert result["path"]["ok"] is True
        assert result["select_1"]["ok"] is True
        assert result["select_1"]["value"] == "ok"
        assert result["overall_ok"] is True
    finally:
        if open_backend is not None:
            open_backend.close()


def test_verify_connection_sqlite_missing_path() -> None:
    """Empty path → ok=False with helpful error and select_1 fails."""
    conn = ConnectionConfig(backend="sqlite", path="")
    result, open_backend = verify_connection(conn)
    try:
        assert result["path"]["ok"] is False
        assert "must be set" in result["path"]["error"]
        assert result["select_1"]["ok"] is False
        assert result["overall_ok"] is False
    finally:
        if open_backend is not None:
            open_backend.close()


def test_verify_connection_unimplemented_backend_is_err() -> None:
    """`postgresql` (no impl) → select_1 fails via create_backend ValueError."""
    conn = ConnectionConfig(
        backend="postgresql",
        host="localhost",
        port=5432,
        database="db",
        password="pw",
    )
    result, open_backend = verify_connection(conn)
    try:
        assert result["select_1"]["ok"] is False
        assert "Unsupported backend" in result["select_1"]["error"]
    finally:
        if open_backend is not None:
            open_backend.close()


def test_verify_connection_credentials_password_set() -> None:
    """Password resolved → credentials row ok=True."""
    conn = ConnectionConfig(
        backend="mssql",
        host="h",
        port=1433,
        database="d",
        password="resolved",
    )
    result, open_backend = verify_connection(conn)
    try:
        assert result["credentials"]["ok"] is True
    finally:
        if open_backend is not None:
            open_backend.close()


def test_verify_connection_credentials_missing_for_mssql() -> None:
    """No password or trusted_connection for mssql → credentials row ok=False."""
    conn = ConnectionConfig(backend="mssql", host="h", port=1433, database="d")
    result, open_backend = verify_connection(conn)
    try:
        assert result["credentials"]["ok"] is False
    finally:
        if open_backend is not None:
            open_backend.close()


def test_verify_connection_returns_open_backend_on_success(tmp_path: Path) -> None:
    """On success the second element is a connected DatabaseBackend instance."""
    db_path = tmp_path / "real.sqlite"
    db_path.write_bytes(b"")
    result, open_backend = verify_connection(_sqlite_connection(db_path))
    try:
        assert result["overall_ok"] is True
        assert open_backend is not None
        assert isinstance(open_backend, DatabaseBackend)
        assert isinstance(open_backend, SQLiteBackend)
        # The backend is connected — a second SELECT should work without re-connect.
        rows = open_backend.execute_query("SELECT 1 AS one")
        assert rows == [{"one": 1}]
    finally:
        if open_backend is not None:
            open_backend.close()


def test_verify_connection_returns_none_backend_on_failure() -> None:
    """On select_1 failure the second tuple element is None."""
    conn = ConnectionConfig(backend="sqlite", path="")
    result, open_backend = verify_connection(conn)
    assert result["select_1"]["ok"] is False
    assert open_backend is None


# ---------------------------------------------------------------------------
# Kerberos check (Linux + mssql + trusted_connection)
# ---------------------------------------------------------------------------


@pytest.fixture
def linux_platform(monkeypatch: pytest.MonkeyPatch) -> None:
    """Force ``sys.platform`` to ``"linux"`` for the duration of the test."""
    monkeypatch.setattr(sys, "platform", "linux")


def _trusted_mssql() -> ConnectionConfig:
    """Return an mssql ConnectionConfig with ``trusted_connection=True``."""
    return ConnectionConfig(
        backend="mssql",
        host="h",
        port=1433,
        database="d",
        trusted_connection=True,
    )


@pytest.fixture
def stub_create_backend(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """Replace ``connection.create_backend`` so tests never touch real pyodbc.

    Returns the factory mock; the backend it returns stubs ``connect``,
    ``execute_query`` and ``close`` so ``verify_connection`` reaches the
    Kerberos branch without errors.
    """
    backend = MagicMock(name="stub_backend")
    backend.connect.return_value = None
    backend.execute_query.return_value = [{"v": 1}]
    backend.close.return_value = None
    factory = MagicMock(return_value=backend)
    monkeypatch.setattr(
        "mcp_tools_sql.verification.connection.create_backend",
        factory,
    )
    return factory


def test_klist_zero_returns_ok(
    monkeypatch: pytest.MonkeyPatch,
    linux_platform: None,  # pylint: disable=unused-argument
    stub_create_backend: MagicMock,  # pylint: disable=unused-argument
) -> None:
    """``klist -s`` exits 0 → kerberos_ticket row ok=True."""
    proc = MagicMock(returncode=0)
    monkeypatch.setattr("subprocess.run", MagicMock(return_value=proc))
    result, _ = verify_connection(_trusted_mssql())
    assert result["kerberos_ticket"]["ok"] is True


def test_klist_nonzero_returns_err(
    monkeypatch: pytest.MonkeyPatch,
    linux_platform: None,  # pylint: disable=unused-argument
    stub_create_backend: MagicMock,  # pylint: disable=unused-argument
) -> None:
    """``klist -s`` exits non-zero → kerberos_ticket row ok=False."""
    proc = MagicMock(returncode=1)
    monkeypatch.setattr("subprocess.run", MagicMock(return_value=proc))
    result, _ = verify_connection(_trusted_mssql())
    assert result["kerberos_ticket"]["ok"] is False
    error = result["kerberos_ticket"]["error"].lower()
    assert "kinit" in error or "ticket" in error


def test_klist_missing_returns_err(
    monkeypatch: pytest.MonkeyPatch,
    linux_platform: None,  # pylint: disable=unused-argument
    stub_create_backend: MagicMock,  # pylint: disable=unused-argument
) -> None:
    """``klist`` not installed → kerberos_ticket row ok=False."""
    monkeypatch.setattr("subprocess.run", MagicMock(side_effect=FileNotFoundError()))
    result, _ = verify_connection(_trusted_mssql())
    assert result["kerberos_ticket"]["ok"] is False


def test_non_linux_platforms_skip_check(
    monkeypatch: pytest.MonkeyPatch,
    stub_create_backend: MagicMock,  # pylint: disable=unused-argument
) -> None:
    """On non-Linux platforms no kerberos_ticket row is added."""
    monkeypatch.setattr(sys, "platform", "win32")
    result, _ = verify_connection(_trusted_mssql())
    assert "kerberos_ticket" not in result


def test_non_trusted_skips_check(
    linux_platform: None,  # pylint: disable=unused-argument
    stub_create_backend: MagicMock,  # pylint: disable=unused-argument
) -> None:
    """Password auth (no trusted_connection) → no kerberos_ticket row."""
    conn = ConnectionConfig(
        backend="mssql", host="h", port=1433, database="d", password="p"
    )
    result, _ = verify_connection(conn)
    assert "kerberos_ticket" not in result
