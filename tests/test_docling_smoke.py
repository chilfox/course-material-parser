"""Opt-in smoke test that runs real Docling (``pytest -m docling``)."""

import pytest

from conftest import TEXT_LAYER_PDF
from course_material_parser.docling_conversion import Converted, DoclingConverter

pytestmark = pytest.mark.docling


def test_real_docling_returns_a_document_with_page_provenance():
    outcome = DoclingConverter().convert(TEXT_LAYER_PDF, device="cpu", ocr=False)

    assert isinstance(outcome, Converted), outcome
    assert any(item.prov for item, _ in outcome.document.iterate_items())
