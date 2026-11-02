"""Shared fixtures for the CLI seam: a temporary library, its settings file, and runners."""

import json
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from docling_core.types.doc import DoclingDocument

from course_material_parser import parse_command, read_command
from course_material_parser.docling_conversion import (
    ConversionFailed,
    Converted,
    PartiallyConverted,
)
from doc_builders import slide_deck

FIXTURES = Path(__file__).resolve().parent / "fixtures"
TEXT_LAYER_PDF = FIXTURES / "text_layer.pdf"
IMAGE_ONLY_PDF = FIXTURES / "image_only.pdf"


@dataclass
class CliResult:
    """What a caller observes from one CLI invocation."""

    exit_code: int
    stdout: str
    stderr: str

    @property
    def json(self):
        """The JSON result printed on stdout."""
        return json.loads(self.stdout)

    @property
    def error(self):
        """The JSON error envelope printed on stderr."""
        return json.loads(self.stderr)


@dataclass
class FakeConverter:
    """Stands in for Docling at the docling_conversion boundary.

    Set ``failure`` to report a failed conversion, plus ``partial`` for a partial one.
    ``calls`` records the ``ocr`` choice of every conversion, in order, so tests can check
    what reached the converter and whether it was called at all.
    """

    document: DoclingDocument | None = None
    failure: str | None = None
    partial: bool = False
    calls: list[dict] = field(default_factory=list)

    def convert(self, pdf: Path, *, device: str, ocr: bool):
        """Record the call and return the configured outcome without looking at the PDF."""
        self.calls.append({"ocr": ocr})
        if self.failure is not None and self.partial:
            return PartiallyConverted(document=self.document, message=self.failure)
        if self.failure is not None:
            return ConversionFailed(message=self.failure)
        return Converted(document=self.document)


@pytest.fixture
def library(tmp_path) -> Path:
    root = tmp_path / "library"
    root.mkdir()
    return root


@pytest.fixture
def settings_path(tmp_path, library) -> Path:
    path = tmp_path / "skill" / "settings.toml"
    path.parent.mkdir()
    write_settings(path, library)
    return path


@pytest.fixture
def converter() -> FakeConverter:
    return FakeConverter(
        document=slide_deck(
            {1: ["1 Introduction", "Slide one body."], 2: ["2 Methods", "Slide two body."]},
            page_count=2,
        )
    )


def assert_error(result: CliResult, code: str, *fragments: str) -> None:
    """Assert ``result`` failed with the error ``code`` and a message holding ``fragments``."""
    assert result.exit_code == 1
    assert result.stdout == ""
    assert result.error["error"] == code
    assert result.error["message"]
    for fragment in fragments:
        assert fragment in result.error["message"]


def write_settings(settings_path: Path, library_root, extra: str = "", *, device="cpu") -> None:
    """Write a settings file with ``library_root``, ``device``, and any ``extra`` TOML lines."""
    settings_path.write_text(f'library_root = "{library_root}"\ndevice = "{device}"\n{extra}')


def start_parse(
    run_parse,
    *flags: str,
    dest: str = "ml/deck",
    pdf: Path | str = TEXT_LAYER_PDF,
    material_type: str = "slides",
) -> CliResult:
    """Run ``parse start`` for ``pdf`` into ``dest`` with any extra ``flags``."""
    return run_parse("start", "--pdf", str(pdf), "--dest", dest, "--type", material_type, *flags)


def parse_slides(run_parse, dest: str = "ml/week3-slides") -> None:
    """Parse the text-layer fixture as slides into ``dest`` and assert it succeeded."""
    result = start_parse(run_parse, dest=dest)
    assert result.exit_code == 0, result.stderr


def record_path(library: Path, dest: str) -> Path:
    """Return the ``material.json`` of the material at ``dest``."""
    return library / dest / "material.json"


def material_status(library: Path, dest: str = "ml/deck") -> str:
    """Return the status stored in the ``material.json`` of ``dest``."""
    return json.loads(record_path(library, dest).read_text())["status"]


def set_material_status(library: Path, dest: str, status: str) -> None:
    """Overwrite the status in the ``material.json`` of ``dest``, keeping the rest."""
    path = record_path(library, dest)
    path.write_text(json.dumps({**json.loads(path.read_text()), "status": status}))


def _runner(capsys, main):
    def run(*argv: str) -> CliResult:
        exit_code = main(list(argv))
        captured = capsys.readouterr()
        return CliResult(exit_code, captured.out, captured.err)

    return run


@pytest.fixture
def run_parse(capsys, settings_path, converter):
    return _runner(
        capsys,
        lambda argv: parse_command.main(argv, settings_path=settings_path, converter=converter),
    )


@pytest.fixture
def run_read(capsys, settings_path):
    return _runner(capsys, lambda argv: read_command.main(argv, settings_path=settings_path))
