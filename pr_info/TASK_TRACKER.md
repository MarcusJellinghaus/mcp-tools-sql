# Task Status Tracker

## Instructions for LLM

This tracks **Feature Implementation** consisting of multiple **Tasks**.

**Summary:** See [summary.md](./steps/summary.md) for implementation overview.

**How to update tasks:**
1. Change [ ] to [x] when implementation step is fully complete (code + checks pass)
2. Change [x] to [ ] if task needs to be reopened
3. Add brief notes in the linked detail files if needed
4. Keep it simple - just GitHub-style checkboxes

**Task format:**
- [x] = Task complete (code + all checks pass)
- [ ] = Task not complete
- Each task links to a detail file in steps/ folder

---

## Tasks

### Step 1: Parsing foundation — sqlparse → sqlglot + reimplement placeholder helpers

Detail: [step_1.md](./steps/step_1.md)

- [x] Implementation: swap `sqlparse`→`sqlglot` in `pyproject.toml` (remove sqlparse mypy override); reimplement `extract_param_names`, `translate_named_to_qmark`, `substitute_named_with_literals` on the sqlglot AST in `sql_placeholders.py`; confirm placeholder node type empirically; update `tests/test_sql_placeholders.py` (TDD) preserving intent + add `:name` round-trip and ordered multi-placeholder tests
- [x] Quality checks: pylint, pytest (unit subset), mypy — fix all issues
- [x] Commit message prepared

### Step 2: Shared preflight helpers + migrate `validate_sql` to sqlglot

Detail: [step_2.md](./steps/step_2.md)

- [x] Implementation: add `to_dialect`, `count_statements`, `first_statement_kind`, `basic_preflight`, and `ParseError` re-export to `sql_placeholders.py`; re-base `validate_sql._preflight` to delegate to `basic_preflight` + layer session-keyword check; remove local `_count_statements`/`_first_keyword`; add fail-closed parse contract; update `tests/test_validation_tools.py` (TDD)
- [x] Quality checks: pylint, pytest (unit subset), mypy — fix all issues
- [x] Commit message prepared

> **Step 2 notes:** pylint ✓, mypy ✓, and all `tests/test_validation_tools.py`
> tests pass. `extract_param_names`/`_statements` gained an optional `dialect`
> arg (kept the existing `:name` recognition for `count_records` reuse). The
> `DECLARE` pre-flight test now runs under the `tsql` dialect because `DECLARE`
> is invalid SQLite syntax under sqlglot.
>
> **Pre-existing (NOT from Step 2) failures observed in the full unit suite** —
> all caused by Step 1's sqlglot migration of `extract_param_names`, verified
> identical before/after this step's changes:
> - `tests/test_tool_builder.py::TestExtractSqlParams::test_multiple_params`
>   (`extract_sql_params` on the bare fragment `"WHERE a = :x AND b = :y"` now
>   raises `ParseError` — sqlglot cannot parse fragments).
> - `tests/verification/test_queries.py::test_verify_queries_detects_invalid_sql`
>   and `tests/cli/test_verify.py::test_verify_cli_queries_updates_snapshot`
>   (`extract_sql_params` on invalid SQL raises `ParseError`).
> - `tests/test_sql_placeholders.py` anonymous-`?` tests (sqlglot reports
>   `Placeholder.name == "?"` instead of `""`).
>
> These need a Step-1-level fix (out of this step's 3-file commit scope) and
> are surfaced here rather than silently absorbed.

### Step 3: `execute_readonly_query` backend seam (ABC + SQLite + MSSQL)

Detail: [step_3.md](./steps/step_3.md)

- [x] Implementation: add `execute_readonly_query` abstractmethod to `backends/base.py`; implement fresh `PRAGMA query_only=ON` per-call connection in `backends/sqlite.py`; delegate to `execute_query` in `backends/mssql.py`; write TDD tests in `tests/backends/test_sqlite.py` and `tests/backends/test_mssql.py`
- [x] Quality checks: pylint, pytest (unit subset), mypy — fix all issues
- [x] Commit message prepared

> **Step 3 notes:** pylint ✓, mypy ✓. New backend tests all pass
> (`tests/backends/test_sqlite.py` + `test_mssql.py`: 73 passed, 8 MSSQL
> integration skipped in CI). The 5 unit-subset failures observed in the full
> run are the same pre-existing Step-1-level sqlglot failures documented in the
> Step 2 notes (fragment/invalid-SQL `ParseError`, anonymous `?` name) — none
> touch the `backends/` files changed in this step.

### Step 4: Read-only AST gate + COUNT-wrap helpers (pure functions)

Detail: [step_4.md](./steps/step_4.md)

- [x] Implementation: add `read_only_violation(sql, dialect)` and `build_count_query(sql, dialect)` (plus `_WRITE_NODES`/`_READONLY_ROOTS`) to `sql_placeholders.py` via sqlglot AST inspection (reject write nodes, `SELECT…INTO`, non-read-only roots fail-closed); confirm root node set empirically; write TDD unit tests in `tests/test_sql_placeholders.py`
- [x] Quality checks: pylint, pytest (unit subset), mypy — fix all issues
- [x] Commit message prepared

> **Step 4 notes:** pylint ✓, mypy ✓. Read-only roots confirmed empirically via
> sqlglot spike: `SELECT`/`WITH…SELECT`/`SELECT…INTO` → `exp.Select`,
> `UNION` → `exp.Union`, `VALUES` → `exp.Values`; `PRAGMA` → `exp.Pragma` (used
> as the fail-closed non-root case). `build_count_query` builds the
> `exp.Subquery` derived table directly (not `inner.subquery(...)`) so `VALUES`
> roots — which are not `exp.Query` — also wrap uniformly. All 22 new
> `tests/test_sql_placeholders.py` cases (`TestReadOnlyViolation` +
> `TestBuildCountQuery`) pass.
>
> **Pre-existing (NOT from Step 4) failures** — the same Step-1-level
> anonymous-`?` cases documented in the Step 2/3 notes
> (`TestPlaceholderNodeSpike::test_anonymous_placeholder_has_empty_name`,
> `TestTranslateNamedToQmark::test_roundtrip_single_named_placeholder`): sqlglot
> reports `Placeholder.name == "?"` instead of `""`. Out of this step's
> 2-file commit scope; surfaced rather than silently absorbed.

### Step 5: `count_records` tool — module + registration + architecture config

Detail: [step_5.md](./steps/step_5.md)

- [x] Implementation: create `count_tools.py` with `CountTools` registering async `count_records(sql, params=None) -> str` (consume `basic_preflight`, `read_only_violation`, precise MSSQL leading-`WITH` rejection, `build_count_query` + `execute_readonly_query`, validate_sql exception mapping); register in `server._register_builtin_tools`; add `"count_records"` to `PROGRAMMATIC_BUILTIN_TOOLS`; add `count_tools` to `.importlinter` and `tach.toml`; write TDD tests in `tests/test_count_tools.py` and registration test in `tests/test_server.py`
- [x] Quality checks: pylint, pytest (unit subset), mypy, `run_lint_imports_check`, `run_tach_check` — fix all issues
- [x] Commit message prepared

> **Step 5 notes:** pylint ✓, mypy ✓, import-linter ✓ (2 contracts kept),
> tach ✓ (`[]`). All 28 tests in `tests/test_count_tools.py` +
> `tests/test_server.py` pass.
>
> **Empirical sqlglot finding:** the statement-level CTE arg is keyed
> `with_` (trailing underscore) in the installed sqlglot, not `with` as the
> step text assumed — confirmed via `Select.arg_types` and a parse spike
> (`WITH x AS (SELECT 1) SELECT * FROM x` → `args["with_"]` is `exp.With`;
> `SELECT * FROM t WITH (NOLOCK)` has **no** `With` node anywhere). The
> `_has_leading_cte` gate checks both `with_` and `with` keys to stay
> version-robust, and the `WITH (NOLOCK)` test confirms no false-positive.
>
> **Pre-existing (NOT from Step 5) failures** in the full unit subset — the
> same Step-1-level sqlglot issues documented in the Step 2/3/4 notes, all
> in files untouched by this step:
> - `tests/test_sql_placeholders.py` anonymous-`?` cases
>   (`name == "?"` not `""`).
> - `tests/test_tool_builder.py::TestExtractSqlParams::test_multiple_params`
>   (`extract_sql_params` on the bare fragment `WHERE a = :x AND b = :y`).
> - `tests/verification/test_queries.py::test_verify_queries_detects_invalid_sql`
>   and `tests/cli/test_verify.py::test_verify_cli_queries_updates_snapshot`
>   (`extract_sql_params` on invalid SQL raises `ParseError`).

---

## Pull Request

- [x] PR review: verify all steps complete, all quality checks pass, and changes align with [summary.md](./steps/summary.md)
- [ ] PR summary prepared (title + description covering the sqlparse→sqlglot migration and the new `count_records` tool)
