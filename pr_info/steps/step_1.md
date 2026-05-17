# Step 1 — Construction builders

**Prompt for LLM:**
> Read `pr_info/steps/summary.md` and then implement `pr_info/steps/step_1.md`.
> TDD: write the tests first, run them red, then implement the builders, run
> them green. Finish by running pylint, mypy, ruff, tach, and import-linter —
> all must be clean. One commit.

---

## WHERE

- **New file (impl):** `src/mcp_tools_sql/config/authoring.py`
- **New file (tests):** `tests/config/test_authoring.py`
- **No other file is touched in this step.**

## WHAT

Two public top-level functions in `authoring.py`:

```python
def build_query_config(
    name: str,
    *,
    description: str = "",
    sql: str,
    params: dict[str, dict[str, Any]] | None = None,
    max_rows_default: int = 100,
    max_rows_hard: int | None = None,
    filter_column: str = "",
) -> QueryConfig: ...

def build_update_config(
    name: str,
    *,
    description: str = "",
    schema: str = "",
    table: str,
    key: dict[str, Any],
    fields: list[dict[str, Any]],
) -> UpdateConfig: ...
```

Notes on signatures:
- `name` is accepted positionally for callsite readability but the builders do
  not store it on the model (`QueryConfig` / `UpdateConfig` have no `name`
  field — the name is the TOML section key, handled by storage helpers in
  Step 2).
- `schema=` (not `schema_name=`) matches the TOML key.
- `backends` is deliberately NOT exposed — advanced users go through
  `QueryConfig(...)` directly (per issue Decision #7).

## HOW

- Imports: `from typing import Any` and the pydantic models from
  `mcp_tools_sql.config.models` (`QueryConfig`, `QueryParamConfig`,
  `UpdateConfig`, `UpdateFieldConfig`, `UpdateKeyConfig`).
- Validation errors propagate as `pydantic.ValidationError` (caller's problem).
- `build_update_config` uses `UpdateConfig.model_validate({"schema": schema, ...})`
  so the alias path is exercised (model already has `populate_by_name=True`).

## ALGORITHM

`build_query_config`:
```
params_in = params or {}
typed_params = {
    key: QueryParamConfig(**{**inner, "name": key})  # dict key wins over inner "name"
    for key, inner in params_in.items()
}
return QueryConfig(
    description=description, sql=sql, params=typed_params,
    max_rows_default=max_rows_default, max_rows_hard=max_rows_hard,
    filter_column=filter_column,
)
```

`build_update_config`:
```
typed_key = UpdateKeyConfig(**key)
typed_fields = [UpdateFieldConfig(**f) for f in fields]
return UpdateConfig.model_validate({
    "description": description, "schema": schema, "table": table,
    "key": typed_key, "fields": typed_fields,
})
```

## DATA

Returns: fully validated `QueryConfig` / `UpdateConfig` pydantic instances.
The `_default_max_rows_hard` model validator on `QueryConfig` runs as usual,
so after construction `max_rows_hard` is never `None`.

## Tests (parametrize where noted)

In `tests/config/test_authoring.py`:

1. **`build_query_config` auto-fills param name from dict key.**
   Input: `params={"id": {"type": "int"}}`. Assert `cfg.params["id"].name == "id"`.
2. **`build_query_config` dict-key overrides inner mismatched name (silently).**
   Input: `params={"id": {"name": "other", "type": "int"}}`. Assert
   `cfg.params["id"].name == "id"`.
3. **`build_query_config` propagates pydantic `ValidationError`.**
   Omit the required `sql=` kwarg → expect `pydantic.ValidationError`.
4. **`build_update_config` happy path; `schema=` kwarg lands on `schema_name`.**
   Assert `ucfg.schema_name == "dbo"`, `ucfg.table == "users"`,
   `ucfg.key.field == "id"`, `[f.field for f in ucfg.fields] == ["email"]`.
5. **`build_update_config` propagates pydantic `ValidationError`.**
   Use a `key=` dict missing the required `field` key to trigger the model
   error.

Run gates after writing tests + impl:
- `pytest tests/config/test_authoring.py -x`
- `pylint`, `mypy`, `ruff`, `tach check`, `lint-imports`.
