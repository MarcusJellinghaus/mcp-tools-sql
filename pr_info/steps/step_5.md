# Step 5 — Short summary renderer and `verify --short`

## LLM prompt

> Read `pr_info/steps/summary.md` (section 4), then implement **this step only**
> (`pr_info/steps/step_5.md`). Do TDD: write `tests/verification/test_render.py` and the
> `--short` tests first, then implement. `tests/cli/test_verify.py` must not be edited and
> must pass; it uses `verify_cmd._format_row` and `verify_cmd._LABEL_WIDTH`. Run pylint,
> pytest (`-n auto`), mypy, ruff, lint-imports, tach and format_code, then make one commit.

## WHERE

- `src/mcp_tools_sql/verification/render.py` (**new**)
- `src/mcp_tools_sql/cli/commands/verify.py`
- `tests/verification/test_render.py` (**new**)
- `tests/cli/test_verify_output.py`
- `docs/cli.md`

## WHAT

`verification/render.py`. Move `STATUS_SYMBOLS`, the label width and `format_row` here
unchanged from the CLI:

```python
STATUS_SYMBOLS: dict[str, str] = {"ok": "[OK]", "err": "[ERR]", "warn": "[WARN]"}
LABEL_WIDTH = 28
def format_row(status: str, label: str, value: str = "", error: str = "") -> str
def row_status(entry: CheckResult) -> Literal["ok", "warn", "err"]
def render_short(result: VerifyResult) -> str
def _summary_line(result: VerifyResult) -> str
```

`cli/commands/verify.py`:

```python
from mcp_tools_sql.verification.render import LABEL_WIDTH as _LABEL_WIDTH
from mcp_tools_sql.verification.render import format_row as _format_row
from mcp_tools_sql.verification.render import render_short, row_status
```

The full printer uses `row_status`. `add_subparser` adds `--short` (`store_true`). `run`
reads it with `getattr(args, "short", False)`.

## HOW

- `render_short` reads sections only by `title` / `ok` / `checks`, plus `summary` and the
  skip counts. It never parses row labels.
- `--short` affects text output only. In JSON mode it is ignored. In `--short` mode, print
  `render_short(result)` and return the same exit code as the full output. Do not print
  the "N checks passed" totals line.

## ALGORITHM

```
by_title = {s["title"]: s for s in result["sections"]}
config = "Config loaded." if by_title["CONFIG"]["ok"] else "Config has errors."
conns = "not checked (targets unresolved)" if "CONNECTION" not in by_title else
        "; ".join(p for p in [", ".join(ok names) + " reachable", ", ".join(bad names) + " unreachable"] if names non-empty)
state(kind) = "not checked (connection failed)" if skipped_queries is not None else
              "not checked" if kind not in by_title else "OK" if by_title[kind]["ok"] else "with errors"
entries = f"{q} queries, {u} updates {sq}" if sq == su else f"{q} queries {sq}, {u} updates {su}"
          + " (not exposed: allow_updates=false)" if allow_updates is False
line = f"{config} Connections: {conns}. {entries}."
then per section with rows where row_status != "ok": "", "=== TITLE ===", format_row(...) for each
```

`row_status`: `"ok"` if `entry["ok"]`, else `"warn"` if `severity == "warning"`, else
`"err"`.

## DATA

All passing, connections A, B, C, 12 queries, 3 updates:

```
Config loaded. Connections: A, B, C reachable. 12 queries, 3 updates OK.
```

With `allow_updates=False`:
`... 12 queries, 3 updates OK (not exposed: allow_updates=false).`

## Tests (write first)

`tests/verification/test_render.py`. Build `VerifyResult` dicts by hand with `make_entry`
and `make_warn_entry`.

- All passing returns exactly the one-line example above. No row lines appear.
- An ERR row in QUERIES gives `"12 queries with errors, 3 updates OK"`, then a blank line,
  `=== QUERIES ===`, and that row formatted as `[ERR]  ...  - <error>`. OK rows are not
  shown.
- A WARN row in CONFIG (CONFIG `ok=True`) gives `Config loaded.`, and the `[WARN]` row
  under `=== CONFIG ===`.
- No CONNECTION section: `Connections: not checked (targets unresolved).` and
  `0 queries, 0 updates not checked.`
- `skipped_queries=2, skipped_updates=1`: `2 queries, 1 updates not checked (connection failed).`
- `connections={"A": True, "B": False}`: `Connections: A reachable; B unreachable.`
- `allow_updates=False` adds the suffix. `None` and `True` add nothing.

`tests/cli/test_verify_output.py`:

- `verify --short` on valid sqlite configs: stdout starts with `Config loaded.`, has no
  `checks passed` line, and exits 0.
- `verify --short` with a failing connection: stdout contains `=== CONNECTION ===` and
  `[ERR]`, and exits 1.

## Docs

`docs/cli.md`, `verify`: document `--short` (summary line plus ERR/WARN rows by section,
same exit codes), with the all-pass example.
