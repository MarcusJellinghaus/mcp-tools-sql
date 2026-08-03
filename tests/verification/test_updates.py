"""Tests for `verify_updates` and `verify_one_update`."""

from __future__ import annotations

import pytest

from mcp_tools_sql.backends.registry import BackendRegistry
from mcp_tools_sql.backends.sqlite import SQLiteBackend
from mcp_tools_sql.config.models import (
    ConnectionConfig,
    ResolvedTarget,
    ResolvedTargets,
    UpdateConfig,
    UpdateFieldConfig,
    UpdateKeyConfig,
)
from mcp_tools_sql.verification import verify_updates
from mcp_tools_sql.verification.updates import verify_one_update

from .conftest import StubRegistry


def test_verify_updates_valid_sqlite(
    sqlite_targets: ResolvedTargets,
    sqlite_registry: BackendRegistry,
    all_reachable: dict[tuple[str, str], bool],
) -> None:
    """Update on `customers` with key=`id` and fields=`name,country` → all ok."""
    updates = {
        "set_customer_name": UpdateConfig(
            table="customers",
            key=UpdateKeyConfig(field="id", type="int"),
            fields=[
                UpdateFieldConfig(field="name", type="str"),
                UpdateFieldConfig(field="country", type="str"),
            ],
        ),
    }
    result = verify_updates(updates, sqlite_targets, sqlite_registry, all_reachable)

    assert result["set_customer_name.table"]["ok"] is True
    assert result["set_customer_name.key_column"]["ok"] is True
    assert result["set_customer_name.fields"]["ok"] is True
    assert result["overall_ok"] is True


def test_verify_updates_detects_missing_table(
    sqlite_targets: ResolvedTargets,
    sqlite_registry: BackendRegistry,
    all_reachable: dict[tuple[str, str], bool],
) -> None:
    """Update on `does_not_exist` → all three rows ok=False with Table not found."""
    updates = {
        "bad_update": UpdateConfig(
            table="does_not_exist",
            key=UpdateKeyConfig(field="id", type="int"),
            fields=[UpdateFieldConfig(field="x", type="str")],
        ),
    }
    result = verify_updates(updates, sqlite_targets, sqlite_registry, all_reachable)

    assert result["bad_update.table"]["ok"] is False
    assert "Table not found" in result["bad_update.table"]["error"]
    assert result["bad_update.key_column"]["ok"] is False
    assert result["bad_update.fields"]["ok"] is False
    assert result["overall_ok"] is False


def test_verify_updates_detects_missing_key_column(
    sqlite_targets: ResolvedTargets,
    sqlite_registry: BackendRegistry,
    all_reachable: dict[tuple[str, str], bool],
) -> None:
    """Key column `nonexistent_id` → key row ok=False, table row ok=True."""
    updates = {
        "bad_key": UpdateConfig(
            table="customers",
            key=UpdateKeyConfig(field="nonexistent_id", type="int"),
            fields=[UpdateFieldConfig(field="name", type="str")],
        ),
    }
    result = verify_updates(updates, sqlite_targets, sqlite_registry, all_reachable)

    assert result["bad_key.table"]["ok"] is True
    assert result["bad_key.key_column"]["ok"] is False
    assert "nonexistent_id" in result["bad_key.key_column"]["value"]
    assert result["bad_key.fields"]["ok"] is True
    assert result["overall_ok"] is False


def test_verify_updates_detects_missing_field_column(
    sqlite_targets: ResolvedTargets,
    sqlite_registry: BackendRegistry,
    all_reachable: dict[tuple[str, str], bool],
) -> None:
    """Issue test (xiv): field `nonexistent_field` → fields row ok=False."""
    updates = {
        "bad_field": UpdateConfig(
            table="customers",
            key=UpdateKeyConfig(field="id", type="int"),
            fields=[
                UpdateFieldConfig(field="name", type="str"),
                UpdateFieldConfig(field="nonexistent_field", type="str"),
            ],
        ),
    }
    result = verify_updates(updates, sqlite_targets, sqlite_registry, all_reachable)

    assert result["bad_field.table"]["ok"] is True
    assert result["bad_field.key_column"]["ok"] is True
    assert result["bad_field.fields"]["ok"] is False
    assert "nonexistent_field" in result["bad_field.fields"]["error"]
    assert result["overall_ok"] is False


def test_verify_updates_no_updates_configured(
    sqlite_targets: ResolvedTargets,
    sqlite_registry: BackendRegistry,
    all_reachable: dict[tuple[str, str], bool],
) -> None:
    """Empty updates dict → empty result, overall_ok=True."""
    result = verify_updates({}, sqlite_targets, sqlite_registry, all_reachable)

    assert [k for k in result if k != "overall_ok"] == []
    assert result["overall_ok"] is True


def test_verify_updates_rejects_invalid_table_identifier(
    sqlite_targets: ResolvedTargets,
    sqlite_registry: BackendRegistry,
    all_reachable: dict[tuple[str, str], bool],
) -> None:
    """Bad table identifier → only `.table` row emitted, ok=False with whitelist message."""
    updates = {
        "bad": UpdateConfig(
            table="orders; DROP TABLE x",
            key=UpdateKeyConfig(field="id", type="int"),
            fields=[UpdateFieldConfig(field="name", type="str")],
        ),
    }
    result = verify_updates(updates, sqlite_targets, sqlite_registry, all_reachable)

    assert result["bad.table"]["ok"] is False
    assert "intentionally restricted" in result["bad.table"]["error"]
    assert "orders; DROP TABLE x" in result["bad.table"]["error"]
    assert "bad.key_column" not in result
    assert "bad.fields" not in result
    assert result["overall_ok"] is False


def test_verify_updates_rejects_invalid_schema_identifier(
    sqlite_targets: ResolvedTargets,
    sqlite_registry: BackendRegistry,
    all_reachable: dict[tuple[str, str], bool],
) -> None:
    """Bad schema_name → only `.table` row emitted; empty schema_name still passes."""
    updates = {
        "bad": UpdateConfig(
            table="customers",
            schema="bad schema",
            key=UpdateKeyConfig(field="id", type="int"),
            fields=[UpdateFieldConfig(field="name", type="str")],
        ),
    }
    result = verify_updates(updates, sqlite_targets, sqlite_registry, all_reachable)

    assert result["bad.table"]["ok"] is False
    assert "intentionally restricted" in result["bad.table"]["error"]
    assert "bad schema" in result["bad.table"]["error"]
    assert "bad.key_column" not in result
    assert "bad.fields" not in result

    # Regression guard: empty schema_name still passes
    ok_updates = {
        "good": UpdateConfig(
            table="customers",
            schema="",
            key=UpdateKeyConfig(field="id", type="int"),
            fields=[UpdateFieldConfig(field="name", type="str")],
        ),
    }
    ok_result = verify_updates(
        ok_updates, sqlite_targets, sqlite_registry, all_reachable
    )
    assert ok_result["good.table"]["ok"] is True


def test_verify_updates_rejects_invalid_key_field_identifier(
    sqlite_targets: ResolvedTargets,
    sqlite_registry: BackendRegistry,
    all_reachable: dict[tuple[str, str], bool],
) -> None:
    """Bad key.field identifier → `.key_column` row ok=False with whitelist message."""
    updates = {
        "bad": UpdateConfig(
            table="customers",
            key=UpdateKeyConfig(field="id; DROP", type="int"),
            fields=[UpdateFieldConfig(field="name", type="str")],
        ),
    }
    result = verify_updates(updates, sqlite_targets, sqlite_registry, all_reachable)

    assert result["bad.table"]["ok"] is True
    assert result["bad.key_column"]["ok"] is False
    assert "intentionally restricted" in result["bad.key_column"]["error"]
    assert "id; DROP" in result["bad.key_column"]["error"]


def test_verify_updates_rejects_invalid_field_identifier(
    sqlite_targets: ResolvedTargets,
    sqlite_registry: BackendRegistry,
    all_reachable: dict[tuple[str, str], bool],
) -> None:
    """One field with bad identifier → `.fields` row ok=False mentioning offender."""
    updates = {
        "bad": UpdateConfig(
            table="customers",
            key=UpdateKeyConfig(field="id", type="int"),
            fields=[UpdateFieldConfig(field="bad-col", type="str")],
        ),
    }
    result = verify_updates(updates, sqlite_targets, sqlite_registry, all_reachable)

    assert result["bad.fields"]["ok"] is False
    assert "intentionally restricted" in result["bad.fields"]["error"]
    assert "bad-col" in result["bad.fields"]["error"]


def test_verify_updates_surfaces_required_flag_inline(
    sqlite_targets: ResolvedTargets,
    sqlite_registry: BackendRegistry,
    all_reachable: dict[tuple[str, str], bool],
) -> None:
    """Two fields (one required, one optional) → `.fields` value shows `(req)` inline."""
    updates = {
        "set_customer": UpdateConfig(
            table="customers",
            key=UpdateKeyConfig(field="id", type="int"),
            fields=[
                UpdateFieldConfig(field="name", type="str", required=True),
                UpdateFieldConfig(field="country", type="str"),
            ],
        ),
    }
    result = verify_updates(updates, sqlite_targets, sqlite_registry, all_reachable)

    fields_value = result["set_customer.fields"]["value"]
    assert "name(req)" in fields_value
    assert "country" in fields_value
    assert "country(req)" not in fields_value


@pytest.mark.parametrize(
    ("name", "update"),
    [
        (
            "set_customer_name",
            UpdateConfig(
                table="customers",
                key=UpdateKeyConfig(field="id", type="int"),
                fields=[
                    UpdateFieldConfig(field="name", type="str"),
                    UpdateFieldConfig(field="country", type="str"),
                ],
            ),
        ),
        (
            "missing",
            UpdateConfig(
                table="does_not_exist",
                key=UpdateKeyConfig(field="id", type="int"),
                fields=[UpdateFieldConfig(field="x", type="str")],
            ),
        ),
        (
            "bad_table",
            UpdateConfig(
                table="orders; DROP",
                key=UpdateKeyConfig(field="id", type="int"),
                fields=[UpdateFieldConfig(field="name", type="str")],
            ),
        ),
    ],
)
def test_verify_one_update_matches_bulk(
    sqlite_targets: ResolvedTargets,
    sqlite_registry: BackendRegistry,
    all_reachable: dict[tuple[str, str], bool],
    name: str,
    update: UpdateConfig,
) -> None:
    """`verify_one_update` matches bulk output across happy/missing/bad-id branches."""
    updates = {name: update}
    bulk = verify_updates(updates, sqlite_targets, sqlite_registry, all_reachable)
    one = verify_one_update(
        name, update, sqlite_targets, sqlite_registry, all_reachable
    )

    bulk_without_overall = {k: v for k, v in bulk.items() if k != "overall_ok"}
    assert list(one.keys()) == list(bulk_without_overall.keys())
    assert one == bulk_without_overall


# ---------------------------------------------------------------------------
# Per-target skip (step 15)
# ---------------------------------------------------------------------------


def test_verify_updates_skips_update_pinned_to_unreachable_connection(
    sqlite_backend: SQLiteBackend,
) -> None:
    """An update pinned to a down connection → three skip rows naming it.

    A reachable update in the same run still gets real verdicts, and the bad
    identifier check still fires statically even for a down target.
    """
    default = ResolvedTarget(
        connection="default",
        database="main",
        config=ConnectionConfig(backend="sqlite", path=":memory:"),
        backend_name="sqlite",
        is_default=True,
    )
    prod = ResolvedTarget(
        connection="prod",
        database="main",
        config=ConnectionConfig(backend="sqlite", path=":memory:"),
        backend_name="sqlite",
        is_default=False,
    )
    targets = ResolvedTargets(
        targets=[default, prod],
        default=default,
        file_default_connection="default",
    )
    registry = StubRegistry(sqlite_backend)
    reachable = {("default", "main"): True, ("prod", "main"): False}

    updates = {
        "reachable_one": UpdateConfig(
            table="customers",
            key=UpdateKeyConfig(field="id", type="int"),
            fields=[UpdateFieldConfig(field="name", type="str")],
        ),
        "pinned_down": UpdateConfig(
            table="customers",
            key=UpdateKeyConfig(field="id", type="int"),
            fields=[UpdateFieldConfig(field="name", type="str")],
            connection="prod",
        ),
    }
    result = verify_updates(updates, targets, registry, reachable)

    # Reachable update gets real verdicts.
    assert result["reachable_one.table"]["ok"] is True
    assert result["reachable_one.key_column"]["ok"] is True

    # Pinned-to-down update → three skip rows naming the connection.
    for suffix in ("table", "key_column", "fields"):
        entry = result[f"pinned_down.{suffix}"]
        assert entry.get("warn") is True
        assert "prod" in entry["value"]

    # Skip alone does not flip overall_ok.
    assert result["overall_ok"] is True


def test_verify_updates_bad_identifier_still_fires_for_unreachable_target(
    sqlite_backend: SQLiteBackend,
) -> None:
    """A bad table identifier is reported even when its target is unreachable."""
    default = ResolvedTarget(
        connection="prod",
        database="main",
        config=ConnectionConfig(backend="sqlite", path=":memory:"),
        backend_name="sqlite",
        is_default=True,
    )
    targets = ResolvedTargets(
        targets=[default],
        default=default,
        file_default_connection="prod",
    )
    registry = StubRegistry(sqlite_backend)
    reachable = {("prod", "main"): False}

    updates = {
        "bad": UpdateConfig(
            table="orders; DROP",
            key=UpdateKeyConfig(field="id", type="int"),
            fields=[UpdateFieldConfig(field="name", type="str")],
        ),
    }
    result = verify_updates(updates, targets, registry, reachable)

    assert result["bad.table"]["ok"] is False
    assert "intentionally restricted" in result["bad.table"]["error"]
    assert "bad.key_column" not in result
