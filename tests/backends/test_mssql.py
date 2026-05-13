"""Unit tests for MSSQL connection-string builder helpers."""

from __future__ import annotations

from mcp_tools_sql.backends.mssql import _build_connection_string, _odbc_escape
from mcp_tools_sql.config.models import ConnectionConfig


class TestOdbcEscape:
    """Tests for `_odbc_escape`."""

    def test_plain_value_unchanged(self) -> None:
        assert _odbc_escape("plain") == "plain"

    def test_value_with_semicolon_wrapped(self) -> None:
        assert _odbc_escape("a;b") == "{a;b}"

    def test_value_with_equals_wrapped(self) -> None:
        assert _odbc_escape("a=b") == "{a=b}"

    def test_value_with_opening_brace_wrapped(self) -> None:
        assert _odbc_escape("a{b") == "{a{b}"

    def test_value_with_closing_brace_doubled(self) -> None:
        assert _odbc_escape("a}b") == "{a}}b}"

    def test_value_with_leading_space_wrapped(self) -> None:
        assert _odbc_escape(" a") == "{ a}"

    def test_value_with_trailing_space_wrapped(self) -> None:
        assert _odbc_escape("a ") == "{a }"

    def test_empty_value_returned_empty(self) -> None:
        assert _odbc_escape("") == ""


class TestConnectionStringBuilder:
    """Tests for `_build_connection_string`."""

    def test_password_auth_basic(self) -> None:
        c = ConnectionConfig(
            backend="mssql",
            host="h",
            port=1433,
            database="d",
            username="u",
            password="p",
        )
        s = _build_connection_string(c)
        assert "Server=h,1433" in s
        assert "UID=u" in s and "PWD=p" in s
        assert "Trusted_Connection" not in s
        assert "Encrypt=yes" in s
        assert "TrustServerCertificate=no" in s

    def test_trusted_connection_omits_uid_pwd(self) -> None:
        c = ConnectionConfig(
            backend="mssql",
            host="h",
            port=1433,
            database="d",
            trusted_connection=True,
        )
        s = _build_connection_string(c)
        assert "Trusted_Connection=yes" in s
        assert "UID=" not in s and "PWD=" not in s

    def test_port_zero_defaults_to_1433(self) -> None:
        c = ConnectionConfig(
            backend="mssql",
            host="h",
            port=0,
            database="d",
            trusted_connection=True,
        )
        assert "Server=h,1433" in _build_connection_string(c)

    def test_port_uses_comma_not_colon(self) -> None:
        c = ConnectionConfig(
            backend="mssql",
            host="h",
            port=1234,
            database="d",
            trusted_connection=True,
        )
        s = _build_connection_string(c)
        assert "Server=h,1234" in s
        assert "h:1234" not in s

    def test_password_with_semicolon_escaped(self) -> None:
        c = ConnectionConfig(
            backend="mssql",
            host="h",
            port=1433,
            database="d",
            username="u",
            password="a;b",
        )
        assert "PWD={a;b}" in _build_connection_string(c)

    def test_password_with_brace_doubled(self) -> None:
        c = ConnectionConfig(
            backend="mssql",
            host="h",
            port=1433,
            database="d",
            username="u",
            password="a}b",
        )
        assert "PWD={a}}b}" in _build_connection_string(c)

    def test_encrypt_false(self) -> None:
        c = ConnectionConfig(
            backend="mssql",
            host="h",
            port=1433,
            database="d",
            trusted_connection=True,
            encrypt=False,
        )
        assert "Encrypt=no" in _build_connection_string(c)

    def test_trust_server_certificate_true(self) -> None:
        c = ConnectionConfig(
            backend="mssql",
            host="h",
            port=1433,
            database="d",
            trusted_connection=True,
            trust_server_certificate=True,
        )
        assert "TrustServerCertificate=yes" in _build_connection_string(c)

    def test_driver_wrapped_in_braces(self) -> None:
        c = ConnectionConfig(
            backend="mssql",
            host="h",
            port=1433,
            database="d",
            trusted_connection=True,
            driver="ODBC Driver 18 for SQL Server",
        )
        assert "Driver={ODBC Driver 18 for SQL Server}" in _build_connection_string(c)

    def test_no_trailing_semicolon(self) -> None:
        c = ConnectionConfig(
            backend="mssql",
            host="h",
            port=1433,
            database="d",
            trusted_connection=True,
        )
        assert not _build_connection_string(c).endswith(";")

    def test_database_with_semicolon_escaped(self) -> None:
        c = ConnectionConfig(
            backend="mssql",
            host="h",
            port=1433,
            database="db;weird",
            trusted_connection=True,
        )
        assert "Database={db;weird}" in _build_connection_string(c)
