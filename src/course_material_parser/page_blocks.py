"""Own the ``<page N>`` marker format of stored Markdown and its per-page blocks.

A block is a ``<page N>`` marker line plus the content up to the next marker, so a page
with no content is a bare marker. Both the writer and the reader build on this module,
so the marker syntax is defined once. It must never import Docling, because the reader
imports it and reader startup must stay fast.
"""

import re

_MARKER = re.compile(r"^<page (\d+)>$", re.MULTILINE)
_SEPARATOR = "\n\n"


def page_marker(page: int) -> str:
    """Return the marker line that starts the block of source page ``page``."""
    return f"<page {page}>"


def page_block(page: int, contents: list[str]) -> str:
    """Return the block of source page ``page`` holding ``contents`` in order."""
    return _SEPARATOR.join([page_marker(page), *contents])


def split_page_blocks(markdown: str) -> dict[int, str]:
    """Return each page's block of ``markdown``, keyed by its source page.

    Blocks keep their marker and lose the blank lines that separated them.
    """
    markers = list(_MARKER.finditer(markdown))
    ends = [marker.start() for marker in markers[1:]] + [len(markdown)]
    return {
        int(marker.group(1)): markdown[marker.start() : end].strip("\n")
        for marker, end in zip(markers, ends, strict=True)
    }


def join_page_blocks(blocks: list[str]) -> str:
    """Return ``blocks`` as one Markdown document, in the given order."""
    return _SEPARATOR.join(blocks) + "\n"
