"""Opt-in smoke test that runs real Docling (``pytest -m docling``)."""

import platform

import pytest

from conftest import FIXTURES, TEXT_LAYER_PDF
from course_material_parser.docling_conversion import Converted, DoclingConverter
from course_material_parser.settings import load_settings

pytestmark = pytest.mark.docling


@pytest.mark.skipif(
    platform.system() != "Darwin" or platform.machine() != "arm64",
    reason="MLX requires Apple Silicon macOS",
)
def test_mps_returns_formula_latex_without_cpu_fallback():
    converter = DoclingConverter()
    assert converter.missing_models(device="mps", ocr=False) == []
    outcome = converter.convert(FIXTURES / "formula.pdf", device="mps", ocr=False)

    assert isinstance(outcome, Converted), outcome
    formulas = [
        item.text for item, _ in outcome.document.iterate_items() if item.label == "formula"
    ]
    assert formulas == [r"\frac { a } { b } \, = \, \frac { c } { d }"]


def test_downloaded_models_cover_real_preflight():
    assert DoclingConverter().missing_models(device="cpu", ocr=True) == []


def test_downloaded_models_cover_current_settings_real_preflight():
    settings = load_settings()

    assert DoclingConverter().missing_models(device=settings.device, ocr=settings.allow_ocr) == []


def test_real_docling_returns_a_document_with_page_provenance():
    outcome = DoclingConverter().convert(TEXT_LAYER_PDF, device="cpu", ocr=False)

    assert isinstance(outcome, Converted), outcome
    assert any(item.prov for item, _ in outcome.document.iterate_items())
