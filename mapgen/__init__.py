"""Taiwan map generator — Python rewrite of cmd_make2.php."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _metadata_version

try:
    __version__ = _metadata_version("twmap-gen")
except PackageNotFoundError:  # pragma: no cover - source checkout without install
    __version__ = "0.1.0"
