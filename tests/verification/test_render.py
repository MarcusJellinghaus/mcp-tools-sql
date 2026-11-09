"""Tests for `mcp_tools_sql.verification.render`."""

from __future__ import annotations

from mcp_tools_sql.verification import CheckResult, VerifyResult, VerifySection
from mcp_tools_sql.verification._helpers import (
    checks_ok,
    make_entry,
    make_warn_entry,
)
from mcp_tools_sql.verification.render import format_row, render_short, row_status

ALL_PASS_LINE = (
    "Config loaded. Connections: A, B, C reachable. 12 queries, 3 updates OK."
)


def _section(title: str, checks: dict[str, CheckResult]) -> VerifySection:
    return {"title": title, "ok": checks_ok(checks), "checks": checks}


def _result(
    sections: list[VerifySection],
    *,
    connections: dict[str, bool] | None = None,
    query_count: int = 12,
    update_count: int = 3,
    allow_updates: bool | None = True,
    skipped_queries: int | None = None,
    skipped_updates: int | None = None,
) -> VerifyResult:
    return {
        "sections": sections,
        "skipped_queries": skipped_queries,
        "skipped_updates": skipped_updates,
        "summary": {
            "connections": (
                {"A": True, "B": True, "C": True}
                if connections is None
                else connections
            ),
            "query_count": query_count,
            "update_count": update_count,
            "allow_updates": allow_updates,
        },
    }


def _ok(value: str = "ok") -> dict[str, CheckResult]:
    return {"row": make_entry(ok=True, value=value)}


def _passing_sections(**overrides: dict[str, CheckResult]) -> list[VerifySection]:
    titles = ["ENVIRONMENT", "CONFIG", "DEPENDENCIES", "BUILTIN", "CONNECTION"]
    titles += ["QUERIES", "UPDATES"]
    return [_section(title, overrides.get(title, _ok())) for title in titles]


def test_row_status() -> None:
    """`row_status` maps passing / warning / error rows to ok / warn / err."""
    assert row_status(make_entry(ok=True)) == "ok"
    assert row_status(make_warn_entry("v")) == "warn"
    assert row_status(make_entry(ok=False, error="boom")) == "err"


def test_all_passing_is_one_line() -> None:
    """All passing: exactly the summary line, no row lines."""
    assert render_short(_result(_passing_sections())) == ALL_PASS_LINE


def test_err_row_in_queries() -> None:
    """An ERR row in QUERIES is listed under its section; OK rows are not."""
    bad = make_entry(ok=False, value="EXPLAIN", error="syntax error")
    checks = {"good.sql": make_entry(ok=True, value="EXPLAIN ok"), "bad.sql": bad}
    text = render_short(_result(_passing_sections(QUERIES=checks)))

    assert text.splitlines() == [
        "Config loaded. Connections: A, B, C reachable. "
        "12 queries with errors, 3 updates OK.",
        "",
        "=== QUERIES ===",
        format_row("err", "bad.sql", "EXPLAIN", "syntax error"),
    ]
    assert text.splitlines()[-1].startswith("[ERR]")
    assert text.splitlines()[-1].endswith("- syntax error")


def test_warn_row_in_config() -> None:
    """A WARN row leaves CONFIG ok and is listed under `=== CONFIG ===`."""
    checks = {
        "query_config_parse": make_entry(ok=True, value="loaded"),
        "sensitive_keys": make_warn_entry("password", "move it"),
    }
    lines = render_short(_result(_passing_sections(CONFIG=checks))).splitlines()

    assert lines[0].startswith("Config loaded.")
    assert lines[1:] == [
        "",
        "=== CONFIG ===",
        format_row("warn", "sensitive_keys", "password", "move it"),
    ]


def test_config_errors() -> None:
    """A failing CONFIG section reads `Config has errors.`."""
    checks = {"query_config_parse": make_entry(ok=False, error="bad")}
    text = render_short(_result(_passing_sections(CONFIG=checks)))
    assert text.startswith("Config has errors.")


def test_no_connection_section() -> None:
    """Without CONNECTION, connections and entries are not checked."""
    sections = [
        _section(title, _ok())
        for title in ("ENVIRONMENT", "CONFIG", "DEPENDENCIES", "BUILTIN")
    ]
    result = _result(sections, connections={}, query_count=0, update_count=0)
    assert render_short(result) == (
        "Config loaded. Connections: not checked (targets unresolved). "
        "0 queries, 0 updates not checked."
    )


def test_skipped_by_failed_connection() -> None:
    """Skip counts render as `not checked (connection failed)`."""
    sections = [
        _section(title, _ok())
        for title in ("ENVIRONMENT", "CONFIG", "DEPENDENCIES", "BUILTIN")
    ]
    sections.append(
        _section("CONNECTION", {"select_1": make_entry(ok=False, error="down")})
    )
    result = _result(
        sections,
        connections={"A": False},
        query_count=2,
        update_count=1,
        skipped_queries=2,
        skipped_updates=1,
    )
    first = render_short(result).splitlines()[0]
    assert first.endswith("2 queries, 1 updates not checked (connection failed).")


def test_reachable_and_unreachable_connections() -> None:
    """Reachable and unreachable connections are joined with `; `."""
    result = _result(_passing_sections(), connections={"A": True, "B": False})
    assert "Connections: A reachable; B unreachable." in render_short(result)


def test_allow_updates_false_adds_suffix() -> None:
    """`allow_updates=False` marks updates as not exposed."""
    result = _result(_passing_sections(), allow_updates=False)
    assert render_short(result) == (
        "Config loaded. Connections: A, B, C reachable. "
        "12 queries, 3 updates OK (not exposed: allow_updates=false)."
    )


def test_allow_updates_none_or_true_adds_nothing() -> None:
    """`allow_updates` of `None` or `True` adds no suffix."""
    for allow in (None, True):
        result = _result(_passing_sections(), allow_updates=allow)
        assert render_short(result) == ALL_PASS_LINE
