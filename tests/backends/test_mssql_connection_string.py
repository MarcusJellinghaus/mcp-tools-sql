"""Unit tests for the MSSQL connection-string and redaction helpers."""

from __future__ import annotations

import pytest

from mcp_tools_sql.backends.mssql import (
    _build_connection_string,
    _odbc_escape,
    _sanitize,
    build_sanitized_connection_string,
)
from mcp_tools_sql.config.models import ConnectionConfig
from tests.backends.conftest import LEAKY_PASSWORDS, _cfg, assert_no_leak


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

    def test_port_zero_omits_port_from_server(self) -> None:
        """port=0 (the model default) → Server=host with no ,port suffix."""
        c = ConnectionConfig(
            backend="mssql",
            host="h",
            port=0,
            database="d",
            trusted_connection=True,
        )
        s = _build_connection_string(c)
        assert "Server=h;" in s
        assert "Server=h," not in s

    def test_named_instance_with_port_zero(self) -> None:
        """host=server\\instance, port=0 → Server=server\\instance (no port).

        This is the form ODBC needs so SQL Browser can resolve the named
        instance's dynamic port. Specifying a port alongside an instance
        name makes ODBC bypass SQL Browser, which is almost never desired.
        """
        c = ConnectionConfig(
            backend="mssql",
            host=r"myserver\inst",
            port=0,
            database="d",
            trusted_connection=True,
        )
        s = _build_connection_string(c)
        assert r"Server=myserver\inst;" in s
        assert ",1433" not in s

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


class TestSanitize:
    """Tests for `_sanitize` against driver text."""

    @pytest.mark.parametrize("password", LEAKY_PASSWORDS)
    def test_escaped_password_redacted(self, password: str) -> None:
        msg = f"Login failed; PWD={_odbc_escape(password)}"
        result = _sanitize(msg, password)
        assert_no_leak(result, password)
        assert "***" in result

    @pytest.mark.parametrize("password", LEAKY_PASSWORDS)
    def test_literal_password_redacted(self, password: str) -> None:
        msg = f"Login failed for password '{password}'"
        result = _sanitize(msg, password)
        assert_no_leak(result, password)
        assert "***" in result

    def test_empty_password_leaves_message_unchanged(self) -> None:
        msg = "Login failed; PWD="
        assert _sanitize(msg, "") == msg


class TestSanitizedConnectionString:
    """Tests for the public ``build_sanitized_connection_string`` helper."""

    def test_password_replaced_with_stars(self) -> None:
        c = ConnectionConfig(
            backend="mssql",
            host="h",
            port=1433,
            database="d",
            username="u",
            password="supersecret",
        )
        s = build_sanitized_connection_string(c)
        assert "supersecret" not in s
        assert "PWD=***" in s

    def test_trusted_connection_no_redaction_marker(self) -> None:
        """trusted_connection has no password → string identical to raw."""
        c = ConnectionConfig(
            backend="mssql",
            host="h",
            port=1433,
            database="d",
            trusted_connection=True,
        )
        s = build_sanitized_connection_string(c)
        assert "Trusted_Connection=yes" in s
        assert "***" not in s
        # No password → result identical to the raw connection string.
        assert s == _build_connection_string(c)

    def test_rest_of_string_matches_raw(self) -> None:
        """All non-password parts match ``_build_connection_string`` output."""
        c = ConnectionConfig(
            backend="mssql",
            host=r"myserver\inst",
            port=0,
            database="d",
            username="u",
            password="secret",
            encrypt=False,
            trust_server_certificate=True,
        )
        # No value in this config contains a semicolon, so splitting is safe.
        raw_parts = _build_connection_string(c).split(";")
        san_parts = build_sanitized_connection_string(c).split(";")
        assert [p for p in san_parts if not p.startswith("PWD=")] == [
            p for p in raw_parts if not p.startswith("PWD=")
        ]
        assert "PWD=***" in san_parts

    @pytest.mark.parametrize("password", LEAKY_PASSWORDS)
    def test_no_password_form_leaks(self, password: str) -> None:
        s = build_sanitized_connection_string(_cfg(password=password))
        assert_no_leak(s, password)
        assert "PWD=***" in s

    def test_empty_password_renders_bare_pwd(self) -> None:
        """An unset password stays visible as a bare ``PWD=``, not ``PWD=***``."""
        s = build_sanitized_connection_string(
            _cfg(password="", trusted_connection=False)
        )
        assert "PWD=" in s
        assert "PWD=***" not in s
