# Step 2 — Shared verdict helper + the registration gate

Read [summary.md](./summary.md) first, especially *"One shared verdict function"*,
*"The gate cannot run at config-load time"* and *"Failure mode: skip + warn"*.

This is the step that closes the hole. Depends on step 1.

## WHERE

- `src/mcp_tools_sql/query_helpers.py` — the shared helper
- `src/mcp_tools_sql/query_tools.py` — the gate
- `tests/test_query_tools.py`
- `tests/test_server.py` — the decision-1 wiring test

## WHAT

In `query_helpers.py`, next to `extract_sql_params`:

```python
def read_only_rejection(sql: str, dialect: str) -> str | None:
    """Return a rejection message when ``sql`` is not provably read-only."""
```

It exists so the startup gate and the `verify` row (step 5) cannot disagree —
one implementation, two callers. Its docstring should say so.

In `query_tools.py`:

```python
logger = logging.getLogger(__name__)
```

and the gate inside the existing `for name, config in self._queries.items():`
loop of `QueryTools.register`, placed **after** `target`/`backend` resolution and
**before** `build_query_sig_params`.

## HOW

- `read_only_rejection` takes a **dialect, not a backend name** — so it has no
  `to_dialect` `ValueError` to report and no tri-state return. Mapping is the
  caller's job.
- `query_tools.py` imports `to_dialect` from `mcp_tools_sql.backends.base` (a
  real runtime import, not `TYPE_CHECKING`) and `read_only_rejection` from
  `query_helpers`. Both are permitted by `.importlinter` and `tach.toml`; the
  checks confirm it.
- `logger` mirrors `schema_tools.py:27` — plain `logging.getLogger(__name__)`.
  Do **not** reach for the `log_utils` shim; nothing here needs structlog.
- `resolve_sql` is called twice for a registered query — once by the gate, once
  inside `build_query_body`. Leave it. Threading the resolved string through
  `build_query_body`'s signature buys nothing and touches the schema-tools
  caller.
- Update `QueryTools.register`'s docstring: it currently documents only the
  `ValueError` paths. Add that a query whose SQL is not provably read-only is
  skipped with a warning while the rest register.
- **Leave the `raise ValueError` for a bad query name exactly as it is.** A bad
  name is a config error, a bad statement is a security rejection. Two failure
  modes in one loop, intentionally.

## ALGORITHM

`read_only_rejection`:

```
try:
    verdict = read_only_violation(sql, dialect)
    if verdict is None:
        verdict = keyword_absorption_violation(sql, dialect)
except ParseError as exc:
    return f"Not read-only. SQL could not be parsed as {dialect}: {exc}"
return verdict
```

The gate in `register`:

```
resolved_sql = config.resolve_sql(target.backend_name)
rejection = read_only_rejection(resolved_sql, to_dialect(target.backend_name))
if rejection is not None:
    logger.warning("Skipping query %r — %s", name, rejection)
    continue
```

## DATA

- `read_only_rejection` → `str | None`.
- The gate registers no tool and no stub for a rejected query (decision 3). The
  `verify` row added in step 5 is the discoverability mechanism.

## TESTS (write first)

`tests/test_query_tools.py` — use the existing `RecordingRegistry` /
`single_target` helpers from `tests.target_helpers`.

Registration behaviour:

- A `[queries.purge] sql = "DELETE FROM Orders"` config registers **no**
  `query_purge` tool, and `caplog` records a warning naming the query.
- **Siblings still register**: a config with one violating and one valid query
  registers exactly `query_<valid>` — this is decision 3's whole point.
- `EXEC dbo.usp_x :p` is rejected (decision 2, no opt-out).
- The separator-less batch `"SELECT 1\nDELETE FROM t"` is rejected — this is the
  case only step 1's guard catches, so it proves the two layers are actually
  composed here and not just in `utils`.
- Unparseable SQL (`"SELECT FROM WHERE )("`) is rejected with a warning, not a
  raw `ParseError` traceback escaping `register`.
- A valid `SELECT` query still registers, and a **bad query name still raises
  `ValueError`** — pin that the two failure modes did not get merged.
- **Decision 1 gets its own test — required, not optional.** It is the issue's
  headline claim, so it must be pinned at the wiring level rather than left
  implicit in `QueryTools` not seeing `SecurityConfig`. Add it to
  `tests/test_server.py`, following the existing idiom there
  (`tests/test_server.py:217-219`): build `ToolServer(qcfg, targets, registry,
  allow_updates=True)` from a config carrying
  `[queries.purge] sql = "DELETE FROM Orders"`, call
  `_register_configured_tools()`, and assert `query_purge` is absent from the
  registered tool names. The `allow_updates=True` value is the point: the gate
  must reject regardless of the flag.

Helper behaviour — a couple of direct `read_only_rejection` tests are enough
(clean `SELECT` → `None`; unparseable → a message mentioning the dialect). The
shape tables live in step 1; do not duplicate them.

## LLM PROMPT

> Read `pr_info/steps/summary.md` and `pr_info/steps/step_2.md`. Step 1 is done.
>
> Implement step 2 test-first: add the registration-gate tests to
> `tests/test_query_tools.py` and the mandatory decision-1 wiring test to
> `tests/test_server.py` (`ToolServer(..., allow_updates=True)` must still not
> register a `DELETE` query), watch them fail, then add `read_only_rejection` to
> `src/mcp_tools_sql/query_helpers.py` and the gate to `QueryTools.register` in
> `src/mcp_tools_sql/query_tools.py`.
>
> Keep the existing `raise ValueError` for bad query names untouched — a bad name
> is a config error, a bad statement is a security rejection, and they stay
> separate. Do not gate the built-in schema queries; they are server-authored.
>
> Then run `run_format_code`, `run_pylint_check`, `run_pytest_check` with
> `extra_args: ["-n", "auto"]`, `run_mypy_check`, `run_tach_check` and
> `run_lint_imports_check`. All must pass. Commit as one commit.
