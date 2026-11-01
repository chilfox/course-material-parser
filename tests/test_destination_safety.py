"""CLI seam: parse never overwrites, nests, or escapes the library, and refuses early."""

import json

import pytest
from conftest import TEXT_LAYER_PDF

from course_material_parser import pdf


def start(run_parse, dest):
    return run_parse("start", "--pdf", str(TEXT_LAYER_PDF), "--dest", dest, "--type", "slides")


def snapshot(root):
    """Every path under ``root`` with file bytes, so any modification is visible."""
    return {
        path.relative_to(root).as_posix(): path.read_bytes() if path.is_file() else None
        for path in sorted(root.rglob("*"))
    }


def assert_refused(result, code):
    assert result.exit_code == 1
    assert result.stdout == ""
    assert result.error["error"] == code
    assert result.error["message"]


def test_an_existing_empty_destination_is_refused_and_left_untouched(run_parse, library):
    (library / "ml" / "prml").mkdir(parents=True)
    before = snapshot(library)

    result = start(run_parse, "ml/prml")

    assert_refused(result, "destination_exists")
    assert "ml/prml" in result.error["message"]
    assert snapshot(library) == before


def test_an_existing_material_is_refused_and_left_untouched(run_parse, library):
    assert start(run_parse, "ml/deck").exit_code == 0
    before = snapshot(library)

    result = start(run_parse, "ml/deck")

    assert_refused(result, "destination_exists")
    assert snapshot(library) == before


def test_a_destination_appearing_after_the_preliminary_check_is_refused(
    run_parse, library, converter, monkeypatch
):
    # parse runs pdf.page_count after its preliminary destination check and before it
    # creates the destination, so this hook is the gap where another process can win the
    # race. If that order changes, this test must hook another step in the same gap.
    real_page_count = pdf.page_count

    def page_count_while_another_process_creates_the_destination(path):
        (library / "ml" / "deck").mkdir(parents=True)
        (library / "ml" / "deck" / "theirs.txt").write_text("keep me")
        return real_page_count(path)

    monkeypatch.setattr(pdf, "page_count", page_count_while_another_process_creates_the_destination)

    result = start(run_parse, "ml/deck")

    assert_refused(result, "destination_exists")
    assert snapshot(library / "ml" / "deck") == {"theirs.txt": b"keep me"}


@pytest.mark.parametrize(
    "dest",
    [
        "/tmp/deck",
        "ml/../deck",
        "..",
        "ml/./deck",
        ".",
        "ml/.hidden",
        ".deck",
        "ml/week 3",
        "ml/deck*",
        "ml\\deck",
        "ml//deck",
        "ml/deck/",
        "",
    ],
)
def test_escaping_or_invalid_destinations_are_refused_before_anything_is_created(
    run_parse, library, dest
):
    result = start(run_parse, dest)

    assert_refused(result, "invalid_request")
    assert "destination" in result.error["message"]
    assert snapshot(library) == {}


@pytest.mark.parametrize("dest", ["ml/deck", "ml/week3/deck"])
def test_a_destination_through_a_symlink_leaving_the_library_is_refused(
    run_parse, library, tmp_path, dest
):
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (library / "ml").symlink_to(elsewhere, target_is_directory=True)
    before = snapshot(library)

    result = start(run_parse, dest)

    assert_refused(result, "invalid_request")
    assert "outside library_root" in result.error["message"]
    assert snapshot(library) == before
    assert list(elsewhere.iterdir()) == []


def test_a_destination_nested_inside_a_material_is_refused(run_parse, library):
    assert start(run_parse, "ml/deck").exit_code == 0
    before = snapshot(library)

    result = start(run_parse, "ml/deck/contents/more")

    assert_refused(result, "invalid_request")
    assert "inside material ml/deck" in result.error["message"]
    assert snapshot(library) == before


@pytest.mark.parametrize("leftover", ["source.pdf", "contents"])
def test_a_destination_nested_inside_an_interrupted_parse_is_refused(run_parse, library, leftover):
    interrupted = library / "ml" / "deck"
    interrupted.mkdir(parents=True)
    if leftover == "contents":
        (interrupted / leftover).mkdir()
    else:
        (interrupted / leftover).write_bytes(TEXT_LAYER_PDF.read_bytes())
    before = snapshot(library)

    result = start(run_parse, "ml/deck/more")

    assert_refused(result, "invalid_request")
    assert "ml/deck" in result.error["message"]
    assert "interrupted parse" in result.error["message"]
    assert "delete" in result.error["message"]
    assert snapshot(library) == before


def test_a_destination_under_an_existing_file_is_refused_before_anything_is_created(
    run_parse, library
):
    (library / "ml").write_text("not a folder")
    before = snapshot(library)

    result = start(run_parse, "ml/prml")

    assert_refused(result, "invalid_request")
    assert "ml exists and is not a folder" in result.error["message"]
    assert snapshot(library) == before


def test_refusals_happen_before_the_pdf_is_even_read(run_parse, library):
    (library / "deck").mkdir()

    result = run_parse("start", "--pdf", "missing.pdf", "--dest", "deck", "--type", "slides")

    assert_refused(result, "destination_exists")


def test_missing_parent_folders_of_the_destination_are_created(run_parse, library):
    result = start(run_parse, "cs/ml/prml-slides_2024.v2")

    assert result.exit_code == 0, result.stderr
    record = json.loads((library / "cs/ml/prml-slides_2024.v2/material.json").read_text())
    assert record["status"] == "ready"
