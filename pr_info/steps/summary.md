# Summary — Adopt mcp_coder's ruff rule set (issue #81)

Part of MarcusJellinghaus/mcp_coder#1163. Brings `[tool.ruff.lint]` in line with
mcp_coder `0949073a`: `F, E, B, C4, S, SIM, ANN, UP, PLW1510` on top of the
existing `D` + `DOC` rules, with preview rules gated.

Baseline (measured on `main` @ `b063522`, target config, `src tests tools`):
2158 findings — `S101` 2095, `UP045` 20, `S608` 20, `S106` 10, `SIM117` 3,
`B017` 3, `B905` 2, `S105` 2, `S607` 1, `B009` 1, `S108` 1. Everything else is
already clean.

## Architectural / design changes

This is a lint-policy change. No public API, tool schema or behaviour changes.

1. **Preview rules are opt-in by exact code.** `explicit-preview-rules = true`;
   `DOC` and `SIM905` are listed by exact code. A bare preview prefix enforces
   nothing once the gate is on.
2. **Asserts no longer carry runtime invariants in `src`.** Asserts vanish
   under `python -O`, so each src assert either becomes a real check or the
   code is restructured so the type narrows without one:
   - `SQLiteBackend._require_connection()` (new, private): `connect()`, raise
     `RuntimeError` if still `None`, return the connection. The four
     connection-using methods call it, matching MSSQL's existing
     `_ensure_connected()`, whose assert becomes a `raise RuntimeError`.
   - `update_tools`: `register()` already raises `ValueError` when `key` is
     missing. The two private builders now take the narrowed
     `key: UpdateKeyConfig` as a parameter instead of re-checking
     `config.key`. **KISS deviation from the issue text:** the issue asked for
     a `raise ValueError` in each builder; passing the key removes two
     unreachable branches and two `Raises:` sections and still meets every
     acceptance criterion.
   - `summarize/tools.py`: the value-list condition tests `distinct is not None`
     directly (equivalent to `include_distinct and category != "other"`, since
     `_split_stats` returns `None` exactly when distinct was not measured).
3. **String-built SQL and PATH-resolved executables in src stay visible.**
   Each one gets an inline `# noqa: S608` / `# noqa: S607` with a reason,
   never a per-file ignore. Tests get a per-file ignore (fixtures build SQL and
   use fake credentials and `/tmp` literals on purpose).
4. **PEP 604 unions everywhere.** `Optional[X]` → `X | None`, including the
   runtime-built tool signatures. Because `get_origin(int | None)` is
   `types.UnionType` (not `typing.Union`), the `tool` CLI's
   `_unwrap_annotation` accepts both; otherwise optional `int`/`float`/`bool`
   params would degrade to `str` flags. Tool `inputSchema`s stay
   byte-identical (checked with a throwaway `.scratch/` probe).
5. **CI:** the `ruff-docstrings` job becomes `ruff` and also checks `tools/`.

Not adopted: `TRY`, `PL` (except `PLW1510`), `EM`, `ANN401`, `E501`
(rejected in mcp_coder #1172 / #1181). No `S404`/`S603` ignores (they don't
fire here once preview rules are gated).

## Final `[tool.ruff.lint]` shape

```toml
[tool.ruff.lint]
# preview needed for DOC rules (pydoclint)
#
# TRY, EM, PL (except PLW1510) rejected — see mcp_coder #1172, #1181.
preview = true
explicit-preview-rules = true   # preview rules fire only when selected by exact code
select = [
    "D",
    "ANN",
    # DOC rules are preview-only; with explicit-preview-rules they must be
    # listed by exact code — a bare "DOC" prefix silently enforces nothing.
    "DOC201", "DOC202", "DOC402", "DOC403", "DOC501", "DOC502",
    "SIM",
    # SIM905 is preview-only; see explicit-preview-rules note above.
    "SIM905",
    "E",
    "F",
    "C4", "B",
    "S",
    # PLW1510 only: the PL prefix would re-enable pylint's disabled R category (PLR09xx).
    "PLW1510",
    "UP",
]
ignore = [
    "D104",  # missing docstring in __init__.py (low value)
    "D107",  # missing docstring in __init__ method (redundant with class docstring)
    "ANN401",  # Any is correct at library/CLI boundaries; mypy strict covers the rest
    "E501",  # line length is owned by the formatter (black); not re-checked here
]

[tool.ruff.lint.per-file-ignores]
# tests: assert is the pytest idiom (S101); S105/S106/S108 fire on fake
# credentials and "/tmp/..." literals used as test data, never opened;
# S608: DDL/DML fixtures build SQL from strings on purpose.
"tests/**/*.py" = ["D", "DOC", "SIM117", "S101", "S105", "S106", "S108", "S608"]
```

## Files modified

| File | Step | Change |
|---|---|---|
| `pyproject.toml` | 1, 2, 3, 6, 7 | ruff lint config |
| `tests/backends/test_sqlite.py` | 3 | `B017`: `pytest.raises(sqlite3.DatabaseError)` ×3 |
| `src/mcp_tools_sql/backends/mssql.py` | 3, 4 | `B905` `zip(strict=True)`; `_ensure_connected` assert → raise |
| `tests/backends/test_mssql.py` | 3 | `B905` `zip(strict=True)` |
| `tests/backends/test_registry.py` | 3 | `B009` plain attribute access |
| `src/mcp_tools_sql/backends/sqlite.py` | 4 | new `_require_connection()`; 4 asserts removed |
| `src/mcp_tools_sql/update_tools.py` | 5, 6, 7 | builders take `key`; `noqa: S608`; `Optional` → `\|` |
| `src/mcp_tools_sql/summarize/tools.py` | 5, 7 | `distinct is not None` condition; `Optional` → `\|` |
| `src/mcp_tools_sql/summarize/sql.py` | 6 | `noqa: S608` with reason |
| `src/mcp_tools_sql/verification/connection.py` | 6 | `noqa: S607` with reason |
| `src/mcp_tools_sql/query_helpers.py` | 7 | `Optional` → `\|`, stale `noqa: UP007` removed |
| `src/mcp_tools_sql/count_tools.py` | 7 | same |
| `src/mcp_tools_sql/validation_tools.py` | 7 | same |
| `src/mcp_tools_sql/config/models.py` | 7 | `Optional[UpdateKeyConfig]` → `UpdateKeyConfig \| None` |
| `src/mcp_tools_sql/cli/commands/tool_args.py` | 7 | `_unwrap_annotation` accepts `types.UnionType` |
| `tests/cli/test_tool_args.py` | 7 | new unit test; `Optional` → `\|`, stale `noqa` removed |
| `tests/test_dynamic_tool_registration.py` | 7 | `Optional` → `\|`, stale `noqa` removed |
| other test files with `Optional[...]` | 7 | converted by `run_ruff_fix` |
| `.github/workflows/ci.yml` | 8 | job `ruff-docstrings` → `ruff`, adds `tools` |

No files or modules are created in the repository. `.scratch/` is used
temporarily in step 7 and deleted inside that step.

## Step overview (one commit each)

| Step | Issue step | Content |
|---|---|---|
| 1 | 1 | Gate preview rules |
| 2 | 2 | Add already-clean groups (config only) |
| 3 | 3 | `B` + its 5 fixes |
| 4 | 4 (part) | Backend asserts → `_require_connection` / raise |
| 5 | 4 (part) | `update_tools` key param + `summarize` restructure |
| 6 | 4 (part) | Select `S`, tests per-file ignore, `S608`/`S607` noqa |
| 7 | 5 | `UP` + `_unwrap_annotation` fix + unit test (schema probe) |
| 8 | 6 | CI job rename and `tools/` coverage |

Issue step 4 is split into three commits because its parts are independent.
Steps 4–5 only remove asserts, so every commit keeps `ruff check` green.

## Checks for every step

Before committing: `run_format_code`, then `run_ruff_check`
(`target_directories=["src","tests","tools"]`), `run_pylint_check`,
`run_mypy_check`, and `run_pytest_check(extra_args=["-n","auto"])`. All must
pass.

Before merge (Marcus): swap the required status check `ruff-docstrings` →
`ruff` in branch protection.
