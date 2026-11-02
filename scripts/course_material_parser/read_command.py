"""Entry point for the ``read`` CLI, which gives agents access to parsed material.

This module must never import Docling, so reader startup stays fast.
"""

import argparse
from collections.abc import Sequence
from pathlib import Path
from typing import assert_never

from course_material_parser import material_store, page_renders
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
  list    list ready materials, optionally under a PREFIX folder
  toc     show a material's table of contents
  get     print a material's Markdown
  render  render source pages to PNG
  clean-renders
          delete rendered page images

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

_RENDER_DESCRIPTION = """\
Render source pages of a material to PNG and print their files as JSON. The files are
under dir.

Files stay available until the user cleans them up; rendering a page again recreates its
file."""

_CLEAN_RENDERS_DESCRIPTION = """\
Deletes rendered page images. Run only when the user asks.

Prints the number of files and bytes removed as JSON."""


def main(argv: Sequence[str] | None = None, *, settings_path: Path | None = None) -> int:
    """Run the CLI with ``argv`` (default ``sys.argv[1:]``) and return the exit code.

    ``settings_path`` defaults to the skill's ``settings.toml``; tests inject their own.
    """
    return run_cli(lambda: _run(argv, settings_path))


def _run(argv: Sequence[str] | None, settings_path: Path | None) -> str:
    args = _build_parser().parse_args(argv)
    settings = load_settings(settings_path)
    if args.command == "list":
        return json_line(_list(settings, args.prefix))
    if args.command == "toc":
        return json_line(_toc(settings, args.source))
    if args.command == "render":
        return json_line(_render(settings, args.source, args.pages))
    if args.command == "clean-renders":
        return json_line(_clean_renders(settings, args.source, confirm=args.confirm))
    return _get(settings, args.source, args.id, args.pages)


def _build_parser() -> argparse.ArgumentParser:
    parser = JsonArgumentParser(
        prog="read", description=_DESCRIPTION, formatter_class=argparse.RawTextHelpFormatter
    )
    commands = parser.add_subparsers(dest="command", required=True, metavar="<command>")
    list_ = commands.add_parser(
        "list",
        description="List ready materials as JSON, sorted by MATERIAL. Materials still being "
        "parsed, failed, or interrupted are not listed.",
        help="list ready materials",
    )
    list_.add_argument(
        "prefix",
        nargs="?",
        metavar="PREFIX",
        help="only materials in this folder, matched by whole folder names: ml matches "
        "ml/prml, not mlx/prml",
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
    render = commands.add_parser(
        "render",
        description=_RENDER_DESCRIPTION,
        formatter_class=argparse.RawTextHelpFormatter,
        help="render source pages to PNG",
    )
    render.add_argument("--source", required=True, metavar="MATERIAL", help="exact material id")
    render.add_argument("--pages", required=True, metavar="SPEC", help=PAGES_HELP)
    clean = commands.add_parser(
        "clean-renders",
        description=_CLEAN_RENDERS_DESCRIPTION,
        formatter_class=argparse.RawTextHelpFormatter,
        help="delete rendered page images",
    )
    scope = clean.add_mutually_exclusive_group(required=True)
    scope.add_argument("--source", metavar="MATERIAL", help="exact material id")
    scope.add_argument("--all", action="store_true", help="every material; needs --confirm")
    clean.add_argument("--confirm", action="store_true", help="confirm deleting with --all")
    return parser


def _list(settings: Settings, prefix: str | None) -> dict:
    return {
        "materials": [
            {"source": m.material_id, "type": m.record.type, "pages": m.record.pages}
            for m in material_store.ready_materials(settings.library_root, prefix)
        ]
    }


def _toc(settings: Settings, source: str) -> dict:
    material = material_store.get_ready_material(settings.library_root, source)
    match material.record.type:
        case MaterialType.SLIDES:
            return {"source": source, "type": material.record.type, "pages": material.record.pages}
        case MaterialType.TEXTBOOK:
            # Nothing finalizes a textbook into ready material yet, so this can't be reached.
            raise NotImplementedError("textbook tocs are not supported yet")
        case unhandled:
            assert_never(unhandled)


def _render(settings: Settings, source: str, pages: str) -> dict:
    material = material_store.get_ready_material(settings.library_root, source)
    selected = parse_pages(pages, material_id=source, page_count=material.record.pages)
    renders = page_renders.render(material, selected)
    return {
        "dir": str(renders.dir),
        "pages": [{"page": page, "file": file} for page, file in renders.files],
    }


def _clean_renders(settings: Settings, source: str | None, *, confirm: bool) -> dict:
    if source is not None:
        materials = [material_store.get_ready_material(settings.library_root, source)]
    elif confirm:
        materials = material_store.ready_materials(settings.library_root)
    else:
        raise CliError(
            "confirm_required",
            "--all deletes the renders of every material; re-run with --confirm only if the "
            "user asked for it",
        )
    removed = sum((page_renders.clean(m) for m in materials), page_renders.Removed())
    return {"files": removed.files, "bytes": removed.bytes}


def _get(settings: Settings, source: str, unit_id: str | None, pages: str | None) -> str:
    if unit_id is not None and pages is not None:
        raise CliError("invalid_request", "use either --id or --pages, not both")
    material = material_store.get_ready_material(settings.library_root, source)
    match material.record.type:
        case MaterialType.SLIDES:
            # --confirm is accepted and ignored: slide reads are never size-checked.
            return _get_slides(material, unit_id, pages)
        case MaterialType.TEXTBOOK:
            # Nothing finalizes a textbook into ready material yet, so this can't be reached.
            raise NotImplementedError("textbook reads are not supported yet")
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
