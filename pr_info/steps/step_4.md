# Step 4 — Implement `UpdateTools` (Registration + SQL + Body)

## Goal

Replace the stub `UpdateTools` in `update_tools.py` with a fully working
implementation parallel to `QueryTools` / `SchemaTools`:
- Validates the tool name and all SQL identifiers up front (intentional
  whitelist).
- Raises on `key=None` at registration.
- Builds a flat parameter signature: required key + per-field params
  (optional with `_UNSET` default unless `field.required=True`).
- Generates parameterised `UPDATE [schema.]table SET ... WHERE key=:key`
  SQL on each call.
- Filters `_UNSET` values, distinguishing "absent" from explicit `None`.
- Rejects zero-field calls before any DB call.
- Reports affected rows via `format_update_result`.
- Registers as `update_<name>` on the MCP server.

## WHERE

- `src/mcp_tools_sql/update_tools.py` — full implementation
- `tests/test_update_tools.py` — new test file with full coverage

## WHAT

```python
class UpdateTools:
    _NAME_RE: ClassVar[re.Pattern[str]] = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")

    def __init__(
        self,
        backend: DatabaseBackend,
        updates: dict[str, UpdateConfig],
        backend_name: str,
    ) -> None: ...

    def register(self, mcp: FastMCP) -> None: ...
```

`UpdateTools.register` builds sig_params + body for each entry and calls
the shared `build_tool_fn(name, sig_params, body, doc)` from Step 1.

## HOW

- Imports: `re`, `inspect`, `Annotated`, `Optional`, `Any`, `ClassVar`,
  `Awaitable`, `Callable`; `Field` from `pydantic`; `build_tool_fn` and
  `_UNSET` from `mcp_tools_sql.tool_builder`; `format_update_result` from
  `mcp_tools_sql.formatting`; `log_tool_call` from
  `mcp_tools_sql.tool_logging`; `resolve_python_type` from
  `mcp_tools_sql.utils.data_type_utility.type_mapping`;
  `DatabaseBackend`, `UpdateConfig` under `TYPE_CHECKING`.
- Identifier-validation error wording (used at registration **and** matched
  in tests): `"Invalid identifier {value!r} for update {name!r}: must match
  ^[a-zA-Z_][a-zA-Z0-9_]*$ (SQL identifiers in mcp-tools-sql are
  intentionally restricted to a strict whitelist)"`.

## ALGORITHM — `UpdateTools.register`

```
for name, cfg in self._updates.items():
    if not _NAME_RE.match(name): raise ValueError(...)
    if cfg.key is None: raise ValueError(f"update {name!r} requires a key field")
    _validate_identifier(cfg.table, name)
    if cfg.schema_name: _validate_identifier(cfg.schema_name, name)
    _validate_identifier(cfg.key.field, name)
    for f in cfg.fields: _validate_identifier(f.field, name)

    qualified = f"{cfg.schema_name}.{cfg.table}" if cfg.schema_name else cfg.table
    sig_params = _build_sig(cfg)            # key (required) + per-field (Optional[_UNSET])
    body = _build_body(name, cfg, qualified, self._backend)
    fn = build_tool_fn(name, sig_params, body, cfg.description)
    mcp.add_tool(fn, name=f"update_{name}", description=cfg.description)
```

## ALGORITHM — sig_params builder

```
sig = []
# Key — always required
sig.append(Parameter(cfg.key.field, POSITIONAL_OR_KEYWORD,
                     annotation=Annotated[resolve(cfg.key.type),
                                          Field(description=cfg.key.description)]))
# Fields — required if cfg.required, else Optional[T] with default=_UNSET
for f in cfg.fields:
    T = resolve(f.type)
    if f.required:
        sig.append(Parameter(f.field, POSITIONAL_OR_KEYWORD,
                             annotation=Annotated[T, Field(description=f.description)]))
    else:
        sig.append(Parameter(f.field, POSITIONAL_OR_KEYWORD, default=_UNSET,
                             annotation=Annotated[Optional[T],
                                                  Field(description=f.description)]))
return sig
```

## ALGORITHM — body builder

```
async def body(**kwargs):
    key_value = kwargs[cfg.key.field]
    # Drop _UNSET; keep explicit None (means SET col=NULL)
    field_values = {f.field: kwargs[f.field] for f in cfg.fields
                    if kwargs.get(f.field, _UNSET) is not _UNSET}
    if not field_values:
        raise ValueError(f"update '{name}': at least one field value required")
    set_clause = ", ".join(f"{col}=:{col}" for col in field_values)
    sql = f"UPDATE {qualified} SET {set_clause} WHERE {cfg.key.field}=:{cfg.key.field}"
    params = {**field_values, cfg.key.field: key_value}
    async with log_tool_call(name, params, sql=sql) as rec:
        affected = backend.execute_update(sql, params)
        rec.record(rows=affected, cols=len(field_values))
        return format_update_result(affected, qualified, cfg.key.field, key_value)
```

**Fallback note**: if Pydantic/FastMCP rejects `_UNSET` as a signature
default during testing, replace each optional sig param's `default=_UNSET`
with `default=None` and change the `field_values` comprehension to detect
absence via `if f.field in kwargs` (membership) instead of identity. This
is the documented fallback path from issue Decision #10.

## DATA

- `register` returns `None`.
- Tool callable returns `str` (formatted by `format_update_result` or, in
  the zero-fields error case, raises `ValueError` which surfaces to the
  caller as an MCP tool error).
- SQL: parameterised values only — identifiers (table/schema/columns) are
  interpolated from the validated config; no user-controlled string ever
  reaches the SQL identifier slots.

## Tests

TDD: add tests first in `tests/test_update_tools.py`. Mirror
`test_query_tools.py` for fixture style (`_sqlite_backend(sqlite_db)`,
`@pytest.mark.asyncio`, `create_connected_server_and_client_session`).

### Empty / name / prefix
- `test_empty_updates_is_noop`: `UpdateTools(backend, {}, "sqlite").register(mcp)`
  registers zero tools, no error.
- `test_update_tool_name_is_prefixed`: `[updates.set_name]` registers as
  `update_set_name` (and `set_name` is not present).
- `test_invalid_tool_name_raises`: name like `"bad-name"` raises
  `ValueError` mentioning the offending name.

### Identifier whitelist
- `test_invalid_table_identifier_raises`: `table="orders; DROP"` raises with
  an error message containing both `"intentionally restricted"` and the
  regex pattern.
- `test_invalid_schema_identifier_raises`: `schema_name="dbo prod"` raises
  similarly; empty schema_name does NOT trigger the check.
- `test_invalid_key_field_identifier_raises`: `key.field="id; DROP"` raises.
- `test_invalid_field_identifier_raises`: a `fields[].field="bad-col"` entry
  raises.

### key=None
- `test_key_none_raises_at_registration`: `UpdateConfig(table="x", fields=[...])`
  with `key=None` raises `ValueError` matching `"requires a key field"`.

### Signature / JSON schema
- `test_json_schema_key_required_fields_optional`: list_tools schema shows
  key field in `required`; default-`required=False` fields are present in
  `properties` but absent from `required`.
- `test_json_schema_required_field_in_required_list`:
  `UpdateFieldConfig(field="status", required=True)` → `"status"` appears
  in the schema's `required` list.

### Round-trip with SQLite (uses `sqlite_db` fixture)
- `test_register_and_call_updates_row`: build an update on `customers` with
  key=`id`, field=`name`; call via MCP with `{"id": 1, "name": "Updated"}`;
  verify a follow-up SELECT shows the new name. Result text mentions
  `"1 row"`.

### Partial / sentinel semantics
- `test_partial_update_only_provided_fields_in_sql`: update with two
  fields `(name, country)`; caller passes only `name`; spy on
  `backend.execute_update` to assert the generated SQL contains
  `"SET name=:name"` and does NOT contain `"country"`.
- `test_explicit_none_emits_null`: caller passes `country=None`; spy
  asserts SQL contains `"country=:country"` and params dict contains
  `{"country": None}` (NOT `_UNSET`).

### Zero-field rejection
- `test_zero_fields_passed_rejected_no_db_call`: spy on
  `backend.execute_update` to record any call; call the tool with only
  the key set, no field values; expect `result.isError` is True (the
  body's `ValueError` surfaces) and the spy was never invoked.

### Key not found (0 rows)
- `test_key_not_found_returns_no_row_text`: call with a key that doesn't
  exist; assert `result.isError` is False, text contains `"No row found"`.

### >1 affected rows (warning)
- `test_multiple_rows_returns_warning_token`: build a config where
  key column is non-unique in the test data; call the tool; assert
  the response text begins with `WARNING:` on its own line.

### SQL injection prevention via values
- `test_sql_injection_blocked_via_values`: pass a payload like
  `"x'; DROP TABLE customers; --"` as a field value; spy asserts the
  payload appears in the params dict and NOT inlined in the SQL string;
  the `customers` table still exists afterwards (run a SELECT count).

### Required field omitted → MCP protocol error
- `test_required_field_omitted_errors`: declare `UpdateFieldConfig(field="x",
  required=True)`; call without `x`; assert `result.isError` is True.

### Empty schema vs non-empty schema in generated SQL
- `test_schema_empty_generates_bare_table`: empty `schema_name` → SQL is
  `UPDATE customers SET ...` (no dot).
- `test_schema_nonempty_generates_qualified_table`: `schema_name="main"` on
  SQLite → SQL is `UPDATE main.customers SET ...`.

### Name-collision sanity
- `test_query_and_update_same_base_name_coexist`: register a query named
  `foo` and an update named `foo`; both appear in `list_tools` as
  `query_foo` and `update_foo`.

## LLM Prompt

> Read `pr_info/steps/summary.md` (full file) and `pr_info/steps/step_4.md`.
> Implement Step 4 only: replace the stub `UpdateTools` in
> `src/mcp_tools_sql/update_tools.py` with the full implementation
> described in this step. Build sig_params + body inline in `register`
> (keep small `_build_sig` / `_build_body` private helpers if it helps
> readability, but no public API beyond the class). Use the shared
> `build_tool_fn` and `_UNSET` from `mcp_tools_sql.tool_builder` (from
> Step 1) and `format_update_result` from `mcp_tools_sql.formatting`
> (from Step 3). Identifier-validation error messages must explicitly
> mention "intentionally restricted to a strict whitelist". Follow TDD:
> add the full `tests/test_update_tools.py` suite described in this step
> **before** changing the implementation. If `_UNSET` as a signature
> default is rejected by FastMCP/Pydantic during testing, use the
> documented fallback (`default=None` + `if field in kwargs` membership
> check) — adjust the few affected tests accordingly. Run
> `mcp__tools-py__run_pylint_check`, `mcp__tools-py__run_pytest_check`
> (with the fast unit-test marker exclusion), and
> `mcp__tools-py__run_mypy_check`. Make exactly one commit when green.
