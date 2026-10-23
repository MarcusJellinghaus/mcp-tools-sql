@echo off
REM Check for circular imports using pycycle
REM Statically analyzes import statements to find potential cycles
REM
REM Usage from Git Bash: ./tools/pycycle_check.sh
REM Usage from cmd.exe:  tools\pycycle_check.bat

where pycycle >nul 2>&1
if errorlevel 1 (
    echo ERROR: pycycle not found. Install with: pip install pycycle
    exit /b 1
)

echo Checking for circular imports...
pycycle --here --ignore .venv,__pycache__,build,dist,.git,.pytest_cache,.mypy_cache %*
exit /b %ERRORLEVEL%
