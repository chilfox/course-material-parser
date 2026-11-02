"""CLI seam: failed parses are never published, and only ready material is visible."""

import json

import pytest
from docling_core.types.doc import DocItemLabel

from conftest import TEXT_LAYER_PDF, assert_error, parse_slides
from doc_builders import prov, slide_deck


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


@pytest.mark.parametrize("failure", ["failed", "partial", "missing provenance"])
def test_a_failed_material_holds_only_the_source_pdf_and_its_record(
    run_parse, converter, library, failure
):
    if failure == "missing provenance":
        converter.document.add_text(label=DocItemLabel.TEXT, text="Floating text.")
    else:
        converter.failure = "page 2 timed out"
        converter.partial = failure == "partial"

    assert_error(_start(run_parse), "conversion_failed")

    material = library / "ml" / "deck"
    assert sorted(p.name for p in material.iterdir()) == ["material.json", "source.pdf"]
    assert _status(library) == "failed"


@pytest.mark.parametrize(
    "command", [["get", "--source", "ml/deck"], ["toc", "--source", "ml/deck"]]
)
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


def _interrupt(library, dest: str = "ml/deck") -> None:
    """Leave ``dest`` as a parse that stopped after copying the PDF."""
    folder = library / dest
    folder.mkdir(parents=True)
    (folder / "source.pdf").write_bytes(TEXT_LAYER_PDF.read_bytes())


def _set_status(library, dest: str, status: str) -> None:
    path = library / dest / "material.json"
    path.write_text(json.dumps({**json.loads(path.read_text()), "status": status}))


def test_an_interrupted_parse_is_ignored_by_list_and_rejected_by_get(run_parse, run_read, library):
    parse_slides(run_parse, "ml/ready")
    _interrupt(library)

    assert [m["source"] for m in run_read("list").json["materials"]] == ["ml/ready"]
    result = run_read("get", "--source", "ml/deck")
    assert_error(result, "not_found")
    assert result.error["message"] == "no ready material 'ml/deck'"


def test_an_interrupted_parse_is_refused_as_an_existing_destination(run_parse, library):
    _interrupt(library)

    assert_error(_start(run_parse), "destination_exists", "ml/deck")
    assert sorted(p.name for p in (library / "ml" / "deck").iterdir()) == ["source.pdf"]


def test_a_pending_material_is_hidden_from_list_and_rejected_with_its_status(
    run_parse, run_read, library
):
    parse_slides(run_parse, "ml/prm")
    _set_status(library, "ml/prm", "pending")

    assert run_read("list").json == {"materials": []}
    result = run_read("toc", "--source", "ml/prm")
    assert_error(result, "not_found")
    assert result.error["message"] == "ml/prm is not ready (pending)"


@pytest.mark.parametrize(
    "source", ["ml/deck/", "ml/./deck", "ml/x/../deck", "/ml/deck", "ML/DECK", "ml/dec", "ml"]
)
def test_source_must_be_the_exact_material_id(run_parse, run_read, source):
    parse_slides(run_parse, "ml/deck")

    result = run_read("get", "--source", source)

    assert_error(result, "not_found")
    assert result.error["message"] == f"no ready material '{source}'"


def test_list_prefix_matches_whole_path_segments_and_sorts_the_result(run_parse, run_read):
    for dest in ["mlx/a", "ml/zeta", "ml/prml", "ml-intro", "db/week1", "ml/deep/nets"]:
        parse_slides(run_parse, dest)

    sources = [m["source"] for m in run_read("list", "ml").json["materials"]]

    assert sources == ["ml/deep/nets", "ml/prml", "ml/zeta"]
    assert [m["source"] for m in run_read("list", "ml/deep").json["materials"]] == ["ml/deep/nets"]
    assert [m["source"] for m in run_read("list", "ml/prml").json["materials"]] == ["ml/prml"]
    assert run_read("list", "ml/pr").json == {"materials": []}
    assert run_read("list", "nothing").json == {"materials": []}


@pytest.mark.parametrize("prefix", ["ml/", "/ml", "../ml", "ml//prml"])
def test_a_malformed_list_prefix_is_an_invalid_request(run_read, prefix):
    assert_error(run_read("list", prefix), "invalid_request", prefix)


def test_discovery_never_descends_into_a_material(run_parse, run_read, library):
    parse_slides(run_parse, "ml/deck")
    parse_slides(run_parse, "other")
    nested = library / "ml" / "deck" / "contents" / "copy"
    nested.mkdir()
    (nested / "material.json").write_text((library / "other" / "material.json").read_text())

    assert [m["source"] for m in run_read("list").json["materials"]] == ["ml/deck", "other"]
