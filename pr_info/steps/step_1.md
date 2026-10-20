# Step 1: Split tool registration from the stdio transport in `server.py`

Read `pr_info/steps/summary.md` first for the full design. This step only
touches `src/mcp_tools_sql/server.py` and its tests — no CLI changes yet.

**Precondition:** `src/mcp_tools_sql/server.py` matches the shape described
in `summary.md` (a `ToolServer` class with `_register_builtin_tools`,
`_register_configured_tools`, `run`, and a module-level `run_server`). If it
does not, write one line to `pr_info/.blocked.txt` and stop.

## WHERE

- `src/mcp_tools_sql/server.py` (modified)
- `tests/test_server.py` (modified — new tests only, no existing test
  changes)

## WHAT

New/changed members of `ToolServer`:

```python
@property
def config(self) -> QueryFileConfig: ...   # returns self._config

@property
def targets(self) -> ResolvedTargets: ...  # returns self._targets

def register_all(self) -> None: ...        # _register_builtin_tools() + _register_configured_tools()

def run(self) -> None: ...                 # register_all() then self._mcp.run(transport="stdio")

def close(self) -> None: ...               # self._registry.close_all()
```

New module-level function:

```python
def build_tool_server(args: argparse.Namespace) -> tuple[ToolServer, Path]: ...
```

`run_server` is updated to call it (see ALGORITHM).

## HOW

- `config`/`targets` are plain read-only properties alongside the existing
  `mcp` property; no change to `__init__`.
- `build_tool_server` is the exact sequence currently inlined in
  `run_server`, up to and including `ToolServer(qcfg, targets, registry,
  dbcfg.security.allow_updates)` — moved verbatim, not rewritten. It returns
  `(server, qpath)`; `qpath` is still needed by `run_server`'s existing log
  line.
- `run_server` keeps its existing log statement, reading the four values it
  currently reads from local variables (`targets.default.backend_name`,
  `qcfg.connection`, `len(targets.connection_names)`,
  `len(targets.database_names)`) from `server.targets` / `server.config`
  instead, plus the returned `qpath`. The sixth value, `builtin_tools=%d`
  (`n_builtin = len(load_default_queries()) + len(PROGRAMMATIC_BUILTIN_TOOLS)`),
  is computed exactly as it is today — this call is independent of
  `server.config`/`server.targets`/`qpath` and cannot be derived from them,
  and it cannot be read off `server.mcp` either: `build_tool_server` returns
  an *unregistered* server (see test 2 below), so no tools exist on it yet
  at the point the log line fires. `run_server` keeps calling
  `load_default_queries()` and referencing `PROGRAMMATIC_BUILTIN_TOOLS`
  directly for this one value, same imports as today.
- `run_server`'s `finally` block changes from `registry.close_all()` to
  `server.close()`. Behaviourally identical — `close()` just delegates.
- `create_server`, `ToolServer.__init__`, `_register_builtin_tools`, and
  `_register_configured_tools` are untouched. Existing tests that call the
  two private `_register_*` methods directly keep working unchanged.

## ALGORITHM

```
build_tool_server(args):
    qpath = discover_query_config(args.config, project_dir=cwd())
    qcfg = load_query_config(qpath)
    dbcfg = load_database_config(args.database_config)
    targets = resolve_targets(qcfg, dbcfg)
    registry = BackendRegistry()
    server = ToolServer(qcfg, targets, registry, dbcfg.security.allow_updates)
    return server, qpath

run_server(args):
    server, qpath = build_tool_server(args)   # raises ValueError/OSError same as today
    try:
        n_builtin = len(load_default_queries()) + len(PROGRAMMATIC_BUILTIN_TOOLS)
        log the same INFO line as today (backend/connection/connections/databases
            from server.targets/server.config, query_config=qpath, builtin_tools=n_builtin)
        server.run()                           # register_all() + mcp.run(stdio)
    finally:
        server.close()
```

## DATA

No new data structures. `build_tool_server` returns a plain
`tuple[ToolServer, Path]`.

## Tests (write first)

Add to `tests/test_server.py`:

1. `test_register_all_registers_builtin_and_configured_tools` — construct a
   `ToolServer` directly (as existing tests do), call `register_all()`
   once, assert via `create_connected_server_and_client_session` that both a
   builtin (`read_tables`) and a configured `query_*` tool appear — replaces
   needing two separate protected-method calls.
2. `test_build_tool_server_returns_unregistered_server` — call
   `build_tool_server(args)` against the existing `_write_sqlite_configs`
   fixture, assert the returned server's `mcp._tool_manager.list_tools()`
   is empty before `register_all()` is called, and non-empty after.
3. `test_close_delegates_to_registry_close_all` — monkeypatch
   `BackendRegistry.close_all`, call `server.close()`, assert it was called
   exactly once.
4. `test_config_and_targets_properties_expose_constructor_values` — assert
   `server.config is <the QueryFileConfig passed in>` and same for
   `targets`.

Confirm every existing test in `tests/test_server.py` still passes unchanged
(they exercise `run_server`'s externally observable behaviour: log line
content, `ToolServer.run()` being called, `registry.close_all()` being
invoked — all preserved by this refactor).

## Commit

One commit: the four new tests above, the `server.py` changes, and
`run_format_code` + `run_pylint_check` + `run_pytest_check` + `run_mypy_check`
+ `run_ruff_check` + `run_lint_imports_check` + `run_tach_check` all passing.

## LLM prompt

> Read `pr_info/steps/summary.md` and `pr_info/steps/step_1.md`. Implement
> step 1 exactly as specified: add `ToolServer.register_all()`, `config`/
> `targets` properties, and `close()`, plus the module-level
> `build_tool_server(args)` factory, and update `run_server` to use them
> with no behaviour change. Write the four new tests in `tests/test_server.py`
> first, then the implementation. Do not touch anything under
> `src/mcp_tools_sql/cli/` in this step. Run the project's standard checks
> (pylint, pytest, mypy, ruff, lint-imports, tach) before committing.
