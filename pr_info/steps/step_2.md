# Step 2 — Move the leading-CTE gate to `utils`

**Goal:** make `count_records`' leading-CTE rejection reachable from `summarize`.
`count_tools` and `summarize` sit on the *same* line of `.importlinter`'s layer contract,
so they cannot import each other — the helper and its message must move down to `utils`.

**Depends on:** nothing. **Blocks:** step 3.

---

## WHERE

| File | Change |
|---|---|
| `src/mcp_tools_sql/utils/sql_placeholders.py` | Gains `has_leading_cte` + `LEADING_CTE_REJECTION`, both in `__all__` |
| `src/mcp_tools_sql/count_tools.py` | Deletes `_has_leading_cte` and `_LEADING_CTE_REJECTION`; imports them instead |
| `tests/test_sql_placeholders.py` | New direct unit tests |
| `tests/test_count_tools.py` | Update the one exact-message assertion (line ~237) |

## WHAT

```python
# utils/sql_placeholders.py
LEADING_CTE_REJECTION: str = (
    "CTE (WITH) queries aren't supported on SQL Server — "
    "the query can't be wrapped in a derived table."
)

def has_leading_cte(sql: str, dialect: str) -> bool: ...
```

## HOW

- Move the body of `count_tools._has_leading_cte` verbatim, including its comment about
  sqlglot keying the arg as `with_` in current versions and `with` in older ones, and the
  note that a T-SQL `WITH (NOLOCK)` table hint must not false-positive.
- Add both names to the module's `__all__` list (alphabetical, matching the existing style).
- `count_tools.py` imports them from `mcp_tools_sql.utils.sql_placeholders` alongside its
  existing `basic_preflight` / `build_count_query` / `read_only_violation` import, and
  returns `LEADING_CTE_REJECTION` where it returned the private constant.

### Message wording — deliberate one-clause change

The current text says "can't be counted … the count wrapper doesn't support them", which
is wrong when `summarize_columns` returns it. Decision 9 requires both tools to agree on
gate *and* message, so the shared constant is generalised to name the actual cause — both
tools wrap the source in a derived table (`AS count_sub` / `AS src`). This changes one
user-visible string of `count_records` and one test assertion; the gate's behaviour is
unchanged. Keep it to this single sentence.

## ALGORITHM

```
parsed = sqlglot.parse_one(sql, read=dialect)
with_arg = parsed.args.get("with_") or parsed.args.get("with")
return isinstance(with_arg, exp.With)
```

## DATA

`bool` — `True` only when the *statement-level* CTE arg is an `exp.With` node.

## TESTS (write first)

`tests/test_sql_placeholders.py`
1. `WITH c AS (SELECT 1 AS a) SELECT a FROM c` → `True` on both dialects.
2. Plain `SELECT * FROM t` → `False`.
3. T-SQL `SELECT * FROM t WITH (NOLOCK)` → `False` (the hint lives on the table node).
4. A CTE nested inside a subquery (`SELECT * FROM (WITH …) x` where the dialect parses it)
   → `False`: the gate is statement-level only.
5. `LEADING_CTE_REJECTION` is a non-empty string naming both "WITH" and "SQL Server".

`tests/test_count_tools.py`
6. The existing `test_mssql_leading_cte_rejected_without_execution` still passes with the
   updated expected text and still asserts `execute_readonly_query.assert_not_called()`.
7. The existing `WITH (NOLOCK)` test is untouched and still green.

## ACCEPTANCE

`count_records` behaviour identical apart from the one reworded sentence; `lint-imports`
and `tach check` still pass (no new edges — `utils` remains the bottom layer with no
upward imports); all three MCP checks green.

## LLM PROMPT

> Read `pr_info/steps/summary.md` and `pr_info/steps/step_2.md`.
>
> Implement step 2 only, test-first: move `_has_leading_cte` and its rejection message from
> `src/mcp_tools_sql/count_tools.py` into `src/mcp_tools_sql/utils/sql_placeholders.py` as
> the public `has_leading_cte` and `LEADING_CTE_REJECTION`, add both to `__all__`, and
> re-point `count_tools`.
>
> Apply the one-clause message generalisation described under HOW and update the single
> exact-text assertion in `tests/test_count_tools.py`. Do not change the gate's logic.
>
> Use MCP tools for all file and check operations. When done, run
> `mcp__tools-py__run_pylint_check`, `mcp__tools-py__run_pytest_check`
> (`extra_args=["-n", "auto"]`), and `mcp__tools-py__run_mypy_check`, and fix everything
> they report. Do not start step 3.
