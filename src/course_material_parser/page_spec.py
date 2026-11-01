"""Page SPEC parsing shared by the CLIs: ``28``, ``15-30``, ``3,7,15-18``.

Pages are physical source-PDF pages counted from 1. Printed page labels are never accepted.
"""

import re

from course_material_parser.cli_output import CliError

PAGES_HELP = "source-PDF pages, e.g. 28, 15-30, or 3,7,15-18"
"""The ``--pages`` help text, so every CLI describes SPEC the same way."""

_PART = re.compile(r"(\d+)(?:-(\d+))?")


def parse_pages(spec: str, *, material_id: str, page_count: int) -> list[int]:
    """Return the pages ``spec`` selects, in the order it names them.

    Args:
        spec: Comma-separated pages and inclusive ``start-end`` ranges.
        material_id: The material the pages belong to, named in error messages.
        page_count: The material's number of source pages.

    Raises:
        CliError: ``invalid_request`` when ``spec`` is malformed, a range is reversed,
            or a page lies outside ``1..page_count``.
    """
    pages: list[int] = []
    for part in spec.split(","):
        match = _PART.fullmatch(part.strip())
        if match is None:
            raise CliError(
                "invalid_request",
                f"malformed --pages '{spec}': use pages and ranges like 28, 15-30, or 3,7,15-18",
            )
        start = int(match.group(1))
        end = int(match.group(2) or start)
        if end < start:
            raise CliError(
                "invalid_request", f"malformed --pages '{spec}': range {start}-{end} is reversed"
            )
        pages.extend(range(start, end + 1))
    if any(page < 1 or page > page_count for page in pages):
        raise CliError(
            "invalid_request",
            f"pages out of range: {material_id} has pages 1-{page_count}",
        )
    return pages
