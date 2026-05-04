#!/bin/bash
# Reinstall mcp-tools-sql package in development mode (editable install)
# Usage: source tools/reinstall_local.sh   (from project root; persists venv activation)
#    or: bash tools/reinstall_local.sh     (does not persist activation to caller)

# Detect if script is sourced (return works only in sourced/function context)
(return 0 2>/dev/null) && _SOURCED=1 || _SOURCED=0

echo "============================================="
echo "MCP-Tools-SQL Package Reinstallation"
echo "============================================="
echo ""

# Determine project root (parent of tools directory)
_SCRIPT_PATH="${BASH_SOURCE[0]:-$0}"
_SCRIPT_DIR="$( cd "$( dirname "$_SCRIPT_PATH" )" && pwd )"
PROJECT_DIR="$( cd "$_SCRIPT_DIR/.." && pwd )"
VENV_DIR="$PROJECT_DIR/.venv"
VENV_BIN="$VENV_DIR/bin"
PY="$VENV_BIN/python"

echo "[0/5] Checking Python environment..."

# Guard: if a venv is active, it must be the project-local .venv
if [ -n "${VIRTUAL_ENV:-}" ] && [ "$VIRTUAL_ENV" != "$VENV_DIR" ]; then
    echo "[FAIL] Wrong virtual environment is active!"
    echo ""
    echo "  Active venv:   $VIRTUAL_ENV"
    echo "  Expected venv: $VENV_DIR"
    echo ""
    echo "  Deactivate the current venv first, or activate the correct one:"
    echo "    source $VENV_BIN/activate"
    [ "$_SOURCED" = "1" ] && return 1 || exit 1
fi

if ! command -v uv >/dev/null 2>&1; then
    echo "[FAIL] uv not found. Install it: pip install uv"
    [ "$_SOURCED" = "1" ] && return 1 || exit 1
fi
echo "[OK] uv found"

if [ ! -f "$VENV_BIN/activate" ]; then
    echo "Local virtual environment not found at $VENV_DIR"
    ( cd "$PROJECT_DIR" && uv venv .venv )
    echo "Local virtual environment created at $VENV_DIR"
fi
echo "[OK] Target environment: $VENV_DIR"
echo ""

echo "[1/5] Uninstalling existing packages..."
uv pip uninstall mcp-tools-sql mcp-coder mcp-tools-py mcp-workspace --python "$PY" 2>/dev/null || true
echo "[OK] Packages uninstalled"

echo ""
echo "[2/5] Installing mcp-tools-sql (this project) in editable mode..."
if ! ( cd "$PROJECT_DIR" && uv pip install -e ".[dev,all-backends]" --python "$PY" ); then
    echo "[FAIL] Installation failed!"
    [ "$_SOURCED" = "1" ] && return 1 || exit 1
fi
echo "[OK] Package and dev dependencies installed"

echo ""
echo "[3/5] Overriding dependencies with GitHub versions..."
# Validate read_github_deps.py succeeds before parsing its output
if ! "$PY" "$PROJECT_DIR/tools/read_github_deps.py" >/dev/null 2>&1; then
    echo "[FAIL] read_github_deps.py failed!"
    "$PY" "$PROJECT_DIR/tools/read_github_deps.py"
    [ "$_SOURCED" = "1" ] && return 1 || exit 1
fi
# Read GitHub dependency overrides from pyproject.toml
while IFS= read -r CMD; do
    [ -z "$CMD" ] && continue
    echo "  $CMD"
    if ! eval "$CMD --python \"$PY\""; then
        echo "[FAIL] GitHub dependency override failed!"
        [ "$_SOURCED" = "1" ] && return 1 || exit 1
    fi
done < <("$PY" "$PROJECT_DIR/tools/read_github_deps.py")
echo "[OK] GitHub dependencies overridden from pyproject.toml"

echo ""
echo "[4/5] Verifying CLI entry points in venv..."

if [ ! -x "$VENV_BIN/mcp-tools-sql" ]; then
    echo "[FAIL] mcp-tools-sql not found in $VENV_BIN"
    echo "  The entry point was not installed into the virtual environment."
    [ "$_SOURCED" = "1" ] && return 1 || exit 1
fi
echo "[OK] mcp-tools-sql found in $VENV_BIN"

echo ""
echo "[5/5] Verifying CLI functionality..."
if ! "$VENV_BIN/mcp-tools-sql" --help >/dev/null 2>&1; then
    echo "[FAIL] mcp-tools-sql CLI verification failed!"
    [ "$_SOURCED" = "1" ] && return 1 || exit 1
fi
echo "[OK] mcp-tools-sql CLI works"

echo ""
echo "============================================="
echo "Reinstallation completed successfully!"
echo ""
echo "Entry points installed in: $VENV_BIN"
echo "  - mcp-tools-sql"
echo "============================================="
echo ""

# Activate the correct venv (only persists if this script was sourced)
if [ -n "${VIRTUAL_ENV:-}" ] && [ "$VIRTUAL_ENV" != "$VENV_DIR" ]; then
    echo "  Deactivating wrong virtual environment: $VIRTUAL_ENV"
    deactivate 2>/dev/null || true
fi

if [ "${VIRTUAL_ENV:-}" != "$VENV_DIR" ]; then
    echo "  Activating virtual environment: $VENV_DIR"
    # shellcheck disable=SC1090,SC1091
    source "$VENV_BIN/activate"
fi

if [ "$_SOURCED" != "1" ]; then
    echo ""
    echo "Note: Activation does not persist because this script was not sourced."
    echo "      To activate in your current shell, run:"
    echo "        source $VENV_BIN/activate"
    echo "      Or source this script next time:"
    echo "        source tools/reinstall_local.sh"
fi

unset _SOURCED _SCRIPT_PATH _SCRIPT_DIR
