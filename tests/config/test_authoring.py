"""Tests for the config authoring builders."""

from __future__ import annotations

import tomllib
from typing import Any

import pytest
import tomlkit
from pydantic import ValidationError

from mcp_tools_sql.config.authoring import (
    add_query,
    add_update,
    build_query_config,
    build_update_config,
    list_configured_tools,
    remove_query,
    remove_update,
)
from mcp_tools_sql.config.models import QueryConfig, UpdateConfig


class TestBuildQueryConfig:
    """Tests for build_query_config."""

    def test_auto_fills_param_name_from_dict_key(self) -> None:
        """Dict key for params auto-populates the param's name field."""
        cfg = build_query_config(
            "get_user",
            sql="SELECT * FROM users WHERE id = :id",
            params={"id": {"type": "int"}},
        )
        assert cfg.params["id"].name == "id"

    def test_dict_key_overrides_inner_name(self) -> None:
        """Dict key wins over mismatched inner 'name' silently."""
        cfg = build_query_config(
            "get_user",
            sql="SELECT * FROM users WHERE id = :id",
            params={"id": {"name": "other", "type": "int"}},
        )
        assert cfg.params["id"].name == "id"

    def test_invalid_sql_raises_validation_error(self) -> None:
        """Pydantic ValidationError propagates (sql=None violates model)."""
        with pytest.raises(ValidationError):
            build_query_config("broken", sql=None)  # type: ignore[arg-type]


class TestBuildUpdateConfig:
    """Tests for build_update_config."""

    def test_happy_path_schema_alias(self) -> None:
        """schema= kwarg lands on schema_name via the alias path."""
        ucfg = build_update_config(
            "set_user_email",
            schema="dbo",
            table="users",
            key={"field": "id", "type": "int"},
            fields=[{"field": "email", "type": "str"}],
        )
        assert ucfg.schema_name == "dbo"
        assert ucfg.table == "users"
        assert ucfg.key is not None
        assert ucfg.key.field == "id"
        assert [f.field for f in ucfg.fields] == ["email"]

    def test_invalid_key_raises_validation_error(self) -> None:
        """key dict missing required 'field' propagates pydantic ValidationError."""
        with pytest.raises(ValidationError):
            build_update_config(
                "broken",
                table="users",
                key={"type": "int"},
                fields=[{"field": "email"}],
            )


def _roundtrip(doc: tomlkit.TOMLDocument) -> dict[str, Any]:
    """Render the doc to TOML and parse back through tomllib."""
    return tomllib.loads(tomlkit.dumps(doc))


class TestAddQuery:
    """Tests for add_query."""

    def test_happy_path_roundtrip(self) -> None:
        """Build, add, dump, reparse — QueryConfig equality preserved."""
        qcfg = build_query_config(
            "get_user",
            description="Find user by id",
            sql="SELECT * FROM users WHERE id = :id",
            params={"id": {"type": "int", "required": True}},
            max_rows_default=50,
        )
        doc = tomlkit.document()
        add_query(doc, "get_user", qcfg)
        parsed = _roundtrip(doc)
        reconstructed = QueryConfig.model_validate(parsed["queries"]["get_user"])
        assert reconstructed == qcfg

    def test_scalars_before_subtables(self) -> None:
        """Scalar keys must be emitted BEFORE sub-table headers."""
        qcfg = build_query_config(
            "get_user",
            sql="SELECT * FROM users WHERE id = :id",
            params={"id": {"type": "int", "required": True}},
            max_rows_default=1,
        )
        doc = tomlkit.document()
        add_query(doc, "get_user", qcfg)
        dumped = tomlkit.dumps(doc)
        assert dumped.index("max_rows_default") < dumped.index(
            "[queries.get_user.params"
        )

    def test_lean_output_suppresses_defaults(self) -> None:
        """Default-valued fields are omitted when include_defaults=False."""
        qcfg = build_query_config(
            "minimal",
            sql="SELECT 1",
        )
        doc = tomlkit.document()
        add_query(doc, "minimal", qcfg)
        dumped = tomlkit.dumps(doc)
        assert "max_rows_hard" not in dumped
        assert "filter_column" not in dumped
        assert "backends" not in dumped
        assert "description" not in dumped

    def test_include_defaults_emits_all(self) -> None:
        """include_defaults=True emits every default-valued field."""
        qcfg = build_query_config(
            "minimal",
            sql="SELECT 1",
        )
        doc = tomlkit.document()
        add_query(doc, "minimal", qcfg, include_defaults=True)
        dumped = tomlkit.dumps(doc)
        assert "max_rows_hard" in dumped
        assert "filter_column" in dumped
        assert "backends" in dumped
        assert "description" in dumped

    @pytest.mark.parametrize(
        "params,expected_subtables",
        [
            ({}, 0),
            ({"id": {"type": "int"}}, 1),
            (
                {
                    "a": {"type": "int"},
                    "b": {"type": "str"},
                    "c": {"type": "float"},
                },
                3,
            ),
        ],
    )
    def test_params_count_variants(
        self, params: dict[str, dict[str, Any]], expected_subtables: int
    ) -> None:
        """Zero, one, and multiple params produce correct sub-table count."""
        qcfg = build_query_config(
            "q",
            sql="SELECT 1",
            params=params,
        )
        doc = tomlkit.document()
        add_query(doc, "q", qcfg)
        dumped = tomlkit.dumps(doc)
        if expected_subtables == 0:
            assert "params" not in dumped
        else:
            assert dumped.count("[queries.q.params.") == expected_subtables
            for key in params:
                assert f"[queries.q.params.{key}]" in dumped

    def test_duplicate_name_raises(self) -> None:
        """Adding a query under an existing name raises ValueError."""
        qcfg = build_query_config("dup", sql="SELECT 1")
        doc = tomlkit.document()
        add_query(doc, "dup", qcfg)
        with pytest.raises(ValueError):
            add_query(doc, "dup", qcfg)

    def test_creates_queries_section_when_absent(self) -> None:
        """Empty doc gains a [queries] table on first add."""
        qcfg = build_query_config("q", sql="SELECT 1")
        doc = tomlkit.document()
        assert "queries" not in doc
        add_query(doc, "q", qcfg)
        assert "queries" in doc


class TestAddUpdate:
    """Tests for add_update."""

    def test_happy_path_roundtrip(self) -> None:
        """Build, add, dump, reparse — UpdateConfig equality preserved.

        Asserts AoT structure: parsed `fields` is list[dict], not inline.
        """
        ucfg = build_update_config(
            "set_user_email",
            schema="dbo",
            table="users",
            key={"field": "id", "type": "int"},
            fields=[
                {"field": "email", "type": "str"},
                {"field": "is_active", "type": "bool"},
            ],
        )
        doc = tomlkit.document()
        add_update(doc, "set_user_email", ucfg)
        parsed = _roundtrip(doc)
        fields_parsed = parsed["updates"]["set_user_email"]["fields"]
        assert isinstance(fields_parsed, list)
        assert all(isinstance(item, dict) for item in fields_parsed)
        reconstructed = UpdateConfig.model_validate(parsed["updates"]["set_user_email"])
        assert reconstructed == ucfg

    def test_key_renders_as_subtable_not_inline(self) -> None:
        """key sub-table emits as [updates.<n>.key], not inline."""
        ucfg = build_update_config(
            "set_user_email",
            schema="dbo",
            table="users",
            key={"field": "id", "type": "int"},
            fields=[{"field": "email", "type": "str"}],
        )
        doc = tomlkit.document()
        add_update(doc, "set_user_email", ucfg)
        dumped = tomlkit.dumps(doc)
        assert "[updates.set_user_email.key]" in dumped
        assert "key = {" not in dumped

    def test_duplicate_name_raises(self) -> None:
        """Adding an update under an existing name raises ValueError."""
        ucfg = build_update_config(
            "dup",
            table="users",
            key={"field": "id", "type": "int"},
            fields=[{"field": "email", "type": "str"}],
        )
        doc = tomlkit.document()
        add_update(doc, "dup", ucfg)
        with pytest.raises(ValueError):
            add_update(doc, "dup", ucfg)


class TestRemove:
    """Tests for remove_query and remove_update."""

    @pytest.mark.parametrize("kind", ["queries", "updates"])
    def test_remove_happy_path(self, kind: str) -> None:
        """Remove an existing entry and confirm via list_configured_tools."""
        doc = tomlkit.document()
        if kind == "queries":
            qcfg = build_query_config("q1", sql="SELECT 1")
            add_query(doc, "q1", qcfg)
            remove_query(doc, "q1")
        else:
            ucfg = build_update_config(
                "u1",
                table="users",
                key={"field": "id", "type": "int"},
                fields=[{"field": "email", "type": "str"}],
            )
            add_update(doc, "u1", ucfg)
            remove_update(doc, "u1")
        listing = list_configured_tools(doc)
        assert listing == {"queries": [], "updates": []}

    @pytest.mark.parametrize(
        "fn_name,setup",
        [
            ("remove_query", "missing_name"),
            ("remove_query", "missing_section"),
            ("remove_update", "missing_name"),
            ("remove_update", "missing_section"),
        ],
    )
    def test_remove_raises_keyerror(self, fn_name: str, setup: str) -> None:
        """remove_* raises KeyError on missing name OR missing section."""
        from mcp_tools_sql.config import authoring

        fn = getattr(authoring, fn_name)
        doc = tomlkit.document()
        if setup == "missing_name":
            if fn_name == "remove_query":
                add_query(doc, "other", build_query_config("other", sql="SELECT 1"))
            else:
                add_update(
                    doc,
                    "other",
                    build_update_config(
                        "other",
                        table="users",
                        key={"field": "id", "type": "int"},
                        fields=[{"field": "email", "type": "str"}],
                    ),
                )
        with pytest.raises(KeyError):
            fn(doc, "nope")

    @pytest.mark.parametrize("kind", ["queries", "updates"])
    def test_remove_prunes_empty_parent(self, kind: str) -> None:
        """Removing the last entry deletes the parent section."""
        doc = tomlkit.document()
        if kind == "queries":
            add_query(doc, "q1", build_query_config("q1", sql="SELECT 1"))
            remove_query(doc, "q1")
        else:
            add_update(
                doc,
                "u1",
                build_update_config(
                    "u1",
                    table="users",
                    key={"field": "id", "type": "int"},
                    fields=[{"field": "email", "type": "str"}],
                ),
            )
            remove_update(doc, "u1")
        assert kind not in doc
        parsed = _roundtrip(doc)
        assert kind not in parsed


class TestListConfiguredTools:
    """Tests for list_configured_tools."""

    @pytest.mark.parametrize(
        "queries,updates,expected",
        [
            ([], [], {"queries": [], "updates": []}),
            (["q1", "q2"], [], {"queries": ["q1", "q2"], "updates": []}),
            ([], ["u1"], {"queries": [], "updates": ["u1"]}),
            (
                ["qa", "qb"],
                ["ua"],
                {"queries": ["qa", "qb"], "updates": ["ua"]},
            ),
        ],
    )
    def test_listing_four_cases(
        self,
        queries: list[str],
        updates: list[str],
        expected: dict[str, list[str]],
    ) -> None:
        """Empty / queries only / updates only / both."""
        doc = tomlkit.document()
        for q in queries:
            add_query(doc, q, build_query_config(q, sql="SELECT 1"))
        for u in updates:
            add_update(
                doc,
                u,
                build_update_config(
                    u,
                    table="users",
                    key={"field": "id", "type": "int"},
                    fields=[{"field": "email", "type": "str"}],
                ),
            )
        assert list_configured_tools(doc) == expected
