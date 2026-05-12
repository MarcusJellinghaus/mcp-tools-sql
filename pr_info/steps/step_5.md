# Step 5 — Wire `UpdateTools` into the Server with `allow_updates` Switch

## Goal

Plumb `DatabaseConfig.security.allow_updates` from `run_server` through to
`ToolServer` as a plain `bool`. When `True`, `_register_configured_tools`
registers `UpdateTools`; when `False`, it skips update registration
entirely so no update tools appear in `list_tools`.

## WHERE

- `src/mcp_tools_sql/server.py` — `ToolServer.__init__` gains
  `allow_updates: bool`; `_register_configured_tools` conditionally
  registers `UpdateTools`; `run_server` reads the flag from the loaded
  `DatabaseConfig` and passes it through; `create_server` factory
  forwards it
- `tests/test_server.py` — tests covering the flag

## WHAT

```python
class ToolServer:
    def __init__(
        self,
        config: QueryFileConfig,
        backend: DatabaseBackend,
        backend_name: str,
        allow_updates: bool,
    ) -> None: ...

def create_server(
    config: QueryFileConfig,
    backend: DatabaseBackend,
    backend_name: str,
    allow_updates: bool,
) -> ToolServer: ...
```

## HOW

- **Before editing**: search the repo for all `ToolServer(` and
  `create_server(` call sites (src + tests + docs) using
  `mcp__mcp-workspace__search_files`. Update each call site to pass the
  new `allow_updates` argument.
- New import in `server.py`: `from mcp_tools_sql.update_tools import UpdateTools`.
- `run_server` already loads `dbcfg = load_database_config(...)`; it reads
  `dbcfg.security.allow_updates` once and passes it to `ToolServer`.
- `_register_configured_tools` today registers `QueryTools` only; add a
  conditional `UpdateTools` registration after the existing `QueryTools`
  line, guarded by `self._allow_updates`:

```python
def _register_configured_tools(self) -> None:
    QueryTools(self._backend, self._config.queries, self._backend_name).register(self._mcp)
    if self._allow_updates:
        UpdateTools(self._backend, self._config.updates, self._backend_name).register(self._mcp)
```

`_register_builtin_tools` (which registers `SchemaTools` and other
built-ins) is unchanged.

- All existing `ToolServer(...)` call sites in tests must be updated to
  pass the new positional arg (`allow_updates=True` by default in tests
  except where the flag itself is being tested).

## ALGORITHM

```
# run_server
dbcfg = load_database_config(args.database_config)
...
ToolServer(qcfg, backend, conn.backend, dbcfg.security.allow_updates).run()
```

`run_server` continues to call `ToolServer(...)` directly (unchanged
dispatch). `create_server` is updated for external callers and tests
that prefer the factory; it is not used by `run_server` itself.

## DATA

- `ToolServer._allow_updates: bool` — stored attribute.
- No new return values.

## Tests

TDD: add tests first.

- `tests/test_server.py`:
  - Update existing tests (`test_configured_query_registered_as_tool`,
    smoke / log / keyboard tests) to construct `ToolServer(..., allow_updates=True)`.
  - **New** `test_update_tool_registered_when_allow_updates_true`:
    write a query config with `[updates.set_name]` (table=customers,
    key=id, fields=[name]); `ToolServer(qcfg, backend, "sqlite",
    allow_updates=True)._register_configured_tools()`; via
    `create_connected_server_and_client_session`, list tools and assert
    `"update_set_name"` is present.
  - **New** `test_update_tool_not_registered_when_allow_updates_false`:
    Build the server twice — once with `allow_updates=True`, once with
    `allow_updates=False`. Assert: (a) no tool name starting with
    `update_` appears in the `allow_updates=False` registry; (b) the
    set of non-`update_*` tools is identical in both cases (i.e. only
    `update_*` tools differ). This makes the test resilient to
    additions of new built-in tools.
  - **New** `test_run_server_reads_allow_updates_from_database_config`:
    Patch `ToolServer.__init__` to a wrapper that records the received
    `allow_updates` value and then delegates to the original `__init__`.
    Run `run_server(...)` with a config that has `allow_updates: false`;
    assert the recorded value is `False`.

## LLM Prompt

> Read `pr_info/steps/summary.md` (full file) and `pr_info/steps/step_5.md`.
> Implement Step 5 only: add `allow_updates: bool` to
> `ToolServer.__init__` and `create_server` in
> `src/mcp_tools_sql/server.py`; have `_register_configured_tools`
> register `UpdateTools` (from Step 4) only when the flag is `True`; have
> `run_server` read `dbcfg.security.allow_updates` and pass it through.
> Update all `ToolServer(...)` call sites in tests to pass the new arg.
> Follow TDD: add the three new tests in `tests/test_server.py` described
> in this step before changing implementation. Run
> `mcp__tools-py__run_pylint_check`, `mcp__tools-py__run_pytest_check`
> (with the fast unit-test marker exclusion), and
> `mcp__tools-py__run_mypy_check`. Make exactly one commit when green.
