# Issue #5 — Dynamic SELECT Tool Registration

Each configured SELECT query in `mcp-tools-sql.toml` becomes an MCP tool at server
startup. Extracts the proven dynamic-registration pattern from `schema_tools.py`
into a shared `tool_builder` layer, generalizes the post-query filter, and adds
`max_rows_default` / `max_rows_hard` semantics.

Reference: GitHub issue #5 (milestone M2). Architecture: `docs/architecture/architecture.md`.

---

## Architectural / Design Changes

1. **New `tool_builder` layer.** Sits between the tool-implementation layer
   (`schema_tools | query_tools | update_tools | validation_tools`) and the
   infrastructure layer (`backends | formatting | tool_logging`). Houses
   `extract_sql_params`, `_apply_filter` (column-parameterized), and the
   `build_tool_fn` closure factory. Enforced in `.importlinter` and `tach.toml`.

2. **Class-everywhere tool registration.** `register_builtin_tools()` becomes
   a `SchemaTools(backend, backend_name).register(mcp)` class; the new
   `QueryTools(backend, queries, backend_name).register(mcp)` mirrors it.
   Same shape opens the door to future hot-reload and dynamic re-registration.

3. **Two-value `max_rows` semantics on `QueryConfig`.**
   - `max_rows_default: int` — soft default the LLM can override (replaces
     today's `max_rows`, hard rename, no alias).
   - `max_rows_hard: int` — ceiling; defaults to `max_rows_default` via Pydantic
     `model_validator(mode='after')`. When the LLM passes a value above the
     ceiling, the tool clamps silently and appends a note in the result text.

4. **Generalized post-query filter.** `_apply_filter` is parameterized by
   column name. New `QueryConfig.filter_column: str` (default `""`). When set,
   the dynamically-built tool exposes an optional `<filter_column>_filter`
   parameter (e.g. `name_filter`, `family_name_filter`). Replaces the
   schema-tools-only hardcoded `name`/`filter` mechanism.

5. **Implicit `max_rows` and `<col>_filter` parameters.** They are no longer
   declared in TOML `params` blocks; the builder injects them based on the
   `QueryConfig` shape. The TOML `params` section is now strictly user-defined
   query parameters.

6. **`format_rows` accepts `truncation_hint: str`.** Each caller passes a
   context-appropriate suffix (`"Use filter to narrow."` for schema tools,
   `"Refine your query parameters or increase max_rows."` for query tools).

7. **Strict tool-name validation.** Configured query names must match
   `^[a-zA-Z_][a-zA-Z0-9_]*$`. Tools register under `query_<name>`. Empty
   `queries` dict is a no-op.

---

## Files Created

| Path | Purpose |
|------|---------|
| `src/mcp_tools_sql/tool_builder.py` | Shared dynamic-registration helpers |
| `tests/test_tool_builder.py` | Unit tests for `extract_sql_params`, `_apply_filter` |
| `tests/test_query_tools.py` | End-to-end tests for `QueryTools` class |
| `pr_info/steps/summary.md` | This file |
| `pr_info/steps/step_1.md` … `step_6.md` | Per-step implementation specs |

## Files Modified

| Path | Change |
|------|--------|
| `src/mcp_tools_sql/formatting.py` | Add `truncation_hint` parameter |
| `src/mcp_tools_sql/config/models.py` | Rename `max_rows`; add `max_rows_hard`, `filter_column`, validator |
| `src/mcp_tools_sql/default_queries.toml` | Rename field; replace `params.filter` with `filter_column`; drop redundant `params.max_rows` |
| `src/mcp_tools_sql/schema_tools.py` | Move helpers out; convert to `SchemaTools` class |
| `src/mcp_tools_sql/query_tools.py` | Replace stub with `QueryTools` class |
| `src/mcp_tools_sql/server.py` | Use `SchemaTools` and `QueryTools` classes |
| `src/mcp_tools_sql/cli/commands/verify.py` | Update import + field-name references |
| `src/mcp_tools_sql/cli/commands/init.py` | Rename commented `max_rows` to `max_rows_default` in user-facing TOML template |
| `docs/cli.md` | Update verify-behavior text and example output for `max_rows` → `max_rows_default` |
| `mcp-tools-sql.md` | Global `max_rows` → `max_rows_default` rename in root brainstorm doc (TOML examples, prose, verify mockups, future-API signature) |
| `.importlinter` | Add `tool_builder` layer |
| `tach.toml` | Add `mcp_tools_sql.tool_builder` module + dependencies |
| `tests/test_formatting.py` | Tests for `truncation_hint` |
| `tests/test_schema_tools.py` | Update for `SchemaTools` class; remove moved unit tests |
| `tests/test_default_queries.py` | Update for renamed field, `filter_column` |
| `tests/config/test_models.py` | Tests for new fields + validator |
| `tests/cli/test_verify.py` | Adjust field-name references |
| `pr_info/TASK_TRACKER.md` | List the 6 steps |

---

## Steps

1. [step_1.md](step_1.md) — Add `truncation_hint` parameter to `format_rows`
2. [step_2.md](step_2.md) — Rename `max_rows` → `max_rows_default`; add `max_rows_hard` with clamp
3. [step_3.md](step_3.md) — Create `tool_builder.py`; extract helpers; add layer
4. [step_4.md](step_4.md) — Add `filter_column`; auto-inject `max_rows` and `<col>_filter` params
5. [step_5.md](step_5.md) — Convert `register_builtin_tools` to `SchemaTools` class
6. [step_6.md](step_6.md) — Implement `QueryTools` class; wire into `server.py`

Each step is one commit (tests + implementation + all checks passing).

---

## Out of Scope

- MSSQL backend remains a stub; tests exercise SQLite only.
- No SQL-level validation at registration (verify command, issue #9, owns that).
- No `update_tools` / `validation_tools` changes.
