# Step 1 — Consolidate dev toolchain via `mcp-tools-py`

See `pr_info/steps/summary.md` (item 1). One commit.

## WHERE
- `pyproject.toml` → `[project.optional-dependencies].dev`
- `mcp-tools-sql.md` → the documented `dev` block (around line 667–674)

## WHAT
Reshape the `dev` extra to the target shape:

```toml
dev = [
    "mcp-workspace",
    "mcp-coder",
    "mcp-tools-py",        # single source for ruff + black/isort/pylint/mypy/tach/vulture/pytest...
    "pycycle>=0.0.8",      # KEEP — mcp-tools-py ships it only in its own [dev] extra
]
```

- **Add** `mcp-tools-py`.
- **Remove** the pins it provides as runtime deps: `black`, `isort`, `pylint`,
  `mypy`, `ruff`, `tach>=0.15.0`, `vulture>=2.13`, `pytest`, `pytest-asyncio`,
  `pytest-xdist`.
- **Remove** `pydeps>=1.12.0` (unused here — no CI check, no `pydeps_graph` script).
- **Keep** `mcp-workspace`, `mcp-coder`, `pycycle>=0.0.8`.

In `mcp-tools-sql.md`, delete the single line `    "pydeps",  # dependency graphs`
from the documented `dev` example. Leave the rest of that block as-is (it is
illustrative prose, not enforced config).

## HOW
- Edit `pyproject.toml` only inside the `dev = [ ... ]` list. Do not touch
  `mssql` / `postgresql` / `all-backends` extras or `[project].dependencies`.
- No import or code changes.

## ALGORITHM
N/A — declarative dependency edit.

## DATA
No runtime data structures. The install set is unchanged (`mcp-tools-py` was already
transitive via `mcp-coder`); only the *declaration* of tool versions moves.

## Verification (the "test" for this step)
1. `.[dev]` installs cleanly (CI does this; locally trust the resolver).
2. `black --check src tests` stays green — the one delta to watch
   (`mcp-tools-py` floors `black>=26.5.1`).
3. `mcp__tools-py__run_pylint_check`, `mcp__tools-py__run_pytest_check`
   (`-n auto -m "not sqlite_integration and not mssql_integration and not postgresql_integration"`),
   `mcp__tools-py__run_mypy_check` — all green.

## LLM prompt
> Read `pr_info/steps/summary.md` and `pr_info/steps/step_1.md`. Reshape the `dev`
> extra in `pyproject.toml` to exactly the four-entry target shape (add
> `mcp-tools-py`; remove `black`, `isort`, `pylint`, `mypy`, `ruff`, `tach`,
> `vulture`, `pytest`, `pytest-asyncio`, `pytest-xdist`, and `pydeps`; keep
> `mcp-workspace`, `mcp-coder`, `pycycle>=0.0.8`). Delete only the `pydeps` line from
> the documented `dev` block in `mcp-tools-sql.md`. Then run pylint, pytest (unit
> only) and mypy via the MCP tools and confirm `black --check src tests` is green.
> Commit as one change.
