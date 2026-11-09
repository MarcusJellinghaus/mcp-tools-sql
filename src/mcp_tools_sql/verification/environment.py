"""Environment section: Python version, virtualenv, key package versions."""

from __future__ import annotations

import importlib.metadata
import platform
import sys

from mcp_tools_sql.verification._helpers import CheckResult, make_entry


def verify_environment() -> dict[str, CheckResult]:
    """Report Python version, virtualenv status, and key package versions.

    Returns:
        Verifier rows for ``python_version``, ``os``, ``virtualenv``,
        ``mcp_tools_sql`` and ``mcp_coder_utils``.
    """
    result: dict[str, CheckResult] = {}

    py_version = (
        f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    )
    result["python_version"] = make_entry(ok=True, value=py_version)

    result["os"] = make_entry(
        ok=True,
        value=f"{platform.system()} ({sys.platform})",
    )

    in_venv = sys.prefix != sys.base_prefix
    result["virtualenv"] = make_entry(
        ok=True,
        value=sys.prefix if in_venv else "(not in a virtual environment)",
    )

    for pkg, hint in (
        ("mcp_tools_sql", ""),
        (
            "mcp_coder_utils",
            "pip install mcp-coder-utils",
        ),
    ):
        try:
            ver = importlib.metadata.version(pkg)
            result[pkg] = make_entry(ok=True, value=ver)
        except importlib.metadata.PackageNotFoundError:
            result[pkg] = make_entry(
                ok=False,
                value="(not installed)",
                error=f"package {pkg!r} not found",
                install_hint=hint,
            )

    return result
