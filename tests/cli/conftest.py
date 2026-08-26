"""Shared fixtures for the CLI tests."""

from __future__ import annotations

from typing import Any

import pytest


@pytest.fixture(autouse=True)
def no_op_setup_logging(monkeypatch: pytest.MonkeyPatch) -> None:
    """Neutralise real logging setup for every test under tests/cli/.

    `main()` calls `setup_logging` before dispatch, and the upstream
    implementation reconfigures structlog unconditionally (the old pytest
    special-casing was removed upstream). Several tests in
    `test_main_dispatch.py` take that path. Tests that need to observe the
    call monkeypatch it again themselves, which takes precedence.
    """

    def _no_op(*_args: Any, **_kwargs: Any) -> None:
        return None

    monkeypatch.setattr("mcp_tools_sql.main.setup_logging", _no_op)
