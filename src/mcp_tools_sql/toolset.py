"""Build every SQL tool as a framework-neutral ``ToolSpec``.

One factory for every consumer: the MCP server, the CLI ``tool`` subcommand
and agent-workbench all get the same tools (names, descriptions, validation,
groups) from :func:`build_toolset`. Nothing here imports ``mcp``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from mcp_tools_sql.backends.connection_check import check_connections
from mcp_tools_sql.backends.registry import BackendRegistry
from mcp_tools_sql.config.loader import (
    load_database_config,
    load_query_config,
    resolve_targets,
)
from mcp_tools_sql.count_tools import CountTools
from mcp_tools_sql.query_tools import QueryTools
from mcp_tools_sql.schema_tools import SchemaTools, build_read_databases_tool
from mcp_tools_sql.summarize import SummarizeTools
from mcp_tools_sql.tool_logging import log_tool_call
from mcp_tools_sql.update_tools import UpdateTools
from mcp_tools_sql.utils.tool_spec import ToolCollector, tool_spec
from mcp_tools_sql.validation_tools import ValidationTools
from mcp_tools_sql.verification import verify_all
from mcp_tools_sql.verification.orchestrator import collect_sections
from mcp_tools_sql.verification.render import render_short

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable
    from pathlib import Path

    from mcp_tools_sql.config.models import (
        DatabaseConfig,
        QueryFileConfig,
        ResolvedTargets,
    )
    from mcp_tools_sql.utils.tool_spec import ToolSpec
    from mcp_tools_sql.utils.toolkit import VerifyItem, VerifyStatus
    from mcp_tools_sql.verification import CheckResult

_READ_DATABASES_DESC = (
    "List the (connection, database) targets configured for this server, with "
    "their backend, description, and which one is the default. This reports the "
    "*configured* targets from the server config — not a live `sys.databases` "
    "listing — so a database missing here means it is not configured, not that "
    "it does not exist."
)

_VERIFY_DESC = (
    "Re-run the `mcp-tools-sql verify` checks against the config files on disk: config "
    "parse, dependencies, connectivity of every configured connection, EXPLAIN of every "
    "configured query, update tables/columns. Returns a short summary plus every failing "
    "or warning row. Use it after a query fails to check config and connectivity. Takes "
    "a few seconds."
)

_VERIFY_NOTE = (
    "Note: verify re-read the config files from disk; the running tools "
    "keep the config they were built with."
)


@dataclass(frozen=True, eq=False)
class SqlToolset:
    """Every SQL tool spec plus the objects they were built from.

    Owns ``registry``: :meth:`close` closes every backend connection the
    tools opened. Usable as a context manager.
    """

    specs: tuple[ToolSpec, ...]
    targets: ResolvedTargets
    query_config: QueryFileConfig
    registry: BackendRegistry

    def close(self) -> None:
        """Close every backend connection held by the registry."""
        self.registry.close_all()

    def __enter__(self) -> SqlToolset:
        """Return the toolset itself.

        Returns:
            This toolset.
        """
        return self

    def __exit__(self, *exc: object) -> None:
        """Close the toolset."""
        self.close()


def _build_verify_tool(
    query_config_path: Path | None, database_config_path: Path | None
) -> Callable[[], Awaitable[str]]:
    """Build the ``verify`` tool over the given config paths.

    The tool re-reads the configs from disk with its own backend registry;
    it never touches the toolset's registry. ``None`` paths fall back to
    the same discovery ``verify_all`` uses.

    Returns:
        An async callable returning the short verify summary.
    """

    async def verify() -> str:
        """Re-run the verify checks and return the short summary.

        Returns:
            The short summary followed by the config note.
        """
        async with log_tool_call("verify"):
            result = verify_all(query_config_path, database_config_path)
        return f"{render_short(result)}\n\n{_VERIFY_NOTE}"

    return verify


def assemble_toolset(
    config: QueryFileConfig,
    targets: ResolvedTargets,
    registry: BackendRegistry,
    allow_updates: bool,
    *,
    query_config_path: Path | None = None,
    database_config_path: Path | None = None,
) -> SqlToolset:
    """Build every tool spec from already-loaded config objects.

    Takes ownership of ``registry``: it is closed if the build fails, and by
    :meth:`SqlToolset.close` otherwise. Tool order: built-ins,
    ``read_databases`` (multi-target only), ``verify``, configured queries,
    configured updates (only when ``allow_updates``).

    Returns:
        The assembled toolset.
    """
    sink = ToolCollector()
    try:
        SchemaTools(registry, targets, limits=config.limits).register(sink)
        ValidationTools(registry, targets).register(sink)
        CountTools(registry, targets).register(sink)
        SummarizeTools(registry, targets).register(sink)
        if targets.is_multi:
            sink.add(
                tool_spec(
                    build_read_databases_tool(targets),
                    group="sql.schema",
                    read_only=True,
                    name="read_databases",
                    description=_READ_DATABASES_DESC,
                )
            )
        sink.add(
            tool_spec(
                _build_verify_tool(query_config_path, database_config_path),
                group="sql.validation",
                read_only=True,
                name="verify",
                description=_VERIFY_DESC,
            )
        )
        QueryTools(registry, targets, config.queries, limits=config.limits).register(
            sink
        )
        if allow_updates:
            UpdateTools(registry, targets, config.updates).register(sink)
    except BaseException:
        registry.close_all()
        raise
    return SqlToolset(sink.specs, targets, config, registry)


def _raise_on_dependency_errors(db_config: DatabaseConfig) -> None:
    """Raise ValueError for the first connection failing the dependency check.

    Raises:
        ValueError: Naming the connection, the failing check and its hint.
    """
    for row in check_connections(db_config.connections):
        if not row.ok:
            hint = f" ({row.hint})" if row.hint else ""
            raise ValueError(
                f"Connection {row.connection!r}: {row.key}: "
                f"{row.error or row.value}{hint}"
            )


def build_toolset(
    query_config: Path, database_config: Path | None = None
) -> SqlToolset:
    """Load both config files and build every tool spec.

    Callable repeatedly: to pick up config edits, build a new toolset, swap
    it in and close the old one. A broken setup (unsupported backend,
    missing pyodbc or ODBC driver) raises before any connection is opened.

    Returns:
        The assembled toolset; close it when done.
    """
    qcfg = load_query_config(query_config)
    dbcfg = load_database_config(database_config)
    _raise_on_dependency_errors(dbcfg)
    targets = resolve_targets(qcfg, dbcfg)
    return assemble_toolset(
        qcfg,
        targets,
        BackendRegistry(),
        dbcfg.security.allow_updates,
        query_config_path=query_config,
        database_config_path=database_config,
    )


def _status(row: CheckResult) -> VerifyStatus:
    """Map a verifier row to a ``VerifyItem`` status.

    Returns:
        ``"ok"``, ``"warning"`` or ``"error"``.
    """
    if row["ok"]:
        return "ok"
    return "warning" if row["severity"] == "warning" else "error"


def _message(row: CheckResult) -> str:
    """Join a verifier row's value and error.

    Returns:
        ``"value - error"``, or whichever of the two is non-empty.
    """
    return " - ".join(p for p in (row["value"], row.get("error", "")) if p)


def verify(
    query_config: Path,
    database_config: Path | None = None,
    *,
    connect: bool = False,
) -> list[VerifyItem]:
    """Verify the setup :func:`build_toolset` would use on the same paths.

    Never raises for problems it detects: each becomes an ``error`` or
    ``warning`` item. With ``connect=False`` (the default) it opens no
    connection, does no DNS lookup and runs no subprocess; ``connect=True``
    adds the connection probes, EXPLAIN of every query and the update
    checks. The ``toolset.build`` item runs the real :func:`build_toolset`,
    so when every item passes, building the toolset succeeds.

    Returns:
        One item per check in section order, named
        ``<section lowercased>.<check key>``.
    """
    # The result contract is only needed here: build_toolset and server start
    # must not pay for its import (#39; toolkit pulls in jsonschema).
    from mcp_tools_sql.utils.toolkit import (  # pylint: disable=import-outside-toplevel
        VerifyItem,
    )

    sections = collect_sections(
        query_config,
        database_config,
        connect=connect,
        build_probe=lambda: build_toolset(query_config, database_config).close(),
    )
    return [
        VerifyItem(
            name=f"{section['title'].lower()}.{key}",
            status=_status(row),
            message=_message(row),
            hint=row.get("install_hint") or None,
        )
        for section in sections
        for key, row in section["checks"].items()
    ]
