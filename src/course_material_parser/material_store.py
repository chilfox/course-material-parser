"""Map material ids to folders under ``library_root`` and own the stored-material layout.

A material folder holds ``source.pdf``, ``material.json``, and ``contents/``. A folder
without ``material.json`` is an interrupted parse, which readers ignore. Other modules ask
this one for paths instead of building them, so the layout lives in one place.
"""

import json
import os
import re
import tempfile
from dataclasses import asdict, dataclass
from enum import StrEnum
from pathlib import Path

from course_material_parser.cli_output import CliError

FORMAT_VERSION = 1
_METADATA_FILE = "material.json"
_SOURCE_PDF = "source.pdf"
_CONTENTS_DIR = "contents"
_SLIDES_FILE = "slides.md"
# One folder name: letters, digits, ".", "_", "-", not starting with "." (so ".", "..",
# and hidden folders, which discovery skips, are impossible).
_SEGMENT = re.compile(r"[A-Za-z0-9_-][A-Za-z0-9._-]*")


class MaterialType(StrEnum):
    """The kind of source PDF a material was parsed from."""

    SLIDES = "slides"


class Status(StrEnum):
    """Where a material is in its lifecycle; only ``READY`` material is readable."""

    READY = "ready"
    FAILED = "failed"


@dataclass(frozen=True)
class MaterialRecord:
    """The contents of ``material.json``."""

    type: MaterialType
    status: Status
    source_filename: str
    pages: int
    format_version: int = FORMAT_VERSION


@dataclass(frozen=True)
class Material:
    """A material in the library: its material id, folder, and record."""

    material_id: str
    path: Path
    record: MaterialRecord


def source_pdf(material_dir: Path) -> Path:
    """Return where the retained copy of the source PDF lives."""
    return material_dir / _SOURCE_PDF


def slides_markdown(material_dir: Path) -> Path:
    """Return where a slide deck's Markdown lives."""
    return material_dir / _CONTENTS_DIR / _SLIDES_FILE


def check_destination(library_root: Path, material_id: str) -> Path:
    """Check that ``material_id`` names a new material folder and return its path.

    Nothing is created or modified. The id must be a relative path of ``/``-separated
    folder names made of letters, digits, ``.``, ``_``, and ``-``, none starting with
    ``.``, so it can never escape ``library_root``.

    Raises:
        CliError: ``invalid_request`` when the id breaks those rules or lies inside an
            existing material or interrupted parse, or under an existing file;
            ``destination_exists`` when the folder already exists, even empty.
    """
    segments = material_id.split("/")
    if not all(_SEGMENT.fullmatch(segment) for segment in segments):
        raise CliError(
            "invalid_request",
            f"invalid destination {material_id!r}: use a relative path of folder names made "
            "of letters, digits, '.', '_', '-', not starting with '.', for example ml/prml",
        )
    for depth in range(1, len(segments)):
        ancestor = "/".join(segments[:depth])
        ancestor_path = library_root / ancestor
        # A file (or dangling link) here would make creating the folders fail part way.
        if (ancestor_path.exists() or ancestor_path.is_symlink()) and not ancestor_path.is_dir():
            raise CliError(
                "invalid_request",
                f"invalid destination {material_id}: {ancestor} exists and is not a folder; "
                "choose a destination outside it",
            )
        if (ancestor_path / _METADATA_FILE).exists():
            raise CliError(
                "invalid_request",
                f"invalid destination {material_id}: it is inside material {ancestor}; "
                "choose a destination outside it",
            )
        # A crash between creating the folder and copying the PDF leaves it empty, which
        # looks like any other parent folder, so that interrupted parse can't be detected.
        if (ancestor_path / _SOURCE_PDF).exists() or (ancestor_path / _CONTENTS_DIR).exists():
            raise CliError(
                "invalid_request",
                f"invalid destination {material_id}: it is inside {ancestor}, which looks "
                "like an interrupted parse; delete that folder by hand or choose a "
                "destination outside it",
            )
    path = library_root / material_id
    if path.exists() or path.is_symlink():
        raise _destination_exists(material_id)
    return path


def create_destination(library_root: Path, material_id: str) -> Path:
    """Create the empty folder for ``material_id``, with any missing parent folders.

    Raises:
        CliError: as ``check_destination``; ``destination_exists`` also when the folder
            appears between that check and creation.
    """
    path = check_destination(library_root, material_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        # Exclusive creation, so a folder appearing after any earlier check is still refused.
        path.mkdir()
    except FileExistsError:
        raise _destination_exists(material_id) from None
    return path


def _destination_exists(material_id: str) -> CliError:
    return CliError("destination_exists", f"{material_id} already exists; choose a new destination")


def write_slides(material_dir: Path, markdown: str) -> None:
    """Store a slide deck's Markdown in the material's contents."""
    path = slides_markdown(material_dir)
    path.parent.mkdir()
    path.write_text(markdown, encoding="utf-8")


def write_record(material_dir: Path, record: MaterialRecord) -> None:
    """Write ``material.json`` atomically, so readers never see a partial file."""
    payload = json.dumps(asdict(record), indent=2) + "\n"
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=material_dir, prefix=".material-", delete=False
    ) as handle:
        handle.write(payload)
    os.replace(handle.name, material_dir / _METADATA_FILE)


def ready_materials(library_root: Path) -> list[Material]:
    """Return every ready material under ``library_root``, sorted by material id.

    Discovery stops at a material folder and never descends into it.
    """
    found: list[Material] = []
    for directory, subdirs, files in os.walk(library_root):
        if _METADATA_FILE in files:
            subdirs.clear()
            material = _load(library_root, Path(directory))
            if material.record.status is Status.READY:
                found.append(material)
        else:
            subdirs[:] = [name for name in subdirs if not name.startswith(".")]
    return sorted(found, key=lambda material: material.material_id)


def get_ready_material(library_root: Path, material_id: str) -> Material:
    """Return the ready material with exactly the id ``material_id``.

    Raises:
        CliError: ``not_found`` when no material has that id or it isn't ready.
    """
    path = library_root / material_id
    if not (path / _METADATA_FILE).is_file():
        raise CliError("not_found", f"no ready material '{material_id}'")
    material = _load(library_root, path)
    if material.record.status is not Status.READY:
        raise CliError("not_found", f"{material_id} is not ready ({material.record.status})")
    return material


def _load(library_root: Path, path: Path) -> Material:
    raw = json.loads((path / _METADATA_FILE).read_text(encoding="utf-8"))
    record = MaterialRecord(
        **{**raw, "type": MaterialType(raw["type"]), "status": Status(raw["status"])}
    )
    return Material(material_id=path.relative_to(library_root).as_posix(), path=path, record=record)
