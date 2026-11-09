"""Tests for `verify_environment`."""

from __future__ import annotations

import platform
import sys

from mcp_tools_sql.verification import verify_environment
from mcp_tools_sql.verification._helpers import checks_ok


def test_verify_environment_returns_python_version() -> None:
    """`python_version` entry is OK and matches the running interpreter."""
    result = verify_environment()

    assert result["python_version"]["ok"] is True
    expected = (
        f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    )
    assert result["python_version"]["value"] == expected


def test_verify_environment_returns_os() -> None:
    """`os` entry shows platform.system() and sys.platform."""
    result = verify_environment()

    assert result["os"]["ok"] is True
    assert platform.system() in result["os"]["value"]
    assert sys.platform in result["os"]["value"]


def test_verify_environment_checks_ok_when_packages_present() -> None:
    """`mcp_tools_sql` and `mcp_coder_utils` resolve in the test environment."""
    result = verify_environment()

    assert result["mcp_tools_sql"]["ok"] is True
    assert result["mcp_coder_utils"]["ok"] is True
    assert checks_ok(result) is True
