# Step 3 — `load_database_config`: explicit missing path raises

## LLM prompt
Read `pr_info/steps/summary.md`, then implement `pr_info/steps/step_3.md`.
Write the tests first, then the code. Run `run_format_code`, pylint, pytest
(`extra_args: ["-n", "auto"]`), mypy and ruff; all must pass. One commit:
`feat(config): explicit database config path must exist`.

## WHERE
- `src/mcp_tools_sql/config/loader.py`
- `tests/config/test_loader.py`

## WHAT
```python
def load_database_config(path: Path | None = None) -> DatabaseConfig:
```
## ALGORITHM
```
if path is None:
    path = get_user_app_data_dir("mcp-tools-sql") / "config.toml"
    if not path.exists(): return DatabaseConfig()        # zero-config default unchanged
elif not path.exists():
    raise ValueError(f"Database config not found: {path}")
parse as today
```
Update the docstring (Returns + `Raises: ValueError`).
`verification/config_files.py` checks `exists()` before calling, so it is unaffected.

## Tests (write first)
- Replace `TestLoadDatabaseConfig::test_missing_file_returns_defaults` with a
  test that an explicit missing path raises `ValueError` whose message contains the path.
- Keep/confirm the `load_database_config(None)` default-location test (absent file → defaults).
- Run the full suite; any other test that passed an explicit nonexistent
  database config and relied on defaults must write the file or pass `None`.

## DATA
Unchanged return type; new `ValueError` for an explicit missing path.
