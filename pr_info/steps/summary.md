# Extract verify engine into `mcp_tools_sql.verification`

**Issue:** [#21](../../) — Extract verify logic from `cli.commands` into `mcp_tools_sql.verification`

## Overview

`src/mcp_tools_sql/cli/commands/verify.py` is **973 lines** (over the 600-line
project limit) and mixes CLI presentation with real verification logic. The
`verify_*` functions already return structured dicts but live inside an
entry-point module.

This implementation extracts the verification engine into a new tool-layer
subpackage `mcp_tools_sql.verification`, leaving `cli/commands/verify.py` as a
thin printer shim (~150 lines).

## Architectural / Design Changes

### New tool-layer subpackage

A new `mcp_tools_sql.verification` subpackage sits at the **tool_implementation**
layer (same as `schema_tools`, `query_tools`, etc.). It is split by section,
one file per `verify_*` function. The orchestrator owns canonical section
ordering and full section composition (INSTALL INSTRUCTIONS append-if-non-empty,
skip-M2 summary).

### Public API surface

`mcp_tools_sql.verification` re-exports:
- `verify_all(config_path, db_config_path)` — orchestrator
- `verify_environment`, `verify_config_files`, `verify_dependencies`,
  `verify_builtin`, `verify_connection`, `verify_queries`, `verify_updates`
- `VerifierEntry` TypedDict

Per-entry helpers (`verify_one_query`, `verify_one_update`) remain
submodule-internal (used by the snapshot regression test which imports them
from their submodules directly).

### Orchestrator contract

```python
def verify_all(
    config_path: Path | None,
    db_config_path: Path | None,
) -> tuple[list[tuple[str, dict[str, Any]]], str | None]:
    """Returns (sections, skip_summary).

    Owns the canonical section order:
    ENVIRONMENT → CONFIG → DEPENDENCIES → BUILTIN → CONNECTION →
    QUERIES → UPDATES → INSTALL INSTRUCTIONS

    Owns the "only append INSTALL INSTRUCTIONS if non-empty" check.
    The CLI shim is a pure printer that iterates `sections` as-is.
    """
```

### Typing

`VerifierEntry` TypedDict (in `verification/_helpers.py`) types the
**entry dicts** returned by `make_entry()`. Section dicts stay as
`dict[str, Any]` because they are heterogeneous (`overall_ok: bool`
alongside entries).

### CLI shim shape

`cli/commands/verify.py` keeps only:
- `STATUS_SYMBOLS`, `_LABEL_WIDTH`
- `_pad`, `_format_row`, `_print_section`, `_compute_exit_code`
- `_print_and_summarize`
- `add_subparser`, `run` (calls `verify_all`, hands result to `_print_and_summarize`)

Target: ~150 lines.

### Tach configuration

- New `[[modules]]` entry: `mcp_tools_sql.verification` at `tool_implementation`
  layer with `depends_on = [backends, config, schema_tools, query_helpers, utils]`.
- `cli.commands.depends_on` gains `mcp_tools_sql.verification`.

### Import-linter layers contract

Add `mcp_tools_sql.verification` on its **own line** in the `layers` contract.

> **⚠️ Correction from issue text:** The issue says "placed below
> `schema_tools | ...` and above `query_helpers`". The author was using
> "below" in the architecture-stack sense (= lower abstraction). In
> `.importlinter` syntax, **earlier in the file = higher layer**, and
> verification imports from `schema_tools.load_default_queries`. Therefore
> the line must be placed **above** the `schema_tools|...` line in the file,
> not below. Empirically verified: in the current config, `main` (1st)
> imports `cli` (2nd), and `cli` (2nd) imports `schema_tools` (4th) — so
> "earlier in list = higher layer = may import later items".

Correct placement:

```
mcp_tools_sql.main
mcp_tools_sql.cli
mcp_tools_sql.server
mcp_tools_sql.verification           <-- NEW (its own line)
mcp_tools_sql.schema_tools | mcp_tools_sql.query_tools | mcp_tools_sql.update_tools | mcp_tools_sql.validation_tools
mcp_tools_sql.query_helpers
...
```

This still satisfies the issue's intent ("own line because siblings can't
import each other") and the import constraint ("must import from
schema_tools and query_helpers").

### Test reorganization

- Engine tests move from `tests/cli/test_verify.py` (1336 lines) into seven
  per-section files under `tests/verification/`.
- `tests/cli/test_verify.py` keeps only CLI-level tests: `run()` dispatch,
  `_print_and_summarize` behavior, the byte-exact snapshot regression test.
- **`sqlite_db` fixture is NOT moved** — it lives in `tests/conftest.py` and
  is inherited by all subdirectories; ~10 other test files depend on it
  (`test_query_tools`, `test_schema_tools`, `test_update_tools`,
  `test_validation_tools`, `test_default_queries`, `backends/test_sqlite`).
  Moving it would break unrelated tests. *(Deviation from issue text §9;
  the issue's wording would break the build.)*
- The local `_open_sqlite_backend` helper from `tests/cli/test_verify.py`
  moves to `tests/verification/conftest.py` as a pytest fixture.
- The Kerberos test monkeypatch retargets from
  `mcp_tools_sql.cli.commands.verify.create_backend` to
  `mcp_tools_sql.verification.connection.create_backend`.

### Architecture doc

`docs/architecture/architecture.md` gains a `verification` row in the module
table, a `verification` entry in the layer diagram (just below the Tool
Layer), and a one-paragraph note describing the extraction.

## Folders / modules / files

### Created

- `src/mcp_tools_sql/verification/__init__.py`
- `src/mcp_tools_sql/verification/_helpers.py`
- `src/mcp_tools_sql/verification/environment.py`
- `src/mcp_tools_sql/verification/config_files.py`
- `src/mcp_tools_sql/verification/dependencies.py`
- `src/mcp_tools_sql/verification/builtin.py`
- `src/mcp_tools_sql/verification/connection.py`
- `src/mcp_tools_sql/verification/queries.py`
- `src/mcp_tools_sql/verification/updates.py`
- `src/mcp_tools_sql/verification/orchestrator.py`
- `tests/verification/__init__.py`
- `tests/verification/conftest.py`
- `tests/verification/test_environment.py`
- `tests/verification/test_config_files.py`
- `tests/verification/test_dependencies.py`
- `tests/verification/test_builtin.py`
- `tests/verification/test_connection.py`
- `tests/verification/test_queries.py`
- `tests/verification/test_updates.py`
- `tests/verification/test_orchestrator.py`

### Modified

- `src/mcp_tools_sql/cli/commands/verify.py` — slimmed to ~150 lines
- `tests/cli/test_verify.py` — engine tests removed, CLI-only tests kept
- `tach.toml` — add `verification` module, extend `cli.commands.depends_on`
- `.importlinter` — add `verification` layer line above `schema_tools|...`
- `docs/architecture/architecture.md` — layer diagram, module table, extraction note

### Unchanged but referenced

- `tests/conftest.py` (root `sqlite_db` fixture) — left in place

## Implementation Steps

Each step is a single atomic commit (tests + implementation + checks passing).

1. **[Step 1](step_1.md)** — Foundation: subpackage skeleton, `_helpers.py`,
   `tach.toml` + `.importlinter` updates, `tests/verification/` skeleton.
2. **[Step 2](step_2.md)** — Move `verify_environment` to
   `verification/environment.py`; move its tests.
3. **[Step 3](step_3.md)** — Move `verify_config_files` to
   `verification/config_files.py`; move its tests.
4. **[Step 4](step_4.md)** — Move `verify_dependencies` (incl. mssql/postgresql
   helpers) to `verification/dependencies.py`; move its tests.
5. **[Step 5](step_5.md)** — Move `verify_builtin` to `verification/builtin.py`;
   move its tests.
6. **[Step 6](step_6.md)** — Move `verify_connection` + `_check_kerberos_ticket`
   to `verification/connection.py`; retarget monkeypatch; move tests.
7. **[Step 7](step_7.md)** — Move `verify_queries` + `verify_one_query` +
   helpers to `verification/queries.py`; move tests.
8. **[Step 8](step_8.md)** — Move `verify_updates` + `verify_one_update` +
   helpers to `verification/updates.py`; carry the two load-bearing NOTE
   comments verbatim; move tests.
9. **[Step 9](step_9.md)** — Move orchestrator helpers + create `verify_all`
   in `verification/orchestrator.py`; slim `cli/commands/verify.py` to a
   thin printer; verify snapshot test still passes byte-for-byte.
10. **[Step 10](step_10.md)** — Update `docs/architecture/architecture.md`.

## Risk register

- **Snapshot byte-equality**: Steps 7 and 8 move dict-insertion-order-sensitive
  code. Use `move_symbol` to relocate verbatim; do not refactor.
- **Monkeypatch retarget**: Step 6 must keep `create_backend` importable at
  module level in `verification/connection.py` so
  `monkeypatch.setattr("mcp_tools_sql.verification.connection.create_backend", ...)`
  resolves.
- **Layer contract**: Step 1 establishes the new layer line. Get this right
  upfront (see correction above) or every subsequent step will lint-fail.
