# Step 1 — Relocate `to_dialect` to `backends/base.py` and make it strict

> Read `pr_info/steps/summary.md` first. This step implements items 1 and 2
> ("The move" + "Message changes / create_backend") of the issue. It is one
> atomic commit: the move breaks imports if split, so tests + implementation +
> all gates land together.

## TDD order

1. **Tests first.** Add direct unit tests for the new `to_dialect` in
   `tests/test_smoke.py` (they fail: symbol not yet in `backends.base`). Update
   the `test_connection.py` fixture literal to the enumerated message.
2. **Implementation.** Add `_DIALECTS` + `to_dialect` to `backends/base.py`,
   update `create_backend`'s message, remove `to_dialect` from utils, move the
   three imports.
3. Run all gates green.

## WHERE

- `src/mcp_tools_sql/backends/base.py` — add dict + function, edit `create_backend`.
- `src/mcp_tools_sql/utils/sql_placeholders.py` — remove function, `__all__`
  entry (line 46), and the module-docstring mention (line 15).
- `src/mcp_tools_sql/count_tools.py` (import ~line 30-35),
  `src/mcp_tools_sql/validation_tools.py` (import ~line 14-19),
  `src/mcp_tools_sql/summarize/tools.py` (import line 52) — move the import.
- `tests/test_smoke.py` — new `to_dialect` tests beside `create_backend` tests.
- `tests/verification/test_connection.py` — fixture literal (line 93).

## WHAT

In `backends/base.py`:

```python
# keep in sync with the create_backend dispatch chain below
_DIALECTS: dict[str, str] = {
    "sqlite": "sqlite",
    "mssql": "tsql",
    "pyodbc": "tsql",
}

def to_dialect(backend_name: str) -> str:
    """Map a backend name to the sqlglot dialect used for parsing/rendering.

    Args:
        backend_name: The configured backend identifier
            (``"sqlite"``, ``"mssql"``, or ``"pyodbc"``).

    Returns:
        The sqlglot dialect name (``"sqlite"`` or ``"tsql"``).

    Raises:
        ValueError: If ``backend_name`` is not a supported backend.
            Unreachable via the tool call sites (each runs ``create_backend``
            first); kept as defence-in-depth against a future caller.
    """
```

`create_backend`'s final two lines change from the terser message to the same
enumerated form.

## HOW (integration points)

- Both raises inline the **same** f-string — no helper:
  `f"Unsupported backend: {backend_name}. Supported: {', '.join(sorted(_DIALECTS))}."`
  (`create_backend` uses `config.backend` as the name).
- Call-site import change, e.g. in `count_tools.py`:
  remove `to_dialect` from the `mcp_tools_sql.utils.sql_placeholders` import
  block; add `from mcp_tools_sql.backends.base import to_dialect` (or extend an
  existing `backends` import if present). Same for `validation_tools.py` and
  `summarize/tools.py`. No `.importlinter` / `tach.toml` edits — the layer
  already permits `tools → backends`.
- `utils/sql_placeholders.py`: delete the `to_dialect` def, drop `"to_dialect"`
  from `__all__`, and remove `:func:\`to_dialect\`` from the docstring list at
  line 15 (leave `count_statements` / `first_statement_kind` / `basic_preflight`).

## ALGORITHM (to_dialect)

```
dialect = _DIALECTS.get(backend_name)
if dialect is None:
    raise ValueError(f"Unsupported backend: {backend_name}. "
                     f"Supported: {', '.join(sorted(_DIALECTS))}.")
return dialect
```

## DATA

- `to_dialect("sqlite") -> "sqlite"`, `("mssql"|"pyodbc") -> "tsql"`.
- Unknown name → `ValueError("Unsupported backend: X. Supported: mssql, pyodbc, sqlite.")`.
- `create_backend` unsupported → same message string (piped verbatim into the
  verifier by `orchestrator.py`).

## Test detail

In `tests/test_smoke.py` (beside `test_create_backend_*`):

```python
def test_to_dialect_mappings() -> None:
    from mcp_tools_sql.backends.base import to_dialect
    assert to_dialect("sqlite") == "sqlite"
    assert to_dialect("mssql") == "tsql"
    assert to_dialect("pyodbc") == "tsql"

def test_to_dialect_unknown_raises() -> None:
    from mcp_tools_sql.backends.base import to_dialect
    with pytest.raises(
        ValueError,
        match="Unsupported backend: postgresql. Supported: mssql, pyodbc, sqlite.",
    ):
        to_dialect("postgresql")
```

In `tests/verification/test_connection.py` line 93:
`probe_error="Unsupported backend: postgresql. Supported: mssql, pyodbc, sqlite."`
Leave `test_smoke.py:65` (`match="Unsupported backend"`) unchanged — the regex
search still matches.

## Gates

`run_pylint_check`, `run_pytest_check` (with the CLAUDE.md exclusion markers),
`run_mypy_check`, `run_lint_imports_check`, `run_ruff_check` — all green. Ruff
DOC will fail if the `Raises:` section is missing.

## LLM prompt

> Implement Step 1 from `pr_info/steps/step_1.md` (context in
> `pr_info/steps/summary.md`). Move `to_dialect` from
> `utils/sql_placeholders.py` into `backends/base.py` beside `create_backend`,
> sharing a module-level `_DIALECTS` dict; make it raise `ValueError` on an
> unrecognised name and give `create_backend` the same enumerated message. Move
> the `to_dialect` import in `count_tools.py`, `validation_tools.py`, and
> `summarize/tools.py` to `backends.base`. Remove `to_dialect` from utils'
> `__all__` and module docstring. Write the `to_dialect` unit tests in
> `tests/test_smoke.py` first, and update the `probe_error` fixture literal in
> `tests/verification/test_connection.py`. Do not add a message helper, do not
> turn the dict into a dispatch table, do not edit `.importlinter`/`tach.toml`.
> Finish with all quality gates green. One commit.
