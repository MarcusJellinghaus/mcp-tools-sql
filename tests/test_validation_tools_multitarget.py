"""Multi-target tests for validate_sql (per-call backend + dialect resolution)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, get_args

import pytest
from mcp.server.fastmcp import FastMCP
from mcp.shared.memory import create_connected_server_and_client_session

from mcp_tools_sql.backends.sqlite import SQLiteBackend
from mcp_tools_sql.config.models import ConnectionConfig, ResolvedTargets
from mcp_tools_sql.query_helpers import build_target_params
from mcp_tools_sql.validation_tools import ValidationTools
from tests.target_helpers import RecordingRegistry, make_target


def _sqlite_backend(db_path: Path) -> SQLiteBackend:
    """Return a connected SQLite backend for the given database path."""
    backend = SQLiteBackend(ConnectionConfig(backend="sqlite", path=str(db_path)))
    backend.connect()
    return backend


async def _call_validate(
    client: Any,
    sql: str,
    params: dict[str, Any] | None = None,
    return_plan: bool = False,
    *,
    connection: str | None = None,
    database: str | None = None,
) -> str:
    """Call ``validate_sql`` via the MCP client and return the text content."""
    args: dict[str, Any] = {"sql": sql}
    if params is not None:
        args["params"] = params
    if return_plan:
        args["return_plan"] = return_plan
    if connection is not None:
        args["connection"] = connection
    if database is not None:
        args["database"] = database
    result = await client.call_tool("validate_sql", args)
    return result.content[0].text  # type: ignore[no-any-return]


# ---------------------------------------------------------------------------
# Multi-target: per-call backend + dialect resolution (Step 12)
# ---------------------------------------------------------------------------


def _multi_targets() -> ResolvedTargets:
    """Two connections: ``lite`` (sqlite) default + ``sql`` (mssql/tsql).

    ``lite`` → ``main`` (sqlite); ``sql`` → ``hr`` (mssql). The differing
    backends let a test prove that ``validate_sql`` resolves the sqlglot dialect
    *per call* from the pinned target rather than a single install-wide dialect.
    """
    t_lite = make_target("lite", "main", is_default=True, default_database="main")
    t_sql = make_target("sql", "hr", default_database="hr", backend_name="mssql")
    return ResolvedTargets(
        targets=[t_lite, t_sql], default=t_lite, file_default_connection="lite"
    )


def _literal_members(annotation: Any) -> set[str]:
    """Extract the ``Literal`` members from an ``Annotated[...]`` param annotation.

    Returns:
        The set of string members declared on the (possibly ``Optional``)
        ``Literal`` inside the annotation.
    """
    inner = get_args(annotation)[0]  # unwrap Annotated -> Literal | Optional[Literal]
    literal = inner
    nested = get_args(inner)
    if nested and get_args(nested[0]):  # Optional[Literal[...]]
        literal = nested[0]
    return set(get_args(literal))


def test_validate_target_params_database_enum_omits_star() -> None:
    """``build_target_params(star=False)`` omits ``*``; ``star=True`` keeps it.

    ``validate_sql`` has no fan-out, so its ``database`` enum must never carry
    the ``*`` sentinel — while the shared flag still yields it for the
    ``schema_tools`` fan-out caller.
    """
    targets = _multi_targets()

    pinned = {p.name: p for p in build_target_params(targets, star=False)}
    assert "*" not in _literal_members(pinned["database"].annotation)

    fanned = {p.name: p for p in build_target_params(targets, star=True)}
    assert "*" in _literal_members(fanned["database"].annotation)


@pytest.mark.asyncio
async def test_multi_install_exposes_selector_params(sqlite_db: Path) -> None:
    """A multi-target install surfaces connection/database enums on validate_sql."""
    backend = _sqlite_backend(sqlite_db)
    targets = _multi_targets()
    registry = RecordingRegistry({("lite", "main"): backend, ("sql", "hr"): backend})
    mcp = FastMCP("test-validate-multi-schema")
    ValidationTools(registry, targets).register(mcp)

    async with create_connected_server_and_client_session(
        mcp, raise_exceptions=True
    ) as client:
        result = await client.list_tools()
        tool = next(t for t in result.tools if t.name == "validate_sql")
        props = tool.inputSchema["properties"]
        assert "connection" in props
        assert "database" in props


@pytest.mark.asyncio
async def test_multi_per_call_dialect_resolved_from_target(sqlite_db: Path) -> None:
    """``DECLARE @x INT`` parses under the pinned target's dialect, not one global.

    Pinned to the ``sql`` (mssql/tsql) target it parses and is rejected as a
    session statement; pinned to the ``lite`` (sqlite) target the same text is
    not valid SQLite and fails closed as a parse error. Same install, two
    dialects — proving per-call resolution. The mssql call also records the
    ``(sql, hr)`` target lookup.
    """
    backend = _sqlite_backend(sqlite_db)
    targets = _multi_targets()
    registry = RecordingRegistry({("lite", "main"): backend, ("sql", "hr"): backend})
    mcp = FastMCP("test-validate-multi-dialect")
    ValidationTools(registry, targets).register(mcp)

    async with create_connected_server_and_client_session(
        mcp, raise_exceptions=True
    ) as client:
        tsql_verdict = await _call_validate(
            client, "DECLARE @x INT", connection="sql", database="hr"
        )
        sqlite_verdict = await _call_validate(
            client, "DECLARE @x INT", connection="lite"
        )

    assert (
        tsql_verdict == "Invalid SQL. ValidationError: DECLARE statements not supported"
    )
    assert sqlite_verdict.startswith("Invalid SQL. ParseError: ")
    assert registry.calls[0].connection == "sql"
    assert registry.calls[0].database == "hr"


@pytest.mark.asyncio
async def test_multi_cross_connection_mismatch_returns_verdict(
    sqlite_db: Path,
) -> None:
    """A ``(lite, hr)`` mismatch returns the friendly verdict, hits no backend."""
    backend = _sqlite_backend(sqlite_db)
    targets = _multi_targets()
    registry = RecordingRegistry({("lite", "main"): backend, ("sql", "hr"): backend})
    mcp = FastMCP("test-validate-multi-mismatch")
    ValidationTools(registry, targets).register(mcp)

    async with create_connected_server_and_client_session(
        mcp, raise_exceptions=True
    ) as client:
        text = await _call_validate(
            client, "SELECT 1", connection="lite", database="hr"
        )

    assert "lite" in text
    assert "hr" in text
    assert "main" in text  # lists the available databases
    assert registry.calls == []  # resolve failed before any backend lookup


@pytest.mark.asyncio
async def test_multi_valid_select_binds_selected_target(sqlite_db: Path) -> None:
    """`connection='lite'` resolves the sqlite target and validates the SELECT."""
    backend = _sqlite_backend(sqlite_db)
    targets = _multi_targets()
    registry = RecordingRegistry({("lite", "main"): backend, ("sql", "hr"): backend})
    mcp = FastMCP("test-validate-multi-select")
    ValidationTools(registry, targets).register(mcp)

    async with create_connected_server_and_client_session(
        mcp, raise_exceptions=True
    ) as client:
        text = await _call_validate(
            client, "SELECT * FROM customers", connection="lite"
        )

    assert text == "Valid."
    assert registry.calls[-1].connection == "lite"
    assert registry.calls[-1].database == "main"
