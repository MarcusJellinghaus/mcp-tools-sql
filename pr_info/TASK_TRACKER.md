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

### Step 1: Prereq — dialect-aware placeholder translation
Detail: [step_1.md](./steps/step_1.md)
- [x] Implementation (tests + production code): `dialect` param on `translate_named_to_qmark` / `substitute_named_with_literals`, threaded from `mssql.py` and `validation_tools._explain`
- [x] Quality checks: pylint, pytest (`-n auto` + unit markers), mypy — fix all issues
- [x] Commit message prepared

### Step 2: Prereq — `build_count_query` strips `ORDER BY`
Detail: [step_2.md](./steps/step_2.md)
- [x] Implementation (tests + production code): drop statement-level `ORDER BY` before wrapping in `COUNT(*)` derived table
- [x] Quality checks: pylint, pytest (`-n auto` + unit markers), mypy — fix all issues
- [x] Commit message prepared

### Step 3: Config models — multi-database fields
Detail: [step_3.md](./steps/step_3.md)
- [x] Implementation (tests + production code): `DatabaseSpec`, `ConnectionConfig` databases/default_database/description + before/after validators, pinned `QueryConfig`/`UpdateConfig` fields
- [x] Quality checks: pylint, pytest (`-n auto` + unit markers), mypy — fix all issues
- [x] Commit message prepared

### Step 4: Config resolution — `resolve_targets` + Resolved* models
Detail: [step_4.md](./steps/step_4.md)
- [x] Implementation (tests + production code): `ResolvedTarget`/`ResolvedTargets` in models, `resolve_targets` in loader (keep `resolve_connection`)
- [x] Quality checks: pylint, pytest (`-n auto` + unit markers), mypy — fix all issues
- [x] Commit message prepared

### Step 5: `BackendRegistry`
Detail: [step_5.md](./steps/step_5.md)
- [x] Implementation (tests + production code): `backends/registry.py` with lazy `backend_for` cache + `close_all`; confirm lint-imports/tach boundaries hold
- [x] Quality checks: pylint, pytest (`-n auto` + unit markers), mypy — fix all issues
- [x] Commit message prepared

### Step 6: Server wiring (behaviour unchanged, single default target)
Detail: [step_6.md](./steps/step_6.md)
- [x] Implementation (tests + production code): `ToolServer`/`create_server` take targets + registry; `run_server` owns lifecycle (`close_all` in `finally`)
- [x] Quality checks: pylint, pytest (`-n auto` + unit markers), mypy — fix all issues
- [x] Commit message prepared

### Step 7: Pinned per-target backend for `query_*` / `update_*`
Detail: [step_7.md](./steps/step_7.md)
- [x] Implementation (tests + production code): `QueryTools`/`UpdateTools` take registry + targets, resolve pinned target at registration
- [x] Quality checks: pylint, pytest (`-n auto` + unit markers), mypy — fix all issues
- [x] Commit message prepared

### Step 8: `read_databases` tool (config-only, when >1 target)
Detail: [step_8.md](./steps/step_8.md)
- [x] Implementation (tests + production code): `build_read_databases_tool(targets)` + register in server only when `targets.is_multi`
- [x] Quality checks: pylint, pytest (`-n auto` + unit markers), mypy — fix all issues
- [x] Commit message prepared

### Step 9: Extract shared `execute_and_format` core (pure refactor)
Detail: [step_9.md](./steps/step_9.md)
- [x] Implementation (tests + production code): move execution+format tail out of `build_query_body` into `execute_and_format`; delegate
- [x] Quality checks: pylint, pytest (`-n auto` + unit markers), mypy — fix all issues
- [x] Commit message prepared

### Step 10: schema_tools — runtime single-target `connection`/`database` params
Detail: [step_10.md](./steps/step_10.md)
- [x] Implementation (tests + production code): `build_target_params` + `build_schema_body` (resolve one target, delegate to `execute_and_format`); `SchemaTools` takes registry + targets
- [x] Quality checks: pylint, pytest (`-n auto` + unit markers), mypy — fix all issues
- [x] Commit message prepared

### Step 11: schema_tools — `database="*"` fan-out + `_database` + footer
Detail: [step_11.md](./steps/step_11.md)
- [x] Implementation (tests + production code): `star` flag on `build_target_params`, fan-out branch in `build_schema_body`, `format_fanout_rows` in formatting
- [x] Quality checks: pylint, pytest (`-n auto` + unit markers), mypy — fix all issues
- [x] Commit message prepared

### Step 12: `validate_sql` / `count_records` — `database` param, per-call dialect
Detail: [step_12.md](./steps/step_12.md)
- [x] Implementation (tests + production code): `ValidationTools`/`CountTools` take registry + targets, resolve backend + dialect per call via `build_target_params(star=False)`
- [x] Quality checks: pylint, pytest (`-n auto` + unit markers), mypy — fix all issues
- [x] Commit message prepared

### Step 13: verify — static CONFIG cross-file checks
Detail: [step_13.md](./steps/step_13.md)
- [x] Implementation (tests + production code): cross-file rules 1/4/5/6 in `verification/config_files.py`, recompute `overall_ok`; adjust verify snapshot if ordering shifts
- [x] Quality checks: pylint, pytest (`-n auto` + unit markers), mypy — fix all issues
- [x] Commit message prepared

### Step 14: verify — per-pair CONNECTION probing + orchestrator registry migration
Detail: [step_14.md](./steps/step_14.md)
- [ ] Implementation (tests + production code): probe every `(connection, database)` pair via registry; delete dead `resolve_connection` / `_resolve_connection_for_verify`; M2 + snapshot stay byte-identical
- [ ] Quality checks: pylint, pytest (`-n auto` + unit markers), mypy — fix all issues
- [ ] Commit message prepared

### Step 15: verify — per-target M2 (QUERIES/UPDATES) + skip rows + snapshot
Detail: [step_15.md](./steps/step_15.md)
- [ ] Implementation (tests + production code): per-target EXPLAIN/skip in `verify_queries`/`verify_updates` via reachability map; regenerate verify snapshot fixture
- [ ] Quality checks: pylint, pytest (`-n auto` + unit markers), mypy — fix all issues
- [ ] Commit message prepared

### Step 16: `init` multi-connection template + docs
Detail: [step_16.md](./steps/step_16.md)
- [ ] Implementation (tests + production code): mssql/postgresql templates use `databases`/`default_database`; document two-axis model, fan-out, `read_databases`, pinned query fields, decision-26 security caveat
- [ ] Quality checks: pylint, pytest (`-n auto` + unit markers), mypy — fix all issues
- [ ] Commit message prepared

## Pull Request

- [ ] Address PR review feedback (resolve all comments)
- [ ] Write PR summary describing the multi-connection / multi-database feature
