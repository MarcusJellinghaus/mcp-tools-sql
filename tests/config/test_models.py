"""Tests for Pydantic configuration models."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from mcp_tools_sql.config.models import (
    ConnectionConfig,
    QueryConfig,
    QueryFileConfig,
    QueryParamConfig,
    UpdateConfig,
    UserConfig,
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

    def test_user_config_defaults(self) -> None:
        """UserConfig defaults: empty connections, security.allow_updates=True."""
        config = UserConfig()
        assert config.connections == {}
        assert config.security.allow_updates is True

    def test_connection_config_defaults(self) -> None:
        """ConnectionConfig defaults to sqlite backend."""
        config = ConnectionConfig()
        assert config.backend == "sqlite"

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
