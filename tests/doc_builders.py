"""Build small DoclingDocuments through the docling-core API for tests."""

from docling_core.types.doc import BoundingBox, DocItemLabel, DoclingDocument, ProvenanceItem, Size


def prov(page: int) -> ProvenanceItem:
    """Return a provenance entry on ``page`` with an arbitrary box."""
    return ProvenanceItem(page_no=page, bbox=BoundingBox(l=72, t=100, r=500, b=80), charspan=(0, 0))


def slide_deck(pages: dict[int, list[str]], page_count: int) -> DoclingDocument:
    """Return a document with one heading per listed page followed by its paragraphs.

    ``pages`` maps a page number to its texts; the first text is a heading.
    """
    doc = DoclingDocument(name="deck")
    for page_no in range(1, page_count + 1):
        doc.add_page(page_no=page_no, size=Size(width=612, height=792))
    for page_no, texts in pages.items():
        heading, *paragraphs = texts
        doc.add_heading(text=heading, prov=prov(page_no))
        for paragraph in paragraphs:
            doc.add_text(label=DocItemLabel.TEXT, text=paragraph, prov=prov(page_no))
    return doc
