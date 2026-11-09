"""Tests for the tool_spec shim over mcp-coder-utils."""

from typing import Annotated

import mcp_coder_utils.tool_spec as upstream
import pytest
from pydantic import Field

from mcp_tools_sql.utils import tool_spec as shim


@pytest.mark.parametrize("name", ["ToolSpec", "tool_spec", "ToolSink", "ToolCollector"])
def test_shim_reexports_upstream_objects(name: str) -> None:
    assert getattr(shim, name) is getattr(upstream, name)
    assert name in shim.__all__


async def _sample(limit: Annotated[int, Field(ge=1)]) -> str:
    """Return a sample."""
    return str(limit)


def test_tool_spec_builds_spec() -> None:
    spec = shim.tool_spec(_sample, group="sql.query", read_only=True, name="sample")

    assert spec.name == "sample"
    assert spec.group == "sql.query"
    assert spec.read_only is True
    assert spec.description == "Return a sample."
    assert spec.args_model.model_validate({"limit": 1}).limit == 1  # type: ignore[attr-defined]


def test_collector_rejects_duplicate_name() -> None:
    collector = shim.ToolCollector()
    spec = shim.tool_spec(_sample, group="sql.query", read_only=True, name="sample")
    collector.add(spec)

    with pytest.raises(ValueError, match="duplicate"):
        collector.add(spec)
