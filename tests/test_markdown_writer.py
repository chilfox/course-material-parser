"""markdown_writer seam: DoclingDocument plus selector in, page-marked Markdown out."""

from doc_builders import slide_deck

from course_material_parser.markdown_writer import PdfPages, write_markdown


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
