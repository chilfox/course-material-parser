"""CLI seam: parse start decides on OCR from the text layer and the user's permission."""

import pytest

from conftest import IMAGE_ONLY_PDF, TEXT_LAYER_PDF, assert_error


def start(run_parse, pdf, *flags):
    return run_parse("start", "--pdf", str(pdf), "--dest", "ml/deck", "--type", "slides", *flags)


def allow_ocr(settings_path, allowed: bool) -> None:
    settings_path.write_text(
        settings_path.read_text() + f"allow_ocr = {'true' if allowed else 'false'}\n"
    )


@pytest.mark.parametrize("allowed", [True, False])
def test_a_scanned_pdf_without_an_ocr_flag_is_refused_with_the_page_count(
    run_parse, settings_path, library, converter, allowed
):
    allow_ocr(settings_path, allowed)

    result = start(run_parse, IMAGE_ONLY_PDF)

    assert_error(result, "ocr_required", "1 of 1 pages have no text layer; this looks scanned")
    assert ("disabled" in result.error["message"]) is not allowed
    assert converter.calls == []
    assert list(library.iterdir()) == []


# allow_ocr x {no flag, --ocr, --no-ocr} x {text PDF, scanned PDF}, for every combination
# that converts: the OCR choice that reaches the converter.
@pytest.mark.parametrize("allowed", [True, False])
@pytest.mark.parametrize(
    ("pdf", "flags", "expected_ocr"),
    [
        (TEXT_LAYER_PDF, [], False),
        (TEXT_LAYER_PDF, ["--no-ocr"], False),
        (IMAGE_ONLY_PDF, ["--no-ocr"], False),
    ],
)
def test_parsing_without_ocr_converts_without_it(
    run_parse, settings_path, converter, allowed, pdf, flags, expected_ocr
):
    allow_ocr(settings_path, allowed)

    result = start(run_parse, pdf, *flags)

    assert result.exit_code == 0, result.stderr
    assert converter.calls == [{"ocr": expected_ocr}]


@pytest.mark.parametrize("pdf", [TEXT_LAYER_PDF, IMAGE_ONLY_PDF])
def test_ocr_flag_converts_with_ocr_when_allowed(run_parse, settings_path, converter, pdf):
    allow_ocr(settings_path, True)

    result = start(run_parse, pdf, "--ocr")

    assert result.exit_code == 0, result.stderr
    assert converter.calls == [{"ocr": True}]


@pytest.mark.parametrize("pdf", [TEXT_LAYER_PDF, IMAGE_ONLY_PDF])
def test_ocr_flag_is_refused_before_the_destination_exists_when_ocr_is_disabled(
    run_parse, settings_path, library, converter, pdf
):
    allow_ocr(settings_path, False)

    result = start(run_parse, pdf, "--ocr")

    assert_error(result, "ocr_disabled", "allow_ocr = false")
    assert converter.calls == []
    assert list(library.iterdir()) == []


def test_ocr_and_no_ocr_are_mutually_exclusive(run_parse, library, converter):
    result = start(run_parse, TEXT_LAYER_PDF, "--ocr", "--no-ocr")

    assert_error(result, "invalid_request", "--no-ocr", "--ocr")
    assert converter.calls == []
    assert list(library.iterdir()) == []


def test_start_help_documents_the_ocr_flags(run_parse):
    result = run_parse("start", "--help")

    assert result.exit_code == 0
    for text in ("--ocr", "--no-ocr", "ocr_required", "ocr_disabled", "allow_ocr"):
        assert text in result.stdout
