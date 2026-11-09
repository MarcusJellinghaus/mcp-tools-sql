# Step 2 — Hide credentials in database-config validation errors

## LLM prompt

> Read `pr_info/steps/summary.md` (section 3), then implement **this step only**
> (`pr_info/steps/step_2.md`). Do TDD: add the tests first and confirm they fail, then add
> the config. Run pylint, pytest (`-n auto`), mypy, ruff, lint-imports, tach and
> format_code, then make one commit.

## WHERE

- `src/mcp_tools_sql/config/models.py`
- `tests/config/test_models.py`
- `tests/verification/test_config_files.py`

## WHAT

```python
class ConnectionConfig(BaseModel):
    model_config = ConfigDict(hide_input_in_errors=True)
    ...

class DatabaseConfig(BaseModel):
    model_config = ConfigDict(hide_input_in_errors=True)
    ...
```

Query and update models are not changed.

## HOW

`ConfigDict` is already imported in `models.py`. pydantic applies only the outermost
model's setting to nested errors, so `DatabaseConfig` covers loading from file and
`ConnectionConfig` covers direct validation.

## ALGORITHM

None (config only).

## DATA

`str(ValidationError)` no longer contains `input_value=...`.

## Precondition

If the new tests still find the password in `str(exc)` after the config is added, write
one line to `pr_info/.blocked.txt` and stop.

## Tests (write first)

Use a rule-7 conflict, which prints the whole connection dict today:
`{"backend": "mssql", "host": "h", "database": "a", "databases": ["b"], "password": "s3cret-pw"}`.

- `test_models.py`:
  - `DatabaseConfig.model_validate({"connections": {"c": <dict>}})` raises
    `ValidationError`, and `"s3cret-pw" not in str(exc)`;
  - `ConnectionConfig.model_validate(<dict>)` raises, and `"s3cret-pw" not in str(exc)`;
  - the error text still names the problem (`"conflicts"` is in `str(exc)`).
- `test_config_files.py`: a database config TOML with that connection plus the password
  gives a `database_config_parse` row with `ok is False` and `"s3cret-pw"` not in its
  `error`.
