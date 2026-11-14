"""The Docling boundary: the only code that imports Docling.

``DoclingConverter`` turns a source PDF into a DoclingDocument with formula enrichment on,
and reports success, failure, and partial conversion as distinct outcomes. Entry points
accept any object with the same ``convert`` and ``missing_models`` methods, so tests
inject a fake.
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

    def missing_models(self, *, device: str, ocr: bool) -> list[str]:
        """Name required models absent from the local model directory."""
        ...

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


MLX_FORMULA_REPO = "mlx-community/CodeFormulaV2-mlx-bf16"
MLX_FORMULA_REVISION = "f29c446f17d772025137fabc11288f07769c316f"


@dataclass(frozen=True)
class Model:
    """A model's human-readable name and folder in Docling's model directory."""

    name: str
    folder: str
    repo_id: str | None = None
    revision: str | None = None


def required_models(*, device: str, ocr: bool) -> tuple[Model, ...]:
    """Return the models conversion loads on ``device``, with OCR only if requested."""
    formula = (
        Model(
            "CodeFormulaV2 (MLX)",
            MLX_FORMULA_REPO.replace("/", "--"),
            MLX_FORMULA_REPO,
            MLX_FORMULA_REVISION,
        )
        if device == "mps"
        else Model("CodeFormulaV2", "docling-project--CodeFormulaV2")
    )
    models = (
        Model("docling-layout-heron", "docling-project--docling-layout-heron"),
        Model("TableFormer", "docling-project--docling-models"),
        Model("DocumentFigureClassifier-v2.5", "docling-project--DocumentFigureClassifier-v2.5"),
        formula,
    )
    if ocr:
        models += (Model("RapidOCR", "RapidOcr"),)
    return models


def models_directory() -> Path:
    """Return the same directory used as conversion's ``artifacts_path``."""
    from docling.datamodel.settings import settings as docling_settings

    return docling_settings.cache_dir / "models"


def download_model(model: Model, directory: Path) -> None:
    """Fetch one model through Docling's downloaders, without deleting other models."""
    from docling.datamodel.pipeline_options import LayoutObjectDetectionOptions
    from docling.models.utils.hf_model_download import download_hf_model
    from docling.utils.model_downloader import download_models

    with _console_silenced():
        if model.repo_id is not None:
            from huggingface_hub import snapshot_download

            snapshot_download(
                repo_id=model.repo_id,
                revision=model.revision,
                local_dir=directory / model.folder,
            )
            return
        if model.name == "docling-layout-heron":
            spec = LayoutObjectDetectionOptions().model_spec
            download_hf_model(
                repo_id=spec.repo_id,
                revision=spec.revision,
                local_dir=directory / model.folder,
                force=False,
                progress=False,
            )
            return
        download_models(
            output_dir=directory,
            with_layout=False,
            with_tableformer=model.name == "TableFormer",
            with_picture_classifier=model.name == "DocumentFigureClassifier-v2.5",
            with_code_formula=model.name == "CodeFormulaV2",
            with_rapidocr=model.name == "RapidOCR",
            rapidocr_models=["torch:ch"] if model.name == "RapidOCR" else None,
        )


class DoclingConverter:
    """Convert PDFs with locally run Docling, loading models from the prefetched directory."""

    def __init__(self, *, model_directory: Path | None = None) -> None:
        """Use Docling's model directory unless a caller supplies another."""
        self._model_directory = model_directory

    @property
    def model_directory(self) -> Path:
        """The directory both pre-flight and conversion read."""
        return self._model_directory if self._model_directory is not None else models_directory()

    def missing_models(self, *, device: str, ocr: bool) -> list[str]:
        """Name required models whose folders are absent."""
        directory = self.model_directory
        return [
            model.name
            for model in required_models(device=device, ocr=ocr)
            if not (directory / model.folder).is_dir()
        ]

    def convert(self, pdf: Path, *, device: str, ocr: bool) -> ConversionOutcome:
        """Convert ``pdf`` with formula enrichment on and return the outcome.

        Models come from the ``download-models`` directory, so conversion
        works offline. With ``device = "mps"`` the formula model uses MLX on the GPU,
        without a CPU fallback. An exception raised inside Docling
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
        from docling.datamodel.stage_model_specs import EngineModelConfig
        from docling.datamodel.vlm_engine_options import (
            MlxVlmEngineOptions,
            TransformersVlmEngineOptions,
            VlmEngineType,
        )
        from docling.document_converter import DocumentConverter, PdfFormatOption

        accelerator = AcceleratorDevice(device)
        options = PdfPipelineOptions(
            artifacts_path=self.model_directory,
            accelerator_options=AcceleratorOptions(device=accelerator),
            do_ocr=ocr,
            do_formula_enrichment=True,
        )
        if accelerator is AcceleratorDevice.MPS:
            formula = CodeFormulaVlmOptions.from_preset(
                "codeformulav2", engine_options=MlxVlmEngineOptions()
            )
            formula.model_spec.engine_overrides = {
                **formula.model_spec.engine_overrides,
                VlmEngineType.MLX: EngineModelConfig(repo_id=MLX_FORMULA_REPO),
            }
            options.code_formula_options = formula
        elif accelerator is AcceleratorDevice.CPU:
            options.code_formula_options = CodeFormulaVlmOptions.from_preset(
                "codeformulav2",
                engine_options=TransformersVlmEngineOptions(
                    device=AcceleratorDevice.CPU, torch_dtype="float32"
                ),
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
