# Issue #62 — `queries.*` must be provably read-only

## Problem

`queries.*` is documented as the read-only channel, but nothing verifies it. A
configured query's raw SQL is registered as a `query_<name>` tool and executed
through `backend.execute_query` — on MSSQL an `autocommit=True` connection — so
`[queries.purge] sql = "DELETE FROM Orders"` deletes rows and commits with no
transaction to roll back. `security.allow_updates = false` does not help: it
only skips registering `UpdateTools`.

The switch is how the bug surfaces, not the root cause. `updates.*` is the write
channel (structured table + key + fields, server-generated SQL, governed by
`allow_updates`). `queries.*` is the read channel and must be read-only
**regardless of that flag**.

## Solution

Wire two already-proven primitives into this one entry point, and make the
guarantee visible in `verify` and in the docs.

1. **AST gate at registration.** `read_only_violation` (the existing sqlglot
   proof) plus a new keyword-absorption guard, run on each configured query's
   resolved SQL in `QueryTools.register`. A violation skips that one query with
   a logged warning; the remaining queries register normally.
2. **DB-enforced backstop.** The tool-facing read paths switch from
   `execute_query` to `execute_readonly_query`.
3. **Verify rows.** One `<name>.read_only[<backend>]` row per declared backend
   variant per query, so a write hiding in a `[queries.x.backends.<other>]`
   override is caught before the config ships. Plus a `:memory:` warning on the
   sqlite `path` row.
4. **Docs.** The read-only guarantee is now real and is stated as such.

## Architectural / design changes

**A new invariant, not a new component.** No new module, no new class. The
change is that operator-authored SQL now passes a gate before it can become a
tool, and that the read path's execution method carries the read-only contract.

**One shared verdict function.** `query_helpers.read_only_rejection(sql, dialect)`
combines the AST proof, the absorption guard and the `ParseError` catch, and is
called by *both* the startup gate and the verify row. A single implementation is
the point: the verify row exists to predict what the server will do at startup,
so the two must not be able to disagree. `query_helpers` already sits below both
callers (`query_tools` imports it; `verification/queries` imports it), so this
needs no layering change.

**The gate cannot run at config-load time.** `QueryConfig.resolve_sql(backend_name)`
means a query's SQL depends on its backend, and the backend is known only once
the pinned `(connection, database)` is resolved — a Pydantic validator cannot see
the dialect. The earliest point where resolved SQL *and* dialect both exist is
`QueryTools.register`, which already validates query names. The gated string is
byte-identical to the executed string: `build_query_body` resolves SQL once at
registration from the same pinned `backend_name`, and configured queries have no
per-call target switch.

**Two layers, honestly labelled.** On SQLite, `execute_readonly_query` opens a
fresh `PRAGMA query_only = ON` connection, so the backstop is real. On MSSQL it
delegates straight to `execute_query`; the guarantee there comes from the
operator having configured a `db_datareader` + `db_denydatawriter` login. So on
the primary backend the AST gate plus the absorption guard is the *entire*
in-process enforcement — which is why the gate is unconditional and has no
per-query opt-out.

**A deliberate exception to the "prove, don't blocklist" philosophy.** The
absorption guard blocklists keywords, which `utils/sql_placeholders.py` explicitly
argues against. It is justified only as a second layer *on top of* the AST proof,
never as a replacement: sqlglot 30.19.0 does not truncate a separator-less batch,
it reinterprets the write keyword as a column alias, so `SELECT 1\nDELETE FROM t`
parses clean as `SELECT 1 AS DELETE FROM t` while pyodbc still runs both
statements. A statement-count check detects nothing there.

**Failure mode: skip + warn, not hard fail.** A bad statement is a security
rejection; the query is dropped and logged. This sits directly beside the
existing hard `raise ValueError` for a bad query *name* in the same loop — a bad
name is a config error. Two failure modes in one function, intentionally. A hard
fail would turn one typo into a dead stdio server whose error message is easy to
miss; the verify row is the discoverability mechanism instead.

**Verify gains a static, per-variant check.** Existing query rows are mostly
per-pinned-target. `read_only` is per *declared* variant, because `verify` is a
pre-flight command run on a different box than the one where an override applies.
An unmappable `backends` key (`postgresql`, a typo) is dead config: a `warn` row,
not an error — it would fail `verify` over SQL that never executes.

**Cost accepted.** `sqlite.execute_readonly_query` opens a fresh connection per
call, which under `database="*"` becomes one per target per call. Accepted for
the guarantee.

## Decisions carried from the issue

| # | Decision |
|---|----------|
| 1 | Gate is unconditional; `allow_updates` keeps governing `updates.*` only |
| 2 | `EXEC <proc>` is rejected with no opt-out — the gate cannot see a proc body |
| 3 | Violation at startup: skip that query, log a warning, register the rest; no stub tool |
| 4 | Switch all tool-facing read paths: configured queries, schema pinned, schema `database="*"` fan-out |
| 5 / 8 / 14 | SQLite `:memory:`: a `ok=True, warn=True` row on the existing sqlite `path` row in `verification/connection.py` |
| 6 / 10 | Keyword-absorption guard as a sibling function in `utils/sql_placeholders.py`; `read_only_violation`'s verdict logic unchanged |
| 7 | `verify` emits one `<name>.read_only[<backend>]` row per variant in `{target.backend_name} \| set(qcfg.backends)` |
| 9 | Internal `verify` probes stay on `execute_query` (`connection.py:203`, `updates.py:29,37`) — server-authored, not operator-authored |
| 11 | Unmappable `backends` key → `warn` row |
| 12 | Unresolvable pin → one un-suffixed `<name>.read_only` `(skipped)` row |
| 13 | Stop truncating labels in `_pad`; `_LABEL_WIDTH = 28` becomes a minimum pad |
| 15 | Reword `read_only_violation`'s `count_records`-specific rejection message in place |

## Constraints the implementer must respect

- **`ok=True` on the `:memory:` row is mandatory.** `verify_connection`'s
  `overall_ok` and `_verify_connections` both read bare `entry["ok"]` with no
  warn tolerance; that value becomes `pair_ok` → `reachable` → `default_ok`, and
  `default_ok=False` skips the whole QUERIES/UPDATES block. An `ok=False` path
  row would silently suppress the very `read_only` rows this issue adds.
- **`read_only_violation` raises `ParseError`** on unparseable or empty SQL
  rather than returning a verdict. It must be caught and treated as a violation.
- **Do not add a default `execute_readonly_query`** to the `DatabaseBackend` ABC
  that delegates to `execute_query`. It would shrink the test-fake diff to zero
  and hand every future backend a fake read-only guarantee.
- **Do not "tidy" the skip+warn into the neighbouring `raise ValueError`,** or
  vice versa.
- `tests/cli/fixtures/verify_snapshot.txt` is asserted byte-identical. Steps 4
  and 5 both change it. **Regenerate from actual output; never hand-pad.**

## Files created or modified

No new source modules — deliberate.

**Modified — source**

| File | Change | Step |
|------|--------|------|
| `src/mcp_tools_sql/utils/sql_placeholders.py` | `keyword_absorption_violation` added; `read_only_violation` message reworded | 1 |
| `src/mcp_tools_sql/query_helpers.py` | `read_only_rejection` added; two read paths switched to `execute_readonly_query` | 2, 3 |
| `src/mcp_tools_sql/query_tools.py` | Registration gate + module logger | 2 |
| `src/mcp_tools_sql/cli/commands/verify.py` | `_pad` removed, label truncation dropped | 4 |
| `src/mcp_tools_sql/verification/_helpers.py` | `make_warn_entry` added | 5 |
| `src/mcp_tools_sql/verification/queries.py` | Per-variant `read_only` rows | 5 |
| `src/mcp_tools_sql/verification/connection.py` | `:memory:` warn on the sqlite `path` row | 6 |

**Modified — tests**

| File | Change | Step |
|------|--------|------|
| `tests/test_sql_placeholders.py` | Absorption guard accept/reject tables | 1 |
| `tests/test_query_tools.py` | Gate behaviour; `_StubBackend` gains `execute_readonly_query`; two spies retargeted | 2, 3 |
| `tests/test_schema_tools_multitarget.py` | Fake's `NotImplementedError` → delegation | 3 |
| `tests/backends/test_registry.py` | Fake check (already defines the method) | 3 |
| `tests/cli/test_verify.py` | Long-label test. The `execute_query` side effect stays as-is — that probe is the `SELECT 1` liveness check, which decision 9 leaves on `execute_query`; step 3 only confirms it still passes | 4 |
| `tests/cli/fixtures/verify_snapshot.txt` | Regenerated (padding, then new rows) | 4, 5 |
| `tests/verification/test_queries.py` | Per-variant rows, warn row, skipped row | 5 |
| `tests/verification/test_connection.py` | `:memory:` warn row | 6 |

**Modified — docs**

| File | Change | Step |
|------|--------|------|
| `README.md` | Read-only guarantee on the `queries.*` channel | 7 |
| `docs/architecture/architecture.md` | `query_tools.py` module row; Security bullet list | 7 |
| `docs/cli.md` | `QUERIES` section description; sample output; wrong "default + configured" caption | 7 |

## Step order

| Step | Content | Why here |
|------|---------|----------|
| 1 | Absorption guard + message reword | Pure `utils`, no callers yet |
| 2 | `read_only_rejection` + the registration gate | Closes the hole |
| 3 | `execute_readonly_query` on the read paths + fakes | Independent of the gate |
| 4 | Label truncation dropped + snapshot regen | Before step 5 so the snapshot settles at the new padding first |
| 5 | Per-variant `read_only` verify rows + snapshot regen | Needs step 2's helper |
| 6 | `:memory:` warn row | Independent; does not touch the snapshot (CONNECTION section) |
| 7 | Docs | Last, so it describes shipped behaviour |

Steps 3 and 6 are independent of everything else and could move. Step 5 must
follow steps 2 and 4.

## Checks per step

```
mcp__mcp-tools-py__run_format_code
mcp__mcp-tools-py__run_pylint_check
mcp__mcp-tools-py__run_pytest_check   (extra_args: ["-n", "auto"])
mcp__mcp-tools-py__run_mypy_check
```

Steps 1, 2 and 5 additionally run `run_tach_check` and
`run_lint_imports_check` — step 2 adds a `backends.base` import to
`query_tools`, step 5 a `query_helpers` import to `verification`. Both are
already permitted; the check confirms it.
