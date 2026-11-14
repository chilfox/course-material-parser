"""Human-facing setup command for the models the user's settings require."""

from collections.abc import Callable, Sequence
from pathlib import Path

from course_material_parser.cli_output import JsonArgumentParser, run_cli
from course_material_parser.docling_conversion import (
    Model,
    download_model,
    models_directory,
    required_models,
)
from course_material_parser.settings import load_settings, require_device_available


def main(
    argv: Sequence[str] | None = None,
    *,
    settings_path: Path | None = None,
    downloader: Callable[[Model, Path], None] | None = None,
    model_directory: Path | None = None,
) -> int:
    """Download missing models, with injectable settings and external download boundary."""
    return run_cli(lambda: _run(argv, settings_path, downloader, model_directory))


def _run(
    argv: Sequence[str] | None,
    settings_path: Path | None,
    downloader: Callable[[Model, Path], None] | None,
    model_directory: Path | None,
) -> str:
    JsonArgumentParser(
        prog="download-models",
        description="Download missing models for settings.toml; keep models already present.",
    ).parse_args(argv)
    settings = load_settings(settings_path)
    require_device_available(settings)
    directory = model_directory if model_directory is not None else models_directory()
    fetch = downloader if downloader is not None else download_model
    lines = []
    for model in required_models(device=settings.device, ocr=settings.allow_ocr):
        if (directory / model.folder).is_dir():
            lines.append(f"Skipped {model.name} (already present)")
        else:
            fetch(model, directory)
            lines.append(f"Fetched {model.name}")
    lines.append(str(directory))
    return "\n".join(lines) + "\n"
