"""Describe a stored textbook extraction for inspection, without writing any Markdown.

The structure index lists detected headings so an agent can plan a split without reading
the whole book; page content lists the items of selected source pages with their types,
references, and pages. Both are evidence of what Docling detected, not an authoritative
outline. Furniture (running headers and footers) is left out, as it is from every unit.
"""

import hashlib
from collections.abc import Iterator
from pathlib import Path

from docling_core.types.doc import (
    ContentLayer,
    DocItem,
    DoclingDocument,
    FloatingItem,
    SectionHeaderItem,
    TableItem,
    TextItem,
    TitleItem,
)

from course_material_parser.provenance import source_pages


def extraction_id(path: Path) -> str:
    """Return the identity of the stored extraction at ``path``: a hash of its bytes.

    A content hash ties a split plan to exactly the extraction it was written for, so a
    plan for another book (or another parse of a different PDF) never matches.
    """
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def headings(doc: DoclingDocument) -> list[dict]:
    """Return the detected title and section headings of ``doc`` in reading order.

    Each is ``{page, text}`` plus ``level`` when Docling detected one (section headings
    have a level; a title has none). ``page`` is the heading's first source page.
    """
    found = []
    for item in _body_items(doc):
        if isinstance(item, TitleItem):
            found.append({"page": _first_page(item), "text": item.text})
        elif isinstance(item, SectionHeaderItem):
            found.append({"page": _first_page(item), "level": item.level, "text": item.text})
    return found


def page_items(doc: DoclingDocument, pages: set[int]) -> list[dict]:
    """Return every body item of ``doc`` on any of ``pages``, in reading order.

    Each is ``{ref, type, pages}``: the item's JSON reference, Docling label, and every
    source page it lies on, so an item spanning a boundary shows both sides. Text items
    add ``text``, and a table adds its Markdown as ``text``. A picture or table with
    captions adds ``captions``, the refs of its caption items, which are listed on their
    own rather than repeated.
    """
    found = []
    for item in _body_items(doc):
        item_pages = sorted(source_pages(item))
        if not pages.intersection(item_pages):
            continue
        entry: dict = {"ref": item.self_ref, "type": str(item.label), "pages": item_pages}
        if isinstance(item, TableItem):
            entry["text"] = item.export_to_markdown(doc)
        elif isinstance(item, TextItem):
            entry["text"] = item.text
        if isinstance(item, FloatingItem) and item.captions:
            entry["captions"] = [caption.cref for caption in item.captions]
        found.append(entry)
    return found


def _body_items(doc: DoclingDocument) -> Iterator[DocItem]:
    for item, _level in doc.iterate_items(included_content_layers={ContentLayer.BODY}):
        if isinstance(item, DocItem):
            yield item


def _first_page(item: DocItem) -> int:
    return min(source_pages(item))
