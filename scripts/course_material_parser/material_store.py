"""Map material ids to folders under ``library_root`` and own the stored-material layout.

A material folder holds ``source.pdf``, ``material.json``, and ``contents/``. A folder
without ``material.json`` is an interrupted parse, which readers ignore. Other modules ask
this one for paths instead of building them, so the layout lives in one place.
"""

import json
import os
import re
from dataclasses import asdict, dataclass
from enum import StrEnum
from pathlib import Path

from course_material_parser.atomic_write import write_atomically
from course_material_parser.cli_output import CliError

FORMAT_VERSION = 1
_METADATA_FILE = "material.json"
_SOURCE_PDF = "source.pdf"
_CONTENTS_DIR = "contents"
_SLIDES_FILE = "slides.md"
_EXTRACTION_FILE = "extraction.json"
# One folder name: letters, digits, ".", "_", "-", not starting with "." (so ".", "..",
# and hidden folders, which discovery skips, are impossible).
_SEGMENT = re.compile(r"[A-Za-z0-9_-][A-Za-z0-9._-]*")


class MaterialType(StrEnum):
    """The kind of source PDF a material was parsed from."""

    SLIDES = "slides"
    TEXTBOOK = "textbook"


class Status(StrEnum):
    """Where a material is in its lifecycle; only ``READY`` material is readable."""

    PENDING = "pending"
    READY = "ready"
    FAILED = "failed"


@dataclass(frozen=True)
class MaterialRecord:
    """The contents of ``material.json``.

    ``extraction_id`` identifies the stored extraction of a pending textbook, so a split
    plan written for one extraction can't be applied to another; it is ``None`` otherwise.
    """

    type: MaterialType
    status: Status
    source_filename: str
    pages: int
    extraction_id: str | None = None
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


def extraction_json(material_dir: Path) -> Path:
    """Return where a pending textbook's stored DoclingDocument JSON lives."""
    return material_dir / _EXTRACTION_FILE


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
    if not _is_well_formed(material_id):
        raise CliError(
            "invalid_request",
            f"invalid destination '{material_id}': use a relative path of folder names made "
            "of letters, digits, '.', '_', '-', not starting with '.', for example ml/prml",
        )
    _refuse_links_leaving(library_root, material_id)
    for depth in range(1, len(segments)):
        ancestor = "/".join(segments[:depth])
        ancestor_path = library_root / ancestor
        # A file (or dangling link) here would make creating the folders fail part way.
        if (ancestor_path.exists() or ancestor_path.is_symlink()) and not ancestor_path.is_dir():
            raise _invalid_destination(material_id, f"{ancestor} exists and is not a folder")
        if (ancestor_path / _METADATA_FILE).exists():
            raise _invalid_destination(material_id, f"it is inside material {ancestor}")
        # A crash between creating the folder and copying the PDF leaves it empty, which
        # looks like any other parent folder, so that interrupted parse can't be detected.
        if (ancestor_path / _SOURCE_PDF).exists() or (ancestor_path / _CONTENTS_DIR).exists():
            raise _invalid_destination(
                material_id,
                f"it is inside {ancestor}, which looks like an interrupted parse",
                alternative="delete that folder by hand",
            )
    path = library_root / material_id
    if path.exists() or path.is_symlink():
        raise _destination_exists(material_id)
    return path


def _is_well_formed(material_id: str) -> bool:
    """Return whether ``material_id`` follows the folder-name rules of a material id."""
    return all(_SEGMENT.fullmatch(segment) for segment in material_id.split("/"))


def _refuse_links_leaving(library_root: Path, material_id: str) -> None:
    """Refuse ``material_id`` when an existing folder link on its path leaves the library.

    The segment rules keep the id itself inside ``library_root``, but an existing
    symlinked folder could still redirect the destination elsewhere, so the deepest
    existing ancestor (or the destination itself) must resolve under the resolved root.
    """
    root = library_root.resolve()
    existing = library_root / material_id
    while not existing.exists() and existing != library_root:
        existing = existing.parent
    resolved = existing.resolve()
    if not resolved.is_relative_to(root):
        ancestor = existing.relative_to(library_root).as_posix()
        raise _invalid_destination(
            material_id, f"{ancestor} leads to {resolved}, outside library_root"
        )


def _invalid_destination(material_id: str, reason: str, *, alternative: str = "") -> CliError:
    """Return the ``invalid_request`` for a destination refused because of where it lies."""
    fix = f"{alternative} or choose" if alternative else "choose"
    return CliError(
        "invalid_request",
        f"invalid destination '{material_id}': {reason}; {fix} a destination outside it",
    )


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
    fields = {name: value for name, value in asdict(record).items() if value is not None}
    payload = json.dumps(fields, indent=2) + "\n"
    write_atomically(material_dir / _METADATA_FILE, payload.encode("utf-8"))


def ready_materials(library_root: Path, prefix: str | None = None) -> list[Material]:
    """Return every ready material under ``library_root``, sorted by material id.

    With ``prefix``, only materials whose id is ``prefix`` or starts with ``prefix/``:
    whole path segments, so ``ml`` matches ``ml/prml`` but not ``mlx/a``. Discovery stops
    at a material folder and never descends into it, and skips hidden folders.

    Raises:
        CliError: ``invalid_request`` when ``prefix`` isn't a well-formed material id.
    """
    if prefix is not None and not _is_well_formed(prefix):
        raise CliError(
            "invalid_request",
            f"invalid prefix '{prefix}': use leading folder names of a material id, "
            "for example ml, with no leading or trailing '/'",
        )
    found: list[Material] = []
    for directory, subdirs, files in os.walk(library_root):
        if _METADATA_FILE in files:
            subdirs.clear()
            material = _load(library_root, Path(directory))
            if material.record.status is Status.READY and _has_prefix(material.material_id, prefix):
                found.append(material)
        else:
            subdirs[:] = [name for name in subdirs if not name.startswith(".")]
    return sorted(found, key=lambda material: material.material_id)


def _has_prefix(material_id: str, prefix: str | None) -> bool:
    """Return whether ``material_id`` lies under ``prefix``, matching whole path segments.

    ``None`` matches every id; otherwise the id must equal ``prefix`` or start with
    ``prefix/``, so ``ml`` matches ``ml`` and ``ml/prml`` but not ``mlx/a``.
    """
    return prefix is None or material_id == prefix or material_id.startswith(prefix + "/")


def get_ready_material(library_root: Path, material_id: str) -> Material:
    """Return the ready material with exactly the id ``material_id``.

    The id is matched exactly, as discovery would list it: no fuzzy, case-insensitive,
    or ``.``/``..`` matching, and no symlinked folders, which discovery doesn't follow.

    Raises:
        CliError: ``not_found`` when no material has that id, naming its status when
            it exists but isn't ready.
    """
    material = find_material(library_root, material_id)
    if material is None:
        raise CliError("not_found", f"no ready material '{material_id}'")
    if material.record.status is not Status.READY:
        raise CliError("not_found", f"{material_id} is not ready ({material.record.status})")
    return material


def find_material(library_root: Path, material_id: str) -> Material | None:
    """Return the material with exactly the id ``material_id``, whatever its status.

    Returns ``None`` when no folder has that exact id or it holds no ``material.json``
    (an interrupted parse). Matching is as strict as in ``get_ready_material``.
    """
    path = library_root / material_id
    if not (_exists_exactly(library_root, material_id) and (path / _METADATA_FILE).is_file()):
        return None
    return _load(library_root, path)


def _exists_exactly(library_root: Path, material_id: str) -> bool:
    """Return whether ``material_id`` names a real folder, spelled exactly as on disk.

    Checking each name against its parent's listing matters on case-insensitive file
    systems, where ``ML/Deck`` would otherwise open ``ml/deck`` under a second id.
    """
    if not _is_well_formed(material_id):
        return False
    parent = library_root
    for segment in material_id.split("/"):
        path = parent / segment
        if path.is_symlink() or not path.is_dir() or segment not in os.listdir(parent):
            return False
        parent = path
    return True


def _load(library_root: Path, path: Path) -> Material:
    raw = json.loads((path / _METADATA_FILE).read_text(encoding="utf-8"))
    record = MaterialRecord(
        **{**raw, "type": MaterialType(raw["type"]), "status": Status(raw["status"])}
    )
    return Material(material_id=path.relative_to(library_root).as_posix(), path=path, record=record)
