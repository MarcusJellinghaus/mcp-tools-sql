# Step 3 — Enable `B` (flake8-bugbear) and fix its 5 findings

## LLM prompt
> Read `pr_info/steps/summary.md`, then implement `pr_info/steps/step_3.md`.
> Run the checks listed below, format, and make exactly one commit.

## WHERE
- `pyproject.toml`
- `tests/backends/test_sqlite.py` (lines ~331, ~342, ~352)
- `src/mcp_tools_sql/backends/mssql.py` (line ~214, `execute_query`)
- `tests/backends/test_mssql.py` (line ~382)
- `tests/backends/test_registry.py` (line ~128)

## WHAT
1. `pyproject.toml`: `select` gets `"B"` (written as `"C4", "B",` on one line).
2. `B017` — in `test_connect_invalid_path`, `test_connect_readonly_file`,
   `test_connect_corrupt_db`: `pytest.raises(Exception)` →
   `pytest.raises(sqlite3.DatabaseError)`. Add `import sqlite3` if the file
   lacks it. `DatabaseError` is the common base of `OperationalError`; the
   backend does not wrap `sqlite3` errors.
3. `B905`:
   - `mssql.py`: `dict(zip(columns, row))` → `dict(zip(columns, row, strict=True))`
   - `test_mssql.py`: same change in the list comprehension.
4. `B009` — `test_registry.py`: `getattr(backend, "_connection")` →
   `backend._connection  # pylint: disable=protected-access`
   (only add the pylint comment if `run_pylint_check` flags it; pylint's
   `W` category is disabled in this repo).

## HOW
TDD: the existing tests are the tests. Narrowing `pytest.raises` makes them
stricter; they must still pass. `test_connect_readonly_file` is skipped on
Windows, so only Linux CI exercises it.

## Verification
- `run_ruff_check(target_directories=["src","tests","tools"])` → clean.
- `run_pytest_check(extra_args=["-n","auto","tests/backends"])` green, then
  the full suite.
- If a narrowed `pytest.raises` fails because a different exception type is
  raised, write one line to `pr_info/.blocked.txt` naming the test and the
  actual type, and stop.
- pylint, mypy green.

## Commit
`ruff: enable B and fix bugbear findings`
