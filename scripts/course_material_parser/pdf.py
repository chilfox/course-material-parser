"""The pypdfium2 boundary: facts about source PDFs that don't need Docling.

Every failure is a ``PdfError``, so callers decide once which CLI error it becomes.
"""

import io
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

import pypdfium2

_RENDER_DPI = 150
"""The one resolution page renders use: legible for slides and textbook pages alike."""


class PdfError(Exception):
    """A source PDF can't be read, or one of its pages can't be rendered.

    The message names the file or page and says why.
    """


@contextmanager
def _opened(pdf: Path) -> Iterator[pypdfium2.PdfDocument]:
    """Open ``pdf`` with pypdfium2 for the duration of the block, then close it.

    Every pypdfium2 operation in this module goes through here, so an unreadable PDF is
    reported the same way everywhere.

    Raises:
        PdfError: when the file can't be read or opened as a PDF.
    """
    try:
        document = pypdfium2.PdfDocument(pdf)
    except pypdfium2.PdfiumError as error:
        raise PdfError(f"not a readable PDF: {pdf} ({error})") from None
    except FileNotFoundError:
        raise PdfError(f"{pdf} not found") from None
    except OSError as error:
        # pypdfium2 raises some OSErrors with only the path, so strerror can be None.
        raise PdfError(f"can't read {pdf} ({error.strerror or type(error).__name__})") from None
    try:
        yield document
    finally:
        document.close()


def page_count(pdf: Path) -> int:
    """Return the number of source pages in ``pdf``.

    Raises:
        PdfError: when the file can't be read or opened as a PDF.
    """
    with _opened(pdf) as document:
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
        PdfError: when the file can't be read or opened as a PDF.
    """
    with _opened(pdf) as document:
        without_text = 0
        for page in document:
            try:
                textpage = page.get_textpage()
                try:
                    if textpage.count_chars() == 0:
                        without_text += 1
                finally:
                    textpage.close()
            finally:
                page.close()
        return TextLayer(pages=len(document), pages_without_text=without_text)


def render_pngs(pdf: Path, pages: Iterable[int]) -> Iterator[tuple[int, bytes]]:
    """Yield each of ``pages`` (counted from 1) of ``pdf`` as PNG bytes.

    The PDF is opened once and stays open until the iteration ends.

    Raises:
        PdfError: when the PDF can't be read or opened, or a page can't be rendered.
    """
    with _opened(pdf) as document:
        for page in pages:
            yield page, _render_png(document, page)


def _render_png(document: pypdfium2.PdfDocument, page: int) -> bytes:
    try:
        source_page = document[page - 1]
    except (pypdfium2.PdfiumError, IndexError) as error:
        raise PdfError(f"page {page} could not be rendered ({error})") from None
    try:
        image = source_page.render(scale=_RENDER_DPI / 72).to_pil()
    except pypdfium2.PdfiumError as error:
        raise PdfError(f"page {page} could not be rendered ({error})") from None
    finally:
        source_page.close()
    png = io.BytesIO()
    image.save(png, "PNG")
    return png.getvalue()
