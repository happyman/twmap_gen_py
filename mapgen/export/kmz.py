"""KMZ export: Garmin-compatible KML GroundOverlay + cropped tiles in a zip.

Replaces the PHP `GarminKmz` class (zip + per-3km KML overlays).

The tagged PNG is cropped into 3km x 3km tiles, each with a KML
GroundOverlay spanning its WGS84 bounds, then everything is zipped into
the .kmz file.
"""

from __future__ import annotations

import logging
import zipfile
from pathlib import Path
from typing import Sequence

import numpy as np
from PIL import Image

from ..proj import Region, twd_to_wgs84

logger = logging.getLogger(__name__)

TILE_KM = 3  # KMZ tile size in km (matches PHP)


def kml_groundoverlay(
    name: str,
    wgs84_bounds: tuple[float, float, float, float],
    image_file: str,
) -> str:
    """Build a single ``<GroundOverlay>`` fragment for ``doc.kml``."""
    minlon, minlat, maxlon, maxlat = wgs84_bounds
    return f"""    <GroundOverlay>
      <name>{name}</name>
      <Icon>
        <href>{image_file}</href>
      </Icon>
      <LatLonBox>
        <north>{maxlat}</north>
        <south>{minlat}</south>
        <east>{maxlon}</east>
        <west>{minlon}</west>
      </LatLonBox>
    </GroundOverlay>"""


def kmz_grid(img_w: int, img_h: int, px_per_km: float) -> tuple[int, int]:
    """Number of (cols, rows) of ``TILE_KM`` tiles covering an image."""
    tile_px = int(TILE_KM * px_per_km)
    return max(1, -(-img_w // tile_px)), max(1, -(-img_h // tile_px))


def crop_3km_tiles(
    img: np.ndarray,
    region: Region,
    px_per_km: float,
) -> list[tuple[np.ndarray, str, tuple[float, float, float, float]]]:
    """Crop the tagged image into 3km x 3km tiles.

    Returns list of (tile_image, tile_name, wgs84_bounds).
    ``tile_name`` is like "3km-H1-V2" — unique within a map batch.
    """
    tiles: list[tuple[np.ndarray, str, tuple[float, float, float, float]]] = []
    tile_px = int(TILE_KM * px_per_km)
    img_h, img_w = img.shape[:2]

    # How many tiles in each direction
    cols, rows = kmz_grid(img_w, img_h, px_per_km)

    for r in range(rows):
        for c in range(cols):
            x0 = c * tile_px
            y0 = r * tile_px
            x1 = min(x0 + tile_px, img_w)
            y1 = min(y0 + tile_px, img_h)
            tile = img[y0:y1, x0:x1]

            # WGS84 bounds for this tile (from TWD region + pixel offsets)
            # pixel -> TWD meters: x_m = x0 + col_px * 1000/px_per_km
            t_x0 = region.x0 + x0 * 1000.0 / px_per_km
            t_x1 = region.x0 + x1 * 1000.0 / px_per_km
            t_y0 = region.y0 - y0 * 1000.0 / px_per_km
            t_y1 = region.y0 - y1 * 1000.0 / px_per_km

            top_left = twd_to_wgs84(t_x0, t_y0, region.crs)
            bottom_right = twd_to_wgs84(t_x1, t_y1, region.crs)
            bounds = (top_left[0], bottom_right[1], bottom_right[0], top_left[1])

            name = f"3km-H{c+1}-V{r+1}"
            tiles.append((tile, name, bounds))

    return tiles


def write_kmz(
    img: np.ndarray,
    region: Region,
    px_per_km: float,
    out_path: str | Path,
    doc_title: str = "twmap",
) -> Path:
    """Crop the image to 3km tiles, write KML + zipped tiles to a KMZ file."""
    out = Path(out_path)
    tiles = crop_3km_tiles(img, region, px_per_km)
    cols, rows = kmz_grid(img.shape[1], img.shape[0], px_per_km)

    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        overlays = []
        for tile, name, bounds in tiles:
            tile_path = f"{name}.jpg"
            zf.writestr(tile_path, _encode_jpeg(tile))
            overlays.append(kml_groundoverlay(name, bounds, tile_path))

        # One root doc.kml with every GroundOverlay inline. Viewers (Google
        # Earth) and Garmin devices read only doc.kml — a NetworkLink or
        # per-tile KML files would leave most tiles unloaded.
        zf.writestr("doc.kml", _doc_kml(doc_title, overlays))

    logger.info(
        "Wrote %s (%d tiles: %dx%d grid covering %.1fx%.1f km; region %.1fx%.1f km)",
        out,
        len(tiles),
        cols,
        rows,
        cols * TILE_KM,
        rows * TILE_KM,
        region.width_m / 1000.0,
        region.height_m / 1000.0,
    )
    return out


def _encode_jpeg(arr: np.ndarray) -> bytes:
    im = Image.fromarray(arr)
    if im.mode != "RGB":
        im = im.convert("RGB")
    import io

    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=85)
    return buf.getvalue()


def _doc_kml(title: str, overlays: Sequence[str]) -> str:
    """Build the root KML with every tile's GroundOverlay inline.

    Matches the PHP original (``GarminKmz::kml_head/kml_folder``): no
    NetworkLink, no per-tile KML files — Garmin devices and Google Earth
    only process ``doc.kml``.
    """
    entries = "\n".join(overlays)
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document>
    <name>{title}</name>
{entries}
  </Document>
</kml>
"""


__all__ = ["crop_3km_tiles", "write_kmz", "kml_groundoverlay", "kmz_grid"]
