"""The pypdfium2 boundary: facts about source PDFs that don't need Docling."""

import io
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
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
                    image = document[page - 1].render(scale=RENDER_DPI / 72).to_pil()
                except (pypdfium2.PdfiumError, IndexError) as error:
                    raise RenderFailed(f"page {page} could not be rendered ({error})") from None
                png = io.BytesIO()
                image.save(png, "PNG")
                yield page, png.getvalue()
    except CliError as error:
        raise RenderFailed(error.message) from None
    except OSError as error:
        raise RenderFailed(f"can't read {pdf} ({error.strerror})") from None
