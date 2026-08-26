# Step 5 — Wire the `sql=` parameter end to end

**Goal:** the user-visible feature. `summarize_columns(sql=...)` profiles an arbitrary
read-only SELECT, with `where` applied outside the source, call-level notes in a footer,
and the LOB hint on the probed path. After this step the issue is functionally delivered on
both backends; step 6 only upgrades T-SQL type fidelity.

**Depends on:** step 4. **Blocks:** step 6.

---

## WHERE

| File | Change |
|---|---|
| `src/mcp_tools_sql/summarize/source.py` | `build_query_source` |
| `src/mcp_tools_sql/summarize/tools.py` | `sql` param, mutual exclusivity, source dispatch, `_DESCRIPTION`, log field, LOB hint |
| `docs/architecture/architecture.md` | `summarize` package row; the new backend method |
| `mcp-tools-sql.md` | Updated `summarize_columns` signature line (~216) |
| `tests/summarize/test_tools.py` | End-to-end SQLite tests + MagicMock T-SQL tests |

## WHAT

```python
# summarize/source.py
def build_query_source(
    backend: DatabaseBackend, sql: str, params: dict[str, Any] | None, dialect: str
) -> Source | str: ...
```

```python
# summarize/tools.py
SOURCE_CHOICE_MESSAGE: str = "Supply either schema+table or sql, not both."
LOB_HINT: str = (
    " This can happen when a text/ntext/image column is profiled from a sampled type. "
    "Exclude it with columns=, or CAST(... AS nvarchar(max)) inside the source query."
)

async def core(
    schema: str | None = None, table: str | None = None, sql: str | None = None,
    columns: list[str] | None = None, where: str | None = None,
    params: dict[str, Any] | None = None, n: int = 20,
    *, connection: str | None = None, database: str | None = None,
) -> str: ...
```

`_base_summarize_params()` gains `sql` (third position, `Optional[str]`, default `None`)
and makes `schema` / `table` `Optional[str]` with default `None`. Positional order is
cosmetic — `build_tool_fn` calls the body with keyword arguments only.

## HOW

- `build_query_source` composes step 3: `validate_source` → `probe_columns` → `Source(ref,
  label=None, metas, notes=[*source_notes, TYPES_PROBED_NOTE], types_probed=True)`.
- Mutual exclusivity: one constant for both "both given" and "neither given" (and for a
  half-supplied `schema` without `table`) — one string, one-turn recovery.
- `log_tool_call(..., sql=sql or where or "")`: on the `sql` path the source is the field
  worth logging, not the predicate.
- The source build stays **inside** the `try` step 4 widened. `build_query_source` runs the
  user's SELECT as a probe, so an unresolvable source (nonexistent table, ambiguous column,
  type error) reaches the backend and raises; that error is the only report the caller gets
  — `table_not_found_message` has no `sql`-path analogue — so it must come back as a
  returned string, not as an exception escaping the tool.
- LOB hint: at the existing `except _INVALID_SQL_EXC` tail in `core`, append `LOB_HINT`
  when `source.types_probed` is set. No new try/except and no error-code sniffing — under
  the probe a `text`/`ntext`/`image` column types as `str`, so the scalar pass emits
  `LEN`/`MIN`/`MAX` and SQL Server rejects the whole statement.
- `_DESCRIPTION` additions, three sentences, kept tight because it ships on every request:
  1. `Profile a table (schema+table) or an arbitrary read-only SELECT (sql) — supply one, not both.`
  2. `With sql, the where predicate is applied OUTSIDE the query, so it can filter computed and aggregated columns.`
  3. `The source is executed once per profiled column plus three times, so narrow with columns= on expensive queries.`
- Zero-row sources: column resolution deliberately stays **before** the count — it is what
  rejects a bad source. Note this in the `_run` docstring.

## ALGORITHM

```
core(...):
    if bool(sql) == bool(schema or table): return SOURCE_CHOICE_MESSAGE
    if sql is None and not (schema and table): return SOURCE_CHOICE_MESSAGE
    async with log_tool_call(...) as rec:
        built: Source | None = None                   # set before the try, read in it
        try:                                          # step 4's widened tail, unchanged
            built = build_query_source(backend, sql, params, dialect) if sql \
                    else build_table_source(backend, schema, table, dialect)
            if isinstance(built, str): return built
            predicate, err = validate_where(where, built.ref, params, dialect)
            if err: return err
            return _run(backend, rec, built, predicate, params, columns, n, dialect)
        except _INVALID_SQL_EXC as exc:
            probed = isinstance(built, Source) and built.types_probed
            return f"Invalid SQL. {type(exc).__name__}: {exc}" + (LOB_HINT if probed else "")
        except (KeyError, TypeError, ValueError) as exc: ...   # unchanged
        except RuntimeError as exc: ...                        # unchanged
        except Exception as exc: ...                           # unchanged
```

`build_query_source` **executes** the user's SELECT (the probe now, the DMF in step 6), so
it must sit inside this `try` — it is the single most likely place for a SQL error on the
new path, and per the issue an unresolvable source has no `table_not_found` analogue: the
backend error *is* the report. `built` is initialised to `None` first so the handler is
safe when the source build itself raised; a probe failure is not a LOB failure (the probe
is a bare `SELECT *`), so no hint is appended in that case.

## DATA

Return value is still a single formatted string. A `sql`-source call renders the normal
deep/triage body plus a trailing footer block holding, in order: `ORDER BY` stripped,
row-limited, types-probed, then the `n` clamp note if any.

## TESTS (write first)

End-to-end against `profiling_db` through `create_connected_server_and_client_session`
(reuse the existing `_client_for`; extend `_call_summarize` to accept `sql=`):

1. **Join** — self-join `profile_me` with aliased columns; per-column blocks render and the
   footer carries the types-probed note.
2. **Aggregate + outside `where`** — `sql="SELECT category, COUNT(*) AS orders FROM
   profile_me GROUP BY category"`, `where="orders > :min"`, `params={"min": 1}`: a
   `HAVING`-like filter through the existing `params` threading.
3. **`:name` inside the source** binds through the same `params` dict.
4. **`ORDER BY` stripped** — note present, call succeeds.
5. **Row-limited** — `LIMIT 3` keeps `ORDER BY`, emits the row-limited note, no strip note.
6. **Duplicate output columns** rejected with the aliasing hint (step 3's rule, reached
   through the tool).
7. **Zero-row source** → `The source query returned 0 rows.`
8. **`where` matches nothing** → `… (source has N rows).`
9. **Mutual exclusivity** — both given, neither given, `schema` without `table`: all return
   `SOURCE_CHOICE_MESSAGE`; nothing is executed.
10. **Not read-only** — `sql="DELETE FROM profile_me"` and a `VALUES` root are rejected
    before any execution.
10b. **Valid-but-unresolvable source** — `sql="SELECT * FROM no_such_table"` and
    `sql="SELECT id FROM profile_me a JOIN profile_me b ON a.id = b.id"` (ambiguous `id`)
    both parse and pass the read-only gate, then fail when the probe executes. Each must
    return a string starting `Invalid SQL.` and naming the underlying error; assert no
    exception escapes the tool call. This is the regression guard for keeping
    `build_query_source` inside `core`'s `try`.
11. **`columns=` narrowing** works against probed metadata (case-insensitively), and
    `columns=[]` / unknown names give the existing messages.
12. **Triage** — a >15-column source renders the triage table with the notes appended after
    its existing footers.
13. **Table path unchanged** — an existing `schema`/`table` test still returns byte-identical
    output (no stray footer).
14. **MagicMock T-SQL** — the rendered count / scalar / value-list SQL uses
    `FROM (…) AS src`; and a `pyodbc`-style error on a probed source returns the message
    with `LOB_HINT` appended.

## ACCEPTANCE

The issue's motivating example works on SQLite end to end; the table path is unchanged;
`tools.py` and `source.py` stay under 750 lines; all three MCP checks green; docs updated.

## LLM PROMPT

> Read `pr_info/steps/summary.md` and `pr_info/steps/step_5.md`.
>
> Implement step 5 only, test-first: add `build_query_source` to
> `src/mcp_tools_sql/summarize/source.py`, add the `sql` parameter and the
> mutual-exclusivity check to `summarize/tools.py`, append the call-level notes footer
> beside the existing clamp note, add the LOB hint at the existing `except` tail, and
> update `_DESCRIPTION`, `docs/architecture/architecture.md`, and the
> `summarize_columns` signature line in `mcp-tools-sql.md`.
>
> Keep `build_query_source` **inside** the `try` step 4 widened — it executes the user's
> SELECT as a probe, and a source that parses but fails at execution must come back as an
> `Invalid SQL.` string, not as an exception escaping the tool.
>
> Write the end-to-end tests listed under TESTS first. Test 10b guards the `try` placement
> and test 13 is a regression guard: the `schema`/`table` path must produce byte-identical
> output.
>
> Use MCP tools for all file and check operations. When done, run
> `mcp__tools-py__run_pylint_check`, `mcp__tools-py__run_pytest_check`
> (`extra_args=["-n", "auto"]`), and `mcp__tools-py__run_mypy_check`, and fix everything
> they report. Do not start step 6.
