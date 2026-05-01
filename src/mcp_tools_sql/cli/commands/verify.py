"""verify subcommand."""

from __future__ import annotations

import argparse
import datetime
import importlib.metadata
import logging
import os
import sys
from pathlib import Path
from typing import Any

from mcp_tools_sql.backends.base import DatabaseBackend, create_backend
from mcp_tools_sql.cli.parsers import WideHelpFormatter
from mcp_tools_sql.config.loader import (
    _has_sensitive_keys,
    _read_toml,
    discover_query_config,
    load_database_config,
    load_query_config,
    resolve_connection,
)
from mcp_tools_sql.config.models import (
    ConnectionConfig,
    QueryConfig,
    QueryFileConfig,
    QueryParamConfig,
    UpdateConfig,
)
from mcp_tools_sql.schema_tools import extract_sql_params, load_default_queries

logger = logging.getLogger(__name__)

STATUS_SYMBOLS: dict[str, str] = {"ok": "[OK]", "err": "[ERR]", "warn": "[WARN]"}
_LABEL_WIDTH = 28


def _pad(text: str, width: int) -> str:
    """Left-justify ``text`` to ``width`` (truncate if longer).

    Returns:
        The padded (or truncated) text, exactly ``width`` characters long.
    """
    if len(text) >= width:
        return text[:width]
    return text.ljust(width)


def _format_row(status: str, label: str, value: str = "", error: str = "") -> str:
    """Return one formatted row, e.g. ``[OK]  Python version  3.11.5``."""
    symbol = STATUS_SYMBOLS.get(status, status)
    parts = [symbol, _pad(label, _LABEL_WIDTH)]
    if value:
        parts.append(value)
    if error:
        parts.append(f"- {error}")
    return "  ".join(parts).rstrip()


def _print_section(title: str) -> None:
    """Print a section header line."""
    print(f"=== {title} ===")


def _compute_exit_code(error_count: int) -> int:
    """Return ``0`` if no errors, ``1`` otherwise."""
    return 0 if error_count == 0 else 1


def _entry(
    *,
    ok: bool,
    value: str = "",
    error: str = "",
    install_hint: str = "",
) -> dict[str, Any]:
    """Build a single verifier result entry with the standard shape.

    Returns:
        Dict containing ``ok``, ``value``, ``error`` and ``install_hint`` keys.
    """
    return {"ok": ok, "value": value, "error": error, "install_hint": install_hint}


def verify_environment() -> dict[str, Any]:
    """Report Python version, virtualenv status, and key package versions.

    Returns:
        Standard verifier result dict with entries for ``python_version``,
        ``virtualenv``, ``mcp_tools_sql``, ``mcp_coder_utils`` and an
        ``overall_ok`` flag.
    """
    result: dict[str, Any] = {}

    py_version = (
        f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    )
    result["python_version"] = _entry(ok=True, value=py_version)

    in_venv = sys.prefix != sys.base_prefix
    result["virtualenv"] = _entry(
        ok=True,
        value=sys.prefix if in_venv else "(not in a virtual environment)",
    )

    for pkg, hint in (
        ("mcp_tools_sql", ""),
        (
            "mcp_coder_utils",
            "pip install mcp-coder-utils",
        ),
    ):
        try:
            ver = importlib.metadata.version(pkg)
            result[pkg] = _entry(ok=True, value=ver)
        except importlib.metadata.PackageNotFoundError:
            result[pkg] = _entry(
                ok=False,
                value="(not installed)",
                error=f"package {pkg!r} not found",
                install_hint=hint,
            )

    result["overall_ok"] = all(
        entry["ok"] for key, entry in result.items() if key != "overall_ok"
    )
    return result


def verify_config_files(
    config_path: Path | None,
    db_config_path: Path | None,
) -> dict[str, Any]:
    """Verify that both config files resolve to a path and parse cleanly.

    Returns:
        Standard verifier result dict with entries for the resolved path
        and parse status of the query config and the database config.
        A ``query_config_sensitive_keys`` entry is added with ``warn=True``
        when sensitive keys are detected in the query config.
    """
    result: dict[str, Any] = {}

    resolved_query: Path | None
    try:
        resolved_query = discover_query_config(config_path, project_dir=Path.cwd())
        result["query_config_path"] = _entry(ok=True, value=str(resolved_query))
    except ValueError as exc:
        resolved_query = None
        result["query_config_path"] = _entry(ok=False, error=str(exc))
        result["query_config_parse"] = _entry(
            ok=False, error="skipped (path not resolved)"
        )

    if resolved_query is not None:
        try:
            load_query_config(resolved_query)
            result["query_config_parse"] = _entry(ok=True, value="loaded")
        except ValueError as exc:
            result["query_config_parse"] = _entry(ok=False, error=str(exc))

        try:
            data = _read_toml(resolved_query)
            found = _has_sensitive_keys(data)
        except ValueError:
            found = []
        if found:
            entry = _entry(
                ok=False,
                value=", ".join(sorted(set(found))),
                error="Move credentials to ~/.mcp-tools-sql/config.toml",
            )
            entry["warn"] = True
            result["query_config_sensitive_keys"] = entry

    db_path = db_config_path or Path.home() / ".mcp-tools-sql" / "config.toml"
    if not db_path.exists():
        result["database_config_path"] = _entry(
            ok=False,
            value=str(db_path),
            error="file not found",
            install_hint="run `mcp-tools-sql init --backend <backend>`",
        )
        result["database_config_parse"] = _entry(
            ok=False, error="skipped (file not found)"
        )
    else:
        result["database_config_path"] = _entry(ok=True, value=str(db_path))
        try:
            load_database_config(db_path)
            result["database_config_parse"] = _entry(ok=True, value="loaded")
        except ValueError as exc:
            result["database_config_parse"] = _entry(ok=False, error=str(exc))

    result["overall_ok"] = all(
        entry["ok"] or entry.get("warn", False)
        for key, entry in result.items()
        if key != "overall_ok"
    )
    return result


def verify_dependencies(backend: str) -> dict[str, Any]:
    """Backend-conditional check of optional/extra dependencies.

    Args:
        backend: Backend name (``sqlite``, ``mssql``, ``postgresql``)
            or ``"unknown"`` when the backend cannot be resolved.

    Returns:
        Standard verifier result dict with backend-specific entries
        and an ``overall_ok`` flag.
    """
    if backend == "unknown":
        return {
            "backend": _entry(
                ok=False,
                error="cannot determine backend without valid config",
            ),
            "overall_ok": False,
        }

    if backend == "sqlite":
        return {
            "info": _entry(ok=True, value="(no optional dependencies for sqlite)"),
            "overall_ok": True,
        }

    if backend == "mssql":
        return _verify_dependencies_mssql()

    if backend == "postgresql":
        return _verify_dependencies_postgresql()

    return {
        "backend": _entry(
            ok=False,
            value=backend,
            error=f"unknown backend {backend!r}",
        ),
        "overall_ok": False,
    }


def _verify_dependencies_mssql() -> dict[str, Any]:
    """Check for ``pyodbc`` and a ``SQL Server`` ODBC driver.

    Returns:
        Verifier result dict for the mssql backend.
    """
    result: dict[str, Any] = {}
    pyodbc_module: Any = None
    try:
        import pyodbc  # type: ignore[import-not-found]  # pylint: disable=import-outside-toplevel

        pyodbc_module = pyodbc
        version = getattr(pyodbc, "version", "")
        result["pyodbc"] = _entry(ok=True, value=version)
    except ImportError as exc:
        result["pyodbc"] = _entry(
            ok=False,
            value="(not installed)",
            error=str(exc),
            install_hint="pip install mcp-tools-sql[mssql]",
        )

    if pyodbc_module is None:
        result["odbc_driver"] = _entry(
            ok=False,
            value="(skipped)",
            error="pyodbc not available",
        )
    else:
        try:
            drivers = list(pyodbc_module.drivers())
            sql_server_driver = next((d for d in drivers if "SQL Server" in d), None)
            if sql_server_driver is None:
                result["odbc_driver"] = _entry(
                    ok=False,
                    value="(none found)",
                    error="No ODBC driver containing 'SQL Server' found",
                    install_hint=(
                        "Install Microsoft ODBC Driver 18 for SQL Server "
                        "(https://learn.microsoft.com/sql/connect/odbc/"
                        "download-odbc-driver-for-sql-server)"
                    ),
                )
            else:
                result["odbc_driver"] = _entry(ok=True, value=sql_server_driver)
        except Exception as exc:  # pylint: disable=broad-except
            result["odbc_driver"] = _entry(
                ok=False,
                value="(error)",
                error=str(exc),
            )

    result["overall_ok"] = all(
        entry["ok"] for key, entry in result.items() if key != "overall_ok"
    )
    return result


def _verify_dependencies_postgresql() -> dict[str, Any]:
    """Check for the ``psycopg`` package.

    Returns:
        Verifier result dict for the postgresql backend.
    """
    result: dict[str, Any] = {}
    try:
        import psycopg  # type: ignore[import-not-found]  # pylint: disable=import-outside-toplevel

        version = getattr(psycopg, "__version__", "")
        result["psycopg"] = _entry(ok=True, value=version)
    except ImportError as exc:
        result["psycopg"] = _entry(
            ok=False,
            value="(not installed)",
            error=str(exc),
            install_hint="pip install mcp-tools-sql[postgresql]",
        )

    result["overall_ok"] = all(
        entry["ok"] for key, entry in result.items() if key != "overall_ok"
    )
    return result


def verify_builtin() -> dict[str, Any]:
    """Report status of built-in default queries.

    Returns:
        Verifier result dict with ``default_queries_loaded`` and
        ``tools_registered_count`` entries plus ``overall_ok``.
    """
    result: dict[str, Any] = {}
    try:
        queries = load_default_queries()
        result["default_queries_loaded"] = _entry(
            ok=bool(queries),
            value=f"{len(queries)} queries",
            error="" if queries else "no queries found",
        )
        result["tools_registered_count"] = _entry(
            ok=True, value=f"{len(queries)} tools"
        )
        result["overall_ok"] = bool(queries)
    except Exception as exc:  # pylint: disable=broad-except
        result["default_queries_loaded"] = _entry(
            ok=False, value="(error)", error=str(exc)
        )
        result["tools_registered_count"] = _entry(
            ok=False, value="(skipped)", error="default_queries_loaded failed"
        )
        result["overall_ok"] = False
    return result


def verify_connection(
    connection: ConnectionConfig,
) -> tuple[dict[str, Any], DatabaseBackend | None]:
    """Verify connectivity to the configured database.

    Builds a backend via ``create_backend(connection)`` and runs ``SELECT 1``.
    On success the backend is left **open** and returned as the second tuple
    element so M2 sections can reuse it; the caller is responsible for
    closing it. On failure the second tuple element is ``None``.

    Returns:
        A 2-tuple of (result_dict, open_backend_or_None).
    """
    result: dict[str, Any] = {}
    result["backend"] = _entry(ok=True, value=connection.backend)

    if connection.backend == "mssql":
        result["driver"] = _entry(
            ok=bool(connection.driver),
            value=connection.driver or "(empty)",
            error="" if connection.driver else "driver must be set for mssql",
        )

    if connection.backend == "sqlite":
        result["path"] = _entry(
            ok=bool(connection.path),
            value=connection.path or "(empty)",
            error="" if connection.path else "path must be set for sqlite",
        )
    else:
        host_value = (
            f"{connection.host}:{connection.port}" if connection.host else "(empty)"
        )
        result["host_port"] = _entry(
            ok=bool(connection.host),
            value=host_value,
            error="" if connection.host else "host must be set",
        )
        result["database"] = _entry(
            ok=bool(connection.database),
            value=connection.database or "(empty)",
            error="" if connection.database else "database must be set",
        )

    if connection.credential_env_var:
        env_value = os.environ.get(connection.credential_env_var)
        result["credentials"] = _entry(
            ok=env_value is not None,
            value=(
                f"env:{connection.credential_env_var}="
                f"{'<set>' if env_value else '<missing>'}"
            ),
            error=(
                ""
                if env_value
                else f"Environment variable {connection.credential_env_var} not set"
            ),
        )
    elif connection.password or connection.trusted_connection:
        result["credentials"] = _entry(ok=True, value="configured")
    elif connection.backend == "sqlite":
        result["credentials"] = _entry(ok=True, value="(not required for sqlite)")
    else:
        result["credentials"] = _entry(
            ok=False,
            value="(none)",
            error="No credentials configured",
        )

    open_backend: DatabaseBackend | None = None
    try:
        backend = create_backend(connection)
        backend.connect()
        backend.execute_query("SELECT 1")
        result["select_1"] = _entry(ok=True, value="ok")
        open_backend = backend
    except Exception as exc:  # pylint: disable=broad-except
        result["select_1"] = _entry(ok=False, value="failed", error=str(exc))
        open_backend = None

    result["overall_ok"] = all(
        entry["ok"] for key, entry in result.items() if key != "overall_ok"
    )
    return result, open_backend


_VALID_PARAM_TYPES = {"str", "int", "float", "datetime"}
_LEGITIMATE_NON_SQL_PARAMS = {"filter", "max_rows"}
_DUMMY_BY_TYPE: dict[str, Any] = {
    "str": "",
    "int": 0,
    "float": 0.0,
    "datetime": datetime.datetime(2000, 1, 1),
}


def _check_sql_explain(
    sql: str,
    params: dict[str, QueryParamConfig],
    backend_name: str,
    backend: DatabaseBackend,
) -> tuple[bool, str]:
    """Return ``(ok, error_message)`` for a single query's SQL.

    For SQLite, builds a dummy params dict (keys from ``params``, values
    placeholders chosen per declared type: ``""`` / ``0`` / ``0.0`` /
    ``datetime(2000, 1, 1)``) and passes it to
    ``backend.explain(sql, dummy_params)`` so ``EXPLAIN QUERY PLAN`` can
    compile the parameterized SQL. For MSSQL, calls ``backend.explain(sql)``
    — currently raises :class:`NotImplementedError`, so this reports
    ``[ERR]`` with the exception message; that's the intended behaviour
    until the MSSQL backend lands (issues #5/#6).
    """
    del backend_name  # Currently no per-backend branching is required.
    try:
        dummy = {name: _DUMMY_BY_TYPE.get(p.type, "") for name, p in params.items()}
        backend.explain(sql, dummy)
        return True, ""
    except Exception as exc:  # pylint: disable=broad-except
        return False, str(exc)


def _check_params_well_formed(
    sql: str, params: dict[str, QueryParamConfig]
) -> tuple[bool, str]:
    """Verify ``:name`` placeholders in SQL match config params + types.

    Returns:
        Tuple ``(ok, message)`` where ``ok`` is ``True`` when placeholders
        and config params line up with valid types, and ``message`` is a
        ``"; "``-joined description of any problems (empty when ``ok``).
    """
    sql_names = extract_sql_params(sql)
    config_names = set(params.keys())

    missing_in_config = sql_names - config_names
    extra_in_config = (config_names - sql_names) - _LEGITIMATE_NON_SQL_PARAMS
    bad_types = [
        (n, p.type) for n, p in params.items() if p.type not in _VALID_PARAM_TYPES
    ]

    errors: list[str] = []
    if missing_in_config:
        errors.append(
            f"SQL :{','.join(sorted(missing_in_config))} not in config params"
        )
    if extra_in_config:
        errors.append(f"Config params {sorted(extra_in_config)} not used in SQL")
    if bad_types:
        errors.append("Invalid types: " + ", ".join(f"{n}={t!r}" for n, t in bad_types))
    return (not errors, "; ".join(errors))


def verify_queries(
    queries: dict[str, QueryConfig],
    backend_name: str,
    backend: DatabaseBackend,
) -> dict[str, Any]:
    """Per-query validation: SQL EXPLAIN, params well-formed, max_rows > 0.

    Returns:
        Standard verifier result dict with three rows per query
        (``<name>.sql``, ``<name>.params``, ``<name>.max_rows``) and an
        ``overall_ok`` flag.
    """
    result: dict[str, Any] = {}
    for name, qcfg in queries.items():
        sql = qcfg.resolve_sql(backend_name)

        ok, err = _check_sql_explain(sql, qcfg.params, backend_name, backend)
        result[f"{name}.sql"] = _entry(
            ok=ok,
            value="EXPLAIN ok" if ok else "failed",
            error=err,
        )

        ok, err = _check_params_well_formed(sql, qcfg.params)
        result[f"{name}.params"] = _entry(
            ok=ok,
            value="well-formed" if ok else "issue",
            error=err,
        )

        ok = qcfg.max_rows > 0
        result[f"{name}.max_rows"] = _entry(
            ok=ok,
            value=str(qcfg.max_rows),
            error="" if ok else "max_rows must be > 0",
        )
    result["overall_ok"] = all(
        entry["ok"] for key, entry in result.items() if key != "overall_ok"
    )
    return result


def _list_table_columns(
    backend: DatabaseBackend,
    backend_name: str,
    schema: str,
    table: str,
) -> list[str] | None:
    """Return column names for ``table`` in ``schema``, or ``None`` if missing.

    SQLite ignores ``schema`` (single-database file). MSSQL/PostgreSQL look up
    via ``INFORMATION_SCHEMA.COLUMNS`` filtered by both schema and table; the
    user must set ``schema`` in their config when the table lives outside the
    connection's default schema — verify never silently substitutes ``dbo`` or
    ``public``.
    """
    if backend_name == "sqlite":
        rows = backend.execute_query(
            "SELECT name FROM pragma_table_info(:table)",
            {"table": table},
        )
        cols = [r["name"] for r in rows]
        return cols if cols else None

    if backend_name in ("mssql", "postgresql"):
        rows = backend.execute_query(
            "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS "
            "WHERE TABLE_SCHEMA = :schema AND TABLE_NAME = :table",
            {"schema": schema, "table": table},
        )
        cols = [r["COLUMN_NAME"] for r in rows]
        return cols if cols else None

    return None


def verify_updates(
    updates: dict[str, UpdateConfig],
    backend_name: str,
    backend: DatabaseBackend,
) -> dict[str, Any]:
    """Per-update validation: table exists, key column exists, fields exist.

    Returns:
        Standard verifier result dict with three rows per update
        (``<name>.table``, ``<name>.key_column``, ``<name>.fields``) and
        an ``overall_ok`` flag. When the table is missing, all three rows
        are emitted as ``[ERR]`` rather than skipped.
    """
    result: dict[str, Any] = {}
    for name, ucfg in updates.items():
        cols = _list_table_columns(backend, backend_name, ucfg.schema_name, ucfg.table)

        if cols is None:
            qualified = f"{ucfg.schema_name}.{ucfg.table}".lstrip(".")
            result[f"{name}.table"] = _entry(
                ok=False, value=qualified, error="Table not found"
            )
            result[f"{name}.key_column"] = _entry(
                ok=False, value="(skipped)", error="Table not found"
            )
            result[f"{name}.fields"] = _entry(
                ok=False, value="(skipped)", error="Table not found"
            )
            continue

        result[f"{name}.table"] = _entry(ok=True, value=ucfg.table)

        key_field = ucfg.key.field if ucfg.key else ""
        if not key_field:
            result[f"{name}.key_column"] = _entry(
                ok=False, value="(none)", error="No key configured"
            )
        elif key_field not in cols:
            result[f"{name}.key_column"] = _entry(
                ok=False,
                value=key_field,
                error=f"Column not found in {ucfg.table}",
            )
        else:
            result[f"{name}.key_column"] = _entry(ok=True, value=key_field)

        missing = [f.field for f in ucfg.fields if f.field not in cols]
        if missing:
            result[f"{name}.fields"] = _entry(
                ok=False,
                value=", ".join(f.field for f in ucfg.fields),
                error=f"Missing columns: {', '.join(missing)}",
            )
        else:
            result[f"{name}.fields"] = _entry(
                ok=True, value=f"{len(ucfg.fields)} columns"
            )

    result["overall_ok"] = all(
        entry["ok"] for key, entry in result.items() if key != "overall_ok"
    )
    return result


def collect_install_instructions(
    sections: list[tuple[str, dict[str, Any]]],
) -> dict[str, Any]:
    """Aggregate non-empty ``install_hint`` strings from failed entries.

    Returns:
        Result dict with one entry per unique install hint, preserving
        the order in which they were first seen. ``overall_ok`` is always
        ``True`` because this section is informational.
    """
    hints: list[str] = []
    for _title, section in sections:
        for key, entry in section.items():
            if key == "overall_ok":
                continue
            hint = entry.get("install_hint", "")
            if hint and not entry["ok"]:
                hints.append(hint)

    unique_hints = list(dict.fromkeys(hints))
    result: dict[str, Any] = {
        f"hint_{i}": _entry(ok=True, value=hint) for i, hint in enumerate(unique_hints)
    }
    result["overall_ok"] = True
    return result


def render_skip_m2_summary(query_count: int, update_count: int) -> str:
    """Return the one-line summary printed when M2 is skipped.

    Returns:
        ``"connection failed; skipped N query checks, M update checks"``.
    """
    return (
        f"connection failed; skipped {query_count} query checks, "
        f"{update_count} update checks"
    )


def _resolve_backend(
    config_path: Path | None,
    db_config_path: Path | None,
) -> str:
    """Best-effort backend resolution from configs.

    Returns:
        Backend name (e.g. ``sqlite``) or ``"unknown"`` on any failure.
    """
    try:
        resolved_query = discover_query_config(config_path, project_dir=Path.cwd())
        qcfg = load_query_config(resolved_query)
        dbcfg = load_database_config(db_config_path)
        conn = resolve_connection(qcfg, dbcfg)
        return conn.backend
    except (ValueError, OSError) as exc:
        logger.debug("Could not resolve backend: %s", exc)
        return "unknown"


def add_subparser(subparsers: argparse._SubParsersAction) -> None:  # type: ignore[type-arg]
    """Register `verify` subparser (no subcommand-level flags; uses top-level)."""
    subparsers.add_parser(
        "verify",
        help=(
            "Validate environment, configuration, dependencies, and connectivity. "
            "Exit 0 on success, 1 on any error"
        ),
        formatter_class=WideHelpFormatter,
    )


def _resolve_connection_for_verify(
    config_path: Path | None,
    db_config_path: Path | None,
) -> ConnectionConfig | None:
    """Best-effort connection resolution for the CONNECTION section.

    Returns:
        Resolved :class:`ConnectionConfig`, or ``None`` if configs cannot
        be loaded or the named connection cannot be resolved.
    """
    try:
        resolved_query = discover_query_config(config_path, project_dir=Path.cwd())
        qcfg = load_query_config(resolved_query)
        dbcfg = load_database_config(db_config_path)
        return resolve_connection(qcfg, dbcfg)
    except (ValueError, OSError) as exc:
        logger.debug("Could not resolve connection: %s", exc)
        return None


def _load_query_config_for_counts(
    config_path: Path | None,
) -> tuple[int, int]:
    """Return ``(query_count, update_count)`` from the project query config.

    Returns:
        ``(0, 0)`` if the config cannot be loaded.
    """
    try:
        resolved_query = discover_query_config(config_path, project_dir=Path.cwd())
        qcfg = load_query_config(resolved_query)
        return len(qcfg.queries), len(qcfg.updates)
    except (ValueError, OSError) as exc:
        logger.debug("Could not load query config for counts: %s", exc)
        return 0, 0


def _load_query_config_for_m2(
    config_path: Path | None,
) -> QueryFileConfig | None:
    """Return the parsed :class:`QueryFileConfig` or ``None`` on failure."""
    try:
        resolved_query = discover_query_config(config_path, project_dir=Path.cwd())
        return load_query_config(resolved_query)
    except (ValueError, OSError) as exc:
        logger.debug("Could not load query config for M2: %s", exc)
        return None


def run(args: argparse.Namespace) -> int:
    """Entry point for the ``verify`` subcommand.

    Returns:
        Process exit code (``0`` if every section passed, ``1`` otherwise).
    """
    sections: list[tuple[str, dict[str, Any]]] = []
    sections.append(("ENVIRONMENT", verify_environment()))
    sections.append(
        (
            "CONFIG",
            verify_config_files(args.config, args.database_config),
        )
    )
    backend = _resolve_backend(args.config, args.database_config)
    sections.append(("DEPENDENCIES", verify_dependencies(backend)))
    sections.append(("BUILTIN", verify_builtin()))

    skip_summary: str | None = None
    connection = _resolve_connection_for_verify(args.config, args.database_config)
    if connection is not None:
        connection_result, open_backend = verify_connection(connection)
        sections.append(("CONNECTION", connection_result))
        if connection_result.get("overall_ok", False) and open_backend is not None:
            try:
                query_config = _load_query_config_for_m2(args.config)
                if query_config is not None:
                    sections.append(
                        (
                            "QUERIES",
                            verify_queries(
                                query_config.queries, connection.backend, open_backend
                            ),
                        )
                    )
                    sections.append(
                        (
                            "UPDATES",
                            verify_updates(
                                query_config.updates, connection.backend, open_backend
                            ),
                        )
                    )
            finally:
                open_backend.close()
        else:
            n_queries, n_updates = _load_query_config_for_counts(args.config)
            skip_summary = render_skip_m2_summary(n_queries, n_updates)

    install_section = collect_install_instructions(sections)
    if any(key != "overall_ok" for key in install_section):
        sections.append(("INSTALL INSTRUCTIONS", install_section))

    return _print_and_summarize(sections, skip_summary=skip_summary)


def _print_and_summarize(
    sections: list[tuple[str, dict[str, Any]]],
    *,
    skip_summary: str | None = None,
) -> int:
    """Print every section's rows and the trailing summary line.

    Returns:
        Process exit code (0 if no errors, 1 otherwise).
    """
    ok_count = 0
    warn_count = 0
    err_count = 0
    for title, result in sections:
        _print_section(title)
        for key, entry in result.items():
            if key == "overall_ok":
                continue
            if entry.get("warn"):
                print(
                    _format_row(
                        "warn",
                        key,
                        entry.get("value", ""),
                        entry.get("error", ""),
                    )
                )
                warn_count += 1
            elif entry["ok"]:
                print(_format_row("ok", key, entry.get("value", "")))
                ok_count += 1
            else:
                print(
                    _format_row(
                        "err",
                        key,
                        entry.get("value", ""),
                        entry.get("error", ""),
                    )
                )
                err_count += 1
        print()
    if skip_summary is not None:
        print(skip_summary)
    print(f"{ok_count} checks passed, {warn_count} warnings, {err_count} errors")
    return _compute_exit_code(err_count)
