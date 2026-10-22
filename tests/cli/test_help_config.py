"""Tests for `help config`, the top-level epilog, and config hints."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from pydantic import BaseModel

from mcp_tools_sql.cli.commands.help_config import CONFIG_GUIDE
from mcp_tools_sql.config.models import (
    BackendQueryConfig,
    ConnectionConfig,
    QueryConfig,
    QueryFileConfig,
    QueryParamConfig,
    SecurityConfig,
    UpdateConfig,
    UpdateFieldConfig,
    UpdateKeyConfig,
)
from mcp_tools_sql.main import main

# Every user-authored config model; `name` on QueryParamConfig is the TOML key.
_AUTHORED_MODELS: list[type[BaseModel]] = [
    ConnectionConfig,
    SecurityConfig,
    QueryFileConfig,
    QueryConfig,
    QueryParamConfig,
    BackendQueryConfig,
    UpdateConfig,
    UpdateKeyConfig,
    UpdateFieldConfig,
]


def test_help_config_prints_guide(capsys: pytest.CaptureFixture[str]) -> None:
    """`mcp-tools-sql help config` prints the guide and exits 0."""
    rc = main(["help", "config"])

    assert rc == 0
    assert capsys.readouterr().out == CONFIG_GUIDE


@pytest.mark.parametrize("model", _AUTHORED_MODELS, ids=lambda m: m.__name__)
def test_guide_names_every_config_key(model: type[BaseModel]) -> None:
    """Each authored config key appears in the guide (drift guard)."""
    keys = [field.alias or name for name, field in model.model_fields.items()]
    missing = [k for k in keys if not re.search(rf"\b{re.escape(k)}\b", CONFIG_GUIDE)]

    assert not missing, f"keys missing from CONFIG_GUIDE: {missing}"


def test_unknown_help_topic_exits_2() -> None:
    """An unknown help topic is an argparse error."""
    with pytest.raises(SystemExit) as exc_info:
        main(["help", "bogus"])

    assert exc_info.value.code == 2


def test_top_level_help_points_at_setup_commands(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The top-level help lists the getting-started commands."""
    main(["--help"])
    out = capsys.readouterr().out

    assert "help config" in out
    assert "verify" in out


def test_tool_without_config_points_at_help_config(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """`tool` with no discoverable config exits 1 and names `help config`."""
    monkeypatch.chdir(tmp_path)

    rc = main(["--database-config", str(tmp_path / "db.toml"), "tool"])

    assert rc == 1
    assert "mcp-tools-sql help config" in capsys.readouterr().err
