"""Per-tool-call observability helper.

Distinct from `mcp_tools_sql.utils.log_utils`, which configures process-wide
logging. This module emits one structured log line per MCP tool invocation:
INFO with row/col counts + duration on success; DEBUG adds param keys/values
and resolved SQL (may contain PII — only enable DEBUG in trusted environments);
ERROR on exceptions including duration_ms.
"""

from __future__ import annotations

import logging
import time
from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any

log = logging.getLogger(__name__)


@dataclass
class ToolCallRecord:
    """Mutable counters reported back from an MCP tool body."""

    rows: int = 0
    cols: int = 0

    def record(self, rows: int, cols: int) -> None:
        """Record the result shape for the success log line."""
        self.rows = rows
        self.cols = cols


@asynccontextmanager
async def log_tool_call(
    name: str,
    params: Mapping[str, Any] | None = None,
    *,
    sql: str | None = None,
) -> AsyncIterator[ToolCallRecord]:
    """Per-tool-call logging context manager.

    DEBUG output may include parameter values and resolved SQL — only enable
    DEBUG in trusted environments (these can contain PII / secrets).

    Yields:
        The mutable :class:`ToolCallRecord` that callers populate via
        ``record()`` with row/column counts before context exit; those
        counts are emitted in the success INFO log line.
    """
    rec = ToolCallRecord()
    params_map: Mapping[str, Any] = params if params is not None else {}
    start = time.monotonic()

    if log.isEnabledFor(logging.DEBUG):
        param_keys = sorted(params_map.keys())
        param_values = {k: params_map[k] for k in param_keys}
        if sql is None:
            log.debug(
                "tool=%s param_keys=%s param_values=%s",
                name,
                param_keys,
                param_values,
            )
        else:
            log.debug(
                "tool=%s param_keys=%s param_values=%s sql=%s",
                name,
                param_keys,
                param_values,
                sql,
            )

    try:
        yield rec
    except Exception as exc:
        dur_ms = int((time.monotonic() - start) * 1000)
        log.error("tool=%s duration_ms=%d error=%s", name, dur_ms, exc)
        raise
    else:
        dur_ms = int((time.monotonic() - start) * 1000)
        log.info(
            "tool=%s rows=%d cols=%d duration_ms=%d",
            name,
            rec.rows,
            rec.cols,
            dur_ms,
        )
