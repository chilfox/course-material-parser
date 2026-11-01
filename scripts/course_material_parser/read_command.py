"""Entry point for the ``read`` CLI, which gives agents access to parsed material.

This module must never import Docling, so reader startup stays fast.
"""

import argparse
from collections.abc import Sequence
from pathlib import Path
from typing import assert_never

from course_material_parser import material_store
from course_material_parser.cli_output import CliError, JsonArgumentParser, json_line, run_cli
from course_material_parser.material_store import Material, MaterialType
from course_material_parser.page_blocks import join_page_blocks, split_page_blocks
from course_material_parser.page_spec import PAGES_HELP, parse_pages
from course_material_parser.settings import Settings, load_settings

_DESCRIPTION = """\
Read parsed material stored under library_root.

MATERIAL is the material's folder path under library_root, for example ml/prml.
Page numbers are always source-PDF pages counted from 1, not printed page numbers.

commands:
  list    list ready materials
  toc     show a material's table of contents
  get     print a material's Markdown

See `read <command> --help` for details."""

_GET_DESCRIPTION = """\
Print the Markdown of a material, with no JSON wrapper.

Selectors:
  slides     no selector prints the whole deck; --pages SPEC prints exactly those
             pages in the order requested, a bare marker for a page with no content.
             --id does not apply.
  textbooks  --id ID prints a reading unit, or a chapter with its units joined in
             order. --pages does not apply.
  --id and --pages can't be combined. Chapter reads over the size limit return
  too_large; re-run with --confirm only if the whole chapter is needed. --confirm is
  ignored for units and slides.

Markers in the Markdown:
  <page N>  the content below comes from source-PDF page N.
  <visual>  an image was here, followed by its caption if detected. Usually the text
            is enough. Render that page only if the content can't be understood
            without it."""


def main(argv: Sequence[str] | None = None, *, settings_path: Path | None = None) -> int:
    """Run the CLI with ``argv`` (default ``sys.argv[1:]``) and return the exit code.

    ``settings_path`` defaults to the skill's ``settings.toml``; tests inject their own.
    """
    return run_cli(lambda: _run(argv, settings_path))


def _run(argv: Sequence[str] | None, settings_path: Path | None) -> str:
    args = _build_parser().parse_args(argv)
    settings = load_settings(settings_path)
    if args.command == "list":
        return json_line(_list(settings))
    if args.command == "toc":
        return json_line(_toc(settings, args.source))
    return _get(settings, args.source, args.id, args.pages)


def _build_parser() -> argparse.ArgumentParser:
    parser = JsonArgumentParser(
        prog="read", description=_DESCRIPTION, formatter_class=argparse.RawTextHelpFormatter
    )
    commands = parser.add_subparsers(dest="command", required=True, metavar="<command>")
    commands.add_parser(
        "list",
        description="List ready materials as JSON, sorted by MATERIAL.",
        help="list ready materials",
    )
    toc = commands.add_parser(
        "toc",
        description="Show a material's table of contents as JSON. For slides, this is the "
        "source, type, and page count.",
        help="show a material's table of contents",
    )
    toc.add_argument("--source", required=True, metavar="MATERIAL", help="exact material id")
    get = commands.add_parser(
        "get",
        description=_GET_DESCRIPTION,
        formatter_class=argparse.RawTextHelpFormatter,
        help="print a material's Markdown",
    )
    get.add_argument("--source", required=True, metavar="MATERIAL", help="exact material id")
    get.add_argument("--id", metavar="ID", help="textbooks only: a chapter or unit id")
    get.add_argument("--pages", metavar="SPEC", help=f"slides only: {PAGES_HELP}")
    get.add_argument(
        "--confirm", action="store_true", help="read a chapter even when it is over the size limit"
    )
    return parser


def _list(settings: Settings) -> dict:
    return {
        "materials": [
            {"source": m.material_id, "type": m.record.type, "pages": m.record.pages}
            for m in material_store.ready_materials(settings.library_root)
        ]
    }


def _toc(settings: Settings, source: str) -> dict:
    material = material_store.get_ready_material(settings.library_root, source)
    match material.record.type:
        # Textbook tocs (chapters and units) add their case here.
        case MaterialType.SLIDES:
            return {"source": source, "type": material.record.type, "pages": material.record.pages}
        case unhandled:
            assert_never(unhandled)


def _get(settings: Settings, source: str, unit_id: str | None, pages: str | None) -> str:
    if unit_id is not None and pages is not None:
        raise CliError("invalid_request", "use either --id or --pages, not both")
    material = material_store.get_ready_material(settings.library_root, source)
    match material.record.type:
        # Textbook reads (--id, size limit, --confirm) add their case here.
        case MaterialType.SLIDES:
            # --confirm is accepted and ignored: slide reads are never size-checked.
            return _get_slides(material, unit_id, pages)
        case unhandled:
            assert_never(unhandled)


def _get_slides(material: Material, unit_id: str | None, pages: str | None) -> str:
    if unit_id is not None:
        raise CliError(
            "invalid_request",
            f"--id applies only to textbooks; {material.material_id} is slides, use --pages",
        )
    deck = material_store.slides_markdown(material.path).read_text(encoding="utf-8")
    if pages is None:
        return deck
    selected = parse_pages(
        pages, material_id=material.material_id, page_count=material.record.pages
    )
    blocks = split_page_blocks(deck)
    return join_page_blocks([blocks[page] for page in selected])
