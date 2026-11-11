"""Tests for `verify_queries` in config-only mode (``registry=None``)."""

from __future__ import annotations

from mcp_tools_sql.config.models import QueryConfig, ResolvedTargets
from mcp_tools_sql.verification import verify_queries
from mcp_tools_sql.verification._helpers import checks_ok


def test_verify_queries_registry_none_omits_sql_row(
    sqlite_targets: ResolvedTargets,
) -> None:
    """registry=None → no ``.sql`` row; the config rows are still emitted."""
    queries = {
        "plain": QueryConfig(
            sql="SELECT * FROM customers", params={}, max_rows_default=10
        ),
    }
    result = verify_queries(queries, sqlite_targets, None, {})

    assert list(result.keys()) == [
        "plain.read_only[sqlite]",
        "plain.params",
        "plain.max_rows_default",
        "plain.max_rows_hard",
        "plain.description",
    ]
    assert result["plain.read_only[sqlite]"]["ok"] is True
    assert checks_ok(result) is True


def test_verify_queries_registry_none_flags_non_read_only(
    sqlite_targets: ResolvedTargets,
) -> None:
    """registry=None still fails a DELETE query on its ``read_only`` row."""
    queries = {
        "wipe": QueryConfig(sql="DELETE FROM t", params={}, max_rows_default=10),
    }
    result = verify_queries(queries, sqlite_targets, None, {})

    assert "wipe.sql" not in result
    row = result["wipe.read_only[sqlite]"]
    assert row["ok"] is False
    assert row["severity"] == "error"
    assert checks_ok(result) is False


def test_verify_queries_registry_none_bad_pin(
    sqlite_targets: ResolvedTargets,
) -> None:
    """registry=None with a bad pin → error rows, but no ``.sql`` row."""
    queries = {
        "lost": QueryConfig(
            sql="SELECT * FROM customers",
            params={},
            max_rows_default=10,
            connection="nope",
        ),
    }
    result = verify_queries(queries, sqlite_targets, None, {})

    assert "lost.sql" not in result
    assert result["lost.read_only"]["ok"] is False
    assert result["lost.params"]["ok"] is False
    assert "nope" in result["lost.params"]["error"]
    assert checks_ok(result) is False
