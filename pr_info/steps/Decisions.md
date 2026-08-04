# Decisions

Decisions taken while refining the `summarize_columns` plan (issue #43).
Implementation not started at the time of writing.

## Review log 2 — findings applied to the plan (2026-08-04)

Source: completed plan review (`pr_info/plan_review_log_2.md`, continuing
`plan_review_log_1.md`). All 12 findings were applied to `pr_info/steps/`.

1. **Empty `columns=[]` fails the call.** An explicitly empty list is *not*
   "all columns": it produced no error, an empty profile set, and
   `build_scalar_sql([])` → `SELECT FROM "t"` → `Invalid SQL. OperationalError:
   near "FROM"`. Decision: reject it with `empty_columns_message` (same error
   class as the unknown-column error) **before** any data query, and give
   `render_summary`'s empty branch a concrete `NO_COLUMNS_TEXT` return instead
   of a literal `...`.
   (step_7.md, step_6.md)

2. **Param threading gets an end-to-end test.** The round-4 fix was spec-only;
   the existing coverage tests `validate_where` in isolation and a
   nothing-matching `where`, neither of which binds params through the scalar /
   value-list queries. Decision: add a `where` + `:name` + `params` test that
   matches rows. Also corrected the wording — the empty-filter *unfiltered*
   count is built with `predicate=None` and so carries no placeholders.
   (step_7.md)

3. **`None` distinct renders blank.** `COUNT(DISTINCT)` is never emitted for
   `other`/binary columns, so `ColumnProfile.distinct` is `None` for them even
   in an *ungated* triage, and tabulate would print `None`. Decision: blank it
   to `—` (the same convention as an absent min/max), regardless of the gate.
   (step_6.md)

4. **Explicit optional narrowing.** `distinct: int | None` and
   `values: list | None` were used unguarded; `run_mypy_check` runs `--strict`,
   so steps 5 and 7 would land red. Decision: specify the guards — early-return
   on a falsy `values`, and emit the remainder line / `of D` clause only inside
   `if p.distinct is not None`.
   (step_5.md)

5. **`values` annotation unified** to `list[tuple[Any, ...]] | None`
   (summary.md contradicted step 5 and its own trailing comment).
   (summary.md)

6. **`DISTINCT_GATE_ROWS: int = 1_000_000`** replaces the inline 1M literal,
   declared beside `TRIAGE_THRESHOLD`/`COLUMN_CAP`; the gate decision itself is
   tested, since `summary.md` lists it as an invariant that must hold.
   (step_6.md, step_7.md, summary.md)

7. **Tool description specified.** Both `build_tool_fn(..., doc)` and
   `mcp.add_tool(..., description=...)` require one. Decision: a module-level
   `_DESCRIPTION` mirroring `count_tools._DESCRIPTION`, explicitly advertising
   the `:name`-placeholder / `params` contract the issue requires. Also pinned
   the logging: `log_tool_call(..., sql=where or "")` (the user's raw predicate,
   not the derived multi-query SQL) plus an explicit
   `rec.record(rows=len(profiled), cols=1)` — without it the success log line
   reports `rows=0 cols=0`.
   (step_7.md)

8. **`clamp_n` clamps both directions**, into `[1, 50]`. `n=0` gave an empty
   list under a `top values:` header and `n<0` rendered `TOP -1`, which SQL
   Server rejects.
   (step_4.md, summary.md)

9. **`core` is `async def`** — `build_tool_fn` awaits `body(**kwargs)`
   (`count_tools.py:135`).
   (step_7.md)

10. **Duplicate column names de-duplicated**, case-insensitively, preserving
    first-seen order. Repeats otherwise render duplicate blocks, inflate
    `total_columns` for the cap footer, and can flip a 15-name call into triage.
    (step_7.md, summary.md)

11. **`config` removed from `summarize`'s tach `depends_on`** — contradicted
    summary.md § 1 and the `count_tools` precedent (no `config`; its
    `ResolvedTargets` import is `TYPE_CHECKING`-only). Raised in review round 4
    but never applied.
    (step_7.md)

12. **Pytest invocation corrected to plain `-n auto`.** The "fast-exclusion
    markers" / "fast markers" the PROMPTs referenced do not exist —
    `pyproject.toml` defines only `sqlite_integration`, `mssql_integration`,
    `postgresql_integration`, and `integration`, and CLAUDE.md prescribes
    `-n auto`.
    (step_1.md, step_7.md)

## Review log 3 — findings applied to the plan (2026-08-04)

Source: a further plan review (6 findings). Implementation still not started
(TASK_TRACKER: 0 of 7). All 6 were applied to `pr_info/steps/`.

1. **T-SQL `timestamp`/`rowversion` classifies as `other`, not `temporal`.**
   `INFORMATION_SCHEMA.COLUMNS.DATA_TYPE` reports `timestamp` for a
   `rowversion` column, but in T-SQL that is a `binary(8)` row-version stamp.
   The `date/time/timestamp` token rule routed it to `temporal`, so step 3
   would emit `MIN(c)`/`MAX(c)`, which SQL Server rejects (Msg 8117, *"Operand
   data type timestamp is invalid for max operator"*). Since all scalar
   aggregates share one `SELECT`, one legacy rowversion column would take down
   the whole table's scalar pass — the failure mode the LOB guard already
   prevents. Decision: add a **tsql-only** guard beside the LOB trio; SQLite
   `TIMESTAMP` stays `temporal`; test both dialects in one pair.
   (step_1.md)

2. **`IS NOT NULL` built as `exp.Is(..., negate=True)`.** The prescribed
   `ref.is_(exp.null()).not_()` builds `exp.Not(exp.Is(...))` and renders
   `NOT "c" IS NULL` (sqlglot's `Generator.not_sql` is `f"NOT {this}"`, no
   sqlite/tsql override) — semantically correct but contradicting the HOW text,
   the ALGORITHM comment and the TEST assertion, which all say
   `WHERE c IS NOT NULL`. Decision: use
   `exp.Is(this=ref, expression=exp.Null(), negate=True)`, which renders
   `IS NOT NULL` on both dialects, and assert the literal text.
   (step_4.md)

3. **Remainder-arithmetic pseudocode corrected.** `shown_rows = sum(freq)` used
   an unbound `freq`, and `len([v for v in values if v is not NULL])` iterated
   tuples rather than values — contradicting the very next line. Decision:
   `sum(f for _, f in values)` and `len([v for v, _ in values if v is not
   None])`. This is the one calculation the plan says to "pin the exact numbers
   with a test", so the pseudocode has to be right.
   (step_5.md)

4. **`n` dropped from the renderer signatures.** It was threaded through
   `render_summary` / `render_deep` / `_render_block` / `_render_values` with a
   self-cancelling rationale (pass `clamped_n` "so the header count never
   exceeds the cap", then "the renderer derives the shown count from
   `len(values)`, not from any `n`"), and no spec'd path read it. Decision:
   drop the parameter (simpler plan) and delete the contradictory
   justification. `clamped_n` remains — it is consumed by the value-list SQL.
   (step_5.md, step_6.md, step_7.md)

5. **`ColumnProfile` construction pinned explicitly.**
   (a) `execute_readonly_query` returns `list[dict[str, Any]]`
   (`backends/base.py:35-37`) while `ColumnProfile.values` is
   `list[tuple[Any, ...]] | None`; the dict→tuple mapping was never stated.
   Decision: map by the emitted aliases — top → `(r["value"], r["freq"])`,
   sample → `(r["value"],)`. (b) `value_kind` was assigned only "if deep",
   leaving triage profiles unspecified while the frozen dataclass declares no
   defaults. Decision: every column without a value list (all of triage, and
   every `other`-category column in the deep view) is constructed with the
   explicit pair `value_kind="none", values=None`.
   (step_7.md)

6. **`NUM` classifies as `numeric`.** The HOW named `NUM` as the motivating
   affinity for prefix/affinity matching, but the ALGORITHM's numeric token
   list (`int/decimal/float/numeric/real/money`) does not match the bare string
   `NUM`, so it fell through to `other`; the test list never pinned it. SQLite
   gives a `NUM`-declared column NUMERIC affinity. Decision: use the `num`
   prefix (which also covers `numeric`) so the algorithm and its own example
   agree, and add `NUM` to the parametrised test cases.
   (step_1.md)
