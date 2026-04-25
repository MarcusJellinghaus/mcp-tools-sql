# Step 2: TOML Loaders — load_query_config + load_user_config

> See [summary.md](summary.md) for full context (Issue #2).

## Goal

Implement `load_query_config` and `load_user_config` in `config/loader.py`. These read TOML files, validate with Pydantic, handle errors, and warn on credentials in the wrong file.

## WHERE

- **Modify**: `src/mcp_tools_sql/config/loader.py`
- **Create**: `tests/config/test_loader.py`

## WHAT

### `config/loader.py` — two loader functions

```python
import logging
import tomllib
from pathlib import Path

_SENSITIVE_KEYS = {"password", "connection_string", "credential_env_var"}
_logger = logging.getLogger(__name__)

def load_query_config(path: Path) -> QueryFileConfig:
    """Load and validate the project query configuration file."""

def load_user_config(path: Path | None = None) -> UserConfig:
    """Load user config from path or default location.

    Returns defaults if the file does not exist. No side effects.
    """

def _has_sensitive_keys(data: dict) -> list[str]:
    """Recursively scan a parsed TOML dict for sensitive keys."""
```

Private helper: `_has_sensitive_keys` is used internally by `load_query_config` to detect credentials before Pydantic parsing (Pydantic silently drops extra fields).

### `tests/config/test_loader.py` — loader tests

```python
class TestLoadQueryConfig:
    def test_valid_query_config(self, tmp_path: Path) -> None:
        """Loads a complete mcp-tools-sql.toml exercising all nested models (queries with params, updates with key/fields/schema)."""

    def test_empty_file_returns_defaults(self, tmp_path: Path) -> None:
        """Empty TOML file returns QueryFileConfig with defaults."""

    def test_missing_file_raises_value_error(self, tmp_path: Path) -> None:
        """Non-existent path raises ValueError with file path in message."""

    def test_invalid_toml_raises_value_error(self, tmp_path: Path) -> None:
        """Malformed TOML raises ValueError with file path and line number in message."""

    def test_credential_warning(self, tmp_path: Path, caplog) -> None:
        """password in query config triggers a log warning."""

    def test_extra_fields_ignored(self, tmp_path: Path) -> None:
        """Unknown TOML keys are silently ignored by Pydantic."""

    def test_schema_alias_through_toml(self, tmp_path: Path) -> None:
        """TOML 'schema = dbo' maps to UpdateConfig.schema_name."""

class TestLoadUserConfig:
    def test_valid_user_config(self, tmp_path: Path) -> None:
        """Loads user config with multiple named connections using different backends."""

    def test_none_path_uses_default(self) -> None:
        """None path defaults to ~/.mcp-tools-sql/config.toml."""

    def test_missing_file_returns_defaults(self, tmp_path: Path) -> None:
        """Non-existent file returns UserConfig() with empty connections."""

    def test_invalid_toml_raises_value_error(self, tmp_path: Path) -> None:
        """Malformed user config raises ValueError."""
```

## HOW

- `tomllib` (stdlib) for TOML parsing — imported at top of `loader.py`
- `logging.getLogger(__name__)` for credential warnings
- Layer constraint: only stdlib + pydantic + `mcp_tools_sql.config.models` imports
- `load_user_config` default path: `Path.home() / ".mcp-tools-sql" / "config.toml"`
- Change `load_user_config` signature: add default `= None` to `path` parameter so it can be called without arguments.
- `TOMLDecodeError` has `lineno`, `colno`, `msg` attributes in Python 3.11+ — use them for error context.

## ALGORITHM

### load_query_config
```
open path as binary, read with tomllib.loads
scan raw dict recursively for keys in _SENSITIVE_KEYS → log warning
parse dict into QueryFileConfig(**data)
catch TOMLDecodeError → ValueError(f"Invalid TOML in {path} (line {e.lineno}, col {e.colno}): {e.msg}")
catch OSError → ValueError(f"Cannot read {path}: {e}")
return config
```

### load_user_config
```
if path is None: path = Path.home() / ".mcp-tools-sql" / "config.toml"
if not path.exists(): return UserConfig()
open and parse with tomllib (same error wrapping as above)
return UserConfig(**data)
```

### credential scan (inline in load_query_config)
```
def _has_sensitive_keys(data: dict) -> list[str]:
    found = []
    for key, value in data.items():
        if key in _SENSITIVE_KEYS: found.append(key)
        if isinstance(value, dict): found.extend(_has_sensitive_keys(value))
    return found
```

## DATA

- `load_query_config` returns `QueryFileConfig` or raises `ValueError`
- `load_user_config` returns `UserConfig` (never raises for missing file)
- Credential warning: `"Query config {path} contains sensitive key(s): {keys}. Move credentials to user config (~/.mcp-tools-sql/config.toml)."`

## LLM Prompt

```
Implement step 2 of the plan in pr_info/steps/step_2.md.
Read pr_info/steps/summary.md for full context.
Follow TDD: write tests first in tests/config/test_loader.py, then implement the loaders.
Use inline TOML strings written to tmp_path for test fixtures.
Run all three quality checks (pylint, mypy, pytest) before committing.
```
