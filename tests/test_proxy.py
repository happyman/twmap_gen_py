"""Tests for PAC-based proxy resolution (mapgen.proxy) and its wiring.

The scenario behind this: users whose network egress requires a PAC file used
to time out on tile downloads, because aiohttp only honours proxy environment
variables. ``mapgen.proxy`` auto-discovers a PAC via PyPAC and hands the
resulting proxy (or "direct", for PAC ``DIRECT`` / no PAC) to aiohttp and
urllib explicitly.
"""

import logging
import urllib.request

import pypac

import mapgen.proxy as proxy_mod
from mapgen import cli, stitcher

PROXY_URL = "http://proxy.corp:8080"


class _FakePac:
    """Stands in for pypac.parser.PACFile.find_proxy_for_url()."""

    def __init__(self, value: str = "PROXY proxy.corp:8080; DIRECT"):
        self.value = value
        self.calls: list[tuple[str, str]] = []

    def find_proxy_for_url(self, url: str, host: str) -> str:
        self.calls.append((url, host))
        return self.value


class _StaticResolver:
    """Answers with one fixed value (proxy URL / DIRECT / None / exception)."""

    def __init__(self, answer):
        self.answer = answer
        self.calls: list[str] = []

    def get_proxy(self, url: str):
        self.calls.append(url)
        if isinstance(self.answer, Exception):
            raise self.answer
        return self.answer


def _reset(monkeypatch) -> None:
    """Give each test a fresh discovery state and per-host cache."""
    monkeypatch.setattr(proxy_mod, "_discovered", False)
    monkeypatch.setattr(proxy_mod, "_resolver", None)
    monkeypatch.setattr(proxy_mod, "_cache", {})


# --------------------------------------------------------------------------
# Resolution: proxy / DIRECT / no PAC / failures
# --------------------------------------------------------------------------


def test_pac_proxy_resolution(monkeypatch):
    """A PAC saying "PROXY ...; DIRECT" yields the proxy URL for the host."""
    _reset(monkeypatch)
    pac = _FakePac()
    monkeypatch.setattr(pypac, "get_pac", lambda **kwargs: pac)

    assert proxy_mod.proxy_for_url("http://tiles.example/16/1/2.png") == PROXY_URL
    assert proxy_mod.pac_enabled() is True


def test_pac_direct_means_no_proxy(monkeypatch):
    """PAC bypass (DIRECT) must resolve to None — no proxy configured."""
    _reset(monkeypatch)
    monkeypatch.setattr(pypac, "get_pac", lambda **kwargs: _FakePac("DIRECT"))

    assert proxy_mod.proxy_for_url("http://tiles.example/16/1/2.png") is None
    assert proxy_mod.pac_enabled() is True


def test_no_pac_means_direct(monkeypatch):
    """Without a PAC file everything goes direct and pac_enabled() is False."""
    _reset(monkeypatch)
    monkeypatch.setattr(pypac, "get_pac", lambda **kwargs: None)

    assert proxy_mod.proxy_for_url("http://tiles.example/16/1/2.png") is None
    assert proxy_mod.pac_enabled() is False


def test_discovery_failure_degrades_to_direct(monkeypatch):
    """PAC discovery errors must never break the map build."""

    def boom(**kwargs):
        raise RuntimeError("network down")

    _reset(monkeypatch)
    monkeypatch.setattr(pypac, "get_pac", boom)

    assert proxy_mod.proxy_for_url("http://tiles.example/16/1/2.png") is None
    assert proxy_mod.pac_enabled() is False


def test_lookup_failure_degrades_to_direct(monkeypatch):
    """A PAC JS explosion on lookup degrades to direct, not an exception."""
    _reset(monkeypatch)
    monkeypatch.setattr(proxy_mod, "_discovered", True)
    monkeypatch.setattr(proxy_mod, "_resolver", _StaticResolver(RuntimeError("js")))

    assert proxy_mod.proxy_for_url("http://tiles.example/16/1/2.png") is None


def test_socks_proxy_is_warned_and_ignored(monkeypatch, caplog):
    """SOCKS proxies are unsupported (aiohttp/urllib): warn and go direct."""
    _reset(monkeypatch)
    pac = _FakePac("SOCKS5 socks.corp:1080; DIRECT")
    monkeypatch.setattr(pypac, "get_pac", lambda **kwargs: pac)

    with caplog.at_level(logging.WARNING, logger="mapgen.proxy"):
        assert proxy_mod.proxy_for_url("http://tiles.example/16/1/2.png") is None
    assert "SOCKS" in caplog.text


# --------------------------------------------------------------------------
# Caching: PAC fetched once, JS evaluated once per host
# --------------------------------------------------------------------------


def test_pac_discovered_once_and_host_cached(monkeypatch):
    """get_pac() runs once per process; FindProxyForURL() once per host."""
    _reset(monkeypatch)
    pac = _FakePac()
    get_pac_calls: list[dict] = []

    def fake_get_pac(**kwargs):
        get_pac_calls.append(kwargs)
        return pac

    monkeypatch.setattr(pypac, "get_pac", fake_get_pac)

    # Two tiles on the same host → one PAC fetch, one JS evaluation.
    proxy_mod.proxy_for_url("http://tiles.example/16/1/2.png")
    proxy_mod.proxy_for_url("http://tiles.example/16/3/4.png")
    assert len(get_pac_calls) == 1
    assert len(pac.calls) == 1

    # A second host gets its own lookup, still without re-fetching the PAC.
    proxy_mod.proxy_for_url("http://other.example/16/1/2.png")
    assert len(get_pac_calls) == 1
    assert len(pac.calls) == 2


def test_cache_survives_repeated_lookups_for_host(monkeypatch):
    """Cached hosts return the same answer without touching the resolver."""
    _reset(monkeypatch)
    resolver = _StaticResolver(PROXY_URL)
    monkeypatch.setattr(proxy_mod, "_discovered", True)
    monkeypatch.setattr(proxy_mod, "_resolver", resolver)

    for _ in range(5):
        assert proxy_mod.proxy_for_url("http://tiles.example/a.png") == PROXY_URL
    assert resolver.calls == ["http://tiles.example/a.png"]

    # A different path on a *different* host is a fresh lookup.
    assert proxy_mod.proxy_for_url("http://other.example/a.png") == PROXY_URL
    assert len(resolver.calls) == 2


# --------------------------------------------------------------------------
# aiohttp wiring (stitcher.download_tiles)
# --------------------------------------------------------------------------


class _FakeGetCtx:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    def raise_for_status(self):
        pass

    async def read(self):
        return b"fake-tile"


class _FakeSession:
    """Captures ClientSession kwargs and session.get() calls."""

    instances: list["_FakeSession"] = []

    def __init__(self, **kwargs):
        type(self).instances.append(self)
        self.session_kwargs = kwargs
        self.get_calls: list[tuple[str, dict]] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    def get(self, url, **kwargs):
        self.get_calls.append((url, kwargs))
        return _FakeGetCtx()


async def test_download_tiles_uses_pac_proxy(monkeypatch, tmp_path):
    """With a PAC: explicit proxy= per request and trust_env turned off."""
    import aiohttp

    monkeypatch.setattr(proxy_mod, "proxy_for_url", lambda url: PROXY_URL)
    monkeypatch.setattr(proxy_mod, "pac_enabled", lambda: True)
    _FakeSession.instances.clear()
    monkeypatch.setattr(aiohttp, "ClientSession", _FakeSession)

    await stitcher.download_tiles(
        [("http://tiles.example/16/1/2.png", 1, 2)], tmp_path
    )

    session = _FakeSession.instances[0]
    assert session.session_kwargs["trust_env"] is False
    url, kwargs = session.get_calls[0]
    assert url == "http://tiles.example/16/1/2.png"
    assert kwargs["proxy"] == PROXY_URL
    assert (tmp_path / "1_2.png").read_bytes() == b"fake-tile"


async def test_download_tiles_without_pac_keeps_env_behaviour(
    monkeypatch, tmp_path
):
    """No PAC: trust_env stays on and no explicit proxy is forced."""
    import aiohttp

    monkeypatch.setattr(proxy_mod, "proxy_for_url", lambda url: None)
    monkeypatch.setattr(proxy_mod, "pac_enabled", lambda: False)
    _FakeSession.instances.clear()
    monkeypatch.setattr(aiohttp, "ClientSession", _FakeSession)

    await stitcher.download_tiles(
        [("http://tiles.example/16/1/2.png", 1, 2)], tmp_path
    )

    session = _FakeSession.instances[0]
    assert session.session_kwargs["trust_env"] is True
    _url, kwargs = session.get_calls[0]
    assert kwargs["proxy"] is None


# --------------------------------------------------------------------------
# urllib wiring (cli._download_one)
# --------------------------------------------------------------------------


class _FakeResp:
    def read(self):
        return b"fake-tile"

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class _FakeOpener:
    def __init__(self, record: dict):
        self._record = record

    def open(self, req, timeout=None):
        self._record["opened"] = {"url": req.full_url, "timeout": timeout}
        return _FakeResp()


def _no_urlopen(monkeypatch, record: dict):
    def forbidden(req, timeout=None):
        record["urlopen_called"] = True
        raise AssertionError("urlopen must not be called when the PAC decides")

    monkeypatch.setattr(urllib.request, "urlopen", forbidden)


def test_download_one_forces_pac_proxy(monkeypatch, tmp_path):
    """PAC says proxy: urllib routes through a ProxyHandler with it."""
    record: dict = {}
    monkeypatch.setattr(proxy_mod, "proxy_for_url", lambda url: PROXY_URL)
    monkeypatch.setattr(proxy_mod, "pac_enabled", lambda: True)

    def fake_build(*handlers):
        record["handlers"] = handlers
        return _FakeOpener(record)

    monkeypatch.setattr(urllib.request, "build_opener", fake_build)
    _no_urlopen(monkeypatch, record)

    cli._download_one("http://tiles.example/16/1/2.png", tmp_path)

    (handler,) = record["handlers"]
    assert isinstance(handler, urllib.request.ProxyHandler)
    assert handler.proxies == {"http": PROXY_URL, "https": PROXY_URL}
    assert record["opened"]["timeout"] == 30
    assert (tmp_path / "tile.png").read_bytes() == b"fake-tile"


def test_download_one_pac_direct_forces_no_proxy(monkeypatch, tmp_path):
    """PAC says DIRECT: an empty ProxyHandler forces direct (ignores env)."""
    record: dict = {}
    monkeypatch.setattr(proxy_mod, "proxy_for_url", lambda url: None)
    monkeypatch.setattr(proxy_mod, "pac_enabled", lambda: True)

    def fake_build(*handlers):
        record["handlers"] = handlers
        return _FakeOpener(record)

    monkeypatch.setattr(urllib.request, "build_opener", fake_build)
    _no_urlopen(monkeypatch, record)

    cli._download_one("http://tiles.example/16/1/2.png", tmp_path)

    (handler,) = record["handlers"]
    assert isinstance(handler, urllib.request.ProxyHandler)
    assert handler.proxies == {}
    assert (tmp_path / "tile.png").read_bytes() == b"fake-tile"


def test_download_one_without_pac_keeps_urlopen(monkeypatch, tmp_path):
    """No PAC at all: the historical urlopen (env-proxy) path is kept."""
    record: dict = {}
    monkeypatch.setattr(proxy_mod, "proxy_for_url", lambda url: None)
    monkeypatch.setattr(proxy_mod, "pac_enabled", lambda: False)

    def fake_urlopen(req, timeout=None):
        record["opened"] = {"url": req.full_url, "timeout": timeout}
        return _FakeResp()

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    def forbidden_build(*handlers):
        raise AssertionError("build_opener must not be used without a PAC")

    monkeypatch.setattr(urllib.request, "build_opener", forbidden_build)

    cli._download_one("http://tiles.example/16/1/2.png", tmp_path)

    assert record["opened"]["timeout"] == 30
    assert (tmp_path / "tile.png").read_bytes() == b"fake-tile"
