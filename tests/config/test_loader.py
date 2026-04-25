"""Tests for TOML config loading functions."""

from __future__ import annotations

import logging
import stat
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from mcp_tools_sql.config.loader import load_query_config, load_user_config
from mcp_tools_sql.config.models import QueryFileConfig, UserConfig


class TestLoadQueryConfig:
    """Tests for load_query_config."""

    def test_valid_query_config(self, tmp_path: Path) -> None:
        """Loads a complete mcp-tools-sql.toml exercising all nested models."""
        toml_content = """\
connection = "mydb"

[queries.get_users]
description = "Find users by department"
sql = "SELECT * FROM users WHERE dept = :dept"
max_rows = 50

[queries.get_users.params.dept]
name = "dept"
type = "str"
description = "Department name"
required = true

[updates.update_email]
description = "Update user email"
schema = "dbo"
table = "users"

[updates.update_email.key]
field = "id"
type = "int"
description = "User ID"

[[updates.update_email.fields]]
field = "email"
type = "str"
description = "New email address"
"""
        config_file = tmp_path / "mcp-tools-sql.toml"
        config_file.write_text(toml_content)

        config = load_query_config(config_file)

        assert isinstance(config, QueryFileConfig)
        assert config.connection == "mydb"
        assert "get_users" in config.queries
        assert config.queries["get_users"].max_rows == 50
        assert config.queries["get_users"].params["dept"].type == "str"
        assert "update_email" in config.updates
        assert config.updates["update_email"].schema_name == "dbo"
        assert config.updates["update_email"].table == "users"
        assert config.updates["update_email"].fields[0].field == "email"

    def test_empty_file_returns_defaults(self, tmp_path: Path) -> None:
        """Empty TOML file returns QueryFileConfig with defaults."""
        config_file = tmp_path / "mcp-tools-sql.toml"
        config_file.write_text("")

        config = load_query_config(config_file)

        assert config.connection == ""
        assert config.queries == {}
        assert config.updates == {}

    def test_missing_file_raises_value_error(self, tmp_path: Path) -> None:
        """Non-existent path raises ValueError with file path in message."""
        missing = tmp_path / "nonexistent.toml"

        with pytest.raises(ValueError, match="nonexistent.toml"):
            load_query_config(missing)

    def test_invalid_toml_raises_value_error(self, tmp_path: Path) -> None:
        """Malformed TOML raises ValueError with file path and line info."""
        config_file = tmp_path / "bad.toml"
        config_file.write_text("[invalid\n")

        with pytest.raises(ValueError, match="bad.toml"):
            load_query_config(config_file)

    def test_credential_warning(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """password in query config triggers a log warning."""
        toml_content = """\
connection = "mydb"
password = "secret123"
"""
        config_file = tmp_path / "mcp-tools-sql.toml"
        config_file.write_text(toml_content)

        with caplog.at_level(logging.WARNING):
            load_query_config(config_file)

        assert any("password" in record.message for record in caplog.records)

    def test_extra_fields_ignored(self, tmp_path: Path) -> None:
        """Unknown TOML keys are silently ignored by Pydantic."""
        toml_content = """\
connection = "mydb"
unknown_key = "should be ignored"
another_extra = 42
"""
        config_file = tmp_path / "mcp-tools-sql.toml"
        config_file.write_text(toml_content)

        config = load_query_config(config_file)

        assert config.connection == "mydb"

    def test_schema_alias_through_toml(self, tmp_path: Path) -> None:
        """TOML 'schema = dbo' maps to UpdateConfig.schema_name."""
        toml_content = """\
[updates.fix_record]
schema = "dbo"
table = "records"
"""
        config_file = tmp_path / "mcp-tools-sql.toml"
        config_file.write_text(toml_content)

        config = load_query_config(config_file)

        assert config.updates["fix_record"].schema_name == "dbo"


class TestLoadUserConfig:
    """Tests for load_user_config."""

    def test_valid_user_config(self, tmp_path: Path) -> None:
        """Loads user config with multiple named connections."""
        toml_content = """\
[connections.local_sqlite]
backend = "sqlite"
path = "./test.db"

[connections.prod_mssql]
backend = "mssql"
host = "db.example.com"
port = 1433
database = "mydb"
username = "admin"
password = "secret"
"""
        config_file = tmp_path / "config.toml"
        config_file.write_text(toml_content)

        config = load_user_config(config_file)

        assert isinstance(config, UserConfig)
        assert "local_sqlite" in config.connections
        assert config.connections["local_sqlite"].backend == "sqlite"
        assert "prod_mssql" in config.connections
        assert config.connections["prod_mssql"].host == "db.example.com"
        assert config.connections["prod_mssql"].password == "secret"

    def test_none_path_uses_default(self, tmp_path: Path) -> None:
        """None path defaults to ~/.mcp-tools-sql/config.toml."""
        # Point home to tmp_path so the default file won't exist
        with patch("mcp_tools_sql.config.loader.Path.home", return_value=tmp_path):
            config = load_user_config(None)

        assert isinstance(config, UserConfig)
        assert config.connections == {}

    def test_missing_file_returns_defaults(self, tmp_path: Path) -> None:
        """Non-existent file returns UserConfig() with empty connections."""
        missing = tmp_path / "nonexistent.toml"

        config = load_user_config(missing)

        assert isinstance(config, UserConfig)
        assert config.connections == {}

    def test_invalid_toml_raises_value_error(self, tmp_path: Path) -> None:
        """Malformed user config raises ValueError."""
        config_file = tmp_path / "config.toml"
        config_file.write_text("[broken\n")

        with pytest.raises(ValueError, match="config.toml"):
            load_user_config(config_file)

    @pytest.mark.skipif(
        sys.platform == "win32", reason="Cannot reliably remove read on Windows"
    )
    def test_unreadable_file_raises_value_error(self, tmp_path: Path) -> None:
        """Existing but unreadable file raises ValueError (OSError wrapping)."""
        config_file = tmp_path / "config.toml"
        config_file.write_text("[connections]\n")
        config_file.chmod(0o000)

        try:
            with pytest.raises(ValueError, match=str(config_file)):
                load_user_config(config_file)
        finally:
            config_file.chmod(stat.S_IRUSR | stat.S_IWUSR)
