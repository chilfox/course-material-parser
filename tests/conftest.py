"""Shared fixtures for the CLI seam: a temporary library, its settings file, and runners."""

import json
from dataclasses import dataclass
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
    """

    document: DoclingDocument | None = None
    failure: str | None = None
    partial: bool = False

    def convert(self, pdf: Path, *, device: str, ocr: bool):
        """Return the configured outcome without looking at the PDF."""
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


def assert_error(result: CliResult, code: str, *fragments: str) -> None:
    """Assert ``result`` failed with the error ``code`` and a message holding ``fragments``."""
    assert result.exit_code == 1
    assert result.stdout == ""
    assert result.error["error"] == code
    assert result.error["message"]
    for fragment in fragments:
        assert fragment in result.error["message"]


def parse_slides(run_parse, dest: str = "ml/week3-slides") -> None:
    """Parse the text-layer fixture as slides into ``dest`` and assert it succeeded."""
    result = run_parse("start", "--pdf", str(TEXT_LAYER_PDF), "--dest", dest, "--type", "slides")
    assert result.exit_code == 0, result.stderr


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
