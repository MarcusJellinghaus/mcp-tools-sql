"""Import every submodule of a package and report what failed.

Stdlib-only on purpose: it runs as a script in a fresh interpreter
(``python -P tests/_import_walker.py <report.json>``) so that mocks injected
into ``sys.modules`` by test conftests cannot mask a broken import.
"""

from __future__ import annotations

import importlib
import importlib.util
import json
import pkgutil
import sys
from collections.abc import Iterable
from pathlib import Path
from typing import Any

SKIPPED_MODULES: frozenset[str] = frozenset({"mcp_tools_sql.__main__"})


def missing_optional_package(exc: BaseException) -> str | None:
    """Return the absent top-level package name if *exc* stems from a missing
    optional extra, else None (= real failure).

    Follows the ``__cause__``/``__context__`` chain to the first
    ``ModuleNotFoundError``; it counts as a missing extra only when its
    top-level package cannot be found at all.
    """
    seen: set[int] = set()
    cur: BaseException | None = exc
    while cur is not None and id(cur) not in seen:
        seen.add(id(cur))
        if isinstance(cur, ModuleNotFoundError):
            top = (cur.name or "").split(".")[0]
            if top and importlib.util.find_spec(top) is None:
                return top
            return None
        cur = cur.__cause__ or cur.__context__
    return None


def walk(package_name: str) -> dict[str, Any]:
    """Import *package_name* and all its submodules; return the report dict.

    A failure importing the root package is not caught — the crash is the
    signal. A failing subpackage is reported once and its subtree skipped.
    """
    pkg = importlib.import_module(package_name)
    failures: list[dict[str, str]] = []
    skips: list[dict[str, str]] = []

    def visit(path: Iterable[str], prefix: str) -> None:
        for info in pkgutil.iter_modules(path, prefix):
            if info.name in SKIPPED_MODULES:
                continue
            try:
                mod = importlib.import_module(info.name)
            except KeyboardInterrupt:
                raise
            except BaseException as exc:  # pylint: disable=broad-exception-caught
                missing = missing_optional_package(exc)
                if missing:
                    skips.append(
                        {"module": info.name, "missing": missing, "message": str(exc)}
                    )
                else:
                    failures.append(
                        {
                            "module": info.name,
                            "type": type(exc).__name__,
                            "message": str(exc),
                        }
                    )
                continue
            if info.ispkg:
                visit(mod.__path__, info.name + ".")

    visit(pkg.__path__, package_name + ".")
    return {
        "package_path": list(pkg.__path__),
        "failures": failures,
        "skips": skips,
    }


def main(argv: list[str]) -> None:
    """argv[1] = report path; write json.dumps(walk("mcp_tools_sql"))."""
    Path(argv[1]).write_text(json.dumps(walk("mcp_tools_sql")), encoding="utf-8")


if __name__ == "__main__":
    main(sys.argv)
