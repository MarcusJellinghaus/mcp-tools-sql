"""Orchestrator: section composition, discovery helpers, skip-summary."""

from __future__ import annotations

import logging
from pathlib import Path

from mcp_tools_sql.backends.base import DatabaseBackend
from mcp_tools_sql.backends.registry import BackendRegistry
from mcp_tools_sql.config.loader import resolve_targets
from mcp_tools_sql.config.models import ResolvedTargets
from mcp_tools_sql.verification._helpers import (
    CheckResult,
    VerifyResult,
    VerifySection,
    VerifySummary,
    checks_ok,
    make_entry,
)
from mcp_tools_sql.verification.builtin import verify_builtin
from mcp_tools_sql.verification.config_files import (
    LoadedConfigs,
    verify_config_files,
)
from mcp_tools_sql.verification.connection import verify_connection
from mcp_tools_sql.verification.dependencies import verify_dependencies
from mcp_tools_sql.verification.environment import verify_environment
from mcp_tools_sql.verification.queries import verify_queries
from mcp_tools_sql.verification.updates import verify_updates

logger = logging.getLogger(__name__)


def _resolve_loaded_targets(loaded: LoadedConfigs) -> ResolvedTargets | None:
    """Best-effort target resolution for the CONNECTION section.

    Returns:
        Resolved :class:`ResolvedTargets`, or ``None`` if either config did
        not load or the file-default connection cannot be resolved.
    """
    if loaded.query_config is None or loaded.db_config is None:
        return None
    try:
        return resolve_targets(loaded.query_config, loaded.db_config)
    except ValueError as exc:
        logger.debug("Could not resolve targets: %s", exc)
        return None


def _build_summary(
    loaded: LoadedConfigs,
    reachable: dict[tuple[str, str], bool],
) -> VerifySummary:
    """Condense connection reachability, entry counts and ``allow_updates``.

    Returns:
        A :class:`VerifySummary`; a connection is ``True`` only when every one
        of its database probes passed.
    """
    connections: dict[str, bool] = {}
    for (conn, _db), ok in reachable.items():
        connections[conn] = connections.get(conn, True) and ok
    qc = loaded.query_config
    return {
        "connections": connections,
        "query_count": len(qc.queries) if qc else 0,
        "update_count": len(qc.updates) if qc else 0,
        "allow_updates": loaded.allow_updates,
    }


def collect_install_instructions(
    sections: list[VerifySection],
) -> dict[str, CheckResult]:
    """Aggregate non-empty ``install_hint`` strings from ERR rows.

    Returns:
        One passing ``hint_<i>`` row per unique install hint, preserving the
        order in which they were first seen.
    """
    hints: list[str] = []
    for section in sections:
        for entry in section["checks"].values():
            hint = entry.get("install_hint", "")
            if hint and not entry["ok"] and entry["severity"] == "error":
                hints.append(hint)

    unique_hints = list(dict.fromkeys(hints))
    return {
        f"hint_{i}": make_entry(ok=True, value=hint)
        for i, hint in enumerate(unique_hints)
    }


def _section(title: str, checks: dict[str, CheckResult]) -> VerifySection:
    """Wrap verifier rows into a titled section whose ``ok`` follows the rows.

    Returns:
        A :class:`VerifySection`.
    """
    return {"title": title, "ok": checks_ok(checks), "checks": checks}


def render_skip_m2_summary(query_count: int, update_count: int) -> str:
    """Return the one-line summary printed when M2 is skipped.

    Returns:
        ``"connection failed; skipped N query checks, M update checks"``.
    """
    return (
        f"connection failed; skipped {query_count} query checks, "
        f"{update_count} update checks"
    )


def _verify_connections(
    targets: ResolvedTargets,
    registry: BackendRegistry | None,
) -> tuple[dict[str, CheckResult], bool, dict[tuple[str, str], bool]]:
    """Probe every ``(connection, database)`` pair via the registry.

    Merges each pair's rows into one CONNECTION rows dict, prefixing every
    row key with the pair label (``<connection>/<database>``) so a single
    section carries one row-group per pair. The registry owns backend
    lifecycle; on backend-creation failure the pair's ``select_1`` row records
    the error and probing continues. With ``registry=None`` (config-only
    mode) no backend is created and only the config rows are checked.

    Returns:
        Tuple ``(connection_checks, default_ok, reachable)`` where
        ``default_ok`` is True when the file-default target's probe passed (so
        M2 may run against it), and ``reachable`` maps each
        ``(connection, database)`` pair to whether its probe passed (consumed
        by the per-target M2 verifiers). A pair passes when every one of its
        rows is passing (warnings included, see :func:`checks_ok`).
    """
    result: dict[str, CheckResult] = {}
    default_ok = False
    reachable: dict[tuple[str, str], bool] = {}
    for target in targets.targets:
        label = f"{target.connection}/{target.database}"
        if registry is None:
            pair_result = verify_connection(target, None, connect=False)
        else:
            try:
                backend: DatabaseBackend | None = registry.backend_for(target)
                probe_error = ""
            except Exception as exc:  # pylint: disable=broad-except
                logger.debug("Could not create backend for %s: %s", label, exc)
                backend = None
                probe_error = str(exc)
            pair_result = verify_connection(target, backend, probe_error=probe_error)
        pair_ok = checks_ok(pair_result)
        reachable[(target.connection, target.database)] = pair_ok
        if target.is_default:
            default_ok = pair_ok
        for key, entry in pair_result.items():
            result[f"{label}.{key}"] = entry
    return result, default_ok, reachable


def verify_all(
    config_path: Path | None,
    db_config_path: Path | None,
    project_dir: Path | None = None,
) -> VerifyResult:
    """Run every verification section and return a :class:`VerifyResult`.

    Owns canonical section ordering:
    ENVIRONMENT → CONFIG → DEPENDENCIES → BUILTIN → CONNECTION →
    QUERIES → UPDATES → INSTALL INSTRUCTIONS.

    The configs are loaded once (entry by entry) and shared by every later
    section. Without ``config_path``, the query config is discovered under
    ``project_dir`` (default: the current directory).

    Returns:
        A :class:`VerifyResult` whose ``sections`` follow the order above.
        ``skipped_queries`` / ``skipped_updates`` hold the unchecked entry
        counts when the default connection failed, else ``None``.
        ``summary`` condenses reachability, entry counts and ``allow_updates``.
    """
    project_dir = project_dir or Path.cwd()
    sections: list[VerifySection] = []
    sections.append(_section("ENVIRONMENT", verify_environment()))
    loaded = verify_config_files(config_path, db_config_path, project_dir)
    sections.append(_section("CONFIG", loaded.checks))
    resolved_targets = _resolve_loaded_targets(loaded)
    sections.append(_section("DEPENDENCIES", verify_dependencies(loaded.db_config)))
    sections.append(_section("BUILTIN", verify_builtin()))

    skipped_queries: int | None = None
    skipped_updates: int | None = None
    reachable: dict[tuple[str, str], bool] = {}
    # Targets resolve only when both configs loaded, so query_config is set.
    query_config = loaded.query_config
    if resolved_targets is not None and query_config is not None:
        registry = BackendRegistry()
        try:
            connection_checks, default_ok, reachable = _verify_connections(
                resolved_targets, registry
            )
            sections.append(_section("CONNECTION", connection_checks))
            if default_ok:
                sections.append(
                    _section(
                        "QUERIES",
                        verify_queries(
                            query_config.queries,
                            resolved_targets,
                            registry,
                            reachable,
                        ),
                    )
                )
                sections.append(
                    _section(
                        "UPDATES",
                        verify_updates(
                            query_config.updates,
                            resolved_targets,
                            registry,
                            reachable,
                        ),
                    )
                )
            else:
                skipped_queries = len(query_config.queries)
                skipped_updates = len(query_config.updates)
        finally:
            registry.close_all()

    install_checks = collect_install_instructions(sections)
    if install_checks:
        sections.append(_section("INSTALL INSTRUCTIONS", install_checks))

    return {
        "sections": sections,
        "skipped_queries": skipped_queries,
        "skipped_updates": skipped_updates,
        "summary": _build_summary(loaded, reachable),
    }
