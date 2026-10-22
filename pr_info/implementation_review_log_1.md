# Implementation Review Log — Run 1

**Branch**: `feat/config-help-and-docs` (no linked issue)
**Scope**: Config/CLI documentation cleanup; key config docs reachable from the CLI
(`help config`) so an LLM can configure the server via the CLI alone; no new
commands. Includes the pyproject `[tool.mcp-tools-sql]` discovery fix and the
lint-config fixes for optional backends.

## Round 1 — 2026-10-22
**Findings**:
- C1: `QueryParamConfig.name` is required; the query examples in `help config` and docs/configuration.md fail validation; drift guard misses it.
- C2: docs/configuration.md claims every `backends` override is read-only-gated at registration; only the pinned backend's SQL is (verify checks all).
- S1: relative SQLite `path` resolves from the client's cwd; docs only warn about `--config`.
- S2: postgresql documented as failing "when connecting"; it fails at startup (registration).
- S3: `register_all()` ValueError in `tool` gives a traceback, not the hint.
- S4: drift-guard regex matches incidental prose.
- S5: `--log-level` help still says "OUTPUT for init/verify".
- S6: malformed unrelated pyproject.toml now blocks discovery.
- S7: `databases` row tagged mssql-only; postgresql uses it too.

**Decisions**:
- C1 accept — derive `name` from the TOML key (model validator); test the guide's examples by loading them.
- C2, S1, S2 accept — documentation accuracy is the point of this branch.
- S3 skip — pre-existing behaviour, out of scope.
- S4 accept — bounded, and C1 shows the gap.
- S5 accept — trivial; aligns help text with docs.
- S6 skip — defensible, speculative.
- S7 skip — postgresql is documented as unimplemented.

**Changes**:
- models.py: `QueryParamConfig.name` defaults to "" and is filled from the TOML key by a `QueryConfig` before-validator; test added.
- help_config.py: TOML examples extracted to `DATABASE_CONFIG_EXAMPLE` / `QUERY_CONFIG_EXAMPLE`, embedded via `textwrap.indent`; tests load and validate both; MCP-client paragraph notes absolute sqlite `path`.
- test_help_config.py: drift guard only counts keys listed as keys (indented key lists + table headers); `QueryParamConfig.name` excluded with reason.
- docs: read-only gate wording (pinned backend at registration, all overrides in verify); PostgreSQL fails once a configured query/update targets it (built-ins on first call); absolute sqlite path advice.
- main.py: `--log-level` help says "OUTPUT otherwise".
**Status**: committed

## Round 2 — 2026-10-22
**Findings**:
- Explicit param `name` differing from its key is kept; tool exposes the wrong kwarg and `:key` stays unbound at runtime (verify/authoring use the key).
- Drift-guard header regex also matches headers inside the embedded examples, masking removed reference rows.
- `DatabaseSpec` (table form of `databases`) not covered by the drift guard.
- Guide says built-ins gain connection/database params with >1 target; `connection` only appears with >1 connection.
- `read_query_config_data` filename check is case-sensitive.
- Code-built `QueryParamConfig` can now have an empty name.

**Decisions**:
- Param name: accept — always use the key (as authoring.py does); test.
- Header regex: accept — scan the guide without the examples.
- DatabaseSpec: accept — trivial.
- Guide parameter claim: accept — documentation accuracy.
- Case-sensitive filename: skip — edge case, speculative.
- Empty name in code: skip — speculative; only caller sets it.

**Changes**:
- models.py: param `name` always set from its TOML key; test for an explicit mismatching name.
- test_help_config.py: key scan runs on the guide with both examples removed; `DatabaseSpec` covered (`name` excluded as the table key).
- help_config.py: built-ins gain `database` with >1 target, `connection` with >1 connection; `read_databases` with >1 target.
**Status**: committed

## Round 3 — 2026-10-22
**Findings**:
- docs/configuration.md understates which built-ins gain `connection`/`database` (summarize_columns, and `connection` on non-schema built-ins, missing).
- docs/configuration.md says any other `backends` key warns; `pyodbc` is accepted as an alias of `mssql`.

**Decisions**:
- Both accept — documentation accuracy is the point of this branch; trivial edits.

**Changes**:
- docs/configuration.md: every built-in tool gains `connection` (>1 connection) and `database` (>1 target); built-ins are never pinned; `pyodbc` noted as an `mssql` alias for `backends` keys.
**Status**: committed

## Round 4 — 2026-10-22
**Findings**: none material (a duplicated `#exit-codes` anchor in docs/cli.md resolves to the intended section today).
**Decisions**: no changes.
**Changes**: none.
**Status**: no changes needed

## Final Status
- Rounds: 4 (3 with changes, 1 clean).
- Review commits: `f3b43c7` (param name from key, loadable guide), `62cd941` (key wins over explicit name, stricter drift guard), `c381609` (target-param and backend-key docs), plus a vulture whitelist entry for the new pydantic validator.
- vulture: clean after whitelisting `_param_names_from_keys` (pydantic-invoked).
- lint-imports: 2 contracts kept, 0 broken.
- Skipped by decision: `tool` traceback on `register_all()` ValueError (pre-existing); malformed unrelated pyproject.toml surfacing in discovery; `databases` tagged mssql-only; case-sensitive `pyproject.toml` name check; empty name on code-built `QueryParamConfig`.
- Note: `pr_info/` must be removed before opening a PR (CI `check-forbidden-folders`).
