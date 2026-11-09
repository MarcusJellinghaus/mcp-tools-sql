"""Smoke tests for verification helpers."""

from __future__ import annotations

from mcp_tools_sql.verification._helpers import (
    CheckResult,
    checks_ok,
    is_passing,
    make_entry,
    make_skipped_entry,
    make_skipped_not_read_only_entry,
    make_warn_entry,
)


def test_make_entry_ok_omits_empty_optional_keys() -> None:
    """A passing row has exactly ``ok``, ``value`` and ``severity``."""
    result = make_entry(ok=True, value="x")
    assert result == {"ok": True, "value": "x", "severity": "error"}


def test_make_entry_all_fields() -> None:
    """Non-empty ``error`` and ``install_hint`` are both present."""
    result = make_entry(ok=False, error="e", install_hint="h")
    assert result == {
        "ok": False,
        "value": "",
        "severity": "error",
        "error": "e",
        "install_hint": "h",
    }


def test_check_result_keys() -> None:
    """`CheckResult` is a TypedDict with the expected keys."""
    assert set(CheckResult.__annotations__.keys()) == {
        "ok",
        "value",
        "severity",
        "error",
        "install_hint",
    }


def test_make_warn_entry_is_warning() -> None:
    """A warn row is ``ok=False`` with ``severity="warning"``."""
    result = make_warn_entry("v", "e")
    assert result["ok"] is False
    assert result["severity"] == "warning"
    assert result["value"] == "v"
    assert result["error"] == "e"
    assert is_passing(result) is True


def test_skipped_entries_are_warnings() -> None:
    """Both skip builders produce warning rows."""
    for entry in (make_skipped_entry("remote"), make_skipped_not_read_only_entry()):
        assert entry["ok"] is False
        assert entry["severity"] == "warning"
    assert "remote" in make_skipped_entry("remote")["value"]


def test_checks_ok_empty_is_true() -> None:
    """No rows means the section passes."""
    assert checks_ok({}) is True


def test_checks_ok_warning_only_is_true() -> None:
    """Warning rows never fail a section."""
    assert checks_ok({"a": make_warn_entry("v"), "b": make_entry(ok=True)}) is True


def test_checks_ok_false_on_error_row() -> None:
    """Any failing error row fails the section."""
    checks = {"a": make_warn_entry("v"), "b": make_entry(ok=False, error="x")}
    assert checks_ok(checks) is False
