"""Tests for CJK font discovery and ``--font-path`` plumbing."""

from __future__ import annotations

import numpy as np
import pytest

from mapgen import grinder
from mapgen.cli import build_parser


def _system_font_path() -> str:
    """An existing CJK font on this machine (or skip the test)."""
    font = grinder._default_font(26)
    path = getattr(font, "path", None)
    if not path:
        pytest.skip("no CJK font on this machine")
    return path


def test_bundled_font_is_used_by_default():
    font = grinder._default_font(26)
    assert font.path == grinder._bundled_font_path()


def test_bundled_font_renders_cjk():
    gpx = grinder._default_font(26)
    # FreeTypeFont exposes .getbbox(); rendering glyphs must not raise.
    assert gpx.getbbox("路線甲") is not None


def test_default_font_falls_back_to_system_cjk(monkeypatch):
    from PIL.ImageFont import FreeTypeFont

    monkeypatch.setattr(grinder, "_bundled_font_path", lambda: None)
    font = grinder._default_font(26)
    assert isinstance(font, FreeTypeFont)


def test_default_font_uses_explicit_path():
    path = _system_font_path()
    font = grinder._default_font(26, font_path=path)
    assert font.path == path


def test_default_font_missing_path_raises():
    with pytest.raises(ValueError, match="does not exist"):
        grinder._default_font(26, font_path="/nope/missing.ttf")


def test_default_font_raises_when_no_cjk_font(monkeypatch):
    monkeypatch.setattr(grinder, "_bundled_font_path", lambda: None)
    monkeypatch.setattr(grinder, "_candidate_fonts", lambda: [])
    monkeypatch.setattr(grinder, "_fc_match_font", lambda: None)
    monkeypatch.setattr(grinder, "_scan_fonts", lambda max_files=256: None)
    with pytest.raises(RuntimeError, match="--font-path"):
        grinder._default_font(26)


def test_make_parser_exposes_font_path():
    args = build_parser().parse_args(["make", "--font-path", "x.ttf"])
    assert args.font_path == "x.ttf"


def test_font_path_threads_through_renderers():
    path = _system_font_path()

    from pathlib import Path

    from mapgen.gpx2svg import parse_gpx, render_overlay_to_image
    from mapgen.grinder import composite_logo, tag_coordinates
    from mapgen.proj import Region
    from mapgen.splitter import make_simage

    base = np.full((100, 100, 3), 255, np.uint8)
    region = Region(236000, 2578000, 239000, 2575000, datum="TWD67")

    logo = composite_logo(base, "TWD67\n魯地圖", font_path=path)
    assert logo.shape[:2] == base.shape[:2]
    assert logo.shape[2] == 4
    diff = np.abs(logo[..., :3].astype(int) - 255).sum(axis=2)
    assert np.count_nonzero(diff) > 0, "logo text not drawn"

    tags = tag_coordinates(base, region, px_per_km=33.3, font_path=path)
    assert tags.shape[:2] == base.shape[:2]
    assert tags.shape[2] == 4

    page = make_simage(
        base,
        px_w=100,
        px_h=100,
        tiles_w=5,
        tiles_h=7,
        px_per_km=20.0,
        grid_info={"row": 0, "col": 0, "total_cols": 2, "total_rows": 2},
        font_path=path,
    )
    assert page.shape == (100, 100, 4)

    gpx = Path("/tmp/opencode_font_test.gpx")
    gpx.write_text(
        '<?xml version="1.0"?><gpx version="1.1"><trk><name>測試路線</name>'
        "<trkseg><trkpt lat='24.78' lon='121.01'><ele>1</ele></trkpt>"
        "<trkpt lat='24.79' lon='121.02'><ele>2</ele></trkpt></trkseg></trk>"
        "<wpt lat='24.785' lon='121.015'><name>甲</name></wpt></gpx>",
        encoding="utf-8",
    )
    ov = parse_gpx(
        str(gpx),
        region_px=(200, 200),
        region=region,
        label_trk=1,
        label_wpt=3,
    )
    out = render_overlay_to_image(ov, 200, 200, draw_labels=True, font_path=path)
    assert out.shape == (200, 200, 4)
