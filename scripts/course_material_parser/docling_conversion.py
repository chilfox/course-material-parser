"""The Docling boundary: the only code that imports Docling.

``DoclingConverter`` turns a source PDF into a DoclingDocument with formula enrichment on,
and reports success, failure, and partial conversion as distinct outcomes. Entry points
accept any object with the same ``convert`` method, so tests inject a fake.
``save_document`` and ``load_document`` store a converted document as DoclingDocument JSON
and load it back, so a textbook is split later without converting again.
"""

import os
import sys
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from docling_core.types.doc import DoclingDocument, ImageRefMode


@dataclass(frozen=True)
class Converted:
    """Docling converted the whole PDF."""

    document: DoclingDocument


@dataclass(frozen=True)
class PartiallyConverted:
    """Docling converted only part of the PDF; ``message`` says what went wrong."""

    document: DoclingDocument
    message: str


@dataclass(frozen=True)
class ConversionFailed:
    """Docling produced no usable document; ``message`` says why."""

    message: str


ConversionOutcome = Converted | PartiallyConverted | ConversionFailed


class Converter(Protocol):
    """Anything that converts a source PDF into a ``ConversionOutcome``."""

    def convert(self, pdf: Path, *, device: str, ocr: bool) -> ConversionOutcome:
        """Convert ``pdf`` on ``device`` (``cpu``, ``mps``, or ``cuda``), with OCR if ``ocr``."""
        ...


def save_document(document: DoclingDocument, path: Path) -> None:
    """Save ``document`` as DoclingDocument JSON at ``path``, everything except images.

    Picture image data is left out: renders come from the retained source PDF, and
    embedded images would make the stored extraction of a long textbook very large.
    """
    document.save_as_json(path, image_mode=ImageRefMode.PLACEHOLDER)


def load_document(path: Path) -> DoclingDocument:
    """Load the DoclingDocument saved by ``save_document`` at ``path``."""
    return DoclingDocument.load_from_json(path)


class DoclingConverter:
    """Convert PDFs with locally run Docling, loading models from the prefetched directory."""

    def convert(self, pdf: Path, *, device: str, ocr: bool) -> ConversionOutcome:
        """Convert ``pdf`` with formula enrichment on and return the outcome.

        Models come from the ``docling-tools models download`` directory, so conversion
        works offline. With ``device = "mps"`` the formula model runs on CPU, because
        Docling doesn't support MPS for CodeFormulaV2. An exception raised inside Docling
        is reported as ``ConversionFailed``.
        """
        try:
            with _console_silenced():
                return self._convert(pdf, device=device, ocr=ocr)
        except Exception as error:
            return ConversionFailed(message=f"{type(error).__name__}: {error}")

    def _convert(self, pdf: Path, *, device: str, ocr: bool) -> ConversionOutcome:
        # Imported here so that `parse --help` and argument errors don't pay Docling's
        # multi-second import time.
        from docling.datamodel.accelerator_options import AcceleratorDevice, AcceleratorOptions
        from docling.datamodel.base_models import ConversionStatus, InputFormat
        from docling.datamodel.pipeline_options import CodeFormulaVlmOptions, PdfPipelineOptions
        from docling.datamodel.settings import settings as docling_settings
        from docling.datamodel.vlm_engine_options import TransformersVlmEngineOptions
        from docling.document_converter import DocumentConverter, PdfFormatOption

        accelerator = AcceleratorDevice(device)
        options = PdfPipelineOptions(
            artifacts_path=docling_settings.cache_dir / "models",
            accelerator_options=AcceleratorOptions(device=accelerator),
            do_ocr=ocr,
            do_formula_enrichment=True,
        )
        if accelerator is AcceleratorDevice.MPS:
            options.code_formula_options = CodeFormulaVlmOptions.from_preset(
                "codeformulav2",
                engine_options=TransformersVlmEngineOptions(device=AcceleratorDevice.CPU),
            )
        converter = DocumentConverter(
            format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=options)}
        )
        result = converter.convert(pdf, raises_on_error=False)
        message = "; ".join(error.error_message for error in result.errors)
        if result.status is ConversionStatus.SUCCESS:
            return Converted(document=result.document)
        if result.status is ConversionStatus.PARTIAL_SUCCESS:
            return PartiallyConverted(
                document=result.document, message=message or "some pages failed to convert"
            )
        return ConversionFailed(message=message or f"conversion ended as {result.status.value}")


@contextmanager
def _console_silenced() -> Iterator[None]:
    """Discard everything written to stdout and stderr, including by native code.

    The CLIs promise exactly one JSON result on stdout and, on failure, exactly one JSON
    error on stderr. Docling's logs, warnings, and progress bars would break that, and
    some come from native libraries, so the file descriptors are redirected, not just
    ``sys.stdout`` and ``sys.stderr``.
    """
    sys.stdout.flush()
    sys.stderr.flush()
    saved = {fd: os.dup(fd) for fd in (1, 2)}
    with tempfile.TemporaryFile() as sink:
        try:
            for fd in saved:
                os.dup2(sink.fileno(), fd)
            yield
        finally:
            sys.stdout.flush()
            sys.stderr.flush()
            for fd, original in saved.items():
                os.dup2(original, fd)
                os.close(original)
