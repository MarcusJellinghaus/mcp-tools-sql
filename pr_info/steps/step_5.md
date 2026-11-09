# Step 5 — `mcp_tools_sql.toolset` module

## LLM prompt
Read `pr_info/steps/summary.md`, then implement `pr_info/steps/step_5.md`.
TDD: write `tests/test_toolset.py` and the `sys.modules` check first, then `toolset.py`.
Run pylint, mypy, pytest (`-n auto`). One commit.

## WHERE
- Create `src/mcp_tools_sql/toolset.py`
- Create `tests/test_toolset.py`
- Modify `tests/test_module_imports.py` (subprocess `sys.modules` check)
- `server.py` is NOT changed in this step (it still registers its own `verify`/`read_databases`; step 6 switches over).

## WHAT
```python
GROUP/descriptions: _READ_DATABASES_DESC, _VERIFY_DESC, _VERIFY_NOTE (copied from server.py)
_VERIFY_NOTE = ("Note: verify re-read the config files from disk; the running tools "
                "keep the config they were built with.")

@dataclass(frozen=True)
class SqlToolset:
    specs: tuple[ToolSpec, ...]
    targets: ResolvedTargets
    query_config: QueryFileConfig
    registry: BackendRegistry
    def close(self) -> None: self.registry.close_all()
    def __enter__(self) -> SqlToolset: return self
    def __exit__(self, *exc: object) -> None: self.close()

def _build_verify_tool(query_config_path: Path | None,
                       database_config_path: Path | None) -> Callable[[], Awaitable[str]]

def assemble_toolset(config: QueryFileConfig, targets: ResolvedTargets,
                     registry: BackendRegistry, allow_updates: bool, *,
                     query_config_path: Path | None = None,
                     database_config_path: Path | None = None) -> SqlToolset

def build_toolset(query_config: Path, database_config: Path | None = None) -> SqlToolset
```

## ALGORITHM
```
assemble_toolset:
  sink = ToolCollector()
  try:
    SchemaTools(registry, targets, limits=config.limits).register(sink)
    ValidationTools(...).register(sink); CountTools(...).register(sink); SummarizeTools(...).register(sink)
    if targets.is_multi: sink.add(tool_spec(build_read_databases_tool(targets), group="sql.schema",
                                           read_only=True, name="read_databases", description=_READ_DATABASES_DESC))
    sink.add(tool_spec(_build_verify_tool(qpath, dbpath), group="sql.validation", read_only=True,
                       name="verify", description=_VERIFY_DESC))
    QueryTools(registry, targets, config.queries, limits=config.limits).register(sink)
    if allow_updates: UpdateTools(registry, targets, config.updates).register(sink)
  except BaseException: registry.close_all(); raise
  return SqlToolset(sink.specs, targets, config, registry)

build_toolset:
  qcfg = load_query_config(query_config); dbcfg = load_database_config(database_config)
  targets = resolve_targets(qcfg, dbcfg)
  return assemble_toolset(qcfg, targets, BackendRegistry(), dbcfg.security.allow_updates,
                          query_config_path=query_config, database_config_path=database_config)
```
Tool order matches today's server (builtins, read_databases, verify, queries, updates).
`_build_verify_tool` is the body of `ToolServer._build_verify_tool` with `_VERIFY_NOTE`.

## HOW
- Imports: config loader, `BackendRegistry`, toolkits, `build_read_databases_tool` (stays in `schema_tools`), `verify_all`, `render_short`, `log_tool_call`, `utils.tool_spec`. No `server`, no `mcp`.
- `registry` is a dataclass field (needed by `close()`); `.specs`, `.targets`, `.query_config` are the public API.

## Tests (`tests/test_toolset.py`, SQLite configs written to `tmp_path`)
- Groups and `read_only` per the summary table (single- and multi-target; `allow_updates=true`).
- `max_rows` below minimum rejected: `spec.args_model.model_validate({"max_rows": 0})` raises `ValidationError` for a `query_*` tool (use the field constraint actually defined in `build_query_sig_params`; if `max_rows` has no `ge` constraint, use `count_records` without the required `sql`).
- Each tool type (schema, `validate_sql`, `count_records`, `summarize_columns`, `query_*` with an optional param, `update_*`, `verify`, `read_databases`) called through `args_model` with only its required arguments returns a `str`:
  `validated = spec.args_model.model_validate(required_kwargs)` →
  `await spec.fn(**{f: getattr(validated, f) for f in spec.args_model.model_fields})`.
  Parametrize over the tool types.
- `schema` parameter (`summarize_columns`, schema tools such as `read_columns`): the name shadows `BaseModel.schema`.
  FastMCP aliases such fields; `tool_spec` does not. It keeps the field name `schema` and only suppresses
  pydantic's "shadows an attribute" warning. `model_validate({"schema": ...})` accepts it, and `getattr(validated, "schema")`
  returns the field value, not the classmethod (checked with a scratch probe against `mcp_coder_utils.tool_spec`).
  So no alias or rename is needed. Pin it with a test: route `summarize_columns` and one schema tool through
  `args_model` with `schema="main"` (SQLite) and assert the call succeeds and `"schema"` is in
  `spec.args_model.model_json_schema()["properties"]`.
- Rebuild: build, append a `[queries.bar]` to the config file, build again, close the old toolset → `query_bar` in new specs; old registry's backends closed (patch/count `BackendRegistry.close_all` or assert the old backend's connection is closed).
- Failed build closes its registry: config with a query pinned to an unknown connection → `build_toolset` raises `ValueError`; a counting patch of `BackendRegistry.close_all` was called once.
- Query and update without description → fallback description in specs; `verify` spec call output contains `[WARN]` … `.description`.
- `verify` output contains the neutral note text.
- Context manager closes the registry.

## Test (`tests/test_module_imports.py`)
Subprocess via `execute_subprocess` (never `subprocess`): a script that writes SQLite configs to a temp dir, imports `mcp_tools_sql.toolset`, builds a toolset, awaits one spec's `fn` (e.g. `read_tables`), closes it, then prints `"mcp" in sys.modules or any(m.startswith("mcp.") for m in sys.modules)`. Assert output `False`.

## DATA
`SqlToolset(specs: tuple[ToolSpec, ...], targets: ResolvedTargets, query_config: QueryFileConfig, registry: BackendRegistry)`.
