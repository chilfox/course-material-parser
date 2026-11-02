"""Entry point for the ``parse`` CLI, which converts source PDFs into parsed material.

Every type of material goes through one pipeline (settings, destination, creation, PDF
copy, conversion, stored output) that branches on the type only when writing contents.
"""

import argparse
import shutil
from collections.abc import Callable, Sequence
from pathlib import Path

from course_material_parser import material_store, pdf
from course_material_parser.cli_output import CliError, JsonArgumentParser, json_line, run_cli
from course_material_parser.docling_conversion import (
    ConversionFailed,
    ConversionOutcome,
    Converter,
    PartiallyConverted,
)
from course_material_parser.markdown_writer import PdfPages, write_markdown
from course_material_parser.material_store import MaterialRecord, MaterialType, Status
from course_material_parser.provenance import missing_provenance
from course_material_parser.settings import Settings, load_settings, require_device_available

_DESCRIPTION = """\
Convert a source PDF into parsed material stored under library_root.

MATERIAL is the material's folder path under library_root, for example ml/prml.
Page numbers are always source-PDF pages counted from 1, not printed page numbers.

commands:
  start   parse a source PDF into a new material

See `parse <command> --help` for details."""

_START_DESCRIPTION = """\
Parse the source PDF into a new material at MATERIAL. The destination must not exist;
missing parent folders are created. Slides become one Markdown deck with a marker per
source page and are ready to read when this command succeeds.

OCR: without --ocr or --no-ocr, the PDF's text layer is checked first, and the parse is
refused with ocr_required, reporting the count, when more than half the pages have no
text layer. Then decide: --ocr to convert with OCR (refused with ocr_disabled when
allow_ocr = false in settings.toml), or --no-ocr when only page renders matter, which
skips the check."""


def main(
    argv: Sequence[str] | None = None,
    *,
    settings_path: Path | None = None,
    converter: Converter | None = None,
) -> int:
    """Run the CLI with ``argv`` (default ``sys.argv[1:]``) and return the exit code.

    ``settings_path`` and ``converter`` default to the skill's ``settings.toml`` and real
    Docling; tests inject their own.
    """
    return run_cli(lambda: _run(argv, settings_path, converter))


def _run(
    argv: Sequence[str] | None, settings_path: Path | None, converter: Converter | None
) -> str:
    args = _build_parser().parse_args(argv)
    settings = load_settings(settings_path)
    return json_line(_start(args, settings, converter))


def _build_parser() -> argparse.ArgumentParser:
    parser = JsonArgumentParser(
        prog="parse", description=_DESCRIPTION, formatter_class=argparse.RawTextHelpFormatter
    )
    commands = parser.add_subparsers(dest="command", required=True, metavar="<command>")
    start = commands.add_parser(
        "start",
        description=_START_DESCRIPTION,
        help="parse a source PDF into a new material",
    )
    start.add_argument("--pdf", required=True, type=Path, metavar="PATH", help="source PDF")
    start.add_argument(
        "--dest", required=True, metavar="MATERIAL", help="new material folder under library_root"
    )
    start.add_argument(
        "--type", required=True, choices=[t.value for t in MaterialType], help="kind of source PDF"
    )
    ocr = start.add_mutually_exclusive_group()
    ocr.add_argument(
        "--ocr",
        dest="ocr",
        action="store_const",
        const=True,
        help="convert with OCR; refused when allow_ocr = false in settings.toml",
    )
    ocr.add_argument(
        "--no-ocr",
        dest="ocr",
        action="store_const",
        const=False,
        help="convert without OCR and skip the text-layer check",
    )
    return parser


def _check_ocr_choice(source: Path, ocr: bool | None, settings: Settings) -> None:
    """Refuse an OCR choice the PDF or the user's permission rules out.

    ``ocr`` is ``True`` for ``--ocr``, ``False`` for ``--no-ocr``, and ``None`` without a
    flag, which runs the text-layer pre-check.

    Raises:
        CliError: ``ocr_disabled`` for ``--ocr`` when ``allow_ocr = false``;
            ``ocr_required`` without a flag when the PDF looks scanned.
    """
    if ocr is True and not settings.allow_ocr:
        raise CliError(
            "ocr_disabled",
            "--ocr is not allowed: OCR is disabled in settings.toml (allow_ocr = false); "
            "tell the user",
        )
    if ocr is not None:
        return
    layer = _read_pdf(pdf.text_layer, source)
    if not layer.looks_scanned:
        return
    message = (
        f"{layer.pages_without_text} of {layer.pages} pages have no text layer; this looks scanned"
    )
    if settings.allow_ocr:
        message += "; re-run with --ocr, or --no-ocr if only page renders matter"
    else:
        message += (
            "; OCR is disabled in settings.toml (allow_ocr = false), so tell the user, "
            "or re-run with --no-ocr if only page renders matter"
        )
    raise CliError("ocr_required", message)


def _read_pdf[T](read: Callable[[Path], T], source: Path) -> T:
    """Return ``read(source)``, refusing a source PDF that can't be read.

    Raises:
        CliError: ``invalid_request`` when ``source`` isn't a readable PDF.
    """
    try:
        return read(source)
    except pdf.PdfError as error:
        raise CliError("invalid_request", str(error)) from None


def _start(args: argparse.Namespace, settings: Settings, converter: Converter | None) -> dict:
    # Only start converts, so only it checks the device: that imports torch, which the
    # other subcommands never need.
    require_device_available(settings)
    if converter is None:
        from course_material_parser.docling_conversion import DoclingConverter

        converter = DoclingConverter()
    # Every refusal comes before anything is created, so a mistake changes nothing.
    material_store.check_destination(settings.library_root, args.dest)
    source: Path = args.pdf
    if not source.is_file():
        raise CliError("not_found", f"PDF not found: {source}")
    pages = _read_pdf(pdf.page_count, source)
    _check_ocr_choice(source, args.ocr, settings)

    material_type = MaterialType(args.type)
    destination = material_store.create_destination(settings.library_root, args.dest)
    retained_pdf = material_store.source_pdf(destination)
    shutil.copyfile(source, retained_pdf)
    outcome = converter.convert(retained_pdf, device=settings.device, ocr=bool(args.ocr))

    def record(status: Status) -> MaterialRecord:
        return MaterialRecord(
            type=material_type, status=status, source_filename=source.name, pages=pages
        )

    problem = _conversion_problem(outcome)
    if problem is not None:
        raise _fail(destination, record(Status.FAILED), args.dest, problem)

    material_store.write_slides(
        destination, write_markdown(outcome.document, PdfPages(start=1, end=pages))
    )
    # Written last, so a material is only ever visible as ready once all its contents exist.
    material_store.write_record(destination, record(Status.READY))
    return {"source": args.dest, "type": material_type, "status": Status.READY, "pages": pages}


def _conversion_problem(outcome: ConversionOutcome) -> str | None:
    """Return why ``outcome`` can't be published, or ``None`` when it can.

    A partial conversion is never published, and neither is a document with a body item
    that has no source page, because that item would be dropped or misplaced.
    """
    if isinstance(outcome, PartiallyConverted):
        return f"partial conversion: {outcome.message}"
    if isinstance(outcome, ConversionFailed):
        return f"conversion failed: {outcome.message}"
    return missing_provenance(outcome.document)


def _fail(destination: Path, record: MaterialRecord, material_id: str, problem: str) -> CliError:
    """Mark the material at ``destination`` failed and return the ``conversion_failed`` error.

    Shared by every material type. What already exists in the folder is kept for
    inspection; ``record`` must have status ``failed``.
    """
    material_store.write_record(destination, record)
    return CliError(
        "conversion_failed",
        f"{problem}; {material_id} is marked failed, retry with a new destination",
    )
