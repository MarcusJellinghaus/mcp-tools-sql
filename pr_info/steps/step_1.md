# Step 1: UpdateConfig Schema Alias + Model Tests

> See [summary.md](summary.md) for full context (Issue #2).

## Goal

Add `Field(alias="schema")` to `UpdateConfig.schema_name` so TOML can use `schema = "dbo"` while Python uses `schema_name`. Write model validation tests.

## WHERE

- **Modify**: `src/mcp_tools_sql/config/models.py`
- **Create**: `tests/config/__init__.py`
- **Create**: `tests/config/test_models.py`

## WHAT

### `config/models.py` — UpdateConfig changes

```python
from pydantic import BaseModel, ConfigDict, Field

class UpdateConfig(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    description: str = ""
    schema_name: str = Field(default="", alias="schema")
    table: str = ""
    key: Optional[UpdateKeyConfig] = None
    fields: list[UpdateFieldConfig] = []
```

### `tests/config/test_models.py` — model validation tests

```python
class TestUpdateConfigAlias:
    def test_schema_alias_from_toml_key(self) -> None:
        """UpdateConfig accepts 'schema' (TOML key) and maps to schema_name."""

    def test_schema_name_direct(self) -> None:
        """UpdateConfig accepts 'schema_name' (Python name) directly."""

    def test_schema_alias_in_dict_output(self) -> None:
        """model_dump(by_alias=True) uses 'schema' key."""

class TestModelValidation:
    def test_query_config_requires_sql(self) -> None:
        """QueryConfig raises ValidationError without sql field."""

    def test_query_file_config_defaults(self) -> None:
        """QueryFileConfig has empty defaults for all fields."""

    def test_user_config_defaults(self) -> None:
        """UserConfig defaults: empty connections, security.allow_updates=True."""

    def test_connection_config_defaults(self) -> None:
        """ConnectionConfig defaults to sqlite backend."""

    def test_query_file_config_nested_parsing(self) -> None:
        """QueryFileConfig parses nested queries with params from dict."""
```

## HOW

- Import `Field` and `ConfigDict` from pydantic (already a dependency)
- `populate_by_name=True` allows both `schema` (alias) and `schema_name` (field name) in input
- Only `UpdateConfig` gets `ConfigDict` — no shared base class change

## ALGORITHM

No algorithm — this is a declarative model change.

## DATA

`UpdateConfig(schema="dbo")` → `config.schema_name == "dbo"`
`UpdateConfig(schema_name="dbo")` → `config.schema_name == "dbo"`
`config.model_dump(by_alias=True)` → `{"schema": "dbo", ...}`

## LLM Prompt

```
Implement step 1 of the plan in pr_info/steps/step_1.md.
Read pr_info/steps/summary.md for full context.
Follow TDD: write tests first in tests/config/test_models.py, then make the model change.
Create tests/config/__init__.py as an empty file.
Run all three quality checks (pylint, mypy, pytest) before committing.
```
