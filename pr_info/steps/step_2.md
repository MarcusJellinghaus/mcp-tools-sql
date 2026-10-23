# Step 2 — Full pylint run with mcp_coder's config

## LLM prompt

> Read `pr_info/steps/summary.md`, then implement `pr_info/steps/step_2.md` exactly.
> Step 1 (create_backend move) must already be committed. Fix the listed findings,
> switch the pylint config and the CI command. Run format, pylint, pytest (`-n auto`),
> mypy; all must pass. Produce exactly one commit.

## WHERE

- `pyproject.toml` — `[tool.pylint.messages_control]`
- `.github/workflows/ci.yml` — `test` matrix, `pylint` entry
- `tests/test_sql_placeholders.py:429`
- `tests/verification/test_config_files.py:158,181`
- `tests/test_schema_tools_multitarget.py:402-434` (`_FanoutBackend` stubs)

## WHAT / HOW

### 1. pylint config (`pyproject.toml`)

Replace the comment block and `disable = ["W", "C", "R", "W1203"]` with (copied from mcp_coder's `pyproject.toml`):

```toml
[tool.pylint.messages_control]
disable = [
    "C",       # conventions — not enabled in this project
    "R",       # refactor suggestions — not enabled in this project
    "W1203",   # logging-fstring-interpolation — project uses f-strings for readability
    "W0621",   # redefined-outer-name — standard pytest fixture pattern
    "W0511",   # fixme/TODO — informational only, not a quality gate
    "W0212",   # protected-access — legitimate in tests and controlled src usage
    "W0613",   # unused-argument — pytest fixtures injected by name
    "W0611",   # unused-import — owned by ruff F401 (pylint flags the X-as-X re-export convention)
    "W0404",   # reimported — reimports across test functions
    "W0718",   # broad-exception-caught — intentional catch-all in CLI/workflow error handling
    "W0706",   # try-except-raise — explicit re-raise for clarity in error chains
    "W4903",   # deprecated-argument — tracked for future cleanup
]
enable = ["R0401"]
```

Keep `[tool.pylint.main]` and `[tool.pylint.typecheck]` unchanged.

### 2. W1404 implicit string concatenation (3 findings)

Leftover split literals — merge each into one literal, no semantic change:

- `tests/test_sql_placeholders.py:429`:
  `"WITH a AS (SELECT 1 AS x), b AS (SELECT 2 AS y) SELECT a.x, b.y FROM a, b",`
- `tests/verification/test_config_files.py:158`:
  `'[connections.main]\nbackend = "mssql"\ndatabases = ["sales"]\n',`
- `tests/verification/test_config_files.py:181`:
  `'[connections.main]\nbackend = "mssql"\ndatabases = ["sales", "hr"]\n',`

### 3. W0223 abstract-method (4 findings at `_ReadOnlyOnlyBackend`)

In `_FanoutBackend`, the 4 stubs `execute_readonly_query_with_columns`, `execute_update`, `explain`, `get_isolated_connection` raise `NotImplementedError`, which pylint treats as abstract. For each:

```python
    def explain(self, sql: str, params: dict[str, Any] | None = None) -> str:
        """Unused in these tests.

        Raises:
            AssertionError: Always.
        """
        raise AssertionError("unused in these tests")
```

No disable comment, no global disable.

### 4. CI (`ci.yml`)

`{name: "pylint", cmd: "pylint --version && pylint -E ./src ./tests"}` →
`{name: "pylint", cmd: "pylint --version && pylint ./src ./tests"}  # configuration via pyproject.toml`

## DATA

None (config + test literals).

## Checks

- `mcp__mcp-tools-py__run_pylint_check(target_directories=["src", "tests"], max_issues=20)` → clean.
- If pylint reports findings other than the 9 listed above (3× W1404, 2× R0401 — fixed in step 1, 4× W0223), write one line to `pr_info/.blocked.txt` naming the message IDs and stop.
- format, pytest (`-n auto`), mypy, ruff pass.

## Commit

`chore(pylint): run full pylint with mcp_coder's config`
