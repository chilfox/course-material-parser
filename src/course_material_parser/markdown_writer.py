"""Write ``<page N>``-marked Markdown from a DoclingDocument.

This module decides which content of a document is written, and under which source page.
The ``<page N>`` marker syntax and block layout belong to ``page_blocks``, which the
reader shares. Adding a finer-grained selector stays local to this module and its selector
type. Text, formulas (LaTeX math), and tables (Markdown tables) are delegated to
docling-core's public Markdown serializer; content Docling did not recognize passes
through as emitted. Pictures use an own serializer.
"""

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any, Literal

from docling_core.transforms.serializer.base import (
    BaseDocSerializer,
    BasePictureSerializer,
    SerializationResult,
)
from docling_core.transforms.serializer.common import create_ser_result
from docling_core.transforms.serializer.markdown import MarkdownDocSerializer
from docling_core.types.doc import ContentLayer, DocItem, DoclingDocument, NodeItem, PictureItem

from course_material_parser.page_blocks import join_page_blocks, page_block

_VISUAL_MARKER = "<visual>"


@dataclass(frozen=True)
class PdfPages:
    """Select the inclusive range of source pages ``start`` to ``end``, counted from 1."""

    start: int
    end: int
    kind: Literal["pdf_pages"] = "pdf_pages"


Selector = PdfPages
"""Every selector kind ``write_markdown`` accepts. Today only source-page ranges."""


def write_markdown(doc: DoclingDocument, selector: Selector) -> str:
    """Return the selected content of ``doc`` as Markdown with ``<page N>`` markers.

    Every page in the selection gets a marker, even when it has no content. A top-level
    body item is selected when its first source page falls in the selection, and is
    written whole under that page, even when it runs past the selection end. An item
    that starts before the selection and only continues into it is left out. Furniture
    (running headers and footers) is never written.
    """
    serializer = MarkdownDocSerializer(doc=doc, picture_serializer=_VisualSerializer())
    selected = range(selector.start, selector.end + 1)
    blocks_by_page: dict[int, list[str]] = {page: [] for page in selected}
    for child in doc.body.children:
        node = child.resolve(doc)
        if node.content_layer is not ContentLayer.BODY:
            continue
        pages = _pages(doc, node)
        if not pages or min(pages) not in selected:
            continue
        text = serializer.serialize(item=node).text
        if text:
            # Selecting by first page keeps every marker inside the approved pages and
            # writes each spanning item once, whole, so adjacent selections never
            # repeat or cut an item and a marker always means "content starts here".
            blocks_by_page[min(pages)].append(text)

    return join_page_blocks(
        [page_block(page, blocks_by_page[page]) for page in sorted(blocks_by_page)]
    )


def _pages(doc: DoclingDocument, node: NodeItem) -> set[int]:
    """Return every source page in the provenance of ``node`` and its descendants."""
    return {prov.page_no for item in _doc_items(doc, node) for prov in item.prov}


def _doc_items(doc: DoclingDocument, node: NodeItem) -> Iterator[DocItem]:
    for item, _level in doc.iterate_items(root=node, with_groups=True):
        if isinstance(item, DocItem):
            yield item


class _VisualSerializer(BasePictureSerializer):
    """Write a picture as ``<visual>`` followed by its detected caption, if any.

    Docling's own image placeholder is not page-aware and says nothing about the
    picture, so a reader could not tell which source page to render.
    """

    def serialize(
        self,
        *,
        item: PictureItem,
        doc_serializer: BaseDocSerializer,
        doc: DoclingDocument,
        **kwargs: Any,
    ) -> SerializationResult:
        """Return the visual marker line for ``item``."""
        caption = item.caption_text(doc).strip()
        text = f"{_VISUAL_MARKER} {caption}" if caption else _VISUAL_MARKER
        return create_ser_result(text=text, span_source=item)
