"""Tests for the user app data directory shim."""

from __future__ import annotations

from pathlib import Path

import pytest

from mcp_tools_sql.utils.user_app_data import get_user_app_data_dir


def test_get_user_app_data_dir_resolves_home_at_call_time(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Home directory is read on each call, so monkeypatching it works."""
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    assert get_user_app_data_dir("mcp-tools-sql") == tmp_path / ".mcp-tools-sql"
