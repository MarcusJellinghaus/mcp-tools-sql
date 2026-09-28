# Step 7 — Documentation

Read [summary.md](./summary.md) first. Last step, so the docs describe shipped
behaviour. No code, no tests.

## WHERE

- `README.md` (line 5, and the Key Ideas list)
- `docs/architecture/architecture.md` (the `query_tools.py` module row at `:132`;
  the Security bullet list at `:217-221`)
- `docs/cli.md` (the `CONNECTION` section description at `:221`; the `QUERIES`
  section description at `:223`; the `[WARN]` status bullet at `:229-231`; the
  sample output at `:248-292`)

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
it covers every declared backend variant, not just the pinned one. Mention that
an unmappable `backends.<key>` (e.g. `postgresql`, a typo) yields a `[WARN]` row
for dead config rather than an error (step 5, decision 11).

**`docs/cli.md:221`** — the `CONNECTION` row lists the backend-shape checks
including `path`. Add that a sqlite `path` of `:memory:` reports `[WARN]`: a
fresh connection to `:memory:` is a new, empty database, so read paths silently
return zero rows while `updates.*` still writes to the persistent connection
(step 6).

**`docs/cli.md:229-231`** — the `[WARN]` bullet says "the most common case is
detection of sensitive keys". Two more warn cases now exist. Reword so the
bullet describes `[WARN]` generally (non-fatal, does not affect the exit code)
and lists the cases: sensitive keys in the project query config, a skipped check
whose connection is unreachable, a sqlite `:memory:` path, and an unmappable
`backends.<key>` on a configured query.

**`docs/cli.md` sample output** — minimal edits only:

- **Relabel the `QUERIES` sample rows from `read_schemas.*` to `get_user.*`.**
  `read_schemas` is a *default* query (`src/mcp_tools_sql/default_queries.toml`),
  and `verify_queries` receives configured queries only — so with the caption
  corrected below, `read_schemas` rows contradict the sample. `get_user` is the
  configured-query name used by `init`'s template
  (`cli/commands/init.py:_build_query_block`) and by the verify snapshot fixture,
  so it is the right example. Keep the values as they are.
- Add one `read_only[sqlite]` row to that block.
- Fix the `max_rows_default` line's spacing: `_format_row` joins with two spaces,
  so the sample's single space was already wrong before this change.
- Fix the caption at `:272-276`: it says "one row per default + configured query",
  but `verify_queries` is called with configured queries only
  (`orchestrator.py:209-214`). Already wrong today — the issue lists this as a
  boy-scout fix.

`get_user.max_rows_default` is 24 characters, under the pad width, as is every
other label in that sample — so step 4's change does not touch them. Do **not**
regenerate the whole block by hand.

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
> Also update `docs/cli.md`'s `CONNECTION` description and its `[WARN]` status
> bullet to cover the two new warn cases — a sqlite `:memory:` path and an
> unmappable `backends.<key>`.
>
> Keep the `docs/cli.md` sample edits minimal: relabel the `QUERIES` rows from
> `read_schemas.*` to `get_user.*` (a default query can never appear in QUERIES),
> one added `read_only` row, the `max_rows_default` spacing fix, and the caption.
> Copy the row format
> from the regenerated `tests/cli/fixtures/verify_snapshot.txt` rather than
> inventing padding. Be honest that on MSSQL the DB-level backstop is the
> operator's read-only login.
>
> Then run `run_format_code` and `run_pytest_check` with
> `extra_args: ["-n", "auto"]` to confirm nothing regressed. Commit as one commit.
