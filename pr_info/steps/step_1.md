# Step 1 — Add `truncation_hint` parameter to `format_rows`

## LLM Prompt

> Read `pr_info/steps/summary.md` for overall scope, then implement Step 1 from
> `pr_info/steps/step_1.md`: extend `format_rows()` to accept a `truncation_hint`
> parameter. Follow TDD: write the new tests first, then change the function.
> Use only MCP tools per `.claude/CLAUDE.md`. After every edit run pylint,
> mypy, and pytest (parallel + integration exclusions); all must pass before
> a single commit.

## WHERE

- `src/mcp_tools_sql/formatting.py` — modify
- `tests/test_formatting.py` — extend

## WHAT

```python
def format_rows(
    rows: list[dict[str, Any]],
    max_rows: int = 100,
    truncation_hint: str = "Use filter to narrow.",
) -> str:
    ...
```

## HOW

- Default value preserves the current schema-tools message so existing
  tests and callers stay green this step.
- Future steps (Step 4 `tool_builder.build_tool_fn`) pass the hint explicitly.
- Empty hint produces only the count line, no trailing message.

## ALGORITHM

```
if not rows:
    return "No results found."
table = tabulate(rows[:max_rows], headers="keys", tablefmt="simple")
if total > max_rows:
    suffix = f" {truncation_hint}" if truncation_hint else ""
    table += f"\n\nShowing {max_rows} of {total} rows.{suffix}"
return table
```

## DATA

- Return type unchanged: `str`.
- Truncation suffix format: `"Showing N of M rows."` followed by an optional
  space + hint text.

## TDD Tests (add to `tests/test_formatting.py`)

1. `test_truncation_with_custom_hint` — pass `truncation_hint="Refine query."`;
   assert `"Refine query."` appears, `"Use filter to narrow"` does not.
2. `test_truncation_with_empty_hint` — pass `truncation_hint=""`; assert the
   line ends with `"rows."` and contains no extra suffix.
3. Existing `test_truncation_message_text` keeps passing (default behaviour).

## Verification

- `mcp__tools-py__run_pylint_check`
- `mcp__tools-py__run_mypy_check`
- `mcp__tools-py__run_pytest_check(extra_args=["-n", "auto", "-m", "not git_integration and not claude_cli_integration and not claude_api_integration and not formatter_integration and not github_integration and not langchain_integration"])`

## Commit

One commit covering tests + implementation + all checks passing.
