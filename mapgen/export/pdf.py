"""PDF export: convert page PNGs to a single multi-page PDF.

Replaces the PHP pipeline of `img2pdf` (single pages) + `gs` (merge).
This uses the `img2pdf` library for lossless PNG->PDF, then `pypdf` to
merge the single-page PDFs and (optionally) add bookmarks.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Sequence

import img2pdf
from pypdf import PdfReader, PdfWriter

logger = logging.getLogger(__name__)


# Paper page sizes in PostScript points (72pt/inch).
PAPER_SIZES_PT = {
    "A4": (595.28, 841.89),
    "A3": (841.89, 1190.55),
}


def pages_to_pdf(
    page_paths: Sequence[str | Path],
    out_path: str | Path,
    title: str = "我的地圖",
    author: str = "twmap-gen",
    subject: str = "",
    keywords: str = "",
    paper: str = "A4",
) -> Path:
    """Merge a set of page image files into a single PDF.

    Uses img2pdf to convert each PNG page to a single-page PDF (lossless,
    fitting the chosen paper, shrink-only), then pypdf to concatenate them.
    ``paper`` is ``"A4"`` or ``"A3"``; each page matches the image's own
    orientation (portrait/landscape) so landscape pages keep their layout
    instead of being squeezed onto a portrait page.
    """
    page_paths = [Path(p) for p in page_paths]
    out = Path(out_path)

    try:
        paper_pt = PAPER_SIZES_PT[paper]
    except KeyError:
        raise ValueError(
            f"Unknown paper size: {paper!r}. Known sizes: {sorted(PAPER_SIZES_PT)}"
        ) from None
    portrait_pt = paper_pt
    landscape_pt = (paper_pt[1], paper_pt[0])

    # Convert each page to a single-page PDF
    single_pdfs: list[Path] = []
    for i, p in enumerate(page_paths):
        from PIL import Image

        with Image.open(p) as im:
            w, h = im.size
        pagesize = portrait_pt if w <= h else landscape_pt
        pdf_layout = img2pdf.get_layout_fun(
            pagesize=pagesize,
            fit=img2pdf.FitMode.shrink,
            auto_orient=True,
        )
        sp = out.with_name(f"{out.stem}_page{i}.pdf")
        with open(p, "rb") as f, open(sp, "wb") as g:
            g.write(img2pdf.convert(f, layout_fun=pdf_layout))
        single_pdfs.append(sp)

    # Merge
    writer = PdfWriter()
    for sp in single_pdfs:
        reader = PdfReader(sp)
        for page in reader.pages:
            writer.add_page(page)
    writer.add_metadata(
        {
            "/Title": title,
            "/Author": author,
            "/Subject": subject,
            "/Keywords": keywords,
        }
    )
    with open(out, "wb") as f:
        writer.write(f)

    # Clean up single page PDFs
    for sp in single_pdfs:
        try:
            sp.unlink()
        except OSError:
            pass

    logger.info("Wrote %s (%d pages)", out, len(page_paths))
    return out


__all__ = ["PAPER_SIZES_PT", "pages_to_pdf"]
