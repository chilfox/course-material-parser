"""CLI seam: agents cut slide pages, look up a deck's toc, and get selector errors."""

import pytest

from conftest import assert_error, parse_slides
from doc_builders import slide_deck


def test_slide_page_cut_returns_the_requested_blocks_in_request_order(run_parse, run_read):
    parse_slides(run_parse)

    result = run_read("get", "--source", "ml/week3-slides", "--pages", "2,1")

    assert result.exit_code == 0, result.stderr
    assert result.stdout == (
        "<page 2>\n\n## 2 Methods\n\nSlide two body.\n\n"
        "<page 1>\n\n## 1 Introduction\n\nSlide one body.\n"
    )


def test_slide_page_cut_includes_a_bare_marker_for_an_empty_page(run_parse, run_read, converter):
    converter.document = slide_deck({1: ["Only slide", "Body."]}, page_count=2)
    parse_slides(run_parse)

    result = run_read("get", "--source", "ml/week3-slides", "--pages", "1-2")

    assert result.exit_code == 0, result.stderr
    assert result.stdout == "<page 1>\n\n## Only slide\n\nBody.\n\n<page 2>\n"


def test_slide_toc_gives_source_type_and_page_count(run_parse, run_read):
    parse_slides(run_parse)

    result = run_read("toc", "--source", "ml/week3-slides")

    assert result.exit_code == 0, result.stderr
    assert result.stdout == '{"source":"ml/week3-slides","type":"slides","pages":2}\n'


@pytest.mark.parametrize(
    ("selector", "fix"),
    [
        (["--id", "1-1"], "--pages"),
        (["--id", "1-1", "--pages", "1"], "either --id or --pages"),
        (["--pages", "2-1"], "reversed"),
        (["--pages", "p.3"], "15-30"),
        (["--pages", "1,,2"], "15-30"),
        (["--pages", ""], "15-30"),
    ],
)
def test_misused_slide_selectors_are_invalid_requests_naming_the_fix(
    run_parse, run_read, selector, fix
):
    parse_slides(run_parse)

    result = run_read("get", "--source", "ml/week3-slides", *selector)

    assert_error(result, "invalid_request")
    assert fix in result.error["message"]


@pytest.mark.parametrize("pages", ["3", "0", "1-3"])
def test_slide_pages_out_of_range_name_the_valid_range(run_parse, run_read, pages):
    parse_slides(run_parse)

    result = run_read("get", "--source", "ml/week3-slides", "--pages", pages)

    assert_error(result, "invalid_request")
    assert result.error["message"] == "pages out of range: ml/week3-slides has pages 1-2"


def test_a_huge_out_of_range_page_range_is_refused_without_expanding_it(run_parse, run_read):
    parse_slides(run_parse)

    result = run_read("get", "--source", "ml/week3-slides", "--pages", "1-999999999")

    assert_error(result, "invalid_request")
    assert result.error["message"] == "pages out of range: ml/week3-slides has pages 1-2"


def test_get_help_holds_the_selector_rules_and_the_marker_legend(run_read):
    result = run_read("get", "--help")

    assert result.exit_code == 0
    help_text = " ".join(result.stdout.split())
    assert "--pages" in help_text and "--id" in help_text
    assert "<page N> the content below comes from source-PDF page N" in help_text
    assert "<visual> an image was here, followed by its caption if detected" in help_text
    assert "Render that page only if the content can't be understood without it" in help_text
    assert "too_large" in help_text
