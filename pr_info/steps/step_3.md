# Step 3 — pytest `addopts` aligned with mcp_coder

## LLM prompt

> Read `pr_info/steps/summary.md`, then implement `pr_info/steps/step_3.md` exactly.
> Change pytest `addopts`, drop the now-redundant `-n auto` from the CI pytest command.
> Run format, pylint, pytest (`-n auto`), mypy; all must pass. Produce exactly one commit.

## WHERE

- `pyproject.toml` — `[tool.pytest.ini_options]`
- `.github/workflows/ci.yml` — `test` matrix, `pytest` entry

## WHAT / HOW

`pyproject.toml`:

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_default_fixture_loop_scope = "function"
pythonpath = ["src"]
# --strict-markers: unknown markers are errors (catches typos)
# -p no:tach: Disable tach plugin (noisy output about unaffected tests)
addopts = ["--strict-markers", "--tb=short", "-n", "auto", "-p", "no:tach"]
markers = [ ...unchanged... ]
```

Keep `asyncio_default_fixture_loop_scope`, `pythonpath`, `markers` unchanged.

`ci.yml` pytest entry: remove the explicit `-n auto` (now in `addopts`):

`pytest --version && pytest tests -m 'not sqlite_integration and not mssql_integration and not postgresql_integration'`

## DATA

None.

## Checks

- `mcp__mcp-tools-py__run_pytest_check(extra_args=["-n", "auto", "--collect-only", "-q"])` → collection succeeds with no "not found in `markers`" errors (≈1270 tests). If collection errors on an unregistered marker, write one line to `pr_info/.blocked.txt` naming the marker and stop.
- Full pytest (`-n auto`), pylint, mypy pass.

## Commit

`chore(pytest): align addopts with mcp_coder`
