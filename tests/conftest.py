"""Shared fixtures for the CLI seam: a temporary library, its settings file, and runners."""

import json
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from doc_builders import slide_deck
from docling_core.types.doc import DoclingDocument

from course_material_parser import parse_command, read_command
from course_material_parser.docling_conversion import (
    ConversionFailed,
    Converted,
    PartiallyConverted,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures"
TEXT_LAYER_PDF = FIXTURES / "text_layer.pdf"


@dataclass
class CliResult:
    """What a caller observes from one CLI invocation."""

    exit_code: int
    stdout: str
    stderr: str

    @property
    def json(self):
        return json.loads(self.stdout)

    @property
    def error(self):
        return json.loads(self.stderr)


@dataclass
class FakeConverter:
    """Stands in for Docling at the docling_conversion boundary.

    Set ``failure`` to report a failed conversion, plus ``partial`` for a partial one.
    """

    document: DoclingDocument | None = None
    failure: str | None = None
    partial: bool = False
    calls: list[dict] = field(default_factory=list)

    def convert(self, pdf: Path, *, device: str, ocr: bool):
        self.calls.append({"pdf": pdf, "device": device, "ocr": ocr})
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
    path.write_text(f'library_root = "{library}"\ndevice = "cpu"\n')
    return path


@pytest.fixture
def converter() -> FakeConverter:
    return FakeConverter(
        document=slide_deck(
            {1: ["1 Introduction", "Slide one body."], 2: ["2 Methods", "Slide two body."]},
            page_count=2,
        )
    )


@pytest.fixture
def run_parse(capsys, settings_path, converter):
    def run(*argv: str) -> CliResult:
        exit_code = parse_command.main(list(argv), settings_path=settings_path, converter=converter)
        captured = capsys.readouterr()
        return CliResult(exit_code, captured.out, captured.err)

    return run


@pytest.fixture
def run_read(capsys, settings_path):
    def run(*argv: str) -> CliResult:
        exit_code = read_command.main(list(argv), settings_path=settings_path)
        captured = capsys.readouterr()
        return CliResult(exit_code, captured.out, captured.err)

    return run
