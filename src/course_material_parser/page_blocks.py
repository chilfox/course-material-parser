"""Split stored ``<page N>``-marked Markdown into per-page blocks and join them back.

The reader uses this instead of ``markdown_writer`` because the writer imports Docling and
the reader must not. A block is a ``<page N>`` marker line plus the content up to the next
marker, so a page with no content is a bare marker.
"""

import re

_MARKER = re.compile(r"^<page (\d+)>$", re.MULTILINE)
_SEPARATOR = "\n\n"


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
