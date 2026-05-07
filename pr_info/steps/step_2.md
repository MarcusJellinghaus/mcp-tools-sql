# Step 2 — Rename `max_rows` → `max_rows_default`; add `max_rows_hard` clamp

## LLM Prompt

> Read `pr_info/steps/summary.md`, then implement Step 2 from
> `pr_info/steps/step_2.md`: rename `QueryConfig.max_rows`, add `max_rows_hard`
> with a Pydantic validator that defaults it to `max_rows_default`, and add the
> clamp + result-note logic inside `schema_tools._build_tool_fn`. Hard rename,
> no Pydantic alias. Update `default_queries.toml`, `schema_tools.py`,
> `cli/commands/verify.py`, and all touched tests in the same commit. Use TDD.
> Use MCP tools only. Run pylint, mypy, pytest (parallel + integration
> exclusions). One commit when all checks pass.

## WHERE

- `src/mcp_tools_sql/config/models.py` — modify `QueryConfig`
- `src/mcp_tools_sql/default_queries.toml` — rename `max_rows` to
  `max_rows_default` (only `read_columns` currently sets it)
- `src/mcp_tools_sql/schema_tools.py` — `_build_tool_fn`: read
  `config.max_rows_default`, add clamp + note
- `src/mcp_tools_sql/cli/commands/verify.py` — `verify_queries`:
  `qcfg.max_rows` → `qcfg.max_rows_default`
- `tests/config/test_models.py` — validator tests
- `tests/test_default_queries.py` — rename assertion
- `tests/test_schema_tools.py` — clamp test
- `tests/cli/test_verify.py` — adjust field references

## WHAT

```python
class QueryConfig(BaseModel):
    description: str = ""
    sql: str
    params: dict[str, QueryParamConfig] = {}
    max_rows_default: int = 100
    max_rows_hard: int | None = None
    backends: dict[str, BackendQueryConfig] = {}

    @model_validator(mode="after")
    def _default_max_rows_hard(self) -> Self:
        if self.max_rows_hard is None:
            self.max_rows_hard = self.max_rows_default
        return self
```

## HOW

- `max_rows_hard` is declared `int | None` to accept omission from TOML;
  validator copies `max_rows_default` so consumers see an `int`.
- `_build_tool_fn` signature default for `max_rows` becomes
  `config.max_rows_default`.
- After `kwargs.pop("max_rows", ...)`, compare against `config.max_rows_hard`
  and clamp; capture a note string and append it after `format_rows`.

## ALGORITHM (clamp inside `_tool_fn`)

```
requested = kwargs.pop("max_rows", config.max_rows_default)
hard = config.max_rows_hard
note = ""
if requested > hard:
    note = (
        f"\n\nRequested max_rows={requested} exceeds hard limit "
        f"{hard}; capped at {hard}."
    )
    requested = hard
# ... existing query + filter ...
return format_rows(rows, requested) + note
```

## DATA

- Field types after validator: `max_rows_default: int`, `max_rows_hard: int`.
- Note appears after the formatted table, separated by `\n\n`.
- Schema tools see no behaviour change (their `max_rows_hard` defaults to
  `max_rows_default`, so the clamp is a no-op).

## TDD Tests

1. `tests/config/test_models.py::test_max_rows_hard_defaults_to_default`
2. `tests/config/test_models.py::test_max_rows_hard_explicit_value`
3. `tests/test_default_queries.py` — flip `max_rows == 100` →
   `max_rows_default == 100` (test name may stay)
4. `tests/test_schema_tools.py::test_max_rows_clamped_to_hard_limit` —
   build a `QueryConfig` with `max_rows_default=5, max_rows_hard=10`; pass
   `max_rows=500` to the tool over enough rows; assert clamped output and
   that the note text `"Requested max_rows=500 exceeds hard limit 10"`
   appears
5. `tests/cli/test_verify.py` — update any references to the renamed field

## Verification

- pylint, mypy, pytest (parallel + integration exclusions)

## Commit

One commit.
