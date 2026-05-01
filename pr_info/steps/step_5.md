# Step 5 — `verify` skeleton + formatter + ENVIRONMENT + CONFIG sections

**Reference**: [summary.md](./summary.md) — section "`verify` command pattern"
**Commit**: 5 of 10
**Goal**: Land the formatter primitives, the orchestrator skeleton, and the first two domain functions. Other sections still TODO; orchestrator prints what it has and exits.

> **Decisions for this step**:
> - The formatter scaffold includes `"warn" → "[WARN]"` in `STATUS_SYMBOLS` from the **start** (step 5). The actual `[WARN]` row is wired in step 7, but the symbol entry lives in the map immediately so later steps don't have to touch the constant.
> - **Do NOT suppress the loader's own logger output.** Loader warnings (e.g. sensitive-key WARN from `load_query_config`) may interleave with verify CLI output on stderr/stdout. This is accepted as-is. No `logging.disable(...)` or logger-level adjustments inside `verify.run()`.

---

## WHERE

Modify:
- `src/mcp_tools_sql/cli/commands/verify.py` — replace `NotImplementedError` with formatter + first two sections + orchestrator stub
- `tests/cli/test_verify.py` (new file)

---

## WHAT — Module structure of `verify.py`

```python
"""verify subcommand."""
from __future__ import annotations
import argparse
import logging
import sys
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

STATUS_SYMBOLS: dict[str, str] = {"ok": "[OK]", "err": "[ERR]", "warn": "[WARN]"}
_LABEL_WIDTH = 28      # tweak after first run for nice columns


# --- Formatter helpers ---------------------------------------------------
def _pad(text: str, width: int) -> str: ...
def _format_row(status: str, label: str, value: str = "", error: str = "") -> str:
    """Return one formatted row, e.g. '[OK]  Python version            3.11.5'."""

def _print_section(title: str) -> None:
    print(f"=== {title} ===")

def _compute_exit_code(error_count: int) -> int:
    return 0 if error_count == 0 else 1


# --- Domain verifiers (return dicts) --------------------------------------
def verify_environment() -> dict[str, Any]: ...
def verify_config_files(
    config_path: Path | None, db_config_path: Path | None
) -> dict[str, Any]: ...


# --- Orchestrator ---------------------------------------------------------
def add_subparser(subparsers: argparse._SubParsersAction) -> None:
    subparsers.add_parser("verify", help="Validate configuration and exit.")


def run(args: argparse.Namespace) -> int:
    """Entry point."""
    sections: list[tuple[str, dict[str, Any]]] = []

    sections.append(("ENVIRONMENT", verify_environment()))
    sections.append((
        "CONFIG",
        verify_config_files(args.config, args.database_config),
    ))
    # ... DEPENDENCIES / BUILTIN / CONNECTION / QUERIES / UPDATES added in later steps

    return _print_and_summarize(sections)


def _print_and_summarize(sections: list[tuple[str, dict[str, Any]]]) -> int:
    ok = warn = err = 0
    for title, result in sections:
        _print_section(title)
        for key, entry in result.items():
            if key == "overall_ok":
                continue
            if entry["ok"]:
                print(_format_row("ok", key, entry.get("value", "")))
                ok += 1
            else:
                print(_format_row("err", key, entry.get("value", ""), entry.get("error", "")))
                err += 1
        print()
    print(f"{ok} checks passed, {warn} warnings, {err} errors")
    return _compute_exit_code(err)
```

A `[WARN]` path will be added in step 7 when sensitive-key warnings surface. For now, only `ok` / `err`.

---

## WHAT — `verify_environment()`

```python
def verify_environment() -> dict[str, Any]:
    """
    Returns:
      {
        "python_version": {"ok": True, "value": "3.11.5", "error": "", "install_hint": ""},
        "virtualenv":     {"ok": True/False, "value": "<sys.prefix>" or "(none)", ...},
        "mcp_tools_sql":  {"ok": True, "value": "0.1.0.dev1+abc", ...},
        "mcp_coder_utils":{"ok": True/False, "value": "<version>" or "(not installed)", ...},
        "overall_ok": True/False,
      }
    """
```

- `python_version`: `f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"`. Always `ok=True`.
- `virtualenv`: `ok = sys.prefix != sys.base_prefix`; `value = sys.prefix` if ok else `"(not in a virtual environment)"`. Mark `ok=True` and emit a row regardless — venv missing is informational only.
- Package versions: use `importlib.metadata.version(name)`. `ok=True` if found; `False` otherwise (with `install_hint` for `mcp_coder_utils`).

---

## WHAT — `verify_config_files()`

```python
def verify_config_files(
    config_path: Path | None, db_config_path: Path | None
) -> dict[str, Any]:
    """
    For each of the two configs, report:
      - resolved path (uses discover_query_config / default home path)
      - parse status (loads_query_config / load_database_config — catch ValueError)
      - sensitive-key warning (loader already logs at WARN level; emit a row if found)
    """
```

Resolved path:
- query config: try `discover_query_config(config_path, project_dir=Path.cwd())` — on failure, ok=False with the ValueError message.
- database config: `db_config_path or Path.home() / ".mcp-tools-sql" / "config.toml"`. If file does not exist, ok=False with hint to run `init`.

Parse status: call the loader; capture `ValueError`.

Sensitive-key check: the loader already emits a `logger.warning` for sensitive keys in the query config. For verify output, replicate the check inline (call `_has_sensitive_keys` — could expose it or duplicate the small helper).

Return entries:
- `query_config_path`
- `query_config_parse`
- `query_config_sensitive_keys` (only present if any were found, with `ok=False` and a `[WARN]`-style entry — but since we only have `ok/err` in step 5, treat sensitive keys as `ok=True` value with a warning string for now; promote to `[WARN]` semantics in step 7)
- `database_config_path`
- `database_config_parse`

For step 5 simplicity: the sensitive-key handling is **deferred to step 7** (when `[WARN]` symbol is wired up). Emit only path + parse rows in this step.

---

## ALGORITHM — orchestrator (current state)

```
sections = []
sections += verify_environment
sections += verify_config_files
print all sections
print summary
return exit code
```

---

## DATA — Return shapes

Each verifier returns:
```python
{
    "<key>": {"ok": bool, "value": str, "error": str, "install_hint": str},
    ...,
    "overall_ok": bool,   # True iff all entries have ok=True
}
```

Defaults: `error=""`, `install_hint=""` when unused.

---

## Tests — `tests/cli/test_verify.py`

| Test | Asserts |
|---|---|
| `test_verify_environment_returns_python_version` | `result["python_version"]["ok"] is True` and value matches `sys.version_info` |
| `test_verify_environment_overall_ok_true_when_packages_present` | `mcp_tools_sql` and `mcp_coder_utils` resolve in test env |
| `test_verify_config_files_missing_returns_err` | Pass `config_path=Path("/nonexistent.toml")` → ok=False, error mentions path |
| `test_verify_config_files_valid_returns_ok` | Use `tmp_path` with valid minimal config → ok=True |
| `test_verify_run_prints_environment_and_config_sections` | capsys: stdout contains `=== ENVIRONMENT ===` and `=== CONFIG ===` |
| `test_verify_summary_line_format` | capsys: stdout ends with `N checks passed, M warnings, K errors` |
| `test_verify_exit_code_0_when_all_ok` | `run(args)` returns 0 |
| `test_verify_exit_code_1_when_config_missing` | `run(args)` returns 1 |

Use a fixture that builds a minimal `argparse.Namespace` with `config` and `database_config` paths.

---

## Quality gates

All five checks green.

---

## LLM Prompt for this step

> Read `pr_info/steps/summary.md` and `pr_info/steps/step_5.md`. Implement the `verify` skeleton in `src/mcp_tools_sql/cli/commands/verify.py`: formatter helpers (`STATUS_SYMBOLS`, `_pad`, `_format_row`, `_print_section`, `_compute_exit_code`), the orchestrator `run(args)` that calls each domain verifier and prints sections + a summary line, and the first two domain verifiers `verify_environment()` and `verify_config_files(config_path, db_config_path)` returning the standard dict shape. `verify_environment` reports Python version, virtualenv status, and package versions for `mcp_tools_sql` and `mcp_coder_utils` (use `importlib.metadata`). `verify_config_files` reports resolved path + parse status for both configs (defer sensitive-key warning rows to step 7). Output via `print()`; diagnostics via `logger.debug()`. Exit code 0 if no errors, 1 otherwise. Add `tests/cli/test_verify.py` with the listed tests. Run all quality checks and ensure they pass.
