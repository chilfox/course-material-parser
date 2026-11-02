"""CLI seam: a pending textbook's split plan is validated and snapshotted for approval."""

import json

import pypdfium2
import pytest

from conftest import assert_error, material_status, start_parse
from doc_builders import blank_document

DEST = "ml/prml"
PAGES = 10


@pytest.fixture
def book_pdf(tmp_path):
    """A blank ten-page PDF, so plans can cover more than the two-page fixture."""
    path = tmp_path / "prml.pdf"
    document = pypdfium2.PdfDocument.new()
    for _ in range(PAGES):
        document.new_page(612, 792)
    document.save(path)
    return path


@pytest.fixture
def extraction_id(run_parse, converter, book_pdf):
    """Start a pending ten-page textbook at DEST and return its extraction id."""
    converter.document = blank_document(PAGES)
    result = start_parse(run_parse, "--no-ocr", dest=DEST, pdf=book_pdf, material_type="textbook")
    assert result.exit_code == 0, result.stderr
    return result.json["extraction_id"]


def unit(unit_id, title, start, end, kind="section"):
    return {
        "id": unit_id,
        "title": title,
        "kind": kind,
        "selector": {"kind": "pdf_pages", "start": start, "end": end},
    }


def valid_plan(extraction_id):
    """Front matter, chapter 1 with two sections sharing page 4, and references."""
    return {
        "version": 1,
        "extraction_id": extraction_id,
        "contents": [
            unit("front-matter", "Front matter", 1, 1, kind="other"),
            {
                "id": "chapter-01",
                "title": "Introduction",
                "units": [unit("1-1", "Curve Fitting", 2, 4), unit("1-2", "Probability", 4, 8)],
            },
            unit("references", "References", 9, 10, kind="other"),
        ],
    }


def propose(run_parse, tmp_path, plan):
    path = tmp_path / "my-plan.json"
    path.write_text(plan if isinstance(plan, str) else json.dumps(plan))
    return run_parse("propose", "--dest", DEST, "--plan", str(path))


def test_a_valid_plan_returns_the_approval_summary_with_overlap_pages(
    run_parse, tmp_path, extraction_id
):
    result = propose(run_parse, tmp_path, valid_plan(extraction_id))

    assert result.exit_code == 0, result.stderr
    assert result.json == {
        "source": DEST,
        "pdf": "prml.pdf",
        "pages": 10,
        "contents": [
            {"id": "front-matter", "title": "Front matter", "pages": [1, 1]},
            {
                "id": "chapter-01",
                "title": "Introduction",
                "pages": [2, 8],
                "units": [
                    {"id": "1-1", "title": "Curve Fitting", "pages": [2, 4]},
                    {"id": "1-2", "title": "Probability", "pages": [4, 8]},
                ],
            },
            {"id": "references", "title": "References", "pages": [9, 10]},
        ],
        "overlaps": [{"page": 4, "units": ["1-1", "1-2"]}],
    }


def snapshot(library):
    return json.loads((library / DEST / "plan.json").read_text())


def test_a_valid_plan_is_snapshotted_into_the_pending_material(
    run_parse, tmp_path, library, extraction_id
):
    plan = valid_plan(extraction_id)

    propose(run_parse, tmp_path, plan)

    assert snapshot(library) == plan
    assert material_status(library, DEST) == "pending"


def test_proposing_again_replaces_the_snapshot(run_parse, tmp_path, library, extraction_id):
    propose(run_parse, tmp_path, valid_plan(extraction_id))
    revised = valid_plan(extraction_id)
    revised["contents"][0]["title"] = "Preface"

    result = propose(run_parse, tmp_path, revised)

    assert result.json["contents"][0]["title"] == "Preface"
    assert snapshot(library) == revised


def test_an_invalid_plan_reports_every_problem_at_once_and_changes_nothing(
    run_parse, tmp_path, library, extraction_id
):
    approved = valid_plan(extraction_id)
    propose(run_parse, tmp_path, approved)
    plan = valid_plan(extraction_id)
    plan["contents"][0]["selector"]["start"] = 2
    plan["contents"][1]["units"][1]["selector"].update(start=8, end=6)

    result = propose(run_parse, tmp_path, plan)

    assert_error(result, "invalid_plan", "unit front-matter: pages 2-1 reversed")
    assert result.error["problems"] == [
        "unit front-matter: pages 2-1 reversed",
        "unit 1-2: pages 8-6 reversed",
    ]
    assert material_status(library, DEST) == "pending"
    assert snapshot(library) == approved


def _set(path, value):
    """Return an edit that sets the plan field at ``path`` (keys and indexes) to ``value``."""

    def edit(plan):
        *parents, last = path
        target = plan
        for key in parents:
            target = target[key]
        target[last] = value

    return edit


def _delete(path):
    def edit(plan):
        *parents, last = path
        target = plan
        for key in parents:
            target = target[key]
        del target[last]

    return edit


CHAPTER = ("contents", 1)
SECTION_1 = (*CHAPTER, "units", 0)
SECTION_2 = (*CHAPTER, "units", 1)


@pytest.mark.parametrize(
    ("edit", "problem"),
    [
        (_set(("version",), 2), "version 2 is not supported: use 1"),
        (_delete((*SECTION_1, "kind")), "unit 1-1: missing field 'kind'"),
        (_set((*SECTION_1, "chapter"), "chapter-01"), "unit 1-1: unknown field 'chapter'"),
        (_set((*CHAPTER, "kind"), "other"), "chapter chapter-01: unknown field 'kind'"),
        (_set(("chapters",), []), "plan: unknown field 'chapters'"),
        (_set((*SECTION_1, "id"), "1.1"), "invalid id '1.1'"),
        (_set((*SECTION_1, "id"), "-1"), "invalid id '-1'"),
        (_set((*SECTION_2, "id"), "chapter-01"), "duplicate id 'chapter-01'"),
        (_set((*SECTION_1, "title"), " "), "unit 1-1: empty title"),
        (
            _set((*SECTION_1, "kind"), "exercise"),
            "unit 1-1: kind 'exercise' is not section or other",
        ),
        (
            _set((*SECTION_1, "selector", "kind"), "paragraphs"),
            "unit 1-1: selector kind 'paragraphs' is not pdf_pages",
        ),
        (
            _set((*SECTION_1, "selector", "start"), "2"),
            "unit 1-1: selector start is not an integer",
        ),
        (
            _set(("contents", 2, "selector", "end"), 11),
            "unit references: pages 9-11 out of range: ml/prml has pages 1-10",
        ),
        (_set((*CHAPTER, "units"), []), "chapter chapter-01: no units"),
        (
            _set((*SECTION_2, "selector"), {"kind": "pdf_pages", "start": 1, "end": 8}),
            "unit 1-2: starts on page 1, before unit 1-1 on page 2",
        ),
        (
            _set((*SECTION_2, "selector"), {"kind": "pdf_pages", "start": 3, "end": 8}),
            "unit 1-2: pages 3-8 overlap unit 1-1 (pages 2-4) by more than one boundary page",
        ),
        (_set(("contents", 0, "selector", "end"), 0), "unit front-matter: pages 1-0 reversed"),
        (_set((*SECTION_2, "selector", "end"), 6), "pages 7-8 are in no unit"),
        (_set(("contents", 2, "selector", "end"), 9), "page 10 is in no unit"),
        (_set(("extraction_id",), "0123456789abcdef"), "extraction_id '0123456789abcdef'"),
        (_set(("contents",), []), "plan: contents is empty"),
        (_set(("contents", 0), "front-matter"), "contents[0]: not an object"),
    ],
)
def test_each_validation_rule_rejects_a_violating_plan(
    run_parse, tmp_path, library, extraction_id, edit, problem
):
    plan = valid_plan(extraction_id)
    edit(plan)

    result = propose(run_parse, tmp_path, plan)

    assert_error(result, "invalid_plan", problem)
    assert material_status(library, DEST) == "pending"
    assert not (library / DEST / "plan.json").exists()


def test_an_extraction_id_mismatch_names_the_pending_extraction(run_parse, tmp_path, extraction_id):
    plan = valid_plan(extraction_id)
    plan["extraction_id"] = "0123456789abcdef"

    result = propose(run_parse, tmp_path, plan)

    assert_error(result, "invalid_plan", extraction_id, DEST)


def test_a_plan_file_that_is_not_json_is_an_invalid_plan(run_parse, tmp_path, extraction_id):
    assert_error(propose(run_parse, tmp_path, "{not json"), "invalid_plan", "not valid JSON")


def test_a_missing_plan_file_is_not_found(run_parse, tmp_path, extraction_id):
    result = run_parse("propose", "--dest", DEST, "--plan", str(tmp_path / "none.json"))

    assert_error(result, "not_found", "none.json")


def test_several_units_may_share_one_page_and_each_shared_page_is_one_overlap(
    run_parse, tmp_path, extraction_id
):
    plan = valid_plan(extraction_id)
    plan["contents"][1]["units"] = [
        unit("1-intro", "Introduction", 2, 4, kind="other"),
        unit("1-1", "Curve Fitting", 4, 4),
        unit("1-2", "Probability", 4, 8),
    ]

    result = propose(run_parse, tmp_path, plan)

    assert result.exit_code == 0, result.stderr
    assert result.json["overlaps"] == [{"page": 4, "units": ["1-intro", "1-1", "1-2"]}]


def test_proposing_for_ready_slides_is_refused(run_parse, tmp_path):
    start_parse(run_parse, dest=DEST)

    assert_error(
        propose(run_parse, tmp_path, valid_plan("x")), "not_found", "ml/prml is not pending (ready)"
    )


def test_proposing_for_a_missing_material_is_refused(run_parse, tmp_path):
    assert_error(propose(run_parse, tmp_path, valid_plan("x")), "not_found", "ml/prml")


def test_propose_help_documents_the_plan_file_and_its_rules(run_parse):
    result = run_parse("propose", "--help")

    assert result.exit_code == 0
    for fragment in ('"extraction_id"', '"units"', '"pdf_pages"', "boundary page"):
        assert fragment in result.stdout
    assert "propose" in run_parse("--help").stdout
