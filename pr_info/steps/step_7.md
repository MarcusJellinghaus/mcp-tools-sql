# Step 7 — Enforce the `mcp_coder_utils` shim boundary with import-linter

## LLM prompt

> Read `pr_info/steps/summary.md`, then implement `pr_info/steps/step_7.md` exactly.
> Add the import-linter contract and correct CLAUDE.md. Run lint-imports, format,
> pylint, pytest (`-n auto`), mypy; all must pass. Produce exactly one commit.

## WHERE

- `.importlinter`
- `.claude/CLAUDE.md` — "Shared Libraries" section

## WHAT / HOW

### `.importlinter`

Add `include_external_packages = True` to `[importlinter]`:

```ini
[importlinter]
root_package = mcp_tools_sql
root_package_paths = src
include_external_packages = True
```

Append (mirrors mcp_coder's `mcp_coder_utils_isolation`):

```ini
[importlinter:contract:mcp_coder_utils_isolation]
name = MCP Coder Utils Isolation
type = forbidden
source_modules =
    mcp_tools_sql
forbidden_modules =
    mcp_coder_utils
ignore_imports =
    mcp_tools_sql.utils.** -> mcp_coder_utils
```

- Use the `**` wildcard, not per-shim lines: an `ignore_imports` entry that matches nothing is an error.
- Existing `layers` and `forbidden-imports` contracts unchanged.
- Tests stay outside the contract (`tests` is not a root package).

### `.claude/CLAUDE.md` — replace the "Shared Libraries" paragraph

```markdown
## Shared Libraries

`log_utils`, `user_app_data` and `subprocess_runner` in `src/mcp_tools_sql/utils/` are thin shims over `mcp-coder-utils`. Always import through the local shims (e.g. `from mcp_tools_sql.utils.log_utils import ...`), not from `mcp_coder_utils` directly. Enforced by import-linter (`mcp_coder_utils_isolation` contract in `.importlinter`).
```

## DATA

None.

## Checks

- `mcp__mcp-tools-py__run_lint_imports_check()` → all contracts KEPT. If any contract is broken or lint-imports errors on the config, write one line to `pr_info/.blocked.txt` with the contract name and stop.
- `mcp__mcp-workspace__search_files(pattern="mcp_coder_utils", glob="src/**/*.py")` → imports only under `src/mcp_tools_sql/utils/` (string mentions in `verification/environment.py` are not imports).
- format, pylint, pytest (`-n auto`), mypy pass.

## Commit

`chore(import-linter): enforce mcp_coder_utils shim boundary`
