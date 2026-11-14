"""CLI seam: a pending textbook's split plan is validated and snapshotted for approval."""

import json

import pytest

from conftest import assert_error, blank_pdf, material_status, plan_unit, start_parse
from doc_builders import blank_document

DEST = "ml/prml"
PAGES = 10


@pytest.fixture
def book_pdf(tmp_path):
    """A blank ten-page PDF, so plans can cover more than the two-page fixture."""
    return blank_pdf(tmp_path / "prml.pdf", PAGES)


@pytest.fixture
def extraction_id(run_parse, converter, book_pdf):
    """Start a pending ten-page textbook at DEST and return its extraction id."""
    converter.document = blank_document(PAGES)
    result = start_parse(run_parse, "--no-ocr", dest=DEST, pdf=book_pdf, material_type="textbook")
    assert result.exit_code == 0, result.stderr
    return result.json["extraction_id"]


def valid_plan(extraction_id):
    """Front matter, chapter 1 with two sections sharing page 4, and references."""
    return {
        "version": 1,
        "extraction_id": extraction_id,
        "contents": [
            plan_unit("front-matter", "Front matter", 1, 1, kind="other"),
            {
                "id": "chapter-01",
                "title": "Introduction",
                "units": [
                    plan_unit("1-1", "Curve Fitting", 2, 4),
                    plan_unit("1-2", "Probability", 4, 8),
                ],
            },
            plan_unit("references", "References", 9, 10, kind="other"),
        ],
    }


def propose(run_parse, tmp_path, plan):
    path = tmp_path / "my-plan.json"
    path.write_text(plan if isinstance(plan, str) else json.dumps(plan))
    return run_parse("propose", "--dest", DEST, "--plan", str(path))


def test_a_valid_plan_returns_and_stores_the_split_proposal(
    run_parse, tmp_path, library, extraction_id
):
    result = propose(run_parse, tmp_path, valid_plan(extraction_id))

    assert result.exit_code == 0, result.stderr
    assert result.json == {
        "source": DEST,
        "pdf": "prml.pdf",
        "pages": 10,
        "proposal": str(library / DEST / "split-proposal.md"),
        "chapters": 1,
        "units": 4,
        "overlaps": 1,
        "overview": (
            "## Split proposal: ml/prml\n"
            "Source: prml.pdf, 10 pages (PDF pages)\n\n"
            "```\n"
            "front-matter  Front matter   1-1\n"
            "chapter-01    Introduction   2-8\n"
            "├─ 1-1        Curve Fitting  2-4\n"
            "└─ 1-2        Probability    4-8\n"
            "references    References     9-10\n"
            "```\n\n"
            "Overlaps: p.4: 1-1/1-2\n"
        ),
    }
    assert (library / DEST / "split-proposal.md").read_text() == result.json["overview"]


def snapshot(library):
    return json.loads((library / DEST / "plan.json").read_text())


def test_multiline_titles_render_as_single_aligned_tree_rows(
    run_parse, tmp_path, library, extraction_id
):
    plan = valid_plan(extraction_id)
    plan["contents"] = [plan_unit("whole", "Whole" + "\n" * 41 + "book", 1, PAGES)]

    result = propose(run_parse, tmp_path, plan)

    assert result.exit_code == 0, result.stderr
    expected = (
        "## Split proposal: ml/prml\n"
        "Source: prml.pdf, 10 pages (PDF pages)\n\n"
        "```\nwhole  Whole book  1-10\n```\n\nOverlaps: none\n"
    )
    assert result.json["overview"] == expected
    assert (library / DEST / "split-proposal.md").read_text() == expected
    assert snapshot(library) == plan


@pytest.mark.parametrize("tree_lines", [40, 41])
def test_overview_uses_the_complete_tree_or_its_first_40_lines(
    run_parse, tmp_path, library, extraction_id, tree_lines
):
    plan = valid_plan(extraction_id)
    plan["contents"] = [
        {
            "id": "chapter-01",
            "title": "Introduction",
            "units": [
                plan_unit(
                    f"unit-{i}",
                    "A much longer final title" if i == tree_lines - 3 else "Section",
                    1,
                    1,
                )
                for i in range(tree_lines - 2)
            ]
            + [plan_unit("last", "Last", 1, PAGES)],
        }
    ]

    result = propose(run_parse, tmp_path, plan)

    assert result.exit_code == 0, result.stderr
    path = library / DEST / "split-proposal.md"
    complete = path.read_text()
    tree = complete.split("```\n")[1].splitlines()
    assert len(tree) == tree_lines
    assert result.json["proposal"] == str(path)
    assert result.json["chapters"] == 1
    assert result.json["units"] == tree_lines - 1
    overview = result.json["overview"]
    if tree_lines == 40:
        assert overview == complete
        assert "Full proposal:" not in overview
    else:
        assert overview.split("```\n")[1].splitlines() == tree[:40] + ["..."]
        assert f"```\n\nFull proposal: {path}\n\nOverlaps:" in overview
        assert overview.split("Overlaps:")[1] == complete.split("Overlaps:")[1]
        assert "..." not in complete


@pytest.mark.parametrize("shared_pages", [0, 10, 11])
def test_overlaps_lists_up_to_ten_shared_pages_then_only_the_count(
    run_parse, tmp_path, library, converter, shared_pages
):
    pages = 12
    converter.document = blank_document(pages)
    started = start_parse(
        run_parse,
        "--no-ocr",
        dest=DEST,
        material_type="textbook",
        pdf=blank_pdf(tmp_path / "book.pdf", pages),
    )
    units = (
        [plan_unit("only", "Whole book", 1, pages)]
        if shared_pages == 0
        else [plan_unit("first", "First", 1, 1)]
        + [plan_unit(f"unit-{i}", "Section", i, i + 1) for i in range(1, shared_pages)]
        + [plan_unit("last", "Last", shared_pages, pages)]
    )
    plan = {"version": 1, "extraction_id": started.json["extraction_id"], "contents": units}

    result = propose(run_parse, tmp_path, plan)

    assert result.exit_code == 0, result.stderr
    assert result.json["overlaps"] == shared_pages
    assert result.json["chapters"] == 0
    assert result.json["units"] == (1 if shared_pages == 0 else shared_pages + 1)
    if shared_pages == 0:
        expected = "Overlaps: none\n"
    elif shared_pages == 10:
        expected = (
            "Overlaps: p.1: first/unit-1; p.2: unit-1/unit-2; p.3: unit-2/unit-3; "
            "p.4: unit-3/unit-4; p.5: unit-4/unit-5; p.6: unit-5/unit-6; "
            "p.7: unit-6/unit-7; p.8: unit-7/unit-8; p.9: unit-8/unit-9; "
            "p.10: unit-9/last\n"
        )
    else:
        expected = "Overlaps: 11 boundary pages shared by adjacent units (visible in the ranges)\n"
    assert result.json["overview"].endswith(expected)
    assert (library / DEST / "split-proposal.md").read_text().endswith(expected)


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

    assert "Preface" in result.json["overview"]
    assert (library / DEST / "split-proposal.md").read_text() == result.json["overview"]
    assert snapshot(library) == revised


def test_an_invalid_plan_reports_every_problem_at_once_and_changes_nothing(
    run_parse, tmp_path, library, extraction_id
):
    approved = valid_plan(extraction_id)
    propose(run_parse, tmp_path, approved)
    before = {
        path.relative_to(library): path.read_bytes()
        for path in library.rglob("*")
        if path.is_file()
    }
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
    assert {
        path.relative_to(library): path.read_bytes()
        for path in library.rglob("*")
        if path.is_file()
    } == before


def _parent(plan, path):
    """Return the container holding the plan field at ``path`` (keys and indexes)."""
    for key in path[:-1]:
        plan = plan[key]
    return plan


def _set(path, value):
    """Return an edit that sets the plan field at ``path`` to ``value``."""

    def edit(plan):
        _parent(plan, path)[path[-1]] = value

    return edit


def _delete(path):
    """Return an edit that removes the plan field at ``path``."""

    def edit(plan):
        del _parent(plan, path)[path[-1]]

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
        (_set((*SECTION_1, "title"), 42), "unit 1-1: title is not a string"),
        (_set(("version",), 1.0), "version 1.0 is not supported: use 1"),
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
        (
            _set(("contents", 2), {"id": "chapter-1", "title": "Refs", "units": []}),
            "chapter chapter-1: same as chapter chapter-01 once numbers are zero-padded",
        ),
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
        plan_unit("1-intro", "Introduction", 2, 4, kind="other"),
        plan_unit("1-1", "Curve Fitting", 4, 4),
        plan_unit("1-2", "Probability", 4, 8),
    ]

    result = propose(run_parse, tmp_path, plan)

    assert result.exit_code == 0, result.stderr
    assert result.json["overlaps"] == 1
    assert "Overlaps: p.4: 1-intro/1-1/1-2\n" in result.json["overview"]


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
    for fragment in ("split-proposal.md", "path", "counts", "overview", "unchanged"):
        assert fragment in result.stdout
    assert "propose" in run_parse("--help").stdout


def test_a_bad_title_or_kind_does_not_hide_page_problems(run_parse, tmp_path, extraction_id):
    plan = valid_plan(extraction_id)
    plan["contents"][0]["title"] = ""
    plan["contents"][1]["units"][0]["kind"] = "exercise"
    plan["contents"][1]["units"][1]["selector"].update(start=3, end=6)

    result = propose(run_parse, tmp_path, plan)

    assert result.error["problems"] == [
        "unit front-matter: empty title",
        "unit 1-1: kind 'exercise' is not section or other",
        "unit 1-2: pages 3-6 overlap unit 1-1 (pages 2-4) by more than one boundary page",
        "pages 7-8 are in no unit",
    ]
