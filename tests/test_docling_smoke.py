"""Opt-in real Docling checks (``pytest -m docling``).

Current-settings preflight requires completed setup and never skips. Conversion
smokes additionally exercise CPU and MPS without OCR, skipping when that device's
optional weights were not installed by the settings-specific setup.
"""

import platform

import pytest

from conftest import FIXTURES, TEXT_LAYER_PDF
from course_material_parser.docling_conversion import Converted, DoclingConverter
from course_material_parser.settings import load_settings

pytestmark = pytest.mark.docling


def _converter_with_models(device: str) -> DoclingConverter:
    converter = DoclingConverter()
    missing = converter.missing_models(device=device, ocr=False)
    if missing:
        pytest.skip(
            f"Optional {device} conversion smoke needs {', '.join(missing)} in "
            f'{converter.model_directory}; to install, set device = "{device}" in '
            "settings.toml and run uv run download-models, then restore your settings"
        )
    return converter


@pytest.mark.skipif(
    platform.system() != "Darwin" or platform.machine() != "arm64",
    reason="MLX requires Apple Silicon macOS",
)
def test_mps_returns_formula_latex_without_cpu_fallback():
    converter = _converter_with_models("mps")
    outcome = converter.convert(FIXTURES / "formula.pdf", device="mps", ocr=False)

    assert isinstance(outcome, Converted), outcome
    formulas = [
        item.text for item, _ in outcome.document.iterate_items() if item.label == "formula"
    ]
    assert formulas == [r"\frac { a } { b } \, = \, \frac { c } { d }"]


def test_downloaded_models_cover_current_settings_real_preflight():
    settings = load_settings()

    missing = DoclingConverter().missing_models(device=settings.device, ocr=settings.allow_ocr)
    assert missing == [], (
        f"Missing configured models: {', '.join(missing)}; run uv run download-models"
    )


def test_real_docling_returns_a_document_with_page_provenance():
    converter = _converter_with_models("cpu")
    outcome = converter.convert(TEXT_LAYER_PDF, device="cpu", ocr=False)

    assert isinstance(outcome, Converted), outcome
    assert any(item.prov for item, _ in outcome.document.iterate_items())
