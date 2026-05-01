"""Tests for the `init` CLI subcommand."""

from __future__ import annotations

import argparse
import sys
import tomllib
from pathlib import Path

import pytest

from mcp_tools_sql.cli.commands import init as init_cmd


def _make_args(
    backend: str,
    *,
    output: Path,
    pyproject: bool = False,
) -> argparse.Namespace:
    """Return a Namespace mirroring the parsed CLI args for `init`."""
    return argparse.Namespace(backend=backend, output=output, pyproject=pyproject)


@pytest.fixture(autouse=True)
def redirect_home_and_cwd(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Path:
    """Redirect `Path.home()` and CWD to an isolated tmp directory."""
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.chdir(tmp_path)
    return tmp_path


# ---------------------------------------------------------------------------
# Test (i): generated TOML parses cleanly
# ---------------------------------------------------------------------------


def test_init_generates_valid_toml(tmp_path: Path) -> None:
    """Generated `mcp-tools-sql.toml` parses with tomllib and has the connection key."""
    output = tmp_path / "mcp-tools-sql.toml"
    rc = init_cmd.run(_make_args("sqlite", output=output))
    assert rc == 0

    parsed = tomllib.loads(output.read_text(encoding="utf-8"))
    assert parsed["connection"] == "default"


# ---------------------------------------------------------------------------
# Test (ii): per-backend database config keys
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "backend, expected_keys, forbidden_keys",
    [
        ("sqlite", {"backend", "path"}, {"host", "port"}),
        (
            "mssql",
            {"backend", "host", "port", "database", "username", "driver"},
            {"path"},
        ),
        (
            "postgresql",
            {"backend", "host", "port", "database", "username"},
            {"path", "driver"},
        ),
    ],
)
def test_init_database_config_per_backend(
    redirect_home_and_cwd: Path,
    tmp_path: Path,
    backend: str,
    expected_keys: set[str],
    forbidden_keys: set[str],
) -> None:
    """Database config exposes the right keys per backend."""
    del redirect_home_and_cwd
    output = tmp_path / "mcp-tools-sql.toml"
    rc = init_cmd.run(_make_args(backend, output=output))
    assert rc == 0

    db_config_path = Path.home() / ".mcp-tools-sql" / "config.toml"
    assert db_config_path.exists()
    parsed = tomllib.loads(db_config_path.read_text(encoding="utf-8"))
    default = parsed["connections"]["default"]

    assert default["backend"] == backend
    for key in expected_keys:
        assert key in default, f"missing expected key {key!r} for backend {backend!r}"
    for key in forbidden_keys:
        assert key not in default, f"unexpected key {key!r} for backend {backend!r}"


# ---------------------------------------------------------------------------
# Test (iii): --pyproject happy path
# ---------------------------------------------------------------------------


def test_init_pyproject_happy_path(redirect_home_and_cwd: Path) -> None:
    """`init --pyproject` adds [tool.mcp-tools-sql] to existing pyproject.toml."""
    pyproject = redirect_home_and_cwd / "pyproject.toml"
    pyproject.write_text(
        '[project]\nname = "demo"\nversion = "0.0.1"\n',
        encoding="utf-8",
    )

    rc = init_cmd.run(
        _make_args("sqlite", output=Path("mcp-tools-sql.toml"), pyproject=True),
    )
    assert rc == 0

    content = pyproject.read_text(encoding="utf-8")
    parsed = tomllib.loads(content)
    assert "tool" in parsed
    assert "mcp-tools-sql" in parsed["tool"]
    assert parsed["tool"]["mcp-tools-sql"]["connection"] == "default"
    # original [project] section preserved
    assert parsed["project"]["name"] == "demo"


# ---------------------------------------------------------------------------
# Test (iii.b): pointer comment in inserted block
# ---------------------------------------------------------------------------


def test_init_pyproject_block_contains_pointer_comment(
    redirect_home_and_cwd: Path,
) -> None:
    """Inserted block carries a comment pointing to the standalone template."""
    pyproject = redirect_home_and_cwd / "pyproject.toml"
    pyproject.write_text(
        '[project]\nname = "demo"\nversion = "0.0.1"\n',
        encoding="utf-8",
    )

    rc = init_cmd.run(
        _make_args("sqlite", output=Path("mcp-tools-sql.toml"), pyproject=True),
    )
    assert rc == 0

    content = pyproject.read_text(encoding="utf-8")
    assert "standalone mcp-tools-sql.toml template" in content


# ---------------------------------------------------------------------------
# Test (iv): refuse when [tool.mcp-tools-sql] already exists
# ---------------------------------------------------------------------------


def test_init_pyproject_refuses_when_section_exists(
    redirect_home_and_cwd: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """If [tool.mcp-tools-sql] already exists, exit 1 without modifying file."""
    pyproject = redirect_home_and_cwd / "pyproject.toml"
    original = (
        '[project]\nname = "demo"\nversion = "0.0.1"\n'
        "\n"
        '[tool.mcp-tools-sql]\nconnection = "preexisting"\n'
    )
    pyproject.write_text(original, encoding="utf-8")

    rc = init_cmd.run(
        _make_args("sqlite", output=Path("mcp-tools-sql.toml"), pyproject=True),
    )
    captured = capsys.readouterr()
    assert rc == 1
    assert pyproject.read_text(encoding="utf-8") == original
    assert "already exists" in captured.out


# ---------------------------------------------------------------------------
# Test (v): does not overwrite existing database config
# ---------------------------------------------------------------------------


def test_init_does_not_overwrite_existing_database_config(
    redirect_home_and_cwd: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Existing ~/.mcp-tools-sql/config.toml is left untouched."""
    db_config_path = redirect_home_and_cwd / ".mcp-tools-sql" / "config.toml"
    db_config_path.parent.mkdir(parents=True, exist_ok=True)
    sentinel = '[connections.default]\nbackend = "sqlite"\npath = "/preexisting.db"\n'
    db_config_path.write_text(sentinel, encoding="utf-8")

    rc = init_cmd.run(_make_args("sqlite", output=tmp_path / "mcp-tools-sql.toml"))
    captured = capsys.readouterr()

    assert rc == 0
    assert db_config_path.read_text(encoding="utf-8") == sentinel
    assert "left untouched" in captured.out


# ---------------------------------------------------------------------------
# Test (vi): "default" used in both files
# ---------------------------------------------------------------------------


def test_init_writes_default_in_both_files(
    redirect_home_and_cwd: Path,
    tmp_path: Path,
) -> None:
    """Both written files reference `default` consistently."""
    output = tmp_path / "mcp-tools-sql.toml"
    rc = init_cmd.run(_make_args("sqlite", output=output))
    assert rc == 0

    project_parsed = tomllib.loads(output.read_text(encoding="utf-8"))
    assert project_parsed["connection"] == "default"

    db_config_path = redirect_home_and_cwd / ".mcp-tools-sql" / "config.toml"
    db_parsed = tomllib.loads(db_config_path.read_text(encoding="utf-8"))
    assert "default" in db_parsed["connections"]


# ---------------------------------------------------------------------------
# Refuse-on-existing-output
# ---------------------------------------------------------------------------


def test_init_refuses_when_output_exists(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """If the project output file already exists, exit 1 without overwriting."""
    output = tmp_path / "mcp-tools-sql.toml"
    output.write_text("# pre-existing content\n", encoding="utf-8")

    rc = init_cmd.run(_make_args("sqlite", output=output))
    captured = capsys.readouterr()

    assert rc == 1
    assert output.read_text(encoding="utf-8") == "# pre-existing content\n"
    assert "already exists" in captured.out


# ---------------------------------------------------------------------------
# Refuse-on-missing-pyproject
# ---------------------------------------------------------------------------


def test_init_pyproject_when_no_pyproject(
    redirect_home_and_cwd: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """`--pyproject` with no pyproject.toml in CWD exits 1 with a clear message."""
    del redirect_home_and_cwd
    rc = init_cmd.run(
        _make_args("sqlite", output=Path("mcp-tools-sql.toml"), pyproject=True),
    )
    captured = capsys.readouterr()
    assert rc == 1
    assert "pyproject.toml" in captured.out


# ---------------------------------------------------------------------------
# --output ignored under --pyproject (logger.debug is acceptable)
# ---------------------------------------------------------------------------


def test_init_pyproject_ignores_custom_output_silently(
    redirect_home_and_cwd: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A custom --output under --pyproject does not error and does not warn on stdout."""
    pyproject = redirect_home_and_cwd / "pyproject.toml"
    pyproject.write_text(
        '[project]\nname = "demo"\nversion = "0.0.1"\n',
        encoding="utf-8",
    )

    rc = init_cmd.run(
        _make_args(
            "sqlite",
            output=Path("custom-output.toml"),
            pyproject=True,
        ),
    )
    captured = capsys.readouterr()

    assert rc == 0
    assert "custom-output.toml" not in captured.out
    assert not (redirect_home_and_cwd / "custom-output.toml").exists()


# ---------------------------------------------------------------------------
# Sanity: tomllib is available (we assume Python 3.11+ per pyproject.toml).
# ---------------------------------------------------------------------------


def test_python_supports_tomllib() -> None:
    """Project requires Python 3.11+, so tomllib must be available."""
    assert sys.version_info >= (3, 11)
