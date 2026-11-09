"""Help text rendering for the `tool` CLI subcommand."""

from __future__ import annotations

import warnings
from collections.abc import Sequence
from typing import TYPE_CHECKING, Any

from pydantic.json_schema import PydanticJsonSchemaWarning

if TYPE_CHECKING:
    from mcp_tools_sql.utils.tool_spec import ToolSpec

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


def render_overview(specs: Sequence[ToolSpec]) -> str:
    """Render the tool listing plus the exit-code table.

    Returns:
        One ``name  description`` line per tool (sorted by name, name
        padded to a common width), followed by a blank line and
        `EXIT_CODE_HELP`.
    """
    sorted_specs = sorted(specs, key=lambda s: s.name)
    width = max((len(s.name) for s in sorted_specs), default=0)
    lines = [
        f"{s.name.ljust(width)}  {_first_line(s.description)}" for s in sorted_specs
    ]
    return "\n".join(lines) + "\n\n" + EXIT_CODE_HELP


def _parameters_schema(spec: ToolSpec) -> dict[str, Any]:
    """Return the JSON schema of ``spec.args_model``.

    Defaults that are not JSON-serialisable (the ``_UNSET`` sentinel) are
    dropped from the schema; pydantic's warning about that is suppressed.

    Returns:
        The model's JSON schema dict.
    """
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", PydanticJsonSchemaWarning)
        return spec.args_model.model_json_schema()


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


def render_tool_detail(spec: ToolSpec) -> str:
    """Render the detail block for one tool's `--help`.

    Returns:
        The tool's full description followed by one block per parameter
        (required/optional, type, choices, default, description).
    """
    schema = _parameters_schema(spec)
    required = set(schema.get("required", []))
    properties = schema.get("properties", {})
    lines = [spec.name, "", spec.description.strip()]
    if properties:
        lines.append("")
        lines.append("Parameters:")
        lines.extend(
            _param_line(name, schema, required) for name, schema in properties.items()
        )
    return "\n".join(lines)
