# Step 6 — Extend `verify_updates` (Identifier Regex + `required` Flag Visibility)

## Goal

Extend `verify_updates` so the three existing rows per update
(`<name>.table`, `<name>.key_column`, `<name>.fields`) **also** surface:
1. Identifier-regex failures on `table`, `schema_name` (when non-empty),
   `key.field`, and each `fields[].field` — with the same intentional-whitelist
   wording used at registration so users see the same explanation in both
   places.
2. The `required` flag for each field, inline in the `<name>.fields` row's
   `value` text (e.g. `"name(req), country, email(req)"`).

No new row types — everything folds into the existing three rows.

## WHERE

- `src/mcp_tools_sql/cli/commands/verify.py` — extend `verify_updates`
- `tests/cli/test_verify.py` — new tests

## WHAT

`verify_updates`' signature is unchanged. Both the whitelist pattern
and the rejection error message come from the **shared** identifier
module created (or extended) in Step 4 (USER DECISION — shared helper
module; USER DECISION — export pattern from `identifiers.py`). Before
implementing, search the repo for existing identifier-validation code
via `mcp__mcp-workspace__search_files`; if Step 4 has already
introduced `src/mcp_tools_sql/identifiers.py` (or extended an existing
module), import both names here too:

```python
from mcp_tools_sql.identifiers import IDENTIFIER_PATTERN, identifier_error
```

No parallel `_IDENTIFIER_RE` literal and no parallel `_identifier_error`
helper are defined in `verify.py` — there must be exactly one source of
both the pattern and the error string in the codebase.

## HOW

- `verify.py` no longer needs `import re` directly — pattern matching
  goes through the imported `IDENTIFIER_PATTERN`. (If `re` happens to be
  imported for some other reason, leave it; otherwise do not add it.)
- In `verify_updates`, for each `(name, ucfg)` pair:
  - `.table` row: if `not IDENTIFIER_PATTERN.match(ucfg.table)` OR
    (`ucfg.schema_name` non-empty AND not pattern-matching), set ok=False
    with `identifier_error(...)` (the shared helper). Otherwise the
    existing "table-exists" check runs as today.
  - `.key_column` row: if key is present and `key.field` does not match
    the pattern, ok=False with `identifier_error(...)`. Otherwise the
    existing column-exists check runs.
  - `.fields` row: build a value string `"name(req), country, ..."`
    surfacing each field's `required` flag inline (`(req)` suffix on
    required fields, no suffix on optional). If any field name fails the
    pattern, ok=False with `identifier_error(...)` listing the offending
    names. Otherwise the existing "columns exist" check runs and the
    value text keeps the `(req)` annotations.

Identifier failures short-circuit the existing column-lookup check — if
the identifier is invalid, we don't try to query the database for it.

When the table/schema identifier is malformed, only the `.table` row is
emitted for that update — `.key_column` and `.fields` rows are skipped.
This matches the principle that an unverifiable table makes downstream
column checks meaningless.

## ALGORITHM

```
for name, ucfg in updates.items():
    bad_idents = []
    if not IDENTIFIER_PATTERN.match(ucfg.table): bad_idents.append(ucfg.table)
    if ucfg.schema_name and not IDENTIFIER_PATTERN.match(ucfg.schema_name):
        bad_idents.append(ucfg.schema_name)
    if bad_idents:
        result[f"{name}.table"] = _entry(
            ok=False,
            value=ucfg.table,
            error=identifier_error(value=bad_idents[0], update_name=name),
        )
        # bad table/schema identifier blocks every downstream check for this
        # update — emit only the .table row, then skip to the next update.
        # User fixes the identifier and re-runs verify.
        # First offender wins: if both `table` and `schema_name` are
        # malformed, only the first appended to `bad_idents` is surfaced in
        # the error message. The user fixes it and re-runs verify to
        # discover the second.
        continue

    # ... existing table-exists / column-lookup logic, but:
    #   - key_column row: if key.field present and !IDENTIFIER_PATTERN.match, ok=False
    #       + identifier_error(value=ucfg.key.field, update_name=name)
    #   - fields row: value = ", ".join(f"{f.field}(req)" if f.required else f.field for f in ucfg.fields)
    #                 if any f.field !IDENTIFIER_PATTERN.match, ok=False
    #                   + identifier_error(value=<offender>, update_name=name)
```

The `value=ucfg.table` shape on the failing `.table` row matches the
existing happy-path `.table` row in `src/mcp_tools_sql/cli/commands/verify.py`
(`result[f"{name}.table"] = _entry(ok=True, value=ucfg.table)`) — bare
table name, no schema qualification.

Canonical call shape (matches `identifier_error(value: str,
update_name: str) -> str` from Step 4): use
`identifier_error(value=..., update_name=...)` (or the equivalent
positional `identifier_error(bad_value, update_name)`) — explicitly so
step 4 and step 6 call sites match.

## DATA

`verify_updates` still returns `dict[str, dict[str, Any]]` with `overall_ok`.
Row keys unchanged. Row `value` for `.fields` now includes `(req)` suffixes.

## Tests

TDD: add tests first in `tests/cli/test_verify.py`.

- `test_verify_updates_rejects_invalid_table_identifier`:
  `UpdateConfig(table="orders; DROP TABLE x", ...)` →
  `result["bad.table"]["ok"] is False`; error string contains both
  `"intentionally restricted"` and the offending value. Also assert
  that `"bad.key_column"` and `"bad.fields"` are NOT present in
  `result` (one row on table-fail).
- `test_verify_updates_rejects_invalid_schema_identifier`:
  `UpdateConfig(table="customers", schema_name="bad schema", ...)` →
  `.table` row ok=False with identifier error; `.key_column` and
  `.fields` rows are absent for this update; empty `schema_name` still
  passes (regression guard).
- `test_verify_updates_rejects_invalid_key_field_identifier`:
  `UpdateKeyConfig(field="id; DROP", ...)` → `.key_column` row ok=False
  with identifier error.
- `test_verify_updates_rejects_invalid_field_identifier`: one
  `UpdateFieldConfig(field="bad-col")` → `.fields` row ok=False with
  identifier error mentioning `bad-col`.
- `test_verify_updates_surfaces_required_flag_inline`: two fields, one
  with `required=True` and one without; `.fields` row's `value` string
  contains both `"name(req)"` and `"country"` (no `(req)` suffix).
- Regression guard: keep all existing `test_verify_updates_*` tests
  green. The existing happy-path tests should produce unchanged
  `result["<name>.table"]["ok"] is True` etc. but with the `(req)` /
  bare suffix in `.fields` row's value when applicable.

## LLM Prompt

> Read `pr_info/steps/summary.md` (full file) and `pr_info/steps/step_6.md`.
> Implement Step 6 only: extend `verify_updates` in
> `src/mcp_tools_sql/cli/commands/verify.py` so its three existing rows
> per update also report identifier-regex failures (with the same
> "intentionally restricted to a strict whitelist" wording used by
> `UpdateTools.register` from Step 4) and so the `.fields` row's value
> surfaces each field's `required` flag inline (e.g. `"name(req),
> country"`). Do not add new row types. Follow TDD: add the five test
> cases described in this step to `tests/cli/test_verify.py` before
> changing the implementation, and confirm all existing `verify_updates`
> tests still pass. Run `mcp__tools-py__run_pylint_check`,
> `mcp__tools-py__run_pytest_check` (with the fast unit-test marker
> exclusion), and `mcp__tools-py__run_mypy_check`. Make exactly one commit
> when green.
