"""Tests for Pydantic configuration models."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from mcp_tools_sql.config.models import (
    BackendQueryConfig,
    ConnectionConfig,
    DatabaseConfig,
    QueryConfig,
    QueryFileConfig,
    QueryParamConfig,
    UpdateConfig,
    UpdateFieldConfig,
)


class TestUpdateConfigAlias:
    """Tests for UpdateConfig schema alias mapping."""

    def test_schema_alias_from_toml_key(self) -> None:
        """UpdateConfig accepts 'schema' (TOML key) and maps to schema_name."""
        config = UpdateConfig(schema="dbo")
        assert config.schema_name == "dbo"

    def test_schema_name_direct(self) -> None:
        """UpdateConfig accepts 'schema_name' (Python name) directly."""
        config = UpdateConfig.model_validate({"schema_name": "dbo"})
        assert config.schema_name == "dbo"

    def test_schema_alias_in_dict_output(self) -> None:
        """model_dump(by_alias=True) uses 'schema' key."""
        config = UpdateConfig(schema="dbo")
        dumped = config.model_dump(by_alias=True)
        assert dumped["schema"] == "dbo"


class TestModelValidation:
    """Tests for model validation and defaults."""

    def test_query_config_requires_sql(self) -> None:
        """QueryConfig raises ValidationError without sql field."""
        with pytest.raises(ValidationError):
            QueryConfig()  # type: ignore[call-arg]

    def test_query_file_config_defaults(self) -> None:
        """QueryFileConfig has empty defaults for all fields."""
        config = QueryFileConfig()
        assert config.connection == ""
        assert config.queries == {}
        assert config.updates == {}

    def test_database_config_defaults(self) -> None:
        """DatabaseConfig defaults: empty connections, security.allow_updates=True."""
        config = DatabaseConfig()
        assert config.connections == {}
        assert config.security.allow_updates is True

    def test_connection_config_defaults(self) -> None:
        """ConnectionConfig defaults to sqlite backend."""
        config = ConnectionConfig()
        assert config.backend == "sqlite"

    def test_connection_config_driver_default(self) -> None:
        """ConnectionConfig.driver defaults to the standard MSSQL ODBC driver."""
        config = ConnectionConfig()
        assert config.driver == "ODBC Driver 18 for SQL Server"

    def test_connection_config_no_connection_string_field(self) -> None:
        """ConnectionConfig no longer exposes a connection_string field."""
        assert not hasattr(ConnectionConfig(), "connection_string")

    def test_query_file_config_nested_parsing(self) -> None:
        """QueryFileConfig parses nested queries with params from dict."""
        data = {
            "connection": "mydb",
            "queries": {
                "get_users": {
                    "sql": "SELECT * FROM users WHERE id = :id",
                    "params": {
                        "id": {
                            "name": "id",
                            "type": "int",
                            "description": "User ID",
                            "required": True,
                        }
                    },
                }
            },
        }
        config = QueryFileConfig.model_validate(data)
        assert config.connection == "mydb"
        query = config.queries["get_users"]
        assert query.sql == "SELECT * FROM users WHERE id = :id"
        param = query.params["id"]
        assert isinstance(param, QueryParamConfig)
        assert param.type == "int"


class TestBackendQueryConfig:
    """Tests for BackendQueryConfig model."""

    def test_basic_creation(self) -> None:
        """BackendQueryConfig stores a SQL override string."""
        config = BackendQueryConfig(sql="SELECT 1")
        assert config.sql == "SELECT 1"


class TestQueryConfigResolveSQL:
    """Tests for QueryConfig.resolve_sql() method."""

    def test_override_present(self) -> None:
        """resolve_sql returns backend-specific SQL when override exists."""
        config = QueryConfig(
            sql="DEFAULT",
            backends={"sqlite": BackendQueryConfig(sql="SQLITE")},
        )
        assert config.resolve_sql("sqlite") == "SQLITE"

    def test_override_absent_fallback(self) -> None:
        """resolve_sql returns default SQL when backend has no override."""
        config = QueryConfig(
            sql="DEFAULT",
            backends={"sqlite": BackendQueryConfig(sql="SQLITE")},
        )
        assert config.resolve_sql("mssql") == "DEFAULT"

    def test_no_backends_fallback(self) -> None:
        """resolve_sql returns default SQL when no backends configured."""
        config = QueryConfig(sql="DEFAULT")
        assert config.resolve_sql("sqlite") == "DEFAULT"


class TestQueryConfigMaxRows:
    """Tests for max_rows_default / max_rows_hard validator behavior."""

    def test_max_rows_hard_defaults_to_default(self) -> None:
        """max_rows_hard defaults to max_rows_default when omitted."""
        config = QueryConfig(sql="SELECT 1", max_rows_default=25)
        assert config.max_rows_hard == 25

    def test_max_rows_hard_explicit_value(self) -> None:
        """Explicit max_rows_hard is preserved by validator."""
        config = QueryConfig(sql="SELECT 1", max_rows_default=10, max_rows_hard=50)
        assert config.max_rows_default == 10
        assert config.max_rows_hard == 50


class TestQueryConfigFilterColumn:
    """Tests for filter_column field."""

    def test_filter_column_default_empty(self) -> None:
        """filter_column defaults to empty string."""
        config = QueryConfig(sql="SELECT 1")
        assert config.filter_column == ""

    def test_filter_column_explicit_value(self) -> None:
        """Explicit filter_column is preserved."""
        config = QueryConfig(sql="SELECT 1", filter_column="name")
        assert config.filter_column == "name"


class TestUpdateFieldConfigRequired:
    """Tests for UpdateFieldConfig.required attribute."""

    def test_required_defaults_to_false(self) -> None:
        """UpdateFieldConfig.required defaults to False (partial updates)."""
        config = UpdateFieldConfig(field="x")
        assert config.required is False

    def test_required_override_true(self) -> None:
        """UpdateFieldConfig honours required=True override."""
        config = UpdateFieldConfig(field="x", required=True)
        assert config.required is True

    def test_required_parsed_from_toml_dict(self) -> None:
        """UpdateConfig parses nested fields with required from dict."""
        data = {
            "updates": {
                "foo": {
                    "fields": [
                        {"field": "x", "required": True},
                        {"field": "y"},
                    ]
                }
            }
        }
        config = QueryFileConfig.model_validate(data)
        update = config.updates["foo"]
        assert update.fields[0].required is True
        assert update.fields[1].required is False


class TestQueryConfigBackendsParsing:
    """Tests for parsing backends from nested dict (TOML structure)."""

    def test_nested_dict_parsing(self) -> None:
        """QueryConfig parses nested backends dict like TOML would produce."""
        data = {
            "sql": "SELECT * FROM information_schema.tables",
            "backends": {
                "sqlite": {"sql": "SELECT name FROM sqlite_master WHERE type='table'"}
            },
        }
        config = QueryConfig.model_validate(data)
        assert config.resolve_sql("sqlite") == (
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
        assert config.resolve_sql("mssql") == (
            "SELECT * FROM information_schema.tables"
        )
