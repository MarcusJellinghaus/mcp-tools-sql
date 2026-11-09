# Step 4 — Public API exports, `verify --output-format json`, `docs/python-api.md`

## LLM prompt

> Read `pr_info/steps/summary.md` (sections 5 and 7), then implement **this step only**
> (`pr_info/steps/step_4.md`). Do TDD: write `tests/cli/test_verify_output.py` first, then
> implement. `tests/cli/test_verify.py` must not be edited and must pass. Run pylint,
> pytest (`-n auto`), mypy, ruff, lint-imports, tach and format_code, then make one commit.

## WHERE

- `src/mcp_tools_sql/verification/__init__.py`
- `src/mcp_tools_sql/cli/commands/verify.py`
- `tests/cli/test_verify_output.py` (**new**)
- `docs/python-api.md` (**new**), `docs/cli.md`

## WHAT

`verification/__init__.py`:

```python
from mcp_tools_sql.verification._helpers import CheckResult, VerifyResult, VerifySection, VerifySummary
__all__ = ["CheckResult", "VerifyResult", "VerifySection", "VerifySummary", "verify_all",
           "verify_builtin", "verify_config_files", "verify_connection", "verify_dependencies",
           "verify_environment", "verify_queries", "verify_updates"]
```

The module docstring states that `verify_all` and the four types are the stable public
API, and that the `verify_*` section functions carry no stability promise.

`cli/commands/verify.py`:

```python
def add_subparser(subparsers) -> None   # adds --output-format {text,json}, default "text"
def _error_count(result: VerifyResult) -> int   # rows that are not is_passing
def run(args) -> int
```

## HOW

- `parser = subparsers.add_parser("verify", ...)`, then
  `parser.add_argument("--output-format", choices=["text", "json"], default="text", help=...)`.
- In `run`, read the flag with `getattr(args, "output_format", "text")`. The unchanged CLI
  tests build a `Namespace` without it.
- JSON goes to stdout via `print(json.dumps(result, indent=2))`. Nothing else is printed
  to stdout in JSON mode.

## ALGORITHM (`run`)

```
result = verify_all(args.config, args.database_config)
if getattr(args, "output_format", "text") == "json":
    print(json.dumps(result, indent=2))
    return _compute_exit_code(_error_count(result))
return _print_and_summarize(result)
```

## DATA

The JSON document is exactly the `VerifyResult` dict: `sections`, `skipped_queries`,
`skipped_updates`, `summary`.

## Tests (write first): `tests/cli/test_verify_output.py`

Use valid sqlite configs in `tmp_path`. Call `main([...])` from `mcp_tools_sql.main` with
`--config`, `--database-config`, `--console-only`, `verify`, and capture stdout.

- `verify --output-format json`:
  - stdout parses with `json.loads`;
  - its keys are `{"sections", "skipped_queries", "skipped_updates", "summary"}`;
  - it equals `verify_all(q, db)` called directly with the same args, compared after a
    `json.loads(json.dumps(...))` round trip;
  - exit code 0.
- JSON mode with a missing query config: exit code 1, and stdout is still valid JSON.
- `verify --output-format xml` raises `SystemExit` with code 2.
- `mcp_tools_sql.verification.__all__` contains `verify_all`, `CheckResult`,
  `VerifySection`, `VerifySummary` and `VerifyResult`.

## Docs

- `docs/python-api.md` (new):
  - `verify_all(config_path, db_config_path, project_dir=None)`, its synchronous run time
    (seconds), and that it opens and closes its own connections;
  - the four TypedDicts with field meanings: `severity`, the passing rule, `None` skip
    counts, and the `allow_updates` / `connections` semantics;
  - a short usage example;
  - a link to the exit codes in `cli.md#exit-codes`, not a copy of them;
  - the note that the `verify_*` section functions are not part of the stable API.
- `docs/cli.md`, `verify` section:
  - synopsis `verify [--output-format text|json]`;
  - replace "accepts no subcommand-level flags";
  - explain that JSON is the full `verify_all` result and link `python-api.md`;
  - state that exit codes are the scripting contract and link `#exit-codes`.
