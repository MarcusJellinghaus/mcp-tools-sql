"""Builtin section: default queries + tools registered count."""

from __future__ import annotations

from mcp_tools_sql.schema_tools import load_default_queries
from mcp_tools_sql.verification._helpers import CheckResult, make_entry


def verify_builtin() -> dict[str, CheckResult]:
    """Report status of built-in default queries.

    Returns:
        Verifier rows ``default_queries_loaded`` and ``tools_registered_count``.
    """
    result: dict[str, CheckResult] = {}
    try:
        queries = load_default_queries()
        result["default_queries_loaded"] = make_entry(
            ok=bool(queries),
            value=f"{len(queries)} queries",
            error="" if queries else "no queries found",
        )
        result["tools_registered_count"] = make_entry(
            ok=True, value=f"{len(queries)} tools"
        )
    except Exception as exc:  # pylint: disable=broad-except
        result["default_queries_loaded"] = make_entry(
            ok=False, value="(error)", error=str(exc)
        )
        result["tools_registered_count"] = make_entry(
            ok=False, value="(skipped)", error="default_queries_loaded failed"
        )
    return result
