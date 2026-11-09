# Step 7 — CLI `tool` subcommand on `ToolSpec`s

## LLM prompt
Read `pr_info/steps/summary.md`, then implement `pr_info/steps/step_7.md`.
Convert the tests first, then the CLI modules. Run pylint, mypy, pytest (`-n auto`). One commit.

## WHERE
- `src/mcp_tools_sql/cli/commands/tool.py`, `tool_args.py`, `tool_dispatch.py`, `tool_help.py`
- Tests: `tests/cli/test_tool_args.py`, `tests/cli/test_tool_dispatch.py`, `tests/cli/test_tool.py`

## WHAT
```python
# tool_args.py
def build_tool_argparser(spec: ToolSpec, prog: str) -> argparse.ArgumentParser  # uses inspect.signature(spec.fn)
# tool_help.py
def render_overview(specs: Sequence[ToolSpec]) -> str
def render_tool_detail(spec: ToolSpec) -> str
def _parameters_schema(spec: ToolSpec) -> dict[str, Any]
# tool_dispatch.py
async def invoke_tool(spec: ToolSpec, kwargs: dict[str, Any]) -> tuple[int, str]
```

## ALGORITHM
```
_parameters_schema(spec):
  with warnings.catch_warnings():
      warnings.simplefilter("ignore", PydanticJsonSchemaWarning)
      return spec.args_model.model_json_schema()

invoke_tool(spec, kwargs):
  try:
    validated = spec.args_model.model_validate(kwargs)
    result = await spec.fn(**{f: getattr(validated, f) for f in spec.args_model.model_fields})
    return EXIT_OK, str(result)
  except ValidationError as exc: return EXIT_REJECTED, str(exc)
  except Exception as exc: return classify_exception(exc), f"{type(exc).__name__}: {exc}"

tool.run:
  server, _ = build_tool_server(args)        # (ValueError, OSError) → exit 1 + config hint (unchanged)
  specs = {s.name: s for s in server.toolset.specs}
  overview / name parser from specs; spec = specs[ns.name]   # drop the "vanished" RuntimeError guard
```
Do not use `model_dump()` — it warns on the `_UNSET` sentinel.

## HOW
- Replace `TYPE_CHECKING` imports of `mcp.server.fastmcp.tools.base.Tool` with `from mcp_tools_sql.utils.tool_spec import ToolSpec`.
- `render_tool_detail`: `required`/`properties` from `_parameters_schema(spec)`; text uses `spec.name`, `spec.description`.
- `tool.py` docstring: remove the `RuntimeError` "Raises" entry.

## Tests
- `test_tool_args.py`: `Tool.from_function(fn)` → `tool_spec(fn, group="t", read_only=True)` (the helper building tools). Assertions unchanged.
- `test_tool_dispatch.py`: same conversion; constrained arg (`count=0`, `ge=1`) → `EXIT_REJECTED`; other exit codes unchanged.
- New: `invoke_tool` on an update-style fn with an `_UNSET` default omitted → body receives `_UNSET`, no warnings (`pytest.warns` not raised / `warnings.simplefilter("error")`).
- New: `render_tool_detail` on a spec with an `_UNSET` default emits no `PydanticJsonSchemaWarning`.
- `tests/cli/test_tool.py`: existing end-to-end tests pass; add one where a pinned-to-unknown-connection config gives exit 1 with the config hint.
- grep: no `_tool_manager` left in `src/`.

## DATA
`invoke_tool` → `(exit_code, text)` as before.
