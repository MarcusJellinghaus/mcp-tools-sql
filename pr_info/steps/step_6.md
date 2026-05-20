# Step 6 — Move `verify_connection` + Kerberos helper

**Goal:** Move `verify_connection()` and `_check_kerberos_ticket()` from
`cli/commands/verify.py` to `verification/connection.py`. Retarget the
Kerberos-test monkeypatches. Move tests.

## WHERE

### New files
- `src/mcp_tools_sql/verification/connection.py`
- `tests/verification/test_connection.py`

### Modified files
- `src/mcp_tools_sql/cli/commands/verify.py` — remove `verify_connection`
  and `_check_kerberos_ticket`
- `src/mcp_tools_sql/verification/__init__.py` — re-export `verify_connection`
- `tests/cli/test_verify.py` — delete the connection tests (incl. Kerberos)
  and the `linux_platform`, `stub_create_backend`, `_sqlite_connection`,
  `_trusted_mssql` helpers/fixtures

## WHAT

### `verification/connection.py`

```python
"""Connection section: backend instantiation, SELECT 1, Kerberos check."""
from __future__ import annotations

import subprocess
import sys
from typing import Any

from mcp_tools_sql.backends.base import DatabaseBackend, create_backend
from mcp_tools_sql.config.models import ConnectionConfig
from mcp_tools_sql.verification._helpers import make_entry


def _check_kerberos_ticket() -> tuple[bool, str, str]:
    """Run ``klist -s`` to check for a cached Kerberos ticket."""
    # ... body moved verbatim ...


def verify_connection(
    connection: ConnectionConfig,
) -> tuple[dict[str, Any], DatabaseBackend | None]:
    """Verify connectivity to the configured database."""
    # ... body moved verbatim ...
```

**Critical:** `create_backend` must be imported at module level so the
existing test monkeypatch retarget (`monkeypatch.setattr(
"mcp_tools_sql.verification.connection.create_backend", ...)`) resolves.
Do not move the import inside the function.

### `verification/__init__.py` (extended)

```python
from mcp_tools_sql.verification.connection import verify_connection

__all__ = [
    "VerifierEntry",
    "verify_environment",
    "verify_config_files",
    "verify_dependencies",
    "verify_builtin",
    "verify_connection",
]
```

### `tests/verification/test_connection.py`

Move all connection tests from `tests/cli/test_verify.py` to the new file,
updating imports:

```python
from mcp_tools_sql.backends.sqlite import SQLiteBackend
from mcp_tools_sql.verification import verify_connection
```

**Imports to add (do not forget):**
- `from mcp_tools_sql.backends.sqlite import SQLiteBackend` — used by the
  success-path test `test_verify_connection_returns_open_backend_on_success`
  (and any other test that needs to assert the returned backend is a real
  `SQLiteBackend` instance). Verified path:
  `src/mcp_tools_sql/backends/sqlite.py` exposes the `SQLiteBackend` class.

**Retarget the Kerberos monkeypatch** in the `stub_create_backend` fixture:

```python
@pytest.fixture
def stub_create_backend(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    backend = MagicMock(name="stub_backend")
    backend.connect.return_value = None
    backend.execute_query.return_value = [{"v": 1}]
    backend.close.return_value = None
    factory = MagicMock(return_value=backend)
    monkeypatch.setattr(
        "mcp_tools_sql.verification.connection.create_backend",  # CHANGED
        factory,
    )
    return factory
```

Also move the local helpers `_sqlite_connection`, `_trusted_mssql`, and the
`linux_platform` fixture to the new test file.

Tests moved (lines ~389–487 + ~1083–1173 in current file):
- `test_verify_connection_sqlite_select_1_ok`
- `test_verify_connection_sqlite_missing_path`
- `test_verify_connection_unimplemented_backend_is_err`
- `test_verify_connection_credentials_password_set`
- `test_verify_connection_credentials_missing_for_mssql`
- `test_verify_connection_returns_open_backend_on_success`
- `test_verify_connection_returns_none_backend_on_failure`
- `test_klist_zero_returns_ok`
- `test_klist_nonzero_returns_err`
- `test_klist_missing_returns_err`
- `test_non_linux_platforms_skip_check`
- `test_non_trusted_skips_check`

## HOW

### Recommended tool

```
move_symbol(
    source_file="src/mcp_tools_sql/cli/commands/verify.py",
    symbol_names=["verify_connection", "_check_kerberos_ticket"],
    dest_file="src/mcp_tools_sql/verification/connection.py",
)
```

Then manually:
1. Confirm `from mcp_tools_sql.backends.base import DatabaseBackend, create_backend`
   sits at the top of the new file (it must, for monkeypatch retarget to work).
2. Re-export from `verification/__init__.py`.
3. Move the tests + helpers + fixtures, retargeting the monkeypatch string.

### Integration in `cli/commands/verify.py`

Add to the top-level import block:

```python
from mcp_tools_sql.verification import verify_connection
```

`run()` continues to call `verify_connection(connection)` unchanged.

## ALGORITHM

No algorithm — functions moved verbatim. The only mechanical change is the
monkeypatch target string in the test fixture.

## DATA

- `verify_connection` return: `tuple[dict[str, Any], DatabaseBackend | None]`.
- Entry keys (varying by backend):
  `backend`, `driver` (mssql only), `path` (sqlite only),
  `host_port`/`database` (non-sqlite), `credentials`,
  `kerberos_ticket` (mssql + trusted + linux only), `select_1`, `overall_ok`.

## Checks

Run after edits:
- `mcp__mcp-tools-py__run_pylint_check`
- `mcp__mcp-tools-py__run_mypy_check`
- `mcp__mcp-tools-py__run_pytest_check(extra_args=["-n", "auto", "-m", "not git_integration and not claude_cli_integration and not claude_api_integration and not formatter_integration and not github_integration and not langchain_integration"])`
- `mcp__mcp-tools-py__run_tach_check`
- `mcp__mcp-tools-py__run_lint_imports_check`

All must pass. In particular, run the Kerberos tests explicitly to confirm
the monkeypatch retarget works:

```
mcp__mcp-tools-py__run_pytest_check(extra_args=[
    "tests/verification/test_connection.py", "-v"
])
```

## LLM Prompt

> Read `pr_info/steps/summary.md` and `pr_info/steps/step_6.md`. Implement
> step 6: move `verify_connection` and `_check_kerberos_ticket` from
> `cli/commands/verify.py` to a new file
> `src/mcp_tools_sql/verification/connection.py`. Use the `move_symbol`
> MCP tool. **Critical constraint:** `from mcp_tools_sql.backends.base
> import DatabaseBackend, create_backend` must remain a module-level
> import in the new file — the Kerberos tests monkeypatch
> `mcp_tools_sql.verification.connection.create_backend` and need it
> resolvable in that namespace. Re-export `verify_connection` from
> `verification/__init__.py`. Move all twelve connection-related tests
> (the seven `test_verify_connection_*` tests and the five Kerberos
> tests, including the `linux_platform` and `stub_create_backend`
> fixtures and the `_sqlite_connection` / `_trusted_mssql` helpers) from
> `tests/cli/test_verify.py` to a new
> `tests/verification/test_connection.py`. In the `stub_create_backend`
> fixture, change the monkeypatch target string from
> `"mcp_tools_sql.cli.commands.verify.create_backend"` to
> `"mcp_tools_sql.verification.connection.create_backend"`. Do not modify
> function bodies. Run all checks; all must pass before committing.
