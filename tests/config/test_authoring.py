"""Tests for the config authoring builders."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from mcp_tools_sql.config.authoring import build_query_config, build_update_config


class TestBuildQueryConfig:
    """Tests for build_query_config."""

    def test_auto_fills_param_name_from_dict_key(self) -> None:
        """Dict key for params auto-populates the param's name field."""
        cfg = build_query_config(
            "get_user",
            sql="SELECT * FROM users WHERE id = :id",
            params={"id": {"type": "int"}},
        )
        assert cfg.params["id"].name == "id"

    def test_dict_key_overrides_inner_name(self) -> None:
        """Dict key wins over mismatched inner 'name' silently."""
        cfg = build_query_config(
            "get_user",
            sql="SELECT * FROM users WHERE id = :id",
            params={"id": {"name": "other", "type": "int"}},
        )
        assert cfg.params["id"].name == "id"

    def test_invalid_sql_raises_validation_error(self) -> None:
        """Pydantic ValidationError propagates (sql=None violates model)."""
        with pytest.raises(ValidationError):
            build_query_config("broken", sql=None)  # type: ignore[arg-type]


class TestBuildUpdateConfig:
    """Tests for build_update_config."""

    def test_happy_path_schema_alias(self) -> None:
        """schema= kwarg lands on schema_name via the alias path."""
        ucfg = build_update_config(
            "set_user_email",
            schema="dbo",
            table="users",
            key={"field": "id", "type": "int"},
            fields=[{"field": "email", "type": "str"}],
        )
        assert ucfg.schema_name == "dbo"
        assert ucfg.table == "users"
        assert ucfg.key is not None
        assert ucfg.key.field == "id"
        assert [f.field for f in ucfg.fields] == ["email"]

    def test_invalid_key_raises_validation_error(self) -> None:
        """key dict missing required 'field' propagates pydantic ValidationError."""
        with pytest.raises(ValidationError):
            build_update_config(
                "broken",
                table="users",
                key={"type": "int"},
                fields=[{"field": "email"}],
            )
