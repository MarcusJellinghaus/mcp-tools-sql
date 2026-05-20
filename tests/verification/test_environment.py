"""Tests for `verify_environment`."""

from __future__ import annotations

import sys

from mcp_tools_sql.verification import verify_environment


def test_verify_environment_returns_python_version() -> None:
    """`python_version` entry is OK and matches the running interpreter."""
    result = verify_environment()

    assert result["python_version"]["ok"] is True
    expected = (
        f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    )
    assert result["python_version"]["value"] == expected


def test_verify_environment_overall_ok_true_when_packages_present() -> None:
    """`mcp_tools_sql` and `mcp_coder_utils` resolve in the test environment."""
    result = verify_environment()

    assert result["mcp_tools_sql"]["ok"] is True
    assert result["mcp_coder_utils"]["ok"] is True
    assert result["overall_ok"] is True
