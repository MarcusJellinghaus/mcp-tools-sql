"""Tests for the per-tool-call logging context manager."""

from __future__ import annotations

import logging
import re

import pytest

from mcp_tools_sql.tool_logging import ToolCallRecord, log_tool_call


@pytest.mark.asyncio
async def test_info_on_success(caplog: pytest.LogCaptureFixture) -> None:
    """Successful run emits a single INFO line with rows/cols/duration_ms."""
    caplog.set_level(logging.INFO, logger="mcp_tools_sql.tool_logging")

    async with log_tool_call("read_tables", {"schema": "dbo"}) as rec:
        rec.record(rows=5, cols=3)

    info_records = [r for r in caplog.records if r.levelno == logging.INFO]
    assert len(info_records) == 1
    msg = info_records[0].getMessage()
    assert "tool=read_tables" in msg
    assert "rows=5" in msg
    assert "cols=3" in msg
    assert "duration_ms=" in msg


@pytest.mark.asyncio
async def test_debug_includes_param_keys_and_values(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """At DEBUG level, entry log contains param_keys, param_values, and sql."""
    caplog.set_level(logging.DEBUG, logger="mcp_tools_sql.tool_logging")

    async with log_tool_call(
        "read_tables",
        {"schema": "dbo", "name": "orders"},
        sql="SELECT * FROM orders",
    ) as rec:
        rec.record(rows=1, cols=2)

    debug_records = [r for r in caplog.records if r.levelno == logging.DEBUG]
    assert debug_records, "expected at least one DEBUG record"
    debug_msg = debug_records[0].getMessage()
    assert "tool=read_tables" in debug_msg
    assert "param_keys=" in debug_msg
    assert "param_values=" in debug_msg
    assert "sql=" in debug_msg
    assert "SELECT * FROM orders" in debug_msg


@pytest.mark.asyncio
async def test_debug_omits_sql_when_none(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """DEBUG entry log omits the sql= field when sql is None."""
    caplog.set_level(logging.DEBUG, logger="mcp_tools_sql.tool_logging")

    async with log_tool_call("read_schemas", {}) as rec:
        rec.record(rows=0, cols=0)

    debug_records = [r for r in caplog.records if r.levelno == logging.DEBUG]
    assert debug_records
    assert "sql=" not in debug_records[0].getMessage()


@pytest.mark.asyncio
async def test_error_path_logs_duration_and_reraises(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Exception inside the block logs ERROR with duration_ms and re-raises."""
    caplog.set_level(logging.ERROR, logger="mcp_tools_sql.tool_logging")

    with pytest.raises(RuntimeError, match="boom"):
        async with log_tool_call("x", {}) as rec:
            rec.record(rows=0, cols=0)
            raise RuntimeError("boom")

    error_records = [r for r in caplog.records if r.levelno == logging.ERROR]
    assert len(error_records) == 1
    msg = error_records[0].getMessage()
    assert re.search(r"tool=x duration_ms=\d+ error=boom", msg)


@pytest.mark.asyncio
async def test_record_defaults_zero(caplog: pytest.LogCaptureFixture) -> None:
    """Without rec.record(...), INFO line shows rows=0 cols=0."""
    caplog.set_level(logging.INFO, logger="mcp_tools_sql.tool_logging")

    async with log_tool_call("noop", {}):
        pass

    info_records = [r for r in caplog.records if r.levelno == logging.INFO]
    assert len(info_records) == 1
    msg = info_records[0].getMessage()
    assert "rows=0" in msg
    assert "cols=0" in msg


@pytest.mark.asyncio
async def test_no_info_log_on_error(caplog: pytest.LogCaptureFixture) -> None:
    """When the body raises, no INFO success line is emitted."""
    caplog.set_level(logging.DEBUG, logger="mcp_tools_sql.tool_logging")

    with pytest.raises(ValueError):
        async with log_tool_call("x", {}):
            raise ValueError("nope")

    info_records = [r for r in caplog.records if r.levelno == logging.INFO]
    assert not info_records


def test_record_dataclass_defaults() -> None:
    """ToolCallRecord defaults rows and cols to 0 and updates via record()."""
    rec = ToolCallRecord()
    assert rec.rows == 0
    assert rec.cols == 0
    rec.record(rows=7, cols=4)
    assert rec.rows == 7
    assert rec.cols == 4
