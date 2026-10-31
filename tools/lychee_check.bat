@REM Check markdown links with lychee.
@REM
@REM Install: lychee is a single .exe, no toolchain required.
@REM   Download: https://github.com/lycheeverse/lychee/releases
@REM   Asset:    lychee-x86_64-pc-windows-msvc.zip (verify it against the .sha256 file)
@REM   Extract lychee.exe and place it on PATH (e.g. .venv\Scripts\lychee.exe,
@REM   already on PATH when the venv is active).
@REM   With the GitHub CLI:
@REM     gh release download --repo lycheeverse/lychee --pattern "lychee-x86_64-pc-windows-msvc.zip*"
@REM
@REM Usage:
@REM   This script runs in --offline mode (local files only, fast, no network).
@REM   It also checks #anchors (--include-fragments).
@REM   To ALSO check external URLs, remove --offline below (slower, may report
@REM   transient TLS/network errors that are not real broken links).
@where lychee >nul 2>nul
@if errorlevel 1 (
    @echo ERROR: lychee not found on PATH. See the install instructions at the top of this file.
    @exit /b 1
)
lychee --offline --include-fragments README.md SECURITY.md "docs/**/*.md"
