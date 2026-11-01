"""markdown_writer seam: DoclingDocument plus selector in, page-marked Markdown out."""

from docling_core.types.doc import DocItemLabel, TableCell, TableData
from docling_core.types.doc.document import ContentLayer

from course_material_parser.markdown_writer import PdfPages, write_markdown
from doc_builders import blank_document, prov, slide_deck


def test_each_source_page_gets_a_page_marker_above_its_content():
    doc = slide_deck(
        {1: ["Introduction", "First slide body."], 3: ["Methods", "Third slide body."]},
        page_count=3,
    )

    markdown = write_markdown(doc, PdfPages(start=1, end=3))

    assert markdown == (
        "<page 1>\n\n"
        "## Introduction\n\n"
        "First slide body.\n\n"
        "<page 2>\n\n"
        "<page 3>\n\n"
        "## Methods\n\n"
        "Third slide body.\n"
    )


def test_only_pages_inside_the_selection_are_written():
    doc = slide_deck({1: ["One"], 2: ["Two"], 3: ["Three"]}, page_count=3)

    markdown = write_markdown(doc, PdfPages(start=2, end=2))

    assert markdown == "<page 2>\n\n## Two\n"


def test_a_picture_with_a_caption_is_written_as_visual_followed_by_the_caption():
    doc = blank_document(page_count=1)
    caption = doc.add_text(
        label=DocItemLabel.CAPTION, text="Figure 2.3: Gradient descent path", prov=prov(1)
    )
    doc.add_picture(caption=caption, prov=prov(1))

    markdown = write_markdown(doc, PdfPages(start=1, end=1))

    assert markdown == "<page 1>\n\n<visual> Figure 2.3: Gradient descent path\n"


def test_a_picture_without_a_caption_is_written_as_a_bare_visual_marker():
    doc = blank_document(page_count=1)
    doc.add_text(label=DocItemLabel.TEXT, text="Before.", prov=prov(1))
    doc.add_picture(prov=prov(1))
    doc.add_text(label=DocItemLabel.TEXT, text="After.", prov=prov(1))

    markdown = write_markdown(doc, PdfPages(start=1, end=1))

    assert markdown == "<page 1>\n\nBefore.\n\n<visual>\n\nAfter.\n"


def test_running_headers_and_footers_are_excluded():
    doc = blank_document(page_count=1)
    doc.add_text(
        label=DocItemLabel.PAGE_HEADER,
        text="Chapter 1 Introduction",
        prov=prov(1),
        content_layer=ContentLayer.FURNITURE,
    )
    doc.add_text(label=DocItemLabel.TEXT, text="Body text.", prov=prov(1))
    doc.add_text(
        label=DocItemLabel.PAGE_FOOTER,
        text="17",
        prov=prov(1),
        content_layer=ContentLayer.FURNITURE,
    )

    markdown = write_markdown(doc, PdfPages(start=1, end=1))

    assert markdown == "<page 1>\n\nBody text.\n"


def _spanning_paragraph_doc():
    doc = blank_document(page_count=3)
    doc.add_text(label=DocItemLabel.TEXT, text="Page one text.", prov=prov(1))
    spanning = doc.add_text(label=DocItemLabel.TEXT, text="A paragraph across pages.", prov=prov(1))
    spanning.prov.append(prov(2))
    doc.add_text(label=DocItemLabel.TEXT, text="Page two text.", prov=prov(2))
    doc.add_text(label=DocItemLabel.TEXT, text="Page three text.", prov=prov(3))
    return doc


def test_a_spanning_item_is_written_once_under_its_first_page():
    markdown = write_markdown(_spanning_paragraph_doc(), PdfPages(start=1, end=2))

    assert markdown == (
        "<page 1>\n\nPage one text.\n\nA paragraph across pages.\n\n<page 2>\n\nPage two text.\n"
    )


def test_a_spanning_item_is_excluded_when_it_only_continues_into_the_selection():
    markdown = write_markdown(_spanning_paragraph_doc(), PdfPages(start=2, end=3))

    assert markdown == "<page 2>\n\nPage two text.\n\n<page 3>\n\nPage three text.\n"


def test_a_spanning_item_is_included_whole_when_it_starts_inside_and_runs_past_the_end():
    markdown = write_markdown(_spanning_paragraph_doc(), PdfPages(start=1, end=1))

    assert markdown == "<page 1>\n\nPage one text.\n\nA paragraph across pages.\n"


def test_formulas_and_tables_are_written_in_place_under_their_page():
    doc = blank_document(page_count=2)
    doc.add_text(label=DocItemLabel.TEXT, text="Energy is", prov=prov(1))
    doc.add_formula(text="E = mc^2", prov=prov(1))
    doc.add_text(label=DocItemLabel.TEXT, text="Results:", prov=prov(2))
    doc.add_table(data=_two_by_two_table(), prov=prov(2))
    doc.add_text(label=DocItemLabel.TEXT, text="Done.", prov=prov(2))

    markdown = write_markdown(doc, PdfPages(start=1, end=2))

    page_1, page_2 = markdown.split("<page 2>")
    assert page_1.startswith("<page 1>")
    assert page_1.index("Energy is") < page_1.index("$$E = mc^2$$")
    table_start = page_2.index("| model ")
    assert page_2.index("Results:") < table_start < page_2.index("| linear ")
    assert table_start < page_2.index("Done.")


def _two_by_two_table() -> TableData:
    table = TableData(num_rows=2, num_cols=2)
    for row, texts in enumerate([("model", "error"), ("linear", "0.12")]):
        for col, text in enumerate(texts):
            table.table_cells.append(
                TableCell(
                    text=text,
                    start_row_offset_idx=row,
                    end_row_offset_idx=row + 1,
                    start_col_offset_idx=col,
                    end_col_offset_idx=col + 1,
                    column_header=row == 0,
                )
            )
    return table
