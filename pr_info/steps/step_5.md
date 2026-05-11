# Step 5 — Convert `register_builtin_tools` to `SchemaTools` class

## LLM Prompt

> Read `pr_info/steps/summary.md`, then implement Step 5 from
> `pr_info/steps/step_5.md`: convert the function
> `schema_tools.register_builtin_tools` into a class
> `SchemaTools(backend, backend_name)` with a `register(mcp)` method (mirrors
> the future `QueryTools` shape). Update `server.py` to instantiate the class.
> Pass `truncation_hint="Use filter to narrow."` from the schema tools call
> to the builder so the existing message text is preserved through the
> revised `format_rows` signature. Use TDD. MCP tools only. Run pylint,
> mypy, pytest, lint-imports, tach. One commit when all pass.

## WHERE

- `src/mcp_tools_sql/schema_tools.py` — convert function → class
- `src/mcp_tools_sql/server.py` — `_register_builtin_tools` instantiates
  `SchemaTools`
- `src/mcp_tools_sql/tool_builder.py` — accept and pass through
  `truncation_hint` to `format_rows`
- `tests/test_schema_tools.py` — adapt the `_make_mcp_with_tools` helper
- `tests/test_formatting.py` — drop/rewrite the assertion in
  `test_truncation_message_text` (default-call now yields no
  `"Use filter to narrow"` suffix)
- `tests/test_server.py` — verify built-in tools still register

## WHAT

```python
# src/mcp_tools_sql/schema_tools.py
class SchemaTools:
    def __init__(
        self,
        backend: DatabaseBackend,
        backend_name: str,
    ) -> None:
        self._backend = backend
        self._backend_name = backend_name

    def register(self, mcp: FastMCP) -> None:
        for name, config in load_default_queries().items():
            fn = build_tool_fn(
                name,
                config,
                self._backend,
                self._backend_name,
                truncation_hint="Use filter to narrow.",
            )
            mcp.add_tool(fn)
```

`build_tool_fn` gains a `truncation_hint: str = ""` keyword-only parameter
that flows into the `format_rows` call inside the closure.

Tighten `format_rows`'s `truncation_hint` default to `""` in this commit
since every caller now passes it explicitly; update the affected existing
assertion in `tests/test_formatting.py::test_truncation_message_text`
(which currently asserts `'Use filter to narrow' in result` against a
default call) — drop or rewrite that assertion since the default
`truncation_hint` is now `''`. The equivalent assertion in
`tests/test_schema_tools.py::TestSchemaToolsTruncation.test_wide_table_truncation`
(line ~216) is routed through `SchemaTools`, which still passes
`truncation_hint="Use filter to narrow."`, so it remains valid and
unchanged.

## HOW

- `load_default_queries()` stays a module-level function (used by `verify`
  and by `SchemaTools.register`).
- `register_builtin_tools()` is removed (hard rename per issue's clean-break
  policy). `server._register_builtin_tools` is updated in the same commit.
- Built-in tools keep bare names (no `query_` prefix).
- Schema-tools' truncation message text is identical to today's: the hint
  string is the same.

## ALGORITHM

```
SchemaTools.register(mcp):
    queries = load_default_queries()
    for name, cfg in queries.items():
        fn = build_tool_fn(name, cfg, backend, backend_name,
                           truncation_hint="Use filter to narrow.")
        mcp.add_tool(fn)
```

## DATA

- No protocol changes for built-in tools.
- `build_tool_fn` returns `Callable[..., Any]`; signature unchanged from
  Step 4 except for the new `truncation_hint` keyword-only parameter.

## TDD Tests

1. `tests/test_schema_tools.py` — replace direct
   `register_builtin_tools(mcp, backend, "sqlite")` calls in
   `_make_mcp_with_tools` with
   `SchemaTools(backend, "sqlite").register(mcp)`. All existing
   integration tests must pass.
2. `tests/test_server.py` — existing startup smoke test continues to pass
   (server still registers four built-in tools).
3. New: `tests/test_schema_tools.py::test_truncation_hint_preserved` —
   trigger truncation; assert the string `"Use filter to narrow"` appears
   (regression guard for the hint plumbing).
4. New: `tests/test_formatting.py::test_truncation_hint_default_is_empty` —
   call `format_rows` with no `truncation_hint` argument over enough rows
   to trigger truncation; assert the suffix line ends with `"rows."` and
   does NOT contain the legacy schema-specific phrase
   `"Use filter to narrow"`.

## Verification

- pylint, mypy, pytest, lint-imports, tach

## Commit

One commit.
