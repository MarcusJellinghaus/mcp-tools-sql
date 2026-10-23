#!/usr/bin/env bash
# Check for circular imports using pycycle
# Statically analyzes import statements to find potential cycles

set -e

if ! command -v pycycle &> /dev/null; then
    echo "ERROR: pycycle not found. Install with: pip install pycycle"
    exit 1
fi

echo "Checking for circular imports..."
pycycle --here --ignore .venv,__pycache__,build,dist,.git,.pytest_cache,.mypy_cache "$@"
