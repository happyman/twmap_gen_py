#!/usr/bin/env bash
# Install script for the Taiwan Map Generator (Linux/macOS).
# Checks for uv (installs it if missing), then installs the base Python deps
# into a local .venv via `uv sync`. Run from the project root:
#
#   ./install.sh
#
set -euo pipefail

say() { printf '\033[1;32m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m!!\033[0m %s\n' "$*" >&2; }

cd "$(dirname "$0")"

# --- 1. Python must be >= 3.11 (uv will fetch one if needed) ---
if command -v python3 >/dev/null 2>&1; then
    pyver="$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
    say "Found python3 $pyver (project requires 3.11+)"
else
    warn "python3 not found — uv can download a managed Python during sync."
fi

# --- 2. Ensure uv is installed ---
if command -v uv >/dev/null 2>&1; then
    uv_version="$(uv --version)"
    say "Found uv: $uv_version"
else
    say "uv not found. Installing uv via the official installer..."
    if command -v curl >/dev/null 2>&1; then
        curl -LsSf https://astral.sh/uv/install.sh | sh
    elif command -v wget >/dev/null 2>&1; then
        wget -qO- https://astral.sh/uv/install.sh | sh
    else
        echo "ERROR: need curl or wget to install uv. Install uv first, then re-run this script." >&2
        exit 1
    fi
    # Add ~/.local/bin (typical uv install path) to PATH for this script.
    export PATH="$HOME/.local/bin:$PATH"
    command -v uv >/dev/null 2>&1 || { echo "ERROR: uv install failed — add ~/.local/bin to PATH and re-run." >&2; exit 1; }
    say "Installed $(uv --version)"
fi

# --- 3. Install the base dependencies into .venv ---
say "Installing dependencies with uv sync (see pyproject.toml)..."
uv sync

# --- 4. Verify ---
say "Verifying installation..."
uv run mapgen --version

say "Done."
warn "Launch the terminal UI with:  ./mapgen-tui.sh"
warn "If fonts fail to render on Linux, install libcairo (e.g. 'sudo apt install libcairo2' / 'brew install cairo')."