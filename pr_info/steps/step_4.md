# Step 4 — `verify` reports `max_rows_hard <= 0`

Layer 4 of [summary.md](./summary.md). Gives the operator-side entry point a
friendly report, matching the `max_rows_default > 0` check that already exists.

## WHERE

- `src/mcp_tools_sql/verification/queries.py` — new module-level helper plus
  edits in `verify_one_query` (lines 98-137)
- `tests/verification/test_queries.py` — one test next to
  `test_verify_queries_detects_missing_max_rows_default` (~line 139)
- `tests/cli/fixtures/verify_snapshot.txt` — byte-identical golden snapshot of
  the QUERIES + UPDATES sections. Add one `max_rows_hard` row per query
  (`get_user`, `bad_sql`, `mismatched_params`), each directly after that
  query's `max_rows_default` row. The key column is truncated at 28 chars, so
  the third row reads `mismatched_params.max_rows_h` — mirroring the existing
  `mismatched_params.max_rows_d`.
- `docs/cli.md` — QUERIES row description (line 223) and the sample `verify`
  output (lines 272-276)

## WHAT

```python
def _positive_entry(field: str, value: int) -> dict[str, Any]:
    """Build a verifier entry asserting ``value > 0`` for ``field``."""
```

Used twice in `verify_one_query`, replacing the inline block at lines 132-137.
`qcfg.max_rows_hard` is typed `int | None` (the model validator fills it in
after load), so pass `cast(int, qcfg.max_rows_hard)`; add `cast` to the
existing `typing` import.

## HOW

`verify_one_query` gains a fourth row, `<name>.max_rows_hard`, immediately
after `<name>.max_rows_default`. Two places emit rows and both must stay in
sync:

1. The unresolvable-pin early-return branch (lines 98-110) — add one more
   `make_entry(ok=False, value="(skipped)", error=str(exc))` line for
   `max_rows_hard`. Keep the four lines explicit; a loop would be less
   readable than the repetition it removes.
2. The normal path (lines 132-137) — two `_positive_entry` calls.

`verify_queries` needs no change: its `overall_ok` fold already walks every row
in the dict. `test_verify_one_query_matches_bulk_happy_path` compares key lists
between the two functions, so both stay consistent automatically.

Docstrings to update: the module docstring (line 1), `verify_one_query`'s
"Three-row dict" wording, and `verify_queries`' summary line.

## ALGORITHM

```
_positive_entry(field, value):
    ok = value > 0
    return make_entry(ok=ok, value=str(value),
                      error="" if ok else f"{field} must be > 0")
```

The generated message for `max_rows_default` is byte-identical to today's
(`"max_rows_default must be > 0"`), so the existing test still passes.

## DATA

`verify_one_query` returns a four-row dict per query, in order:
`<name>.sql`, `<name>.params`, `<name>.max_rows_default`,
`<name>.max_rows_hard`. Each row is the standard `make_entry` shape
(`ok`, `value`, `error`, `install_hint`).

## Tests (write first)

```python
def test_verify_queries_detects_non_positive_max_rows_hard(
    sqlite_targets: ResolvedTargets,
    sqlite_registry: BackendRegistry,
    all_reachable: dict[tuple[str, str], bool],
) -> None:
    """``max_rows_hard=0`` → ok=False on the ``<name>.max_rows_hard`` row."""
```

Mirror `test_verify_queries_detects_missing_max_rows_default`: one
`QueryConfig(sql="SELECT * FROM customers", params={}, max_rows_default=10,
max_rows_hard=0)`, then assert the row is `ok is False`, its error mentions
`max_rows_hard`, and `overall_ok is False`. Add an assertion in the same test
that a healthy config produces `ok is True` on the new row, so the row is
proven to exist on the happy path too.

## Docs

- `docs/cli.md:223` — change the QUERIES description from
  `` `max_rows_default > 0` `` to name both fields.
- `docs/cli.md:275` — add a `read_schemas.max_rows_hard` row to the sample
  output. Leave the `12 checks passed` total alone; the sample already elides
  rows with `...`.

## Checks

`run_format_code`, `run_pylint_check`, `run_pytest_check` (`["-n", "auto"]`),
`run_mypy_check` — all must pass. Watch `tests/cli/test_verify.py`,
`tests/cli/fixtures/verify_snapshot.txt` and
`tests/verification/test_orchestrator.py`, which run `verify` end to end over
configs with queries. The snapshot failure in `tests/cli/test_verify.py` is
expected and is fixed by editing the `verify_snapshot.txt` fixture to include
the new rows — not by changing the test code.

## Commit

```
feat(verify): check max_rows_hard > 0 alongside max_rows_default
```

## LLM prompt

> Read `pr_info/steps/summary.md` and `pr_info/steps/step_4.md`, then implement
> step 4 only. Follow TDD: add the new verification test first, watch it fail,
> then add `_positive_entry`, the fourth row in both emitting branches of
> `verify_one_query`, the docstring updates and the two `docs/cli.md` edits.
> Do not touch `query_helpers.py` or `formatting.py`. Run `run_format_code`,
> `run_pylint_check`, `run_pytest_check` with `extra_args: ["-n", "auto"]` and
> `run_mypy_check`, then make exactly one commit.
