"""The split plan format: how a pending textbook is organized into chapters and units.

A plan is JSON written by the agent, at any path, and fixed with its edit tool; its
format is documented once, in ``parse propose --help``.

``contents`` is in reading order and shaped like ``read toc``: each entry is a standalone
reading unit or a chapter, told apart by ``units``. Nesting units under their chapter
makes a chapter's units contiguous and chapters ordered by construction. Every field is
required and unknown fields are rejected, so a typo (``"kidn"``, or a stray key that
looks meaningful) is reported instead of silently changing the plan.

Validation never repairs a plan: it reports every problem at once, so the agent can fix
them all in one pass. Selectors are inclusive ranges of source pages. Adjacent units in
reading order may share only their boundary page (boundary-page overlap): a section
starting part way down page 16 makes 16 the last page of the one before. A wider overlap
would repeat whole pages in two units, which is never a boundary, so it is rejected.
Several units may still lie on one shared page.
"""

import re
from collections.abc import Iterator
from dataclasses import dataclass
from enum import StrEnum

from course_material_parser.cli_output import CliError
from course_material_parser.markdown_writer import PdfPages

PLAN_VERSION = 1
# Not starting with "-", so an id can't be mistaken for a flag in `read get --id`.
_ID = re.compile(r"[a-z0-9][a-z0-9-]*")
_CHAPTER_FIELDS = ("id", "title", "units")
_UNIT_FIELDS = ("id", "title", "kind", "selector")
_PLAN_FIELDS = ("version", "extraction_id", "contents")
_SELECTOR_FIELDS = ("kind", "start", "end")


class UnitKind(StrEnum):
    """Whether a reading unit is a numbered section, which decides its file name."""

    SECTION = "section"
    OTHER = "other"


@dataclass(frozen=True)
class Unit:
    """A reading unit: its unit id, title, kind, and the source pages it selects."""

    id: str
    title: str
    kind: UnitKind
    selector: PdfPages

    @property
    def first_page(self) -> int:
        """The first source page the unit selects."""
        return self.selector.start

    @property
    def last_page(self) -> int:
        """The last source page the unit selects."""
        return self.selector.end


@dataclass(frozen=True)
class Chapter:
    """A chapter: its unit id, title, and its units in reading order (at least one)."""

    id: str
    title: str
    units: tuple[Unit, ...]


@dataclass(frozen=True)
class SplitPlan:
    """A valid split plan, tied to the extraction it was written for."""

    extraction_id: str
    contents: tuple[Unit | Chapter, ...]

    def units(self) -> Iterator[Unit]:
        """Yield every reading unit in reading order, chapter units in place."""
        for entry in self.contents:
            if isinstance(entry, Chapter):
                yield from entry.units
            else:
                yield entry


def parse_plan(raw: object, *, material_id: str, page_count: int, extraction_id: str) -> SplitPlan:
    """Return the split plan that the decoded JSON ``raw`` describes, once it is valid.

    Args:
        raw: The decoded plan file.
        material_id: The pending textbook, named in error messages.
        page_count: Its number of source pages, which the units must cover exactly.
        extraction_id: Its pending extraction, which the plan must name.

    Raises:
        CliError: ``invalid_plan`` with every problem found, in plan order, as
            ``problems`` and in the message.
    """
    validator = _Validator(
        material_id=material_id, page_count=page_count, extraction_id=extraction_id
    )
    plan = validator.plan(raw)
    if validator.problems:
        count = len(validator.problems)
        raise CliError(
            "invalid_plan",
            f"{count} problem{'s' if count > 1 else ''} in the plan: "
            + "; ".join(validator.problems),
            problems=validator.problems,
        )
    assert plan is not None
    return plan


class _Validator:
    """Collects every problem of one plan while building the parts that are valid."""

    def __init__(self, *, material_id: str, page_count: int, extraction_id: str) -> None:
        self.material_id = material_id
        self.page_count = page_count
        self.extraction_id = extraction_id
        self.problems: list[str] = []
        self._seen_ids: set[str] = set()
        # Every unit's page range, labelled as in messages, so page problems are found
        # even in units with other problems.
        self._ranges: list[tuple[str, PdfPages]] = []
        self._ranges_known = True

    def plan(self, raw: object) -> SplitPlan | None:
        if not self._fields(raw, "plan", _PLAN_FIELDS):
            return None
        assert isinstance(raw, dict)
        if type(raw["version"]) is not int or raw["version"] != PLAN_VERSION:
            self.problems.append(
                f"version {_quoted(raw['version'])} is not supported: use {PLAN_VERSION}"
            )
        if raw["extraction_id"] != self.extraction_id:
            self.problems.append(
                f"extraction_id {_quoted(raw['extraction_id'])} does not match the pending "
                f"extraction {self.extraction_id} of {self.material_id}; "
                "inspect it and update the plan"
            )
        contents = self._contents(raw["contents"])
        # Order and coverage are only meaningful when every unit's pages are known.
        if self._ranges_known:
            self._check_order()
            self._check_coverage()
        if self.problems:
            return None
        return SplitPlan(extraction_id=self.extraction_id, contents=tuple(contents))

    def _contents(self, raw: object) -> list[Unit | Chapter]:
        if not isinstance(raw, list):
            self.problems.append("plan: contents is not a list")
            return []
        if not raw:
            self.problems.append("plan: contents is empty")
        found: list[Unit | Chapter] = []
        for index, entry in enumerate(raw):
            where = f"contents[{index}]"
            if isinstance(entry, dict) and "units" in entry:
                chapter = self._chapter(entry, where)
                if chapter is not None:
                    found.append(chapter)
            else:
                unit = self._unit(entry, where)
                if unit is not None:
                    found.append(unit)
        return found

    def _chapter(self, raw: dict, where: str) -> Chapter | None:
        label = self._label("chapter", raw, where)
        if not self._fields(raw, label, _CHAPTER_FIELDS):
            return None
        valid = self._id_and_title(raw, label)
        units_raw = raw["units"]
        if not isinstance(units_raw, list):
            self.problems.append(f"{label}: units is not a list")
            self._ranges_known = False
            return None
        if not units_raw:
            self.problems.append(f"{label}: no units")
            return None
        units = [self._unit(u, f"{where}.units[{i}]") for i, u in enumerate(units_raw)]
        if not valid or None in units:
            return None
        return Chapter(raw["id"], raw["title"], tuple(u for u in units if u is not None))

    def _unit(self, raw: object, where: str) -> Unit | None:
        label = self._label("unit", raw, where)
        if not isinstance(raw, dict) or "selector" not in raw:
            self._ranges_known = False
        if not self._fields(raw, label, _UNIT_FIELDS):
            return None
        assert isinstance(raw, dict)
        selector = self._selector(raw["selector"], label)
        if selector is None:
            self._ranges_known = False
        else:
            self._ranges.append((label, selector))
        valid = self._id_and_title(raw, label)
        kind = raw["kind"]
        if kind not in tuple(UnitKind):
            self.problems.append(f"{label}: kind {_quoted(kind)} is not section or other")
            valid = False
        if not valid or selector is None:
            return None
        return Unit(raw["id"], raw["title"], UnitKind(kind), selector)

    def _selector(self, raw: object, label: str) -> PdfPages | None:
        if not self._fields(raw, f"{label}: selector", _SELECTOR_FIELDS):
            return None
        assert isinstance(raw, dict)
        if raw["kind"] != "pdf_pages":
            self.problems.append(f"{label}: selector kind {_quoted(raw['kind'])} is not pdf_pages")
            return None
        bounds = [raw["start"], raw["end"]]
        valid = True
        for name, value in zip(("start", "end"), bounds, strict=True):
            if not isinstance(value, int) or isinstance(value, bool):
                self.problems.append(f"{label}: selector {name} is not an integer")
                valid = False
        if not valid:
            return None
        start, end = bounds
        if end < start:
            self.problems.append(f"{label}: pages {start}-{end} reversed")
            return None
        if start < 1 or end > self.page_count:
            self.problems.append(
                f"{label}: pages {start}-{end} out of range: "
                f"{self.material_id} has pages 1-{self.page_count}"
            )
            return None
        return PdfPages(start=start, end=end)

    def _id_and_title(self, raw: dict, label: str) -> bool:
        valid = True
        unit_id = raw["id"]
        if not isinstance(unit_id, str) or not _ID.fullmatch(unit_id):
            self.problems.append(
                f"{label}: invalid id {_quoted(unit_id)}: use lowercase letters, digits, and '-', "
                "not starting with '-'"
            )
            valid = False
        elif unit_id in self._seen_ids:
            self.problems.append(
                f"{label}: duplicate id '{unit_id}': ids must be unique in the plan"
            )
            valid = False
        else:
            self._seen_ids.add(unit_id)
        title = raw["title"]
        if not isinstance(title, str):
            self.problems.append(f"{label}: title is not a string")
            valid = False
        elif not title.strip():
            self.problems.append(f"{label}: empty title")
            valid = False
        return valid

    def _fields(self, raw: object, label: str, fields: tuple[str, ...]) -> bool:
        """Report a non-object or missing and unknown fields; return whether all are present."""
        if not isinstance(raw, dict):
            self.problems.append(f"{label}: not an object")
            return False
        missing = [name for name in fields if name not in raw]
        for name in missing:
            self.problems.append(f"{label}: missing field '{name}'")
        for name in raw:
            if name not in fields:
                self.problems.append(f"{label}: unknown field '{name}'")
        return not missing

    def _check_order(self) -> None:
        for (before, earlier), (after, later) in zip(self._ranges, self._ranges[1:], strict=False):
            if later.start < earlier.start:
                self.problems.append(
                    f"{after}: starts on page {later.start}, "
                    f"before {before} on page {earlier.start}"
                )
            elif later.start < earlier.end:
                self.problems.append(
                    f"{after}: pages {_span(later)} overlap {before} (pages {_span(earlier)}) "
                    "by more than one boundary page"
                )

    def _check_coverage(self) -> None:
        covered = set()
        for _label, pages in self._ranges:
            covered.update(range(pages.start, pages.end + 1))
        missing = [page for page in range(1, self.page_count + 1) if page not in covered]
        for start, end in _runs(missing):
            if start == end:
                self.problems.append(f"page {start} is in no unit")
            else:
                self.problems.append(f"pages {start}-{end} are in no unit")

    @staticmethod
    def _label(kind: str, raw: object, where: str) -> str:
        """Name an entry by its id when it has a usable one, else by its place in the plan."""
        if isinstance(raw, dict) and isinstance(raw.get("id"), str) and raw["id"]:
            return f"{kind} {raw['id']}"
        return where


def _quoted(value: object) -> str:
    """Return ``value`` for a message, quoting strings so they read as plan values."""
    return f"'{value}'" if isinstance(value, str) else str(value)


def _span(pages: PdfPages) -> str:
    return f"{pages.start}-{pages.end}"


def _runs(pages: list[int]) -> Iterator[tuple[int, int]]:
    """Yield the inclusive ``(start, end)`` runs of consecutive numbers in sorted ``pages``."""
    if not pages:
        return
    start = previous = pages[0]
    for page in pages[1:]:
        if page != previous + 1:
            yield start, previous
            start = page
        previous = page
    yield start, previous


def plan_json(plan: SplitPlan) -> dict:
    """Return ``plan`` in its JSON file format, as ``parse_plan`` reads it."""
    return {
        "version": PLAN_VERSION,
        "extraction_id": plan.extraction_id,
        "contents": [
            {"id": e.id, "title": e.title, "units": [_unit_json(u) for u in e.units]}
            if isinstance(e, Chapter)
            else _unit_json(e)
            for e in plan.contents
        ],
    }


def _unit_json(unit: Unit) -> dict:
    selector = unit.selector
    return {
        "id": unit.id,
        "title": unit.title,
        "kind": unit.kind.value,
        "selector": {"kind": selector.kind, "start": selector.start, "end": selector.end},
    }


def summary(plan: SplitPlan) -> dict:
    """Return the plan as an approval summary: ``contents`` like ``read toc``, and overlaps.

    Each unit has ``pages`` ``[start, end]``; a chapter's ``pages`` span its units.
    ``overlaps`` lists every boundary page shared by adjacent units, with the ids of all
    the units on it in reading order.
    """
    contents = []
    for entry in plan.contents:
        if isinstance(entry, Chapter):
            units = [_unit_summary(unit) for unit in entry.units]
            pages = [entry.units[0].first_page, entry.units[-1].last_page]
            contents.append({"id": entry.id, "title": entry.title, "pages": pages, "units": units})
        else:
            contents.append(_unit_summary(entry))
    return {"contents": contents, "overlaps": _overlaps(plan)}


def _unit_summary(unit: Unit) -> dict:
    return {"id": unit.id, "title": unit.title, "pages": [unit.first_page, unit.last_page]}


def _overlaps(plan: SplitPlan) -> list[dict]:
    shared: dict[int, list[str]] = {}
    units = list(plan.units())
    for before, after in zip(units, units[1:], strict=False):
        if before.last_page == after.first_page:
            ids = shared.setdefault(after.first_page, [before.id])
            if ids[-1] != before.id:
                ids.append(before.id)
            ids.append(after.id)
    return [{"page": page, "units": ids} for page, ids in sorted(shared.items())]
