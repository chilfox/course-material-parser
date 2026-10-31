"""Load ``settings.toml`` from the skill directory and check its basic shape.

The default path is derived from the install location, so the CLIs behave the same from
any working directory. Callers (tests) can inject another path.
"""

import tomllib
from dataclasses import MISSING, dataclass, fields
from pathlib import Path
from typing import Literal, get_args

from course_material_parser.cli_output import CliError

SKILL_DIR = Path(__file__).resolve().parents[2]
DEFAULT_SETTINGS_PATH = SKILL_DIR / "settings.toml"

Device = Literal["cpu", "mps", "cuda"]
DEVICES: tuple[str, ...] = get_args(Device)


@dataclass(frozen=True)
class Settings:
    """Settings shared by both CLIs.

    ``library_root`` has ``~`` expanded and ``device`` is one of ``DEVICES``. Optional keys
    take the defaults below when absent.
    """

    library_root: Path
    device: Device
    allow_ocr: bool = True
    combined_read_max_chars: int = 60000


_REQUIRED_KEYS = [f.name for f in fields(Settings) if f.default is MISSING]
_OPTIONAL_KEYS = [f.name for f in fields(Settings) if f.default is not MISSING]


def load_settings(path: Path | None = None) -> Settings:
    """Read the settings file at ``path`` (default: the skill directory's ``settings.toml``).

    Raises:
        CliError: ``settings_error`` when the file is missing, is not valid TOML, lacks a
            required key, or names an unknown ``device``.
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
    if raw["device"] not in DEVICES:
        raise CliError(
            "settings_error",
            f"settings.toml device must be one of {', '.join(DEVICES)}, not {raw['device']!r}",
        )

    return Settings(
        library_root=Path(raw["library_root"]).expanduser(),
        device=raw["device"],
        **{key: raw[key] for key in _OPTIONAL_KEYS if key in raw},
    )
