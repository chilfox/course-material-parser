"""CLI seam: the shared output contract, settings errors, and help text of both CLIs."""

import subprocess
import sys

import pytest
from conftest import TEXT_LAYER_PDF


def assert_error(result, code):
    assert result.exit_code == 1
    assert result.stdout == ""
    assert result.error["error"] == code
    assert result.error["message"]


@pytest.mark.parametrize(
    "argv",
    [
        [],
        ["start", "--pdf", "x.pdf", "--dest", "m"],
        ["start", "--pdf", "x.pdf", "--dest", "m", "--type", "poster"],
        ["frobnicate"],
    ],
)
def test_parse_usage_errors_are_invalid_request(run_parse, argv):
    assert_error(run_parse(*argv), "invalid_request")


@pytest.mark.parametrize("argv", [[], ["get"], ["list", "--bogus"]])
def test_read_usage_errors_are_invalid_request(run_read, argv):
    assert_error(run_read(*argv), "invalid_request")


def test_reading_an_unknown_source_is_not_found(run_read):
    result = run_read("get", "--source", "ml/nothing")

    assert_error(result, "not_found")
    assert "ml/nothing" in result.error["message"]


def test_missing_settings_file_tells_how_to_fix_it(run_read, settings_path):
    settings_path.unlink()

    result = run_read("list")

    assert_error(result, "settings_error")
    assert "settings.example.toml" in result.error["message"]


def test_settings_without_a_required_key_are_rejected(run_parse, settings_path):
    settings_path.write_text('device = "cpu"\n')

    result = run_parse("start", "--pdf", str(TEXT_LAYER_PDF), "--dest", "m", "--type", "slides")

    assert_error(result, "settings_error")
    assert "library_root" in result.error["message"]


@pytest.mark.parametrize("partial", [False, True])
def test_unsuccessful_conversion_fails_the_parse_and_hides_the_material(
    run_parse, run_read, converter, partial
):
    converter.failure = "page 2 timed out"
    converter.partial = partial

    result = run_parse(
        "start", "--pdf", str(TEXT_LAYER_PDF), "--dest", "ml/deck", "--type", "slides"
    )

    assert_error(result, "conversion_failed")
    assert "page 2 timed out" in result.error["message"]
    assert run_read("list").json == {"materials": []}


@pytest.mark.parametrize("run", ["run_parse", "run_read"])
def test_top_level_help_explains_material_ids_and_source_pages(request, run):
    result = request.getfixturevalue(run)("--help")

    assert result.exit_code == 0
    assert "folder path under library_root, for example ml/prml" in result.stdout
    assert "source-PDF pages counted from 1" in result.stdout


def test_the_reader_never_imports_docling(run_parse, settings_path):
    run_parse("start", "--pdf", str(TEXT_LAYER_PDF), "--dest", "deck", "--type", "slides")
    script = (
        "import sys\n"
        "from pathlib import Path\n"
        "from course_material_parser import read_command\n"
        "read_command.main(['get', '--source', 'deck'], settings_path=Path(sys.argv[1]))\n"
        "loaded = [m for m in sys.modules if m.split('.')[0] in {'docling', 'docling_core'}]\n"
        "assert not loaded, sorted(loaded)\n"
    )

    result = subprocess.run(
        [sys.executable, "-c", script, str(settings_path)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "<page 1>" in result.stdout


def test_an_unknown_device_is_a_settings_error_before_anything_is_created(
    run_parse, settings_path, library
):
    settings_path.write_text(f'library_root = "{library}"\ndevice = "tpu"\n')

    result = run_parse("start", "--pdf", str(TEXT_LAYER_PDF), "--dest", "m", "--type", "slides")

    assert_error(result, "settings_error")
    assert "device" in result.error["message"]
    assert list(library.iterdir()) == []


def test_an_unexpected_failure_is_reported_as_internal_error(run_parse, run_read, library):
    run_parse("start", "--pdf", str(TEXT_LAYER_PDF), "--dest", "deck", "--type", "slides")
    (library / "deck" / "material.json").write_text("{not json")

    assert_error(run_read("get", "--source", "deck"), "internal_error")
