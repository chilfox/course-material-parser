"""The page render cache inside a material: PNG images of source pages, and their cleanup.

Renders are named ``page_<N>.png`` and kept until the user cleans them up. The rest of the
layout (where the folder lives inside the material) is private to this module.
"""

from dataclasses import dataclass
from pathlib import Path

from course_material_parser import material_store, pdf
from course_material_parser.atomic_write import write_atomically
from course_material_parser.cli_output import CliError
from course_material_parser.material_store import Material

_RENDERS_DIR = "renders"


@dataclass(frozen=True)
class Renders:
    """Rendered pages: the folder holding them and each page's file name in request order."""

    dir: Path
    files: list[tuple[int, str]]


@dataclass(frozen=True)
class Removed:
    """What a cleanup deleted: the number of files and their total size in bytes."""

    files: int = 0
    bytes: int = 0

    def __add__(self, other: "Removed") -> "Removed":
        """Return the totals of both cleanups."""
        return Removed(self.files + other.files, self.bytes + other.bytes)


def render(material: Material, pages: list[int]) -> Renders:
    """Make sure each of ``pages`` of ``material`` has a render and return where they are.

    Existing renders are reused. Missing ones are rendered from the retained source PDF.

    Raises:
        CliError: ``render_failed`` when the source PDF can't be opened or a page can't
            be rendered. Pages rendered before the failure stay cached but nothing is
            returned, so the caller never sees a partial result.
    """
    render_dir = (material.path / _RENDERS_DIR).resolve()
    missing = [page for page in dict.fromkeys(pages) if not (render_dir / _file(page)).is_file()]
    if missing:
        render_dir.mkdir(exist_ok=True)
        source = material_store.source_pdf(material.path)
        try:
            for page, png in pdf.render_pngs(source, missing):
                # Overlapping sessions may render the same page at once; each replaces
                # the file whole, so no reader sees a half-written PNG and no lock is needed.
                write_atomically(render_dir / _file(page), png)
        except pdf.RenderFailed as error:
            raise CliError(
                "render_failed",
                f"could not render {material.material_id}: {error}; its source.pdf may be "
                "damaged, so parse the PDF again into a new destination",
            ) from None
    return Renders(dir=render_dir, files=[(page, _file(page)) for page in pages])


def clean(material: Material) -> Removed:
    """Delete every render of ``material`` and report what was removed."""
    removed = Removed()
    # Only finished renders are deleted, and the folder stays: another session may be
    # rendering into it right now, and removing its temporary file or the folder would
    # make that render fail.
    for path in (material.path / _RENDERS_DIR).glob(_file("*")):
        try:
            size = path.stat().st_size
            path.unlink()
        except FileNotFoundError:
            continue  # Another cleanup got there first.
        removed += Removed(1, size)
    return removed


def _file(page: int | str) -> str:
    return f"page_{page}.png"
