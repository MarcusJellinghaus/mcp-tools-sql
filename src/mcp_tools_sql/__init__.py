"""MCP server for safe, configurable SQL database access."""

try:
    from importlib.metadata import version
    __version__ = version("mcp-tools-sql")
except Exception:
    __version__ = "0.0.0.dev0"
