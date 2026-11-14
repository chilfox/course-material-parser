"""CLI seam: parse never overwrites, nests, or escapes the library, and refuses early."""

import pytest

from conftest import (
    TEXT_LAYER_PDF,
    assert_error,
    material_status,
    set_material_status,
    start_parse,
)
from course_material_parser import pdf


def snapshot(root):
    """Every path under ``root`` with file bytes, so any modification is visible."""
    return {
        path.relative_to(root).as_posix(): path.read_bytes() if path.is_file() else None
        for path in sorted(root.rglob("*"))
    }


@pytest.mark.parametrize("leftover", [None, "source.pdf", "contents", "notes.txt"])
def test_an_interrupted_destination_is_refused_with_recovery_guidance(
    run_parse, library, converter, leftover
):
    destination = library / "ml" / "prml"
    destination.mkdir(parents=True)
    if leftover == "contents":
        (destination / leftover).mkdir()
    elif leftover is not None:
        (destination / leftover).write_bytes(b"keep me")
    before = snapshot(library)

    result = start_parse(run_parse, dest="ml/prml")

    assert_error(result, "destination_exists")
    assert result.error["message"] == (
        "ml/prml is an interrupted parse; delete it by hand or choose a new destination"
    )
    assert snapshot(library) == before
    assert converter.calls == []


@pytest.mark.parametrize("status", ["ready", "pending", "failed"])
def test_an_existing_material_is_refused_and_left_untouched(run_parse, library, converter, status):
    assert start_parse(run_parse, dest="ml/deck").exit_code == 0
    set_material_status(library, "ml/deck", status)
    before = snapshot(library)
    converter.calls.clear()

    result = start_parse(run_parse, dest="ml/deck")

    assert_error(result, "destination_exists")
    assert result.error["message"] == "ml/deck already exists; choose a new destination"
    assert snapshot(library) == before
    assert converter.calls == []


def test_an_existing_file_is_refused_and_left_untouched(run_parse, library, converter):
    (library / "deck").write_bytes(b"keep me")
    before = snapshot(library)

    result = start_parse(run_parse, dest="deck")

    assert_error(result, "destination_exists")
    assert result.error["message"] == "deck already exists; choose a new destination"
    assert snapshot(library) == before
    assert converter.calls == []


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

    result = start_parse(run_parse, dest="ml/deck")

    assert_error(result, "destination_exists")
    assert result.error["message"] == (
        "ml/deck is an interrupted parse; delete it by hand or choose a new destination"
    )
    assert snapshot(library / "ml" / "deck") == {"theirs.txt": b"keep me"}
    assert converter.calls == []


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
    result = start_parse(run_parse, dest=dest)

    assert_error(result, "invalid_request")
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

    result = start_parse(run_parse, dest=dest)

    assert_error(result, "invalid_request")
    assert "outside library_root" in result.error["message"]
    assert snapshot(library) == before
    assert list(elsewhere.iterdir()) == []


def test_a_destination_nested_inside_a_material_is_refused(run_parse, library):
    assert start_parse(run_parse, dest="ml/deck").exit_code == 0
    before = snapshot(library)

    result = start_parse(run_parse, dest="ml/deck/contents/more")

    assert_error(result, "invalid_request")
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

    result = start_parse(run_parse, dest="ml/deck/more")

    assert_error(result, "invalid_request")
    assert "ml/deck" in result.error["message"]
    assert "interrupted parse" in result.error["message"]
    assert "delete" in result.error["message"]
    assert snapshot(library) == before


def test_a_destination_under_an_existing_file_is_refused_before_anything_is_created(
    run_parse, library
):
    (library / "ml").write_text("not a folder")
    before = snapshot(library)

    result = start_parse(run_parse, dest="ml/prml")

    assert_error(result, "invalid_request")
    assert "ml exists and is not a folder" in result.error["message"]
    assert snapshot(library) == before


def test_refusals_happen_before_the_pdf_is_even_read(run_parse, library):
    (library / "deck").mkdir()

    result = run_parse("start", "--pdf", "missing.pdf", "--dest", "deck", "--type", "slides")

    assert_error(result, "destination_exists")


def test_missing_parent_folders_of_the_destination_are_created(run_parse, library):
    result = start_parse(run_parse, dest="cs/ml/prml-slides_2024.v2")

    assert result.exit_code == 0, result.stderr
    assert material_status(library, "cs/ml/prml-slides_2024.v2") == "ready"
