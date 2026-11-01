"""The pypdfium2 boundary: facts about source PDFs that don't need Docling."""

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pypdfium2

from course_material_parser.cli_output import CliError


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
