"""Entry point for the ``parse`` CLI, which converts source PDFs into parsed material.

Every type of material goes through one pipeline (settings, destination, creation, PDF
copy, conversion, stored output) that branches on the type only when writing contents.
"""

import argparse
import shutil
from collections.abc import Sequence
from pathlib import Path

from course_material_parser import material_store
from course_material_parser.cli_output import CliError, JsonArgumentParser, run_cli, to_json
from course_material_parser.docling_conversion import (
    ConversionFailed,
    Converted,
    Converter,
    PartiallyConverted,
)
from course_material_parser.markdown_writer import PdfPages, write_markdown
from course_material_parser.pdf import page_count
from course_material_parser.settings import Settings, load_settings

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


def _run(argv: Sequence[str] | None, settings_path: Path | None, converter: Converter | None):
    args = _build_parser().parse_args(argv)
    settings = load_settings(settings_path)
    if converter is None:
        from course_material_parser.docling_conversion import DoclingConverter

        converter = DoclingConverter()
    return to_json(_start(args, settings, converter)) + "\n"


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
    start.add_argument("--type", required=True, choices=["slides"], help="kind of source PDF")
    return parser


def _start(args: argparse.Namespace, settings: Settings, converter: Converter) -> dict:
    pdf: Path = args.pdf
    if not pdf.is_file():
        raise CliError("not_found", f"PDF not found: {pdf}")
    pages = page_count(pdf)

    destination = material_store.create_destination(settings.library_root, args.dest)
    shutil.copyfile(pdf, destination / material_store.SOURCE_PDF)
    outcome = converter.convert(
        destination / material_store.SOURCE_PDF, device=settings.device, ocr=False
    )

    def record(status: str) -> material_store.MaterialRecord:
        return material_store.MaterialRecord(
            type=args.type, status=status, source_filename=pdf.name, pages=pages
        )

    if isinstance(outcome, ConversionFailed | PartiallyConverted):
        material_store.write_record(destination, record("failed"))
        partial = "partially converted" if isinstance(outcome, PartiallyConverted) else "failed"
        raise CliError(
            "conversion_failed",
            f"conversion {partial}: {outcome.message}; {args.dest} is marked failed, "
            "retry with a new destination",
        )
    assert isinstance(outcome, Converted)

    contents = destination / material_store.CONTENTS_DIR
    contents.mkdir()
    (contents / material_store.SLIDES_FILE).write_text(
        write_markdown(outcome.document, PdfPages(start=1, end=pages)), encoding="utf-8"
    )
    # Written last, so a material is only ever visible as ready once all its contents exist.
    material_store.write_record(destination, record("ready"))
    return {"source": args.dest, "type": args.type, "status": "ready", "pages": pages}
