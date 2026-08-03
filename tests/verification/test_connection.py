"""Tests for ``mcp_tools_sql.verification.connection``."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from mcp_tools_sql.backends.base import create_backend
from mcp_tools_sql.backends.sqlite import SQLiteBackend
from mcp_tools_sql.config.models import ConnectionConfig, ResolvedTarget
from mcp_tools_sql.verification import verify_connection


def _target(
    config: ConnectionConfig,
    *,
    connection: str = "conn",
    database: str = "main",
    is_default: bool = True,
) -> ResolvedTarget:
    """Wrap a ConnectionConfig in a ResolvedTarget for one pair."""
    return ResolvedTarget(
        connection=connection,
        database=database,
        config=config,
        backend_name=config.backend,
        is_default=is_default,
    )


def _sqlite_connection(path: Path) -> ConnectionConfig:
    """Build a ConnectionConfig pointing at the given sqlite file."""
    return ConnectionConfig(backend="sqlite", path=str(path))


@pytest.fixture
def ok_backend() -> MagicMock:
    """Return a stub backend whose ``SELECT 1`` probe always succeeds."""
    backend = MagicMock(name="ok_backend")
    backend.connect.return_value = None
    backend.execute_query.return_value = [{"v": 1}]
    backend.close.return_value = None
    return backend


def test_verify_connection_sqlite_select_1_ok(tmp_path: Path) -> None:
    """Real sqlite tmp file + registry backend → all rows ok, select_1 'ok'."""
    db_path = tmp_path / "real.sqlite"
    db_path.write_bytes(b"")
    config = _sqlite_connection(db_path)
    backend = create_backend(config)
    try:
        result = verify_connection(_target(config), backend)
        assert isinstance(backend, SQLiteBackend)
        assert result["backend"]["ok"] is True
        assert result["path"]["ok"] is True
        assert result["select_1"]["ok"] is True
        assert result["select_1"]["value"] == "ok"
        assert result["overall_ok"] is True
    finally:
        backend.close()


def test_verify_connection_sqlite_missing_path() -> None:
    """Empty path → ok=False with helpful error and select_1 fails on connect."""
    config = ConnectionConfig(backend="sqlite", path="")
    backend = create_backend(config)
    try:
        result = verify_connection(_target(config), backend)
        assert result["path"]["ok"] is False
        assert "must be set" in result["path"]["error"]
        assert result["select_1"]["ok"] is False
        assert result["overall_ok"] is False
    finally:
        backend.close()


def test_verify_connection_none_backend_uses_probe_error() -> None:
    """A None backend (creation failed) → select_1 fails with the probe error."""
    conn = ConnectionConfig(
        backend="postgresql",
        host="localhost",
        port=5432,
        database="db",
        password="pw",
    )
    result = verify_connection(
        _target(conn, database="db"),
        None,
        probe_error="Unsupported backend: postgresql",
    )
    assert result["select_1"]["ok"] is False
    assert "Unsupported backend" in result["select_1"]["error"]
    assert result["overall_ok"] is False


def test_verify_connection_none_backend_default_error() -> None:
    """A None backend with no probe error → generic 'backend unavailable'."""
    conn = ConnectionConfig(backend="sqlite", path="/x")
    result = verify_connection(_target(conn), None)
    assert result["select_1"]["ok"] is False
    assert result["select_1"]["error"] == "backend unavailable"


def test_verify_connection_database_row_is_pinned_catalog(
    ok_backend: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The ``database`` row reflects the per-pair pinned catalog under test."""
    monkeypatch.setattr(
        "mcp_tools_sql.verification.connection.socket.gethostbyname",
        MagicMock(return_value="10.0.0.1"),
    )
    conn = ConnectionConfig.model_validate(
        {
            "backend": "mssql",
            "host": "h",
            "port": 1433,
            "databases": ["sales", "hr"],
            "trusted_connection": True,
        }
    )
    pinned = conn.model_copy(update={"database": "hr"})
    result = verify_connection(_target(pinned, database="hr"), ok_backend)
    assert result["database"]["ok"] is True
    assert result["database"]["value"] == "hr"


def test_verify_connection_credentials_password_set(ok_backend: MagicMock) -> None:
    """Password resolved → credentials row ok=True with value 'password'."""
    conn = ConnectionConfig(
        backend="mssql",
        host="h",
        port=1433,
        database="d",
        password="resolved",
    )
    result = verify_connection(_target(conn, database="d"), ok_backend)
    assert result["credentials"]["ok"] is True
    assert result["credentials"]["value"] == "password"


def test_verify_connection_credentials_trusted_only(ok_backend: MagicMock) -> None:
    """trusted_connection=true (no password) → value 'trusted_connection'."""
    conn = ConnectionConfig(
        backend="mssql", host="h", port=1433, database="d", trusted_connection=True
    )
    result = verify_connection(_target(conn, database="d"), ok_backend)
    assert result["credentials"]["ok"] is True
    assert result["credentials"]["value"] == "trusted_connection"


def test_verify_connection_credentials_trusted_and_password(
    ok_backend: MagicMock,
) -> None:
    """Both trusted_connection and password set → value mentions both."""
    conn = ConnectionConfig(
        backend="mssql",
        host="h",
        port=1433,
        database="d",
        trusted_connection=True,
        password="resolved",
    )
    result = verify_connection(_target(conn, database="d"), ok_backend)
    assert result["credentials"]["ok"] is True
    assert "trusted_connection" in result["credentials"]["value"]
    assert "password" in result["credentials"]["value"]


def test_verify_connection_credentials_missing_for_mssql(
    ok_backend: MagicMock,
) -> None:
    """No password or trusted_connection for mssql → credentials row ok=False."""
    conn = ConnectionConfig(backend="mssql", host="h", port=1433, database="d")
    result = verify_connection(_target(conn, database="d"), ok_backend)
    assert result["credentials"]["ok"] is False


def test_verify_connection_host_port_value_with_port_zero(
    ok_backend: MagicMock,
) -> None:
    """port=0 → host_port row shows just the host, not ``host:0``."""
    conn = ConnectionConfig(
        backend="mssql",
        host=r"myserver\inst",
        port=0,
        database="d",
        trusted_connection=True,
    )
    result = verify_connection(_target(conn, database="d"), ok_backend)
    assert result["host_port"]["value"] == r"myserver\inst"
    assert ":0" not in result["host_port"]["value"]


def test_verify_connection_host_port_value_with_explicit_port(
    ok_backend: MagicMock,
) -> None:
    """port > 0 → host_port row shows ``host:port``."""
    conn = ConnectionConfig(
        backend="mssql",
        host="h",
        port=1234,
        database="d",
        trusted_connection=True,
    )
    result = verify_connection(_target(conn, database="d"), ok_backend)
    assert result["host_port"]["value"] == "h:1234"


def test_verify_connection_dns_lookup_success(
    monkeypatch: pytest.MonkeyPatch,
    ok_backend: MagicMock,
) -> None:
    """gethostbyname returns an IP → dns_lookup row ok with that IP."""
    monkeypatch.setattr(
        "mcp_tools_sql.verification.connection.socket.gethostbyname",
        MagicMock(return_value="10.1.2.3"),
    )
    conn = ConnectionConfig(
        backend="mssql",
        host="myserver",
        database="d",
        trusted_connection=True,
    )
    result = verify_connection(_target(conn, database="d"), ok_backend)
    assert result["dns_lookup"]["ok"] is True
    assert result["dns_lookup"]["value"] == "10.1.2.3"


def test_verify_connection_dns_lookup_strips_named_instance(
    monkeypatch: pytest.MonkeyPatch,
    ok_backend: MagicMock,
) -> None:
    """Named-instance host: only the host part is looked up, instance stripped."""
    mock = MagicMock(return_value="10.1.2.3")
    monkeypatch.setattr(
        "mcp_tools_sql.verification.connection.socket.gethostbyname",
        mock,
    )
    conn = ConnectionConfig(
        backend="mssql",
        host=r"myserver\inst",
        database="d",
        trusted_connection=True,
    )
    result = verify_connection(_target(conn, database="d"), ok_backend)
    assert result["dns_lookup"]["ok"] is True
    # gethostbyname should have been called with the host *without* \instance
    mock.assert_called_with("myserver")


def test_verify_connection_dns_lookup_failure(
    monkeypatch: pytest.MonkeyPatch,
    ok_backend: MagicMock,
) -> None:
    """gaierror → dns_lookup row fails, value is host, error mentions DNS."""
    import socket  # pylint: disable=import-outside-toplevel

    monkeypatch.setattr(
        "mcp_tools_sql.verification.connection.socket.gethostbyname",
        MagicMock(side_effect=socket.gaierror("Name or service not known")),
    )
    conn = ConnectionConfig(
        backend="mssql",
        host="no-such-host.invalid",
        database="d",
        trusted_connection=True,
    )
    result = verify_connection(_target(conn, database="d"), ok_backend)
    assert result["dns_lookup"]["ok"] is False
    assert result["dns_lookup"]["value"] == "no-such-host.invalid"
    assert "DNS lookup failed" in result["dns_lookup"]["error"]


def test_verify_connection_sqlite_omits_dns_lookup(tmp_path: Path) -> None:
    """sqlite backend → no dns_lookup row (no host)."""
    db_path = tmp_path / "real.sqlite"
    db_path.write_bytes(b"")
    config = _sqlite_connection(db_path)
    backend = create_backend(config)
    try:
        result = verify_connection(_target(config), backend)
        assert "dns_lookup" not in result
    finally:
        backend.close()


def test_verify_connection_mssql_includes_sanitized_conn_string(
    ok_backend: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """mssql backend → conn_string row present, ok=True, password redacted."""
    # Avoid touching real DNS resolution.
    monkeypatch.setattr(
        "mcp_tools_sql.verification.connection.socket.gethostbyname",
        MagicMock(return_value="10.1.2.3"),
    )
    conn = ConnectionConfig(
        backend="mssql",
        host="h",
        port=1433,
        database="d",
        username="u",
        password="supersecret",
    )
    result = verify_connection(_target(conn, database="d"), ok_backend)
    assert "conn_string" in result
    assert result["conn_string"]["ok"] is True
    value = result["conn_string"]["value"]
    assert "supersecret" not in value
    assert "PWD=***" in value
    assert "Server=h,1433" in value


def test_verify_connection_sqlite_omits_conn_string(tmp_path: Path) -> None:
    """sqlite backend → no conn_string row (mssql-only)."""
    db_path = tmp_path / "real.sqlite"
    db_path.write_bytes(b"")
    config = _sqlite_connection(db_path)
    backend = create_backend(config)
    try:
        result = verify_connection(_target(config), backend)
        assert "conn_string" not in result
    finally:
        backend.close()


def test_verify_connection_host_with_control_char_is_err(
    ok_backend: MagicMock,
) -> None:
    """Host containing a control char (e.g. newline) → host_port row ok=False."""
    conn = ConnectionConfig(
        backend="mssql",
        host="server\name",  # intentional newline — same effect as TOML "server\n"
        port=1433,
        database="d",
        trusted_connection=True,
    )
    result = verify_connection(_target(conn, database="d"), ok_backend)
    assert result["host_port"]["ok"] is False
    # repr() makes the offending character visible in the printed value
    assert "\\n" in result["host_port"]["value"]
    error = result["host_port"]["error"].lower()
    assert "control character" in error
    assert "toml" in error


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


def test_klist_zero_returns_ok(
    monkeypatch: pytest.MonkeyPatch,
    linux_platform: None,  # pylint: disable=unused-argument
    ok_backend: MagicMock,
) -> None:
    """``klist -s`` exits 0 → kerberos_ticket row ok=True."""
    proc = MagicMock(returncode=0)
    monkeypatch.setattr("subprocess.run", MagicMock(return_value=proc))
    result = verify_connection(_target(_trusted_mssql(), database="d"), ok_backend)
    assert result["kerberos_ticket"]["ok"] is True


def test_klist_nonzero_returns_err(
    monkeypatch: pytest.MonkeyPatch,
    linux_platform: None,  # pylint: disable=unused-argument
    ok_backend: MagicMock,
) -> None:
    """``klist -s`` exits non-zero → kerberos_ticket row ok=False."""
    proc = MagicMock(returncode=1)
    monkeypatch.setattr("subprocess.run", MagicMock(return_value=proc))
    result = verify_connection(_target(_trusted_mssql(), database="d"), ok_backend)
    assert result["kerberos_ticket"]["ok"] is False
    error = result["kerberos_ticket"]["error"].lower()
    assert "kinit" in error or "ticket" in error


def test_klist_nonzero_logs_debug(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    linux_platform: None,  # pylint: disable=unused-argument
    ok_backend: MagicMock,
) -> None:
    """``klist -s`` exits non-zero → debug log records exit code + stderr."""
    proc = MagicMock(returncode=1, stderr=b"kinit: no credentials cache")
    monkeypatch.setattr("subprocess.run", MagicMock(return_value=proc))
    with caplog.at_level("DEBUG", logger="mcp_tools_sql.verification.connection"):
        verify_connection(_target(_trusted_mssql(), database="d"), ok_backend)
    debug_lines = [
        r.getMessage()
        for r in caplog.records
        if r.name == "mcp_tools_sql.verification.connection" and r.levelname == "DEBUG"
    ]
    assert any("klist -s exit 1" in line for line in debug_lines)
    assert any("kinit: no credentials cache" in line for line in debug_lines)


def test_klist_missing_returns_err(
    monkeypatch: pytest.MonkeyPatch,
    linux_platform: None,  # pylint: disable=unused-argument
    ok_backend: MagicMock,
) -> None:
    """``klist`` not installed → kerberos_ticket row ok=False."""
    monkeypatch.setattr("subprocess.run", MagicMock(side_effect=FileNotFoundError()))
    result = verify_connection(_target(_trusted_mssql(), database="d"), ok_backend)
    assert result["kerberos_ticket"]["ok"] is False


def test_non_linux_platforms_skip_check(
    monkeypatch: pytest.MonkeyPatch,
    ok_backend: MagicMock,
) -> None:
    """On non-Linux platforms no kerberos_ticket row is added."""
    monkeypatch.setattr(sys, "platform", "win32")
    result = verify_connection(_target(_trusted_mssql(), database="d"), ok_backend)
    assert "kerberos_ticket" not in result


def test_non_trusted_skips_check(
    linux_platform: None,  # pylint: disable=unused-argument
    ok_backend: MagicMock,
) -> None:
    """Password auth (no trusted_connection) → no kerberos_ticket row."""
    conn = ConnectionConfig(
        backend="mssql", host="h", port=1433, database="d", password="p"
    )
    result = verify_connection(_target(conn, database="d"), ok_backend)
    assert "kerberos_ticket" not in result
