"""Derive a ``mapgen make --region`` and suggested title from a GPX file.

The TUI's ``--from-gpx`` flag uses this to bound the map to exactly the area a
track/routes/waypoints cover: every point is projected from WGS84 into the
chosen datum's Transverse Mercator grid, the bounding box is padded (at least
``DEFAULT_PAD_M`` each side) and the region is sized/centred to tile A4
5 km × 7 km map pages exactly. The result is a ``x0,y0,shiftx,shifty,DATUM``
region spec that is copy-pasteable into ``mapgen make --region``, plus a
suggested map title (first track/route name, else the GPX file stem).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

from .proj import get_twd_crs, wgs84_to_twd

DEFAULT_PAD_M = 1000  # minimum margin around the track on every side
PAGE_W_M = 5000  # one A4 map page, km width  -> shiftx is a multiple of 5 km
PAGE_H_M = 7000  # one A4 map page, km height -> shifty is a multiple of 7 km


@dataclass(frozen=True)
class GpxRegion:
    """Everything needed to prefill the TUI from a GPX file."""

    x0: int
    y0: int
    shiftx: int
    shifty: int
    datum: str
    penghu: bool
    points: int
    tracks: int
    routes: int
    waypoints: int
    lon_min: float
    lat_min: float
    lon_max: float
    lat_max: float
    path: str
    title: str

    @property
    def spec(self) -> str:
        """The ``--region`` value: ``x0,y0,shiftx,shifty[,datum]``.

        TWD97 is the ``_parse_region`` default, so its spec omits the datum
        suffix; TWD67 (and the deprecated longitude/latitude modes) spell it
        out.
        """
        base = f"{self.x0},{self.y0},{self.shiftx},{self.shifty}"
        return base + f",{self.datum}" if self.datum != "TWD97" else base

    @property
    def file_bounds(self) -> tuple[float, float, float, float]:
        return self.lon_min, self.lat_min, self.lon_max, self.lat_max


def collect_points(path: str | Path) -> dict:
    """Parse ``path`` with gpxpy and return its points/counts.

    Returns ``{"points": [(lon, lat), ...], "tracks", "routes", "waypoints",
    "track_names", "route_names"}``. Raises :class:`ValueError` when the file
    is missing, invalid, or contains no usable coordinates.
    """
    import gpxpy

    p = Path(path)
    if not p.exists():
        raise ValueError(f"GPX file does not exist: {p}")
    try:
        gpx = gpxpy.parse(p.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001 - gpxpy raises many types
        raise ValueError(f"unable to parse GPX file: {exc}") from exc

    lons: list[float] = []
    lats: list[float] = []

    def add(lon: float, lat: float) -> None:
        if lon is not None and lat is not None:
            lons.append(lon)
            lats.append(lat)

    for trk in gpx.tracks:
        for seg in trk.segments:
            for pt in seg.points:
                add(pt.longitude, pt.latitude)
    for rte in gpx.routes:
        for pt in rte.points:
            add(pt.longitude, pt.latitude)
    for wpt in gpx.waypoints:
        add(wpt.longitude, wpt.latitude)

    if not lons:
        raise ValueError(f"GPX file has no usable coordinates: {p}")

    return {
        "points": list(zip(lons, lats)),
        "tracks": len(gpx.tracks),
        "routes": len(gpx.routes),
        "waypoints": len(gpx.waypoints),
        "track_names": [t.name for t in gpx.tracks if t.name],
        "route_names": [r.name for r in gpx.routes if r.name],
    }


def _auto_penghu(lons: list[float]) -> bool:
    return sum(lons) / len(lons) < 120.0


def _fit_box(
    lo: float,
    hi: float,
    page: int,
    pad_m: int,
) -> tuple[float, float]:
    """Pad/size/centre an extent to tile ``page``-metre cells.

    Returns ``(start, shift_km)`` where ``shift_km`` is a whole number: the
    box ``[start, start + shift_km*1000]`` covers ``[lo, hi]`` padded by at
    least ``pad_m`` on both sides, is centred on ``lo..hi``, is a multiple of
    ``page`` metres, and starts on a whole-kilometre boundary.
    """
    extent = hi - lo
    size = page * max(math.ceil((extent + 2 * pad_m) / page), 1)
    centre = (lo + hi) / 2.0
    shift_km = size // 1000
    while True:
        start = round((centre - size / 2.0) / 1000.0) * 1000
        left = lo - start
        right = start + size - hi
        if left >= pad_m and right >= pad_m:
            return start, shift_km
        size += page
        shift_km = size // 1000


def _suggest_title(parsed: dict, path: Path) -> str:
    for name in (*parsed["track_names"], *parsed["route_names"]):
        if name:
            return name
    return path.stem


def region_from_gpx(
    path: str | Path,
    datum: str = "TWD67",
    pad_m: int = DEFAULT_PAD_M,
) -> GpxRegion:
    """Compute a centred, A4-page-aligned region covering every GPX point.

    ``datum`` is ``"TWD67"`` (default) or ``"TWD97"``. The area (Taiwan vs
    Penghu) is auto-detected from the mean longitude (Penghu uses the 119°E
    central meridian). ``pad_m`` is the minimum margin (metres) kept on every
    side; the region is then expanded to a whole number of A4 pages
    (5 km × 7 km), centred on the track, and snapped to whole kilometres, so
    ``shiftx`` is a multiple of 5 and ``shifty`` a multiple of 7.
    """
    parsed = collect_points(path)
    lons = [lon for lon, _ in parsed["points"]]
    lats = [lat for _, lat in parsed["points"]]

    penghu = _auto_penghu(lons)
    crs = get_twd_crs(datum, penghu)

    xs, ys = [], []
    for lon, lat in parsed["points"]:
        x, y = wgs84_to_twd(lon, lat, crs)
        xs.append(x)
        ys.append(y)

    x_min, x_max = min(xs), max(xs)
    y_min, y_max = min(ys), max(ys)  # TWD Y grows north; y_max is the top

    x0, shiftx = _fit_box(x_min, x_max, PAGE_W_M, pad_m)
    y_bottom, shifty = _fit_box(y_min, y_max, PAGE_H_M, pad_m)
    y0 = y_bottom + shifty * 1000  # top edge (north)

    p = Path(path)
    return GpxRegion(
        x0=int(x0),
        y0=int(y0),
        shiftx=int(shiftx),
        shifty=int(shifty),
        datum=datum,
        penghu=penghu,
        points=len(parsed["points"]),
        tracks=parsed["tracks"],
        routes=parsed["routes"],
        waypoints=parsed["waypoints"],
        lon_min=min(lons),
        lat_min=min(lats),
        lon_max=max(lons),
        lat_max=max(lats),
        path=str(p),
        title=_suggest_title(parsed, p),
    )


__all__ = [
    "DEFAULT_PAD_M",
    "GpxRegion",
    "PAGE_H_M",
    "PAGE_W_M",
    "collect_points",
    "region_from_gpx",
]
