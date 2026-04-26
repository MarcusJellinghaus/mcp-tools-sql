"""Vulture whitelist - false positives and intentionally kept code.

This file tells Vulture to ignore certain items that appear unused but are
intentionally kept for:
- API completeness (base class methods, Pydantic model fields)
- False positives (pytest fixtures, framework patterns)

Format: _.attribute_name (Vulture's attribute-style whitelist syntax)

Review this list periodically - items may become used or truly dead over time.
"""

# =============================================================================
# FALSE POSITIVES - Pytest Fixtures
# =============================================================================
_.pytestmark
_.sqlite_db
_.sqlite_memory_db

# =============================================================================
# DatabaseBackend ABC - abstract methods (implemented by subclasses)
# =============================================================================
_.connect
_.close
_.execute_query
_.execute_update
_.explain
_.read_schemas
_.read_tables
_.read_columns
_.read_relations
_.search_columns
_.run

# =============================================================================
# Backend implementations - stored config and method params
# =============================================================================
_._config
_._backend
_._mcp
_._queries
_._updates
_.schema
_.pattern
_.filter_pattern

# =============================================================================
# Pydantic model fields (accessed dynamically)
# =============================================================================
_.database
_.username
_.password
_.trusted_connection
_.credential_env_var
_.connection_string
_.name
_.description
_.required
_.params
_.field
_.schema_name
_.key
_.connection
_.model_config

# =============================================================================
# Tool/Server classes - registered dynamically
# =============================================================================
_.register
SchemaTools
QueryTools
UpdateTools
ValidationTools

# =============================================================================
# Dynamic tool registration — attrs set at runtime
# =============================================================================
_.__signature__
_.__doc__

# =============================================================================
# Stub functions - will be used when implemented
# =============================================================================
_.load_query_config
_.load_user_config
_.resolve_connection
_.create_server
_.format_rows
_.format_columns
_.format_update_result
_.logger
