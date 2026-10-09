"""KMZ structure: one flat ``doc.kml`` holding every GroundOverlay.

Regression guard for the report 「地圖列印範圍 3×4，kmz 卻只出現 3×3」:
the port once routed all tiles through a single malformed ``<NetworkLink>``
with lowercase ``<link>`` children, so viewers loaded only the first
(3×3 km) tile. The PHP original (``GarminKmz::makekml``) writes every
``<GroundOverlay>`` directly into ``doc.kml`` — Garmin devices and Google
Earth only process that file.
"""

import math
import xml.etree.ElementTree as ET
import zipfile

import numpy as np

from mapgen.export.kmz import TILE_KM, kmz_grid, write_kmz
from mapgen.proj import Region, twd_to_wgs84

NS = "{http://www.opengis.net/kml/2.2}"
PPK = 315


def _region(sx: int, sy: int) -> Region:
    return Region(250000.0, 2700000.0, 250000 + sx * 1000, 2700000 - sy * 1000, datum="TWD67")


def _write(tmp_path, sx: int, sy: int):
    reg = _region(sx, sy)
    img = np.full((round(sy * PPK), round(sx * PPK), 3), 120, dtype=np.uint8)
    out = tmp_path / f"{sx}x{sy}.tag.kmz"
    write_kmz(img, reg, PPK, out, doc_title="test")
    with zipfile.ZipFile(out) as zf:
        names = zf.namelist()
        doc = zf.read("doc.kml").decode("utf-8")
    return out, reg, names, doc


def _overlays(doc: str):
    root = ET.fromstring(doc)
    return root, root.findall(f".//{NS}GroundOverlay")


def _union_bounds(overlays) -> tuple[float, float, float, float]:
    boxes = [o.find(f"{NS}LatLonBox") for o in overlays]
    return (
        min(float(b.find(f"{NS}west").text) for b in boxes),
        min(float(b.find(f"{NS}south").text) for b in boxes),
        max(float(b.find(f"{NS}east").text) for b in boxes),
        max(float(b.find(f"{NS}north").text) for b in boxes),
    )


def test_doc_kml_is_flat_and_parses(tmp_path):
    """doc.kml must contain all overlays inline — no NetworkLink, no per-tile kml."""
    _, _, names, doc = _write(tmp_path, 3, 4)

    root, overlays = _overlays(doc)
    assert root.tag == f"{NS}kml"
    assert len(overlays) == 2  # 3x4 km -> 3x3 full tile + 3x1 strip
    assert not list(root.iter(f"{NS}NetworkLink"))

    kml_files = [n for n in names if n.endswith(".kml")]
    assert kml_files == ["doc.kml"]


def test_overlay_hrefs_exist_in_zip(tmp_path):
    _, _, names, doc = _write(tmp_path, 9, 8)
    _, overlays = _overlays(doc)
    hrefs = [o.find(f"{NS}Icon/{NS}href").text for o in overlays]
    assert hrefs
    assert all(h in names for h in hrefs)


def test_tile_grid_matches_php_formula(tmp_path):
    """Tile count is ceil(sx/3) x ceil(sy/3), like the PHP makekml loop."""
    for sx, sy in [(1, 1), (3, 4), (7, 10), (9, 7), (9, 8), (9, 9), (12, 6)]:
        _, _, names, doc = _write(tmp_path, sx, sy)
        _, overlays = _overlays(doc)

        cols = math.ceil(sx / TILE_KM)
        rows = math.ceil(sy / TILE_KM)
        assert len(overlays) == cols * rows, (sx, sy)

        expected = {f"3km-H{c}-V{r}.jpg" for c in range(1, cols + 1) for r in range(1, rows + 1)}
        assert {n for n in names if n.endswith(".jpg")} == expected


def test_3x4_region_covers_full_height(tmp_path):
    """The reported case: region 3x4 km must yield a second (3x1 km) tile row."""
    _, reg, _, doc = _write(tmp_path, 3, 4)
    _, overlays = _overlays(doc)
    assert {o.find(f"{NS}name").text for o in overlays} == {"3km-H1-V1", "3km-H1-V2"}

    west, south, east, north = _union_bounds(overlays)
    nw = twd_to_wgs84(reg.x0, reg.y0, reg.crs)
    se = twd_to_wgs84(reg.x1, reg.y1, reg.crs)
    # Union must span the whole 3 x 4 km region (tolerance ~1e-4 deg).
    assert abs(west - nw[0]) < 1e-4
    assert abs(east - se[0]) < 1e-4
    assert abs(north - nw[1]) < 1e-4
    assert abs(south - se[1]) < 1e-4


def test_overlays_tile_without_gaps(tmp_path):
    """Adjacent tiles share an edge (no gap beyond ~1 m of projection skew).

    Each tile's north edge is computed at its own left corner while the tile
    above reports its south edge at the right corner, so a few metres of
    skew is inherent to the LatLonBox corner convention — a missing row
    would instead leave a ~3 km (0.027 deg) gap.
    """
    _, _, _, doc = _write(tmp_path, 9, 8)
    _, overlays = _overlays(doc)

    by_name = {o.find(f"{NS}name").text: o for o in overlays}
    for c in range(1, 4):
        top = by_name[f"3km-H{c}-V1"].find(f"{NS}LatLonBox")
        mid = by_name[f"3km-H{c}-V2"].find(f"{NS}LatLonBox")
        bot = by_name[f"3km-H{c}-V3"].find(f"{NS}LatLonBox")
        assert abs(float(top.find(f"{NS}south").text) - float(mid.find(f"{NS}north").text)) < 5e-5
        assert abs(float(mid.find(f"{NS}south").text) - float(bot.find(f"{NS}north").text)) < 5e-5


def test_print_3x4_vs_kmz_3x3_is_by_design():
    """A4 dim 2x3 prints a 9x8 km region as 3x4 pages, but KMZ tiles are a
    fixed 3 km grid: 3x3 tiles covering 9x9 km (a superset of the region).
    Nothing is dropped — page dim and KMZ tile size are independent.
    """
    assert kmz_grid(round(9 * PPK), round(8 * PPK), PPK) == (3, 3)
