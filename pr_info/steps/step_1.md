# Step 1 — Keyword-absorption guard + reworded rejection message

Read [summary.md](./summary.md) first, especially *"A deliberate exception to the
'prove, don't blocklist' philosophy"*.

Scope: `utils` only. No caller is wired up in this step.

## WHERE

- `src/mcp_tools_sql/utils/sql_placeholders.py`
- `tests/test_sql_placeholders.py`

## WHAT

```python
_ABSORBABLE_KEYWORDS: frozenset[str] = frozenset({
    "DELETE", "INSERT", "UPDATE", "MERGE", "CREATE", "DROP",
    "ALTER", "TRUNCATE", "EXEC", "EXECUTE", "GRANT", "REVOKE",
})


def keyword_absorption_violation(sql: str, dialect: str) -> str | None:
    """Return a rejection message when a statement keyword was parsed as an identifier."""
```

Place it immediately after `read_only_violation` (it is that function's sibling)
and add `"keyword_absorption_violation"` to `__all__`.

Also reword `read_only_violation`'s root rejection (currently
`sql_placeholders.py:373`):

```python
# before
return "Not read-only. Only SELECT/WITH/VALUES queries can be counted."
# after
return "Not read-only. Only SELECT/WITH/VALUES statements are permitted."
```

Nothing else in `read_only_violation` changes — its verdict logic must stay
identical so `count_records` behaviour is untouched (decision 10).

## HOW

- Same imports the module already has: `sqlglot`, `sqlglot.exp as exp`. No new
  dependency.
- `keyword_absorption_violation` raises `ParseError` on unparseable SQL, exactly
  like its sibling. It does not catch — step 2's shared wrapper owns that.
- The docstring must state that this is a deliberate exception to the
  "positively proves … rather than blocklisting keywords" philosophy stated in
  this module, justified only as a second layer *on top of* the AST proof and
  never as a replacement. Explain the mechanism: sqlglot consumes a
  separator-less batch whole and reinterprets the write keyword as a column
  alias, so the AST proof sees a clean `SELECT`.

## ALGORITHM

```
parse sql under dialect (parse_one)
for each exp.Identifier node in the tree:
    if the node is quoted (args["quoted"] truthy): skip  # a genuine column
    if identifier name, upper-cased, is in _ABSORBABLE_KEYWORDS:
        return "Not read-only. '<NAME>' appears where an identifier was expected; ..."
return None
```

## DATA

`str | None` — a rejection message, or `None` when clean. Same contract as
`read_only_violation`, so the two compose by `or`.

## TESTS (write first)

Add to `tests/test_sql_placeholders.py`. Parametrize the tables rather than
writing one function per case.

**Rejected — the measured slipping shapes** (all under both `sqlite` and `tsql`
where they parse). The core case:

```
SELECT 1
DELETE FROM t
```

which sqlglot renders as `SELECT 1 AS DELETE FROM t`. Assert
`keyword_absorption_violation(...) is not None`, and assert in a separate test
that `read_only_violation` returns `None` for it — that asymmetry is the reason
this function exists, and the test documents it.

**Accepted — no false rejection:**

- `SELECT 'DELETE' AS action` (string literal, not an identifier)
- `SELECT create_date` (keyword is a prefix, not the whole name)
- `SELECT [Update]` (bracket-quoted, `tsql`)
- `SELECT 1 AS "delete"` (double-quoted)
- The four bundled SQLite schema queries, including
  `pragma_table_info(:table)` and `pragma_foreign_key_list(:table)`
- Representative T-SQL reads: `WITH (NOLOCK)`, `OPENJSON(...) WITH (...)`,
  a table-valued function, `CROSS APPLY`, `FOR XML PATH`,
  `OPTION (RECOMPILE)`, a multi-CTE query, `UNION ALL`, a scalar subquery,
  an `INFORMATION_SCHEMA` join

**Message reword:** the existing `tests/test_sql_placeholders.py:362` asserts
only the `"SELECT/WITH/VALUES"` fragment, so it must still pass unchanged. Do
not add an assertion on the new tail — that just re-pins a string.

## LLM PROMPT

> Read `pr_info/steps/summary.md` and `pr_info/steps/step_1.md`.
>
> Implement step 1 test-first: add the parametrized accept/reject tests for
> `keyword_absorption_violation` to `tests/test_sql_placeholders.py`, watch them
> fail, then add `keyword_absorption_violation` and `_ABSORBABLE_KEYWORDS` to
> `src/mcp_tools_sql/utils/sql_placeholders.py` and reword
> `read_only_violation`'s root rejection message per decision 15.
>
> Do not change `read_only_violation`'s verdict logic and do not wire any caller
> — that is step 2.
>
> Then run `run_format_code`, `run_pylint_check`, `run_pytest_check` with
> `extra_args: ["-n", "auto"]`, `run_mypy_check`, `run_tach_check` and
> `run_lint_imports_check`. All must pass. Commit as one commit.
