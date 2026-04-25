# Step 3: resolve_connection + discover_query_config

> See [summary.md](summary.md) for full context (Issue #2).

## Goal

Implement `resolve_connection` (dict lookup by connection name) and `discover_query_config` (config file discovery chain). Both are simple functions with clear error paths.

## WHERE

- **Modify**: `src/mcp_tools_sql/config/loader.py` (replace remaining stubs, add `discover_query_config`)
- **Modify**: `tests/config/test_loader.py` (add resolution + discovery test classes)

## WHAT

### `config/loader.py` — two functions

```python
def resolve_connection(
    query_config: QueryFileConfig,
    user_config: UserConfig,
) -> ConnectionConfig:
    """Look up the named connection from user config.

    Raises ValueError if query_config.connection is not found
    in user_config.connections.
    """
    # Note: Also update the existing stub docstring from
    # "Merge project and user configs..." to reflect the actual dict-lookup behavior.

def discover_query_config(
    config_flag: Path | None,
    project_dir: Path,
) -> Path:
    """Find the query config file.

    Discovery chain:
    1. Explicit --config flag path
    2. mcp-tools-sql.toml in project_dir
    3. Raise ValueError with guidance
    """
```

### `tests/config/test_loader.py` — resolution + discovery tests

```python
class TestResolveConnection:
    def test_valid_connection_found(self) -> None:
        """Returns ConnectionConfig when name matches."""

    def test_missing_connection_raises(self) -> None:
        """ValueError when connection name not in user config."""

    def test_empty_connection_name_raises(self) -> None:
        """ValueError when query_config.connection is empty."""

    def test_empty_connections_dict_raises(self) -> None:
        """ValueError when user_config has no connections."""

class TestDiscoverQueryConfig:
    def test_explicit_flag_returned(self, tmp_path: Path) -> None:
        """--config flag path is returned directly."""

    def test_explicit_flag_missing_raises(self, tmp_path: Path) -> None:
        """ValueError when --config points to non-existent file."""

    def test_auto_discovery_in_project_dir(self, tmp_path: Path) -> None:
        """Finds mcp-tools-sql.toml in project_dir."""

    def test_no_config_found_raises(self, tmp_path: Path) -> None:
        """ValueError with guidance when no config exists."""
```

## HOW

- `resolve_connection`: pure dict lookup, no file I/O
- `discover_query_config`: `Path.exists()` checks, returns `Path`
- Both raise `ValueError` with descriptive messages

## ALGORITHM

### resolve_connection
```
name = query_config.connection
if not name: raise ValueError("No connection name specified in query config")
if name not in user_config.connections:
    available = list(user_config.connections.keys())
    raise ValueError(f"Connection '{name}' not found. Available: {available}")
return user_config.connections[name]
```

### discover_query_config
```
if config_flag is not None:
    if not config_flag.exists(): raise ValueError(f"Config not found: {config_flag}")
    return config_flag
candidate = project_dir / "mcp-tools-sql.toml"
if candidate.exists(): return candidate
raise ValueError(f"No mcp-tools-sql.toml found in {project_dir}. Use --config or create the file.")
```

## DATA

- `resolve_connection` returns `ConnectionConfig` or raises `ValueError`
- `discover_query_config` returns `Path` or raises `ValueError`
- Error messages include available connection names / expected file paths

## LLM Prompt

```
Implement step 3 of the plan in pr_info/steps/step_3.md.
Read pr_info/steps/summary.md for full context.
Follow TDD: write tests first in tests/config/test_loader.py, then implement the functions.
Run all three quality checks (pylint, mypy, pytest) before committing.
```
