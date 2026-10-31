"""Regenerate the tiny fixture PDFs used by the tests.

Run with ``uv run python tests/fixtures/make_fixtures.py``. The outputs are committed, so
this only needs to run when a fixture must change.

- ``text_layer.pdf``: two pages with a real text layer (a heading and a paragraph each).
- ``image_only.pdf``: one page that is a single raster image of text and has no text
  layer, so it looks scanned to the text-layer pre-check.
"""

import time
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

FIXTURES_DIR = Path(__file__).resolve().parent
PAGE_WIDTH, PAGE_HEIGHT = 612, 792  # US Letter in PDF points.

TEXT_PAGES = [
    ("1 Introduction", "Course material parser fixture page one."),
    ("2 Methods", "Course material parser fixture page two."),
]


def _content_stream(heading: str, body: str) -> bytes:
    return (
        f"BT /F1 24 Tf 72 700 Td ({heading}) Tj ET\nBT /F1 12 Tf 72 660 Td ({body}) Tj ET\n"
    ).encode("latin-1")


def write_text_layer_pdf(path: Path) -> None:
    """Write a minimal multi-page PDF whose pages carry a Helvetica text layer."""
    page_count = len(TEXT_PAGES)
    # Object numbers: 1 catalog, 2 pages, 3 font, then (page, content) pairs.
    page_ids = [4 + 2 * i for i in range(page_count)]
    objects: dict[int, bytes] = {
        1: b"<< /Type /Catalog /Pages 2 0 R >>",
        2: (
            "<< /Type /Pages /Kids [{}] /Count {} >>".format(
                " ".join(f"{n} 0 R" for n in page_ids), page_count
            )
        ).encode(),
        3: b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    }
    for page_id, (heading, body) in zip(page_ids, TEXT_PAGES, strict=True):
        stream = _content_stream(heading, body)
        objects[page_id] = (
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {PAGE_WIDTH} {PAGE_HEIGHT}] "
            f"/Resources << /Font << /F1 3 0 R >> >> /Contents {page_id + 1} 0 R >>"
        ).encode()
        objects[page_id + 1] = (
            f"<< /Length {len(stream)} >>\nstream\n".encode() + stream + b"endstream"
        )

    out = bytearray(b"%PDF-1.4\n")
    offsets = {}
    for number in sorted(objects):
        offsets[number] = len(out)
        out += f"{number} 0 obj\n".encode() + objects[number] + b"\nendobj\n"
    xref_offset = len(out)
    size = max(objects) + 1
    out += f"xref\n0 {size}\n0000000000 65535 f \n".encode()
    for number in range(1, size):
        out += f"{offsets[number]:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {size} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF\n".encode()
    path.write_bytes(bytes(out))


def write_image_only_pdf(path: Path) -> None:
    """Write a one-page PDF that is only a grayscale raster image of some text."""
    dpi = 100
    scale = dpi / 72
    image = Image.new("L", (round(PAGE_WIDTH * scale), round(PAGE_HEIGHT * scale)), 255)
    draw = ImageDraw.Draw(image)
    draw.text((100, 100), "Scanned fixture page", fill=0, font=ImageFont.load_default(40))
    draw.text((100, 170), "This page has no text layer.", fill=0, font=ImageFont.load_default(24))
    # A fixed timestamp keeps regeneration byte-identical, so unchanged fixtures never show diffs.
    fixed_date = time.gmtime(0)
    image.save(path, "PDF", resolution=dpi, creationDate=fixed_date, modDate=fixed_date)


if __name__ == "__main__":
    write_text_layer_pdf(FIXTURES_DIR / "text_layer.pdf")
    write_image_only_pdf(FIXTURES_DIR / "image_only.pdf")
