"""Map material ids to folders under ``library_root`` and own the stored-material layout.

A material folder holds ``source.pdf``, ``material.json``, and ``contents/``. A folder
without ``material.json`` is an interrupted parse, which readers ignore. Other modules ask
this one for paths instead of building them, so the layout lives in one place.

A ready textbook's ``contents/`` holds its standalone units directly and each chapter's
units in a folder named after the chapter id with its number zero-padded, so folders sort
in reading order (``chapter-01``). A numbered section is ``section_<id>.md`` and any other
unit ``<id>.md``, so a file name says what it holds. There are no chapter files: a chapter
is its units.
"""

import json
import os
import re
import shutil
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from enum import StrEnum
from pathlib import Path
from typing import assert_never

from course_material_parser.atomic_write import write_atomically
from course_material_parser.cli_output import CliError

FORMAT_VERSION = 1
_METADATA_FILE = "material.json"
_SOURCE_PDF = "source.pdf"
_CONTENTS_DIR = "contents"
_SLIDES_FILE = "slides.md"
_EXTRACTION_FILE = "extraction.json"
_PLAN_FILE = "plan.json"
# One folder name: letters, digits, ".", "_", "-", not starting with "." (so ".", "..",
# and hidden folders, which discovery skips, are impossible).
_SEGMENT = re.compile(r"[A-Za-z0-9_-][A-Za-z0-9._-]*")
_CHAPTER_NUMBER = re.compile(r"\d+")


class MaterialType(StrEnum):
    """The kind of source PDF a material was parsed from."""

    SLIDES = "slides"
    TEXTBOOK = "textbook"


class Status(StrEnum):
    """Where a material is in its lifecycle; only ``READY`` material is readable."""

    PENDING = "pending"
    READY = "ready"
    FAILED = "failed"


class UnitKind(StrEnum):
    """Whether a reading unit is a numbered section, which decides its file name."""

    SECTION = "section"
    OTHER = "other"


@dataclass(frozen=True)
class ChapterRecord:
    """A chapter of a ready textbook: its unit id and title."""

    id: str
    title: str


@dataclass(frozen=True)
class UnitRecord:
    """A reading unit of a ready textbook.

    ``chapter`` is the id of the chapter it belongs to, or ``None`` for a standalone unit.
    ``pages`` is its approved inclusive ``(start, end)`` range of source pages.
    """

    id: str
    title: str
    kind: UnitKind
    chapter: str | None
    pages: tuple[int, int]


@dataclass(frozen=True)
class MaterialRecord:
    """The contents of ``material.json``.

    ``extraction_id`` identifies the stored extraction of a pending textbook, so a split
    plan written for one extraction can't be applied to another; it is ``None`` otherwise.
    ``chapters`` and ``units`` are a ready textbook's, in reading order, and empty otherwise.
    """

    type: MaterialType
    status: Status
    source_filename: str
    pages: int
    extraction_id: str | None = None
    chapters: tuple[ChapterRecord, ...] = ()
    units: tuple[UnitRecord, ...] = ()
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


def unit_markdown(material_dir: Path, unit: UnitRecord) -> Path:
    """Return where a ready textbook's reading unit ``unit`` lives."""
    name = f"section_{unit.id}.md" if unit.kind is UnitKind.SECTION else f"{unit.id}.md"
    contents = material_dir / _CONTENTS_DIR
    if unit.chapter is None:
        return contents / name
    return contents / chapter_folder(unit.chapter) / name


def chapter_folder(chapter_id: str) -> str:
    """Return the folder name of the chapter ``chapter_id``: its numbers zero-padded to two.

    Padding makes folders sort in reading order (``chapter-01`` before ``chapter-10``).
    Distinct ids can share a folder name (``chapter-1`` and ``chapter-01``), which a split
    plan must therefore rule out.
    """
    return _CHAPTER_NUMBER.sub(lambda number: number.group().zfill(2), chapter_id)


def extraction_json(material_dir: Path) -> Path:
    """Return where a pending textbook's stored DoclingDocument JSON lives."""
    return material_dir / _EXTRACTION_FILE


def plan_snapshot(material_dir: Path) -> Path:
    """Return where a pending textbook's proposed split plan snapshot lives."""
    return material_dir / _PLAN_FILE


def split_proposal(material_dir: Path) -> Path:
    """Return where the pending textbook's complete split proposal lives."""
    return material_dir / "split-proposal.md"


def write_split_proposal(material_dir: Path, proposal: str) -> None:
    """Replace the complete split proposal using the snapshot's atomic write mechanism."""
    write_atomically(split_proposal(material_dir), proposal.encode("utf-8"))


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
        if _looks_interrupted(ancestor_path):
            raise _invalid_destination(
                material_id,
                f"it is inside {ancestor}, which looks like an interrupted parse",
                alternative="delete that folder by hand",
            )
    path = library_root / material_id
    if path.exists() or path.is_symlink():
        raise _destination_exists(material_id, path)
    return path


def _looks_interrupted(path: Path) -> bool:
    """Return whether ``path`` holds a parse's files; callers have ruled out ``material.json``."""
    # A crash between creating the folder and copying the PDF leaves it empty, which
    # looks like any other parent folder, so that interrupted parse can't be detected.
    return (path / _SOURCE_PDF).exists() or (path / _CONTENTS_DIR).exists()


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
        raise _destination_exists(material_id, path) from None
    return path


def _destination_exists(material_id: str, path: Path) -> CliError:
    if path.is_dir() and not (path / _METADATA_FILE).exists():
        return CliError(
            "destination_exists",
            f"{material_id} is an interrupted parse; delete it by hand or choose a new destination",
        )
    return CliError("destination_exists", f"{material_id} already exists; choose a new destination")


def write_slides(material_dir: Path, markdown: str) -> None:
    """Store a slide deck's Markdown in the material's contents."""
    path = slides_markdown(material_dir)
    path.parent.mkdir()
    path.write_text(markdown, encoding="utf-8")


def write_textbook_units(material_dir: Path, units: Iterable[tuple[UnitRecord, str]]) -> None:
    """Store a textbook's reading units, each ``(unit, markdown)``, as its whole contents.

    Any ``contents/`` already there can only be left by a finalization that stopped part
    way, since a pending textbook has none, so it is replaced rather than merged into.
    """
    contents = material_dir / _CONTENTS_DIR
    if contents.exists():
        shutil.rmtree(contents)
    contents.mkdir()
    for unit, markdown in units:
        path = unit_markdown(material_dir, unit)
        path.parent.mkdir(exist_ok=True)
        path.write_text(markdown, encoding="utf-8")


def remove_pending_artifacts(material_dir: Path) -> None:
    """Delete a finalized textbook's extraction, plan snapshot and split proposal."""
    extraction_json(material_dir).unlink(missing_ok=True)
    plan_snapshot(material_dir).unlink(missing_ok=True)
    split_proposal(material_dir).unlink(missing_ok=True)


def read_plan_snapshot(material_dir: Path) -> object | None:
    """Return the decoded split plan snapshot of a pending textbook, or ``None`` if none."""
    path = plan_snapshot(material_dir)
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def write_plan_snapshot(material_dir: Path, plan: dict) -> None:
    """Replace the pending textbook's split plan snapshot atomically with ``plan``."""
    payload = json.dumps(plan, indent=2, ensure_ascii=False) + "\n"
    write_atomically(plan_snapshot(material_dir), payload.encode("utf-8"))


def write_record(material_dir: Path, record: MaterialRecord) -> None:
    """Write ``material.json`` atomically, so readers never see a partial file."""
    payload = json.dumps(asdict(record), indent=2) + "\n"
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
    material = _find_material(library_root, material_id)
    if material is None:
        raise CliError("not_found", f"no ready material '{material_id}'")
    if material.record.status is not Status.READY:
        raise CliError("not_found", f"{material_id} is not ready ({material.record.status})")
    return material


def get_pending_material(library_root: Path, material_id: str) -> Material:
    """Return the pending textbook with exactly the id ``material_id``, awaiting its split.

    The id is matched as strictly as in ``get_ready_material``.

    Raises:
        CliError: ``not_found`` when no material has that id, saying how to fix it when
            the folder is an interrupted parse or the material is ready or failed.
    """
    material = _find_material(library_root, material_id)
    if material is None:
        if _exists_exactly(library_root, material_id) and _looks_interrupted(
            library_root / material_id
        ):
            raise CliError(
                "not_found",
                f"{material_id} is an interrupted parse; delete that folder by hand or parse "
                "into a new destination",
            )
        raise CliError(
            "not_found", f"no material '{material_id}'; parse it first with `parse start`"
        )
    match material.record.status:
        case Status.PENDING:
            return material
        case Status.READY:
            fix = "it is ready; read it with `read`"
        case Status.FAILED:
            fix = "its parse failed; parse again into a new destination"
        case unhandled:
            assert_never(unhandled)
    raise CliError("not_found", f"{material_id} is not pending ({material.record.status}): {fix}")


def _find_material(library_root: Path, material_id: str) -> Material | None:
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
        **{
            **raw,
            "type": MaterialType(raw["type"]),
            "status": Status(raw["status"]),
            # Records written before textbooks could be finalized have no chapters or units.
            "chapters": tuple(ChapterRecord(**chapter) for chapter in raw.get("chapters", [])),
            "units": tuple(
                UnitRecord(
                    **{**unit, "kind": UnitKind(unit["kind"]), "pages": tuple(unit["pages"])}
                )
                for unit in raw.get("units", [])
            ),
        }
    )
    return Material(material_id=path.relative_to(library_root).as_posix(), path=path, record=record)
