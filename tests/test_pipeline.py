"""Tests for compositor, grinder, and splitter (Pillow/numpy)."""

import numpy as np
import pytest

from mapgen.compositor import composite_layers
from mapgen.proj import Region
from mapgen.splitter import _pad_to, determine_type, make_simage, split_image


def _rgba(h, w, fill=255):
    img = np.zeros((h, w, 4), dtype=np.uint8)
    img[..., 0] = fill
    img[..., 1] = fill
    img[..., 2] = fill
    img[..., 3] = 255
    return img


def test_multiply_composite_darkens():
    a = _rgba(10, 10, fill=128)
    b = _rgba(10, 10, fill=128)
    out = composite_layers([a, b], mode="multiply")
    # (128*128)/255 ≈ 64
    assert out[0, 0, 0] == pytest.approx(64, abs=1)


# --------------------------------------------------------------------------
# Paper dimension tables (PHP Splitter parity)
# --------------------------------------------------------------------------


def test_a4_and_a3_share_frontend_dim_names():
    from mapgen.config import PAPER_TYPES

    assert set(PAPER_TYPES["A4"]["dimensions"]) == {
        "5x7",
        "4x6",
        "3x4",
        "2x3",
        "1x2",
    }
    assert set(PAPER_TYPES["A3"]["dimensions"]) == set(
        PAPER_TYPES["A4"]["dimensions"]
    )


def test_a3_dimensions_use_php_splitter_grids():
    from mapgen.config import PAPER_TYPES

    a3 = PAPER_TYPES["A3"]["dimensions"]
    px = (2110, 2984)
    px_l = (2984, 2110)
    # Mirrors the PHP `Splitter` switch: each frontend dim keeps its name and
    # maps to a scaled-up A3 tile grid (7x10, 6x8, 4x6, 3x4, 2x2).
    assert a3["5x7"] == (7, 10, px, px_l)
    assert a3["4x6"] == (6, 8, px, px_l)
    assert a3["3x4"] == (4, 6, px, px_l)
    assert a3["2x3"] == (3, 4, px, px_l)
    assert a3["1x2"] == (2, 2, px, px_l)


def test_multiply_white_is_identity():
    a = _rgba(10, 10, fill=100)
    white = _rgba(10, 10, fill=255)
    out = composite_layers([a, white], mode="multiply")
    assert np.all(out[..., :3] == 100)


def test_multiply_keeps_base_through_transparent_overlay():
    # Transparent overlay pixels often have RGB 0; a raw RGB multiply would
    # blacken the base. IM `composite -compose Multiply` shows the base where
    # the overlay is transparent (NLSC/archival -G layers).
    base = _rgba(10, 10, fill=200)
    overlay = np.zeros((10, 10, 4), dtype=np.uint8)  # fully transparent
    out = composite_layers([base, overlay], mode="multiply")
    assert np.all(out[..., :3] == 200)
    assert np.all(out[..., 3] == 255)


def test_multiply_opaque_overlay_darkens():
    base = _rgba(10, 10, fill=200)
    overlay = _rgba(10, 10, fill=100)
    out = composite_layers([base, overlay], mode="multiply")
    assert out[0, 0, 0] == pytest.approx((200 * 100) / 255, abs=1)


def test_alpha_composite():
    base = _rgba(10, 10, fill=0)  # black base
    overlay = _rgba(10, 10, fill=255)  # white overlay, opaque
    out = composite_layers([base, overlay], mode="alpha")
    # Fully opaque overlay -> white
    assert np.all(out[..., :3] == 255)


def test_unknown_mode_raises():
    a = _rgba(10, 10)
    b = _rgba(10, 10)
    with pytest.raises(ValueError):
        composite_layers([a, b], mode="nonsense")


def test_composite_no_layers_raises():
    with pytest.raises(ValueError):
        composite_layers([])


def test_split_image_pages_cover():
    """Splitting a 2x2 km image at 315px/km into 1x1km pages yields 4 pages.

    Match PHP: page origins step by the full page size (315px), each crop is
    page + overlap (42px) extending right/bottom, and every page -- including
    the partial last row/column -- is padded to the full page canvas (PHP
    `cropimage`), so the 2x2 tiling is four 357x357 pages with the clamped
    content kept at top-left and white elsewhere.
    """
    px = 315
    ov = 42
    img = _rgba(px * 2, px * 2, fill=100)  # 2x2 km, 630x630
    region = Region(300000, 2774000, 302000, 2772000)
    pages = split_image(img, region, px, tiles_w=1, tiles_h=1, overlap_px=ov)
    assert len(pages) == 4
    for page in pages:
        assert page.shape == (px + ov, px + ov, 4)
    # Partial page (1,1): 315x315 content at top-left, white pad right/bottom.
    last = pages[-1]
    assert np.all(last[:px, :px, :3] == 100)
    assert np.all(last[px:, :, :3] == 255)
    assert np.all(last[:, px:, :3] == 255)


def test_split_image_no_overlap():
    """With overlap=0, splitting a 2x2km into 1x1 gives four 315px pages."""
    px = 315
    img = _rgba(px * 2, px * 2)
    region = Region(300000, 2774000, 302000, 2772000)
    pages = split_image(img, region, px, tiles_w=1, tiles_h=1, overlap_px=0)
    assert len(pages) == 4
    for p in pages:
        assert p.shape[0] == px
        assert p.shape[1] == px


def test_pad_to_preserves_content():
    img = _rgba(10, 10, fill=50)
    padded = _pad_to(img, 12, 12)
    assert padded.shape == (12, 12, 4)
    # Top-left content preserved (RGB)
    assert np.all(padded[:10, :10, :3] == 50)
    # Padding is white (255)
    assert np.all(padded[10:, :, :3] == 255)


def test_determine_type_picks_landscape_for_wide_region():
    """A 7km-wide x 5km-tall region with 5x7 pages must print landscape."""
    tw, th, landscape = determine_type(7, 5, 5, 7)
    assert landscape is True
    assert (tw, th) == (7, 5)  # grid rotated to fit one landscape page


def test_determine_type_portrait_for_small_region():
    tw, th, landscape = determine_type(3, 3, 5, 7)
    assert landscape is False
    assert (tw, th) == (5, 7)


# Exact 1:25,000 (40 mm/km) resize ratio for A4/A3 5x7-family layouts.
_540 = 40.0 * 1492 / (210.0 * 315)  # A4 ratio (same for every layout in family)


def test_make_simage_keeps_scale_for_small_map():
    """A region smaller than a page keeps its print scale and lands near the
    top-left of the paper (PHP parity), never floating centered or stretched.

    split_image pads the page to the full page canvas (content top-left +
    white right/bottom); center-placing that padded page pins the 2x2 km map
    to the paper's top-left area at the exact 40mm-per-km layout ratio.
    """
    px = 315
    page = _pad_to(_rgba(2 * px, 2 * px, fill=100), 5 * px + 42, 7 * px + 42)
    out = make_simage(page, 1492, 2110, 5, 7, px)
    assert out.shape == (2110, 1492, 4)
    # Content is the non-white region
    ys, xs = np.where(out[..., :3].min(axis=-1) != 255)
    h = ys.max() - ys.min() + 1
    w = xs.max() - xs.min() + 1
    # 630 * 40mm ratio = 568 (aspect preserved, square)
    assert abs(h - round(630 * _540)) <= 3 and abs(w - round(630 * _540)) <= 3
    # Near the top-left corner, NOT floating on the paper center
    assert xs.min() < 60 and ys.min() < 80
    assert xs.max() < 1492 // 2 and ys.max() < 2110 // 2


def test_make_simage_full_page_same_scale():
    """A full 5x7 page crop must land at the exact 40mm-per-km layout ratio."""
    px = 315
    page = _rgba(7 * px, 5 * px + 42, fill=100)  # full height page + overlap
    out = make_simage(page, 1492, 2110, 5, 7, px)
    ys, xs = np.where(out[..., :3].min(axis=-1) != 255)
    # (5*315+42)*40mm ratio; 7*315*40mm ratio (aspect preserved)
    assert abs((xs.max() - xs.min() + 1) - round(1617 * _540)) <= 3
    assert abs((ys.max() - ys.min() + 1) - round(2205 * _540)) <= 3


def test_make_simage_multi_page_aligns_northwest():
    """Multi-page layouts paste each page at the top-left (PHP NorthWest).

    Partial pages (a small last-column map) must start from the paper's
    corner, so neighboring tiles paste together at the same reference corner
    instead of each floating centered on its own page.
    """
    px = 315
    page = _pad_to(_rgba(3 * px, 2 * px, fill=100), 5 * px + 42, 7 * px + 42)
    out = make_simage(
        page, 1492, 2110, 5, 7, px,
        grid_info={"row": 0, "col": 1, "total_cols": 2, "total_rows": 1},
    )
    mask = out[..., :3].min(axis=-1) != 255
    # Exclude the 56px paste-strip area (the SE junction index lives there)
    ys, xs = np.where(mask[: 2110 - 56, : 1492 - 56])
    # Top-left pinned (NW), not centered; 2x3 km at 40mm ratio = 568x853
    assert xs.min() <= 1 and ys.min() <= 1
    assert abs((xs.max() - xs.min() + 1) - round(630 * _540)) <= 3
    assert abs((ys.max() - ys.min() + 1) - round(945 * _540)) <= 3


@pytest.mark.parametrize(
    "px_w,px_h,paper_mm,tw,th",
    [
        (1492, 2110, (210.0, 297.0), 5, 7),   # A4 5x7 portrait
        (2110, 1492, (297.0, 210.0), 7, 5),   # A4R 7x5 landscape
        (2110, 2984, (297.0, 420.0), 7, 10),  # A3 7x10 portrait
        (2984, 2110, (420.0, 297.0), 10, 7),  # A3R 10x7 landscape
    ],
)
def test_make_simage_exact_40mm_per_km(px_w, px_h, paper_mm, tw, th):
    """Each 5x7-family layout prints exactly 40 mm per 1km grid cell."""
    px = 315
    page = _pad_to(_rgba(th * px, tw * px, fill=100), tw * px + 42, th * px + 42)
    out = make_simage(page, px_w, px_h, tw, th, px)
    ys, xs = np.where(out[..., :3].min(axis=-1) != 255)
    # Content bbox = terrain only (the 42px paste overlap is white here)
    w_px = xs.max() - xs.min() + 1
    h_px = ys.max() - ys.min() + 1
    paper_w_mm, paper_h_mm = paper_mm
    # mm/km = content_px / canvas_px * paper_mm / km_tiles
    mm_per_km_w = w_px / px_w * paper_w_mm / tw
    mm_per_km_h = h_px / px_h * paper_h_mm / th
    assert mm_per_km_w == pytest.approx(40.0, abs=0.1)
    assert mm_per_km_h == pytest.approx(40.0, abs=0.1)


def _dark_page_mask(out):
    return out[..., :3].sum(axis=-1) < 400


def test_single_page_has_no_paste_marks_or_index():
    """A one-page map must be printed bare (no paste markers, no index),
    mirroring PHP `make_simages` early-return for a single page."""
    page = _rgba(7 * 315, 5 * 315 + 42, fill=255)
    out = make_simage(page, 1492, 2110, 5, 7, 315,
                      grid_info={"row": 0, "col": 0, "total_cols": 1, "total_rows": 1})
    assert _dark_page_mask(out).sum() < 100


def test_multi_page_paste_markers_centered_and_index_drawn():
    """Multi-page maps get centered paste markers (bottom/right) plus a
    page-grid index confined to the SE paste-strip junction; markers must not
    appear on the last row/column, and the index must not cover the map."""
    page = _rgba(5 * 315, 5 * 315, fill=255)
    h, w = 2110, 1492

    # First page (row=0, col=0): both markers + index.
    out = make_simage(page, 1492, 2110, 5, 5, 315,
                      grid_info={"row": 0, "col": 0, "total_cols": 3, "total_rows": 2})
    dark = _dark_page_mask(out)
    # Bottom marker: ink near the bottom edge, horizontally centered.
    bottom = dark[h - 56:h - 8]
    xs = np.where(bottom[:, :w - 60].any(axis=0))[0]
    assert abs((xs.min() + xs.max()) / 2 - w / 2) <= 8
    # Right marker: ink near the right edge, vertically centered.
    right = dark[:, w - 56:w - 8]
    ys = np.where(right[:h - 60].any(axis=1))[0]
    assert abs((ys.min() + ys.max()) / 2 - h / 2) <= 8
    # The page-grid index lives fully inside the 48px strip junction
    # (w-56..w-8, h-56..h-8): some dark cell grid there...
    junction = dark[h - 56:h - 8, w - 56:w - 8]
    assert 0.03 < junction.mean() < 0.5
    # ...and NOTHING dark between the junction and the map content edge:
    # the 100m band just inside the strips (h-140..h-60 / w-140..w-60) stays
    # blank on this white page.
    assert dark[h - 140:h - 60, w - 140:w - 60].sum() < 100

    # Last-row page (row=1, col=0): no bottom marker, right marker still there.
    out = make_simage(page, 1492, 2110, 5, 5, 315,
                      grid_info={"row": 1, "col": 0, "total_cols": 3, "total_rows": 2})
    dark = _dark_page_mask(out)
    xs = np.where(dark[h - 56:h - 8, :w - 60].any(axis=0))[0]
    assert len(xs) == 0
    ys = np.where(dark[:, w - 56:w - 8][:h - 60].any(axis=1))[0]
    assert len(ys) > 0


def test_composite_logo_multiline_spacing():
    """A two-line logo must render with a wider-than-old inter-line gap."""
    from mapgen.grinder import composite_logo

    base = np.full((240, 320, 3), 200, np.uint8)
    out = composite_logo(base, "TWD67\n魯地圖", font_size=26)
    dark = out.sum(axis=-1) < 400
    cols = np.where(np.any(dark, axis=0))[0]
    band = dark[:, cols.min():cols.max() + 1]
    hits = band.any(axis=1)
    # Two text bands separated by a white gap of at least 8px (the old
    # `font_size // 8` = 3px gap would fail this).
    gaps = []
    in_white = False
    start = 0
    for i, v in enumerate(hits):
        if not v and not in_white:
            in_white, start = True, i
        elif v and in_white:
            gaps.append(i - start)
            in_white = False
    assert len(gaps) >= 2          # top pad + inter-line gap
    assert gaps[-2] >= 8           # the inter-line gap itself
