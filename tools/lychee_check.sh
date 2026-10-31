#!/bin/bash
# Check markdown links with lychee
#
# Usage from Git Bash: ./tools/lychee_check.sh
#
# Install: single binary, no toolchain required.
#   Download: https://github.com/lycheeverse/lychee/releases (verify the asset
#   against its .sha256 file), then put the binary on PATH.
#   With the GitHub CLI (Windows asset shown; pick the one for your platform):
#     gh release download --repo lycheeverse/lychee --pattern "lychee-x86_64-pc-windows-msvc.zip*"
#
# Runs in --offline mode (local files only, fast, no network) and also checks
# #anchors (--include-fragments). To ALSO check external URLs, remove --offline
# below (slower, may report transient TLS/network errors that are not broken links).

if ! command -v lychee &> /dev/null; then
    echo "ERROR: lychee not found on PATH. See the install instructions at the top of this file."
    exit 1
fi

echo "Checking links with lychee..."
lychee --offline --include-fragments README.md SECURITY.md "docs/**/*.md" "$@"
