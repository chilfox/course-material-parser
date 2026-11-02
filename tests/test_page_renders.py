"""CLI seam: agents render source pages to PNG, and the user cleans the renders up."""

from pathlib import Path

import pytest

from conftest import assert_error, parse_slides, start_parse

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def test_render_returns_page_files_in_request_order(run_parse, run_read):
    parse_slides(run_parse)

    result = run_read("render", "--source", "ml/week3-slides", "--pages", "2,1")

    assert result.exit_code == 0, result.stderr
    output = result.json
    assert output["pages"] == [{"page": 2, "file": "page_2.png"}, {"page": 1, "file": "page_1.png"}]
    render_dir = Path(output["dir"])
    assert render_dir.is_absolute()
    for entry in output["pages"]:
        assert (render_dir / entry["file"]).read_bytes().startswith(PNG_SIGNATURE)


def test_existing_renders_are_reused_and_a_deleted_one_is_recreated(run_parse, run_read):
    parse_slides(run_parse)
    first = run_read("render", "--source", "ml/week3-slides", "--pages", "1-2").json
    render_dir = Path(first["dir"])
    reused = render_dir / "page_1.png"
    reused.write_bytes(PNG_SIGNATURE + b"cached")
    (render_dir / "page_2.png").unlink()

    second = run_read("render", "--source", "ml/week3-slides", "--pages", "1-2")

    assert second.exit_code == 0, second.stderr
    assert second.json == first
    assert reused.read_bytes() == PNG_SIGNATURE + b"cached"
    assert (render_dir / "page_2.png").read_bytes().startswith(PNG_SIGNATURE)


def test_rendering_leaves_only_the_page_files_behind(run_parse, run_read):
    parse_slides(run_parse)

    output = run_read("render", "--source", "ml/week3-slides", "--pages", "1,2,1").json

    assert output["pages"] == [
        {"page": 1, "file": "page_1.png"},
        {"page": 2, "file": "page_2.png"},
        {"page": 1, "file": "page_1.png"},
    ]
    assert sorted(p.name for p in Path(output["dir"]).iterdir()) == ["page_1.png", "page_2.png"]


@pytest.mark.parametrize("pages", ["1,3", "0", "2-1", "p.1"])
def test_one_bad_page_fails_the_whole_render_request(run_parse, run_read, pages):
    parse_slides(run_parse)

    result = run_read("render", "--source", "ml/week3-slides", "--pages", pages)

    assert_error(result, "invalid_request")


@pytest.mark.parametrize("damage", ["corrupt", "missing"])
def test_an_unrenderable_source_fails_with_render_failed(run_parse, run_read, library, damage):
    parse_slides(run_parse)
    source = library / "ml/week3-slides/source.pdf"
    if damage == "corrupt":
        source.write_bytes(b"not a pdf")
    else:
        source.unlink()

    result = run_read("render", "--source", "ml/week3-slides", "--pages", "1")

    assert_error(result, "render_failed", "ml/week3-slides", "source.pdf")
    reason = {"corrupt": "not a readable PDF", "missing": "not found"}[damage]
    assert reason in result.error["message"]
    assert "None" not in result.error["message"]


def test_renders_are_only_for_ready_material(run_parse, run_read, converter):
    converter.failure = "page 2 timed out"
    start_parse(run_parse)

    for source in ["ml/deck", "ml/nothing"]:
        result = run_read("render", "--source", source, "--pages", "1")
        assert_error(result, "not_found", source)


def test_clean_renders_of_one_source_reports_files_and_bytes_removed(run_parse, run_read):
    parse_slides(run_parse, "ml/a")
    parse_slides(run_parse, "ml/b")
    a_dir = Path(run_read("render", "--source", "ml/a", "--pages", "1-2").json["dir"])
    b_dir = Path(run_read("render", "--source", "ml/b", "--pages", "1").json["dir"])
    a_bytes = sum(p.stat().st_size for p in a_dir.iterdir())

    result = run_read("clean-renders", "--source", "ml/a")

    assert result.exit_code == 0, result.stderr
    assert result.json == {"files": 2, "bytes": a_bytes}
    assert not list(a_dir.glob("*.png"))
    assert (b_dir / "page_1.png").is_file()


def test_rendering_after_cleanup_recreates_the_files(run_parse, run_read):
    parse_slides(run_parse)
    run_read("render", "--source", "ml/week3-slides", "--pages", "1")
    run_read("clean-renders", "--source", "ml/week3-slides")

    output = run_read("render", "--source", "ml/week3-slides", "--pages", "1").json

    assert (Path(output["dir"]) / "page_1.png").is_file()


def test_clean_renders_all_without_confirm_deletes_nothing(run_parse, run_read):
    parse_slides(run_parse)
    render_dir = Path(run_read("render", "--source", "ml/week3-slides", "--pages", "1").json["dir"])

    result = run_read("clean-renders", "--all")

    assert_error(result, "confirm_required", "--confirm")
    assert (render_dir / "page_1.png").is_file()


def test_clean_renders_all_with_confirm_removes_every_materials_renders(run_parse, run_read):
    parse_slides(run_parse, "ml/a")
    parse_slides(run_parse, "physics/b")
    run_read("render", "--source", "ml/a", "--pages", "1-2")
    run_read("render", "--source", "physics/b", "--pages", "2")

    result = run_read("clean-renders", "--all", "--confirm")

    assert result.exit_code == 0, result.stderr
    assert result.json["files"] == 3
    assert result.json["bytes"] > 0
    assert run_read("clean-renders", "--all", "--confirm").json == {"files": 0, "bytes": 0}


@pytest.mark.parametrize("argv", [[], ["--source", "ml/a", "--all"], ["--confirm"]])
def test_clean_renders_needs_exactly_one_scope(run_read, argv):
    assert_error(run_read("clean-renders", *argv), "invalid_request")


def test_clean_renders_of_an_unknown_source_is_not_found(run_read):
    assert_error(run_read("clean-renders", "--source", "ml/nothing"), "not_found", "ml/nothing")


def test_render_help_gives_the_spec_syntax_and_the_file_lifetime(run_read):
    result = run_read("render", "--help")

    assert result.exit_code == 0
    help_text = " ".join(result.stdout.split())
    assert "28, 15-30, or 3,7,15-18" in help_text
    assert (
        "files stay available until the user cleans them up; "
        "rendering a page again recreates its file"
    ) in help_text.lower()
    assert "dir" in help_text


def test_clean_renders_help_says_to_run_it_only_when_the_user_asks(run_read):
    result = run_read("clean-renders", "--help")

    assert result.exit_code == 0
    assert "Deletes rendered page images. Run only when the user asks." in result.stdout


def test_read_help_lists_render_and_clean_renders(run_read):
    help_text = run_read("--help").stdout

    assert "render" in help_text and "clean-renders" in help_text
