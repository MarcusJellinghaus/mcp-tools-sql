"""Unit tests for tools/ci_coverage_summary.py.

Covers top-level package bucketing, Cobertura XML parsing, step-summary
rendering, and the CLI entry point.
"""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path
from types import ModuleType

import pytest

_TOOL_PY = Path(__file__).resolve().parents[2] / "tools" / "ci_coverage_summary.py"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("ci_coverage_summary", _TOOL_PY)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ci_coverage_summary = _load()


def _coverage_xml(packages_xml: str) -> str:
    return (
        '<?xml version="1.0" ?>\n'
        '<coverage version="7.16.2" lines-valid="0" lines-covered="0">\n'
        "  <packages>\n"
        f"{packages_xml}"
        "  </packages>\n"
        "</coverage>\n"
    )


@pytest.mark.parametrize(
    "full_name, expected",
    [
        ("utils.data_type_utility", "utils"),
        (".", "mcp_tools_sql"),
        ("cli", "cli"),
    ],
)
def test_top_level_package_name(full_name: str, expected: str) -> None:
    assert ci_coverage_summary.top_level_package_name(full_name) == expected


def test_parse_coverage_xml_aggregates_by_top_level(tmp_path: Path) -> None:
    xml = _coverage_xml("""\
    <package name="utils.data_type_utility">
      <classes>
        <class name="type_mapping.py" filename="utils/data_type_utility/type_mapping.py">
          <lines>
            <line number="1" hits="1"/>
            <line number="2" hits="0"/>
          </lines>
        </class>
      </classes>
    </package>
    <package name="utils">
      <classes>
        <class name="sql_placeholders.py" filename="utils/sql_placeholders.py">
          <lines>
            <line number="1" hits="1"/>
            <line number="2" hits="1"/>
          </lines>
        </class>
      </classes>
    </package>
    <package name=".">
      <classes>
        <class name="main.py" filename="main.py">
          <lines>
            <line number="1" hits="1"/>
          </lines>
        </class>
      </classes>
    </package>
""")
    xml_path = tmp_path / "coverage.xml"
    xml_path.write_text(xml, encoding="utf-8")

    summary = ci_coverage_summary.parse_coverage_xml(xml_path)

    assert summary.lines_valid == 5
    assert summary.lines_covered == 4
    rollups = {p.name: p for p in summary.packages}
    assert set(rollups) == {"utils", "mcp_tools_sql"}
    assert rollups["utils"].lines_valid == 4
    assert rollups["utils"].lines_covered == 3
    assert rollups["mcp_tools_sql"].lines_valid == 1
    assert rollups["mcp_tools_sql"].lines_covered == 1


def test_render_step_summary_includes_caveat_and_table() -> None:
    summary = ci_coverage_summary.CoverageSummary(
        lines_valid=10,
        lines_covered=8,
        packages=[
            ci_coverage_summary.PackageRollup(
                name="backends", lines_valid=6, lines_covered=5
            ),
            ci_coverage_summary.PackageRollup(
                name="cli", lines_valid=4, lines_covered=3
            ),
        ],
    )
    rendered = ci_coverage_summary.render_step_summary(summary, diff_report=None)

    assert "## Coverage: 80%" in rendered
    assert ci_coverage_summary.INTEGRATION_COVERAGE_CAVEAT in rendered
    assert "continue-on-error" in rendered
    assert "postgresql_integration" in rendered
    assert "<details>" in rendered
    assert "Per-package breakdown" in rendered
    assert "backends" in rendered
    assert "cli" in rendered


def test_render_step_summary_omits_diff_section_when_none() -> None:
    summary = ci_coverage_summary.CoverageSummary(
        lines_valid=1, lines_covered=1, packages=[]
    )
    rendered = ci_coverage_summary.render_step_summary(summary, diff_report=None)

    assert "Diff coverage" not in rendered


def test_render_step_summary_includes_diff_report() -> None:
    summary = ci_coverage_summary.CoverageSummary(
        lines_valid=1, lines_covered=1, packages=[]
    )
    rendered = ci_coverage_summary.render_step_summary(
        summary, diff_report="| file | % |\n| --- | --- |\n| a.py | 100% |"
    )

    assert "Diff coverage" in rendered
    assert "advisory, not a gate" in rendered
    assert "| a.py | 100% |" in rendered


def test_main_writes_markdown_to_output_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    xml_path = tmp_path / "coverage.xml"
    xml_path.write_text(
        _coverage_xml("""\
    <package name=".">
      <classes>
        <class name="__init__.py" filename="__init__.py">
          <lines>
            <line number="1" hits="1"/>
          </lines>
        </class>
      </classes>
    </package>
"""),
        encoding="utf-8",
    )
    output_path = tmp_path / "summary.md"

    exit_code = ci_coverage_summary.main(
        [
            "--coverage-xml",
            str(xml_path),
            "--output",
            str(output_path),
        ]
    )

    assert exit_code == 0
    content = output_path.read_text(encoding="utf-8")
    assert "## Coverage: 100%" in content


def test_main_appends_to_github_step_summary_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    xml_path = tmp_path / "coverage.xml"
    xml_path.write_text(
        _coverage_xml("""\
    <package name=".">
      <classes>
        <class name="__init__.py" filename="__init__.py">
          <lines>
            <line number="1" hits="1"/>
          </lines>
        </class>
      </classes>
    </package>
"""),
        encoding="utf-8",
    )
    step_summary_path = tmp_path / "step_summary.md"
    step_summary_path.write_text("existing content\n", encoding="utf-8")
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(step_summary_path))

    exit_code = ci_coverage_summary.main(["--coverage-xml", str(xml_path)])

    assert exit_code == 0
    content = step_summary_path.read_text(encoding="utf-8")
    assert content.startswith("existing content\n")
    assert "## Coverage: 100%" in content
    assert os.environ["GITHUB_STEP_SUMMARY"] == str(step_summary_path)
