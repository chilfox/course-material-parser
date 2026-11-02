"""CLI seam: a slide deck is parsed into ready material and read back."""

from conftest import TEXT_LAYER_PDF, material_status, parse_slides, start_parse


def test_parsing_slides_stores_a_ready_material_with_page_marked_markdown(run_parse, library):
    result = start_parse(run_parse, dest="ml/week3-slides")

    assert result.exit_code == 0, result.stderr
    assert result.stderr == ""
    material = library / "ml" / "week3-slides"
    assert (material / "source.pdf").read_bytes() == TEXT_LAYER_PDF.read_bytes()
    assert material_status(library, "ml/week3-slides") == "ready"
    slides = (material / "contents" / "slides.md").read_text()
    assert slides.index("<page 1>") < slides.index("Slide one body.")
    assert slides.index("<page 2>") < slides.index("Slide two body.")


def test_read_list_shows_parsed_slides_with_source_type_and_page_count(run_parse, run_read):
    parse_slides(run_parse, "ml/week3-slides")
    parse_slides(run_parse, "db/week1")

    result = run_read("list")

    assert result.exit_code == 0, result.stderr
    assert result.stdout == (
        '{"materials":[{"source":"db/week1","type":"slides","pages":2},'
        '{"source":"ml/week3-slides","type":"slides","pages":2}]}\n'
    )


def test_read_get_prints_the_whole_deck_as_raw_markdown(run_parse, run_read):
    parse_slides(run_parse)

    result = run_read("get", "--source", "ml/week3-slides")

    assert result.exit_code == 0, result.stderr
    assert result.stdout == (
        "<page 1>\n\n## 1 Introduction\n\nSlide one body.\n\n"
        "<page 2>\n\n## 2 Methods\n\nSlide two body.\n"
    )
