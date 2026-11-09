# Step 4 — Toolkits register into a `ToolSink`

## LLM prompt
Read `pr_info/steps/summary.md`, then implement `pr_info/steps/step_4.md`.
Adapt the tests at the registration call first (they fail), then change the toolkits.
Run pylint, mypy, pytest (`-n auto`). One commit.

## WHERE
- `src/mcp_tools_sql/schema_tools.py`, `query_tools.py`, `update_tools.py`, `validation_tools.py`, `count_tools.py`, `summarize/tools.py`
- `src/mcp_tools_sql/server.py` — add `FastMCPSink`; `ToolServer` uses it internally (constructor signature unchanged in this step)
- Tests (registration call only): `tests/test_count_tools.py`, `test_query_tools.py`, `test_query_tools_readonly.py`, `test_query_limits_tools.py`, `test_schema_tools.py`, `test_schema_tools_multitarget.py`, `test_tool_timeouts.py`, `test_update_tools.py`, `test_update_tools_multitarget.py`, `test_validation_tools.py`, `test_validation_tools_multitarget.py`, `tests/summarize/test_tools.py`, `tests/summarize/tool_helpers.py`

## WHAT
```python
# server.py
class FastMCPSink:
    """ToolSink adapter that registers each spec on a FastMCP instance."""
    def __init__(self, mcp: FastMCP) -> None: ...
    def add(self, spec: ToolSpec) -> None:
        self._mcp.add_tool(spec.fn, name=spec.name, description=spec.description)

# each toolkit
def register(self, sink: ToolSink) -> None: ...
```

| Toolkit | `tool_spec(...)` call |
|---|---|
| `SchemaTools` | `tool_spec(fn, group="sql.schema", read_only=True, name=name, description=config.description)` |
| `ValidationTools` | `group="sql.validation"`, `name="validate_sql"`, `description=_DESCRIPTION` |
| `CountTools` | `group="sql.profiling"`, `name="count_records"` |
| `SummarizeTools` | `group="sql.profiling"`, `name="summarize_columns"` |
| `QueryTools` | `group="sql.query"`, `name=f"query_{name}"`, `description=config.description or f"Run configured query `{name}`."` |
| `UpdateTools` | `group="sql.update"`, `read_only=False`, `name=f"update_{name}"`, `description=cfg.description or f"Run configured update `{name}`."` |

Pass the same description to `build_tool_fn(..., doc)` as to `tool_spec`.

## HOW
- Toolkits import `from mcp_tools_sql.utils.tool_spec import ToolSink, tool_spec` (`ToolSink` under `TYPE_CHECKING` is fine).
- Delete every `if TYPE_CHECKING: from mcp.server.fastmcp import FastMCP` in the toolkits.
- `ToolServer._register_builtin_tools` / `_register_configured_tools`: create `sink = FastMCPSink(self._mcp)` and pass it to each toolkit's `register`. `read_databases` / `verify` stay on `self._mcp.add_tool` for now (moved in step 5).
- Tests: replace `.register(mcp)` with `.register(FastMCPSink(mcp))` and import `FastMCPSink` from `mcp_tools_sql.server`. Also `.register(FastMCP("..."))` → `.register(FastMCPSink(FastMCP("...")))`. Assertions unchanged.
- Docstrings: "Registers … on an MCP server" → "Builds … tool specs".

## ALGORITHM (QueryTools.register, unchanged except the end)
```
for name, config in queries: validate name, resolve target, read-only gate (skip on rejection)
    description = config.description or f"Run configured query `{name}`."
    fn = build_tool_fn(name, sig_params, body, description)
    sink.add(tool_spec(fn, group="sql.query", read_only=True,
                       name=f"query_{name}", description=description))
```

## Tests (new, in `tests/test_query_tools.py` and `tests/test_update_tools.py`)
- A query and an update with `description=""` register with the fallback description (via `ToolCollector`, check `spec.description`).
- `test_query_limits_tools.py` description-less queries now exercise the fallback; adjust any assertion on description text if present.

## DATA
`ToolSpec(name, description, fn, args_model, group, read_only)` per tool.
