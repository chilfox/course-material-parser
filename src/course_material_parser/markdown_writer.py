"""Write ``<page N>``-marked Markdown from a DoclingDocument.

This module owns every Markdown rule of parsed material, so that changing marker syntax
or adding a finer-grained selector stays local to it and its selector type. Content
serialization is delegated to docling-core's public Markdown serializer.
"""

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Literal

from docling_core.transforms.serializer.markdown import MarkdownDocSerializer
from docling_core.types.doc import DocItem, DoclingDocument, NodeItem


@dataclass(frozen=True)
class PdfPages:
    """Select the inclusive range of source pages ``start`` to ``end``, counted from 1."""

    start: int
    end: int
    kind: Literal["pdf_pages"] = "pdf_pages"


Selector = PdfPages
"""Every selector kind ``write_markdown`` accepts. Today only source-page ranges."""


def write_markdown(doc: DoclingDocument, selector: Selector) -> str:
    """Return the selected content of ``doc`` as Markdown with a ``<page N>`` marker per page.

    Every page in the selection gets a marker, even when it has no content. Each top-level
    body item is written under the first source page of its provenance.
    """
    serializer = MarkdownDocSerializer(doc=doc)
    blocks_by_page: dict[int, list[str]] = {
        page: [] for page in range(selector.start, selector.end + 1)
    }
    for item in doc.body.children:
        node = item.resolve(doc)
        page = _first_page(doc, node)
        if page not in blocks_by_page:
            continue
        text = serializer.serialize(item=node).text
        if text:
            blocks_by_page[page].append(text)

    sections = ["\n\n".join([f"<page {page}>", *blocks]) for page, blocks in blocks_by_page.items()]
    return "\n\n".join(sections) + "\n"


def _first_page(doc: DoclingDocument, node: NodeItem) -> int | None:
    """Return the first source page of ``node`` or of its first descendant with provenance."""
    for item in _doc_items(doc, node):
        if item.prov:
            return item.prov[0].page_no
    return None


def _doc_items(doc: DoclingDocument, node: NodeItem) -> Iterator[DocItem]:
    for item, _level in doc.iterate_items(root=node, with_groups=True):
        if isinstance(item, DocItem):
            yield item
