# Step 2 — Add `required` Flag to `UpdateFieldConfig`

## Goal

Add a `required: bool = False` attribute to `UpdateFieldConfig` so update
tools can declare individual fields as required. Default is `False` because
partial updates are the common case (deliberate flip of
`QueryParamConfig`'s `required: bool = True` default).

This is a tiny, self-contained config-model change.

## WHERE

- `src/mcp_tools_sql/config/models.py` — `UpdateFieldConfig` gains one field
- `tests/config/test_models.py` — tests for the new field
- `vulture_whitelist.py` — confirm no change needed (`_.required` already
  whitelisted for `QueryParamConfig` and covers the new attribute too)

## WHAT

```python
class UpdateFieldConfig(BaseModel):
    """A field that can be updated."""

    field: str
    type: str = "str"
    description: str = ""
    required: bool = False
```

## HOW

- No new imports.
- Pydantic picks up the new attribute automatically.
- `vulture_whitelist.py` already contains `_.required` — re-run vulture to
  confirm no false positive surfaces.

## ALGORITHM

No algorithm — model field addition only.

## DATA

`UpdateFieldConfig` instances now expose `.required` (bool, default
`False`).

## Tests

TDD: add tests first.

- `tests/config/test_models.py`:
  - `UpdateFieldConfig` default `required` is `False`.
  - `UpdateFieldConfig(field="x", required=True)` honours the override.
  - Loading TOML `[[updates.foo.fields]] field = "x" required = true` parses
    correctly via `UpdateConfig.model_validate(...)`.

## LLM Prompt

> Read `pr_info/steps/summary.md` (full file) and `pr_info/steps/step_2.md`.
> Implement Step 2 only: add `required: bool = False` to the
> `UpdateFieldConfig` Pydantic model in
> `src/mcp_tools_sql/config/models.py`. Follow TDD: add the three test
> cases described in this step to `tests/config/test_models.py` before
> changing the model. Run `mcp__tools-py__run_pylint_check`,
> `mcp__tools-py__run_pytest_check` (with the fast unit-test marker
> exclusion), and `mcp__tools-py__run_mypy_check`. Make exactly one commit
> when green.
