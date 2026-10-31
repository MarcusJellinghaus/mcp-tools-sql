"""Subprocess execution utilities — thin shim over mcp-coder-utils."""

from mcp_coder_utils.subprocess_runner import (
    CommandOptions,
    CommandResult,
    execute_subprocess,
)

__all__ = ["CommandOptions", "CommandResult", "execute_subprocess"]
