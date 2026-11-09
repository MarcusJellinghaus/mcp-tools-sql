"""Tool contract — thin shim over mcp-coder-utils."""

from mcp_coder_utils.tool_spec import ToolCollector, ToolSink, ToolSpec, tool_spec

__all__ = ["ToolSpec", "tool_spec", "ToolSink", "ToolCollector"]
