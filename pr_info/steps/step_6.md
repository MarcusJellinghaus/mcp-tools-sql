# Step 6 — Implement `QueryTools` class; wire into `server.py`

## LLM Prompt

> Read `pr_info/steps/summary.md`, then implement Step 6 from
> `pr_info/steps/step_6.md`: replace the `QueryTools` stub with a class that
> registers configured SELECT queries as MCP tools named `query_<name>`,
> validates names against `^[a-zA-Z_][a-zA-Z0-9_]*$`, treats an empty queries
> dict as a no-op, and passes a query-tools-specific truncation hint. Wire
> it into `ToolServer._register_configured_tools`. Add the comprehensive
> test suite from the issue. Use TDD. MCP tools only. Run pylint, mypy,
> pytest, lint-imports, tach. One commit when all pass.

## WHERE

- `src/mcp_tools_sql/query_tools.py` — replace stub
- `src/mcp_tools_sql/server.py` — instantiate `QueryTools` in
  `_register_configured_tools`
- `tests/test_query_tools.py` — **create** (full coverage)
- `tests/test_server.py` — add an integration test

## WHAT

```python
# src/mcp_tools_sql/query_tools.py
class QueryTools:
    _NAME_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")

    def __init__(
        self,
        backend: DatabaseBackend,
        queries: dict[str, QueryConfig],
        backend_name: str,
    ) -> None:
        self._backend = backend
        self._queries = queries
        self._backend_name = backend_name

    def register(self, mcp: FastMCP) -> None:
        for name, config in self._queries.items():
            if not self._NAME_RE.match(name):
                raise ValueError(
                    f"Invalid query name {name!r}: must match "
                    f"{self._NAME_RE.pattern}"
                )
            fn = build_tool_fn(
                name,
                config,
                self._backend,
                self._backend_name,
                truncation_hint=(
                    "Refine your query parameters or increase max_rows."
                ),
            )
            mcp.add_tool(
                fn,
                name=f"query_{name}",
                description=config.description,
            )
```

`server.ToolServer._register_configured_tools`:

```python
def _register_configured_tools(self) -> None:
    QueryTools(
        self._backend, self._config.queries, self._backend_name
    ).register(self._mcp)
```

## HOW

- Empty `self._queries` → loop body never executes → registration is a no-op.
- Name regex validated before calling `build_tool_fn`. Closure `__name__` is
  set inside the builder; the prefixed name passed to `mcp.add_tool` is what
  appears to the LLM.
- `build_tool_fn` already provides parameterized SQL execution, max_rows
  clamp + note, optional `<col>_filter` injection, and forgiving kwarg
  stripping (Steps 2–4). `QueryTools` only adds: name validation, prefix,
  and the description override.
- The truncation hint differs from schema tools: schema tools tell the LLM
  to use `filter`; query tools tell it to refine query parameters or raise
  `max_rows`.

## ALGORITHM

```
QueryTools.register(mcp):
    for name, cfg in self._queries.items():
        if not _NAME_RE.match(name):
            raise ValueError(...)
        fn = build_tool_fn(name, cfg, backend, backend_name,
                           truncation_hint="Refine your query ...")
        mcp.add_tool(fn, name=f"query_{name}", description=cfg.description)
```

## DATA

- Tool names registered as `query_<name>` (e.g. `query_customers_by_country`).
- Description sourced from `QueryConfig.description`.
- Result text: standard `format_rows` output, optionally followed by a
  `\n\nRequested max_rows=...` note when clamped.

## TDD Tests (`tests/test_query_tools.py`)

Cover every item from issue #5's Tests section:

1. **Empty queries dict** — `QueryTools(backend, {}, "sqlite").register(mcp)`
   adds zero tools.
2. **Tool name prefix** — register `{"customers": ...}`; assert
   `"query_customers"` is in `list_tools()` and `"customers"` is not.
3. **Invalid tool name** — `{"123-bad": ...}` raises `ValueError` at
   registration with a clear message.
4. **JSON schema generation** — register a query with `int` + `str` +
   optional `float` params; assert the FastMCP-generated input schema has
   the right `type`/`required` entries and includes the implicit `max_rows`.
5. **SQLite integration: register + call** — round-trip via
   `create_connected_server_and_client_session` with the `sqlite_db` fixture.
6. **Parameterized queries (int/string/optional)** — verify each type binds
   correctly through `backend.execute_query`.
7. **`max_rows` truncation (existing behavior)** — assert
   `"Showing N of M rows"` text plus the query-tools hint
   `"Refine your query parameters or increase max_rows."`.
8. **`max_rows_hard` clamp** — request above the hard limit; assert the
   result is clamped and the note text appears.
9. **SQL injection prevention** — spy on `backend.execute_query`; assert
   parameters are passed as a `dict`, not interpolated into the SQL string.
10. **Missing required param** — call without it; assert the MCP error
    surfaces clearly (the framework raises; we just verify the path).
11. **Per-backend SQL override applied** — config with both default and
    `backends.sqlite` SQL; verify the SQLite override is what executes.
12. **Filter parameter** — config with `filter_column = "name"`; call
    with `name_filter="user_*"`; assert the result is filtered.
13. `test_query_tool_binds_datetime_param` — **datetime parameter
    binding**: a parameterized SELECT query with a `datetime` param.
    Assert (a) that an ISO 8601 string passed by the MCP caller is parsed
    by Pydantic to a `datetime.datetime`, and (b) that the parameter
    passed to the backend is a `datetime.datetime` (not `str`). Spy on
    `backend.execute_query` to capture the bound `dict`.

## TDD Tests (`tests/test_server.py`)

13. `test_configured_query_registered_as_tool` — write a
    `mcp-tools-sql.toml` with one `[queries.foo]` entry; build a
    `ToolServer` (without calling `mcp.run()`); list its registered tools
    and assert `query_foo` is present alongside the four built-in tools.

## Verification

- `mcp__tools-py__run_pylint_check`
- `mcp__tools-py__run_mypy_check`
- `mcp__tools-py__run_pytest_check(extra_args=["-n", "auto", "-m", "not git_integration and not claude_cli_integration and not claude_api_integration and not formatter_integration and not github_integration and not langchain_integration"])`
- `mcp__tools-py__run_lint_imports_check`
- `mcp__tools-py__run_tach_check`

## Commit

One commit. After it lands, issue #5 is complete.
