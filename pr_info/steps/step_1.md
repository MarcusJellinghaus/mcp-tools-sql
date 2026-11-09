# Step 1 – Config: timeouts, `[limits]`, validation, `verify`, help/docs

## LLM prompt
Read `pr_info/steps/summary.md` (sections 1 and 6) and this file. Implement
step 1 only, test-first: add the timeout fields to `ConnectionConfig`, add
`LimitsConfig` with its validation, report violations through `verify`, and
document all five settings in `help_config.py` and `docs/configuration.md`. No
behaviour changes outside config yet. Run pylint, pytest (`-n auto`), mypy and
lint-imports; format; one commit.

## WHERE
- `src/mcp_tools_sql/config/models.py`
- `src/mcp_tools_sql/verification/config_files.py`
- `src/mcp_tools_sql/cli/commands/help_config.py`
- `docs/configuration.md`
- Tests: `tests/config/test_limits_config.py` (new),
  `tests/verification/test_config_files_limits.py` (new),
  `tests/cli/test_help_config.py` (add `LimitsConfig` to `_AUTHORED_MODELS`),
  `tests/test_default_queries.py` (sync test)

## WHAT
```python
# config/models.py
BUILTIN_MAX_ROWS_HARD: int = 100  # max_rows_hard of the bundled schema tools

class ConnectionConfig(BaseModel):
    ...
    query_timeout_seconds: int = Field(default=30, gt=0)
    connect_timeout_seconds: int = Field(default=15, gt=0)  # SQL Server only

class LimitsConfig(BaseModel):
    max_output_chars: int = Field(default=80_000, gt=0)
    max_cell_chars: int = Field(default=500, gt=0)
    max_count_rows: int = Field(default=100_000, ge=BUILTIN_MAX_ROWS_HARD)

def count_rows_violation(
    limits: LimitsConfig, queries: dict[str, QueryConfig]
) -> str | None: ...

class QueryFileConfig(BaseModel):
    ...
    limits: LimitsConfig = LimitsConfig()

    @model_validator(mode="after")
    def _check_count_rows(self) -> Self: ...  # raises ValueError(violation)
```

## HOW
- `QueryConfig._default_max_rows_hard` already fills `max_rows_hard`; the
  effective hard limit is `max(config.max_rows_hard, MAX_ROWS_MIN)`. Use the
  literal `1` floor in `config` (it cannot import `formatting`), with a comment
  pointing to `formatting.MAX_ROWS_MIN`.
- `verify` (`_load_query_half`): after
  `query_config = top.model_copy(update=...)`, call
  `count_rows_violation(top.limits, queries)`. If it returns a message, overwrite
  `checks["query_config_parse"] = make_entry(ok=False, error=msg)`. Still return
  `query_config` so the other checks run. Invalid `<= 0` values already fail
  `QueryFileConfig.model_validate` / `load_database_config` and land in the
  existing `query_config_parse` / `database_config_parse` rows; only add tests.
- `help_config.py`: under the connection keys add
  `query_timeout_seconds` (default 30; statement timeout for every statement on
  the connection) and `connect_timeout_seconds` (default 15; SQL Server login
  timeout, ignored on SQLite). In the query-config part add a `[limits]` block
  listing `max_output_chars`, `max_cell_chars`, `max_count_rows` with defaults
  and the rule `max_count_rows >= every max_rows_hard`. Keep the key-line layout
  the drift guard parses (indented, two or more spaces before the description).
- `docs/configuration.md`: document the two connection keys (note that 0 is
  rejected because ODBC treats `timeout = 0` as no timeout) and a new `[limits]`
  section (table with key / default / meaning, plus the "two boundaries" table
  from the issue).

## ALGORITHM
```
count_rows_violation(limits, queries):
    for name, q in queries.items():
        hard = max(q.max_rows_hard or q.max_rows_default, 1)
        if hard > limits.max_count_rows:
            return f"[queries.{name}] max_rows_hard {hard} exceeds [limits] max_count_rows {limits.max_count_rows}"
    return None
```

## DATA
- `count_rows_violation` → `None` or a one-line message.
- `QueryFileConfig.limits` → `LimitsConfig` (defaults when `[limits]` is absent).

## Tests (write first)
- `tests/config/test_limits_config.py`, parametrised:
  - defaults (30 / 15 / 80000 / 500 / 100000);
  - `0` and `-1` rejected for each of the five settings;
  - `max_count_rows = 99` rejected (below `BUILTIN_MAX_ROWS_HARD`);
  - a configured query with `max_rows_hard = 500` and `max_count_rows = 200`
    rejected; `max_rows_default = 500` without `max_rows_hard` rejected too;
  - `connect_timeout_seconds` accepted on a SQLite connection.
- `tests/verification/test_config_files_limits.py`: `verify_config_files` reports
  `query_config_parse` not-ok for (a) `[limits] max_output_chars = 0` and (b) a
  query whose `max_rows_hard` exceeds `max_count_rows`; reports
  `database_config_parse` not-ok for `query_timeout_seconds = 0`.
- `tests/test_default_queries.py`: every built-in's effective `max_rows_hard`
  ≤ `BUILTIN_MAX_ROWS_HARD`.
- `tests/cli/test_help_config.py`: import `LimitsConfig` and add it to
  `_AUTHORED_MODELS`; the drift guard must pass.
