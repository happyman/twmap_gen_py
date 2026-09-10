@echo off
rem Install script for the Taiwan Map Generator (Windows).
rem Checks for uv (installs it if missing), then installs the base Python deps
rem into a local .venv via `uv sync`. Run from the project root:
rem
rem   install.bat
rem
setlocal enabledelayedexpansion

echo.
echo === Taiwan Map Generator install ===
echo.

rem --- 1. Ensure uv is installed ---
where uv >nul 2>nul
if %errorlevel%==0 (
    for /f "delims=" %%v in ('uv --version') do echo Found uv: %%v
) else (
    echo uv not found. Installing uv via the official installer...
    powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
    if errorlevel 1 (
        echo ERROR: uv install failed. Install it manually, then re-run this script.
        exit /b 1
    )
    rem Add ~/.local/bin (typical uv install path) to PATH for this session.
    set "PATH=%USERPROFILE%\.local\bin;%PATH%"
    where uv >nul 2>nul
    if not errorlevel 1 (
        echo Installed uv.
    ) else (
        echo ERROR: uv not on PATH. Add %USERPROFILE%\.local\bin to PATH and re-run.
        exit /b 1
    )
)

rem --- 2. Install the base dependencies into .venv ---
echo Installing dependencies with "uv sync" (see pyproject.toml)...
uv sync
if errorlevel 1 (
    echo ERROR: uv sync failed.
    exit /b 1
)

rem --- 3. Verify ---
echo Verifying installation...
uv run mapgen --version
if errorlevel 1 (
    echo ERROR: verification failed.
    exit /b 1
)

echo.
echo Done. Launch the terminal UI with:  mapgen-tui.bat
echo.