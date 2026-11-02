"""CLI seam: every settings mistake is a ``settings_error`` that says how to fix it."""

import pytest

from conftest import assert_error, start_parse, write_settings
from course_material_parser import settings as settings_module


@pytest.fixture(params=["parse", "read"])
def run_any(request, run_parse, run_read):
    """Run each CLI's simplest command, so a case is checked against both CLIs."""
    if request.param == "parse":
        return lambda: start_parse(run_parse, dest="deck")
    return lambda: run_read("list")


def assert_settings_error(result, *fragments):
    assert_error(result, "settings_error", *fragments)


def test_a_missing_file_says_to_copy_the_example_and_set_the_required_keys(run_any, settings_path):
    settings_path.unlink()

    assert_settings_error(run_any(), "settings.example.toml", "library_root", "device")


def test_an_unknown_key_is_named(run_any, settings_path, library):
    write_settings(settings_path, library, "libary_root = 1\n")

    assert_settings_error(run_any(), "libary_root")


def test_a_missing_library_root_is_named(run_any, settings_path):
    settings_path.write_text('device = "cpu"\n')

    assert_settings_error(run_any(), "library_root")


@pytest.mark.parametrize("value", ['"relative/library"', "42"])
def test_a_library_root_that_is_not_an_absolute_path_is_rejected(run_any, settings_path, value):
    settings_path.write_text(f'library_root = {value}\ndevice = "cpu"\n')

    assert_settings_error(run_any(), "library_root", "absolute")


def test_a_library_root_that_does_not_exist_is_rejected_and_not_created(
    run_any, settings_path, tmp_path
):
    missing = tmp_path / "no-such-library"
    write_settings(settings_path, missing)

    assert_settings_error(run_any(), "library_root", str(missing))
    assert not missing.exists()


def test_a_library_root_that_is_a_file_is_rejected(run_any, settings_path, tmp_path):
    file = tmp_path / "library.txt"
    file.write_text("")
    write_settings(settings_path, file)

    assert_settings_error(run_any(), "library_root", "directory")


def test_a_tilde_library_root_is_expanded(run_read, settings_path, tmp_path, monkeypatch):
    home = tmp_path / "home"
    (home / "course-library").mkdir(parents=True)
    monkeypatch.setenv("HOME", str(home))
    write_settings(settings_path, "~/course-library")

    result = run_read("list")

    assert result.exit_code == 0, result.stderr
    assert result.json == {"materials": []}


@pytest.mark.parametrize("value", ['"tpu"', '"auto"', "1"])
def test_an_invalid_device_is_rejected(run_any, settings_path, library, value):
    settings_path.write_text(f'library_root = "{library}"\ndevice = {value}\n')

    assert_settings_error(run_any(), "device", "cpu, mps, cuda")


def test_parse_start_reports_an_unavailable_device_ahead_of_an_invalid_destination(
    run_parse, settings_path, library, monkeypatch
):
    monkeypatch.setattr(settings_module, "device_available", lambda device: device == "cpu")
    write_settings(settings_path, library, device="cuda")

    result = run_parse("start", "--pdf", "missing.pdf", "--dest", "../x", "--type", "slides")

    assert_settings_error(result, "device", "cuda", "not available")


def test_read_does_not_need_the_device_to_be_available(
    run_read, settings_path, library, monkeypatch
):
    monkeypatch.setattr(settings_module, "device_available", lambda device: device == "cpu")
    write_settings(settings_path, library, device="cuda")

    assert run_read("list").exit_code == 0


@pytest.mark.parametrize("value", ["0", "-5", "1.5", '"60000"', "true"])
def test_an_invalid_combined_read_max_chars_is_rejected(run_any, settings_path, library, value):
    write_settings(settings_path, library, f"combined_read_max_chars = {value}\n")

    assert_settings_error(run_any(), "combined_read_max_chars", "positive integer")


@pytest.mark.parametrize("value", ['"yes"', "1"])
def test_an_invalid_allow_ocr_is_rejected(run_any, settings_path, library, value):
    write_settings(settings_path, library, f"allow_ocr = {value}\n")

    assert_settings_error(run_any(), "allow_ocr", "true or false")


def test_invalid_toml_is_rejected(run_any, settings_path):
    settings_path.write_text("library_root = \n")

    assert_settings_error(run_any(), "TOML")


def test_settings_errors_come_before_anything_is_created(run_parse, settings_path, library):
    write_settings(settings_path, library, "allow_ocr = 1\n")

    start_parse(run_parse, dest="deck")

    assert list(library.iterdir()) == []
