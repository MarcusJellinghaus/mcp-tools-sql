"""Pydantic configuration models for mcp-tools-sql."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class ConnectionConfig(BaseModel):
    """Database connection parameters (stored in user config)."""

    backend: str = "sqlite"  # sqlite | mssql | postgresql
    host: str = ""
    port: int = 0
    database: str = ""
    username: str = ""
    password: str = ""
    trusted_connection: bool = False
    credential_env_var: str = ""
    connection_string: str = ""
    path: str = ""  # SQLite file path


class QueryParamConfig(BaseModel):
    """Definition of a single query parameter."""

    name: str
    type: str = "str"  # str | int | float | datetime
    description: str = ""
    required: bool = True


class QueryConfig(BaseModel):
    """A configured SELECT query that becomes an MCP tool."""

    description: str = ""
    sql: str
    params: dict[str, QueryParamConfig] = {}
    max_rows: int = 100


class UpdateFieldConfig(BaseModel):
    """A field that can be updated."""

    field: str
    type: str = "str"
    description: str = ""


class UpdateKeyConfig(BaseModel):
    """Unique key that identifies the row to update."""

    field: str
    type: str = "int"
    description: str = ""


class UpdateConfig(BaseModel):
    """A configured UPDATE definition that becomes an MCP tool."""

    description: str = ""
    schema_name: str = ""  # 'schema' is a Pydantic reserved name
    table: str = ""
    key: Optional[UpdateKeyConfig] = None
    fields: list[UpdateFieldConfig] = []


class SecurityConfig(BaseModel):
    """Security settings (phase 2/3 placeholder)."""

    allow_updates: bool = True


class QueryFileConfig(BaseModel):
    """Root model for the project query config file (mcp-tools-sql.toml)."""

    connection: str = ""  # named connection reference
    queries: dict[str, QueryConfig] = {}
    updates: dict[str, UpdateConfig] = {}


class UserConfig(BaseModel):
    """Root model for user config (~/.mcp-tools-sql/config.toml)."""

    connections: dict[str, ConnectionConfig] = {}
    security: SecurityConfig = SecurityConfig()
