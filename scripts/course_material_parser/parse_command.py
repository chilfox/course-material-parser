"""Entry point for the ``parse`` CLI, which converts source PDFs into parsed material.

Every type of material goes through one pipeline (settings, destination, creation, PDF
copy, conversion, stored output) that branches on the type only when writing contents.
"""

import argparse
import shutil
from collections.abc import Sequence
from pathlib import Path

from course_material_parser import material_store, pdf
from course_material_parser.cli_output import CliError, JsonArgumentParser, json_line, run_cli
from course_material_parser.docling_conversion import (
    Converted,
    Converter,
    PartiallyConverted,
)
from course_material_parser.markdown_writer import PdfPages, write_markdown
from course_material_parser.material_store import MaterialRecord, MaterialType, Status
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
source page and are ready to read when this command succeeds."""


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
    return parser


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
    pages = pdf.page_count(source)

    material_type = MaterialType(args.type)
    destination = material_store.create_destination(settings.library_root, args.dest)
    retained_pdf = material_store.source_pdf(destination)
    shutil.copyfile(source, retained_pdf)
    outcome = converter.convert(retained_pdf, device=settings.device, ocr=False)

    def record(status: Status) -> MaterialRecord:
        return MaterialRecord(
            type=material_type, status=status, source_filename=source.name, pages=pages
        )

    if not isinstance(outcome, Converted):
        material_store.write_record(destination, record(Status.FAILED))
        outcome_wording = (
            "partially converted" if isinstance(outcome, PartiallyConverted) else "failed"
        )
        raise CliError(
            "conversion_failed",
            f"conversion {outcome_wording}: {outcome.message}; {args.dest} is marked failed, "
            "retry with a new destination",
        )

    material_store.write_slides(
        destination, write_markdown(outcome.document, PdfPages(start=1, end=pages))
    )
    # Written last, so a material is only ever visible as ready once all its contents exist.
    material_store.write_record(destination, record(Status.READY))
    return {"source": args.dest, "type": material_type, "status": Status.READY, "pages": pages}
