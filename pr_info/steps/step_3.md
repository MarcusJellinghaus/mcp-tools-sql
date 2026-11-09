# Step 3 — `verify` warns on empty query/update descriptions

## LLM prompt
Read `pr_info/steps/summary.md`, then implement `pr_info/steps/step_3.md`.
TDD: update/add tests first, then the implementation. Run pylint, mypy, pytest (`-n auto`). One commit.

## WHERE
- `src/mcp_tools_sql/verification/queries.py` — `verify_one_query`
- `src/mcp_tools_sql/verification/updates.py` — `verify_one_update`
- Tests: `tests/verification/test_queries.py`, `tests/verification/test_updates.py` (if it asserts exact keys), `tests/cli/fixtures/verify_snapshot.txt`, `tests/cli/test_verify_output.py`

## WHAT
- Rename the existing bodies to private helpers `_verify_query_checks(...)` / `_verify_update_checks(...)` (same parameters, same return).
- Public `verify_one_query(...)` / `verify_one_update(...)` keep their signatures and append one row last.
- `QueryConfig.description` / `UpdateConfig.description` already default to `""` — no model change.

## ALGORITHM
```
def verify_one_query(name, qcfg, targets, registry, reachable):
    result = _verify_query_checks(name, qcfg, targets, registry, reachable)
    if not qcfg.description.strip():
        result[f"{name}.description"] = make_warn_entry(
            "(empty)", "no description; the tool uses a generated one")
    return result
```
Same for updates. Whitespace-only counts as empty (`.strip()`), the same test the step 4 toolkits use for the fallback, so the WARN fires exactly when the tool gets the generated description. The row is a warning: exit code and `query_count`/`update_count` are unaffected.
Only emit the row when the description is empty (no OK row otherwise), so configs with descriptions keep identical output.

## HOW
- Import `make_warn_entry` from `verification._helpers` in both modules.
- Update both docstrings' "Returns" to mention the optional trailing `<name>.description` row.

## Tests
- `verify_one_query` / `verify_one_update` with `description=""` or `"  "` (parametrized) → last key is `<name>.description`, `severity == "warning"`, existing keys keep their order.
- With a description → no `.description` key.
- Regenerate expectations: `verify_snapshot.txt` (the snapshot TOML has no descriptions, so each query/update gains a `[WARN]` row), JSON-output tests in `test_verify_output.py`, exact-key tests in `tests/verification/test_queries.py`.

## DATA
`dict[str, CheckResult]`, new optional key `<name>.description`.
