# Step 3a — Wire `validate_sql` into ToolServer

Wire `ValidationTools` into `ToolServer._register_builtin_tools`, add the `_PROGRAMMATIC_BUILTIN_TOOLS` tuple, bump the startup `builtin_tools=<N>` counter, and teach `load_default_queries()` to skip TOML entries whose names collide with a programmatic builtin. Add a unit test that asserts `validate_sql` is registered. MSSQL integration tests are split off into Step 3b.

## WHERE

- `src/mcp_tools_sql/server.py` — register `ValidationTools`, add programmatic-builtin tuple, bump counter.
- `src/mcp_tools_sql/schema_tools.py` — skip-with-warning for colliding names in `load_default_queries()`.
- `tests/test_server.py` — assert `validate_sql` is among the registered tools; assert `builtin_tools=<N>` log.
- `tests/test_default_queries.py` — assert TOML collision is skipped with a warning.

## WHAT

### `server.py` changes

```python
from mcp_tools_sql.validation_tools import ValidationTools

_PROGRAMMATIC_BUILTIN_TOOLS: tuple[str, ...] = ("validate_sql",)
```

Defined at module scope. Future programmatic builtins are added by extending the tuple — no separate counter constant to update.

In `ToolServer._register_builtin_tools`:
```python
def _register_builtin_tools(self) -> None:
    """Register schema-exploration tools from default_queries.toml and built-in validation tools."""
    SchemaTools(self._backend, self._backend_name).register(self._mcp)
    ValidationTools(self._backend, self._backend_name).register(self._mcp)
```

In `run_server`:
```python
n_builtin = len(load_default_queries()) + len(_PROGRAMMATIC_BUILTIN_TOOLS)
```

### `load_default_queries()` change

When iterating TOML query entries, skip any entry whose name appears in `_PROGRAMMATIC_BUILTIN_TOOLS`. Emit a warning log line identifying the colliding name and that the programmatic builtin wins.

```python
# Pseudo:
for name, spec in toml_queries.items():
    if name in _PROGRAMMATIC_BUILTIN_TOOLS:
        log.warning(
            "Skipping TOML query %r — name reserved by programmatic builtin", name
        )
        continue
    ...
```

The import of `_PROGRAMMATIC_BUILTIN_TOOLS` from `server.py` is acceptable (one-way dependency: `schema_tools` is already imported by `server`). If a cycle materialises, lift the tuple into a small shared module — but the simplest first cut is to define it once in `server.py` and import it where needed.

### `tests/test_server.py` additions

Tests the production path via `_register_builtin_tools()` in `server.py` (after Step 2's manual-register tests verified the tool itself).

- [ ] `validate_sql` is among the names listed by `mcp.list_tools()` after `_register_builtin_tools()` runs.
- [ ] Verify the `builtin_tools=<N>` log line is emitted. Preferred: `caplog` against the existing `run_server` test surface. If `run_server`'s logging isn't capturable without significant async/mock setup, fall back to: (a) assert the value via the `_PROGRAMMATIC_BUILTIN_TOOLS` constant directly (e.g. `len(load_default_queries()) + len(_PROGRAMMATIC_BUILTIN_TOOLS) == expected`), or (b) patch `log.info` and assert the call args. Pick whichever requires the least mocking.

### `tests/test_default_queries.py` additions

- [ ] Mock a TOML file containing `[queries.validate_sql]` (with arbitrary `sql` body). Call `load_default_queries()`. Assert:
  - The returned mapping does NOT contain `validate_sql`.
  - A warning is logged that mentions the reserved name.

## HOW

- Constructor for `ValidationTools` takes `(backend, backend_name)` — matches `QueryTools` / `UpdateTools` / `SchemaTools`.
- Update the existing `_register_builtin_tools` docstring to reflect that it now registers schema-exploration tools **and** built-in validation tools.
- The `n_builtin` log counter sums TOML-driven schema tools plus `len(_PROGRAMMATIC_BUILTIN_TOOLS)`; if a future step adds another programmatic built-in, extend the tuple in one place and the counter follows.
- The TOML collision skip is defence-in-depth: prevents a user-supplied `default_queries.toml` from accidentally (or maliciously) overriding `validate_sql`.

## ALGORITHM

```
server.py module scope:
    _PROGRAMMATIC_BUILTIN_TOOLS = ("validate_sql",)

ToolServer._register_builtin_tools:
    SchemaTools(...).register(mcp)
    ValidationTools(...).register(mcp)

load_default_queries:
    for name, spec in toml:
        if name in _PROGRAMMATIC_BUILTIN_TOOLS:
            log.warning(...); continue
        emit (name, spec)

run_server:
    n_builtin = len(load_default_queries()) + len(_PROGRAMMATIC_BUILTIN_TOOLS)
```

## DATA

- No return-value changes. `_PROGRAMMATIC_BUILTIN_TOOLS: tuple[str, ...]` constant added to `server.py`.

## Tests checklist for this step

### `tests/test_server.py`
- [ ] `validate_sql` is among the names listed by `mcp.list_tools()` after `_register_builtin_tools()` runs.
- [ ] `builtin_tools=<N>` counter reflects `len(load_default_queries()) + len(_PROGRAMMATIC_BUILTIN_TOOLS)` — preferred via `caplog`, fall back to constant-based assertion or `log.info` patch (whichever is least invasive).

### `tests/test_default_queries.py`
- [ ] TOML containing `[queries.validate_sql]` is skipped with a warning; the resulting mapping does not register `validate_sql` as a TOML-driven tool.

## Commit & checks

Commit message: `feat(server): register validate_sql as a programmatic builtin tool`.

Run before commit:
- `mcp__mcp-tools-py__run_format_code`
- `mcp__mcp-tools-py__run_pytest_check` with `extra_args=["-n", "auto"]`
- `mcp__mcp-tools-py__run_pylint_check`
- `mcp__mcp-tools-py__run_mypy_check`

All must pass.

## LLM prompt for this step

> Implement Step 3a of issue #8 per `pr_info/steps/summary.md` and `pr_info/steps/step_3a.md`. In `src/mcp_tools_sql/server.py`: import `ValidationTools`, add `_PROGRAMMATIC_BUILTIN_TOOLS: tuple[str, ...] = ("validate_sql",)` at module scope, register `ValidationTools(self._backend, self._backend_name).register(self._mcp)` after `SchemaTools` in `_register_builtin_tools`, and update `n_builtin` in `run_server` to `len(load_default_queries()) + len(_PROGRAMMATIC_BUILTIN_TOOLS)`. Update the `_register_builtin_tools` docstring. In `load_default_queries()`, skip with a warning any TOML entry whose name is in `_PROGRAMMATIC_BUILTIN_TOOLS`. Add a `validate_sql`-registration test in `tests/test_server.py` (assert it appears in `mcp.list_tools()`; verify the counter log via `caplog` or fall back per the step file). Add a collision-skip test for `load_default_queries()`. Run format / pytest / pylint / mypy and commit as one commit.
