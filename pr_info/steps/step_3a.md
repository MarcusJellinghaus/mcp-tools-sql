# Step 3a — `cli/` package skeleton + `main.py` dispatch refactor

**Reference**: [summary.md](./summary.md) — section "New `cli/` package"
**Commit**: 3a of 10
**Goal**: Stand up the dispatch infrastructure. Both subcommands raise `NotImplementedError` for now; steps 3b–9 fill them in. `--help` polish (mcp_coder-parity) lands in step 3b.

> **Note about `tomlkit`**: `tomlkit>=0.13.0` has **already** been added to `pyproject.toml` runtime dependencies (uncommitted change in the worktree). This step does **not** include "add tomlkit"; it is a prerequisite already in place.

---

## WHERE

Create:
- `src/mcp_tools_sql/cli/__init__.py` (empty docstring)
- `src/mcp_tools_sql/cli/commands/__init__.py` (empty docstring)
- `src/mcp_tools_sql/cli/commands/init.py`
- `src/mcp_tools_sql/cli/commands/verify.py`
- `tests/cli/__init__.py`
- `tests/cli/test_main_dispatch.py`

Modify:
- `src/mcp_tools_sql/main.py` — argparse + dispatch only; remove the placeholder `_setup_logging` (currently a no-op) and import the real `setup_logging` from `mcp_tools_sql.utils.log_utils` instead. Call it once in `main()` before dispatching to a subcommand.
- `tach.toml` — add `mcp_tools_sql.cli` and `mcp_tools_sql.cli.commands` modules
- `.importlinter` — add `cli` to layered-architecture contract

---

## WHAT — Function signatures

### `cli/commands/init.py`
```python
"""init subcommand."""
from __future__ import annotations
import argparse
from pathlib import Path


def add_subparser(subparsers: argparse._SubParsersAction) -> None:
    """Register `init` subparser and its flags."""
    p = subparsers.add_parser("init", help="Create starter configuration files.")
    p.add_argument("--backend", choices=["sqlite", "mssql", "postgresql"], required=True)
    p.add_argument("--output", type=Path, default=Path("mcp-tools-sql.toml"))
    p.add_argument("--pyproject", action="store_true",
                   help="Append [tool.mcp-tools-sql] to existing pyproject.toml.")


def run(args: argparse.Namespace) -> int:
    """Entry point. Returns process exit code."""
    raise NotImplementedError("init: implemented in step 4")
```

### `cli/commands/verify.py`
```python
"""verify subcommand."""
from __future__ import annotations
import argparse


def add_subparser(subparsers: argparse._SubParsersAction) -> None:
    """Register `verify` subparser (no subcommand-level flags; uses top-level)."""
    subparsers.add_parser("verify", help="Validate configuration and exit.")


def run(args: argparse.Namespace) -> int:
    """Entry point. Returns process exit code."""
    raise NotImplementedError("verify: implemented in steps 5-9")
```

### `main.py` — refactored

```python
def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="mcp-tools-sql", ...)
    parser.add_argument("--config", type=Path, default=None, help="...")
    parser.add_argument("--database-config", type=Path, default=None, help="...")
    parser.add_argument("--log-level", ...)
    parser.add_argument("--log-file", ...)
    parser.add_argument("--console-only", action="store_true")

    subparsers = parser.add_subparsers(dest="command")
    subparsers.add_parser("server", help="Start the MCP server (default).")
    init.add_subparser(subparsers)
    verify.add_subparser(subparsers)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv or sys.argv[1:])
    setup_logging(args.log_level, args.log_file, args.console_only)
    command = args.command or "server"
    if command == "server":
        raise NotImplementedError("server command not yet implemented")
    if command == "init":
        return init.run(args)
    if command == "verify":
        return verify.run(args)
    parser.print_help()
    return 1
```

`setup_logging` is imported from `mcp_tools_sql.utils.log_utils` (the existing shim over `mcp-coder-utils`). The current `main.py` has a placeholder local `_setup_logging` that does nothing — **delete it** and replace the call with the real `setup_logging(...)`. Call it exactly once at the top of `main()`, before dispatching to any subcommand, using the parsed `--log-level`, `--log-file`, and `--console-only` flags.

`__main__.py` should call `sys.exit(main())` to honor exit codes.

`help=` strings on `add_parser()` / `add_argument()` may stay terse here — step 3b finalizes all help text.

---

## HOW — Integration points

### `tach.toml` — append two module entries

Declare **all** import edges upfront — even those only used in steps 5/6/7 (`backends`, `schema_tools`, `formatting`, `utils`). This avoids touching `tach.toml` again in later steps. (Decision: declare-all-upfront — supervisor confirmed.)

```toml
[[modules]]
path = "mcp_tools_sql.cli"
layer = "entry_point"
depends_on = [
    { path = "mcp_tools_sql.config" },
    { path = "mcp_tools_sql.utils" },
]

[[modules]]
path = "mcp_tools_sql.cli.commands"
layer = "entry_point"
depends_on = [
    { path = "mcp_tools_sql.backends" },
    { path = "mcp_tools_sql.config" },
    { path = "mcp_tools_sql.schema_tools" },
    { path = "mcp_tools_sql.formatting" },
    { path = "mcp_tools_sql.utils" },
]
```

Update existing `mcp_tools_sql.main` entry to also depend on `mcp_tools_sql.cli`.

### `.importlinter` — extend layers contract

Insert `cli` between `main` and `server` in the layered contract:

```ini
[importlinter:contract:layers]
name = Layered Architecture
type = layers
layers =
    mcp_tools_sql.main
    mcp_tools_sql.cli
    mcp_tools_sql.server
    mcp_tools_sql.schema_tools | mcp_tools_sql.query_tools | mcp_tools_sql.update_tools | mcp_tools_sql.validation_tools
    mcp_tools_sql.backends | mcp_tools_sql.formatting
    mcp_tools_sql.config
    mcp_tools_sql.utils
```

Note: `cli` sits between `main` and `server` so it can call into server-layer code (load config, build backend, register builtin tools count) without main importing those directly.

---

## ALGORITHM — `main.main`

```
parse args via _build_parser
call setup_logging(args.log_level, args.log_file, args.console_only) once
  # imported from mcp_tools_sql.utils.log_utils — replaces the existing no-op _setup_logging placeholder
dispatch on args.command:
    "server" → existing NotImplementedError
    "init"   → return init.run(args)
    "verify" → return verify.run(args)
    None     → default to "server"
return exit code
```

The `args.command == "server"` branch continues to raise `NotImplementedError` for the duration of issue #9 — server-mode wiring is out of scope here. Step 3a does not change the dispatch logic for that branch; it only adds the `init` / `verify` arms alongside the existing `server` placeholder.

---

## DATA

`run(args)` returns `int` exit code. `main()` returns `int`. `__main__.py` calls `sys.exit(main())`.

---

## Tests — `tests/cli/test_main_dispatch.py`

```python
def test_dispatch_init_calls_init_run(monkeypatch): ...
def test_dispatch_verify_calls_verify_run(monkeypatch): ...
def test_database_config_flag_parsed(): ...     # --database-config foo → args.database_config == Path("foo")
def test_config_flag_parsed(): ...
def test_no_command_defaults_to_server(): ...
def test_init_subparser_requires_backend(): ... # SystemExit on missing --backend
def test_init_subparser_rejects_unknown_backend(): ...
```

Use `monkeypatch.setattr` on `init.run` / `verify.run` to assert dispatch.

No test for actual init/verify behavior here (covered in later steps).

---

## Quality gates

All five checks green. The new dispatch shim should not break existing tests.

---

## LLM Prompt for this step

> Read `pr_info/steps/summary.md` and `pr_info/steps/step_3a.md`. Implement step 3a: create the `src/mcp_tools_sql/cli/` package with `commands/init.py` and `commands/verify.py` skeletons (each exposing `add_subparser(subparsers)` and `run(args)` — both `run` raise `NotImplementedError`). Refactor `main.py` so it only parses arguments and dispatches to `init.run(args)` or `verify.run(args)` and returns an exit code. **Remove** the existing no-op `_setup_logging` placeholder in `main.py` and replace it with a call to the real `setup_logging` imported from `mcp_tools_sql.utils.log_utils`; invoke it exactly once in `main()` before dispatching, passing the parsed `--log-level`, `--log-file`, `--console-only` flags. Update `__main__.py` to `sys.exit(main())`. Add `mcp_tools_sql.cli` and `mcp_tools_sql.cli.commands` modules to `tach.toml` declaring **all** import edges upfront (config, utils, backends, schema_tools, formatting). Extend `.importlinter` to insert `cli` between `main` and `server` in the layered contract. Note: `tomlkit>=0.13.0` is already present in `pyproject.toml` — do not add it again. Write `tests/cli/test_main_dispatch.py` covering: dispatch of init/verify, `--database-config`/`--config` flag parsing, default to `server`, and argparse rejection of missing/unknown `--backend`. Run all quality checks and ensure they pass.
