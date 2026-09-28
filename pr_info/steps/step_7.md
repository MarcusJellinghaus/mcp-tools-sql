# Step 7 — Documentation

Read [summary.md](./summary.md) first. Last step, so the docs describe shipped
behaviour. No code, no tests.

## WHERE

- `README.md` (line 5, and the Key Ideas list)
- `docs/architecture/architecture.md` (the `query_tools.py` module row at `:132`;
  the Security bullet list at `:217-221`)
- `docs/cli.md` (the `QUERIES` section description at `:223`; the sample output at
  `:248-292`)

## WHAT

**`README.md`** — line 5 says "user-defined SELECT queries". Make the guarantee
explicit: configured queries are enforced read-only, checked before registration,
independent of `security.allow_updates`. One added clause or one Key Ideas bullet;
do not restructure the section.

**`architecture.md:132`** — the `query_tools.py` row reads "Dynamic registration
of configured SELECT tools". Add that each query's SQL passes a read-only AST gate
at registration and that a violating query is skipped with a warning.

**`architecture.md` Security bullets** — add one bullet: configured queries are
proved read-only by AST inspection before registration and execute through the
backend's read-only path, unconditionally — `allow_updates` governs `updates.*`
only. Worth stating honestly that on MSSQL the DB-level backstop is the operator's
`db_datareader` + `db_denydatawriter` login, since `execute_readonly_query`
delegates there; on SQLite it is a `PRAGMA query_only = ON` connection.

**`docs/cli.md:223`** — the `QUERIES` row currently lists "SQL `EXPLAIN`,
well-formed parameters, `max_rows_default > 0`". Add the read-only check and note
it covers every declared backend variant, not just the pinned one.

**`docs/cli.md` sample output** — minimal edits only:

- Add one `read_only[sqlite]` row to the `read_schemas` block.
- Fix the `read_schemas.max_rows_default` line's spacing: the label is 29
  characters, and `_format_row` joins with two spaces, so the sample's single
  space was already wrong before this change.
- Fix the caption at `:272-276`: it says "one row per default + configured query",
  but `verify_queries` is called with configured queries only
  (`orchestrator.py:209-214`). Already wrong today — the issue lists this as a
  boy-scout fix.

Every other label in that sample is under the pad width, so step 4's change does
not touch them. Do **not** regenerate the whole block by hand.

## HOW

Copy the real row format from the regenerated
`tests/cli/fixtures/verify_snapshot.txt` rather than inventing padding. The
trailing check-count line in the sample (`12 checks passed, ...`) is illustrative
for an abbreviated block — leave it unless adding a row makes it obviously wrong.

## ALGORITHM / DATA

None.

## TESTS

None. No test asserts doc content.

## LLM PROMPT

> Read `pr_info/steps/summary.md` and `pr_info/steps/step_7.md`. Steps 1–6 are
> done.
>
> Update the docs per step 7: `README.md`, the `query_tools.py` row and Security
> bullets in `docs/architecture/architecture.md`, and the `QUERIES` description
> plus sample output in `docs/cli.md` — including the boy-scout fix to the "one row
> per default + configured query" caption, which is wrong today because
> `verify_queries` receives configured queries only.
>
> Keep the `docs/cli.md` sample edits minimal: one added `read_only` row, the
> `read_schemas.max_rows_default` spacing fix, and the caption. Copy the row format
> from the regenerated `tests/cli/fixtures/verify_snapshot.txt` rather than
> inventing padding. Be honest that on MSSQL the DB-level backstop is the
> operator's read-only login.
>
> Then run `run_format_code` and `run_pytest_check` with
> `extra_args: ["-n", "auto"]` to confirm nothing regressed. Commit as one commit.
