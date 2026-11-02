"""CLI seam: a textbook is extracted once and inspected while it awaits its split plan."""

import pytest
from docling_core.types.doc import DocItemLabel

from conftest import assert_error, material_status, start_parse
from doc_builders import prov, textbook

DEST = "ml/prml"

HEADINGS = [
    {"page": 1, "text": "Pattern Recognition"},
    {"page": 1, "level": 1, "text": "1 Introduction"},
    {"page": 1, "level": 2, "text": "1.1 Curve Fitting"},
    {"page": 2, "level": 2, "text": "1.2 Probability"},
]


@pytest.fixture(autouse=True)
def _textbook_converter(converter):
    converter.document = textbook()


def start_textbook(run_parse, dest: str = DEST):
    return start_parse(run_parse, dest=dest, material_type="textbook")


def test_a_textbook_parse_ends_pending_with_an_extraction_id_and_structure_index(
    run_parse, library
):
    result = start_textbook(run_parse)

    assert result.exit_code == 0, result.stderr
    index = result.json
    assert index["extraction_id"]
    assert index == {
        "source": DEST,
        "type": "textbook",
        "status": "pending",
        "extraction_id": index["extraction_id"],
        "pages": 2,
        "headings": HEADINGS,
    }
    assert material_status(library, DEST) == "pending"
    assert not (library / DEST / "contents").exists()


def test_inspect_without_pages_returns_the_same_structure_index(run_parse):
    started = start_textbook(run_parse).json

    result = run_parse("inspect", "--dest", DEST)

    assert result.exit_code == 0, result.stderr
    assert result.json == started


def test_the_extraction_is_stored_so_inspect_never_converts_again(run_parse, converter):
    start_textbook(run_parse)
    converter.document = None

    assert run_parse("inspect", "--dest", DEST).json["headings"] == HEADINGS
    assert len(converter.calls) == 1


def test_extraction_ids_identify_different_extractions(run_parse, converter):
    first = start_textbook(run_parse, "ml/first").json["extraction_id"]
    converter.document.add_text(label=DocItemLabel.TEXT, text="More.", prov=prov(2))
    second = start_textbook(run_parse, "ml/second").json["extraction_id"]

    assert first != second


def test_inspect_pages_returns_only_items_on_those_pages_with_types_refs_and_pages(run_parse):
    start_textbook(run_parse)

    result = run_parse("inspect", "--dest", DEST, "--pages", "2")

    assert result.exit_code == 0, result.stderr
    items = result.json["items"]
    assert [(i["type"], i["pages"], i["text"]) for i in items] == [
        ("text", [1, 2], "A paragraph across pages."),
        ("section_header", [2], "1.2 Probability"),
        ("formula", [2], "p(x) = 1"),
        ("caption", [2], "Figure 1.1: A curve"),
        ("picture", [2], "Figure 1.1: A curve"),
    ]
    assert all(i["ref"].startswith("#/") for i in items)
    assert len({i["ref"] for i in items}) == len(items)
    assert "Pattern Recognition" not in result.stdout


def test_inspect_pages_rejects_pages_outside_the_textbook(run_parse):
    start_textbook(run_parse)

    assert_error(
        run_parse("inspect", "--dest", DEST, "--pages", "2-3"),
        "invalid_request",
        "ml/prml has pages 1-2",
    )


def test_inspecting_a_missing_material_says_to_parse_it_first(run_parse):
    assert_error(run_parse("inspect", "--dest", "ml/none"), "not_found", "ml/none", "parse start")


def test_inspecting_a_ready_material_is_refused_with_its_status(run_parse):
    start_parse(run_parse, dest="ml/deck")

    assert_error(
        run_parse("inspect", "--dest", "ml/deck"), "not_found", "ml/deck is not pending (ready)"
    )


def test_inspecting_a_failed_textbook_is_refused_with_its_status(run_parse, converter):
    converter.failure = "page 2 timed out"
    assert_error(start_textbook(run_parse), "conversion_failed")

    assert_error(
        run_parse("inspect", "--dest", DEST),
        "not_found",
        "ml/prml is not pending (failed)",
        "new destination",
    )


def test_a_failed_textbook_keeps_no_extraction(run_parse, converter, library):
    converter.failure = "page 2 timed out"
    converter.partial = True

    assert_error(start_textbook(run_parse), "conversion_failed")

    assert sorted(p.name for p in (library / DEST).iterdir()) == ["material.json", "source.pdf"]
    assert material_status(library, DEST) == "failed"


@pytest.mark.parametrize(
    "command", [["get", "--source", DEST, "--id", "1-1"], ["toc", "--source", DEST]]
)
def test_a_pending_textbook_is_invisible_to_the_reader(run_parse, run_read, command):
    start_textbook(run_parse)

    assert run_read("list").json == {"materials": []}
    result = run_read(*command)
    assert_error(result, "not_found")
    assert result.error["message"] == "ml/prml is not ready (pending)"


def test_inspect_help_documents_both_forms(run_parse):
    result = run_parse("inspect", "--help")

    assert result.exit_code == 0
    assert "inspect --dest MATERIAL\n" in result.stdout
    assert "inspect --dest MATERIAL --pages SPEC" in result.stdout
    assert "extraction_id" in result.stdout
