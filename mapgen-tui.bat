@echo off
rem Taiwan Map Generator TUI launcher (Windows)
rem Usage: mapgen-tui [args...]   e.g.  mapgen-tui -t 合歡山 -v 3
cd /d "%~dp0"
uv run mapgen-tui %*
