"""Tests for deriving a map region from a GPX file."""

from __future__ import annotations

import pytest

from mapgen.gpx_region import (
    DEFAULT_PAD_M,
    PAGE_H_M,
    PAGE_W_M,
    collect_points,
    region_from_gpx,
)
from mapgen.proj import get_twd_crs, wgs84_to_twd


def _write_gpx(tmp_path, name="track.gpx") -> str:
    path = tmp_path / name
    path.write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<gpx version="1.1" creator="pytest">
  <metadata><name>test</name></metadata>
  <wpt lat="24.08" lon="121.16"><name>start</name></wpt>
  <trk><trkseg>
    <trkpt lat="24.13" lon="121.19"><ele>3000</ele></trkpt>
    <trkpt lat="24.10" lon="121.18"></trkpt>
  </trkseg></trk>
</gpx>
""",
        encoding="utf-8",
    )
    return str(path)


def test_collect_points_counts_tracks_waypoints(tmp_path):
    data = collect_points(_write_gpx(tmp_path))
    assert data["tracks"] == 1
    assert data["routes"] == 0
    assert data["waypoints"] == 1
    assert len(data["points"]) == 3
    assert data["track_names"] == []
    assert data["route_names"] == []


def test_region_pads_min_centred_and_fits_a4_pages(tmp_path):
    path = _write_gpx(tmp_path)
    reg = region_from_gpx(path, datum="TWD67", pad_m=DEFAULT_PAD_M)

    crs = get_twd_crs("TWD67", False)
    xs, ys = [], []
    for lon, lat in [(121.16, 24.08), (121.19, 24.13), (121.18, 24.10)]:
        x, y = wgs84_to_twd(lon, lat, crs)
        xs.append(x)
        ys.append(y)

    left = min(xs) - reg.x0
    right = reg.x0 + reg.shiftx * 1000 - max(xs)
    bottom = min(ys) - (reg.y0 - reg.shifty * 1000)
    top = reg.y0 - max(ys)

    # whole-km, A4-page-aligned grid (5 km x, 7 km y)
    assert reg.x0 % 1000 == 0
    assert reg.y0 % 1000 == 0
    assert reg.shiftx * 1000 % PAGE_W_M == 0
    assert reg.shifty * 1000 % PAGE_H_M == 0
    assert reg.shiftx > 0 and reg.shifty > 0

    # at least pad_m margin on every side, and centering within one km
    assert left >= DEFAULT_PAD_M and right >= DEFAULT_PAD_M
    assert top >= DEFAULT_PAD_M and bottom >= DEFAULT_PAD_M
    assert abs(left - right) <= 1000
    assert abs(top - bottom) <= 1000

    assert reg.datum == "TWD67"
    assert not reg.penghu
    assert reg.spec.endswith(",TWD67")
    assert reg.spec.startswith(f"{reg.x0},{reg.y0},{reg.shiftx},{reg.shifty},")


def test_region_with_valid_buffer_contains_all_points(tmp_path):
    path = _write_gpx(tmp_path)
    reg = region_from_gpx(path, pad_m=0)
    crs = get_twd_crs("TWD67", False)
    for lon, lat in [(121.16, 24.08), (121.19, 24.13), (121.18, 24.10)]:
        x, y = wgs84_to_twd(lon, lat, crs)
        assert reg.x0 <= x <= reg.x0 + reg.shiftx * 1000
        assert reg.y0 - reg.shifty * 1000 <= y <= reg.y0
        assert reg.shiftx * 1000 % PAGE_W_M == 0
        assert reg.shifty * 1000 % PAGE_H_M == 0


def test_region_title_from_track_name(tmp_path):
    path = tmp_path / "named.gpx"
    path.write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<gpx version="1.1" creator="pytest"><trk><name>合歡山 主峰</name><trkseg>
  <trkpt lat="24.14" lon="121.27"></trkpt>
</trkseg></trk></gpx>
""",
        encoding="utf-8",
    )
    reg = region_from_gpx(str(path))
    assert reg.title == "合歡山 主峰"


def test_region_title_falls_back_to_route_then_filename_stem(tmp_path):
    path = tmp_path / "北三段.gpx"
    path.write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<gpx version="1.1" creator="pytest"><rte><rtept lat="24.0" lon="121.0"></rtept></rte></gpx>
""",
        encoding="utf-8",
    )
    # route name wins over the file stem
    named = tmp_path / "route.gpx"
    named.write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<gpx version="1.1" creator="pytest"><rte><name>能高安東軍</name>
<rtept lat="24.0" lon="121.0"></rtept></rte></gpx>
""",
        encoding="utf-8",
    )
    assert region_from_gpx(str(named)).title == "能高安東軍"
    # no names at all -> filename stem "北三段"
    assert region_from_gpx(str(path)).title == "北三段"


def test_region_twd97_omits_suffix_twd67_spells_it(tmp_path):
    path = _write_gpx(tmp_path)
    twd67 = region_from_gpx(path, datum="TWD67")
    twd97 = region_from_gpx(path, datum="TWD97")
    assert twd67.datum == "TWD67"
    assert twd97.datum == "TWD97"
    assert twd67.spec.endswith(",TWD67")
    assert twd97.spec == (
        f"{twd97.x0},{twd97.y0},{twd97.shiftx},{twd97.shifty}"
    )


def test_region_auto_detects_penghu(tmp_path):
    ph = tmp_path / "ph.gpx"
    ph.write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<gpx version="1.1" creator="pytest"><trk><trkseg>
  <trkpt lat="23.5" lon="119.5"></trkpt>
  <trkpt lat="23.6" lon="119.6"></trkpt>
</trkseg></trk></gpx>
""",
        encoding="utf-8",
    )
    reg = region_from_gpx(str(ph), datum="TWD67")
    assert reg.penghu is True
    # Penghu uses the 119E central meridian -> x in the 270-330 km band
    assert 250000 <= reg.x0 <= 340000


def test_region_missing_file_raises(tmp_path):
    with pytest.raises(ValueError, match="does not exist"):
        region_from_gpx(str(tmp_path / "nope.gpx"))


def test_region_empty_or_invalid_file_raises(tmp_path):
    empty = tmp_path / "empty.gpx"
    empty.write_text("""<?xml version="1.0"?><gpx version="1.1"/>""",
                     encoding="utf-8")
    with pytest.raises(ValueError, match="no usable coordinates"):
        region_from_gpx(str(empty))
    bad = tmp_path / "bad.gpx"
    bad.write_text("not xml", encoding="utf-8")
    with pytest.raises(ValueError, match="unable to parse"):
        region_from_gpx(str(bad))
