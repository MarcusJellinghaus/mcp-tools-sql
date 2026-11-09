"""Fan-out (``database="*"``) reads share display and counting budgets (#97)."""

from __future__ import annotations

from collections.abc import Generator, Iterator
from contextlib import contextmanager
from typing import Any

import pytest

from mcp_tools_sql.backends.base import DatabaseBackend, Deadline, QueryTimeoutError
from mcp_tools_sql.config.models import LimitsConfig, QueryConfig, ResolvedTargets
from mcp_tools_sql.query_helpers import build_schema_body
from tests.target_helpers import RecordingRegistry, make_target

_TIMEOUT = "Query aborted after 30 s (statement timeout)."


class _StreamBackend(DatabaseBackend):
    """Backend yielding preset rows in batches, then optionally raising."""

    def __init__(
        self,
        rows: list[dict[str, Any]],
        *,
        batch_size: int = 10,
        raises: Exception | None = None,
    ) -> None:
        self._rows = rows
        self._batch_size = batch_size
        self._raises = raises
        self.closed_generators = 0

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
        """Yield copies of the preset rows in batches, then raise if configured.

        Yields:
            Batches of at most ``batch_size`` row copies.

        Raises:
            Exception: The configured ``raises`` after the last batch.
        """
        try:
            for start in range(0, len(self._rows), self._batch_size):
                yield [dict(r) for r in self._rows[start : start + self._batch_size]]
            if self._raises is not None:
                raise self._raises
        finally:
            self.closed_generators += 1


def _rows(prefix: str, n: int) -> list[dict[str, Any]]:
    return [{"name": f"{prefix}{i}"} for i in range(n)]


def _targets(backend_name: str = "sqlite") -> ResolvedTargets:
    """One connection ``prod`` with databases ``sales``, ``hr``, ``fin``."""
    sales = make_target(
        "prod",
        "sales",
        is_default=True,
        default_database="sales",
        backend_name=backend_name,
    )
    hr = make_target("prod", "hr", default_database="sales", backend_name=backend_name)
    fin = make_target(
        "prod", "fin", default_database="sales", backend_name=backend_name
    )
    return ResolvedTargets(
        targets=[sales, hr, fin], default=sales, file_default_connection="prod"
    )


def _config() -> QueryConfig:
    return QueryConfig(description="List tables", sql="SELECT name FROM t")


async def _fanout(
    backends: dict[str, DatabaseBackend],
    *,
    limits: LimitsConfig | None = None,
    backend_name: str = "sqlite",
    **kwargs: Any,
) -> str:
    registry = RecordingRegistry({("prod", db): b for db, b in backends.items()})
    body = build_schema_body(
        "read_tables", _config(), registry, _targets(backend_name), limits=limits
    )
    return await body(database="*", **kwargs)


def _table_rows(text: str) -> list[str]:
    """Return the data lines of the rendered table."""
    return text.split("\n\n")[0].splitlines()[2:]


@pytest.mark.asyncio
async def test_display_budget_only_counts_every_database() -> None:
    """(a) Display budget hit in sales; counting continues through hr and fin."""
    text = await _fanout(
        {
            "sales": _StreamBackend(_rows("s", 20)),
            "hr": _StreamBackend(_rows("h", 7)),
            "fin": _StreamBackend([]),
        },
        max_rows=5,
    )

    assert len(_table_rows(text)) == 5
    assert "showing 5 of 27 rows (max_rows=5 reached)." in text
    assert "Matched: sales 20, hr 7, fin 0." in text


@pytest.mark.asyncio
async def test_counting_budget_stops_later_databases() -> None:
    """(b) sales exhausts max_count_rows → ``100+``, later dbs not queried."""
    hr = _StreamBackend(_rows("h", 3))
    text = await _fanout(
        {"sales": _StreamBackend(_rows("s", 150)), "hr": hr, "fin": _StreamBackend([])},
        limits=LimitsConfig(max_count_rows=100),
        max_rows=5,
    )

    assert "counting stopped" in text
    assert (
        "Matched: sales 100+, hr not queried (limit reached), "
        "fin not queried (limit reached)." in text
    )
    assert hr.closed_generators == 0  # never opened


@pytest.mark.asyncio
async def test_timeout_after_rows_keeps_shown_rows() -> None:
    """(c) A timeout after rows → ``N+``, rows kept, later dbs not queried."""
    text = await _fanout(
        {
            "sales": _StreamBackend(_rows("s", 3)),
            "hr": _StreamBackend(_rows("h", 2), raises=QueryTimeoutError(30)),
            "fin": _StreamBackend(_rows("f", 4)),
        },
        backend_name="mssql",
    )

    table = "\n".join(_table_rows(text))
    assert "h1" in table
    assert "hr" in table  # _database value visible on the kept rows
    assert "f0" not in text
    assert "stopped: statement timeout" in text
    assert (
        "Matched: sales 3, hr 2+, fin not queried (stopped: statement timeout)." in text
    )


@pytest.mark.asyncio
async def test_timeout_before_any_row_renders_error_line() -> None:
    """(d) A timeout before any row → error line, later dbs not queried."""
    text = await _fanout(
        {
            "sales": _StreamBackend(_rows("s", 3)),
            "hr": _StreamBackend([], raises=QueryTimeoutError(30)),
            "fin": _StreamBackend(_rows("f", 4)),
        },
        backend_name="mssql",
    )

    assert f"hr: {_TIMEOUT}" in text
    assert "f0" not in text
    assert "Matched: sales 3, fin not queried (stopped: statement timeout)." in text


@pytest.mark.asyncio
async def test_display_budget_is_shared_across_databases() -> None:
    """Total shown rows across databases never exceed ``max_rows``."""
    text = await _fanout(
        {
            "sales": _StreamBackend(_rows("s", 3)),
            "hr": _StreamBackend(_rows("h", 4)),
            "fin": _StreamBackend(_rows("f", 4)),
        },
        max_rows=5,
    )

    table = "\n".join(_table_rows(text))
    assert len(_table_rows(text)) == 5
    assert "s2" in table
    assert "h1" in table
    assert "h2" not in table
    assert "Matched: sales 3, hr 4, fin 4." in text


@pytest.mark.asyncio
async def test_counting_budget_is_shared_across_databases() -> None:
    """Counted rows across databases never exceed ``max_count_rows``."""
    text = await _fanout(
        {
            "sales": _StreamBackend(_rows("s", 60)),
            "hr": _StreamBackend(_rows("h", 60)),
            "fin": _StreamBackend(_rows("f", 10)),
        },
        limits=LimitsConfig(max_count_rows=100),
        max_rows=5,
    )

    assert "showing 5 of 100+ rows" in text
    assert "Matched: sales 60, hr 40+, fin not queried (limit reached)." in text


@pytest.mark.asyncio
async def test_non_timeout_error_keeps_counting_other_databases() -> None:
    """A non-timeout error → its error line; later databases still read."""
    text = await _fanout(
        {
            "sales": _StreamBackend(_rows("s", 2)),
            "hr": _StreamBackend([], raises=RuntimeError("boom")),
            "fin": _StreamBackend(_rows("f", 2)),
        },
    )

    assert "hr: boom" in text
    assert "f1" in text
    assert "s1" in text


@pytest.mark.asyncio
async def test_backend_lookup_error_is_recorded_per_database() -> None:
    """``registry.backend_for`` failing is an error line, not an abort."""
    text = await _fanout(
        {
            "sales": _StreamBackend(_rows("s", 2)),
            "fin": _StreamBackend(_rows("f", 2)),
        },
    )

    assert "hr: " in text  # KeyError from the registry, recorded inline
    assert "s1" in text
    assert "f1" in text


@pytest.mark.asyncio
async def test_generators_closed_on_early_stop() -> None:
    """The inner backend generator is closed when counting stops early."""
    sales = _StreamBackend(_rows("s", 150))
    await _fanout(
        {"sales": sales, "hr": _StreamBackend([]), "fin": _StreamBackend([])},
        limits=LimitsConfig(max_count_rows=100),
    )

    assert sales.closed_generators == 1


@pytest.mark.asyncio
async def test_single_database_connection_renders_like_single_target() -> None:
    """A connection with one database gets no ``Matched:`` footer."""
    only = make_target("solo", "main", is_default=True, default_database="main")
    sales = make_target("prod", "sales", default_database="sales")
    targets = ResolvedTargets(
        targets=[sales, only], default=sales, file_default_connection="prod"
    )
    registry = RecordingRegistry(
        {
            ("solo", "main"): _StreamBackend(_rows("m", 10)),
            ("prod", "sales"): _StreamBackend([]),
        }
    )
    body = build_schema_body("read_tables", _config(), registry, targets)

    text = await body(connection="solo", database="*", max_rows=5)

    assert "showing 5 of 10 rows" in text
    assert "Matched:" not in text
