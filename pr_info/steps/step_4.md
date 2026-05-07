# Step 4 — `run_server()` + `main` server dispatch

## LLM prompt

> Read `pr_info/steps/summary.md` and then implement Step 4 in
> `pr_info/steps/step_4.md`. Step 1 (lazy-connect) must be merged. TDD: write
> `tests/test_server.py` and update `tests/cli/test_main_dispatch.py` first, then
> add `run_server` to `server.py` and update `main.py`. Run pylint + pytest +
> mypy. One commit at the end.

## Goal

`mcp-tools-sql server` (and `mcp-tools-sql` with no args) start the MCP server.
Pre-`mcp.run()` config errors print a friendly hint to stderr and return exit 2.
`KeyboardInterrupt` returns 130. `backend.close()` always runs.

---

## WHERE

- `src/mcp_tools_sql/server.py` — add `run_server(args)` plus a startup INFO log.
- `src/mcp_tools_sql/main.py` — replace `NotImplementedError`; route no-command
  to `server`; wrap `run_server` with exit-code translation.
- `tests/test_server.py` — new file: smoke + KeyboardInterrupt + lazy-connect.
- `tests/cli/test_main_dispatch.py` — replace `test_no_command_prints_help_and_exits_0`
  with two server-dispatch tests; add the friendly-error tests.

## WHAT

`run_server(args: argparse.Namespace) -> None` (in `server.py`)
- Pure wiring; raises `ValueError` on config failures, `KeyboardInterrupt` on
  Ctrl+C. Always closes the backend in `finally`.

`main` dispatch change (in `main.py`)
- When `args.command in (None, "server")` and not in help mode, call
  `run_server(args)` inside try/except.

Module-private startup log line (in `server.py`):
```
INFO  starting MCP server backend=<b> connection=<c> query_config=<path> builtin_tools=<n>
```

## HOW

- `server.py` imports (at module top, not under TYPE_CHECKING):
  - `argparse` (param type), `sys`
  - `discover_query_config`, `load_query_config`, `load_database_config`,
    `resolve_connection` from `mcp_tools_sql.config.loader`
  - `create_backend` from `mcp_tools_sql.backends.base`
  - `load_default_queries` from `mcp_tools_sql.schema_tools`
  - `Path` from `pathlib`
- `main.py` adds `import traceback` and `from mcp_tools_sql.server import run_server`.
- The friendly-error UX (catches `OSError` too — covers permission errors,
  unreadable files, etc.; matches `verify.py`'s existing pattern):
  ```python
  except (ValueError, OSError) as exc:
      print(f"Error: {exc}", file=sys.stderr)
      print("Try 'mcp-tools-sql verify' for diagnostics.", file=sys.stderr)
      if args.log_level == "DEBUG":
          traceback.print_exc()
      return 2
  ```
- Help-mode preserved: `--help` / `-h` / explicit `help` subcommand still print
  help and return 0. Only **no command at all** falls through to server.

## ALGORITHM

```
run_server(args):
    qpath = discover_query_config(args.config, project_dir=Path.cwd())
    qcfg  = load_query_config(qpath)
    dbcfg = load_database_config(args.database_config)
    conn  = resolve_connection(qcfg, dbcfg)
    backend = create_backend(conn)
    try:
        n_builtin = len(load_default_queries())
        logger.info("starting MCP server backend=%s connection=%s query_config=%s builtin_tools=%d",
                    conn.backend, qcfg.connection, qpath, n_builtin)
        # connection name comes from qcfg.connection (the resolved name), NOT conn.backend
        ToolServer(qcfg, backend, conn.backend).run()
    finally:
        backend.close()
```

```
main():
    ...parse args, setup logging...
    if help-mode: print_help(); return 0
    cmd = args.command or "server"
    if cmd == "server":
        try: run_server(args); return 0
        except KeyboardInterrupt: return 130
        except (ValueError, OSError) as exc: <friendly-stderr>; return 2
    if cmd == "init":   return init.run(args)
    if cmd == "verify": return verify.run(args)
```

## DATA

`run_server` returns `None`; control flow is via exceptions. Exit codes are
chosen in `main`.

---

## Tests (TDD — write first)

### `tests/test_server.py` (new)

Use a SQLite tmp config and monkeypatch one seam: `ToolServer.run` (the entry
point that would otherwise block on STDIO). Helper to write the config files:

```python
def _write_sqlite_configs(tmp_path: Path) -> argparse.Namespace:
    db = tmp_path / "test.db"
    sqlite3.connect(str(db)).close()
    qcfg = tmp_path / "mcp-tools-sql.toml"
    qcfg.write_text('connection = "default"\n')
    dbcfg = tmp_path / "db.toml"
    dbcfg.write_text(
        f'[connections.default]\nbackend = "sqlite"\npath = "{db.as_posix()}"\n'
    )
    return argparse.Namespace(config=qcfg, database_config=dbcfg, log_level="INFO")
```

Tests:

1. **`test_run_server_smoke_calls_run_and_closes`**: monkeypatch
   `ToolServer.run` to a no-op recording `self._registered = True`; assert
   `run_server` returns `None` and the underlying backend's `close()` was called
   (use a wrapper backend whose `close()` increments a counter, OR
   monkeypatch `SQLiteBackend.close` and assert the counter).

2. **`test_keyboard_interrupt_runs_close`**: monkeypatch `ToolServer.run` to
   raise `KeyboardInterrupt`; call `run_server(args)`. Assert
   `KeyboardInterrupt` propagates and the backend was closed.

3. **`test_pre_mcp_run_value_error_for_bad_config`**: pass an `args` whose
   `config` points at a non-existent file. Assert `run_server` raises
   `ValueError` (message contains "Config not found").

4. **`test_lazy_connect_constructible_when_db_unreachable`**: write a database
   config whose `path` points under a non-existent parent directory (e.g.
   `tmp_path / "missing_subdir" / "test.db"`) — opening this path would fail at
   `sqlite3.connect()` time. Monkeypatch `SQLiteBackend.connect` to a counter,
   monkeypatch `ToolServer.run` to a no-op. Call `run_server(args)`. Assert it
   returns without error AND the connect counter is `0` (i.e. `connect()` was
   never called because the server never executed a tool). Replicates the
   issue's "DB unreachable but server constructs."

5. **`test_startup_info_log_line`**: monkeypatch `ToolServer.run` to no-op.
   Assert `caplog` contains one INFO record matching
   `"starting MCP server backend=sqlite connection=default .* builtin_tools="`.

### `tests/cli/test_main_dispatch.py` updates

Remove `test_no_command_prints_help_and_exits_0`. Replace with:

1. **`test_no_command_dispatches_to_server`**:
   ```python
   def test_no_command_dispatches_to_server(monkeypatch):
       called = {"n": 0}
       def fake(args): called["n"] += 1
       monkeypatch.setattr("mcp_tools_sql.main.run_server", fake)
       rc = main([])
       assert rc == 0
       assert called["n"] == 1
   ```

2. **`test_server_command_dispatches_to_server`**: same as above but `main(["server"])`.

3. **`test_server_friendly_error_for_bad_config_returns_2`** (parametrized over
   three failure modes — each must produce exit 2, stderr containing `"Error:"`
   and `"verify"`, and **no** `"Traceback"` at the default log level):
   - `--config` points at a non-existent file (FileNotFoundError → exit 2)
   - `--database-config` points at a missing connection name (ValueError → exit 2)
   - `--database-config` connection has unknown backend type (ValueError → exit 2)
   ```python
   @pytest.mark.parametrize("scenario", ["missing_config", "missing_connection_name", "unknown_backend"])
   def test_server_friendly_error_for_bad_config_returns_2(
       tmp_path, capsys, scenario,
   ):
       # build args per scenario, run main([...]), assert rc == 2,
       # assert "Error:" in err and "verify" in err and "Traceback" not in err
       ...
   ```

4. **`test_server_keyboard_interrupt_returns_130`**: monkeypatch `run_server`
   to raise `KeyboardInterrupt`; assert `main(["server"])` returns 130.

5. **`test_help_subcommand_still_prints_help`** (keep behaviour): explicit
   `main(["help"])` → 0 with help text in stdout.

6. **`test_setup_logging_runs_before_run_server`**: monkeypatch both
   `setup_logging` and `run_server` to append their name to a shared list when
   called. Run `main(["server"])`. Assert the list is `["setup_logging",
   "run_server"]` (i.e. `setup_logging` was invoked first). Guards against
   regressions that would silently swallow startup-error logs.

## Acceptance

- Three checks green; `lint-imports` and `tach check` green.
- One commit: `feat(server): wire run_server + main dispatch with friendly errors`.
