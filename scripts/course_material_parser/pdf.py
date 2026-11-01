"""The pypdfium2 boundary: facts about source PDFs that don't need Docling."""

from pathlib import Path

import pypdfium2

from course_material_parser.cli_output import CliError


def page_count(pdf: Path) -> int:
    """Return the number of source pages in ``pdf``.

    Raises:
        CliError: ``invalid_request`` when the file can't be opened as a PDF.
    """
    try:
        document = pypdfium2.PdfDocument(pdf)
    except pypdfium2.PdfiumError as error:
        raise CliError("invalid_request", f"not a readable PDF: {pdf} ({error})") from None
    try:
        return len(document)
    finally:
        document.close()
