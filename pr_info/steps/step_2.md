# Step 2 — Coverage summary script + ported tests

## LLM prompt
> Read `pr_info/steps/summary.md`, then implement **only** `pr_info/steps/step_2.md`.
> Follow TDD: port the tests first (they fail because the script is missing),
> then add the script so they pass. Make the small `pyproject.toml` /
> `.gitignore` changes, run all checks, then format and make exactly one commit.
> Do not touch `ci.yml` (that is step 3).

## WHERE
- `tests/tools/__init__.py` (new, empty, like every other `tests/*` package)
- `tests/tools/test_ci_coverage_summary.py` (new; ported from mcp_coder `main`)
- `tools/ci_coverage_summary.py` (new; copied from mcp_coder `main`)
- `pyproject.toml`
- `.gitignore`

## WHAT

### 2a — tests first: `tests/tools/test_ci_coverage_summary.py`
Port mcp_coder's `tests/tools/test_ci_coverage_summary.py` as is. It loads the
script with `importlib.util.spec_from_file_location` from
`Path(__file__).resolve().parents[2] / "tools" / "ci_coverage_summary.py"`.
Make **only** these adaptations, and keep the fixture data unchanged so the file
can still be diffed against the blueprint:
- `test_top_level_package_name` parametrize: `(".", "mcp_coder")` → `(".", "mcp_tools_sql")`.
- `test_parse_coverage_xml_aggregates_by_top_level`: the root bucket key changes
  from `"mcp_coder"` to `"mcp_tools_sql"` (in `set(rollups) == {"llm", "mcp_tools_sql"}`
  and in both `rollups["mcp_tools_sql"]` asserts).
- `test_render_step_summary_includes_caveat_and_table`: keep
  `assert ci_coverage_summary.MARKER_TRAP_CAVEAT in rendered` and add
  `assert "continue-on-error" in rendered` and
  `assert "postgresql_integration" in rendered`, which pins the repo-specific text.

Test functions (unchanged names/signatures):
```python
def test_top_level_package_name(full_name: str, expected: str) -> None
def test_parse_coverage_xml_aggregates_by_top_level(tmp_path: Path) -> None
def test_render_step_summary_includes_caveat_and_table() -> None
def test_render_step_summary_omits_diff_section_when_none() -> None
def test_render_step_summary_includes_diff_report() -> None
def test_main_writes_markdown_to_output_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None
def test_main_appends_to_github_step_summary_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None
```
Run `run_pytest_check` with `extra_args: ["-p", "no:cacheprovider", "tests/tools"]`.
Expected: collection error / failures, because the script doesn't exist yet.

### 2b — implementation: `tools/ci_coverage_summary.py`
Copy mcp_coder `main`'s `tools/ci_coverage_summary.py` as is (stdlib only, keep
the `# noqa: S314` on `ET.parse`). Public surface (unchanged):
```python
MARKER_TRAP_CAVEAT: str

@dataclass
class PackageRollup:
    name: str; lines_valid: int; lines_covered: int
    @property
    def rate(self) -> float

@dataclass
class CoverageSummary:
    lines_valid: int; lines_covered: int; packages: list[PackageRollup]
    @property
    def rate(self) -> float

def top_level_package_name(full_name: str) -> str
def parse_coverage_xml(xml_path: Path) -> CoverageSummary
def render_step_summary(summary: CoverageSummary, diff_report: str | None) -> str
def main(argv: list[str] | None = None) -> int
```
Adaptations (only these):
1. `top_level_package_name`: `if full_name == ".": return "mcp_tools_sql"`.
2. `top_level_package_name` docstring: rewrite the examples for this repo:
   ```
   ``coverage xml`` for ``--cov=src/mcp_tools_sql`` reports package names
   relative to that measured root, dropping the ``mcp_tools_sql`` prefix:
   ``backends.mssql`` -> ``backends``, ``cli.commands`` -> ``cli``. The root
   package itself (loose top-level modules like ``main.py``) is reported as
   ``.``, which buckets into the readable ``mcp_tools_sql`` row.
   ```
   Before writing the example names, check them against the real
   `src/mcp_tools_sql/` layout (`mcp__mcp-workspace__list_directory`) and use
   subpackages/modules that actually exist.
3. `MARKER_TRAP_CAVEAT` keeps its name (the blueprint and tests reference it).
   Its value becomes:
   ```python
   MARKER_TRAP_CAVEAT = (
       "_The `mssql-integration` job is `continue-on-error`, so a failed run "
       "leaves the mssql backend uncovered. No test carries "
       "`postgresql_integration` yet, so that job contributes no data._"
   )
   ```

### `pyproject.toml`
- `dev` extra: add `"pytest-cov",` and `"diff-cover",`.
- `[tool.ruff.lint.per-file-ignores]`: add, with a short comment:
  ```toml
  # tools: standalone CI scripts copied from mcp_coder; Returns sections not required.
  "tools/**" = ["DOC201"]
  ```

### `.gitignore`
Add a block:
```
# Coverage artefacts
.coverage
.coverage.*
coverage.xml
htmlcov/
```

## HOW
- The test imports the script by file path (not as a package), so `tools/` needs
  no `__init__.py`, and no `sys.path` or mypy config changes are needed.
- `tests/**/*.py` per-file-ignores already cover the test file's D/DOC/S101 rules.
- The CI jobs `ruff`, `black` and `isort` already scan `tools/`; `pylint`, `mypy`
  and `vulture` scan `tests/`.

## ALGORITHM (`parse_coverage_xml`, unchanged from blueprint)
```
root = parse xml
for each <package>: bucket = top_level_package_name(name)
    for each class/lines/line: bucket.valid += 1, total.valid += 1
        if hits != "0": bucket.covered += 1, total.covered += 1
return CoverageSummary(totals, packages sorted by name)
```

## DATA
- `render_step_summary` → Markdown string: `## Coverage: NN%`, the caveat, a
  `<details>` per-package table, and an optional "Diff coverage (advisory, not a
  gate)" section.
- `main` → `0` always. It appends to `--output`, else `$GITHUB_STEP_SUMMARY`,
  else writes to stdout.

## Verification
1. Run `run_pytest_check` with `extra_args: ["-n", "auto"]`. All tests must pass,
   including `tests/tools`.
2. Run `run_ruff_check` with `target_directories: ["src", "tests", "tools"]`.
   It must be clean.
3. Run `run_pylint_check` and `run_mypy_check`; both must pass.
4. Run `run_format_code` with `target_directories: ["src", "tests", "tools"]`,
   and `run_format_code` with `check_only: true` on the same directories.
   Both must be clean.
5. Commit: `feat(tools): add CI coverage summary script`.
