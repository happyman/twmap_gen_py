"""Load user configuration from ``config.toml`` at the project root.

The file is optional; missing keys fall back to the built-in defaults
defined here (which mirror the historical hard-coded values). Config
keys are read once per process and cached.
"""

from __future__ import annotations

import sys
import tomllib
from pathlib import Path

_CONFIG_NAME = "config.toml"

DEFAULTS: dict = {
    "picker": {
        "url": "https://dev.happyman.idv.tw/map/?mode=picker&return=http://127.0.0.1:",
        "timeout": 300,
    },
    "output": {
        "font_path": "",
    },
}

_cache: dict | None = None


def project_root() -> Path:
    """Absolute path of the project root (where ``config.toml`` lives)."""
    # mapgen/settings.py -> ../
    return Path(__file__).resolve().parent.parent


def config_path() -> Path:
    return project_root() / _CONFIG_NAME


def load_config() -> dict:
    """Read ``config.toml``, merged over :data:`DEFAULTS`, cached after first call."""
    global _cache  # noqa: PLW0603
    if _cache is not None:
        return _cache

    data: dict = {}
    path = config_path()
    if path.is_file():
        try:
            with path.open("rb") as fh:
                data = tomllib.load(fh)
        except (tomllib.TOMLDecodeError, OSError) as exc:
            print(f"mapgen: cannot read {path}: {exc}", file=sys.stderr)

    merged: dict = {}
    for section, defaults in DEFAULTS.items():
        merged[section] = {**defaults, **(data.get(section) or {})}
    _cache = merged
    return _cache


def picker_url() -> str:
    return load_config()["picker"]["url"]


def picker_timeout() -> int:
    timeout = load_config()["picker"]["timeout"]
    return int(timeout) if timeout else 300


def font_path() -> str:
    """Configured font path; empty string means "use the bundled font"."""
    return load_config()["output"].get("font_path", "") or ""
