"""Verification engine for the `verify` CLI subcommand and MCP tool.

Stable public API: :func:`verify_all` and the result types
:class:`CheckResult`, :class:`VerifySection`, :class:`VerifySummary` and
:class:`VerifyResult` (see ``docs/python-api.md``). The per-section
``verify_*`` functions are importable but carry no stability promise.
"""

from mcp_tools_sql.verification._helpers import (
    CheckResult,
    VerifyResult,
    VerifySection,
    VerifySummary,
)
from mcp_tools_sql.verification.builtin import verify_builtin
from mcp_tools_sql.verification.config_files import verify_config_files
from mcp_tools_sql.verification.connection import verify_connection
from mcp_tools_sql.verification.dependencies import verify_dependencies
from mcp_tools_sql.verification.environment import verify_environment
from mcp_tools_sql.verification.orchestrator import verify_all
from mcp_tools_sql.verification.queries import verify_queries
from mcp_tools_sql.verification.updates import verify_updates

__all__ = [
    "CheckResult",
    "VerifyResult",
    "VerifySection",
    "VerifySummary",
    "verify_all",
    "verify_builtin",
    "verify_config_files",
    "verify_connection",
    "verify_dependencies",
    "verify_environment",
    "verify_queries",
    "verify_updates",
]
