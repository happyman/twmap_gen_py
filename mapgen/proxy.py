"""PAC-based proxy auto-discovery and per-host resolution (PyPAC).

Corporate users whose egress needs a Proxy Auto-Configuration (PAC) file
previously timed out: aiohttp only honours ``HTTP_PROXY``-style environment
variables and never consults a PAC, so tile downloads went out direct and
died on the firewall. This module closes that gap:

- ``pypac.get_pac()`` auto-discovers a PAC (OS settings on Windows/macOS,
  WPAD over DNS elsewhere) — no configuration needed.
- ``proxy_for_url()`` answers, per tile host and cached, which proxy (if any)
  to hand to aiohttp/urllib. ``DIRECT`` (bypass) and "no PAC" both mean
  "no proxy": a direct connection.
- Discovery/lookup failures degrade to direct with a log line instead of
  aborting the map build.

SOCKS proxies are not supported (aiohttp/urllib cannot use them without extra
dependencies), so they are logged and treated as direct.
"""

from __future__ import annotations

import logging
import threading
from urllib.parse import urlsplit

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_discovered = False
_resolver = None  # pypac.resolver.ProxyResolver | None
_cache: dict[str, str | None] = {}


def _get_resolver():
    """Return the ProxyResolver for the auto-discovered PAC, or None.

    Discovery runs at most once per process (thread-safe, lazy: on first
    download) so PAC lookups never cost more than one round trip.
    """
    global _discovered, _resolver
    if _discovered:
        return _resolver
    with _lock:
        if _discovered:
            return _resolver
        _discovered = True
        try:
            from pypac import get_pac
            from pypac.resolver import ProxyResolver

            pac = get_pac()
        except Exception as exc:  # noqa: BLE001 — never fail the map build
            logger.debug("PAC auto-discovery failed: %s", exc)
            pac = None
        if pac is None:
            logger.debug("No PAC file found; falling back to proxy env vars (if any)")
        else:
            logger.info("PAC file discovered; tile downloads will follow it")
            _resolver = ProxyResolver(pac)
        return _resolver


def pac_enabled() -> bool:
    """True when a PAC file was auto-discovered."""
    return _get_resolver() is not None


def proxy_for_url(url: str) -> str | None:
    """Return the proxy URL for ``url``, or None for a direct connection.

    None means "direct": no PAC configured, the PAC returned ``DIRECT``
    (bypass), the host resolved to an unsupported SOCKS proxy, or resolution
    failed (graceful degradation).
    """
    resolver = _get_resolver()
    if resolver is None:
        return None
    host = (urlsplit(url).hostname or "").lower()
    with _lock:
        if host in _cache:
            return _cache[host]
    proxy = None
    try:
        proxy = resolver.get_proxy(url)  # 'DIRECT', a proxy URL, or None
    except Exception as exc:  # noqa: BLE001 — PAC JS may blow up
        logger.debug("PAC lookup failed for %s: %s", url, exc)
    if not proxy or proxy == "DIRECT":
        proxy = None
    elif proxy.startswith("socks"):
        logger.warning(
            "PAC returned a SOCKS proxy (%s) for %s — unsupported, going direct",
            proxy,
            host,
        )
        proxy = None
    else:
        logger.debug("PAC: %s -> %s", host, proxy)
    with _lock:
        _cache[host] = proxy
    return proxy


__all__ = ["pac_enabled", "proxy_for_url"]
