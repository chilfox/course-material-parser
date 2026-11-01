"""The pypdfium2 boundary: facts about source PDFs that don't need Docling."""

import io
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

import pypdfium2

from course_material_parser.cli_output import CliError

RENDER_DPI = 150
"""The one resolution page renders use: legible for slides and textbook pages alike."""


@contextmanager
def opened(pdf: Path) -> Iterator[pypdfium2.PdfDocument]:
    """Open ``pdf`` with pypdfium2 for the duration of the block, then close it.

    Every pypdfium2 operation in this module goes through here, so an unreadable PDF is
    reported the same way everywhere.

    Raises:
        CliError: ``invalid_request`` when the file can't be opened as a PDF.
    """
    try:
        document = pypdfium2.PdfDocument(pdf)
    except pypdfium2.PdfiumError as error:
        raise CliError("invalid_request", f"not a readable PDF: {pdf} ({error})") from None
    try:
        yield document
    finally:
        document.close()


def page_count(pdf: Path) -> int:
    """Return the number of source pages in ``pdf``.

    Raises:
        CliError: ``invalid_request`` when the file can't be opened as a PDF.
    """
    with opened(pdf) as document:
        return len(document)


@dataclass(frozen=True)
class TextLayer:
    """How much of a source PDF carries a text layer, from ``text_layer``."""

    pages: int
    pages_without_text: int

    @property
    def looks_scanned(self) -> bool:
        """Whether more than half the pages have no text layer, the fixed OCR threshold."""
        return self.pages_without_text * 2 > self.pages


def text_layer(pdf: Path) -> TextLayer:
    """Count the pages of ``pdf`` whose text layer holds no characters.

    This is the pre-check that decides whether a PDF looks scanned and needs OCR. It only
    asks pdfium for each page's character count, without extracting text or rendering.

    Raises:
        CliError: ``invalid_request`` when the file can't be opened as a PDF.
    """
    with opened(pdf) as document:
        without_text = 0
        for page in document:
            textpage = page.get_textpage()
            if textpage.count_chars() == 0:
                without_text += 1
            textpage.close()
            page.close()
        return TextLayer(pages=len(document), pages_without_text=without_text)


class RenderFailed(Exception):
    """A page of a PDF could not be rendered; the message says why."""


def render_pngs(pdf: Path, pages: Iterable[int]) -> Iterator[tuple[int, bytes]]:
    """Yield each of ``pages`` (counted from 1) of ``pdf`` as PNG bytes at ``RENDER_DPI``.

    The PDF is opened once and stays open until the iteration ends.

    Raises:
        RenderFailed: when the PDF can't be opened or a page can't be rendered.
    """
    try:
        with opened(pdf) as document:
            for page in pages:
                try:
                    source_page = document[page - 1]
                    image = source_page.render(scale=RENDER_DPI / 72).to_pil()
                    source_page.close()
                except (pypdfium2.PdfiumError, IndexError) as error:
                    raise RenderFailed(f"page {page} could not be rendered ({error})") from None
                png = io.BytesIO()
                image.save(png, "PNG")
                yield page, png.getvalue()
    except CliError as error:
        raise RenderFailed(error.message) from None
    except OSError as error:
        raise RenderFailed(f"can't read {pdf} ({error.strerror})") from None
