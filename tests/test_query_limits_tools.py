"""Query/schema tools read through ``collect`` + ``render_limited`` (#97)."""

from __future__ import annotations

import itertools
import sqlite3
from collections.abc import Generator, Iterator
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from mcp.server.fastmcp import FastMCP
from mcp.shared.memory import create_connected_server_and_client_session

from mcp_tools_sql import result_limits
from mcp_tools_sql.backends.base import DatabaseBackend, Deadline, QueryTimeoutError
from mcp_tools_sql.backends.sqlite import SQLiteBackend
from mcp_tools_sql.config.models import (
    ConnectionConfig,
    LimitsConfig,
    QueryConfig,
    QueryFileConfig,
    QueryParamConfig,
)
from mcp_tools_sql.query_tools import QueryTools
from mcp_tools_sql.schema_tools import SchemaTools
from mcp_tools_sql.server import ToolServer
from tests.target_helpers import single_target, sqlite_backend

_TRUNC = "\n\n[Output truncated"


class _BatchBackend(DatabaseBackend):
    """Backend yielding preset batches, then optionally a statement timeout."""

    def __init__(
        self, batches: list[list[dict[str, Any]]], *, timeout_after: bool = False
    ) -> None:
        self._batches = batches
        self._timeout_after = timeout_after

    def connect(self) -> None:
        """No-op."""

    def close(self) -> None:
        """No-op."""

    def execute_query(
        self, sql: str, params: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        raise AssertionError("unused")

    def execute_readonly_query(
        self, sql: str, params: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        raise AssertionError("unused")

    def execute_readonly_query_with_columns(
        self, sql: str, params: dict[str, Any] | None = None
    ) -> tuple[list[str], list[tuple[Any, ...]]]:
        raise AssertionError("unused")

    def execute_update(self, sql: str, params: dict[str, Any] | None = None) -> int:
        raise AssertionError("unused")

    def explain(self, sql: str, params: dict[str, Any] | None = None) -> str:
        raise AssertionError("unused")

    @contextmanager
    def get_isolated_connection(self) -> Iterator[Any]:
        """Unused in these tests."""
        yield None

    def iter_readonly_batches(
        self,
        sql: str,
        params: dict[str, Any] | None = None,
        *,
        counting: Deadline | None = None,
    ) -> Generator[list[dict[str, Any]], None, None]:
        """Yield the preset batches, then raise a timeout when configured.

        Yields:
            Copies of the preset batches.

        Raises:
            QueryTimeoutError: After the last batch, when ``timeout_after``.
        """
        for batch in self._batches:
            yield [dict(r) for r in batch]
        if self._timeout_after:
            raise QueryTimeoutError(30)


def _make_db(tmp_path: Path, rows: list[tuple[int, str, str]]) -> Path:
    """Create ``big(id, name, note)`` seeded with *rows*.

    Returns:
        Path of the SQLite database file.
    """
    db_path = tmp_path / "big.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE big (id INTEGER, name TEXT, note TEXT)")
    conn.executemany("INSERT INTO big VALUES (?, ?, ?)", rows)
    conn.commit()
    conn.close()
    return db_path


def _query_mcp(
    backend: DatabaseBackend,
    queries: dict[str, QueryConfig],
    limits: LimitsConfig | None = None,
) -> FastMCP:
    mcp = FastMCP("test-query-limits")
    QueryTools(*single_target(backend), queries, limits=limits).register(mcp)
    return mcp


def _schema_mcp(backend: DatabaseBackend) -> FastMCP:
    mcp = FastMCP("test-schema-limits")
    SchemaTools(*single_target(backend)).register(mcp)
    return mcp


async def _call(mcp: FastMCP, tool: str, args: dict[str, Any]) -> str:
    """Call *tool* via an in-memory MCP client.

    Returns:
        The text content of the result.
    """
    async with create_connected_server_and_client_session(
        mcp, raise_exceptions=True
    ) as client:
        result = await client.call_tool(tool, args)
    return result.content[0].text  # type: ignore[union-attr]


def _min_id_query(**kwargs: Any) -> QueryConfig:
    return QueryConfig(
        description="Rows from an id",
        sql="SELECT id FROM big WHERE id >= :min_id ORDER BY id",
        params={"min_id": QueryParamConfig(name="min_id", type="int")},
        **kwargs,
    )


def _rows(n: int) -> list[tuple[int, str, str]]:
    return [(i, f"n{i}", "x") for i in range(n)]


# ---------------------------------------------------------------------------
# Truncation messages
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_params_truncation_names_total_and_hard_limit(tmp_path: Path) -> None:
    """max_rows truncation names the total and the effective max_rows_hard."""
    backend = sqlite_backend(_make_db(tmp_path, _rows(5)))
    mcp = _query_mcp(backend, {"q": _min_id_query(max_rows_hard=4)})

    text = await _call(mcp, "query_q", {"min_id": 0, "max_rows": 2})

    assert "[Output truncated: showing 2 of 5 rows (max_rows=2 reached)." in text
    assert "To see more rows: increase max_rows (hard limit 4) or refine " in text


@pytest.mark.asyncio
async def test_params_truncation_at_hard_limit_only_refine(tmp_path: Path) -> None:
    """A capped request offers only ``refine parameters``."""
    backend = sqlite_backend(_make_db(tmp_path, _rows(5)))
    mcp = _query_mcp(backend, {"q": _min_id_query(max_rows_hard=2)})

    text = await _call(mcp, "query_q", {"min_id": 0, "max_rows": 9})

    assert "showing 2 of 5 rows (max_rows=2 reached)." in text
    assert "To see more rows: refine parameters.]" in text
    assert "increase max_rows" not in text
    assert "Requested max_rows=9 exceeds hard limit 2; capped at 2." in text


@pytest.mark.asyncio
async def test_builtin_read_columns_wide_table(sqlite_wide_db: Path) -> None:
    """read_columns on the 150-column fixture stops at max_rows=100."""
    mcp = _schema_mcp(sqlite_backend(sqlite_wide_db))

    text = await _call(mcp, "read_columns", {"schema": "main", "table": "wide_table"})

    assert "showing 100 of 150 rows (max_rows=100 reached)" in text


@pytest.mark.asyncio
async def test_sqlite_read_tables_truncation_has_no_param_phrase(
    tmp_path: Path,
) -> None:
    """read_tables declares ``schema`` but its SQLite SQL binds nothing."""
    db_path = tmp_path / "tables.db"
    conn = sqlite3.connect(str(db_path))
    for name in ("a", "b", "c"):
        conn.execute(f"CREATE TABLE {name} (id INTEGER)")
    conn.commit()
    conn.close()
    mcp = _schema_mcp(sqlite_backend(db_path))

    text = await _call(mcp, "read_tables", {"schema": "main", "max_rows": 2})

    assert "showing 2 of 3 rows (max_rows=2 reached)." in text
    assert "parameters" not in text


@pytest.mark.asyncio
async def test_sqlite_read_tables_timeout_has_no_hint() -> None:
    """A read_tables timeout on SQLite carries no parameter hint."""
    mcp = _schema_mcp(_BatchBackend([], timeout_after=True))

    text = await _call(mcp, "read_tables", {"schema": "main"})

    assert text == "Query aborted after 30 s (statement timeout)."


@pytest.mark.asyncio
async def test_builtin_read_schemas_timeout_exact() -> None:
    """read_schemas timeout → exactly the bare statement-timeout message."""
    mcp = _schema_mcp(_BatchBackend([], timeout_after=True))

    text = await _call(mcp, "read_schemas", {})

    assert text == "Query aborted after 30 s (statement timeout)."


def _filter_query(**kwargs: Any) -> QueryConfig:
    return QueryConfig(
        description="Names",
        sql="SELECT name FROM big ORDER BY id",
        filter_column="name",
        **kwargs,
    )


@pytest.mark.asyncio
async def test_filter_column_truncation_names_filter(tmp_path: Path) -> None:
    """A filter column without placeholders suggests ``narrow with <col>_filter``."""
    backend = sqlite_backend(_make_db(tmp_path, _rows(5)))
    mcp = _query_mcp(backend, {"q": _filter_query(max_rows_hard=2)})

    text = await _call(mcp, "query_q", {"max_rows": 2})

    assert "showing 2 of 5 rows (max_rows=2 reached)." in text
    assert "To see more rows: narrow with name_filter.]" in text


@pytest.mark.asyncio
async def test_filter_column_timeout_has_no_hint() -> None:
    """A filter-only query's timeout carries no hint."""
    mcp = _query_mcp(_BatchBackend([], timeout_after=True), {"q": _filter_query()})

    text = await _call(mcp, "query_q", {})

    assert text == "Query aborted after 30 s (statement timeout)."


# ---------------------------------------------------------------------------
# Char budget and cell cut
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_char_budget_bounds_table(tmp_path: Path) -> None:
    """The table before the message stays within ``max_output_chars``."""
    backend = sqlite_backend(_make_db(tmp_path, _rows(200)))
    query = QueryConfig(sql="SELECT id, name FROM big ORDER BY id")
    limits = LimitsConfig(max_output_chars=300)
    mcp = _query_mcp(backend, {"q": query}, limits)

    text = await _call(mcp, "query_q", {})

    assert len(text.split(_TRUNC)[0]) <= 300
    assert "300-char output limit reached" in text
    assert "of 200 rows" in text


@pytest.mark.asyncio
async def test_char_budget_with_header_wider_than_cells(tmp_path: Path) -> None:
    """A header wider than every cell still respects the budget."""
    backend = sqlite_backend(_make_db(tmp_path, _rows(200)))
    query = QueryConfig(
        sql="SELECT id AS a_column_header_much_wider_than_any_cell FROM big"
    )
    limits = LimitsConfig(max_output_chars=400)
    mcp = _query_mcp(backend, {"q": query}, limits)

    text = await _call(mcp, "query_q", {})

    assert _TRUNC in text
    assert len(text.split(_TRUNC)[0]) <= 400
    assert "400-char output limit reached" in text


@pytest.mark.asyncio
async def test_cell_cut_marker_and_note(tmp_path: Path) -> None:
    """Long cells are cut with a marker and a closing note."""
    backend = sqlite_backend(_make_db(tmp_path, [(1, "n1", "z" * 50)]))
    query = QueryConfig(sql="SELECT note FROM big")
    mcp = _query_mcp(backend, {"q": query}, LimitsConfig(max_cell_chars=10))

    text = await _call(mcp, "query_q", {})

    assert "zzzzzzzzzz…[cut, 50 chars total]" in text
    assert text.endswith("Long values were cut at 10 chars.")


@pytest.mark.asyncio
async def test_first_row_wider_than_budget(tmp_path: Path) -> None:
    """A first row wider than the budget shows 0 rows and the operator line."""
    backend = sqlite_backend(_make_db(tmp_path, [(1, "n1", "y" * 300)]))
    query = QueryConfig(sql="SELECT note FROM big")
    mcp = _query_mcp(backend, {"q": query}, LimitsConfig(max_output_chars=100))

    text = await _call(mcp, "query_q", {})

    assert text.startswith("No results found.")
    assert (
        "[Output truncated: the first row is wider than the 100-char output "
        "limit; showing 0 of 1 rows." in text
    )
    assert "Operator: select fewer columns in the configured SQL" in text


# ---------------------------------------------------------------------------
# Filter across batches
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_filter_matches_beyond_first_batch(tmp_path: Path) -> None:
    """Matches past the first 500 raw rows are found and counted exactly."""
    rows = [(i, f"skip{i}", "x") for i in range(900)]
    rows += [(900 + i, f"hit{i}", "x") for i in range(150)]
    backend = sqlite_backend(_make_db(tmp_path, rows))
    mcp = _query_mcp(backend, {"q": _filter_query(max_rows_default=100)})

    text = await _call(mcp, "query_q", {"name_filter": "hit*"})

    assert "hit0" in text
    assert "skip" not in text
    assert "showing 100 of 150 rows (max_rows=100 reached)." in text


# ---------------------------------------------------------------------------
# Timeouts
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sqlite_statement_timeout_before_any_row(tmp_path: Path) -> None:
    """A real SQLite statement timeout before any row → bare message + hint."""
    db_path = _make_db(tmp_path, [])
    backend = SQLiteBackend(
        ConnectionConfig(backend="sqlite", path=str(db_path), query_timeout_seconds=1)
    )
    backend.connect()
    query = QueryConfig(
        sql=(
            "WITH RECURSIVE c(x) AS (SELECT :start UNION ALL SELECT x+1 FROM c) "
            "SELECT count(*) FROM (SELECT x FROM c LIMIT 500000000)"
        ),
        params={"start": QueryParamConfig(name="start", type="int")},
    )
    mcp = _query_mcp(backend, {"slow": query})

    text = await _call(mcp, "query_slow", {"start": 1})

    assert text == (
        "Query aborted after 1 s (statement timeout). Use more selective parameters."
    )


@pytest.mark.asyncio
async def test_statement_timeout_after_rows_shows_partial_count() -> None:
    """Rows read before the statement timeout are shown with ``N+``."""
    backend = _BatchBackend([[{"id": 1}, {"id": 2}]], timeout_after=True)
    mcp = _query_mcp(backend, {"q": _min_id_query()})

    text = await _call(mcp, "query_q", {"min_id": 0})

    assert "showing 2 of 2+ rows (stopped: statement timeout)." in text
    assert "Use more selective parameters." in text


@pytest.mark.asyncio
async def test_counting_time_limit_stops_counting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The counting time limit stops counting once the display set is full."""
    clock = itertools.count(0.0, 100.0)
    monkeypatch.setattr(
        result_limits, "time", SimpleNamespace(monotonic=lambda: next(clock))
    )
    batches = [[{"id": i} for i in range(3)], [{"id": 3}]]
    mcp = _query_mcp(_BatchBackend(batches), {"q": _min_id_query(max_rows_hard=2)})

    text = await _call(mcp, "query_q", {"min_id": 0, "max_rows": 2})

    assert "showing 2 of 3+ rows (max_rows=2 reached; counting stopped)." in text


# ---------------------------------------------------------------------------
# ToolServer wiring
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tool_server_passes_limits(tmp_path: Path) -> None:
    """``[limits]`` from the project config reaches query and schema tools."""
    backend = sqlite_backend(_make_db(tmp_path, [(1, "n1", "z" * 50)]))
    qcfg = QueryFileConfig(
        queries={"notes": QueryConfig(sql="SELECT note FROM big")},
        limits=LimitsConfig(max_cell_chars=5),
    )
    registry, targets = single_target(backend)
    server = ToolServer(qcfg, targets, registry, allow_updates=False)
    server._register_builtin_tools()  # pylint: disable=protected-access
    server._register_configured_tools()  # pylint: disable=protected-access

    query_text = await _call(server.mcp, "query_notes", {})
    schema_text = await _call(
        server.mcp, "read_columns", {"schema": "main", "table": "big"}
    )

    assert "Long values were cut at 5 chars." in query_text
    assert "Long values were cut at 5 chars." in schema_text
