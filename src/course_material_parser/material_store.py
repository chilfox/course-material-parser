"""Map material ids to folders under ``library_root`` and manage their ``material.json``.

A material folder holds ``source.pdf``, ``material.json``, and ``contents/``. A folder
without ``material.json`` is an interrupted parse, which readers ignore.
"""

import json
import os
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path

from course_material_parser.cli_output import CliError

FORMAT_VERSION = 1
METADATA_FILE = "material.json"
SOURCE_PDF = "source.pdf"
CONTENTS_DIR = "contents"
SLIDES_FILE = "slides.md"


@dataclass(frozen=True)
class MaterialRecord:
    """The contents of ``material.json``."""

    type: str
    status: str
    source_filename: str
    pages: int
    format_version: int = FORMAT_VERSION


@dataclass(frozen=True)
class Material:
    """A material found in the library: its id, folder, and record."""

    source: str
    path: Path
    record: MaterialRecord


def create_destination(library_root: Path, material_id: str) -> Path:
    """Create the empty folder for ``material_id``, with any missing parent folders.

    Raises:
        CliError: ``destination_exists`` when the folder already exists, even empty.
    """
    path = library_root / material_id
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        # Exclusive creation, so a folder appearing after any earlier check is still refused.
        path.mkdir()
    except FileExistsError:
        raise CliError(
            "destination_exists", f"{material_id} already exists; choose a new destination"
        ) from None
    return path


def write_record(material_dir: Path, record: MaterialRecord) -> None:
    """Write ``material.json`` atomically, so readers never see a partial file."""
    payload = json.dumps(asdict(record), indent=2) + "\n"
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=material_dir, prefix=".material-", delete=False
    ) as handle:
        handle.write(payload)
    os.replace(handle.name, material_dir / METADATA_FILE)


def ready_materials(library_root: Path) -> list[Material]:
    """Return every ready material under ``library_root``, sorted by id.

    Discovery stops at a material folder and never descends into it.
    """
    found: list[Material] = []
    for directory, subdirs, files in os.walk(library_root):
        if METADATA_FILE in files:
            subdirs.clear()
            material = _load(library_root, Path(directory))
            if material.record.status == "ready":
                found.append(material)
        else:
            subdirs[:] = [name for name in subdirs if not name.startswith(".")]
    return sorted(found, key=lambda material: material.source)


def get_ready_material(library_root: Path, material_id: str) -> Material:
    """Return the ready material with exactly the id ``material_id``.

    Raises:
        CliError: ``not_found`` when no material has that id or it isn't ready.
    """
    path = library_root / material_id
    if not (path / METADATA_FILE).is_file():
        raise CliError("not_found", f"no ready material '{material_id}'")
    material = _load(library_root, path)
    if material.record.status != "ready":
        raise CliError("not_found", f"{material_id} is not ready ({material.record.status})")
    return material


def _load(library_root: Path, path: Path) -> Material:
    raw = json.loads((path / METADATA_FILE).read_text(encoding="utf-8"))
    return Material(
        source=path.relative_to(library_root).as_posix(),
        path=path,
        record=MaterialRecord(**raw),
    )
