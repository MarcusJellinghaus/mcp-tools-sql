# Issue #6 — Dynamic UPDATE Tool Registration

**Milestone**: M3
**Depends on**: #5 (introduces `tool_builder.py` and the class-based registration pattern this issue mirrors)

## Goal

Each configured `[updates.<name>]` entry in `mcp-tools-sql.toml` becomes an MCP
tool named `update_<name>`. UPDATEs are **structured** (table + key + fields),
not raw SQL — the server generates the SQL from `UpdateConfig`.

## Architectural / Design Changes

### 1. `tool_builder.py` becomes a pure assembler

Today `build_tool_fn(name, config, backend, backend_name, *, truncation_hint)`
takes a `QueryConfig` and bakes in query-specific behaviour (`max_rows` clamp,
`<col>_filter` injection, SQL parameter stripping). After this change the
assembler is tool-type-agnostic:

```python
build_tool_fn(name: str,
              sig_params: list[inspect.Parameter],
              body: Callable[..., Awaitable[str]],
              doc: str) -> Callable[..., Any]
```

Both `QueryTools` and `UpdateTools` build their own `sig_params` + body and
hand them to the assembler. Query-specific helpers (`extract_sql_params`,
`apply_filter`, the `max_rows`/`<col>_filter` injection logic) move out of
`tool_builder.py` directly into `query_tools.py` — no sibling helpers
module, no extra import dance.

A new module-level `_UNSET = object()` sentinel is exposed from
`tool_builder.py` for update bodies to detect "field not passed" at runtime.

### 2. `UpdateTools` class — parallel to `QueryTools` / `SchemaTools`

```python
class UpdateTools:
    def __init__(self, backend, updates: dict[str, UpdateConfig], backend_name): ...
    def register(self, mcp: FastMCP) -> None: ...
```

For each update entry, `register()`:
1. Validates the tool name with regex `^[a-zA-Z_][a-zA-Z0-9_]*$`.
2. Validates `table`, `schema_name` (when non-empty), `key.field`, and each
   `fields[].field` against the same regex — error messages explicitly say
   the whitelist is intentional.
3. Raises `ValueError("update '<name>' requires a key field")` when
   `config.key is None`.
4. Builds `sig_params`: key (required) + one param per field
   (`Annotated[Optional[T], Field(description=...)]`, default `_UNSET` unless
   `field.required` is True).
5. Builds a body closure that filters `_UNSET` values, rejects zero-field
   calls, generates parameterised SQL, calls `backend.execute_update`, and
   formats via `format_update_result`.
6. Registers via `mcp.add_tool(fn, name=f"update_{name}", description=...)`.

### 3. SQL generation contract

`UPDATE [schema.]table SET field1=:field1, field2=:field2 WHERE key=:key`

- Empty `schema_name` → bare `UPDATE table`; non-empty → `UPDATE schema.table`.
- Only fields the LLM actually passed (i.e. not `_UNSET`) appear in `SET`.
- Explicit `None` survives as `SET field=NULL` (sentinel distinguishes
  absent from None).
- Zero field values → reject with a clear error before any DB call.
- **No per-backend SQL override** for updates (no `backends` field on
  `UpdateConfig`) — structured generation is the contract.

### 4. Affected-row semantics

Reported via `format_update_result(affected_rows, qualified_table, key_field, key_value)`:
- `0` → plain "no row found" text, `isError=False` (LLM decides next move).
- `1` → success confirmation.
- `>1` → result text begins with a stable `WARNING:` token at line start so
  downstream callers can detect the unique-key violation reliably.

The signature change vs. the current stub
(`format_update_result(affected_rows, table, key_value)`) is intentional —
mirrors `format_rows`' primitive-only shape, lets future INSERT/DELETE tools
reuse it.

### 5. `allow_updates` is a hard switch

`run_server` reads `dbcfg.security.allow_updates` and passes it as a plain
`bool` to `ToolServer.__init__`. When `False`, `_register_configured_tools`
skips `UpdateTools` entirely — no update tools appear in `list_tools`. This
is cleaner than registering then refusing at call time.

### 6. Config model — `required` flag on `UpdateFieldConfig`

`UpdateFieldConfig` gains `required: bool = False`. Default is `False`
because partial updates are the common case (flip of `QueryParamConfig`'s
`required: bool = True` default).

`UpdateConfig.key` stays `Optional[UpdateKeyConfig]` in the Pydantic model;
the strict check moves to `UpdateTools.register` so `verify_updates` can
still report multiple config problems in one run.

### 7. `verify_updates` extension

The three existing rows per update (`<name>.table`, `<name>.key_column`,
`<name>.fields`) are extended in place — no new row types:
- `.table` row also runs the regex against `table` and `schema_name`.
- `.key_column` row also runs the regex against `key.field`.
- `.fields` row also runs the regex against each field; its `value` text
  surfaces the `required` flag inline (e.g. `name(req), country, email(req)`).

Identifier failures use the same "whitelist is intentional" wording as
registration so users see the same explanation in both places.

## Files Created / Modified

### Modified
- `src/mcp_tools_sql/tool_builder.py` — refactored to pure assembler;
  query helpers removed; `_UNSET` sentinel added
- `src/mcp_tools_sql/query_tools.py` — query helpers move in;
  `QueryTools.register` builds its own sig_params + body
- `src/mcp_tools_sql/schema_tools.py` — `SchemaTools.register` builds its
  own sig_params + body (uses the moved helpers from `query_tools.py`)
- `src/mcp_tools_sql/update_tools.py` — stub replaced with `UpdateTools` class
- `src/mcp_tools_sql/config/models.py` — `required: bool = False` added to
  `UpdateFieldConfig`
- `src/mcp_tools_sql/formatting.py` — `format_update_result` implemented
  with new signature
- `src/mcp_tools_sql/server.py` — `ToolServer.__init__` accepts
  `allow_updates: bool`; `_register_configured_tools` registers
  `UpdateTools` when allowed; `run_server` passes the flag through
- `src/mcp_tools_sql/cli/commands/verify.py` — `verify_updates` extended
  with identifier regex check and `required`-flag visibility; import of
  `extract_sql_params` updated to its new location
- `tests/test_tool_builder.py` — updated for the new assembler shape
- `tests/test_query_tools.py` — minor adjustments where helpers moved
- `tests/test_schema_tools.py` — minor adjustments where helpers moved
- `tests/test_formatting.py` — tests for `format_update_result`
- `tests/test_server.py` — tests for `allow_updates` flag
- `tests/cli/test_verify.py` — tests for extended `verify_updates`
- `vulture_whitelist.py` — confirm `_.required` covers the new attribute
  (no change expected)

### Created
- `pr_info/steps/summary.md` — this file
- `pr_info/steps/step_1.md` … `step_6.md` — per-step implementation prompts
- `src/mcp_tools_sql/identifiers.py` — new module exposing both
  `IDENTIFIER_PATTERN: re.Pattern[str]` (the whitelist regex) and
  `identifier_error(value, update_name) -> str` (the error-message
  helper) — single source for both the pattern and the error wording,
  imported by `update_tools.py` and `verify.py` alike
- `tests/test_update_tools.py` — full coverage for `UpdateTools`
- `tests/test_identifiers.py` — unit test for the new `identifier_error`
  helper

### Unchanged (referenced only)
- `src/mcp_tools_sql/backends/base.py` — `execute_update` already returns
  affected row count
- `src/mcp_tools_sql/backends/sqlite.py` — implicit commit-on-success
  sufficient for #6 (explicit transactions deferred to #7)
- `src/mcp_tools_sql/tool_logging.py` — `log_tool_call` reused as-is
- `src/mcp_tools_sql/utils/data_type_utility/type_mapping.py` — reused as-is

## Step Sequence

| # | Title | Net effect |
|---|-------|-----------|
| 1 | Refactor `tool_builder.py` into a pure assembler | No behaviour change; existing tests pass |
| 2 | Add `required: bool = False` to `UpdateFieldConfig` | Config model gains a flag |
| 3 | Implement `format_update_result` | Formatter ready for use |
| 4 | Implement `UpdateTools` (registration + SQL + body) | Update tools dynamically registered |
| 5 | Wire `allow_updates` through `ToolServer` | Hard switch respected |
| 6 | Extend `verify_updates` | Identifier regex + `required` visibility |

Each step is exactly one commit: tests + implementation + all quality checks
(`pylint`, `pytest`, `mypy`) passing.

## Out of Scope (deferred)

- Explicit BEGIN/COMMIT/ROLLBACK transaction wrapping (defer to #7 with MSSQL).
- Multi-backend testing — #6 only exercises SQLite.
- INSERT/DELETE structured tools — separate future issues.
