# Step 3 — Wire `log_tool_call` into built-in schema tools

## LLM prompt

> Read `pr_info/steps/summary.md` and then implement Step 3 in
> `pr_info/steps/step_3.md`. Step 2 must be merged. TDD: add the caplog test in
> `tests/test_schema_tools.py` first, then update `_build_tool_fn`. Run pylint +
> pytest + mypy + lint-imports + tach check. One commit at the end.

## Goal

Built-in schema tools emit one INFO line per call with the standard
`tool=<name> rows=<n> cols=<m> duration_ms=<k>` shape. No behavioural change to
tool output or signatures.

---

## WHERE

- `src/mcp_tools_sql/schema_tools.py` — modify `_build_tool_fn` only.
- `tests/test_schema_tools.py` — add one caplog test.
- `tach.toml` — extend `mcp_tools_sql.schema_tools` `depends_on` with
  `mcp_tools_sql.tool_logging`.

## WHAT

Modify the inner `_tool_fn` inside `_build_tool_fn` to wrap the body in
`log_tool_call`:

```python
async def _tool_fn(**kwargs: Any) -> str:
    max_rows: int = kwargs.pop("max_rows", config.max_rows)
    filter_pattern: str | None = kwargs.pop("filter", None)
    stripped = {k: v for k, v in kwargs.items() if k in sql_params}

    async with log_tool_call(name, stripped, sql=resolved_sql) as rec:
        rows = backend.execute_query(resolved_sql, stripped or None)
        rows = _apply_filter(rows, filter_pattern)
        rec.record(rows=len(rows), cols=len(rows[0]) if rows else 0)
        return format_rows(rows, max_rows)
```

## HOW

- `from mcp_tools_sql.tool_logging import log_tool_call` at module top.
- `record(...)` is called **after** filtering, **before** `format_rows(...)` so
  the count reflects what the user sees.
- `cols` = `len(rows[0])` when rows present, else `0`.
- `name` is the tool name being built (already in scope inside `_build_tool_fn`).
- `stripped` (the SQL-relevant params) is logged, not raw `kwargs`, to keep
  `max_rows` / `filter` out of the SQL params view.

## ALGORITHM

(See WHAT block above — the algorithm is the wrapping itself.)

## DATA

Same return type as today: `str` from `format_rows(...)`. No new public
attributes.

---

## Tests (TDD — write first)

Add to `tests/test_schema_tools.py` — reuse the existing `_make_mcp_with_tools`
helper, but bypass the FastMCP plumbing and call the registered async function
directly via the FastMCP tool registry:

```python
@pytest.mark.sqlite_integration
async def test_builtin_tool_logs_info_line(
    sqlite_db: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger="mcp_tools_sql.tool_logging")
    mcp = _make_mcp_with_tools(str(sqlite_db))
    # Locate the read_tables (or read_schemas) tool object and invoke its run fn.
    # Either via FastMCP's internal tool dict, or via
    # create_connected_server_and_client_session (already used in this file).
    ...
    info_records = [r for r in caplog.records if r.levelno == logging.INFO]
    assert any("tool=" in r.getMessage() and "duration_ms=" in r.getMessage()
               for r in info_records)
```

If invoking through FastMCP is awkward, the test can call `_build_tool_fn`
directly:

```python
fn = _build_tool_fn("read_tables", config, backend, "sqlite")
result = await fn()
```

## Architecture wiring

`tach.toml` — extend the module's deps:

```toml
[[modules]]
path = "mcp_tools_sql.schema_tools"
layer = "tool_implementation"
depends_on = [
    { path = "mcp_tools_sql.backends" },
    { path = "mcp_tools_sql.config" },
    { path = "mcp_tools_sql.formatting" },
    { path = "mcp_tools_sql.tool_logging" },   # added
    { path = "mcp_tools_sql.utils" },
]
```

(The other tool-implementation modules — `query_tools`, `update_tools`,
`validation_tools` — can also have `tool_logging` added preemptively in this
step, since #5 / #6 / #8 will need it. **Decision per KISS**: add only to
`schema_tools` here; the other modules pick it up when their issues land. Don't
expand scope.)

## Acceptance

- Three checks green; `lint-imports` and `tach check` green.
- One commit: `feat(schema_tools): emit per-call INFO log via log_tool_call`.
