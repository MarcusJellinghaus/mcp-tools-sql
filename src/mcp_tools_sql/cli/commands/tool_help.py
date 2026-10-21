"""Help text rendering for the `tool` CLI subcommand."""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from mcp.server.fastmcp.tools.base import Tool

EXIT_CODE_HELP = """\
Exit codes:
  0  Success
  1  Config/connection error (bad config, can't reach DB — including a
     connection failure discovered lazily mid-call)
  2  Argparse parse error (unknown flag, unknown tool name, missing
     required flag)
  3  Tool rejected the call (pydantic Field validation, or a body-level
     KeyError/TypeError/ValueError)
  4  Backend/SQL execution error (query ran, database returned an error)\
"""


def _first_line(text: str) -> str:
    """Return the first non-blank line of ``text``, or "" if none."""
    for line in text.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped
    return ""


def render_overview(tools: Sequence[Tool]) -> str:
    """Render the tool listing plus the exit-code table.

    Returns:
        One ``name  description`` line per tool (sorted by name, name
        padded to a common width), followed by a blank line and
        `EXIT_CODE_HELP`.
    """
    sorted_tools = sorted(tools, key=lambda t: t.name)
    width = max((len(t.name) for t in sorted_tools), default=0)
    lines = [
        f"{t.name.ljust(width)}  {_first_line(t.description)}" for t in sorted_tools
    ]
    return "\n".join(lines) + "\n\n" + EXIT_CODE_HELP


def _param_line(name: str, schema: dict[str, Any], required: set[str]) -> str:
    """Render one `--param` detail line from its JSON-schema entry.

    Returns:
        A ``  --name  (required/optional, type=..., ...)`` line, with the
        parameter's description on a second indented line when present.
    """
    marker = "required" if name in required else "optional"
    details = [marker]
    if "type" in schema:
        details.append(f"type={schema['type']}")
    if "enum" in schema:
        details.append(f"choices={schema['enum']}")
    if "default" in schema:
        details.append(f"default={schema['default']!r}")
    line = f"  --{name}  ({', '.join(details)})"
    description = schema.get("description")
    if description:
        line += f"\n      {description}"
    return line


def render_tool_detail(tool: Tool) -> str:
    """Render the detail block for one tool's `--help`.

    Returns:
        The tool's full docstring followed by one block per parameter
        (required/optional, type, choices, default, description).
    """
    required = set(tool.parameters.get("required", []))
    properties = tool.parameters.get("properties", {})
    lines = [tool.name, "", tool.description.strip()]
    if properties:
        lines.append("")
        lines.append("Parameters:")
        lines.extend(
            _param_line(name, schema, required) for name, schema in properties.items()
        )
    return "\n".join(lines)
