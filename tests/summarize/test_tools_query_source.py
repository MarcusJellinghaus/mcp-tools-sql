"""End-to-end tests for the ``summarize_columns`` ``sql=`` source path.

The SQLite cases drive a real database through
``create_connected_server_and_client_session``: an arbitrary read-only SELECT
is validated, probed for its output columns, profiled, and rendered with the
call-level notes in a trailing footer. The MagicMock cases pin the T-SQL
rendering (every profiling query selects ``FROM (...) AS src``) and the two
halves of the LOB hint's gate.

Two tests here are deliberate regression guards:
``test_unresolvable_source_returns_invalid_sql`` proves the source build stays
inside ``core``'s exception tail, and the ``sqlite_probe_cannot_see`` pair pins
the documented SQLite type divergence against the table path -- the gap must
never become silent.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from mcp_tools_sql.summarize.source import (
    ORDER_BY_STRIPPED_NOTE,
    ROW_LIMITED_NOTE,
    SQLITE_PROBE_TYPE_LIMITS_NOTE,
    TYPES_PROBED_NOTE,
)
from mcp_tools_sql.summarize.tools import LOB_HINT, SOURCE_CHOICE_MESSAGE
from tests.summarize.tool_helpers import call_summarize, client_for, sqlite_backend

# A source whose probe resolves one ordinary string column, reused by the
# MagicMock T-SQL cases.
_STRING_SCALAR_ROW: dict[str, Any] = {
    "c0__nonnull": 10,
    "c0__distinct": 4,
    "c0__min": "a",
    "c0__max": "z",
    "c0__empty": 0,
    "c0__len_min": 1,
    "c0__len_max": 5,
    "c0__len_avg": 3.0,
}


def _probe_backend(
    names: list[str],
    rows: list[tuple[Any, ...]],
    *,
    fail_queries_with: Exception | None = None,
) -> tuple[MagicMock, dict[str, str]]:
    """Build a backend double: canned probe result, captured profiling SQL.

    Args:
        names: Output column names the probe reports.
        rows: Sampled probe rows.
        fail_queries_with: When set, every *non-probe* query raises it -- the
            source resolves, then the profiling pass fails.

    Returns:
        The configured :class:`MagicMock` and a dict capturing the count /
        scalar / value-list SQL under those keys.
    """
    captured: dict[str, str] = {}

    def fake(sql: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        if fail_queries_with is not None:
            raise fail_queries_with
        if "row_count" in sql:
            captured["count_sql"] = sql
            return [{"row_count": 10}]
        if "c0__nonnull" in sql:
            captured["scalar_sql"] = sql
            return [_STRING_SCALAR_ROW]
        captured["value_sql"] = sql
        return [{"value": "a", "freq": 3}]

    backend = MagicMock()
    backend.execute_readonly_query_with_columns.return_value = (names, rows)
    backend.execute_readonly_query.side_effect = fake
    return backend, captured


# ---------------------------------------------------------------------------
# SQLite end-to-end — the sources the feature exists for
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_self_join_source_profiles_aliased_columns(profiling_db: Path) -> None:
    """A join is profiled per aliased output column, with the probed footer."""
    backend = sqlite_backend(profiling_db)
    async with client_for(backend) as client:
        out = await call_summarize(
            client,
            sql=(
                "SELECT a.qty AS a_qty, b.ref AS b_ref "
                "FROM profile_me a JOIN profile_me b ON a.qty = b.qty"
            ),
        )
    assert "a_qty  (INTEGER, numeric)" in out
    assert "b_ref  (TEXT, string)" in out
    assert "rows 6" in out
    assert TYPES_PROBED_NOTE in out


@pytest.mark.asyncio
async def test_aggregate_source_with_outside_where(profiling_db: Path) -> None:
    """``where`` filters the aggregate from outside -- HAVING-like filtering.

    ``profile_me`` groups into four categories (NULL, whitespace, ``x``, ``y``)
    of which only ``x`` and ``y`` have more than one row, so the predicate on
    the computed ``orders`` column leaves exactly two.
    """
    backend = sqlite_backend(profiling_db)
    async with client_for(backend) as client:
        out = await call_summarize(
            client,
            sql=(
                "SELECT category, COUNT(*) AS orders "
                "FROM profile_me GROUP BY category"
            ),
            where="orders > :min",
            params={"min": 1},
        )
    assert not out.startswith("Invalid")
    assert "orders  (INTEGER, numeric)" in out
    assert "rows 2" in out
    assert "min 2 | max 2" in out


@pytest.mark.asyncio
async def test_placeholder_inside_the_source_binds(profiling_db: Path) -> None:
    """A ``:name`` in the source binds through the same ``params`` dict."""
    backend = sqlite_backend(profiling_db)
    async with client_for(backend) as client:
        out = await call_summarize(
            client,
            sql="SELECT qty FROM profile_me WHERE qty > :min",
            params={"min": 5},
        )
    assert not out.startswith("Invalid")
    assert "rows 3" in out
    assert "min 7 | max 20" in out
    assert "sum 37" in out


@pytest.mark.asyncio
async def test_order_by_stripped_note(profiling_db: Path) -> None:
    """An unlimited ``ORDER BY`` is dropped and the footer says so."""
    backend = sqlite_backend(profiling_db)
    async with client_for(backend) as client:
        out = await call_summarize(
            client, sql="SELECT qty FROM profile_me ORDER BY qty DESC"
        )
    assert "rows 6" in out
    assert ORDER_BY_STRIPPED_NOTE in out
    assert ROW_LIMITED_NOTE not in out


@pytest.mark.asyncio
async def test_row_limited_source_keeps_order_by(profiling_db: Path) -> None:
    """With a ``LIMIT`` the ordering decides which rows are profiled."""
    backend = sqlite_backend(profiling_db)
    async with client_for(backend) as client:
        out = await call_summarize(
            client, sql="SELECT qty FROM profile_me ORDER BY qty DESC LIMIT 3"
        )
    assert "rows 3" in out
    assert "min 7 | max 20" in out  # the three largest, so the order was kept
    assert ROW_LIMITED_NOTE in out
    assert ORDER_BY_STRIPPED_NOTE not in out


@pytest.mark.asyncio
async def test_duplicate_output_columns_rejected(profiling_db: Path) -> None:
    """Duplicate output names are unaddressable; the message names the fix."""
    backend = sqlite_backend(profiling_db)
    async with client_for(backend) as client:
        out = await call_summarize(
            client,
            sql=(
                "SELECT a.qty, b.qty FROM profile_me a "
                "JOIN profile_me b ON a.qty = b.qty"
            ),
        )
    assert "duplicate or unnamed output columns" in out
    assert "AS" in out  # the aliasing recovery


@pytest.mark.asyncio
async def test_zero_row_source_message(profiling_db: Path) -> None:
    """A resolvable source with no rows gets the query wording, not a table's."""
    backend = sqlite_backend(profiling_db)
    async with client_for(backend) as client:
        out = await call_summarize(client, sql="SELECT a, b FROM empty_t")
    assert out == "The source query returned 0 rows."


@pytest.mark.asyncio
async def test_where_matching_nothing_names_the_source(profiling_db: Path) -> None:
    """The empty-filter message attributes the total to the source, not a table."""
    backend = sqlite_backend(profiling_db)
    async with client_for(backend) as client:
        out = await call_summarize(
            client,
            sql="SELECT qty FROM profile_me",
            where="qty > :min",
            params={"min": 100},
        )
    assert out == "No rows match the where predicate (source has 6 rows)."


# ---------------------------------------------------------------------------
# Source choice + read-only gates — all before any backend call
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "kwargs",
    [
        pytest.param(
            {"schema": "main", "table": "profile_me", "sql": "SELECT 1"}, id="both"
        ),
        pytest.param({}, id="neither"),
        pytest.param({"schema": "main"}, id="schema-without-table"),
        pytest.param({"table": "profile_me"}, id="table-without-schema"),
    ],
)
@pytest.mark.asyncio
async def test_source_choice_message(kwargs: dict[str, Any]) -> None:
    """Both / neither / a half-supplied pair share one message, executing nothing."""
    backend = MagicMock()
    async with client_for(backend) as client:
        out = await call_summarize(client, **kwargs)
    assert out == SOURCE_CHOICE_MESSAGE
    backend.execute_readonly_query.assert_not_called()
    backend.execute_readonly_query_with_columns.assert_not_called()


@pytest.mark.parametrize(
    ("sql", "fragment"),
    [
        ("DELETE FROM profile_me", "Not read-only."),
        ("VALUES (1), (2)", "must be a SELECT"),
    ],
)
@pytest.mark.asyncio
async def test_non_select_sources_rejected_before_execution(
    sql: str, fragment: str
) -> None:
    """A write or a bare ``VALUES`` root never reaches the backend."""
    backend = MagicMock()
    async with client_for(backend) as client:
        out = await call_summarize(client, sql=sql)
    assert fragment in out
    backend.execute_readonly_query.assert_not_called()
    backend.execute_readonly_query_with_columns.assert_not_called()


@pytest.mark.parametrize(
    ("sql", "fragment"),
    [
        ("SELECT * FROM no_such_table", "no such table"),
        (
            "SELECT qty FROM profile_me a JOIN profile_me b ON a.qty = b.qty",
            "ambiguous column name",
        ),
    ],
)
@pytest.mark.asyncio
async def test_unresolvable_source_returns_invalid_sql(
    profiling_db: Path, sql: str, fragment: str
) -> None:
    """A source that parses but fails at execution is reported, not raised.

    Both sources pass every static gate and only fail when the probe runs, so
    they reach the backend from inside ``build_query_source``. The client
    session raises on an escaping exception, so simply getting a string back is
    the regression guard for keeping that call inside ``core``'s ``try``.
    """
    backend = sqlite_backend(profiling_db)
    async with client_for(backend) as client:
        out = await call_summarize(client, sql=sql)
    assert out.startswith("Invalid SQL.")
    assert fragment in out
    assert LOB_HINT not in out  # SQLite never gets the T-SQL-only hint


# ---------------------------------------------------------------------------
# The documented SQLite type divergence, pinned against the table path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sqlite_probe_cannot_see_declared_date_type(profiling_db: Path) -> None:
    """A DATE column profiles as string via ``sql=``, temporal via the table path.

    ``backends/sqlite.py`` connects without ``detect_types``, so the probe sees
    a plain ``str``. The gap is surfaced through
    :data:`SQLITE_PROBE_TYPE_LIMITS_NOTE`, never silently. If SQLite ever
    resolves declared types for a sampled source, this is the test to update.
    """
    backend = sqlite_backend(profiling_db)
    async with client_for(backend) as client:
        probed = await call_summarize(client, sql="SELECT created FROM profile_me")
        catalog = await call_summarize(
            client, "main", "profile_me", columns=["created"]
        )

    assert "created  (TEXT, string)" in probed
    assert "length  min 10" in probed
    assert "min 2020-01-01 | max 2024-02-29" not in probed
    assert SQLITE_PROBE_TYPE_LIMITS_NOTE in probed

    assert "created  (DATE, temporal)" in catalog
    assert "min 2020-01-01 | max 2024-02-29" in catalog
    assert SQLITE_PROBE_TYPE_LIMITS_NOTE not in catalog


@pytest.mark.asyncio
async def test_sqlite_probe_cannot_see_declared_boolean_type(
    profiling_db: Path,
) -> None:
    """A BOOLEAN column profiles as numeric via ``sql=``, boolean via the table."""
    backend = sqlite_backend(profiling_db)
    async with client_for(backend) as client:
        probed = await call_summarize(client, sql="SELECT is_active FROM profile_me")
        catalog = await call_summarize(
            client, "main", "profile_me", columns=["is_active"]
        )

    assert "is_active  (INTEGER, numeric)" in probed
    assert "true 3 (50.0%)" not in probed
    assert SQLITE_PROBE_TYPE_LIMITS_NOTE in probed

    assert "is_active  (BOOLEAN, boolean)" in catalog
    assert "true 3 (50.0%)" in catalog


# ---------------------------------------------------------------------------
# Narrowing + triage against probed metadata
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_columns_narrowing_is_case_insensitive(profiling_db: Path) -> None:
    """``columns=`` matches probed output names ignoring case."""
    backend = sqlite_backend(profiling_db)
    async with client_for(backend) as client:
        out = await call_summarize(
            client, sql="SELECT qty, category FROM profile_me", columns=["QTY"]
        )
    assert "qty  (INTEGER, numeric)" in out
    assert "category  (" not in out


@pytest.mark.parametrize(
    ("columns", "fragment"),
    [([], "empty list"), (["nope"], "Unknown column(s): nope.")],
)
@pytest.mark.asyncio
async def test_columns_guards_reach_probed_metadata(
    profiling_db: Path, columns: list[str], fragment: str
) -> None:
    """The existing empty / unknown messages apply to probed names too."""
    backend = sqlite_backend(profiling_db)
    async with client_for(backend) as client:
        out = await call_summarize(
            client, sql="SELECT qty, category FROM profile_me", columns=columns
        )
    assert fragment in out
    assert "qty" in out  # the available-names list echoes the probed names


@pytest.mark.asyncio
async def test_wide_source_renders_triage_with_notes_after_footers(
    profiling_db: Path,
) -> None:
    """A > 15-column source triages; the notes follow triage's own footers."""
    backend = sqlite_backend(profiling_db)
    async with client_for(backend) as client:
        out = await call_summarize(client, sql="SELECT * FROM wide_t")
    assert "null_pct" in out  # triage table header
    assert "Narrow with columns=" in out  # triage's own footer, still first
    assert out.index("Narrow with columns=") < out.index(TYPES_PROBED_NOTE)
    assert out.endswith(SQLITE_PROBE_TYPE_LIMITS_NOTE)


@pytest.mark.asyncio
async def test_table_path_output_is_unchanged(profiling_db: Path) -> None:
    """The ``schema``/``table`` path renders byte-identically -- no stray footer.

    Pinned in full rather than by substring: the notes footer is appended
    *after* ``render_summary`` returns, so only an exact comparison proves a
    table source contributes none of it.
    """
    backend = sqlite_backend(profiling_db)
    async with client_for(backend) as client:
        out = await call_summarize(client, "main", "profile_me", columns=["qty"])
    assert out == (
        "qty  (INTEGER, numeric)\n"
        "  rows 6 | nulls 0 (0.0%) | distinct 6\n"
        "  min -5 | max 20 | mean 5.8 | sum 35\n"
        "  zeros 1 (16.7%) | negatives 1 (16.7%)\n"
        "  sample values (6 of 6 distinct — every value unique):\n"
        "    -5\n"
        "    0\n"
        "    3\n"
        "    7\n"
        "    10\n"
        "    20"
    )


# ---------------------------------------------------------------------------
# MagicMock T-SQL: derived-table rendering and the LOB hint's gate
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tsql_profiling_queries_select_from_the_derived_table() -> None:
    """Count, scalar and value-list all select ``FROM (...) AS src``."""
    backend, captured = _probe_backend(["s"], [("hello",)])
    async with client_for(backend, backend_name="mssql") as client:
        out = await call_summarize(client, sql="SELECT s FROM t")
    assert not out.startswith("Invalid")
    assert ") AS src" in captured["count_sql"]
    assert ") AS src" in captured["scalar_sql"]
    assert ") AS src" in captured["value_sql"]


@pytest.mark.asyncio
async def test_tsql_probed_string_column_profiles_as_string() -> None:
    """A probed ``str`` gets the string aggregates, not the ``other`` shape."""
    backend, captured = _probe_backend(["s"], [("hello",)])
    async with client_for(backend, backend_name="mssql") as client:
        out = await call_summarize(client, sql="SELECT s FROM t")
    assert "s  (nvarchar, string)" in out
    assert "COUNT(DISTINCT" in captured["scalar_sql"]
    assert "LEN(" in captured["scalar_sql"]
    assert "DATALENGTH" not in captured["scalar_sql"]
    assert "value_sql" in captured  # a value list was issued for the column


@pytest.mark.asyncio
async def test_tsql_probed_source_failure_appends_lob_hint() -> None:
    """A driver error after a probed source resolved carries the LOB hint.

    A ``sqlite3`` error stands in for the pyodbc one so the test runs without
    the optional driver installed; the hint is gated on the *dialect* and
    ``types_probed``, never on the exception type.
    """
    backend, _captured = _probe_backend(
        ["s"],
        [("hello",)],
        fail_queries_with=sqlite3.OperationalError("Msg 306: text/ntext/image"),
    )
    async with client_for(backend, backend_name="mssql") as client:
        out = await call_summarize(client, sql="SELECT s FROM t")
    assert out.startswith("Invalid SQL.")
    assert out.endswith(LOB_HINT)


@pytest.mark.asyncio
async def test_tsql_probe_failure_gets_no_lob_hint() -> None:
    """The probe is a bare ``SELECT *``: its failure is not a LOB failure."""
    backend = MagicMock()
    backend.execute_readonly_query_with_columns.side_effect = sqlite3.OperationalError(
        "no such table: t"
    )
    async with client_for(backend, backend_name="mssql") as client:
        out = await call_summarize(client, sql="SELECT s FROM t")
    assert out.startswith("Invalid SQL.")
    assert LOB_HINT not in out


@pytest.mark.asyncio
async def test_sqlite_probed_source_failure_gets_no_lob_hint() -> None:
    """``types_probed`` alone must not staple T-SQL advice onto SQLite errors."""
    backend, _captured = _probe_backend(
        ["s"],
        [("hello",)],
        fail_queries_with=sqlite3.OperationalError("database disk image is malformed"),
    )
    async with client_for(backend) as client:
        out = await call_summarize(client, sql="SELECT s FROM t")
    assert out.startswith("Invalid SQL.")
    assert LOB_HINT not in out
