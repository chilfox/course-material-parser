"""CLI seam: an approved split is finalized into a ready textbook read unit by unit."""

import json

import pytest

from conftest import assert_error, blank_pdf, material_status, plan_unit, start_parse
from course_material_parser import parse_command
from doc_builders import paged_book

DEST = "ml/prml"
PAGES = 10


@pytest.fixture
def extraction_id(run_parse, converter, tmp_path):
    """Start a pending ten-page textbook at DEST, one paragraph per page, and return its id."""
    converter.document = paged_book(PAGES)
    pdf = blank_pdf(tmp_path / "prml.pdf", PAGES)
    result = start_parse(run_parse, "--no-ocr", dest=DEST, pdf=pdf, material_type="textbook")
    assert result.exit_code == 0, result.stderr
    return result.json["extraction_id"]


def approved_plan(extraction_id):
    """Front matter, chapter 1 (intro and two sections sharing page 4), and references."""
    return {
        "version": 1,
        "extraction_id": extraction_id,
        "contents": [
            plan_unit("front-matter", "Front matter", 1, 1, kind="other"),
            {
                "id": "chapter-1",
                "title": "Introduction",
                "units": [
                    plan_unit("1-intro", "Introduction", 2, 2, kind="other"),
                    plan_unit("1-1", "Curve Fitting", 3, 4),
                    plan_unit("1-2", "Probability", 4, 8),
                ],
            },
            plan_unit("references", "References", 9, 10, kind="other"),
        ],
    }


@pytest.fixture
def plan_file(run_parse, tmp_path, extraction_id):
    """Propose the approved plan for DEST and return the agent's working plan file."""
    path = tmp_path / "my-plan.json"
    path.write_text(json.dumps(approved_plan(extraction_id)))
    result = run_parse("propose", "--dest", DEST, "--plan", str(path))
    assert result.exit_code == 0, result.stderr
    return path


def finalize(run_parse):
    return run_parse("finalize", "--dest", DEST, "--confirm")


def stored_files(library):
    folder = library / DEST
    return sorted(
        path.relative_to(folder).as_posix() for path in folder.rglob("*") if path.is_file()
    )


def test_finalize_reports_the_ready_material(run_parse, plan_file):
    result = finalize(run_parse)

    assert result.exit_code == 0, result.stderr
    assert result.json == {
        "source": DEST,
        "type": "textbook",
        "status": "ready",
        "pages": PAGES,
        "chapters": 1,
        "units": 5,
    }


def test_finalize_stores_units_by_kind_in_zero_padded_chapter_folders_and_drops_intermediates(
    run_parse, library, plan_file
):
    finalize(run_parse)

    assert material_status(library, DEST) == "ready"
    assert stored_files(library) == [
        "contents/chapter-01/1-intro.md",
        "contents/chapter-01/section_1-1.md",
        "contents/chapter-01/section_1-2.md",
        "contents/front-matter.md",
        "contents/references.md",
        "material.json",
        "source.pdf",
    ]


def test_finalize_runs_the_snapshot_not_the_edited_working_plan(
    run_parse, run_read, extraction_id, plan_file
):
    edited = approved_plan(extraction_id)
    edited["contents"][0]["title"] = "Preface"
    edited["contents"][0]["selector"]["end"] = 2
    plan_file.write_text(json.dumps(edited))

    finalize(run_parse)

    front_matter = run_read("toc", "--source", DEST).json["contents"][0]
    assert front_matter == {"id": "front-matter", "title": "Front matter", "pages": [1, 1]}


def test_finalize_without_confirm_is_refused_and_changes_nothing(run_parse, library, plan_file):
    result = run_parse("finalize", "--dest", DEST)

    assert_error(result, "confirm_required", "approv", "--confirm")
    assert material_status(library, DEST) == "pending"
    assert not (library / DEST / "contents").exists()


def test_a_second_finalize_is_refused(run_parse, plan_file):
    finalize(run_parse)

    assert_error(finalize(run_parse), "not_found", "ml/prml is not pending (ready)")


def test_finalize_before_any_proposal_is_refused(run_parse, library, extraction_id):
    assert_error(finalize(run_parse), "invalid_request", "parse propose")
    assert material_status(library, DEST) == "pending"


def test_a_finalize_that_fails_part_way_leaves_the_textbook_pending_and_can_be_rerun(
    run_parse, run_read, library, plan_file, monkeypatch
):
    real_write = parse_command.write_markdown
    calls = []

    def failing_write(document, selector):
        calls.append(selector)
        if len(calls) == 3:
            raise OSError("disk full")
        return real_write(document, selector)

    monkeypatch.setattr(parse_command, "write_markdown", failing_write)
    assert_error(finalize(run_parse), "internal_error", "disk full")

    assert material_status(library, DEST) == "pending"
    assert_error(run_read("toc", "--source", DEST), "not_found", "not ready (pending)")
    monkeypatch.setattr(parse_command, "write_markdown", real_write)
    assert finalize(run_parse).exit_code == 0
    assert "extraction.json" not in stored_files(library)


def test_textbook_toc_lists_contents_in_reading_order_with_inclusive_ranges(
    run_parse, run_read, plan_file
):
    finalize(run_parse)

    result = run_read("toc", "--source", DEST)

    assert result.exit_code == 0, result.stderr
    assert result.json == {
        "source": DEST,
        "type": "textbook",
        "pages": PAGES,
        "contents": [
            {"id": "front-matter", "title": "Front matter", "pages": [1, 1]},
            {
                "id": "chapter-1",
                "title": "Introduction",
                "pages": [2, 8],
                "units": [
                    {"id": "1-intro", "title": "Introduction", "pages": [2, 2]},
                    {"id": "1-1", "title": "Curve Fitting", "pages": [3, 4]},
                    {"id": "1-2", "title": "Probability", "pages": [4, 8]},
                ],
            },
            {"id": "references", "title": "References", "pages": [9, 10]},
        ],
    }


def test_unit_get_prints_the_units_markdown_as_is(run_parse, run_read, plan_file):
    finalize(run_parse)

    result = run_read("get", "--source", DEST, "--id", "1-1")

    assert result.exit_code == 0, result.stderr
    assert result.stdout == "<page 3>\n\nText on page 3.\n\n<page 4>\n\nText on page 4.\n"


def test_unit_get_accepts_and_ignores_confirm(run_parse, run_read, plan_file):
    finalize(run_parse)

    result = run_read("get", "--source", DEST, "--id", "references", "--confirm")

    assert result.exit_code == 0, result.stderr
    assert result.stdout.startswith("<page 9>")


@pytest.mark.parametrize(
    ("selector", "code", "fragment"),
    [
        (["--id", "2-9"], "unknown_id", "unknown id '2-9' in ml/prml"),
        ([], "invalid_request", "missing --id: ml/prml is a textbook"),
        (["--pages", "3"], "invalid_request", "--pages applies only to slides; ml/prml is a"),
    ],
)
def test_textbook_selector_errors_name_the_fix(
    run_parse, run_read, plan_file, selector, code, fragment
):
    finalize(run_parse)

    assert_error(run_read("get", "--source", DEST, *selector), code, fragment)


def test_finalize_help_says_it_runs_the_approved_snapshot(run_parse):
    result = run_parse("finalize", "--help")

    assert result.exit_code == 0
    for fragment in ("--confirm", "approv", "snapshot"):
        assert fragment in result.stdout
    assert "finalize" in run_parse("--help").stdout
