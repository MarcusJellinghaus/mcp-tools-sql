# Step 9 — Move orchestrator helpers + create `verify_all`; slim CLI

**Goal:** Move the four discovery helpers, `collect_install_instructions`,
and `render_skip_m2_summary` into `verification/orchestrator.py`. Introduce
`verify_all()` that composes all sections. Slim `cli/commands/verify.py`
down to a thin printer that calls `verify_all` and feeds the result to
`_print_and_summarize`. After this step, `cli/commands/verify.py` is ~150
lines and the snapshot test still passes byte-for-byte.

## WHERE

### New files
- `src/mcp_tools_sql/verification/orchestrator.py`
- `tests/verification/test_orchestrator.py`

### Modified files
- `src/mcp_tools_sql/cli/commands/verify.py` — slimmed to ~150 lines
- `src/mcp_tools_sql/verification/__init__.py` — re-export `verify_all`
- `tests/cli/test_verify.py` — keep only CLI-level integration tests
  (target: ~300 lines; current: 1336 lines); delete
  `test_collect_install_instructions_aggregates_unique` (moves to
  test_orchestrator)
- `tach.toml` — prune `cli.commands.depends_on`: remove `backends`,
  `schema_tools`, `query_helpers`, `tool_builder`, `formatting`, and
  `utils` (now reached only via `mcp_tools_sql.verification`, or no longer
  used at all); see HOW for the safety check and the diff

## WHAT

### `verification/orchestrator.py`

```python
"""Orchestrator: section composition, discovery helpers, skip-summary."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from mcp_tools_sql.config.loader import (
    discover_query_config,
    load_database_config,
    load_query_config,
    resolve_connection,
)
from mcp_tools_sql.config.models import ConnectionConfig, QueryFileConfig
from mcp_tools_sql.verification._helpers import make_entry
from mcp_tools_sql.verification.builtin import verify_builtin
from mcp_tools_sql.verification.config_files import verify_config_files
from mcp_tools_sql.verification.connection import verify_connection
from mcp_tools_sql.verification.dependencies import verify_dependencies
from mcp_tools_sql.verification.environment import verify_environment
from mcp_tools_sql.verification.queries import verify_queries
from mcp_tools_sql.verification.updates import verify_updates

logger = logging.getLogger(__name__)


def _resolve_backend(
    config_path: Path | None,
    db_config_path: Path | None,
) -> str:
    """Best-effort backend resolution from configs."""
    # ... body moved verbatim ...


def _resolve_connection_for_verify(
    config_path: Path | None,
    db_config_path: Path | None,
) -> ConnectionConfig | None:
    """Best-effort connection resolution for the CONNECTION section."""
    # ... body moved verbatim ...


def _load_query_config_for_counts(config_path: Path | None) -> tuple[int, int]:
    """Return ``(query_count, update_count)`` from the project query config."""
    # ... body moved verbatim ...


def _load_query_config_for_m2(
    config_path: Path | None,
) -> QueryFileConfig | None:
    """Return the parsed QueryFileConfig or None on failure."""
    # ... body moved verbatim ...


def collect_install_instructions(
    sections: list[tuple[str, dict[str, Any]]],
) -> dict[str, Any]:
    """Aggregate non-empty install_hint strings from failed entries."""
    # ... body moved verbatim ...


def render_skip_m2_summary(query_count: int, update_count: int) -> str:
    """Return the one-line summary printed when M2 is skipped."""
    # ... body moved verbatim ...


def verify_all(
    config_path: Path | None,
    db_config_path: Path | None,
) -> tuple[list[tuple[str, dict[str, Any]]], str | None]:
    """Run every verification section and return (sections, skip_summary).

    Owns canonical section ordering:
    ENVIRONMENT → CONFIG → DEPENDENCIES → BUILTIN → CONNECTION →
    QUERIES → UPDATES → INSTALL INSTRUCTIONS
    """
    # ... composition logic moved from cli.commands.verify.run() ...
```

### `verification/__init__.py` (final)

```python
"""Verification engine for the `verify` CLI subcommand."""
from mcp_tools_sql.verification._helpers import VerifierEntry
from mcp_tools_sql.verification.builtin import verify_builtin
from mcp_tools_sql.verification.config_files import verify_config_files
from mcp_tools_sql.verification.connection import verify_connection
from mcp_tools_sql.verification.dependencies import verify_dependencies
from mcp_tools_sql.verification.environment import verify_environment
from mcp_tools_sql.verification.orchestrator import verify_all
from mcp_tools_sql.verification.queries import verify_queries
from mcp_tools_sql.verification.updates import verify_updates

__all__ = [
    "VerifierEntry",
    "verify_all",
    "verify_builtin",
    "verify_config_files",
    "verify_connection",
    "verify_dependencies",
    "verify_environment",
    "verify_queries",
    "verify_updates",
]
```

### `cli/commands/verify.py` (final, ~150 lines)

```python
"""verify subcommand — thin CLI printer over mcp_tools_sql.verification."""
from __future__ import annotations

import argparse
from typing import Any

from mcp_tools_sql.cli.parsers import WideHelpFormatter
from mcp_tools_sql.verification import verify_all

STATUS_SYMBOLS: dict[str, str] = {"ok": "[OK]", "err": "[ERR]", "warn": "[WARN]"}
_LABEL_WIDTH = 28


def _pad(text: str, width: int) -> str:
    ...

def _format_row(status: str, label: str, value: str = "", error: str = "") -> str:
    ...

def _print_section(title: str) -> None:
    ...

def _compute_exit_code(error_count: int) -> int:
    ...

def add_subparser(subparsers: argparse._SubParsersAction) -> None:  # type: ignore[type-arg]
    ...

def run(args: argparse.Namespace) -> int:
    """Entry point for the ``verify`` subcommand."""
    sections, skip_summary = verify_all(args.config, args.database_config)
    return _print_and_summarize(sections, skip_summary=skip_summary)


def _print_and_summarize(
    sections: list[tuple[str, dict[str, Any]]],
    *,
    skip_summary: str | None = None,
) -> int:
    """Print every section's rows and the trailing summary line."""
    # ... iterates sections as-is; never reorders ...
```

### `tests/verification/test_orchestrator.py`

New unit tests for `verify_all`:
- It returns a tuple of `(sections, skip_summary)`.
- Section order is `ENVIRONMENT, CONFIG, DEPENDENCIES, BUILTIN` then
  conditionally `CONNECTION, QUERIES, UPDATES`, then `INSTALL INSTRUCTIONS`
  (only when non-empty).
- `skip_summary` is `None` on the happy path, a string when CONNECTION
  fails or query/update sections were skipped.

Plus migration of `test_collect_install_instructions_aggregates_unique`
from `tests/cli/test_verify.py`.

### `tests/cli/test_verify.py` (final shape)

Keep only these CLI-level integration tests:
- `test_verify_run_prints_environment_and_config_sections`
- `test_verify_summary_line_format`
- `test_verify_exit_code_0_when_all_ok`
- `test_verify_exit_code_1_when_config_missing`
- `test_verify_run_includes_dependencies_and_builtin_sections`
- `test_verify_run_uses_unknown_backend_when_config_invalid`
- `test_verify_sqlite_full_run_all_ok`
- `test_verify_detects_missing_connection`
- `test_verify_run_skips_m2_on_connection_failure`
- `test_verify_warn_for_sensitive_keys_in_query_config`
- `test_verify_full_sqlite_run_returns_0`
- `test_verify_full_run_returns_1_on_error`
- `test_verify_full_run_with_queries_and_updates_returns_0`
- `test_verify_cli_queries_updates_snapshot`

Imports drop everything except `mcp_tools_sql.cli.commands.verify`.
Keep the `_make_args`, `valid_query_config`, `valid_database_config`
helpers/fixtures. Keep `_extract_section`, `_prepare_snapshot_db`.
**Inline whatever the snapshot test still needs** (no cross-conftest
reach into `tests/verification/`).

## HOW

### Recommended tool sequence

```
move_symbol(
    source_file="src/mcp_tools_sql/cli/commands/verify.py",
    symbol_names=[
        "_resolve_backend",
        "_resolve_connection_for_verify",
        "_load_query_config_for_counts",
        "_load_query_config_for_m2",
        "collect_install_instructions",
        "render_skip_m2_summary",
    ],
    dest_file="src/mcp_tools_sql/verification/orchestrator.py",
)
```

Then manually:
1. Add the `verify_*` imports at the top of `orchestrator.py`.
2. Write `verify_all` by copying the composition logic from
   `cli.commands.verify.run()` — but only the section-building parts,
   not the printing/summary. Return `(sections, skip_summary)`.
3. Re-export `verify_all` from `verification/__init__.py`.
4. **Rewrite `cli/commands/verify.py`** to be a thin printer (see "final
   shape" above). All section-building logic is gone; `run()` is now ~3
   lines calling `verify_all` and `_print_and_summarize`.
5. Move `test_collect_install_instructions_aggregates_unique` to
   `test_orchestrator.py`. Write 2–3 new `verify_all` unit tests.
6. Trim `tests/cli/test_verify.py` to the listed final shape.

### Confirm line count

Run:

```
mcp__mcp-workspace__check_file_size(max_lines=600)
```

`src/mcp_tools_sql/cli/commands/verify.py` should now be well under the
600-line limit (target ~150 lines).

Also confirm `tests/cli/test_verify.py` is under the limit (target ~300
lines, down from 1336):

```
mcp__mcp-workspace__check_file_size(max_lines=600)
# for tests/cli/test_verify.py
```

### Prune `cli.commands.depends_on` in `tach.toml`

Once `cli/commands/verify.py` is slimmed, the only direct imports it makes
are `argparse`, `mcp_tools_sql.cli.parsers`, and
`mcp_tools_sql.verification`. The following entries become unused and must
be pruned from the `cli.commands` module's `depends_on`:

- `mcp_tools_sql.backends`
- `mcp_tools_sql.schema_tools`
- `mcp_tools_sql.query_helpers`
- `mcp_tools_sql.tool_builder`
- `mcp_tools_sql.formatting`
- `mcp_tools_sql.utils`

**Safety check before pruning (mandatory).** Other modules in
`src/mcp_tools_sql/cli/commands/` (currently: `init.py`; potentially future
`query.py`, `update.py`, etc.) may also use these. Run:

```
mcp__mcp-workspace__search_files(
    pattern="src/mcp_tools_sql/cli/commands/*.py",
    text="<module_name>",   # one of: backends, schema_tools, query_helpers,
                            # tool_builder, formatting, utils
)
```

for each candidate prune. **Only prune an entry if NO file under
`src/mcp_tools_sql/cli/commands/` imports from that module.** As of this
plan, `init.py` only imports `mcp_tools_sql.cli.parsers` and
`mcp_tools_sql.config.authoring`, so all six are confirmed safe to prune;
re-verify at implementation time in case new commands have landed.

**`tach.toml` diff (after pruning):**

```toml
[[modules]]
path = "mcp_tools_sql.cli.commands"
layer = "entry_point"
depends_on = [
    { path = "mcp_tools_sql.cli" },
    { path = "mcp_tools_sql.config" },
    { path = "mcp_tools_sql.verification" },
]
```

(Removed: `backends`, `schema_tools`, `query_helpers`, `tool_builder`,
`formatting`, `utils`. Kept: `cli`, `config` — needed by `init.py` for
`config.authoring` — and the new `verification`.)

## ALGORITHM (for `verify_all`)

```
sections = []
sections.append(("ENVIRONMENT", verify_environment()))
sections.append(("CONFIG", verify_config_files(cfg, db_cfg)))
backend = _resolve_backend(cfg, db_cfg)
sections.append(("DEPENDENCIES", verify_dependencies(backend)))
sections.append(("BUILTIN", verify_builtin()))

skip_summary = None
conn = _resolve_connection_for_verify(cfg, db_cfg)
if conn is not None:
    conn_result, open_backend = verify_connection(conn)
    sections.append(("CONNECTION", conn_result))
    try:
        if conn_result.get("overall_ok") and open_backend is not None:
            qcfg = _load_query_config_for_m2(cfg)
            if qcfg is not None:
                sections.append(("QUERIES",
                    verify_queries(qcfg.queries, conn.backend, open_backend)))
                sections.append(("UPDATES",
                    verify_updates(qcfg.updates, conn.backend, open_backend)))
            # NOTE: When qcfg is None on the happy path (connection succeeded
            # but query-config load failed), the QUERIES/UPDATES sections are
            # SILENTLY OMITTED with NO skip_summary. This is intentional and
            # mirrors the current cli.commands.verify.run() behaviour: the
            # CONFIG section already reported the failure via its
            # query_config_parse entry, so there is nothing more to say here.
            # Do NOT "fix" this by adding a skip_summary call — that would
            # double-report the same failure and break the snapshot.
        else:
            n_q, n_u = _load_query_config_for_counts(cfg)
            skip_summary = render_skip_m2_summary(n_q, n_u)
    finally:
        if open_backend is not None:
            open_backend.close()

install = collect_install_instructions(sections)
if any(k != "overall_ok" for k in install):
    sections.append(("INSTALL INSTRUCTIONS", install))

return sections, skip_summary
```

## DATA

- `verify_all` return: `tuple[list[tuple[str, dict[str, Any]]], str | None]`.
- The list element `(section_title, section_dict)`. Section dict is
  `{<entry_key>: dict[str, Any], ..., "overall_ok": bool}`.

## Checks

Run after edits:
- `mcp__mcp-tools-py__run_pylint_check`
- `mcp__mcp-tools-py__run_mypy_check`
- `mcp__mcp-tools-py__run_pytest_check(extra_args=["-n", "auto", "-m", "not git_integration and not claude_cli_integration and not claude_api_integration and not formatter_integration and not github_integration and not langchain_integration"])`
- `mcp__mcp-tools-py__run_tach_check` — must pass with the pruned
  `cli.commands.depends_on`.
- `mcp__mcp-tools-py__run_lint_imports_check` — must pass with the pruned
  `cli.commands.depends_on`.
- `mcp__mcp-workspace__check_file_size(max_lines=600)` for
  `src/mcp_tools_sql/cli/commands/verify.py` — must be ≤ 600 (target ~150).
- `mcp__mcp-workspace__check_file_size(max_lines=600)` for
  `tests/cli/test_verify.py` — must be ≤ 600 (target ~300, down from 1336).

All must pass. The CLI snapshot test
(`test_verify_cli_queries_updates_snapshot`) must still pass byte-equal.

## LLM Prompt

> Read `pr_info/steps/summary.md` and `pr_info/steps/step_9.md`. Implement
> step 9 — the largest step:
>
> 1. Move the four discovery helpers (`_resolve_backend`,
>    `_resolve_connection_for_verify`, `_load_query_config_for_counts`,
>    `_load_query_config_for_m2`), plus `collect_install_instructions`
>    and `render_skip_m2_summary`, from `cli/commands/verify.py` to a
>    new file `src/mcp_tools_sql/verification/orchestrator.py`. Use
>    `move_symbol`.
> 2. Add a new `verify_all(config_path, db_config_path)` function to
>    `orchestrator.py` that composes all sections in the canonical order
>    (ENVIRONMENT → CONFIG → DEPENDENCIES → BUILTIN → CONNECTION →
>    QUERIES → UPDATES → INSTALL INSTRUCTIONS) and returns
>    `(sections, skip_summary)`. Use the ALGORITHM pseudocode in step_9.md
>    as a literal guide — it's a direct extraction of the current
>    `run()` composition logic.
> 3. Re-export `verify_all` from `verification/__init__.py`.
> 4. **Rewrite `cli/commands/verify.py`** to a thin ~150-line printer:
>    keep `STATUS_SYMBOLS`, `_LABEL_WIDTH`, `_pad`, `_format_row`,
>    `_print_section`, `_compute_exit_code`, `add_subparser`,
>    `_print_and_summarize`, and a 3-line `run(args)` that calls
>    `verify_all(args.config, args.database_config)` and feeds the
>    result to `_print_and_summarize`. Remove all other code. Preserve
>    the existing implementations of `_pad`, `_format_row`,
>    `_print_section`, `_compute_exit_code`, and `_print_and_summarize`
>    verbatim from the current `cli/commands/verify.py` — these control
>    the byte-exact snapshot test output and must not be modified during
>    the move.
> 5. Create `tests/verification/test_orchestrator.py` with the moved
>    `test_collect_install_instructions_aggregates_unique` plus 2–3 new
>    `verify_all` tests covering: tuple shape, section ordering, and
>    the `skip_summary is None` happy path.
> 6. Trim `tests/cli/test_verify.py` to the final shape listed in
>    step_9.md (CLI-level integration tests only, including the
>    byte-exact snapshot test). Target: ~300 lines, down from 1336.
> 7. **Prune `tach.toml`.** After the slim shim is in place, remove the
>    now-unused entries from `cli.commands.depends_on`: `backends`,
>    `schema_tools`, `query_helpers`, `tool_builder`, `formatting`, and
>    `utils`. **Before** pruning, run the safety check described in the
>    HOW section (`search_files` across
>    `src/mcp_tools_sql/cli/commands/*.py` for each candidate) — only
>    remove entries that no `cli/commands/*.py` file still uses. Then
>    re-run `run_tach_check` and `run_lint_imports_check`; both must pass.
>
> Run all checks plus `check_file_size(max_lines=600)` for BOTH
> `src/mcp_tools_sql/cli/commands/verify.py` (target ~150) AND
> `tests/cli/test_verify.py` (target ~300). Confirm the snapshot test
> still passes byte-for-byte. All checks must pass before committing.
