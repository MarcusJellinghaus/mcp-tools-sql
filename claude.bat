@echo off
cls
setlocal enabledelayedexpansion
REM Launcher for Claude Code with MCP servers
REM Assumes you're running from the project root

REM === Step 1: Activate project environment ===
if not exist "%CD%\.venv\Scripts\activate.bat" (
    echo ERROR: Virtual environment not found at .venv
    echo Please run: uv sync
    exit /b 1
)
echo Activating project environment: %CD%\.venv
call "%CD%\.venv\Scripts\activate.bat"
if "!VIRTUAL_ENV!"=="" (
    echo ERROR: Failed to activate virtual environment.
    exit /b 1
)

REM === Step 2: MCP tool verification ===
set "VENV_SCRIPTS=!VIRTUAL_ENV!\Scripts"
if not exist "!VENV_SCRIPTS!\mcp-tools-py.exe" (
    echo ERROR: mcp-tools-py.exe not found in !VENV_SCRIPTS!
    echo Please run: uv sync
    exit /b 1
)
if not exist "!VENV_SCRIPTS!\mcp-workspace.exe" (
    echo ERROR: mcp-workspace.exe not found in !VENV_SCRIPTS!
    echo Please run: uv sync
    exit /b 1
)

REM === Step 3: Print versions ===
"!VENV_SCRIPTS!\mcp-coder.exe" --version
"!VENV_SCRIPTS!\mcp-workspace.exe" --version
"!VENV_SCRIPTS!\mcp-tools-py.exe" --version

REM === Step 4: Set env vars and launch ===
set "MCP_CODER_VENV_PATH=!VENV_SCRIPTS!"
set "MCP_CODER_VENV_DIR=!VIRTUAL_ENV!"
set "MCP_CODER_PROJECT_DIR=%CD%"
set "DISABLE_AUTOUPDATER=1"

echo Starting Claude Code with:
echo   Project env:  !VIRTUAL_ENV!
echo   Project dir:  !MCP_CODER_PROJECT_DIR!

C:\Users\%USERNAME%\.local\bin\claude.exe %*

REM Reset terminal state after Claude exits (workaround for dirty terminal bug)
REM See https://github.com/anthropics/claude-code/issues/38761
for /f %%a in ('echo prompt $E ^| cmd') do set "ESC=%%a"
<nul set /p="!ESC![?2004l!ESC![?1l!ESC![?25h!ESC![J"
