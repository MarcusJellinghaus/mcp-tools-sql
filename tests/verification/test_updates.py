"""Tests for `verify_updates` and `verify_one_update`."""

from __future__ import annotations

import pytest

from mcp_tools_sql.backends.sqlite import SQLiteBackend
from mcp_tools_sql.config.models import (
    UpdateConfig,
    UpdateFieldConfig,
    UpdateKeyConfig,
)
from mcp_tools_sql.verification import verify_updates
from mcp_tools_sql.verification.updates import verify_one_update


def test_verify_updates_valid_sqlite(sqlite_backend: SQLiteBackend) -> None:
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
    result = verify_updates(updates, "sqlite", sqlite_backend)

    assert result["set_customer_name.table"]["ok"] is True
    assert result["set_customer_name.key_column"]["ok"] is True
    assert result["set_customer_name.fields"]["ok"] is True
    assert result["overall_ok"] is True


def test_verify_updates_detects_missing_table(sqlite_backend: SQLiteBackend) -> None:
    """Update on `does_not_exist` → all three rows ok=False with Table not found."""
    updates = {
        "bad_update": UpdateConfig(
            table="does_not_exist",
            key=UpdateKeyConfig(field="id", type="int"),
            fields=[UpdateFieldConfig(field="x", type="str")],
        ),
    }
    result = verify_updates(updates, "sqlite", sqlite_backend)

    assert result["bad_update.table"]["ok"] is False
    assert "Table not found" in result["bad_update.table"]["error"]
    assert result["bad_update.key_column"]["ok"] is False
    assert result["bad_update.fields"]["ok"] is False
    assert result["overall_ok"] is False


def test_verify_updates_detects_missing_key_column(
    sqlite_backend: SQLiteBackend,
) -> None:
    """Key column `nonexistent_id` → key row ok=False, table row ok=True."""
    updates = {
        "bad_key": UpdateConfig(
            table="customers",
            key=UpdateKeyConfig(field="nonexistent_id", type="int"),
            fields=[UpdateFieldConfig(field="name", type="str")],
        ),
    }
    result = verify_updates(updates, "sqlite", sqlite_backend)

    assert result["bad_key.table"]["ok"] is True
    assert result["bad_key.key_column"]["ok"] is False
    assert "nonexistent_id" in result["bad_key.key_column"]["value"]
    assert result["bad_key.fields"]["ok"] is True
    assert result["overall_ok"] is False


def test_verify_updates_detects_missing_field_column(
    sqlite_backend: SQLiteBackend,
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
    result = verify_updates(updates, "sqlite", sqlite_backend)

    assert result["bad_field.table"]["ok"] is True
    assert result["bad_field.key_column"]["ok"] is True
    assert result["bad_field.fields"]["ok"] is False
    assert "nonexistent_field" in result["bad_field.fields"]["error"]
    assert result["overall_ok"] is False


def test_verify_updates_no_updates_configured(sqlite_backend: SQLiteBackend) -> None:
    """Empty updates dict → empty result, overall_ok=True."""
    result = verify_updates({}, "sqlite", sqlite_backend)

    assert [k for k in result if k != "overall_ok"] == []
    assert result["overall_ok"] is True


def test_verify_updates_rejects_invalid_table_identifier(
    sqlite_backend: SQLiteBackend,
) -> None:
    """Bad table identifier → only `.table` row emitted, ok=False with whitelist message."""
    updates = {
        "bad": UpdateConfig(
            table="orders; DROP TABLE x",
            key=UpdateKeyConfig(field="id", type="int"),
            fields=[UpdateFieldConfig(field="name", type="str")],
        ),
    }
    result = verify_updates(updates, "sqlite", sqlite_backend)

    assert result["bad.table"]["ok"] is False
    assert "intentionally restricted" in result["bad.table"]["error"]
    assert "orders; DROP TABLE x" in result["bad.table"]["error"]
    assert "bad.key_column" not in result
    assert "bad.fields" not in result
    assert result["overall_ok"] is False


def test_verify_updates_rejects_invalid_schema_identifier(
    sqlite_backend: SQLiteBackend,
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
    result = verify_updates(updates, "sqlite", sqlite_backend)

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
    ok_result = verify_updates(ok_updates, "sqlite", sqlite_backend)
    assert ok_result["good.table"]["ok"] is True


def test_verify_updates_rejects_invalid_key_field_identifier(
    sqlite_backend: SQLiteBackend,
) -> None:
    """Bad key.field identifier → `.key_column` row ok=False with whitelist message."""
    updates = {
        "bad": UpdateConfig(
            table="customers",
            key=UpdateKeyConfig(field="id; DROP", type="int"),
            fields=[UpdateFieldConfig(field="name", type="str")],
        ),
    }
    result = verify_updates(updates, "sqlite", sqlite_backend)

    assert result["bad.table"]["ok"] is True
    assert result["bad.key_column"]["ok"] is False
    assert "intentionally restricted" in result["bad.key_column"]["error"]
    assert "id; DROP" in result["bad.key_column"]["error"]


def test_verify_updates_rejects_invalid_field_identifier(
    sqlite_backend: SQLiteBackend,
) -> None:
    """One field with bad identifier → `.fields` row ok=False mentioning offender."""
    updates = {
        "bad": UpdateConfig(
            table="customers",
            key=UpdateKeyConfig(field="id", type="int"),
            fields=[UpdateFieldConfig(field="bad-col", type="str")],
        ),
    }
    result = verify_updates(updates, "sqlite", sqlite_backend)

    assert result["bad.fields"]["ok"] is False
    assert "intentionally restricted" in result["bad.fields"]["error"]
    assert "bad-col" in result["bad.fields"]["error"]


def test_verify_updates_surfaces_required_flag_inline(
    sqlite_backend: SQLiteBackend,
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
    result = verify_updates(updates, "sqlite", sqlite_backend)

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
    sqlite_backend: SQLiteBackend, name: str, update: UpdateConfig
) -> None:
    """`verify_one_update` matches bulk output across happy/missing/bad-id branches."""
    updates = {name: update}
    bulk = verify_updates(updates, "sqlite", sqlite_backend)
    one = verify_one_update(name, update, "sqlite", sqlite_backend)

    bulk_without_overall = {k: v for k, v in bulk.items() if k != "overall_ok"}
    assert list(one.keys()) == list(bulk_without_overall.keys())
    assert one == bulk_without_overall
