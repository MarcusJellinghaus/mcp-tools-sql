# Step 1 — Foundation: subpackage skeleton + config updates

**Goal:** Create the `mcp_tools_sql.verification` subpackage with its shared
helpers (`VerifierEntry` + `make_entry`), wire it into `tach.toml` and
`.importlinter`, and set up the `tests/verification/` test directory.
After this step, the CLI shim still owns all `verify_*` functions but
imports `make_entry` from the new location.

### Rename rationale (`_entry` → `make_entry`)

The original CLI module name was `_entry`. With the helper now living in a
different module and being imported by all sibling submodules + the CLI shim,
an underscore prefix would trigger pylint's `protected-access` warning on
every cross-module import. Dropping the underscore (renamed to `make_entry`)
sidesteps the lint noise. The semantic intent — "not part of the public API;
used only within the `verification` subpackage and the CLI shim during
transition" — is preserved by convention: `make_entry` is simply not
re-exported from `verification/__init__.py`.

(`VerifierEntry` TypedDict keeps its name — it IS public and is re-exported
from `__init__.py`.)

## WHERE

### New files
- `src/mcp_tools_sql/verification/__init__.py`
- `src/mcp_tools_sql/verification/_helpers.py`
- `tests/verification/__init__.py`
- `tests/verification/conftest.py`
- `tests/verification/test_helpers.py`

**Convention check (`tests/verification/__init__.py`):** Verified that the
existing test subpackages `tests/cli/`, `tests/backends/`, and
`tests/config/` all contain `__init__.py`. The new
`tests/verification/__init__.py` follows the same convention. (If this
convention ever changes — i.e., the other subpackages drop their
`__init__.py` — drop this one too; do NOT introduce an inconsistency.)

### Modified files
- `src/mcp_tools_sql/cli/commands/verify.py` — remove the local `_entry`
  definition; import the renamed helper as
  `from mcp_tools_sql.verification._helpers import make_entry`, and replace
  every call site (`_entry(...)` → `make_entry(...)`) in the CLI shim
- `tach.toml` — add `[[modules]]` entry for `mcp_tools_sql.verification`;
  add `mcp_tools_sql.verification` to `cli.commands.depends_on`
- `.importlinter` — add `mcp_tools_sql.verification` as its own layer line
  **above** `mcp_tools_sql.schema_tools | ...`

## WHAT

### `verification/_helpers.py`

```python
from __future__ import annotations
from typing import Any, TypedDict


class VerifierEntry(TypedDict):
    """Standard shape of a single verifier result row."""
    ok: bool
    value: str
    error: str
    install_hint: str


def make_entry(
    *,
    ok: bool,
    value: str = "",
    error: str = "",
    install_hint: str = "",
) -> dict[str, Any]:
    """Build a single verifier result entry with the standard shape.

    Not part of the public ``mcp_tools_sql.verification`` API — used only
    within the subpackage's submodules and (during the extraction) the CLI
    shim. Intentionally NOT re-exported from ``__init__.py``. The name
    deliberately lacks an underscore prefix to avoid pylint
    ``protected-access`` warnings on cross-module imports.
    """
    return {"ok": ok, "value": value, "error": error, "install_hint": install_hint}
```

### `verification/__init__.py`

```python
"""Verification engine for the `verify` CLI subcommand."""
from mcp_tools_sql.verification._helpers import VerifierEntry

__all__ = ["VerifierEntry"]
```

(Section functions get added to `__all__` in steps 2–9.)

### `tests/verification/conftest.py`

```python
@pytest.fixture
def sqlite_backend(sqlite_db: Path) -> Generator[SQLiteBackend, None, None]:
    """Open a connected SQLiteBackend on the shared `sqlite_db` fixture."""
    backend = SQLiteBackend(ConnectionConfig(backend="sqlite", path=str(sqlite_db)))
    backend.connect()
    yield backend
    backend.close()
```

This replaces the inline `_open_sqlite_backend` helper from
`tests/cli/test_verify.py` (which is removed in step 7/8 alongside its
consumers). `sqlite_db` is inherited from `tests/conftest.py`.

### `tests/verification/test_helpers.py`

Smoke tests for the new helpers:
- `make_entry(ok=True)` returns `{"ok": True, "value": "", "error": "", "install_hint": ""}`.
- `make_entry(ok=False, value="x", error="e", install_hint="h")` returns expected dict.
- `VerifierEntry` is a TypedDict with the four expected keys.

## HOW

### `tach.toml` patch

Add a new module block (anywhere in the `[[modules]]` section; group with
other `tool_implementation` modules for readability):

```toml
[[modules]]
path = "mcp_tools_sql.verification"
layer = "tool_implementation"
depends_on = [
    { path = "mcp_tools_sql.backends" },
    { path = "mcp_tools_sql.config" },
    { path = "mcp_tools_sql.schema_tools" },
    { path = "mcp_tools_sql.query_helpers" },
    { path = "mcp_tools_sql.utils" },
]
```

Extend `mcp_tools_sql.cli.commands.depends_on` to include the new module:

```toml
[[modules]]
path = "mcp_tools_sql.cli.commands"
layer = "entry_point"
depends_on = [
    { path = "mcp_tools_sql.cli" },
    { path = "mcp_tools_sql.backends" },
    { path = "mcp_tools_sql.config" },
    { path = "mcp_tools_sql.schema_tools" },
    { path = "mcp_tools_sql.query_helpers" },
    { path = "mcp_tools_sql.tool_builder" },
    { path = "mcp_tools_sql.formatting" },
    { path = "mcp_tools_sql.utils" },
    { path = "mcp_tools_sql.verification" },     # NEW
]
```

### `.importlinter` patch

Insert `mcp_tools_sql.verification` as its own line **above** the
`schema_tools | ...` line. See `summary.md` "Architectural / Design Changes
→ Import-linter layers contract" for the directionality rationale.

```ini
[importlinter:contract:layers]
name = Layered Architecture
type = layers
layers =
    mcp_tools_sql.main
    mcp_tools_sql.cli
    mcp_tools_sql.server
    mcp_tools_sql.verification
    mcp_tools_sql.schema_tools | mcp_tools_sql.query_tools | mcp_tools_sql.update_tools | mcp_tools_sql.validation_tools
    mcp_tools_sql.query_helpers
    mcp_tools_sql.tool_builder
    mcp_tools_sql.backends | mcp_tools_sql.formatting | mcp_tools_sql.tool_logging
    mcp_tools_sql.config
    mcp_tools_sql.utils
```

### `cli/commands/verify.py` patch

Replace the local `_entry` definition with an import of the renamed helper,
then update every call site:

```python
from mcp_tools_sql.verification._helpers import make_entry
```

Delete the local `def _entry(...)` block (lines ~67–82 in current file)
and replace every `_entry(...)` call in the CLI shim with `make_entry(...)`.

## ALGORITHM

No algorithm — pure code reorganization.

## DATA

- `VerifierEntry` TypedDict: `{ok: bool, value: str, error: str, install_hint: str}`
- `make_entry(...)` return: `dict[str, Any]` with the four keys above.
  *(Return type stays `dict[str, Any]` rather than `VerifierEntry` to avoid
  a cascade of type-narrowing changes in callers; section dicts mix entry
  dicts and `overall_ok: bool` and would otherwise need union types.)*

## Checks

Run after edits:
- `mcp__mcp-tools-py__run_pylint_check`
- `mcp__mcp-tools-py__run_mypy_check`
- `mcp__mcp-tools-py__run_pytest_check(extra_args=["-n", "auto", "-m", "not git_integration and not claude_cli_integration and not claude_api_integration and not formatter_integration and not github_integration and not langchain_integration"])`
- `mcp__mcp-tools-py__run_tach_check`
- `mcp__mcp-tools-py__run_lint_imports_check`

All must pass.

## LLM Prompt

> Read `pr_info/steps/summary.md` and `pr_info/steps/step_1.md`. Implement
> step 1 exactly as specified: create the `mcp_tools_sql.verification`
> subpackage with `_helpers.py` (containing `VerifierEntry` TypedDict and
> `make_entry()` — note the rename from `_entry`; rationale in the step's
> intro), create the `tests/verification/` directory with `__init__.py`,
> `conftest.py` (with the `sqlite_backend` fixture), and a smoke
> `test_helpers.py`. Update `tach.toml` (add `verification` module, extend
> `cli.commands.depends_on`) and `.importlinter` (add `verification` line
> above `schema_tools|...`). Update `cli/commands/verify.py` to import
> `make_entry` from `verification._helpers`, delete the local
> `_entry` definition, and replace every `_entry(...)` call site with
> `make_entry(...)`. Do NOT move any `verify_*` section function in this
> step — that comes in later steps. Run pylint, mypy, pytest (with the
> standard exclusion markers), tach, and lint-imports; all must pass
> before committing.
