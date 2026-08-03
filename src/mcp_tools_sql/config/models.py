"""Pydantic configuration models for mcp-tools-sql."""

from __future__ import annotations

from typing import Any, Optional, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


class DatabaseSpec(BaseModel):
    """A single database (catalog) within a connection."""

    name: str
    description: str = ""


def _raw_to_specs(raw: Any) -> list[dict[str, Any]]:
    """Normalise the authored ``databases`` value into a list of spec dicts.

    Accepts the list form (``["sales", "hr"]`` or ``[{"name": "sales"}]``) and
    the table form (``{"sales": {"description": "..."}}``), preserving the
    declared order.
    """
    specs: list[dict[str, Any]] = []
    if isinstance(raw, dict):
        for name, value in raw.items():
            if isinstance(value, dict):
                specs.append({"name": name, **value})
            else:
                specs.append({"name": name})
    elif isinstance(raw, list):
        for item in raw:
            if isinstance(item, str):
                specs.append({"name": item})
            elif isinstance(item, dict):
                specs.append(dict(item))
    return specs


class ConnectionConfig(BaseModel):
    """Database connection parameters (stored in database config)."""

    backend: str = "sqlite"  # sqlite | mssql | postgresql
    host: str = ""
    port: int = 0
    database: str = ""  # legacy single-database input alias (kept populated)
    databases: list[DatabaseSpec] = []  # internal normalised catalog list
    default_database: str = ""
    description: str = ""
    username: str = ""
    password: str = ""
    trusted_connection: bool = False
    encrypt: bool = True
    trust_server_certificate: bool = False
    driver: str = "ODBC Driver 18 for SQL Server"  # MSSQL only
    path: str = ""  # SQLite file path

    @model_validator(mode="before")
    @classmethod
    def _normalise_databases(cls, data: Any) -> Any:
        """Normalise the three input forms into ``databases`` + ``default_database``.

        Runs the rule 7 conflict check against the raw authored values *before*
        the legacy ``database`` field is overwritten.
        """
        if not isinstance(data, dict):
            return data
        if data.get("backend", "sqlite") == "sqlite":
            data["databases"] = [{"name": "main"}]
            data["default_database"] = "main"
            data["database"] = "main"
            return data
        legacy = data.get("database")
        raw = data.get("databases")
        source = raw if raw else ([legacy] if legacy else [])
        specs = _raw_to_specs(source)
        default_db = data.get("default_database") or (specs[0]["name"] if specs else "")
        # rule 7: legacy `database` disagreeing with an explicit `databases`.
        if legacy and data.get("databases") is not None:
            names = [s["name"] for s in specs]
            if legacy not in names or (
                data.get("default_database") and legacy != default_db
            ):
                raise ValueError(
                    "`database` conflicts with `databases`/`default_database`"
                )
        data["databases"] = specs
        data["default_database"] = default_db
        data["database"] = default_db  # keep legacy field valid for Steps 3-5
        return data

    @model_validator(mode="after")
    def _validate_databases(self) -> Self:
        """Validate membership and per-backend cardinality rules."""
        names = [d.name for d in self.databases]
        if self.default_database and self.default_database not in names:
            raise ValueError(
                f"default_database '{self.default_database}' is not one of "
                f"the configured databases: {names}"
            )
        if self.backend in ("mssql", "pyodbc") and not self.databases:
            raise ValueError(
                f"{self.backend} connection requires at least one database "
                "(set `database` or `databases`)"
            )
        if self.backend == "postgresql" and len(self.databases) != 1:
            raise ValueError(
                "postgresql connection requires exactly one database, got "
                f"{len(self.databases)}"
            )
        return self


class QueryParamConfig(BaseModel):
    """Definition of a single query parameter."""

    name: str
    type: str = "str"  # str | int | float | datetime
    description: str = ""
    required: bool = True


class BackendQueryConfig(BaseModel):
    """Per-backend SQL override for a query."""

    sql: str


class QueryConfig(BaseModel):
    """A configured SELECT query that becomes an MCP tool."""

    description: str = ""
    sql: str
    params: dict[str, QueryParamConfig] = {}
    max_rows_default: int = 100
    max_rows_hard: int | None = None
    filter_column: str = ""
    backends: dict[str, BackendQueryConfig] = {}
    connection: str = ""  # pinned connection name (optional)
    database: str = ""  # pinned database name (optional)

    @model_validator(mode="after")
    def _default_max_rows_hard(self) -> Self:
        if self.max_rows_hard is None:
            self.max_rows_hard = self.max_rows_default
        return self

    def resolve_sql(self, backend_name: str) -> str:
        """Return backend-specific SQL if override exists, else default sql."""
        if backend_name in self.backends:
            return self.backends[backend_name].sql
        return self.sql


class UpdateFieldConfig(BaseModel):
    """A field that can be updated."""

    field: str
    type: str = "str"
    description: str = ""
    required: bool = False


class UpdateKeyConfig(BaseModel):
    """Unique key that identifies the row to update."""

    field: str
    type: str = "int"
    description: str = ""


class UpdateConfig(BaseModel):
    """A configured UPDATE definition that becomes an MCP tool."""

    model_config = ConfigDict(populate_by_name=True)

    description: str = ""
    schema_name: str = Field(default="", alias="schema")
    table: str = ""
    key: Optional[UpdateKeyConfig] = None
    fields: list[UpdateFieldConfig] = []
    connection: str = ""  # pinned connection name (optional)
    database: str = ""  # pinned database name (optional)


class SecurityConfig(BaseModel):
    """Security settings (phase 2/3 placeholder)."""

    allow_updates: bool = True


class QueryFileConfig(BaseModel):
    """Root model for the project query config file (mcp-tools-sql.toml)."""

    connection: str = ""  # named connection reference
    queries: dict[str, QueryConfig] = {}
    updates: dict[str, UpdateConfig] = {}


class DatabaseConfig(BaseModel):
    """Root model for database config (~/.mcp-tools-sql/config.toml)."""

    connections: dict[str, ConnectionConfig] = {}
    security: SecurityConfig = SecurityConfig()
