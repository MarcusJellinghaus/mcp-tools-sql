# Step 1 — Typed rows and sections; `verify_all` returns `VerifyResult`

## LLM prompt

> Read `pr_info/steps/summary.md`, then implement **this step only**
> (`pr_info/steps/step_1.md`). Do TDD: write or rewrite the tests listed below first, then
> change the code until they pass. Default `verify` text output must stay byte-identical:
> `tests/cli/test_verify.py` and `tests/cli/fixtures/verify_snapshot.txt` must not be edited
> and must pass. Run pylint, pytest (`-n auto`), mypy, ruff, lint-imports, tach and
> format_code, then make one commit.

## WHERE

- `src/mcp_tools_sql/verification/_helpers.py`
- `src/mcp_tools_sql/verification/environment.py`, `dependencies.py`, `builtin.py`,
  `config_files.py`, `connection.py`, `queries.py`, `updates.py`
- `src/mcp_tools_sql/verification/orchestrator.py`
- `src/mcp_tools_sql/cli/commands/verify.py`
- `tests/verification/test_helpers.py`, `test_environment.py`, `test_dependencies.py`,
  `test_builtin.py`, `test_config_files.py`, `test_connection.py`, `test_queries.py`,
  `test_updates.py`, `test_orchestrator.py`
- `docs/architecture/architecture.md` (Verification Layer paragraph)

## WHAT

`_helpers.py`. Replace `VerifierEntry` with:

```python
class CheckResult(TypedDict):
    ok: bool
    value: str
    severity: Literal["error", "warning"]
    error: NotRequired[str]
    install_hint: NotRequired[str]

class VerifySection(TypedDict):
    title: str
    ok: bool
    checks: dict[str, CheckResult]

class VerifyResult(TypedDict):          # `summary` is added in step 3
    sections: list[VerifySection]
    skipped_queries: int | None
    skipped_updates: int | None

def make_entry(*, ok: bool, value: str = "", error: str = "", install_hint: str = "",
               severity: Literal["error", "warning"] = "error") -> CheckResult
def make_warn_entry(value: str, error: str = "") -> CheckResult      # ok=False, severity="warning"
def make_skipped_entry(connection: str) -> CheckResult               # -> make_warn_entry(...)
def make_skipped_not_read_only_entry() -> CheckResult                # -> make_warn_entry("(skipped)", "not read-only; see the read_only row")
def is_passing(entry: CheckResult) -> bool                           # ok or severity == "warning"
def checks_ok(checks: Mapping[str, CheckResult]) -> bool             # all(is_passing(...))
```

Verifier signatures. Same parameters as today; the return type changes from
`dict[str, Any]` to `dict[str, CheckResult]`, and no `overall_ok` key is written:

```python
verify_environment() -> dict[str, CheckResult]
verify_dependencies(backend, configured_driver="") -> dict[str, CheckResult]
verify_builtin() -> dict[str, CheckResult]
verify_config_files(config_path, db_config_path) -> dict[str, CheckResult]
verify_connection(target, backend, *, probe_error="") -> dict[str, CheckResult]
verify_queries(...) / verify_one_query(...) -> dict[str, CheckResult]
verify_updates(...) / verify_one_update(...) -> dict[str, CheckResult]
```

`orchestrator.py`:

```python
def collect_install_instructions(sections: list[VerifySection]) -> dict[str, CheckResult]
def _section(title: str, checks: dict[str, CheckResult]) -> VerifySection   # ok = checks_ok(checks)
def _verify_connections(targets, registry) -> tuple[dict[str, CheckResult], bool, dict[tuple[str, str], bool]]
def verify_all(config_path: Path | None, db_config_path: Path | None) -> VerifyResult
```

`render_skip_m2_summary` keeps its signature and text.

`cli/commands/verify.py`:

```python
def run(args) -> int                                   # result = verify_all(...); return _print_and_summarize(result)
def _print_and_summarize(result: VerifyResult) -> int
```

## HOW

- `config_files.py`: the sensitive-keys row becomes
  `make_warn_entry(", ".join(sorted(set(found))), "Move credentials to ~/.mcp-tools-sql/config.toml")`.
- `connection.py`: the `:memory:` row already uses `make_warn_entry`. Delete the
  `overall_ok` computation.
- `queries.py`: `if not pinned_row["ok"]:` becomes `if not is_passing(pinned_row):`. Delete
  `overall_ok`.
- `updates.py`, `environment.py`, `dependencies.py`, `builtin.py`: delete every
  `overall_ok` assignment. The early-return dicts in `verify_dependencies` lose their
  `"overall_ok"` key.
- `_verify_connections`: `pair_ok = checks_ok(pair_checks)`. The merged CONNECTION checks
  are returned without `overall_ok`; the orchestrator wraps them with `_section`.
- `collect_install_instructions`: collect `entry.get("install_hint")` from rows where
  `not entry["ok"] and entry["severity"] == "error"`. Return `hint_<i>` rows built with
  `make_entry(ok=True, value=hint)`.
- CLI row status: if not `ok` and `severity == "warning"` → `"warn"`; elif `ok` → `"ok"`;
  else `"err"`. Use `entry.get("value", "")` and `entry.get("error", "")`.

## ALGORITHM (`verify_all`)

```
sections = [_section("ENVIRONMENT", verify_environment()), _section("CONFIG", ...), DEPENDENCIES, BUILTIN]
skipped_q = skipped_u = None
if targets resolved:
    conn_checks, default_ok, reachable = _verify_connections(...); append CONNECTION
    if default_ok and query_config: append QUERIES, UPDATES sections
    else if not default_ok: skipped_q, skipped_u = _load_query_config_for_counts(...)
install = collect_install_instructions(sections); if install: append INSTALL INSTRUCTIONS
return {"sections": sections, "skipped_queries": skipped_q, "skipped_updates": skipped_u}
```

CLI printer: for each section, print `=== title ===` and each row via `_format_row`. If
`skipped_queries is not None`, print
`render_skip_m2_summary(skipped_queries, skipped_updates or 0)`. Then print the totals line
and return `_compute_exit_code(err_count)`.

## DATA

- Passing row: `{"ok": True, "value": "...", "severity": "error"}`. `error` and
  `install_hint` keys appear only when non-empty.
- Warning row: `{"ok": False, "value": "...", "severity": "warning", "error": "..."}`.
- Section: `{"title": "CONFIG", "ok": bool, "checks": {...}}`.

## Tests (write first)

- `test_helpers.py` (rewrite the `VerifierEntry` test):
  - `make_entry(ok=True, value="x")` returns exactly
    `{"ok": True, "value": "x", "severity": "error"}`;
  - `make_entry(ok=False, error="e", install_hint="h")` contains both keys;
  - `make_warn_entry("v", "e")` has `ok is False` and `severity == "warning"`;
  - `make_skipped_entry` / `make_skipped_not_read_only_entry` are warning rows;
  - `checks_ok` is True for `{}` and for warning-only rows, and False when any error row has
    `ok=False`.
- Rewrite every `result["overall_ok"] is X` as `checks_ok(result) is X`.
- Rewrite every `["warn"] is True` / `.get("warn") is True` as
  `severity == "warning"` and `ok is False`.
- Drop the `bulk_without_overall` filtering in `test_queries.py` / `test_updates.py`.
- `test_connection.py`: a sqlite `:memory:` target with every other row passing has
  `checks_ok(result) is True`.
- `test_queries.py`: when the pinned variant is an unknown backend (its `read_only` row is
  a warning, e.g. `make_targets(backend_name="postgresql")` with a stub registry), the
  `<name>.sql` row is not the "not read-only" skip row.
- `test_orchestrator.py`:
  - rewrite the tuple tests: `verify_all` returns a dict with keys
    `{"sections", "skipped_queries", "skipped_updates"}`, and every section has
    `title` / `ok` / `checks`;
  - happy path: both skip counts are `None`;
  - connection failure: the skip counts are ints, e.g. `0`/`0`;
  - unresolved targets: no CONNECTION section and both counts `None`;
  - a sqlite `:memory:` config with a query: QUERIES is present (the target counts as
    reachable) and CONNECTION `ok is True`;
  - `collect_install_instructions` test takes `VerifySection` input.
- Unchanged and must pass: `tests/cli/test_verify.py` (snapshot included).

## Docs

`architecture.md`, Verification Layer: replace "returns `(sections, skip_summary)`" with a
one-sentence description of `VerifyResult`.
