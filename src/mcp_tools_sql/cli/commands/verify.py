"""verify subcommand."""

from __future__ import annotations

import argparse
import importlib.metadata
import logging
import sys
from pathlib import Path
from typing import Any

from mcp_tools_sql.cli.parsers import WideHelpFormatter
from mcp_tools_sql.config.loader import (
    discover_query_config,
    load_database_config,
    load_query_config,
    resolve_connection,
)
from mcp_tools_sql.schema_tools import load_default_queries

logger = logging.getLogger(__name__)

STATUS_SYMBOLS: dict[str, str] = {"ok": "[OK]", "err": "[ERR]", "warn": "[WARN]"}
_LABEL_WIDTH = 28


def _pad(text: str, width: int) -> str:
    """Left-justify ``text`` to ``width`` (truncate if longer)."""
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
    """Build a single verifier result entry with the standard shape."""
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
        entry["ok"] for key, entry in result.items() if key != "overall_ok"
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


def run(args: argparse.Namespace) -> int:
    """Entry point. Returns process exit code."""
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
    return _print_and_summarize(sections)


def _print_and_summarize(sections: list[tuple[str, dict[str, Any]]]) -> int:
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
            if entry["ok"]:
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
    print(f"{ok_count} checks passed, {warn_count} warnings, {err_count} errors")
    return _compute_exit_code(err_count)
