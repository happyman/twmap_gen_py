#!/usr/bin/env bash
# Taiwan Map Generator TUI launcher (Linux/macOS)
# Usage: ./mapgen-tui.sh [args...]
set -euo pipefail
cd "$(dirname "$0")"
exec uv run mapgen-tui "$@"
