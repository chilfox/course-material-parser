"""CLI seam: failed parses are never published, and only ready material is visible."""

import json

import pytest
from conftest import TEXT_LAYER_PDF, assert_error, parse_slides
from doc_builders import prov, slide_deck
from docling_core.types.doc import DocItemLabel


def _start(run_parse, dest: str = "ml/deck"):
    return run_parse("start", "--pdf", str(TEXT_LAYER_PDF), "--dest", dest, "--type", "slides")


def _status(library, dest: str = "ml/deck") -> str:
    return json.loads((library / dest / "material.json").read_text())["status"]


def test_body_items_without_a_source_page_fail_the_parse_with_count_and_kinds(
    run_parse, run_read, converter, library
):
    doc = slide_deck({1: ["Title", "Placed text."]}, page_count=2)
    for _ in range(3):
        doc.add_text(label=DocItemLabel.TEXT, text="Floating text.")
    doc.add_formula(text="x^2")
    doc.add_picture()
    converter.document = doc

    result = _start(run_parse)

    assert_error(
        result,
        "conversion_failed",
        "3 text items, 1 formula, 1 picture have no source page",
        "ml/deck",
    )
    assert _status(library) == "failed"
    assert (library / "ml" / "deck" / "source.pdf").is_file()
    assert run_read("list").json == {"materials": []}


def test_a_single_unplaced_item_is_reported_in_the_singular(run_parse, converter):
    doc = slide_deck({1: ["Title"]}, page_count=1)
    doc.add_text(label=DocItemLabel.TEXT, text="Floating text.")
    converter.document = doc

    assert_error(_start(run_parse), "conversion_failed", "1 text item has no source page")


def test_furniture_without_a_source_page_does_not_fail_the_parse(run_parse, converter):
    from docling_core.types.doc.document import ContentLayer

    doc = slide_deck({1: ["Title", "Body."]}, page_count=1)
    doc.add_text(
        label=DocItemLabel.PAGE_FOOTER, text="Footer", content_layer=ContentLayer.FURNITURE
    )
    doc.add_text(label=DocItemLabel.TEXT, text="Placed.", prov=prov(1))
    converter.document = doc

    assert _start(run_parse).exit_code == 0


@pytest.mark.parametrize("command", [["get", "--source", "ml/deck"], ["toc", "--source", "ml/deck"]])
def test_a_failed_material_is_rejected_with_its_status(run_parse, run_read, converter, command):
    converter.failure = "page 2 timed out"
    _start(run_parse)

    result = run_read(*command)

    assert_error(result, "not_found")
    assert result.error["message"] == "ml/deck is not ready (failed)"


def test_retrying_a_failed_parse_requires_a_new_destination(run_parse, converter):
    converter.failure = "page 2 timed out"
    _start(run_parse)
    converter.failure = None

    assert_error(_start(run_parse), "destination_exists", "ml/deck")
    assert_error(_start(run_parse), "destination_exists")
    assert _start(run_parse, "ml/deck-retry").exit_code == 0
