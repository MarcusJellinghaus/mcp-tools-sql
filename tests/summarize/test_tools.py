"""Tests for :class:`SummarizeTools` and the ``summarize_columns`` tool.

The SQLite cases drive the whole pipeline end-to-end through
``create_connected_server_and_client_session``; the MagicMock cases pin
dialect-specific SQL generation and the distinct-gate decision without a live
server.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
from mcp.server.fastmcp import FastMCP
from mcp.shared.memory import create_connected_server_and_client_session

from mcp_tools_sql.backends.sqlite import SQLiteBackend
from mcp_tools_sql.config.models import ConnectionConfig, ResolvedTargets
from mcp_tools_sql.summarize import SummarizeTools
from tests.target_helpers import RecordingRegistry, make_target, single_target


def _sqlite_backend(db_path: Path) -> SQLiteBackend:
    """Return a connected SQLite backend for the given database path."""
    backend = SQLiteBackend(ConnectionConfig(backend="sqlite", path=str(db_path)))
    backend.connect()
    return backend


@asynccontextmanager
async def _client_for(
    backend: Any, *, backend_name: str = "sqlite"
) -> AsyncIterator[Any]:
    """Yield an MCP client with ``summarize_columns`` bound to *backend*."""
    mcp = FastMCP("test-summarize")
    SummarizeTools(*single_target(backend, backend_name=backend_name)).register(mcp)
    async with create_connected_server_and_client_session(
        mcp, raise_exceptions=True
    ) as client:
        yield client


async def _call_summarize(
    client: Any,
    schema: str,
    table: str,
    *,
    columns: list[str] | None = None,
    where: str | None = None,
    params: dict[str, Any] | None = None,
    n: int | None = None,
    connection: str | None = None,
    database: str | None = None,
) -> str:
    """Call ``summarize_columns`` via the MCP client and return the text."""
    args: dict[str, Any] = {"schema": schema, "table": table}
    if columns is not None:
        args["columns"] = columns
    if where is not None:
        args["where"] = where
    if params is not None:
        args["params"] = params
    if n is not None:
        args["n"] = n
    if connection is not None:
        args["connection"] = connection
    if database is not None:
        args["database"] = database
    result = await client.call_tool("summarize_columns", args)
    return result.content[0].text  # type: ignore[no-any-return]


# ---------------------------------------------------------------------------
# SQLite end-to-end — deep view per category
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_duplicated_string_column_deep_view(profiling_db: Path) -> None:
    """A duplicated column renders the nulls/empty/distinct line, top + remainder."""
    backend = _sqlite_backend(profiling_db)
    async with _client_for(backend) as client:
        out = await _call_summarize(
            client, "main", "profile_me", columns=["category"], n=2
        )
    assert "category  (TEXT, string)" in out
    assert "nulls 1 (16.7%)" in out
    assert "empty 1 (16.7%)" in out
    assert "distinct 3" in out
    assert "top values:" in out
    assert "x  2  (33.3%)" in out
    assert "1 other values" in out  # remainder line present


@pytest.mark.asyncio
async def test_unique_key_column_sample_header_count(profiling_db: Path) -> None:
    """A unique-key column samples; header count == values shown, never n=999."""
    backend = _sqlite_backend(profiling_db)
    async with _client_for(backend) as client:
        out = await _call_summarize(
            client, "main", "profile_me", columns=["ref"], n=999
        )
    assert "sample values (6 of 6 distinct — every value unique):" in out
    # The header count is the values actually shown (6), never the requested n;
    # 999 only appears in the trailing clamp note, not in the rendered block.
    assert "999" not in out.split("Requested n=")[0]
    assert out.count("R") >= 6  # all six unique refs shown


@pytest.mark.asyncio
async def test_numeric_column_stats(profiling_db: Path) -> None:
    """Numeric column: min/max/mean and zero/negative counts are correct."""
    backend = _sqlite_backend(profiling_db)
    async with _client_for(backend) as client:
        out = await _call_summarize(client, "main", "profile_me", columns=["qty"])
    assert "qty  (INTEGER, numeric)" in out
    assert "min -5 | max 20" in out
    assert "sum 35" in out
    assert "zeros 1" in out
    assert "negatives 1" in out


@pytest.mark.asyncio
async def test_temporal_column_bounds(profiling_db: Path) -> None:
    """Temporal column renders its min/max date bounds and distinct."""
    backend = _sqlite_backend(profiling_db)
    async with _client_for(backend) as client:
        out = await _call_summarize(client, "main", "profile_me", columns=["created"])
    assert "created  (DATE, temporal)" in out
    assert "min 2020-01-01 | max 2024-02-29" in out
    assert "distinct 6" in out


@pytest.mark.asyncio
async def test_boolean_column_true_false_null(profiling_db: Path) -> None:
    """Boolean column renders true/false/null counts and the true %."""
    backend = _sqlite_backend(profiling_db)
    async with _client_for(backend) as client:
        out = await _call_summarize(client, "main", "profile_me", columns=["is_active"])
    assert "is_active  (BOOLEAN, boolean)" in out
    assert "true 3 (50.0%)" in out
    assert "false 2 | null 1" in out


@pytest.mark.asyncio
async def test_all_null_column_no_value_list(profiling_db: Path) -> None:
    """An all-NULL column reads nulls 100% and shows no value-list section."""
    backend = _sqlite_backend(profiling_db)
    async with _client_for(backend) as client:
        out = await _call_summarize(client, "main", "profile_me", columns=["note"])
    assert "nulls 6 (100.0%)" in out
    assert "top values" not in out
    assert "sample values" not in out  # no nonsensical "1 of 0 distinct"


# ---------------------------------------------------------------------------
# Zero-row and filter short-circuits
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_empty_table_message(profiling_db: Path) -> None:
    """A zero-row table returns the empty-table message (not empty-filter)."""
    backend = _sqlite_backend(profiling_db)
    async with _client_for(backend) as client:
        out = await _call_summarize(client, "main", "empty_t")
    assert "is empty (0 rows)" in out


@pytest.mark.asyncio
async def test_where_matching_nothing_empty_filter_message(profiling_db: Path) -> None:
    """A ``where`` matching no rows returns the empty-filter message + true total."""
    backend = _sqlite_backend(profiling_db)
    async with _client_for(backend) as client:
        out = await _call_summarize(
            client,
            "main",
            "profile_me",
            where="category = :cat",
            params={"cat": "nomatch"},
        )
    assert out == "No rows match the where predicate (table has 6 rows)."


@pytest.mark.asyncio
async def test_param_threading_end_to_end(profiling_db: Path) -> None:
    """A matching ``:name`` predicate binds through count + scalar + value list.

    ``category = :cat`` with ``{"cat": "x"}`` matches rows 1-2 (qty 10 and 0);
    the profiled ``qty`` block reflects only that filtered subset. A dropped
    ``params`` argument on any predicate-bearing query would surface an
    unbound-parameter error string instead of a deep block.
    """
    backend = _sqlite_backend(profiling_db)
    async with _client_for(backend) as client:
        out = await _call_summarize(
            client,
            "main",
            "profile_me",
            columns=["qty"],
            where="category = :cat",
            params={"cat": "x"},
        )
    assert not out.startswith("Invalid")
    assert "rows 2" in out  # only the filtered subset
    assert "min 0 | max 10" in out


# ---------------------------------------------------------------------------
# Not-found / narrowing guards (all before any data query)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_non_existent_table_not_found_message(profiling_db: Path) -> None:
    """A missing table returns the table-not-found message (distinct wording)."""
    backend = _sqlite_backend(profiling_db)
    async with _client_for(backend) as client:
        out = await _call_summarize(client, "main", "no_such_table")
    assert "not found" in out
    assert "is empty" not in out


@pytest.mark.asyncio
async def test_unknown_columns_message_echoes_casing(profiling_db: Path) -> None:
    """An unknown requested column fails the call, echoing declared casing."""
    backend = _sqlite_backend(profiling_db)
    async with _client_for(backend) as client:
        out = await _call_summarize(client, "main", "profile_me", columns=["Nope"])
    assert out.startswith("Unknown column(s): Nope.")


@pytest.mark.asyncio
async def test_empty_columns_list_fails_before_query(profiling_db: Path) -> None:
    """``columns=[]`` fails with the empty-columns message, never an SQL error."""
    backend = _sqlite_backend(profiling_db)
    async with _client_for(backend) as client:
        out = await _call_summarize(client, "main", "profile_me", columns=[])
    assert "empty list" in out
    assert not out.startswith("Invalid SQL.")  # guard fired before any data query


@pytest.mark.asyncio
async def test_duplicate_columns_profiled_once(profiling_db: Path) -> None:
    """Repeated column names are de-duplicated: the block appears exactly once."""
    backend = _sqlite_backend(profiling_db)
    async with _client_for(backend) as client:
        out = await _call_summarize(
            client, "main", "profile_me", columns=["qty", "QTY", "qty"]
        )
    assert out.count("(INTEGER, numeric)") == 1
    assert "Showing" not in out  # no cap footer triggered by the repeats
    assert "null_pct" not in out  # not flipped into triage


# ---------------------------------------------------------------------------
# Triage vs deep dispatch
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_wide_table_triage_then_narrowed_deep(profiling_db: Path) -> None:
    """> 15 columns render triage; a narrowed ≤ 15 subset renders deep blocks."""
    backend = _sqlite_backend(profiling_db)
    async with _client_for(backend) as client:
        wide = await _call_summarize(client, "main", "wide_t")
        narrow = await _call_summarize(
            client, "main", "wide_t", columns=["w0", "w1", "w2"]
        )
    assert "null_pct" in wide  # triage table header
    assert "(INTEGER, numeric)" not in wide
    assert "(INTEGER, numeric)" in narrow  # deep per-column blocks


# ---------------------------------------------------------------------------
# n clamp behaviour
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_n_clamp_note_high_and_low(profiling_db: Path) -> None:
    """``n=999`` notes the max clamp; ``n=0`` clamps to 1 (no empty list)."""
    backend = _sqlite_backend(profiling_db)
    async with _client_for(backend) as client:
        high = await _call_summarize(
            client, "main", "profile_me", columns=["category"], n=999
        )
        low = await _call_summarize(
            client, "main", "profile_me", columns=["category"], n=0
        )
    # The clamp note is separated from the rendered block by a blank line, not
    # glued onto the final value row.
    assert "\n\nRequested n=999 exceeds the maximum 50; using 50." in high
    assert high.endswith("Requested n=999 exceeds the maximum 50; using 50.")
    assert not high.rstrip().splitlines()[-1].startswith("    ")  # not a value row
    assert "\n\nRequested n=0 is below the minimum 1; using 1." in low
    assert "top values:" in low  # clamped to 1, still a non-empty list


# ---------------------------------------------------------------------------
# Registration + multi-target selectors
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_registration_exposes_tool(profiling_db: Path) -> None:
    """A single-target install exposes ``summarize_columns`` in list_tools."""
    backend = _sqlite_backend(profiling_db)
    mcp = FastMCP("test-summarize-registration")
    SummarizeTools(*single_target(backend)).register(mcp)
    async with create_connected_server_and_client_session(
        mcp, raise_exceptions=True
    ) as client:
        result = await client.list_tools()
    names = {t.name for t in result.tools}
    assert "summarize_columns" in names


def _multi_targets() -> ResolvedTargets:
    """Two connections: ``lite`` (sqlite) default + ``sql`` (mssql/tsql)."""
    t_lite = make_target("lite", "main", is_default=True, default_database="main")
    t_sql = make_target("sql", "hr", default_database="hr", backend_name="mssql")
    return ResolvedTargets(
        targets=[t_lite, t_sql], default=t_lite, file_default_connection="lite"
    )


@pytest.mark.asyncio
async def test_multi_target_selectors_omit_star(profiling_db: Path) -> None:
    """Multi-target surfaces connection/database props but never the ``*`` sentinel."""
    backend = _sqlite_backend(profiling_db)
    targets = _multi_targets()
    registry = RecordingRegistry({("lite", "main"): backend, ("sql", "hr"): backend})
    mcp = FastMCP("test-summarize-multi")
    SummarizeTools(registry, targets).register(mcp)
    async with create_connected_server_and_client_session(
        mcp, raise_exceptions=True
    ) as client:
        result = await client.list_tools()
    tool = next(t for t in result.tools if t.name == "summarize_columns")
    props = tool.inputSchema["properties"]
    assert "connection" in props
    assert "database" in props
    assert "*" not in str(props["database"])  # pinned enum, no fan-out sentinel


# ---------------------------------------------------------------------------
# MagicMock: distinct-gate decision + T-SQL dialect parity (no live server)
# ---------------------------------------------------------------------------


def _fake_scalar_row(n_cols: int) -> dict[str, Any]:
    """Build a synthetic scalar-pass result row for *n_cols* numeric columns."""
    row: dict[str, Any] = {}
    for i in range(n_cols):
        row[f"c{i}__nonnull"] = 100
        row[f"c{i}__distinct"] = 10
        row[f"c{i}__min"] = 1
        row[f"c{i}__max"] = 5
        row[f"c{i}__mean"] = 3.0
        row[f"c{i}__sum"] = 300
        row[f"c{i}__zero"] = 0
        row[f"c{i}__neg"] = 0
    return row


def _gate_backend(n_cols: int, row_count: int) -> tuple[MagicMock, dict[str, str]]:
    """Return a MagicMock backend and a dict that captures the scalar SQL."""
    captured: dict[str, str] = {}
    metas = [{"name": f"n{i}", "type": "INTEGER", "ordinal": i} for i in range(n_cols)]
    scalar_row = _fake_scalar_row(n_cols)

    def fake(sql: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        if "pragma_table_info" in sql or "INFORMATION_SCHEMA" in sql:
            return metas
        if "row_count" in sql:
            return [{"row_count": row_count}]
        if "c0__nonnull" in sql:
            captured["scalar_sql"] = sql
            return [scalar_row]
        return [{"value": 1, "freq": 5}]

    backend = MagicMock()
    backend.execute_readonly_query.side_effect = fake
    return backend, captured


@pytest.mark.asyncio
async def test_distinct_gate_triage_omits_count_distinct() -> None:
    """A triage call above the row gate builds the scalar SQL without distinct."""
    backend, captured = _gate_backend(n_cols=16, row_count=2_000_000)
    async with _client_for(backend) as client:
        out = await _call_summarize(client, "main", "big")
    assert "null_pct" in out  # rendered triage
    assert "COUNT(DISTINCT" not in captured["scalar_sql"]


@pytest.mark.asyncio
async def test_distinct_gate_deep_never_gated() -> None:
    """A deep call is never gated: distinct is computed even above the row gate."""
    backend, captured = _gate_backend(n_cols=3, row_count=2_000_000)
    async with _client_for(backend) as client:
        out = await _call_summarize(client, "main", "big")
    assert "(INTEGER, numeric)" in out  # rendered deep
    assert "COUNT(DISTINCT" in captured["scalar_sql"]


@pytest.mark.asyncio
async def test_mssql_dialect_metadata_and_scalar_sql() -> None:
    """Under the tsql target the metadata + scalar SQL render for T-SQL."""
    captured: dict[str, str] = {}

    def fake(sql: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        if "INFORMATION_SCHEMA" in sql:
            captured["metadata_sql"] = sql
            return [{"name": "amount", "type": "int", "ordinal": 1}]
        if "row_count" in sql:
            return [{"row_count": 10}]
        if "c0__nonnull" in sql:
            captured["scalar_sql"] = sql
            return [
                {
                    "c0__nonnull": 10,
                    "c0__distinct": 5,
                    "c0__min": 1,
                    "c0__max": 9,
                    "c0__mean": 5.0,
                    "c0__sum": 50,
                    "c0__zero": 0,
                    "c0__neg": 0,
                }
            ]
        return [{"value": 1, "freq": 3}]

    backend = MagicMock()
    backend.execute_readonly_query.side_effect = fake
    async with _client_for(backend, backend_name="mssql") as client:
        out = await _call_summarize(client, "dbo", "t", columns=["amount"])
    assert not out.startswith("Invalid")
    assert "INFORMATION_SCHEMA.COLUMNS" in captured["metadata_sql"]
    assert "AVG(CAST([amount] AS FLOAT))" in captured["scalar_sql"]
