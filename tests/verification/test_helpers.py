"""Smoke tests for verification helpers."""

from __future__ import annotations

from mcp_tools_sql.verification._helpers import VerifierEntry, make_entry


def test_make_entry_ok_defaults() -> None:
    """`make_entry(ok=True)` returns a dict with empty string defaults."""
    result = make_entry(ok=True)
    assert result == {"ok": True, "value": "", "error": "", "install_hint": ""}


def test_make_entry_all_fields() -> None:
    """`make_entry(...)` with all fields returns the expected dict."""
    result = make_entry(ok=False, value="x", error="e", install_hint="h")
    assert result == {"ok": False, "value": "x", "error": "e", "install_hint": "h"}


def test_verifier_entry_is_typed_dict() -> None:
    """`VerifierEntry` is a TypedDict with the four expected keys."""
    assert set(VerifierEntry.__annotations__.keys()) == {
        "ok",
        "value",
        "error",
        "install_hint",
    }
