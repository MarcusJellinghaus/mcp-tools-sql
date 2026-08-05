# Issue #51 — Harden dialect resolution

## Goal

Close three gaps in the layer that decides how SQL is parsed and re-rendered.
None is a reproducible user-facing bug today; all three are silent or
uninformative failures.

1. **Relocate `to_dialect` from `utils/sql_placeholders.py` to `backends/base.py`**
   and make it **strict** — raise `ValueError` on an unrecognised backend name
   instead of silently defaulting to `"sqlite"`. Beside `create_backend`, both
   read one module-level dict (backend name → sqlglot dialect) as the single
   source of truth for the supported-name set.
2. **Clearer parse errors** — `basic_preflight`'s verdict names the dialect the
   SQL was parsed under, dialect-first so it precedes sqlglot's multi-line text.
3. **Bump the sqlglot floor** to `>=30` (no upper bound).

## Architectural / design changes

- **The move is the fix, not a workaround.** `to_dialect` maps a *backend
  identifier* to a dialect and parses nothing, yet it lived in a module
  documented as placeholder handling. Making it strict there would create a
  *second* enumeration of the supported-backend set, duplicating
  `create_backend` — and the `forbidden-imports` contract in `.importlinter`
  bars `utils → backends`, so no shared constant is legal across that boundary.
  Co-locating `to_dialect` with `create_backend` in `backends/base.py` lets both
  functions share one module-level dict `_DIALECTS`. The import-linter contract
  that blocked a shared constant was the signal the function was in the wrong
  module.

- **Single source of truth for the *name set*, not for dispatch.** `_DIALECTS`
  feeds `to_dialect` and both error messages only. `create_backend` keeps its
  lazy-import `if`/`elif` chain (deliberate — it avoids importing `pyodbc` when
  unused). The dict carries a "keep in sync with the dispatch chain below"
  comment. Both failure modes are benign and asymmetric: forget the dict → the
  backend works but is missing from the error list; forget the chain →
  `to_dialect` succeeds and `create_backend` raises.

- **Layering is preserved.** All three call sites (`count_tools`,
  `validation_tools`, `summarize`) already sit above `backends` in the layer
  stack and already declare `depends_on = mcp_tools_sql.backends` in
  `tach.toml`, so **no `tach.toml` or `.importlinter` edit is needed**.
  `backends` never imports the tools layer, so no import cycle is introduced.

- **The strict raise is genuinely unreachable today** — defence-in-depth. At all
  three call sites `registry.backend_for(target)` runs one line earlier and
  `create_backend` rejects the same names, so `to_dialect` only ever receives
  `sqlite`/`mssql`/`pyodbc`. It gets a **direct unit test** because no tool path
  can reach it.

- **Two user-visible message changes.**
  - `create_backend`'s `ValueError` string is piped into the verifier by
    `verification/orchestrator.py`, so `verify` on an unsupported config prints
    the enumerated list.
  - The parse-error verdict reaches `count_records`, `validate_sql`, **and**
    `summarize_columns` (via `summarize/sql.py:validate_where`). The dialect is
    placed **first** — sqlglot's `ParseError` text ends in an ANSI-underlined SQL
    excerpt, so appending after it would land the label inside that excerpt; and
    the misread being fixed is an inference the model forms *while reading*, so
    the fact must arrive first.

## KISS decisions

- **No message helper.** The two raises are adjacent functions in one file; each
  inlines the identical f-string. `', '.join(sorted(_DIALECTS))` yields the
  required `mssql, pyodbc, sqlite` regardless of dict order.
- **Test assertions stop before the dialect name** — `startswith("Invalid SQL.
  ParseError (SQL parsed as ")` — so they verify the new format without a
  per-test backend-dialect lookup. The one multi-target test that exists to
  distinguish sqlite vs tsql keeps `as sqlite)` pinned.
- **`create_backend` keeps its `if`/`elif` chain** — the dict is not a dispatch
  table (rejected in the issue; revisit only if a third backend lands).

## Out of scope (do not touch)

Postgres fail-fast, `ConnectionConfig.backend` `Literal` typing, `init.py`
scaffolding, the dead `_has_leading_cte` `"with"` fallback (kept as-is), any
new call-site error handling, ANSI escape codes in parse errors.

## Files created / modified

**Source (modified):**
- `src/mcp_tools_sql/backends/base.py` — add `_DIALECTS` dict + `to_dialect`;
  update `create_backend`'s error message to the enumerated form.
- `src/mcp_tools_sql/utils/sql_placeholders.py` — remove `to_dialect`
  (function, `__all__` entry, module-docstring mention); change
  `basic_preflight`'s parse-error verdict to the dialect-first format.
- `src/mcp_tools_sql/count_tools.py` — move `to_dialect` import to `backends.base`.
- `src/mcp_tools_sql/validation_tools.py` — move `to_dialect` import to `backends.base`.
- `src/mcp_tools_sql/summarize/tools.py` — move `to_dialect` import to `backends.base`.
- `pyproject.toml` — `sqlglot>=25` → `sqlglot>=30`.

**Tests (modified):**
- `tests/test_smoke.py` — add direct unit tests for `to_dialect` (strict raise +
  mappings) beside the `create_backend` tests.
- `tests/verification/test_connection.py` — update the `probe_error` fixture
  literal (line 93) to the enumerated message.
- `tests/test_count_tools.py` — parse-error prefix assertion (line 215).
- `tests/test_validation_tools.py` — parse-error prefix assertions (lines 193, 232).
- `tests/test_validation_tools_multitarget.py` — parse-error prefix assertion (line 147).

No files or folders are created.

## Steps (one commit each)

1. **`step_1.md`** — Move `to_dialect` to `backends/base.py`, make it strict,
   enumerated message on both functions; move the three imports; update utils
   docstring/`__all__`; update the `to_dialect` unit tests and the
   `test_connection.py` fixture literal.
2. **`step_2.md`** — Dialect-first parse-error verdict in `basic_preflight`;
   update the four parse-error assertions.
3. **`step_3.md`** — Bump the sqlglot floor to `>=30`.

Each step ends with all gates green: `run_pylint_check`, `run_pytest_check`,
`run_mypy_check`, plus `run_lint_imports_check` and `run_ruff_check` (DOC).
