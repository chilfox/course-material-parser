"""Load and validate ``settings.toml`` from the skill directory.

The default path is derived from the install location, so the CLIs behave the same from
any working directory. Callers (tests) can inject another path.
"""

import tomllib
from dataclasses import dataclass
from pathlib import Path

from course_material_parser.cli_output import CliError

SKILL_DIR = Path(__file__).resolve().parents[2]
DEFAULT_SETTINGS_PATH = SKILL_DIR / "settings.toml"

_REQUIRED_KEYS = ("library_root", "device")


@dataclass(frozen=True)
class Settings:
    """Validated settings shared by both CLIs."""

    library_root: Path
    device: str
    allow_ocr: bool = True
    combined_read_max_chars: int = 60000


def load_settings(path: Path | None = None) -> Settings:
    """Read the settings file at ``path`` (default: the skill directory's ``settings.toml``).

    Raises:
        CliError: ``settings_error`` when the file is missing, is not valid TOML, or lacks
            a required key.
    """
    path = path or DEFAULT_SETTINGS_PATH
    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise CliError(
            "settings_error",
            "settings.toml not found: copy settings.example.toml to settings.toml "
            "and set library_root and device",
        ) from None
    except tomllib.TOMLDecodeError as error:
        raise CliError("settings_error", f"settings.toml is not valid TOML: {error}") from None

    missing = [key for key in _REQUIRED_KEYS if key not in raw]
    if missing:
        raise CliError(
            "settings_error", f"settings.toml is missing required key(s): {', '.join(missing)}"
        )

    return Settings(
        library_root=Path(raw["library_root"]).expanduser(),
        device=raw["device"],
        allow_ocr=raw.get("allow_ocr", True),
        combined_read_max_chars=raw.get("combined_read_max_chars", 60000),
    )
