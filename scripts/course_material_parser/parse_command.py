"""Entry point for the ``parse`` CLI, which converts source PDFs into parsed material.

Every type of material goes through one pipeline (settings, destination, creation, PDF
copy, conversion, stored output) that branches on the type only when writing contents.
"""

import argparse
import json
import shutil
from collections.abc import Callable, Sequence
from dataclasses import replace
from pathlib import Path
from typing import assert_never

from docling_core.types.doc import DoclingDocument

from course_material_parser import extraction, material_store, pdf, split_plan
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
from course_material_parser.material_store import (
    ChapterRecord,
    Material,
    MaterialRecord,
    MaterialType,
    Status,
    UnitRecord,
)
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
  propose  validate a textbook's split plan and save it for the user's approval
  finalize split a textbook as the user approved, making it ready to read

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

_PROPOSE_DESCRIPTION = """\
Validate the split plan at PATH for a pending textbook and save a snapshot of it in the
material. Every problem is reported at once as invalid_plan; the material stays pending
and a previous snapshot is kept. A valid plan replaces any previous snapshot and returns
a summary for the approval request: contents with ids, titles, and pages, and overlaps.

Plan file (every field required, no others allowed):
  {"version": 1, "extraction_id": "<from inspect>", "contents": [
    {"id": "front-matter", "title": "Front matter", "kind": "other",
     "selector": {"kind": "pdf_pages", "start": 1, "end": 20}},
    {"id": "chapter-01", "title": "Introduction", "units": [
      {"id": "1-1", "title": "Curve Fitting", "kind": "section",
       "selector": {"kind": "pdf_pages", "start": 21, "end": 32}}]}]}

contents is in reading order: standalone units and chapters, with each chapter's units
nested in it. kind is section for a numbered section, other for anything else. Ids use
lowercase letters, digits, and '-', not starting with '-', and are unique in the plan.
Pages are inclusive source pages. Units must cover every page, in order of their first
page. Adjacent units may share only their boundary page, where one ends and the next
starts; several units may lie on that one page."""

_FINALIZE_DESCRIPTION = """\
Split a pending textbook by its proposed plan snapshot and make it ready to read. Only
the snapshot saved by the last `parse propose` runs: edits to the plan file since then
have no effect until proposed again and approved again. Pass --confirm only after the
user approved that proposal; without it, finalize is refused. A ready textbook can't be
finalized again. Read the result with `read toc` and `read get`."""


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
    if args.command == "propose":
        return json_line(_propose(settings, args.dest, args.plan))
    if args.command == "finalize":
        return json_line(_finalize(settings, args.dest, confirm=args.confirm))
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
    propose = commands.add_parser(
        "propose",
        description=_PROPOSE_DESCRIPTION,
        formatter_class=argparse.RawTextHelpFormatter,
        help="validate a textbook's split plan and save it for the user's approval",
    )
    propose.add_argument("--dest", required=True, metavar="MATERIAL", help="pending textbook")
    propose.add_argument("--plan", required=True, type=Path, metavar="PATH", help="split plan JSON")
    finalize = commands.add_parser(
        "finalize",
        description=_FINALIZE_DESCRIPTION,
        help="split a textbook as the user approved, making it ready to read",
    )
    finalize.add_argument("--dest", required=True, metavar="MATERIAL", help="pending textbook")
    finalize.add_argument(
        "--confirm", action="store_true", help="assert that the user approved the proposal"
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
            _record(destination, material_type, Status.READY, source.name, pages)
            return {
                "source": args.dest,
                "type": material_type,
                "status": Status.READY,
                "pages": pages,
            }
        case MaterialType.TEXTBOOK:
            extraction_path = material_store.extraction_json(destination)
            save_document(outcome.document, extraction_path)
            record = _record(
                destination,
                material_type,
                Status.PENDING,
                source.name,
                pages,
                extraction_id=extraction.extraction_id(extraction_path),
            )
            return _structure_index(Material(args.dest, destination, record), outcome.document)
        case unhandled:
            assert_never(unhandled)


def _record(
    destination: Path,
    material_type: MaterialType,
    status: Status,
    source_filename: str,
    pages: int,
    *,
    extraction_id: str | None = None,
) -> MaterialRecord:
    """Write the material's record at ``destination`` and return it.

    Every outcome of a parse (ready, pending, or failed) ends here, after everything the
    status promises exists, so a material only ever shows a status it can honour.
    """
    record = MaterialRecord(
        type=material_type,
        status=status,
        source_filename=source_filename,
        pages=pages,
        extraction_id=extraction_id,
    )
    material_store.write_record(destination, record)
    return record


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
    material = material_store.get_pending_material(settings.library_root, material_id)
    document = load_document(material_store.extraction_json(material.path))
    if pages is None:
        return _structure_index(material, document)
    selected = parse_pages(pages, material_id=material_id, page_count=material.record.pages)
    return {
        "source": material_id,
        "extraction_id": material.record.extraction_id,
        "items": extraction.page_items(document, set(selected)),
    }


def _propose(settings: Settings, material_id: str, plan_path: Path) -> dict:
    material = material_store.get_pending_material(settings.library_root, material_id)
    record = material.record
    assert record.extraction_id is not None
    plan = split_plan.parse_plan(
        _read_plan_file(plan_path),
        material_id=material_id,
        page_count=record.pages,
        extraction_id=record.extraction_id,
    )
    material_store.write_plan_snapshot(material.path, split_plan.plan_json(plan))
    return {
        "source": material_id,
        "pdf": record.source_filename,
        "pages": record.pages,
        **split_plan.summary(plan),
    }


def _finalize(settings: Settings, material_id: str, *, confirm: bool) -> dict:
    material = material_store.get_pending_material(settings.library_root, material_id)
    record = material.record
    assert record.extraction_id is not None
    if not confirm:
        raise CliError(
            "confirm_required",
            "finalize splits the textbook as last proposed; re-run with --confirm only after "
            "the user approved that proposal",
        )
    snapshot = material_store.read_plan_snapshot(material.path)
    if snapshot is None:
        raise CliError(
            "invalid_request",
            f"{material_id} has no proposed split plan; run `parse propose` and get the "
            "user's approval first",
        )
    # Validated again rather than trusted, so a snapshot that no longer fits its
    # extraction is refused instead of producing units the user never approved.
    plan = split_plan.parse_plan(
        snapshot,
        material_id=material_id,
        page_count=record.pages,
        extraction_id=record.extraction_id,
    )
    document = load_document(material_store.extraction_json(material.path))
    chapters, units = _stored_contents(plan)
    material_store.write_textbook_units(
        material.path,
        ((unit, write_markdown(document, selector)) for unit, selector in units),
    )
    # ready is written last, and atomically: a finalization that stops before this point
    # leaves the textbook pending, with its extraction and snapshot, so it can be re-run.
    material_store.write_record(
        material.path,
        replace(
            record,
            status=Status.READY,
            extraction_id=None,
            chapters=chapters,
            units=tuple(unit for unit, _selector in units),
        ),
    )
    material_store.remove_extraction_and_snapshot(material.path)
    return {
        "source": material_id,
        "type": record.type,
        "status": Status.READY,
        "pages": record.pages,
        "chapters": len(chapters),
        "units": len(units),
    }


def _stored_contents(
    plan: split_plan.SplitPlan,
) -> tuple[tuple[ChapterRecord, ...], list[tuple[UnitRecord, PdfPages]]]:
    """Return the chapters of ``plan`` and its units with their selectors, in reading order."""
    chapters: list[ChapterRecord] = []
    units: list[tuple[UnitRecord, PdfPages]] = []
    for entry in plan.contents:
        if isinstance(entry, split_plan.Chapter):
            chapters.append(ChapterRecord(id=entry.id, title=entry.title))
            units.extend((_unit_record(unit, entry.id), unit.selector) for unit in entry.units)
        else:
            units.append((_unit_record(entry, None), entry.selector))
    return tuple(chapters), units


def _unit_record(unit: split_plan.Unit, chapter_id: str | None) -> UnitRecord:
    return UnitRecord(
        id=unit.id,
        title=unit.title,
        kind=unit.kind,
        chapter=chapter_id,
        pages=(unit.first_page, unit.last_page),
    )


def _read_plan_file(path: Path) -> object:
    """Return the decoded JSON of the plan file at ``path``.

    Raises:
        CliError: ``not_found`` when there is no such file; ``invalid_plan`` when it isn't
            valid UTF-8 JSON.
    """
    if not path.is_file():
        raise CliError("not_found", f"plan file not found: {path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise CliError("invalid_plan", f"{path} is not valid JSON: {error}") from None


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
    _record(destination, material_type, Status.FAILED, source_filename, pages)
