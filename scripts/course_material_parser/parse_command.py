"""Entry point for the ``parse`` CLI, which converts source PDFs into parsed material.

Every type of material goes through one pipeline (settings, destination, creation, PDF
copy, conversion, stored output) that branches on the type only when writing contents.
"""

import argparse
import shutil
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import assert_never

from docling_core.types.doc import DoclingDocument

from course_material_parser import extraction, material_store, pdf
from course_material_parser.cli_output import CliError, JsonArgumentParser, json_line, run_cli
from course_material_parser.docling_conversion import (
    ConversionFailed,
    ConversionOutcome,
    Converted,
    Converter,
    PartiallyConverted,
    load_document,
    save_document,
)
from course_material_parser.markdown_writer import PdfPages, write_markdown
from course_material_parser.material_store import Material, MaterialRecord, MaterialType, Status
from course_material_parser.page_spec import PAGES_HELP, parse_pages
from course_material_parser.provenance import missing_provenance
from course_material_parser.settings import Settings, load_settings, require_device_available

_DESCRIPTION = """\
Convert a source PDF into parsed material stored under library_root.

MATERIAL is the material's folder path under library_root, for example ml/prml.
Page numbers are always source-PDF pages counted from 1, not printed page numbers.

commands:
  start    parse a source PDF into a new material
  inspect  show a pending textbook's detected structure or page content

See `parse <command> --help` for details."""

_START_DESCRIPTION = """\
Parse the source PDF into a new material at MATERIAL. The destination must not exist;
missing parent folders are created. Slides become one Markdown deck with a marker per
source page and are ready to read when this command succeeds. A textbook is extracted
once and left pending: the result is its structure index (see `parse inspect --help`),
including the extraction_id a split plan must name.

OCR: without --ocr or --no-ocr, the PDF's text layer is checked first, and the parse is
refused with ocr_required, reporting the count, when more than half the pages have no
text layer. Then decide: --ocr to convert with OCR (refused with ocr_disabled when
allow_ocr = false in settings.toml), or --no-ocr when only page renders matter, which
skips the check."""

_INSPECT_DESCRIPTION = """\
Inspect a pending textbook's stored extraction as JSON, to plan its split without
converting again. Detected structure is evidence, not an authoritative outline.

Forms:
  inspect --dest MATERIAL
      the structure index: page count, detected headings in reading order with their
      level (when detected) and first source page, status, and extraction_id.
  inspect --dest MATERIAL --pages SPEC
      the content of those source pages only: each item's ref, type, every source page
      it lies on (an item spanning a boundary shows both), and its text. Use this to
      check where a section starts; inspect a few pages at a time, not the whole book.

Running headers and footers are left out of both."""


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
    if args.command == "inspect":
        return json_line(_inspect(settings, args.dest, args.pages))
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
    inspect = commands.add_parser(
        "inspect",
        description=_INSPECT_DESCRIPTION,
        formatter_class=argparse.RawTextHelpFormatter,
        help="show a pending textbook's detected structure or page content",
    )
    inspect.add_argument("--dest", required=True, metavar="MATERIAL", help="pending textbook")
    inspect.add_argument("--pages", metavar="SPEC", help=f"show content of {PAGES_HELP}")
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

    problem = _conversion_problem(outcome)
    if problem is not None:
        _mark_failed(destination, material_type, source.name, pages)
        raise CliError(
            "conversion_failed",
            f"{problem}; {args.dest} is marked failed, retry with a new destination",
        )
    # Narrowed for the reader and the type checker: only a full conversion has no problem.
    assert isinstance(outcome, Converted)

    match material_type:
        case MaterialType.SLIDES:
            material_store.write_slides(
                destination, write_markdown(outcome.document, PdfPages(start=1, end=pages))
            )
            status, extraction_id = Status.READY, None
        case MaterialType.TEXTBOOK:
            extraction_path = material_store.extraction_json(destination)
            save_document(outcome.document, extraction_path)
            status, extraction_id = Status.PENDING, extraction.extraction_id(extraction_path)
        case unhandled:
            assert_never(unhandled)
    record = MaterialRecord(
        type=material_type,
        status=status,
        source_filename=source.name,
        pages=pages,
        extraction_id=extraction_id,
    )
    # Written last, so a material only ever shows a status once everything it needs exists.
    material_store.write_record(destination, record)
    if material_type is MaterialType.TEXTBOOK:
        return _structure_index(Material(args.dest, destination, record), outcome.document)
    return {"source": args.dest, "type": material_type, "status": status, "pages": pages}


def _structure_index(material: Material, document: DoclingDocument) -> dict:
    """Return the structure index of a pending textbook, as ``start`` and ``inspect`` print it."""
    record = material.record
    return {
        "source": material.material_id,
        "type": record.type,
        "status": record.status,
        "extraction_id": record.extraction_id,
        "pages": record.pages,
        "headings": extraction.headings(document),
    }


def _inspect(settings: Settings, material_id: str, pages: str | None) -> dict:
    material = _pending_material(settings, material_id)
    document = load_document(material_store.extraction_json(material.path))
    if pages is None:
        return _structure_index(material, document)
    selected = parse_pages(pages, material_id=material_id, page_count=material.record.pages)
    return {
        "source": material_id,
        "extraction_id": material.record.extraction_id,
        "items": extraction.page_items(document, set(selected)),
    }


def _pending_material(settings: Settings, material_id: str) -> Material:
    """Return the pending textbook ``material_id``, awaiting its split.

    Raises:
        CliError: ``not_found`` when there is no such material, naming its status when it
            exists but isn't pending.
    """
    material = material_store.find_material(settings.library_root, material_id)
    if material is None and material_store.is_interrupted_parse(settings.library_root, material_id):
        raise CliError(
            "not_found",
            f"{material_id} is an interrupted parse; delete that folder by hand or parse "
            "into a new destination",
        )
    if material is None:
        raise CliError(
            "not_found", f"no material '{material_id}'; parse it first with `parse start`"
        )
    match material.record.status:
        case Status.PENDING:
            return material
        case Status.READY:
            fix = "it is ready; read it with `read`"
        case Status.FAILED:
            fix = "its parse failed; parse again into a new destination"
        case unhandled:
            assert_never(unhandled)
    raise CliError("not_found", f"{material_id} is not pending ({material.record.status}): {fix}")


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


def _mark_failed(
    destination: Path, material_type: MaterialType, source_filename: str, pages: int
) -> None:
    """Write a ``failed`` record for the material at ``destination``.

    Shared by every material type. It runs before any contents are written, so the folder
    is left holding only the retained source PDF and this record.
    """
    record = MaterialRecord(
        type=material_type, status=Status.FAILED, source_filename=source_filename, pages=pages
    )
    material_store.write_record(destination, record)
