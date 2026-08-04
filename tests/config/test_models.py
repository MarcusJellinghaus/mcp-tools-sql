"""Tests for Pydantic configuration models."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from mcp_tools_sql.config.models import (
    BackendQueryConfig,
    ConnectionConfig,
    DatabaseConfig,
    DatabaseSpec,
    QueryConfig,
    QueryFileConfig,
    QueryParamConfig,
    ResolvedTarget,
    ResolvedTargets,
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

    def test_connection_config_no_credential_env_var(self) -> None:
        """ConnectionConfig no longer exposes a credential_env_var field."""
        assert not hasattr(ConnectionConfig(), "credential_env_var")

    def test_connection_config_encrypt_default_true(self) -> None:
        """ConnectionConfig.encrypt defaults to True (TLS on)."""
        assert ConnectionConfig().encrypt is True

    def test_connection_config_trust_server_certificate_default_false(self) -> None:
        """ConnectionConfig.trust_server_certificate defaults to False."""
        assert ConnectionConfig().trust_server_certificate is False

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


class TestDatabaseSpec:
    """Tests for the DatabaseSpec model."""

    def test_name_only(self) -> None:
        """DatabaseSpec accepts a name with an empty description default."""
        spec = DatabaseSpec(name="sales")
        assert spec.name == "sales"
        assert spec.description == ""

    def test_name_and_description(self) -> None:
        """DatabaseSpec preserves an explicit description."""
        spec = DatabaseSpec(name="sales", description="Sales catalog")
        assert spec.description == "Sales catalog"


class TestConnectionConfigDatabaseNormalisation:
    """Tests for ConnectionConfig databases/default_database normalisation."""

    def test_sqlite_normalises_to_main(self) -> None:
        """sqlite ignores authored database info and uses the 'main' catalog."""
        config = ConnectionConfig(backend="sqlite", path="/tmp/db.sqlite")
        assert [d.name for d in config.databases] == ["main"]
        assert config.default_database == "main"
        assert config.database == "main"

    def test_sqlite_ignores_authored_databases(self) -> None:
        """sqlite discards any authored databases/database values."""
        config = ConnectionConfig.model_validate(
            {"backend": "sqlite", "databases": ["sales", "hr"], "database": "x"}
        )
        assert [d.name for d in config.databases] == ["main"]
        assert config.default_database == "main"

    def test_list_form(self) -> None:
        """List form produces DatabaseSpec entries preserving order."""
        config = ConnectionConfig.model_validate(
            {"backend": "mssql", "databases": ["sales", "hr"]}
        )
        assert [d.name for d in config.databases] == ["sales", "hr"]
        assert config.default_database == "sales"
        assert config.database == "sales"

    def test_table_form(self) -> None:
        """Table form maps names to descriptions preserving declared order."""
        config = ConnectionConfig.model_validate(
            {
                "backend": "mssql",
                "databases": {
                    "sales": {"description": "Sales DB"},
                    "hr": {"description": "HR DB"},
                },
            }
        )
        assert [d.name for d in config.databases] == ["sales", "hr"]
        assert config.databases[0].description == "Sales DB"
        assert config.databases[1].description == "HR DB"
        assert config.default_database == "sales"

    def test_legacy_database(self) -> None:
        """Legacy single database normalises to a one-entry list."""
        config = ConnectionConfig.model_validate(
            {"backend": "mssql", "database": "sales"}
        )
        assert [d.name for d in config.databases] == ["sales"]
        assert config.default_database == "sales"
        assert config.database == "sales"

    def test_default_database_explicit(self) -> None:
        """An explicit default_database is honoured when a member."""
        config = ConnectionConfig.model_validate(
            {
                "backend": "mssql",
                "databases": ["sales", "hr"],
                "default_database": "hr",
            }
        )
        assert config.default_database == "hr"
        assert config.database == "hr"

    def test_default_database_defaults_to_first(self) -> None:
        """default_database defaults to the first entry when unset."""
        config = ConnectionConfig.model_validate(
            {"backend": "mssql", "databases": ["sales", "hr"]}
        )
        assert config.default_database == "sales"

    def test_description_field(self) -> None:
        """ConnectionConfig accepts a connection-level description."""
        config = ConnectionConfig.model_validate(
            {"backend": "mssql", "database": "sales", "description": "Prod server"}
        )
        assert config.description == "Prod server"


class TestConnectionConfigValidationErrors:
    """Tests for ConnectionConfig validation failures."""

    def test_default_database_not_member(self) -> None:
        """default_database not in databases raises ValidationError."""
        with pytest.raises(ValidationError):
            ConnectionConfig.model_validate(
                {
                    "backend": "mssql",
                    "databases": ["sales", "hr"],
                    "default_database": "finance",
                }
            )

    def test_postgresql_two_databases(self) -> None:
        """postgresql with more than one database raises ValidationError."""
        with pytest.raises(ValidationError):
            ConnectionConfig.model_validate(
                {"backend": "postgresql", "databases": ["sales", "hr"]}
            )

    def test_postgresql_one_database_ok(self) -> None:
        """postgresql with exactly one database validates."""
        config = ConnectionConfig.model_validate(
            {"backend": "postgresql", "databases": ["sales"]}
        )
        assert [d.name for d in config.databases] == ["sales"]

    def test_mssql_empty_databases(self) -> None:
        """mssql with neither database nor databases raises ValidationError."""
        with pytest.raises(ValidationError):
            ConnectionConfig.model_validate({"backend": "mssql"})

    def test_pyodbc_empty_databases(self) -> None:
        """pyodbc (mssql alias) with no database raises ValidationError."""
        with pytest.raises(ValidationError):
            ConnectionConfig.model_validate({"backend": "pyodbc"})

    def test_legacy_conflicts_with_databases(self) -> None:
        """Legacy database not among explicit databases raises ValidationError."""
        with pytest.raises(ValidationError):
            ConnectionConfig.model_validate(
                {"backend": "mssql", "database": "hr", "databases": ["sales"]}
            )

    def test_legacy_conflicts_with_default_database(self) -> None:
        """Legacy database disagreeing with default_database raises."""
        with pytest.raises(ValidationError):
            ConnectionConfig.model_validate(
                {
                    "backend": "mssql",
                    "database": "sales",
                    "databases": ["sales", "hr"],
                    "default_database": "hr",
                }
            )

    def test_legacy_consistent_with_databases(self) -> None:
        """Legacy database that is a member of databases validates."""
        config = ConnectionConfig.model_validate(
            {"backend": "mssql", "database": "sales", "databases": ["sales", "hr"]}
        )
        assert config.default_database == "sales"


class TestConnectionConfigBackwardCompat:
    """Existing single-database configs keep loading unchanged."""

    def test_default_sqlite_config(self) -> None:
        """A bare ConnectionConfig still defaults to sqlite/main."""
        config = ConnectionConfig()
        assert config.backend == "sqlite"
        assert config.default_database == "main"

    def test_mssql_single_database_roundtrip(self) -> None:
        """A legacy mssql config exposes database for the ODBC reader."""
        config = ConnectionConfig(backend="mssql", database="AdventureWorks")
        assert config.database == "AdventureWorks"
        assert config.default_database == "AdventureWorks"


class TestPinnedTargetFields:
    """Tests for optional pinned connection/database on query/update configs."""

    def test_query_config_pinned_defaults_empty(self) -> None:
        """QueryConfig connection/database default to empty strings."""
        config = QueryConfig(sql="SELECT 1")
        assert config.connection == ""
        assert config.database == ""

    def test_query_config_pinned_values(self) -> None:
        """QueryConfig accepts explicit pinned connection/database."""
        config = QueryConfig(sql="SELECT 1", connection="prod", database="sales")
        assert config.connection == "prod"
        assert config.database == "sales"

    def test_update_config_pinned_defaults_empty(self) -> None:
        """UpdateConfig connection/database default to empty strings."""
        config = UpdateConfig()
        assert config.connection == ""
        assert config.database == ""

    def test_update_config_pinned_values(self) -> None:
        """UpdateConfig accepts explicit pinned connection/database."""
        config = UpdateConfig(connection="prod", database="hr")
        assert config.connection == "prod"
        assert config.database == "hr"


def _make_target(
    connection: str,
    database: str,
    *,
    is_default: bool = False,
    default_database: str = "",
) -> ResolvedTarget:
    """Build a ResolvedTarget for the given connection/database pair."""
    default_db = default_database or database
    names = list(dict.fromkeys([default_db, database]))
    base = ConnectionConfig.model_validate(
        {"backend": "mssql", "databases": names, "default_database": default_db}
    )
    config = base.model_copy(update={"database": database})
    return ResolvedTarget(
        connection=connection,
        database=database,
        config=config,
        backend_name="mssql",
        is_default=is_default,
    )


class TestResolvedTarget:
    """Tests for the frozen ResolvedTarget model."""

    def test_fields(self) -> None:
        """ResolvedTarget exposes its connection/database/backend fields."""
        target = _make_target("prod", "sales", is_default=True)
        assert target.connection == "prod"
        assert target.database == "sales"
        assert target.backend_name == "mssql"
        assert target.is_default is True
        assert target.connection_description == ""
        assert target.database_description == ""

    def test_is_frozen(self) -> None:
        """ResolvedTarget is immutable (frozen)."""
        target = _make_target("prod", "sales")
        with pytest.raises(ValidationError):
            target.database = "hr"


class TestResolvedTargets:
    """Tests for ResolvedTargets helper methods."""

    def test_single_target_not_multi(self) -> None:
        """A one-target set reports is_multi False with matching names."""
        target = _make_target("prod", "sales", is_default=True)
        targets = ResolvedTargets(
            targets=[target], default=target, file_default_connection="prod"
        )
        assert targets.is_multi is False
        assert targets.connection_names == ["prod"]
        assert targets.database_names == ["sales"]

    def test_multi_target_dedup_order(self) -> None:
        """Connection/database names dedup while preserving config order."""
        t1 = _make_target("prod", "sales", is_default=True, default_database="sales")
        t2 = _make_target("prod", "hr", default_database="sales")
        t3 = _make_target("localdb", "sales", default_database="sales")
        targets = ResolvedTargets(
            targets=[t1, t2, t3], default=t1, file_default_connection="prod"
        )
        assert targets.is_multi is True
        assert targets.connection_names == ["prod", "localdb"]
        assert targets.database_names == ["sales", "hr"]

    def test_for_connection(self) -> None:
        """for_connection returns only the matching connection's targets."""
        t1 = _make_target("prod", "sales", is_default=True, default_database="sales")
        t2 = _make_target("prod", "hr", default_database="sales")
        t3 = _make_target("localdb", "sales", default_database="sales")
        targets = ResolvedTargets(
            targets=[t1, t2, t3], default=t1, file_default_connection="prod"
        )
        assert targets.for_connection("prod") == [t1, t2]
        assert targets.for_connection("localdb") == [t3]
        assert targets.for_connection("missing") == []

    def test_resolve_pinned_defaults(self) -> None:
        """resolve_pinned(None, None) returns the file default target."""
        t1 = _make_target("prod", "sales", is_default=True, default_database="sales")
        t2 = _make_target("prod", "hr", default_database="sales")
        targets = ResolvedTargets(
            targets=[t1, t2], default=t1, file_default_connection="prod"
        )
        assert targets.resolve_pinned(None, None) is t1

    def test_resolve_pinned_explicit(self) -> None:
        """resolve_pinned selects the named connection/database pair."""
        t1 = _make_target("prod", "sales", is_default=True, default_database="sales")
        t2 = _make_target("prod", "hr", default_database="sales")
        targets = ResolvedTargets(
            targets=[t1, t2], default=t1, file_default_connection="prod"
        )
        assert targets.resolve_pinned("prod", "hr") is t2

    def test_resolve_pinned_unknown_database_raises(self) -> None:
        """resolve_pinned raises when the database is absent in the connection."""
        t1 = _make_target("prod", "sales", is_default=True, default_database="sales")
        t2 = _make_target("localdb", "sales", default_database="sales")
        targets = ResolvedTargets(
            targets=[t1, t2], default=t1, file_default_connection="prod"
        )
        with pytest.raises(ValueError, match="hr"):
            targets.resolve_pinned("localdb", "hr")

    def test_resolve_pinned_unknown_connection_raises(self) -> None:
        """resolve_pinned raises when the connection is absent."""
        t1 = _make_target("prod", "sales", is_default=True, default_database="sales")
        targets = ResolvedTargets(
            targets=[t1], default=t1, file_default_connection="prod"
        )
        with pytest.raises(ValueError, match="missing"):
            targets.resolve_pinned("missing", None)
