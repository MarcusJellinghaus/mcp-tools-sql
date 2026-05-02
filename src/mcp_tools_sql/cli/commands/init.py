"""init subcommand."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

import tomlkit

from mcp_tools_sql.cli.parsers import WideHelpFormatter

logger = logging.getLogger(__name__)

BACKENDS = ("sqlite", "mssql", "postgresql")

_PROJECT_TEMPLATE_STANDALONE = """\
connection = "default"

# Example SELECT query (uncomment to enable):
# [queries.get_user]
# description = "Look up a user by id"
# sql = "SELECT * FROM users WHERE id = :id"
# max_rows = 1
#
# [queries.get_user.params.id]
# name = "id"
# type = "int"
# description = "User id"
# required = true

# Example UPDATE definition (uncomment to enable):
# [updates.set_user_email]
# description = "Update a user's email"
# schema = "dbo"
# table = "users"
#
# [updates.set_user_email.key]
# field = "id"
# type = "int"
# description = "User id"
#
# [[updates.set_user_email.fields]]
# field = "email"
# type = "str"
# description = "New email"

# Default schema-introspection queries auto-load from the package.
# Uncomment any block below to override the default for a specific query.
# [queries.read_schemas]
# sql = "..."
#
# [queries.read_tables]
# sql = "..."
# (etc - see src/mcp_tools_sql/default_queries.toml for the full set)
"""


_DATABASE_CONFIG_SQLITE = """\
[connections.default]
backend = "sqlite"
path = "./mydb.db"
"""

_DATABASE_CONFIG_MSSQL = """\
[connections.default]
backend = "mssql"
host = ""
port = 1433
database = ""
username = ""
credential_env_var = "MSSQL_PASSWORD"
driver = "ODBC Driver 18 for SQL Server"
"""

_DATABASE_CONFIG_POSTGRESQL = """\
[connections.default]
backend = "postgresql"
host = ""
port = 5432
database = ""
username = ""
credential_env_var = "POSTGRES_PASSWORD"
"""


def add_subparser(subparsers: argparse._SubParsersAction) -> None:  # type: ignore[type-arg]
    """Register `init` subparser and its flags."""
    p = subparsers.add_parser(
        "init",
        help=(
            "Create starter mcp-tools-sql.toml and ~/.mcp-tools-sql/config.toml "
            "for a chosen backend"
        ),
        formatter_class=WideHelpFormatter,
    )
    p.add_argument(
        "--backend",
        choices=list(BACKENDS),
        required=True,
        help="Database backend to scaffold for (sqlite, mssql, postgresql)",
    )
    p.add_argument(
        "--output",
        type=Path,
        default=Path("mcp-tools-sql.toml"),
        help="Path to write the project query config (default: ./mcp-tools-sql.toml)",
    )
    p.add_argument(
        "--pyproject",
        action="store_true",
        help=(
            "Append [tool.mcp-tools-sql] to existing pyproject.toml instead of "
            "writing a standalone file"
        ),
    )


def run(args: argparse.Namespace) -> int:
    """Dispatch to standalone or pyproject mode.

    Returns:
        Process exit code (``0`` on success, non-zero on failure).
    """
    backend: str = args.backend
    if args.pyproject:
        if args.output != Path("mcp-tools-sql.toml"):
            logger.debug(
                "--output=%s ignored because --pyproject was supplied", args.output
            )
        return _run_pyproject(backend)
    return _run_standalone(backend, args.output)


def _build_project_template_standalone(backend: str) -> str:
    """Return full standalone `mcp-tools-sql.toml` content for ``backend``."""
    del backend
    return _PROJECT_TEMPLATE_STANDALONE


def _build_pyproject_inserted_table() -> tomlkit.items.Table:
    """Build the tomlkit Table to insert under `[tool.mcp-tools-sql]`.

    Returns:
        The constructed :class:`tomlkit.items.Table` with default values
        and explanatory comments.
    """
    table = tomlkit.table()
    table["connection"] = "default"
    table.add(tomlkit.nl())
    table.add(
        tomlkit.comment("For commented examples of [queries.*] / [updates.*] blocks,")
    )
    table.add(tomlkit.comment("see the standalone mcp-tools-sql.toml template"))
    table.add(tomlkit.comment("(run `mcp-tools-sql init` without --pyproject)."))
    return table


def _build_database_config_template(backend: str) -> str:
    """Return per-backend `~/.mcp-tools-sql/config.toml` content.

    Returns:
        TOML content string for the requested backend.

    Raises:
        ValueError: If ``backend`` is not one of the supported values.
    """
    if backend == "sqlite":
        return _DATABASE_CONFIG_SQLITE
    if backend == "mssql":
        return _DATABASE_CONFIG_MSSQL
    if backend == "postgresql":
        return _DATABASE_CONFIG_POSTGRESQL
    raise ValueError(f"Unknown backend: {backend!r}")


def _database_config_path() -> Path:
    """Return target path for database config file."""
    return Path.home() / ".mcp-tools-sql" / "config.toml"


def _write_database_config_if_absent(backend: str) -> None:
    """Write the database config file, or print a message if it already exists."""
    path = _database_config_path()
    if path.exists():
        print(f"Existing {path} left untouched.")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_build_database_config_template(backend), encoding="utf-8")
    print(f"Wrote {path}")


def _run_standalone(backend: str, output: Path) -> int:
    """Write standalone `mcp-tools-sql.toml` and the database config.

    Returns:
        Process exit code (``0`` on success, ``1`` if ``output`` already exists).
    """
    if output.exists():
        print(f"{output} already exists - refusing to overwrite.")
        return 1
    output.write_text(_build_project_template_standalone(backend), encoding="utf-8")
    print(f"Wrote {output}")
    _write_database_config_if_absent(backend)
    return 0


def _run_pyproject(backend: str) -> int:
    """Append `[tool.mcp-tools-sql]` to `pyproject.toml` and write db config.

    Returns:
        Process exit code (``0`` on success, ``1`` if ``pyproject.toml`` is
        missing or already contains a ``[tool.mcp-tools-sql]`` section).
    """
    pyproject = Path("pyproject.toml")
    if not pyproject.exists():
        print("pyproject.toml not found in current directory - refusing.")
        return 1

    doc = tomlkit.parse(pyproject.read_text(encoding="utf-8"))

    tool_table = doc.get("tool")
    if tool_table is not None and "mcp-tools-sql" in tool_table:
        print(
            "[tool.mcp-tools-sql] already exists in pyproject.toml "
            "- refusing to overwrite."
        )
        return 1

    if tool_table is None:
        tool_table = tomlkit.table()
        doc["tool"] = tool_table

    tool_table["mcp-tools-sql"] = _build_pyproject_inserted_table()

    pyproject.write_text(tomlkit.dumps(doc), encoding="utf-8")
    print("Appended [tool.mcp-tools-sql] to pyproject.toml")
    _write_database_config_if_absent(backend)
    return 0
