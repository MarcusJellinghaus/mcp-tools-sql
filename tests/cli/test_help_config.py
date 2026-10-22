"""Tests for `help config`, the top-level epilog, and config hints."""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

import pytest
from pydantic import BaseModel

from mcp_tools_sql.cli.commands.help_config import (
    CONFIG_GUIDE,
    DATABASE_CONFIG_EXAMPLE,
    QUERY_CONFIG_EXAMPLE,
)
from mcp_tools_sql.config.models import (
    BackendQueryConfig,
    ConnectionConfig,
    DatabaseConfig,
    DatabaseSpec,
    QueryConfig,
    QueryFileConfig,
    QueryParamConfig,
    SecurityConfig,
    UpdateConfig,
    UpdateFieldConfig,
    UpdateKeyConfig,
)
from mcp_tools_sql.main import main

# Model fields users never write as keys.
_NOT_AUTHORED: dict[type[BaseModel], set[str]] = {
    # Derived from the [queries.<name>.params.<param>] table key.
    QueryParamConfig: {"name"},
    # The `databases` table key or list entry.
    DatabaseSpec: {"name"},
}

# Every config model whose fields are authored in a TOML file.
_AUTHORED_MODELS: list[type[BaseModel]] = [
    ConnectionConfig,
    DatabaseSpec,
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


# An indented key list: `key`, `key, key`, `key (default "int"), key,` ...
# followed by two or more spaces (start of the description) or end of line.
_KEY = r"[a-z_]+(?: \([^)\n]*\))?"
_KEY_LINE = re.compile(rf"^ {{2,}}({_KEY}(?:, {_KEY})*,?)(?: {{2,}}|$)", re.MULTILINE)
# A table header: `[a.<name>.b]` or `[[a.<name>.b]]`.
_HEADER_LINE = re.compile(r"^ *\[\[?([a-z_.<>]+)\]\]?", re.MULTILINE)


def _indent(example: str) -> str:
    """Return *example* as the guide embeds it: indented by two spaces."""
    return "".join(
        f"  {line}" if line.strip() else line
        for line in example.splitlines(keepends=True)
    )


def _reference_text(guide: str) -> str:
    """Return *guide* without the embedded examples.

    Example table headers would otherwise mask a removed reference line.
    """
    for example in (DATABASE_CONFIG_EXAMPLE, QUERY_CONFIG_EXAMPLE):
        indented = _indent(example)
        assert indented in guide
        guide = guide.replace(indented, "")
    return guide


def _listed_keys(guide: str) -> set[str]:
    """Return the keys the guide lists, in key lists or table headers."""
    keys: set[str] = set()
    for match in _KEY_LINE.finditer(guide):
        for item in match.group(1).split(","):
            key = item.split(" (", 1)[0].strip()
            if key:
                keys.add(key)
    for match in _HEADER_LINE.finditer(guide):
        keys.update(p for p in match.group(1).split(".") if not p.startswith("<"))
    return keys


@pytest.mark.parametrize("model", _AUTHORED_MODELS, ids=lambda m: m.__name__)
def test_guide_names_every_config_key(model: type[BaseModel]) -> None:
    """Each authored config key is listed as a key in the guide (drift guard)."""
    skip = _NOT_AUTHORED.get(model, set())
    keys = [
        field.alias or name
        for name, field in model.model_fields.items()
        if name not in skip
    ]
    listed = _listed_keys(_reference_text(CONFIG_GUIDE))
    missing = [k for k in keys if k not in listed]

    assert not missing, f"keys missing from CONFIG_GUIDE: {missing}"


def test_guide_examples_load() -> None:
    """Both guide examples parse as TOML and validate against the models."""
    DatabaseConfig.model_validate(tomllib.loads(DATABASE_CONFIG_EXAMPLE))
    QueryFileConfig.model_validate(tomllib.loads(QUERY_CONFIG_EXAMPLE))


def test_guide_embeds_examples_indented() -> None:
    """Each example appears in the guide indented by two spaces."""
    for example in (DATABASE_CONFIG_EXAMPLE, QUERY_CONFIG_EXAMPLE):
        assert _indent(example) in CONFIG_GUIDE


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
