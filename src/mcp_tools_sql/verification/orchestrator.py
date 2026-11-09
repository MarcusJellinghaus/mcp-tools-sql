"""Orchestrator: section composition, discovery helpers, skip-summary."""

from __future__ import annotations

import logging
from pathlib import Path

from mcp_tools_sql.backends.base import DatabaseBackend
from mcp_tools_sql.backends.registry import BackendRegistry
from mcp_tools_sql.config.loader import (
    discover_query_config,
    load_database_config,
    load_query_config,
    resolve_targets,
)
from mcp_tools_sql.config.models import QueryFileConfig, ResolvedTargets
from mcp_tools_sql.verification._helpers import (
    CheckResult,
    VerifyResult,
    VerifySection,
    checks_ok,
    make_entry,
)
from mcp_tools_sql.verification.builtin import verify_builtin
from mcp_tools_sql.verification.config_files import verify_config_files
from mcp_tools_sql.verification.connection import verify_connection
from mcp_tools_sql.verification.dependencies import verify_dependencies
from mcp_tools_sql.verification.environment import verify_environment
from mcp_tools_sql.verification.queries import verify_queries
from mcp_tools_sql.verification.updates import verify_updates

logger = logging.getLogger(__name__)


def _resolve_targets_for_verify(
    config_path: Path | None,
    db_config_path: Path | None,
) -> ResolvedTargets | None:
    """Best-effort target resolution for the CONNECTION section.

    Returns:
        Resolved :class:`ResolvedTargets`, or ``None`` if configs cannot
        be loaded or the file-default connection cannot be resolved.
    """
    try:
        resolved_query = discover_query_config(config_path, project_dir=Path.cwd())
        qcfg = load_query_config(resolved_query)
        dbcfg = load_database_config(db_config_path)
        return resolve_targets(qcfg, dbcfg)
    except (ValueError, OSError) as exc:
        logger.debug("Could not resolve targets: %s", exc)
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
    registry: BackendRegistry,
) -> tuple[dict[str, CheckResult], bool, dict[tuple[str, str], bool]]:
    """Probe every ``(connection, database)`` pair via the registry.

    Merges each pair's rows into one CONNECTION rows dict, prefixing every
    row key with the pair label (``<connection>/<database>``) so a single
    section carries one row-group per pair. The registry owns backend
    lifecycle; on backend-creation failure the pair's ``select_1`` row records
    the error and probing continues.

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
) -> VerifyResult:
    """Run every verification section and return a :class:`VerifyResult`.

    Owns canonical section ordering:
    ENVIRONMENT → CONFIG → DEPENDENCIES → BUILTIN → CONNECTION →
    QUERIES → UPDATES → INSTALL INSTRUCTIONS.

    Returns:
        A :class:`VerifyResult` whose ``sections`` follow the order above.
        ``skipped_queries`` / ``skipped_updates`` hold the unchecked entry
        counts when the default connection failed, else ``None``.
    """
    sections: list[VerifySection] = []
    sections.append(_section("ENVIRONMENT", verify_environment()))
    sections.append(
        _section("CONFIG", verify_config_files(config_path, db_config_path))
    )
    resolved_targets = _resolve_targets_for_verify(config_path, db_config_path)
    default_target = resolved_targets.default if resolved_targets is not None else None
    backend = default_target.backend_name if default_target is not None else "unknown"
    configured_driver = (
        default_target.config.driver
        if default_target is not None and backend == "mssql"
        else ""
    )
    sections.append(
        _section("DEPENDENCIES", verify_dependencies(backend, configured_driver))
    )
    sections.append(_section("BUILTIN", verify_builtin()))

    skipped_queries: int | None = None
    skipped_updates: int | None = None
    if resolved_targets is not None:
        registry = BackendRegistry()
        try:
            connection_checks, default_ok, reachable = _verify_connections(
                resolved_targets, registry
            )
            sections.append(_section("CONNECTION", connection_checks))
            if default_ok:
                query_config = _load_query_config_for_m2(config_path)
                if query_config is not None:
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
                skipped_queries, skipped_updates = _load_query_config_for_counts(
                    config_path
                )
        finally:
            registry.close_all()

    install_checks = collect_install_instructions(sections)
    if install_checks:
        sections.append(_section("INSTALL INSTRUCTIONS", install_checks))

    return {
        "sections": sections,
        "skipped_queries": skipped_queries,
        "skipped_updates": skipped_updates,
    }
