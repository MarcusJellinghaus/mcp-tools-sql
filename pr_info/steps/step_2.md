# Step 2 — `no-url-deps` script + `test` matrix entry

See `pr_info/steps/summary.md` (item 2). One commit.

## WHERE
- Create `tools/check_no_url_deps.py`
- Modify `.github/workflows/ci.yml` → `test` job `matrix.check`

## WHAT
Port `mcp_coder`'s script **verbatim** (stdlib only — `tomllib`). Signature:

```python
def main() -> int: ...   # returns 1 if any direct URL dep found, else 0
```

Full content to create (do not rewrite or shrink — byte-identical to the peer group):

```python
"""Fail if pyproject.toml [project] dependencies contain direct URL specs.

Direct URL dependencies (e.g. ``pkg @ git+https://...``) are not allowed in
``[project].dependencies`` or ``[project.optional-dependencies]``. PyPI and
``twine check`` reject sdists/wheels that include them, and they make the
project install non-portable.

Use ``[tool.mcp-coder.install-from-github]`` for pre-installing GitHub
sources via ``tools/reinstall_local.bat`` and the CI install step instead.
"""

import sys
import tomllib
from pathlib import Path


def main() -> int:
    """Return 1 if any direct URL dependency is found, else 0."""
    project_dir = Path(__file__).resolve().parent.parent
    path = project_dir / "pyproject.toml"

    with open(path, "rb") as f:
        data = tomllib.load(f)

    project = data.get("project", {})
    sources: list[tuple[str, str]] = []
    for dep in project.get("dependencies", []):
        sources.append(("dependencies", dep))
    for group, items in project.get("optional-dependencies", {}).items():
        for dep in items:
            sources.append((f"optional-dependencies.{group}", dep))

    bad = [
        (loc, dep)
        for loc, dep in sources
        if "git+" in dep or " @ http" in dep or " @ file" in dep
    ]

    if bad:
        print("ERROR: direct URL dependencies are not allowed:")
        for loc, dep in bad:
            print(f"  [{loc}] {dep}")
        print()
        print("Use [tool.mcp-coder.install-from-github] for git installs.")
        return 1

    print("OK: no direct URL dependencies in [project]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

## HOW
Add this matrix entry to the **`test`** job's `matrix.check` list (after `mypy`):

```yaml
          - {name: "no-url-deps", cmd: "python tools/check_no_url_deps.py"}
```

## ALGORITHM
1. Load `pyproject.toml` with `tomllib`.
2. Collect `[project].dependencies` + every `optional-dependencies.<group>` entry.
3. Flag any spec containing `git+`, ` @ http`, or ` @ file`.
4. Print offenders and `return 1`; else print OK and `return 0`.

## DATA
- `sources: list[tuple[str, str]]` — `(location, dep-spec)`.
- Exit code `0` (clean) / `1` (violation).

## Verification (the "test" for this step)
- `python tools/check_no_url_deps.py` prints `OK: no direct URL dependencies in
  [project]` and exits `0` (this repo's `[project]` has no URL specs today).
- Standard pylint/pytest/mypy via MCP tools — green. (mypy must accept the script:
  it is under `tools/`, which is in mypy's check path only if configured; CI runs
  `mypy --strict src tests`, so `tools/` is not type-checked — no concern.)

## LLM prompt
> Read `pr_info/steps/summary.md` and `pr_info/steps/step_2.md`. Create
> `tools/check_no_url_deps.py` with the exact verbatim content shown (do not modify
> it). Add the `no-url-deps` matrix entry to the `test` job in
> `.github/workflows/ci.yml`. Run `python tools/check_no_url_deps.py` and confirm it
> exits 0 with the OK message. Run the standard MCP quality checks. Commit as one
> change.
