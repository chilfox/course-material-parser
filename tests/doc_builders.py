"""Build small DoclingDocuments through the docling-core API for tests."""

from docling_core.types.doc import (
    BoundingBox,
    ContentLayer,
    DocItemLabel,
    DoclingDocument,
    ProvenanceItem,
    Size,
)


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


def blank_document(page_count: int) -> DoclingDocument:
    """Return an empty document with ``page_count`` source pages."""
    doc = DoclingDocument(name="doc")
    for page_no in range(1, page_count + 1):
        doc.add_page(page_no=page_no, size=Size(width=612, height=792))
    return doc


def textbook() -> DoclingDocument:
    """Return a two-page textbook excerpt matching the two-page text-layer fixture PDF.

    Page 1 holds the title, chapter 1, and section 1.1, whose paragraph runs onto page 2.
    Page 2 holds section 1.2 with a formula and a captioned picture. Both pages have a
    running header.
    """
    doc = blank_document(page_count=2)
    for page_no in (1, 2):
        doc.add_text(
            label=DocItemLabel.PAGE_HEADER,
            text="Pattern Recognition",
            prov=prov(page_no),
            content_layer=ContentLayer.FURNITURE,
        )
    doc.add_title(text="Pattern Recognition", prov=prov(1))
    doc.add_heading(text="1 Introduction", level=1, prov=prov(1))
    doc.add_text(label=DocItemLabel.TEXT, text="Chapter introduction.", prov=prov(1))
    doc.add_heading(text="1.1 Curve Fitting", level=2, prov=prov(1))
    spanning = doc.add_text(label=DocItemLabel.TEXT, text="A paragraph across pages.", prov=prov(1))
    spanning.prov.append(prov(2))
    doc.add_heading(text="1.2 Probability", level=2, prov=prov(2))
    doc.add_formula(text="p(x) = 1", prov=prov(2))
    caption = doc.add_text(label=DocItemLabel.CAPTION, text="Figure 1.1: A curve", prov=prov(2))
    doc.add_picture(caption=caption, prov=prov(2))
    return doc
