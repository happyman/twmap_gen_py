"""Tests for PDF export (page paper size / orientation)."""

import numpy as np
import pytest
from PIL import Image
from pypdf import PdfReader

from mapgen.export.pdf import pages_to_pdf


def _page_png(path, w, h):
    img = np.full((h, w, 3), 200, np.uint8)
    Image.fromarray(img).save(path)


def _page_sizes(pdf_path):
    reader = PdfReader(pdf_path)
    return [((p.mediabox.width), (p.mediabox.height)) for p in reader.pages]


def test_a4_pdf_pages_stay_a4(tmp_path):
    png = tmp_path / "p.png"
    _page_png(png, 1492, 2110)  # A4 portrait px
    out = tmp_path / "out.pdf"
    pages_to_pdf([png], out, paper="A4")
    assert _page_sizes(out) == [(595.28, 841.89)]


def test_a3_pdf_pages_are_a3(tmp_path):
    """--a3 must produce A3-sized PDF pages (841.89 x 1190.55 pt), not A4."""
    png = tmp_path / "p.png"
    _page_png(png, 2110, 2984)  # A3 portrait px
    out = tmp_path / "out.pdf"
    pages_to_pdf([png], out, paper="A3")
    assert _page_sizes(out) == [(841.89, 1190.55)]


def test_a3_landscape_page_keeps_landscape(tmp_path):
    """A landscape A3 page image must yield a landscape (rotated) PDF page."""
    png = tmp_path / "p.png"
    _page_png(png, 2984, 2110)  # A3 landscape px
    out = tmp_path / "out.pdf"
    pages_to_pdf([png], out, paper="A3")
    assert _page_sizes(out) == [(1190.55, 841.89)]


def test_unknown_paper_raises(tmp_path):
    png = tmp_path / "p.png"
    _page_png(png, 100, 100)
    with pytest.raises(ValueError, match="Unknown paper size"):
        pages_to_pdf([png], tmp_path / "out.pdf", paper="A2")
