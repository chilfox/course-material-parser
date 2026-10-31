"""Entry point for the ``read`` CLI, which gives agents access to parsed material.

This module must never import Docling, so reader startup stays fast.
"""

import argparse
from collections.abc import Sequence
from pathlib import Path

from course_material_parser import material_store
from course_material_parser.cli_output import JsonArgumentParser, json_line, run_cli
from course_material_parser.settings import Settings, load_settings

_DESCRIPTION = """\
Read parsed material stored under library_root.

MATERIAL is the material's folder path under library_root, for example ml/prml.
Page numbers are always source-PDF pages counted from 1, not printed page numbers.

commands:
  list    list ready materials
  get     print a material's Markdown

See `read <command> --help` for details."""

_GET_DESCRIPTION = """\
Print the Markdown of a material, with no JSON wrapper. For slides, this is the whole deck.

Markers in the Markdown:
  <page N>  the content below comes from source-PDF page N."""


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
    return _get(settings, args.source)


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
    get = commands.add_parser(
        "get",
        description=_GET_DESCRIPTION,
        formatter_class=argparse.RawTextHelpFormatter,
        help="print a material's Markdown",
    )
    get.add_argument("--source", required=True, metavar="MATERIAL", help="exact material id")
    return parser


def _list(settings: Settings) -> dict:
    return {
        "materials": [
            {"source": m.material_id, "type": m.record.type, "pages": m.record.pages}
            for m in material_store.ready_materials(settings.library_root)
        ]
    }


def _get(settings: Settings, source: str) -> str:
    material = material_store.get_ready_material(settings.library_root, source)
    return material_store.slides_markdown(material.path).read_text(encoding="utf-8")
